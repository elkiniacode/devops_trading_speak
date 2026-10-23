"""A fake Claude config folder with one team, written the way Claude Code writes transcripts."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from monitor.config import Settings
from monitor.sources import project_dir_name

LEAD_SESSION = "11111111-2222-3333-4444-555555555555"
BASE = datetime(2026, 10, 19, 20, 0, 0, tzinfo=timezone.utc)


def T(seconds: float) -> str:
    return (BASE + timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def ms(seconds: float) -> int:
    return int((BASE + timedelta(seconds=seconds)).timestamp() * 1000)


class Transcript:
    def __init__(self, path: Path):
        self.path = path
        self.n = 0
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def write(self, rec: dict) -> None:
        self.n += 1
        rec.setdefault("uuid", f"{self.path.stem}-{self.n}")
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")

    def user(self, ts: str, content, **extra) -> None:
        self.write({"type": "user", "timestamp": ts, "message": {"role": "user", "content": content}, **extra})

    def assistant(self, ts: str, blocks: list, stop: str | None = None) -> None:
        self.write({"type": "assistant", "timestamp": ts, "message": {"role": "assistant", "content": blocks, "stop_reason": stop}})

    def text(self, ts: str, text: str, end: bool = False) -> None:
        self.assistant(ts, [{"type": "text", "text": text}], "end_turn" if end else None)

    def tool(self, ts: str, tid: str, name: str, inp: dict) -> None:
        self.assistant(ts, [{"type": "tool_use", "id": tid, "name": name, "input": inp}], "tool_use")

    def result(self, ts: str, tid: str, text: str, error: bool = False, extra: dict | None = None) -> None:
        block = {"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}
        self.user(ts, [block], toolUseResult=extra or {})

    def inbox(self, ts: str, sender: str, summary: str, body: str) -> None:
        self.user(ts, f'<teammate-message teammate_id="{sender}" summary="{summary}">\n{body}\n</teammate-message>')

    def idle(self, ts: str, sender: str) -> None:
        body = json.dumps({"type": "idle_notification", "from": sender})
        self.user(ts, f'<teammate-message teammate_id="{sender}">\n{body}\n</teammate-message>')


class FakeClaude:
    def __init__(self, root: Path):
        self.dir = root / "claude"
        self.project = root / "project"
        self.project.mkdir(parents=True, exist_ok=True)
        self.team = "demo-team"
        self.members: list[dict] = [
            {"agentId": "team-lead@demo-team", "name": "team-lead", "agentType": "team-lead", "joinedAt": ms(0), "cwd": str(self.project)}
        ]
        self.sessions = self.dir / "projects" / project_dir_name(str(self.project))
        self.lead = Transcript(self.sessions / f"{LEAD_SESSION}.jsonl")
        self.write_config()

    def write_config(self) -> None:
        config = {
            "name": self.team,
            "createdAt": ms(0),
            "leadAgentId": "team-lead@demo-team",
            "leadSessionId": LEAD_SESSION,
            "members": self.members,
        }
        path = self.dir / "teams" / self.team / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config), encoding="utf-8")

    def add_member(self, name: str, joined: float, description: str) -> Transcript:
        self.members.append(
            {
                "agentId": f"{name}@demo-team",
                "name": name,
                "agentType": "general-purpose",
                "color": "blue",
                "model": "opus",
                "prompt": f"You are {name}. Contact: someone@example.com",
                "joinedAt": ms(joined),
                "cwd": str(self.project),
            }
        )
        self.write_config()
        sub = self.sessions / LEAD_SESSION / "subagents"
        sub.mkdir(parents=True, exist_ok=True)
        (sub / f"agent-a{name}-0123.meta.json").write_text(
            json.dumps({"name": name, "teamName": self.team, "description": description}), encoding="utf-8"
        )
        return Transcript(sub / f"agent-a{name}-0123.jsonl")

    def plan_path(self, agent: str) -> str:
        return str(self.project / ".agent-monitor" / "plans" / f"{agent}.md")

    def settings(self) -> Settings:
        return Settings(claude_dir=self.dir, runs_dir=self.dir.parent / "runs", web_dir=self.dir.parent / "web")


def write_story(fake: FakeClaude) -> Transcript:
    """The lead asks for work, spawns `builder`, who plans, codes, tests and reports back."""
    lead = fake.lead
    lead.user(T(-30), "Earlier unrelated question")
    lead.text(T(-29), "Earlier answer", end=True)
    lead.user(T(0), "Build the demo with a team")
    lead.text(T(1), "I'll start a builder.")
    lead.tool(T(2), "spawn-ghost", "Agent", {"name": "ghost", "description": "Ghost: never starts", "prompt": "boo"})
    lead.result(T(3), "spawn-ghost", "Lock file is already being held", error=True)
    lead.tool(T(10), "spawn-1", "Agent", {"name": "builder", "description": "Builder: make it", "prompt": "You are builder"})
    lead.result(T(11), "spawn-1", "Spawned successfully.")
    lead.text(T(11.5), "Builder is working.", end=True)

    b = fake.add_member("builder", 12, "Builder: make it")
    b.inbox(T(12), "team-lead", "Builder: make it", "You are builder")
    b.text(T(12.5), "Reading the code first.")
    b.tool(T(13), "r1", "Read", {"file_path": str(fake.project / "a.py")})
    b.result(T(13.2), "r1", "print('a')")
    b.tool(T(14), "r2", "Read", {"file_path": str(fake.project / "b.py")})
    b.result(T(14.2), "r2", "print('b')")
    plan = "# builder plan\n- [~] T1 Write code\n- [ ] T2 Test it\n"
    b.tool(T(15), "p1", "Write", {"file_path": fake.plan_path("builder"), "content": plan})
    b.result(T(15.1), "p1", "File created", extra={"type": "create"})
    b.tool(T(16), "w1", "Write", {"file_path": str(fake.project / "src" / "app.py"), "content": "print('app')\n"})
    b.result(T(16.1), "w1", "File created", extra={"type": "create", "structuredPatch": []})
    edit = {"file_path": fake.plan_path("builder"), "old_string": "- [~] T1 Write code\n- [ ] T2", "new_string": "- [x] T1 Write code\n- [~] T2"}
    b.tool(T(20), "p2", "Edit", edit)
    b.result(T(20.1), "p2", "Updated", extra={"originalFile": plan})
    b.tool(T(21), "t1", "Bash", {"command": "uv run pytest -q", "description": "Run the tests"})
    b.result(T(23), "t1", "...\n3 passed in 0.10s")
    final = "# builder plan\n- [x] T1 Write code\n- [x] T2 Test it\n- [!] T3 Deploy — no docker\n"
    b.tool(T(25), "p3", "Write", {"file_path": fake.plan_path("builder"), "content": final})
    b.result(T(25.1), "p3", "Updated", extra={"type": "update"})
    b.tool(T(26), "s1", "SendMessage", {"to": "team-lead", "summary": "Done", "message": "All done; key OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnopqrstuvwxyz"})
    b.result(T(26.1), "s1", '{"success": true}')
    b.text(T(27), "**Finished** the demo.", end=True)

    lead.inbox(T(26.5), "builder", "Done", "All done; key OPENROUTER_API_KEY=sk-or-v1-abcdefghijklmnopqrstuvwxyz")
    lead.idle(T(27.5), "builder")
    lead.text(T(28), "Great, the builder is done.", end=True)
    return b


@pytest.fixture
def fake():
    # Transcript folders embed the project path, so pytest's long tmp_path breaks Windows' path limit.
    root = Path(tempfile.mkdtemp(prefix="am-"))
    yield FakeClaude(root)
    shutil.rmtree(root, ignore_errors=True)
