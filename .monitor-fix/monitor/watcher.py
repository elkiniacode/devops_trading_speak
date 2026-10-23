"""Find teams, build their runs from transcripts, and keep each team's newest run live."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from .config import Settings
from .layout import build_layout
from .model import Snapshot
from .parser import RunParser, display_title
from .records import Item, parse_record
from .redact import Redactor
from .sources import JsonlTail, Member, Team, attach_transcripts, list_team_configs, load_team, now_iso, parse_iso
from .subagents import SubagentDiscovery

log = logging.getLogger("agent-monitor")


@dataclass
class Segment:
    """Teammates that worked together; a teammate joining after a long quiet spell starts a new run."""

    run_id: str
    members: list[Member]
    first_join: str
    last_activity: str
    start: str = ""
    end: str | None = None


def _last_timestamp(paths: list[Path]) -> str | None:
    """The newest record timestamp across transcripts (reads only each file's tail)."""
    latest = None
    for path in paths:
        try:
            with open(path, "rb") as fh:
                fh.seek(0, 2)
                fh.seek(max(0, fh.tell() - 256 * 1024))
                lines = fh.read().split(b"\n")
        except OSError:
            continue
        for line in reversed(lines):
            try:
                ts = json.loads(line).get("timestamp")
            except ValueError:
                continue
            if ts:
                latest = max(latest or ts, ts)
                break
    return latest


def plan_segments(team: Team, settings: Settings) -> list[Segment]:
    gap = timedelta(seconds=settings.idle_end_seconds)
    segments: list[Segment] = []
    for m in sorted(team.teammates, key=lambda m: m.joined_at):
        last = max(m.joined_at, _last_timestamp(m.transcripts) or m.joined_at)
        if segments and parse_iso(m.joined_at) <= parse_iso(segments[-1].last_activity) + gap:
            segments[-1].members.append(m)
            segments[-1].last_activity = max(segments[-1].last_activity, last)
        else:
            run_id = team.name if not segments else f"{team.name}-{len(segments) + 1}"
            segments.append(Segment(run_id, [m], m.joined_at, last))
    return segments


def assign_windows(segments: list[Segment], lead_path: Path, settings: Settings) -> None:
    """Each run starts at the lead's last user prompt before its first teammate joined, and ends where the next starts."""
    prompts = _lead_prompt_times(lead_path)
    lookback = timedelta(seconds=settings.lead_lookback_seconds)
    for i, seg in enumerate(segments):
        floor = segments[i - 1].last_activity if i else ""
        earlier = [p for p in prompts if floor < p <= seg.first_join and parse_iso(p) >= parse_iso(seg.first_join) - lookback]
        seg.start = earlier[-1] if earlier else seg.first_join
    for seg, following in zip(segments, segments[1:]):
        seg.end = following.start
    return segments


def _lead_prompt_times(lead_path: Path) -> list[str]:
    times = []
    for rec in JsonlTail(lead_path).read_new():
        if rec.get("type") == "user":
            times += [item.ts for item in parse_record(rec) if item.kind == "prompt"]
    return sorted(times)


class RunHandle:
    def __init__(self, run_id: str, settings: Settings):
        self.id = run_id
        self.settings = settings
        self.dir = settings.runs_dir / run_id
        self.events: list[dict] = []
        self.snapshot = Snapshot()
        self.subscribers: set[asyncio.Queue] = set()
        self.team: Team | None = None
        self.members: list[Member] = []
        self.parser: RunParser | None = None
        self.tails: list[tuple[str, JsonlTail]] = []
        self.live = False
        self._unsaved: list[dict] = []
        self._rewrite = True
        self._layout_text: str | None = None
        self._layout_mtime: float | None = None

    # ----- building -------------------------------------------------------------------------

    @classmethod
    def from_archive(cls, run_id: str, settings: Settings) -> "RunHandle":
        handle = cls(run_id, settings)
        with open(handle.dir / "events.jsonl", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    event = json.loads(line)
                    handle.events.append(event)
                    handle.snapshot.apply(event)
        handle._rewrite = False
        return handle

    def build(self, team: Team, segment: Segment, lead_path: Path, live: bool) -> None:
        """Parses everything written so far. Live handles keep their file offsets for polling."""
        self.team, self.members, self.live = team, list(segment.members), live
        lead = next(m for m in team.members if m.is_lead)
        redactor = Redactor(project=team.project)
        self.parser = RunParser(
            self.id,
            team,
            [lead, *segment.members],
            segment.start,
            segment.end,
            redactor,
            self._emit,
            on_layout=self.team_layout_written,
            idle_end_ms=int(self.settings.idle_end_seconds * 1000),
        )
        self.parser.start()
        self.tails = [(team.lead, JsonlTail(lead_path))]
        for m in segment.members:
            self.tails += [(m.name, JsonlTail(p)) for p in m.transcripts]
        joins = [Item("join", segment.start, f"join:{team.lead}")]
        joins += [Item("join", m.joined_at, f"join:{m.name}") for m in segment.members]
        self._feed(joins, [team.lead] + [m.name for m in segment.members], first=True)
        self.parser.tick(now_iso())
        self.save()

    def add_member(self, member: Member) -> None:
        if any(m.name == member.name for m in self.members):
            known = {t.path for _, t in self.tails}
            self.tails += [(member.name, JsonlTail(p)) for p in member.transcripts if p not in known]
            return
        self.members.append(member)
        self.parser.members[member.name] = member
        self.tails += [(member.name, JsonlTail(p)) for p in member.transcripts]
        self.parser.feed(member.name, Item("join", member.joined_at, f"join:{member.name}"))
        self.reload_layout()

    def poll(self) -> None:
        if self.parser is None:
            return
        self._feed([], [], first=False)
        self.parser.tick(now_iso())
        self._check_layout_file()
        self.save()

    def close_window(self, end: str) -> None:
        """A newer run of the same team started; this one stops following the lead."""
        if self.parser:
            self.parser.window_end = end
            self.poll()
            if self.parser.run["status"] == "live":
                self.parser.end(self.parser.last_activity or end)
                self.save()
        self.live = False

    def _feed(self, extra: list[Item], extra_agents: list[str], first: bool) -> None:
        batch = [(item.ts, -1, i, agent, item) for i, (agent, item) in enumerate(zip(extra_agents, extra))]
        for index, (agent, tail) in enumerate(self.tails):
            for rec in tail.read_new():
                for item in parse_record(rec):
                    batch.append((item.ts, index, len(batch), agent, item))
        batch.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        for _, _, _, agent, item in batch:
            self.parser.feed(agent, item)
            if first and item.kind == "join" and agent == self.team.lead:
                self.reload_layout(at=self.parser.window_start)

    # ----- events -----------------------------------------------------------------------------

    def _emit(self, etype: str, ts: str, data: dict) -> None:
        event = {"seq": len(self.events) + 1, "type": etype, "ts": ts, "data": data}
        self.events.append(event)
        self.snapshot.apply(event)
        self._unsaved.append(event)
        for queue in list(self.subscribers):
            queue.put_nowait(event)

    def save(self) -> None:
        if not self._unsaved and not self._rewrite:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        events = self.events if self._rewrite else self._unsaved
        with open(self.dir / "events.jsonl", "w" if self._rewrite else "a", encoding="utf-8") as fh:
            for event in events:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._rewrite = False
        self._unsaved = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.subscribers.discard(queue)

    def events_since(self, seq: int) -> list[dict]:
        return self.events[max(seq, 1) - 1 :]

    # ----- layout -----------------------------------------------------------------------------

    @property
    def team_layout_path(self) -> Path | None:
        """The layout file the lead writes: this run's folder first (.agent-monitor/<run id>/), then the
        project-wide one. Several runs can share a team name, so a team-named file would leak across runs."""
        if not self.team or not self.team.project:
            return None
        folder = Path(self.team.project) / ".agent-monitor"
        named = folder / self.id / "layout.json"
        return named if named.exists() else folder / "layout.json"

    @property
    def user_layout_path(self) -> Path:
        return self.dir / "layout.json"

    def team_layout_written(self, text: str | None) -> None:
        """The lead wrote (text) or edited (None: read the file) its layout during this run."""
        self._layout_text = text if text is not None else _read_text(self.team_layout_path)
        self.reload_layout()

    def reload_layout(self, at: str | None = None) -> None:
        # User override, then what the lead wrote during this run, then the file on disk.
        raw, source = _load_json(self.user_layout_path), "user"
        if raw is None and self._layout_text:
            raw, source = _parse_json(self._layout_text), "team"
        if raw is None:
            raw, source = _load_json(self.team_layout_path), "team"
        if self.parser:
            people = [{"name": n, **self._agent_labels(n)} for n in self.parser.members]
            lead = self.parser.lead
        else:
            people = list(self.snapshot.agents.values())
            lead = (self.snapshot.run or {}).get("lead", "")
        layout = build_layout(raw, people, lead, source)
        if layout != self.snapshot.layout:
            self._emit("layout.updated", at or now_iso(), {"layout": layout})

    def _agent_labels(self, name: str) -> dict:
        member = self.parser.members[name]
        assignment = member.description or ("Coordinates the team" if member.is_lead else None)
        return {"title": display_title(member), "assignment": assignment}

    def set_user_layout(self, raw: dict | None) -> None:
        if raw is None:
            self.user_layout_path.unlink(missing_ok=True)
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.user_layout_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        self.reload_layout()
        self.save()

    def _check_layout_file(self) -> None:
        path = self.team_layout_path
        try:
            mtime = path.stat().st_mtime if path else None
        except OSError:
            mtime = None
        if mtime != self._layout_mtime:
            first = self._layout_mtime is None and mtime is not None and self._layout_text is None
            self._layout_mtime = mtime
            if mtime is not None and not first:
                self._layout_text = _read_text(path)
            self.reload_layout()


def _read_text(path: Path | None) -> str | None:
    try:
        return path.read_text(encoding="utf-8") if path else None
    except OSError:
        return None


def _load_json(path: Path | None) -> dict | None:
    text = _read_text(path)
    return _parse_json(text) if text else None


def _parse_json(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


class Monitor:
    """Owns every run: builds them from ~/.claude/teams, polls the live ones, loads archived ones."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.runs: dict[str, RunHandle] = {}
        self._teams: dict[str, dict] = {}
        self._subagents = SubagentDiscovery()

    def scan(self) -> list[tuple[list[Segment], dict[str, RunHandle]]]:
        """Reads team configs and builds handles for runs not seen before. Safe off the event loop:
        it never touches registered handles."""
        results = []
        teams = []
        registered_sessions = set()
        for config_path in list_team_configs(self.settings.claude_dir):
            team = load_team(config_path)
            if team is not None:
                registered_sessions.add(team.lead_session_id)
            if team is None or not team.teammates:
                continue
            lead_path = attach_transcripts(self.settings.claude_dir, team)
            if lead_path is None:
                continue
            teams.append((team, lead_path))
        teams.extend(self._subagents.discover(self.settings.claude_dir, registered_sessions))
        for team, lead_path in teams:
            segments = plan_segments(team, self.settings)
            known = self._teams.get(team.name, [])
            built = {}
            if any(seg.run_id not in known for seg in segments):
                assign_windows(segments, lead_path, self.settings)
                for seg in segments:
                    if seg.run_id not in known:
                        handle = RunHandle(seg.run_id, self.settings)
                        handle.build(team, seg, lead_path, live=seg is segments[-1])
                        built[seg.run_id] = handle
            results.append((team.name, segments, built))
        return results

    def apply(self, results) -> list[RunHandle]:
        """Registers newly built runs and adds new teammates to live ones. Runs on the event loop."""
        added = []
        for team_name, segments, built in results:
            known = self._teams.setdefault(team_name, [])
            for seg in segments:
                if seg.run_id in built:
                    previous = self.runs.get(known[-1]) if known else None
                    if previous and previous.live:
                        previous.close_window(seg.start)
                    self.runs[seg.run_id] = built[seg.run_id]
                    known.append(seg.run_id)
                    added.append(built[seg.run_id])
                elif seg is segments[-1]:
                    handle = self.runs.get(seg.run_id)
                    if handle and handle.live:
                        for member in seg.members:
                            handle.add_member(member)
        self._load_archives()
        return added

    def discover(self) -> list[RunHandle]:
        """Blocking scan + apply, for the importer and tests."""
        return self.apply(self.scan())

    def _load_archives(self) -> None:
        if not self.settings.runs_dir.exists():
            return
        for run_dir in self.settings.runs_dir.iterdir():
            if run_dir.name not in self.runs and (run_dir / "events.jsonl").exists():
                try:
                    self.runs[run_dir.name] = RunHandle.from_archive(run_dir.name, self.settings)
                except (OSError, ValueError) as exc:
                    log.warning("Skipping archived run %s: %s", run_dir.name, exc)

    def poll(self) -> None:
        for handle in list(self.runs.values()):
            if handle.live:
                handle.poll()

    async def run_forever(self) -> None:
        # Building a team's history reads large files, so scanning runs off the event loop.
        self.apply(await asyncio.to_thread(self.scan))
        loop = asyncio.get_running_loop()
        next_discovery = loop.time() + self.settings.discover_seconds
        while True:
            try:
                self.poll()
                if loop.time() >= next_discovery:
                    self.apply(await asyncio.to_thread(self.scan))
                    next_discovery = loop.time() + self.settings.discover_seconds
            except Exception:  # keep watching even if one poll fails
                log.exception("Monitor poll failed")
            await asyncio.sleep(self.settings.poll_seconds)

    def summaries(self) -> list[dict]:
        runs = [h.snapshot.summary() for h in self.runs.values() if h.snapshot.run]
        return sorted(runs, key=lambda r: r.get("started_at") or "", reverse=True)
