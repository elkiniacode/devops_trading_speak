"""Find agent teams and their transcripts in the Claude config folder, and tail JSONL files."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


def iso_from_ms(ms: int | float) -> str:
    return iso(datetime.fromtimestamp(ms / 1000, timezone.utc))


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def now_iso() -> str:
    return iso(datetime.now(timezone.utc))


@dataclass
class Member:
    name: str
    agent_type: str
    is_lead: bool
    joined_at: str
    color: str | None = None
    model: str | None = None
    prompt: str | None = None
    cwd: str | None = None
    description: str | None = None
    transcripts: list[Path] = field(default_factory=list)


@dataclass
class Team:
    name: str
    created_at: str
    lead_session_id: str
    lead: str
    project: str
    members: list[Member]
    config_path: Path

    @property
    def teammates(self) -> list[Member]:
        return [m for m in self.members if not m.is_lead]


def project_dir_name(cwd: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def load_team(config_path: Path) -> Team | None:
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lead_id = config.get("leadAgentId", "")
    members = []
    for raw in config.get("members", []):
        is_lead = raw.get("agentId") == lead_id or raw.get("agentType") == "team-lead"
        members.append(
            Member(
                name=raw["name"],
                agent_type=raw.get("agentType", ""),
                is_lead=is_lead,
                joined_at=iso_from_ms(raw.get("joinedAt") or config.get("createdAt") or 0),
                color=raw.get("color"),
                model=raw.get("model"),
                prompt=raw.get("prompt"),
                cwd=raw.get("cwd"),
            )
        )
    leads = [m for m in members if m.is_lead]
    if not leads:
        return None
    return Team(
        name=config.get("name") or config_path.parent.name,
        created_at=iso_from_ms(config.get("createdAt") or 0),
        lead_session_id=config.get("leadSessionId", ""),
        lead=leads[0].name,
        project=leads[0].cwd or "",
        members=members,
        config_path=config_path,
    )


def list_team_configs(claude_dir: Path) -> list[Path]:
    return sorted((claude_dir / "teams").glob("*/config.json"))


def attach_transcripts(claude_dir: Path, team: Team) -> Path | None:
    """Fill in each teammate's transcript files and return the lead's transcript."""
    projects = claude_dir / "projects"
    lead_path = projects / project_dir_name(team.project) / f"{team.lead_session_id}.jsonl"
    if not lead_path.exists():
        found = sorted(projects.glob(f"*/{team.lead_session_id}.jsonl"))
        lead_path = found[0] if found else None
    if lead_path is None:
        return None
    by_name = {m.name: m for m in team.teammates}
    for meta_path in sorted((lead_path.parent / team.lead_session_id / "subagents").glob("*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        member = by_name.get(meta.get("name"))
        transcript = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
        if member and meta.get("teamName") == team.name and transcript.exists():
            member.description = meta.get("description") or member.description
            if transcript not in member.transcripts:
                member.transcripts.append(transcript)
    return lead_path


class JsonlTail:
    """Reads only the complete lines appended to a JSONL file since the last call."""

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self._partial = b""

    def read_new(self) -> list[dict]:
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:
            self.offset, self._partial = 0, b""
        if size == self.offset:
            return []
        with open(self.path, "rb") as fh:
            fh.seek(self.offset)
            data = fh.read()
        self.offset += len(data)
        lines = (self._partial + data).split(b"\n")
        self._partial = lines.pop()
        records = []
        for line in lines:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
        return records
