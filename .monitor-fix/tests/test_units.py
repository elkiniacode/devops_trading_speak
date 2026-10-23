from monitor.layout import build_layout
from monitor.plans import parse_plan
from monitor.records import parse_record
from monitor.redact import Redactor
from monitor.steps import classify, parse_test_counts, step_title


def test_parse_plan_marks_ids_and_notes():
    items = parse_plan("# plan\n- [ ] T1 First\n* [~] T2: Second\n- [x] t3 Third\n- [!] Fourth — broke\n- [-] Fifth\nnot a task")
    assert [(i.key, i.title, i.status, i.note) for i in items] == [
        ("T1", "First", "pending", None),
        ("T2", "Second", "in_progress", None),
        ("T3", "Third", "completed", None),
        ("fourth", "Fourth", "failed", "broke"),
        ("fifth", "Fifth", "cancelled", None),
    ]


def test_redactor_masks_secrets_and_home_and_relativizes_paths():
    r = Redactor(home=r"C:\Users\pat", project=r"C:\Users\pat\work\app", names=("patsmith77",))
    assert r.text("mail pat@example.com") == "mail [email]"
    assert r.text("grep 'PatSmith77' in Users\\\\pat and home/pat") == "grep '[email]' in Users\\\\[user] and home/[user]"
    assert r.text(r"escaped\r\nUsers/pat 1") == r"escaped\r\nUsers/[user] 1"
    assert r.text("API_KEY=abc123 and sk-or-v1-0123456789abcdefghij") == "API_KEY=[redacted] and sk-[redacted]"
    assert r.text(r"C:\Users\pat\other and /mnt/c/Users/pat/x") == r"~\other and ~/x"
    assert r.path(r"C:\Users\pat\work\app\src\main.py") == "src/main.py"
    assert r.path("db/x.py", cwd=r"C:\Users\pat\work\app") == "db/x.py"
    assert r.path(r"C:\Users\pat\elsewhere\f.txt") == "~/elsewhere/f.txt"


def test_test_counts_take_the_last_summary_per_outcome():
    vitest = " Test Files  12 passed (12)\n      Tests  57 passed (57)"
    assert parse_test_counts(vitest) == {"passed": 57, "failed": 0, "skipped": 0}
    assert parse_test_counts("2 failed, 27 passed, 1 error in 3s") == {"passed": 27, "failed": 1, "skipped": 0}
    assert parse_test_counts("no tests ran") is None


def test_classify_and_titles():
    assert classify("Bash", {"command": "cd backend && uv run pytest -q"}) == "test"
    assert classify("Bash", {"command": "ls"}) == "command"
    assert classify("Agent", {"name": "x"}) == "spawn" and classify("Agent", {}) == "tool"
    assert classify("ToolSearch", {}) == "hidden"
    assert step_title("test", {"label": "Run tests", "tests": {"passed": 27, "failed": 2, "skipped": 0}}) == "Run tests → 2 failed, 27 passed"
    files = {"a.py": {"changes": 3, "created": False}}
    assert step_title("edit", {"files": files}) == "Edited a.py (3 changes)"
    assert step_title("edit", {"files": files, "failed": 1}) == "Edited a.py (3 changes)"
    assert step_title("edit", {"files": {"r.md": {"changes": 1, "created": False}}, "failed": 1}) == "Couldn't save r.md"


def test_records_split_batched_messages_and_skip_injected_context():
    content = (
        '<teammate-message teammate_id="a" summary="Hi &amp; bye">\nhello\n</teammate-message>\n'
        '<teammate-message teammate_id="b">\n{"type":"idle_notification","from":"b"}\n</teammate-message>'
    )
    items = parse_record({"type": "user", "timestamp": "t", "uuid": "u", "message": {"content": content}})
    assert [(i.kind, i.data.get("from"), i.data.get("summary")) for i in items] == [("inbox", "a", "Hi & bye"), ("idle", "b", None)]
    reminder = {"type": "user", "timestamp": "t", "uuid": "v", "message": {"content": "<system-reminder>x</system-reminder>"}}
    assert [i.kind for i in parse_record(reminder)] == ["notice"]
    cross = {"type": "user", "isMeta": True, "timestamp": "t", "uuid": "w",
             "message": {"content": 'Another Claude session sent a message:\n<agent-message from="ops">\nops: ready\n</agent-message>\nignore'}}
    assert [(i.kind, i.data["from"], i.data["body"]) for i in parse_record(cross)] == [("inbox", "ops", "ready")]


def test_layout_places_every_agent_and_drops_unknown_edges():
    agents = [{"name": "lead", "title": "Lead", "assignment": "Coordinates"}, {"name": "a", "title": "A", "assignment": "x"}]
    raw = {"layers": [{"name": "Top", "nodes": ["lead", "gate"]}], "nodes": {"gate": {"title": "Gate"}},
           "edges": [{"from": "lead", "to": "gate"}, {"from": "lead", "to": "nobody"}]}
    layout = build_layout(raw, agents, "lead", "team")
    assert [layer["nodes"] for layer in layout["layers"]] == [["lead", "gate"], ["a"]]
    assert layout["nodes"]["gate"] == {"agent": None, "title": "Gate", "subtitle": ""}
    assert layout["edges"] == [{"from": "lead", "to": "gate"}]
    assert build_layout(None, agents, "lead", "team")["source"] == "default"
