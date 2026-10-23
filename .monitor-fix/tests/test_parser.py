from conftest import T, write_story

from monitor.watcher import Monitor


def build(fake):
    write_story(fake)
    monitor = Monitor(fake.settings())
    monitor.discover()
    return monitor.runs["demo-team"]


def test_run_window_starts_at_the_last_prompt_before_the_team(fake):
    handle = build(fake)
    run = handle.snapshot.run
    assert run["started_at"] == T(0)
    assert run["team_started_at"] == T(12)
    # The run ended long ago (the fake data is from 2026-10-19), at the last activity.
    assert run["status"] == "ended" and run["ended_at"] == T(28)
    assert run["project"] == "project"


def test_agents_join_with_their_role_and_redacted_spec(fake):
    agents = build(fake).snapshot.agents
    assert list(agents) == ["team-lead", "builder"]
    builder = agents["builder"]
    assert builder["title"] == "Builder" and builder["assignment"] == "Builder: make it"
    assert "[email]" in builder["spec"] and "example.com" not in builder["spec"]
    assert builder["status"] == "done"
    assert builder["active_ms"] == 15_000  # 12s → 27s


def test_messages_are_matched_and_redacted(fake):
    snap = build(fake).snapshot
    msgs = {(m["from"], m["to"], m["kind"]): m for m in snap.messages.values()}
    assert msgs[("user", "team-lead", "prompt")]["status"] == "delivered"
    assignment = msgs[("team-lead", "builder", "assignment")]
    assert assignment["status"] == "delivered" and assignment["delivered_at"] == T(12)
    assert assignment["step_id"].startswith("team-lead-") and assignment["delivered_step_id"] == "builder-1"
    assert msgs[("team-lead", "ghost", "assignment")]["status"] == "failed"
    done = msgs[("builder", "team-lead", "message")]
    assert done["status"] == "delivered" and done["delivered_at"] == T(26.5)
    assert "sk-or" not in done["body"] and "OPENROUTER_API_KEY=[redacted]" in done["body"]
    assert len(snap.messages) == 4
    assert {t["id"] for t in snap.threads()} == {"team-lead~user", "builder~team-lead", "ghost~team-lead"}


def test_plan_file_drives_tasks_with_durations(fake):
    tasks = build(fake).snapshot.tasks
    assert tasks["builder:S1"]["source"] == "reconstructed"
    assert tasks["builder:S1"]["title"] == "Builder: make it"
    t1, t2, t3 = tasks["builder:T1"], tasks["builder:T2"], tasks["builder:T3"]
    assert (t1["status"], t1["started_at"], t1["ended_at"], t1["duration_ms"]) == ("completed", T(15.1), T(20.1), 5000)
    assert (t2["status"], t2["duration_ms"]) == ("completed", 5000)
    assert (t3["status"], t3["note"], t3["title"]) == ("failed", "no docker", "Deploy")
    assert [h["status"] for h in t1["history"]] == ["in_progress", "completed"]


def test_steps_are_grouped_and_titled(fake):
    snap = build(fake).snapshot
    steps = snap.steps_for("builder")
    titles = [(s["kind"], s["title"], s["task_id"]) for s in steps]
    assert titles == [
        ("message_in", "Assignment from team-lead: Builder: make it", "builder:S1"),
        ("read", "Read 2 files: a.py, b.py", "builder:S1"),
        ("plan", "Wrote my plan", "builder:S1"),
        ("edit", "Created app.py", "builder:T1"),
        ("plan", "Updated my plan", "builder:T1"),
        ("test", "Run the tests → 3 passed", "builder:T2"),
        ("plan", "Updated my plan", "builder:T2"),
        ("message_out", "Message to team-lead: Done", "builder:T2"),
        ("note", "Finished the demo.", "builder:T2"),
    ]
    assert steps[1]["files"] == [] and steps[3]["files"] == ["src/app.py"]
    assert steps[5]["tests"] == {"passed": 3, "failed": 0, "skipped": 0}
    detail = snap.step_detail(steps[1]["id"])
    kinds = [i["type"] for i in detail["items"]]
    assert kinds == ["text", "tool_call", "tool_result", "tool_call", "tool_result"]
    assert detail["items"][1]["input"] == {"file": "a.py"}


def test_lead_activity_outside_the_team_window_is_ignored(fake):
    snap = build(fake).snapshot
    texts = [i.get("text") for items in snap.items.values() for i in items]
    assert "Earlier answer" not in texts
    lead_steps = [s["title"] for s in snap.steps_for("team-lead")]
    assert lead_steps[0] == "Message from user: Build the demo with a team"
    assert "Started teammate builder" in lead_steps
