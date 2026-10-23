import json

from conftest import write_story
from fastapi.testclient import TestClient

from monitor.api import create_app
from monitor.watcher import Monitor


def client_for(fake) -> TestClient:
    write_story(fake)
    monitor = Monitor(fake.settings())
    monitor.discover()
    return TestClient(create_app(fake.settings(), monitor, watch=False))


def test_rest_endpoints(fake):
    client = client_for(fake)
    assert client.get("/api/health").json()["status"] == "ok"
    runs = client.get("/api/runs").json()["runs"]
    assert [(r["id"], r["agent_count"], r["message_count"]) for r in runs] == [("demo-team", 2, 4)]

    view = client.get("/api/runs/demo-team").json()
    assert {"run", "layout", "agents", "tasks", "seq", "now"} <= set(view)
    assert view["seq"] > 0 and len(view["tasks"]) == 5

    steps = client.get("/api/runs/demo-team/agents/builder/steps", params={"task": "builder:T1"}).json()["steps"]
    assert [s["title"] for s in steps] == ["Created app.py", "Updated my plan"]
    detail = client.get(f"/api/runs/demo-team/steps/{steps[0]['id']}").json()
    assert detail["items"][0]["input"]["file"] == "src/app.py"

    threads = client.get("/api/runs/demo-team/threads").json()["threads"]
    thread = client.get("/api/runs/demo-team/threads/builder~team-lead").json()
    assert thread["thread"]["count"] == 2 and len(threads) == 3
    assert client.get("/api/runs/demo-team/messages", params={"agent": "builder"}).json()["messages"]

    assert client.get("/api/runs/nope").status_code == 404
    assert client.get("/api/runs/demo-team/steps/nope").status_code == 404
    assert client.get("/api/runs/demo-team/agents/nobody/steps").status_code == 404


def test_layout_put_and_reset(fake):
    client = client_for(fake)
    assert client.put("/api/runs/demo-team/layout", json={"nodes": {}}).status_code == 400
    layout = client.put("/api/runs/demo-team/layout", json={"layers": [{"name": "Only", "nodes": ["builder"]}]}).json()["layout"]
    assert layout["source"] == "user" and [l["name"] for l in layout["layers"]] == ["Only", "Other"]
    assert client.get("/api/runs/demo-team").json()["layout"]["source"] == "user"
    assert client.delete("/api/runs/demo-team/layout").json()["layout"]["source"] == "default"


def test_replay_stream_sends_every_event_in_order(fake):
    client = client_for(fake)
    total = client.get("/api/runs/demo-team").json()["seq"]
    with client.stream("GET", "/api/runs/demo-team/events", params={"speed": 0, "keepalive": "false"}) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
    assert events[0]["type"] == "run.started" and events[-1]["type"] == "replay.finished"
    seqs = [e["seq"] for e in events if "seq" in e]
    assert seqs == list(range(1, total + 1))

    with client.stream("GET", "/api/runs/demo-team/events", params={"speed": 0, "keepalive": "false", "from": total - 1}) as response:
        tail = [json.loads(line[6:]) for line in response.iter_lines() if line.startswith("data: ")]
    assert [e.get("seq") for e in tail] == [total - 1, total, None]


def test_log_pages_through_stored_events(fake):
    client = client_for(fake)
    page = client.get("/api/runs/demo-team/log", params={"from": 2, "limit": 3}).json()
    assert [e["seq"] for e in page["events"]] == [2, 3, 4] and page["more"] is True
    rest = client.get("/api/runs/demo-team/log", params={"from": 5}).json()
    assert rest["more"] is False and rest["events"][-1]["type"] == "run.updated"
