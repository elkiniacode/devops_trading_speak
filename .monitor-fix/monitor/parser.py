"""Turn one run's merged transcript items into contract events (see CONTRACT.md)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .plans import LAYOUT_PATH, PLAN_PATH, parse_plan
from .records import Item
from .redact import Redactor
from .sources import Member, Team, parse_iso
from .steps import MERGEABLE, SEARCH_TOOLS, classify, command_label, headline, lookup_label, parse_test_counts, step_title

Emit = Callable[[str, str, dict], None]
OUTPUT_LIMIT = 4000
INPUT_LIMIT = 2000
DIFF_LINE_LIMIT = 400
# The lead's own work counts as part of the run while a teammate works, and this long after.
LEAD_GRACE_MS = 10 * 60 * 1000
DONE_STATES = ("completed", "failed", "cancelled")
# Steps that count as real work (a wake-up with only messages and notes is not a new task).
WORK_KINDS = {"read", "edit", "command", "test", "research", "browser", "tool", "spawn", "plan"}


def ms_between(start: str, end: str) -> int:
    return max(0, int((parse_iso(end) - parse_iso(start)).total_seconds() * 1000))


def clip(text: str | None, limit: int = OUTPUT_LIMIT) -> tuple[str, bool]:
    text = text or ""
    if len(text) <= limit:
        return text, False
    head, tail = int(limit * 0.75), int(limit * 0.25)
    return f"{text[:head]}\n… [{len(text) - head - tail} characters omitted] …\n{text[-tail:]}", True


def thread_id(a: str, b: str) -> str:
    return "~".join(sorted([a, b]))


def _norm(text: str | None) -> str:
    return " ".join((text or "").split()).lower()


def _body_key(sender: str, body: str | None) -> str:
    """Bodies compared for matching sends to deliveries; agents sometimes prefix their own name."""
    key = _norm(body)
    prefix = f"{sender.lower()}:"
    return (key[len(prefix):].strip() if key.startswith(prefix) else key)[:120]


def display_title(member: Member) -> str:
    if member.is_lead:
        return "Lead"
    name = member.name.replace("-", " ").replace("_", " ")
    return name.upper() if len(name) <= 3 else name[:1].upper() + name[1:]


@dataclass
class AgentState:
    name: str
    is_lead: bool
    cwd: str | None
    status: str = "idle"
    working_since: str | None = None
    active_ms: int = 0
    step_count: int = 0
    session_count: int = 0
    open_step: str | None = None
    pending_text: list = field(default_factory=list)
    trigger: dict | None = None
    session_task: str | None = None
    # Steps of the current wake-up placed on the previous task until real work starts a new one.
    session_steps: list = field(default_factory=list)
    last_task: str | None = None
    plan_keys: list = field(default_factory=list)
    plan_text: str | None = None
    last_task_end: str | None = None
    current_plan_task: str | None = None
    last_plan_change: str | None = None


class RunParser:
    """Feeds on transcript items in time order and emits events through `emit(type, ts, data)`."""

    def __init__(
        self,
        run_id: str,
        team: Team,
        members: list[Member],
        window_start: str,
        window_end: str | None,
        redactor: Redactor,
        emit: Emit,
        on_layout: Callable[[str | None], None] | None = None,
        idle_end_ms: int = 30 * 60 * 1000,
    ):
        self.team = team
        self.members = {m.name: m for m in members}
        self.lead = team.lead
        self.window_start = window_start
        self.window_end = window_end
        self.r = redactor
        self.emit = emit
        self.on_layout = on_layout or (lambda text: None)
        self.idle_end_ms = idle_end_ms
        self.agents: dict[str, AgentState] = {}
        self.steps: dict[str, dict] = {}
        self.meta: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.messages: dict[str, dict] = {}
        self.match_keys: dict[str, tuple] = {}
        self.calls: dict[str, dict] = {}
        self.pending_sends: dict[tuple, list] = {}
        self.inbox_only: dict[tuple, list] = {}
        self.seen: set[str] = set()
        self.auto_titled: set[str] = set()
        teammates = [m.joined_at for m in members if not m.is_lead]
        self.first_join = min(teammates) if teammates else window_start
        self.last_teammate_ts: str | None = None
        self.last_activity: str | None = None
        self.run = {
            "id": run_id,
            "team": team.name,
            "project": Path(team.project.replace("\\", "/")).name if team.project else None,
            "project_path": redactor.text(team.project.replace("\\", "/")) if team.project else None,
            "lead": team.lead,
            "status": "live",
            "started_at": window_start,
            "team_started_at": self.first_join,
            "ended_at": None,
        }

    # ----- entry points -------------------------------------------------------------------

    def start(self) -> None:
        self.emit("run.started", self.window_start, {"run": dict(self.run)})

    def feed(self, agent: str, item: Item) -> None:
        if item.uid in self.seen:
            return
        self.seen.add(item.uid)
        if item.kind == "join":
            self._join(agent, item.ts)
            return
        a = self.agents.get(agent)
        if a is None or (a.is_lead and not self._lead_allows(item)):
            return
        if not a.is_lead:
            self.last_teammate_ts = max(self.last_teammate_ts or item.ts, item.ts)
            if self.run["status"] == "ended" and item.kind not in ("idle", "turn_end"):
                self.run.update(status="live", ended_at=None)
                self.emit("run.updated", item.ts, {"run": dict(self.run)})
        self.last_activity = max(self.last_activity or item.ts, item.ts)
        getattr(self, f"_on_{item.kind}")(a, item)

    def tick(self, now: str) -> None:
        """Ends the run once no one has worked for idle_end_ms."""
        if self.run["status"] == "live" and self.last_activity and ms_between(self.last_activity, now) > self.idle_end_ms:
            self.end(self.last_activity)

    def end(self, ts: str) -> None:
        for a in self.agents.values():
            self._sleep(a, ts)
            a.status = "done"
            self._emit_status(a, ts)
        self.run.update(status="ended", ended_at=ts)
        self.emit("run.updated", ts, {"run": dict(self.run)})

    # ----- item handlers ------------------------------------------------------------------

    def _join(self, name: str, ts: str) -> None:
        member = self.members.get(name)
        if member is None or name in self.agents:
            return
        self.agents[name] = AgentState(name=name, is_lead=member.is_lead, cwd=member.cwd)
        joined = self.window_start if member.is_lead else ts
        self.emit(
            "agent.joined",
            joined,
            {
                "agent": {
                    "name": name,
                    "title": display_title(member),
                    "assignment": member.description or ("Coordinates the team" if member.is_lead else None),
                    "role": member.agent_type,
                    "color": member.color,
                    "model": member.model,
                    "is_lead": member.is_lead,
                    "joined_at": joined,
                    "cwd": self.r.path(member.cwd) if member.cwd else None,
                    "spec": self.r.text(member.prompt),
                }
            },
        )

    def _on_text(self, a: AgentState, item: Item) -> None:
        text, _ = clip(self.r.text(item.data["text"]))
        a.pending_text.append({"type": "text", "ts": item.ts, "text": text})
        self._wake(a, item.ts)

    def _on_turn_end(self, a: AgentState, item: Item) -> None:
        self._sleep(a, item.ts)

    def _on_notice(self, a: AgentState, item: Item) -> None:
        self._wake(a, item.ts)

    def _on_idle(self, a: AgentState, item: Item) -> None:
        other = self.agents.get(self._name(item.data.get("from")))
        if other and not other.is_lead:
            self._sleep(other, item.ts)
            if a.status != "working":
                a.trigger = {"title": f"Follow up on {other.name}", "message_id": None, "ts": item.ts}

    def _on_prompt(self, a: AgentState, item: Item) -> None:
        text = item.data["text"]
        self._receive(a, item.ts, "user", None, text, matched=None, kind="prompt")

    def _on_inbox(self, a: AgentState, item: Item) -> None:
        sender = self._name(item.data.get("from"))
        summary, body = item.data.get("summary"), item.data.get("body")
        matched = self._take_match(self.pending_sends, (sender, a.name), summary, body)
        kind = "assignment" if sender == self.lead and a.step_count == 0 and not a.is_lead else "message"
        self._receive(a, item.ts, sender, summary, body, matched=matched, kind=kind)

    def _on_tool_use(self, a: AgentState, item: Item) -> None:
        name, inp, ts = item.data["name"], item.data["input"], item.ts
        kind = classify(name, inp)
        if kind == "hidden":
            return
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        plan_kind = None
        if kind == "edit" and path:
            for pattern, label in ((PLAN_PATH, "plan"), (LAYOUT_PATH, "layout")):
                match = pattern.search(path)
                if match and (match["team"] is None or match["team"].lower() in (self.team.name.lower(), self.run["id"].lower())):
                    kind, plan_kind = "plan", label
        self._wake(a, ts)
        sid, new = self._step_for(a, kind, ts)
        meta = self.meta[sid]
        meta["open"] += 1
        self.steps[sid]["calls"] += 1
        display = self.r.path(path, a.cwd) if path else None
        self.calls[item.data["id"]] = {"step": sid, "name": name, "kind": kind, "input": inp, "agent": a.name, "path": path, "plan": plan_kind, "display": display}
        items = self._take_text(a) + [self._call_item(a, name, inp, ts)]
        if kind == "read":
            if name in SEARCH_TOOLS:
                meta["searches"] += 1
            else:
                meta["reads"].append(display or "?")
        elif kind == "edit":
            info = meta["files"].setdefault(display or "?", {"changes": 0, "created": False})
            info["changes"] += 1
        elif kind == "command":
            meta["commands"].append(command_label(inp))
        elif kind == "test":
            meta.update(label=inp.get("description") or "Ran tests", running=True)
        elif kind == "research":
            meta["lookups"].append(lookup_label(name, inp))
        elif kind == "browser":
            meta["actions"] += 1
        elif kind == "plan":
            first = plan_kind == "plan" and self.agents.get(self._plan_owner(path, a.name), a).plan_text is None
            meta["label"] = "Published the team layout" if plan_kind == "layout" else ("Wrote my plan" if first else "Updated my plan")
        elif kind == "tool":
            meta["tool"] = name
        outgoing = self._send(a, sid, name, inp, ts) if kind in ("message_out", "spawn") else []
        self._publish_step(sid, ts)
        for etype, msg in outgoing:
            self.emit(etype, ts, {"message": dict(msg)})
            items.append(self._message_item(msg, "out", ts))
        self._emit_items(sid, a.name, ts, items)

    def _on_tool_result(self, a: AgentState, item: Item) -> None:
        call = self.calls.pop(item.data.get("tool_use_id"), None)
        if call is None:
            return
        sid, name, ts = call["step"], call["name"], item.ts
        step, meta = self.steps[sid], self.meta[sid]
        ok = not item.data["is_error"]
        output, truncated = clip(self.r.text(item.data["text"]))
        items = [{"type": "tool_result", "ts": ts, "tool": name, "ok": ok, "output": output, "truncated": truncated}]
        extra = item.data.get("extra") or {}
        if name in ("Write", "Edit", "MultiEdit"):
            if call["kind"] == "edit" and extra.get("type") == "create":
                meta["files"].get(call["display"] or "?", {})["created"] = True
            hunks = self._hunks(extra.get("structuredPatch"))
            if hunks:
                items.append({"type": "diff", "ts": ts, "file": call["display"], "hunks": hunks})
        if call["kind"] == "test":
            counts = parse_test_counts(item.data["text"])
            meta.update(tests=counts, running=False)
            step["tests"] = counts
            if counts and counts["failed"]:
                ok = False
        if call["kind"] == "plan" and ok:
            self._apply_plan_call(call, item)
        if call["kind"] in ("message_out", "spawn") and not ok:
            self._fail_messages(step, ts)
        meta["open"] = max(0, meta["open"] - 1)
        meta["error"] = meta["error"] or not ok
        meta["failed"] = meta.get("failed", 0) + (0 if ok else 1)
        self._publish_step(sid, ts)
        self._emit_items(sid, call["agent"], ts, items)

    # ----- agents, sessions and tasks -----------------------------------------------------

    def _wake(self, a: AgentState, ts: str) -> None:
        if a.status != "working":
            a.status, a.working_since = "working", ts
            self._emit_status(a, ts)

    def _sleep(self, a: AgentState, ts: str) -> None:
        self._flush_note(a)
        a.open_step = None
        if a.status == "working":
            a.active_ms += ms_between(a.working_since or ts, ts)
            a.status, a.working_since = "idle", None
            self._emit_status(a, ts)
        if a.session_task:
            task = self.tasks[a.session_task]
            self._set_task_status(a, task, "completed", ts)
            self.emit("task.updated", ts, {"task": dict(task)})
            a.session_task = None
        a.trigger, a.session_steps = None, []

    def _emit_status(self, a: AgentState, ts: str) -> None:
        self.emit(
            "agent.status",
            ts,
            {"agent": a.name, "status": a.status, "active_ms": a.active_ms, "working_since": a.working_since},
        )

    def _task_for(self, a: AgentState, ts: str, kind: str) -> tuple[str, bool]:
        """The task a new step belongs to, and whether that home is provisional.

        With a plan: the plan task in progress (else the last one touched). Without one, each
        wake-up that does real work becomes a reconstructed task; wake-ups that only exchange
        messages stay on the agent's previous task."""
        if a.plan_keys:
            running = [
                self.tasks[f"{a.name}:{k}"] for k in a.plan_keys if self.tasks[f"{a.name}:{k}"]["status"] == "in_progress"
            ]
            if running:
                return max(running, key=lambda t: t["started_at"] or "")["id"], False
            # Between tasks, work belongs to the task started last (else the last one ticked off).
            if a.current_plan_task or a.last_plan_change:
                return a.current_plan_task or a.last_plan_change, False
        if a.session_task:
            return a.session_task, False
        if kind not in WORK_KINDS and a.last_task:
            return a.last_task, True
        a.session_count += 1
        trigger = a.trigger or {}
        title = trigger.get("title") or ("Coordinate the team" if a.is_lead else "Follow-up work")
        start = trigger.get("ts") or ts
        task = self._new_task(a, f"S{a.session_count}", title, "reconstructed", start)
        task["trigger_message_id"] = trigger.get("message_id")
        if not trigger.get("title"):
            # No message started this work: the agent's latest note (its closing summary) names it.
            self.auto_titled.add(task["id"])
        self._set_task_status(a, task, "in_progress", start)
        self.emit("task.created", start, {"task": dict(task)})
        a.session_task = a.last_task = task["id"]
        for sid in a.session_steps:
            self.steps[sid]["task_id"] = task["id"]
            self.emit("step.updated", ts, {"step": dict(self.steps[sid])})
        a.session_steps = []
        return task["id"], False

    def _new_task(self, a: AgentState, key: str, title: str, source: str, ts: str) -> dict:
        task = {
            "id": f"{a.name}:{key}",
            "agent": a.name,
            "key": key,
            "title": self.r.text(title),
            "status": "pending",
            "note": None,
            "order": len([t for t in self.tasks.values() if t["agent"] == a.name]),
            "source": source,
            "created_at": ts,
            "started_at": None,
            "ended_at": None,
            "duration_ms": None,
            "trigger_message_id": None,
            "removed": False,
            "history": [],
        }
        self.tasks[task["id"]] = task
        return task

    def _set_task_status(self, a: AgentState, task: dict, status: str, ts: str) -> None:
        previous = task["status"]
        task["status"] = status
        if status == "in_progress" and not task["started_at"]:
            task["started_at"] = ts
        if status in DONE_STATES and previous not in DONE_STATES:
            if not task["started_at"]:
                task["started_at"] = max(task["created_at"], a.last_task_end or task["created_at"])
            task["ended_at"] = ts
            task["duration_ms"] = ms_between(task["started_at"], ts)
            if task["source"] == "plan":
                a.last_task_end = ts
        if status not in DONE_STATES and previous in DONE_STATES:
            task["ended_at"] = task["duration_ms"] = None
        if task["source"] == "plan" and status == "in_progress":
            a.current_plan_task = task["id"]
        elif task["source"] == "plan" and status != "pending":
            a.last_plan_change = task["id"]
        task["history"].append({"ts": ts, "status": status, "title": task["title"]})

    def _plan_owner(self, path: str, writer: str) -> str:
        match = PLAN_PATH.search(path)
        return match["agent"] if match and match["agent"] in self.agents else writer

    def _apply_plan_call(self, call: dict, item: Item) -> None:
        inp, extra, path = call["input"], item.data.get("extra") or {}, call["path"]
        if call["plan"] == "layout":
            self.on_layout(inp.get("content") if call["name"] == "Write" else None)
            return
        owner = self.agents[self._plan_owner(path, call["agent"])]
        if call["name"] == "Write":
            text = inp.get("content", "")
        else:
            text = extra.get("originalFile") or owner.plan_text or _read(path) or ""
            edits = inp.get("edits") or [inp]
            for edit in edits:
                old, new = edit.get("old_string", ""), edit.get("new_string", "")
                if old and old in text:
                    text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
                else:
                    text = _read(path) or text
                    break
        self._update_plan(owner, text, item.ts)

    def _update_plan(self, a: AgentState, text: str, ts: str) -> None:
        items = parse_plan(text)
        keys = [it.key for it in items]
        for it in items:
            task = self.tasks.get(f"{a.name}:{it.key}")
            if task is None:
                task = self._new_task(a, it.key, it.title, "plan", ts)
                task.update(note=self.r.text(it.note), order=it.order)
                self._set_task_status(a, task, it.status, ts)
                self.emit("task.created", ts, {"task": dict(task)})
                continue
            changed = task["removed"]
            task["removed"] = False
            for name, value in (("title", self.r.text(it.title)), ("note", self.r.text(it.note)), ("order", it.order)):
                if task[name] != value:
                    task[name], changed = value, True
            if task["status"] != it.status:
                self._set_task_status(a, task, it.status, ts)
                changed = True
            if changed:
                self.emit("task.updated", ts, {"task": dict(task)})
        for key in a.plan_keys:
            task = self.tasks[f"{a.name}:{key}"]
            if key not in keys and not task["removed"]:
                task["removed"] = True
                if task["status"] not in DONE_STATES:
                    self._set_task_status(a, task, "cancelled", ts)
                self.emit("task.updated", ts, {"task": dict(task)})
        a.plan_keys, a.plan_text = keys, text

    # ----- steps ----------------------------------------------------------------------------

    def _step_for(self, a: AgentState, kind: str, ts: str) -> tuple[str, bool]:
        task_id, provisional = self._task_for(a, ts, kind)
        if kind in MERGEABLE and a.open_step:
            open_step = self.steps[a.open_step]
            if open_step["kind"] == kind and open_step["task_id"] == task_id:
                return open_step["id"], False
        return self._new_step(a, kind, ts, (task_id, provisional)), True

    def _new_step(self, a: AgentState, kind: str, ts: str, home: tuple[str, bool] | None = None, **meta) -> str:
        task_id, provisional = home or self._task_for(a, ts, kind)
        a.step_count += 1
        sid = f"{a.name}-{a.step_count}"
        if provisional:
            a.session_steps.append(sid)
        self.steps[sid] = {
            "id": sid,
            "agent": a.name,
            "task_id": task_id,
            "kind": kind,
            "title": "",
            "status": "running",
            "started_at": ts,
            "ended_at": None,
            "calls": 0,
            "files": [],
            "message_ids": [],
            "tests": None,
        }
        self.meta[sid] = {"open": 0, "error": False, "reads": [], "searches": 0, "files": {}, "commands": [], "lookups": [], "actions": 0, **meta}
        a.open_step = sid if kind in MERGEABLE else None
        return sid

    def _publish_step(self, sid: str, ts: str) -> None:
        step, meta = self.steps[sid], self.meta[sid]
        step["title"] = self.r.text(step_title(step["kind"], meta))
        step["files"] = list(meta["files"]) or ([meta["path"]] if meta.get("path") else [])
        step["status"] = "error" if meta["error"] else ("running" if meta["open"] else "ok")
        if not meta["open"]:
            step["ended_at"] = ts
        self.emit("step.updated" if meta.get("announced") else "step.added", ts, {"step": dict(step)})
        meta["announced"] = True

    def _emit_items(self, sid: str, agent: str, ts: str, items: list[dict]) -> None:
        if items:
            self.emit("step.interaction", ts, {"step_id": sid, "agent": agent, "items": items})

    def _take_text(self, a: AgentState) -> list[dict]:
        items, a.pending_text = a.pending_text, []
        return items

    def _flush_note(self, a: AgentState) -> None:
        if not a.pending_text:
            return
        items = self._take_text(a)
        text, ts = "\n".join(i["text"] for i in items), items[-1]["ts"]
        sid = self._new_step(a, "note", items[0]["ts"], text=text)
        self._publish_step(sid, ts)
        self._emit_items(sid, a.name, ts, items)
        task = self.tasks[self.steps[sid]["task_id"]]
        if task["id"] in self.auto_titled and headline(text, 80):
            task["title"] = headline(text, 80)
            self.emit("task.updated", ts, {"task": dict(task)})

    def _hunks(self, patch) -> list[dict]:
        if not isinstance(patch, list):
            return []
        hunks, budget = [], DIFF_LINE_LIMIT
        for hunk in patch:
            lines = [self.r.text(line[:300]) for line in hunk.get("lines", [])[:budget]]
            budget -= len(lines)
            hunks.append({k: hunk.get(k) for k in ("oldStart", "oldLines", "newStart", "newLines")} | {"lines": lines})
            if budget <= 0:
                break
        return hunks

    def _call_item(self, a: AgentState, name: str, inp: dict, ts: str) -> dict:
        r = self.r

        def path(key: str) -> str | None:
            return r.path(str(inp[key]), a.cwd) if inp.get(key) else None

        if name in ("Bash", "PowerShell"):
            shown = {"command": clip(r.text(str(inp.get("command", ""))), INPUT_LIMIT)[0], "background": bool(inp.get("run_in_background"))}
        elif name == "Read":
            shown = {"file": path("file_path"), "offset": inp.get("offset"), "limit": inp.get("limit")}
        elif name in ("Glob", "Grep"):
            shown = {"pattern": r.text(inp.get("pattern")), "path": path("path"), "glob": inp.get("glob")}
        elif name == "Write":
            shown = {"file": path("file_path"), "content": clip(r.text(inp.get("content", "")))[0]}
        elif name == "Edit":
            shown = {
                "file": path("file_path"),
                "replace_all": bool(inp.get("replace_all")),
                "old": clip(r.text(inp.get("old_string", "")), INPUT_LIMIT)[0],
                "new": clip(r.text(inp.get("new_string", "")), INPUT_LIMIT)[0],
            }
        elif name == "SendMessage":
            shown = {"to": inp.get("to"), "summary": r.text(inp.get("summary"))}
        elif name in ("Agent", "Task"):
            shown = {"name": inp.get("name"), "description": r.text(inp.get("description")), "type": inp.get("subagent_type")}
        elif name == "WebSearch":
            shown = {"query": inp.get("query")}
        elif name == "WebFetch":
            shown = {"url": inp.get("url")}
        else:
            shown = {k: clip(r.text(str(v)), 500)[0] for k, v in inp.items()}
        shown = {k: v for k, v in shown.items() if v not in (None, "")}
        return {"type": "tool_call", "ts": ts, "tool": name, "title": r.text(inp.get("description")), "input": shown}

    # ----- messages ---------------------------------------------------------------------------

    def _name(self, raw) -> str:
        name = str(raw or "").strip().lstrip("@").split("@")[0]
        name = re.sub(r"\s*\[[^\]]*\]$", "", name)
        return self.lead if name in ("main", self.lead) else name

    def _new_message(self, sender: str, to: str, summary, body, ts: str, kind: str) -> dict:
        msg = {
            "id": f"m{len(self.messages) + 1}",
            "from": sender,
            "to": to,
            "kind": kind,
            "summary": self.r.text(summary),
            "body": self.r.text(body),
            "status": "sent",
            "sent_at": ts,
            "delivered_at": None,
            "thread_id": thread_id(sender, to),
            "step_id": None,
            "delivered_step_id": None,
        }
        self.messages[msg["id"]] = msg
        self.match_keys[msg["id"]] = (_norm(summary), _body_key(sender, body))
        return msg

    def _take_match(self, pool: dict, key: tuple, summary, body) -> dict | None:
        candidates = pool.get(key) or []
        want_summary, want_body = _norm(summary), _body_key(key[0], body)
        for i, msg in enumerate(candidates):
            have_summary, have_body = self.match_keys[msg["id"]]
            same = have_summary == want_summary if have_summary and want_summary else have_body == want_body
            if same:
                return candidates.pop(i)
        return None

    def _send(self, a: AgentState, sid: str, name: str, inp: dict, ts: str) -> list[tuple[str, dict]]:
        """Creates (or matches) the outgoing messages; returns the events to emit once the step exists."""
        if name == "SendMessage":
            raw_to = str(inp.get("to", ""))
            targets = [n for n in self.agents if n != a.name] if raw_to.strip() == "*" else [self._name(raw_to)]
            summary, body, kind = inp.get("summary"), inp.get("message"), "message"
            if not isinstance(body, str):
                body = str(body)
        else:
            targets, summary, body, kind = [str(inp.get("name"))], inp.get("description"), inp.get("prompt"), "assignment"
            self.meta[sid]["name"] = targets[0]
        meta = self.meta[sid]
        meta.update(to=", ".join(targets) if len(targets) < 4 else "everyone", summary=summary, body=body)
        outgoing = []
        for target in targets:
            msg = self._take_match(self.inbox_only, (a.name, target), summary, body)
            if msg:
                outgoing.append(("message.updated", msg))
            else:
                msg = self._new_message(a.name, target, summary, body, ts, kind)
                self.pending_sends.setdefault((a.name, target), []).append(msg)
                outgoing.append(("message.sent", msg))
            msg["step_id"] = sid
            self.steps[sid]["message_ids"].append(msg["id"])
        return outgoing

    def _fail_messages(self, step: dict, ts: str) -> None:
        """The send tool failed (e.g. a spawn error), so its messages never arrive."""
        for mid in step["message_ids"]:
            msg = self.messages[mid]
            if msg["status"] == "sent":
                msg["status"] = "failed"
                pending = self.pending_sends.get((msg["from"], msg["to"]), [])
                if msg in pending:
                    pending.remove(msg)
                self.emit("message.updated", ts, {"message": dict(msg)})

    def _receive(self, a: AgentState, ts: str, sender: str, summary, body, matched: dict | None, kind: str) -> None:
        self._flush_note(a)
        msg = matched or self._new_message(sender, a.name, summary, body, ts, kind)
        if a.status != "working":
            title = headline(msg["summary"], 80) or headline(msg["body"], 80)
            a.trigger = {"title": title, "message_id": msg["id"], "ts": ts}
        self._wake(a, ts)
        sid = self._new_step(
            a, "message_in", ts, **{"from": sender, "summary": msg["summary"], "body": msg["body"], "assignment": msg["kind"] == "assignment"}
        )
        msg["status"], msg["delivered_at"], msg["delivered_step_id"] = "delivered", ts, sid
        self.steps[sid]["message_ids"].append(msg["id"])
        self._publish_step(sid, ts)
        self._emit_items(sid, a.name, ts, [self._message_item(msg, "in", ts)])
        if matched:
            self.emit("message.updated", ts, {"message": dict(msg)})
        else:
            if sender in self.members and sender != "user":
                self.inbox_only.setdefault((sender, a.name), []).append(msg)
            self.emit("message.sent", ts, {"message": dict(msg)})

    def _message_item(self, msg: dict, direction: str, ts: str) -> dict:
        return {
            "type": "message",
            "ts": ts,
            "direction": direction,
            "message_id": msg["id"],
            "from": msg["from"],
            "to": msg["to"],
            "summary": msg["summary"],
            "body": msg["body"],
        }

    # ----- lead window ------------------------------------------------------------------------

    def _lead_allows(self, item: Item) -> bool:
        if item.ts < self.window_start or (self.window_end and item.ts >= self.window_end):
            return False
        if item.kind in ("inbox", "idle"):
            return True
        if item.kind == "turn_end":
            return self.agents[self.lead].status == "working"
        if item.kind == "tool_use" and classify(item.data["name"], item.data["input"]) in ("message_out", "spawn"):
            # Talking to this run's teammates always counts; spawning or messaging someone new only
            # while the team is active (otherwise it belongs to the lead's next run).
            inp = item.data["input"]
            target = self._name(inp.get("name") or inp.get("to"))
            return target in self.members or (self.run["status"] == "live" and self._team_active(item.ts))
        if item.kind == "tool_result":
            return item.data.get("tool_use_id") in self.calls
        return self._team_active(item.ts)

    def _team_active(self, ts: str) -> bool:
        if any(a.status == "working" for a in self.agents.values() if not a.is_lead):
            return True
        reference = self.last_teammate_ts or self.first_join
        return ts <= reference or ms_between(reference, ts) <= LEAD_GRACE_MS


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
