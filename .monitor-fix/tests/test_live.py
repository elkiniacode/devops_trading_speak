"""Following a team while it works: new lines, new teammates, new runs, layouts."""

import json

from conftest import T, ms

from monitor.watcher import Monitor


def live_settings(fake):
    # Treat the fake 2026-10-19 data as recent so the run stays live.
    from dataclasses import replace

    return replace(fake.settings(), idle_end_seconds=10**9)


def test_new_transcript_lines_become_events(fake):
    fake.lead.user(T(0), "Go")
    b = fake.add_member("builder", 5, "Builder")
    b.inbox(T(5), "team-lead", "Start", "Start please")
    monitor = Monitor(live_settings(fake))
    monitor.discover()
    handle = monitor.runs["demo-team"]
    assert handle.live and handle.snapshot.run["status"] == "live"
    seen = len(handle.events)

    b.tool(T(6), "x1", "Bash", {"command": "npm test", "description": "Run unit tests"})
    b.result(T(9), "x1", "Tests  4 passed (4)")
    handle.poll()
    new = [e["type"] for e in handle.events[seen:]]
    assert "step.added" in new and "step.interaction" in new
    step = handle.snapshot.steps_for("builder")[-1]
    assert step["title"] == "Run unit tests → 4 passed" and step["status"] == "ok"
    saved = (fake.settings().runs_dir / "demo-team" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(saved) == len(handle.events)


def test_late_teammate_joins_the_live_run_and_a_much_later_one_starts_a_new_run(fake):
    fake.lead.user(T(0), "Go")
    a = fake.add_member("alpha", 5, "Alpha")
    a.inbox(T(5), "team-lead", "Start", "Start")
    a.text(T(6), "done", end=True)
    monitor = Monitor(live_settings(fake))
    monitor.discover()

    fake.add_member("beta", 60, "Beta").inbox(T(60), "team-lead", "Help", "Help alpha")
    monitor.discover()
    assert set(monitor.runs["demo-team"].snapshot.agents) == {"team-lead", "alpha", "beta"}

    fake.lead.user(T(5 * 3600), "New project")
    fake.add_member("gamma", 5 * 3600 + 10, "Gamma").inbox(T(5 * 3600 + 10), "team-lead", "Go", "Go")
    from dataclasses import replace

    monitor.settings = replace(monitor.settings, idle_end_seconds=3600)
    monitor.discover()
    second = monitor.runs["demo-team-2"]
    assert set(second.snapshot.agents) == {"team-lead", "gamma"}
    assert second.snapshot.run["started_at"] == T(5 * 3600)
    assert not monitor.runs["demo-team"].live


def test_layout_sources_team_file_then_user_override(fake):
    fake.lead.user(T(0), "Go")
    fake.add_member("alpha", 5, "Alpha").inbox(T(5), "team-lead", "Start", "Start")
    monitor = Monitor(live_settings(fake))
    monitor.discover()
    handle = monitor.runs["demo-team"]
    assert handle.snapshot.layout["source"] == "default"

    team_file = fake.project / ".agent-monitor" / "demo-team" / "layout.json"
    team_file.parent.mkdir(parents=True)
    team_file.write_text(json.dumps({"layers": [{"name": "All", "nodes": ["team-lead", "alpha"]}]}), encoding="utf-8")
    handle.poll()
    assert handle.snapshot.layout["source"] == "team"

    handle.set_user_layout({"layers": [{"name": "Mine", "nodes": ["alpha", "team-lead"]}]})
    assert handle.snapshot.layout["layers"][0]["name"] == "Mine"
    handle.set_user_layout(None)
    assert handle.snapshot.layout["source"] == "team"


def test_layout_written_by_the_lead_during_the_run(fake):
    fake.lead.user(T(0), "Go")
    layout = {"layers": [{"name": "Top", "nodes": ["team-lead"]}, {"name": "Crew", "nodes": ["alpha"]}],
              "edges": [{"from": "team-lead", "to": "alpha"}]}
    path = fake.project / ".agent-monitor" / "layout.json"
    fake.lead.tool(T(1), "l1", "Write", {"file_path": str(path), "content": json.dumps(layout)})
    fake.lead.result(T(1.1), "l1", "File created", extra={"type": "create"})
    fake.add_member("alpha", 5, "Alpha").inbox(T(5), "team-lead", "Start", "Start")
    monitor = Monitor(live_settings(fake))
    monitor.discover()
    snap = monitor.runs["demo-team"].snapshot
    assert snap.layout["source"] == "team" and [l["name"] for l in snap.layout["layers"]] == ["Top", "Crew"]
    assert snap.layout["edges"] == [{"from": "team-lead", "to": "alpha"}]
    assert snap.steps_for("team-lead")[1]["title"] == "Published the team layout"


def test_archived_runs_load_when_transcripts_are_gone(fake):
    fake.lead.user(T(0), "Go")
    fake.add_member("alpha", 5, "Alpha").inbox(T(5), "team-lead", "Start", "Start")
    Monitor(fake.settings()).discover()
    (fake.dir / "teams" / "demo-team" / "config.json").unlink()
    monitor = Monitor(fake.settings())
    monitor.discover()
    handle = monitor.runs["demo-team"]
    assert not handle.live and set(handle.snapshot.agents) == {"team-lead", "alpha"}


def test_join_time_matches_config(fake):
    fake.add_member("alpha", 5, "Alpha")
    assert fake.members[-1]["joinedAt"] == ms(5)
