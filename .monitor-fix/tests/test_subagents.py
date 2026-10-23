import json
from dataclasses import replace

from conftest import LEAD_SESSION, T
from monitor.watcher import Monitor


def background(fake, name, at):
    fake.lead.tool(T(at), f"spawn-{name}", "Agent", {"name": name, "description": name})
    child = fake.add_member(name, at, name)
    meta = child.path.with_name(child.path.stem + ".meta.json")
    meta.write_text(json.dumps({"name": name, "toolUseId": f"spawn-{name}"}), encoding="utf-8")
    (fake.dir / "teams" / fake.team / "config.json").unlink()
    child.text(T(at + 1), "Working")
    return child


def test_background_swarm_live_discovery_and_following(fake):
    fake.lead.user(T(0), "Start", cwd=str(fake.project))
    child = background(fake, "backend-auth", 5)
    monitor = Monitor(replace(fake.settings(), idle_end_seconds=10**9))
    monitor.discover()
    run_id = f"subagents-{LEAD_SESSION}"
    handle = monitor.runs[run_id]
    assert set(handle.snapshot.agents) == {"team-lead", "backend-auth"}
    assert handle.team.project == str(fake.project)
    child.tool(T(10), "edit", "Write", {"file_path": str(fake.project / "a.py"), "content": "x=1"})
    handle.poll()
    assert any(s["kind"] == "edit" for s in handle.snapshot.steps_for("backend-auth"))
    background(fake, "frontend-shell", 12)
    monitor.discover()
    handle.poll()
    assert set(handle.snapshot.agents) == {"team-lead", "backend-auth", "frontend-shell"}
    count = len(handle.events)
    monitor.discover()
    handle.poll()
    assert len(handle.events) == count
    assert len(monitor.runs) == 1


def test_registered_team_not_duplicated(fake):
    fake.lead.user(T(0), "Start")
    fake.add_member("builder", 5, "Builder").text(T(6), "Working")
    monitor = Monitor(replace(fake.settings(), idle_end_seconds=10**9))
    monitor.discover()
    assert list(monitor.runs) == ["demo-team"]


def test_incomplete_metadata_retried_and_unnamed_agent_ignored(fake):
    fake.lead.user(T(0), "Start", cwd=str(fake.project))
    child = background(fake, "builder", 5)
    meta = child.path.with_name(child.path.stem + ".meta.json")
    original = meta.read_text()
    meta.write_text('{"name":')
    monitor = Monitor(replace(fake.settings(), idle_end_seconds=10**9))
    monitor.discover()
    assert not monitor.runs
    meta.write_text(original)
    monitor.discover()
    assert len(monitor.runs) == 1
    meta.write_text(json.dumps({"toolUseId": "spawn-builder"}))
    from monitor.subagents import SubagentDiscovery
    assert SubagentDiscovery().discover(fake.dir, set()) == []
