"""Discover named background agents without a Claude team config."""
import json
from pathlib import Path

from .sources import JsonlTail, Member, Team


class SubagentDiscovery:
    def __init__(self):
        self.parents = {}

    def discover(self, claude_dir: Path, registered_sessions: set[str]):
        found = []
        for folder in sorted((claude_dir / "projects").glob("*/*/subagents")):
            session = folder.parent.name
            if session in registered_sessions:
                continue
            lead_path = folder.parent.with_suffix(".jsonl")
            if not lead_path.exists():
                continue
            # Read only appended parent records; transcripts can be many megabytes.
            parent = self.parents.setdefault(lead_path, {
                "tail": JsonlTail(lead_path), "calls": {}, "project": "",
            })
            if lead_path.stat().st_size < parent["tail"].offset:
                parent.update(tail=JsonlTail(lead_path), calls={}, project="")
            for rec in parent["tail"].read_new():
                parent["project"] = rec.get("cwd") or parent["project"]
                ts = rec.get("timestamp")
                content = (rec.get("message") or {}).get("content")
                if not ts or not isinstance(content, list):
                    continue
                for block in content:
                    if (isinstance(block, dict) and block.get("type") == "tool_use"
                            and block.get("name") in ("Agent", "Task")):
                        parent["calls"].setdefault(block.get("id"), (ts, block.get("input") or {}))
            members = {}
            for meta_path in sorted(folder.glob("*.meta.json")):
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(meta, dict) or meta.get("teamName"):
                    continue
                name = meta.get("name")
                spawn = parent["calls"].get(meta.get("toolUseId"))
                transcript = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
                if not isinstance(name, str) or not name or name == "team-lead" or not spawn or not transcript.exists():
                    continue
                ts, inp = spawn
                if inp.get("name") != name:
                    continue
                member = members.get(name)
                if member is None:
                    member = members[name] = Member(
                        name=name, agent_type=meta.get("agentType", "general-purpose"),
                        is_lead=False, joined_at=ts, cwd=parent["project"],
                        description=meta.get("description") or inp.get("description"),
                        prompt=inp.get("prompt"),
                    )
                member.joined_at = min(member.joined_at, ts)
                member.transcripts.append(transcript)
            if not members:
                continue
            started = min(m.joined_at for m in members.values())
            lead = Member("team-lead", "team-lead", True, started, cwd=parent["project"])
            team = Team(
                name=f"subagents-{session}", created_at=started,
                lead_session_id=session, lead=lead.name, project=parent["project"],
                members=[lead, *members.values()], config_path=lead_path,
            )
            found.append((team, lead_path))
        return found
