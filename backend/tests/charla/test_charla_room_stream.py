"""The room SSE streams (CONTRACT.md §5.6, §6.3): payload builder, generators and one ASGI smoke test."""

from __future__ import annotations

import asyncio
import json

from app.api import charla_room
from app.charla import accounts, common, content, room


class FakeRequest:
    """Just enough of a Request for the event generators."""

    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


def parse(event: str) -> dict:
    assert event.startswith("data: ") and event.endswith("\n\n")
    return json.loads(event.removeprefix("data: "))


def test_sse_data_is_one_compact_utf8_event():
    event = charla_room.sse_data({"text": "¿Qué?", "n": [1, 2]})
    assert event == 'data: {"text":"¿Qué?","n":[1,2]}\n\n'


async def test_attendee_stream_resends_me_after_own_answer(charla_client, enter, admin, monkeypatch):
    monkeypatch.setattr(charla_room, "PUSH_INTERVAL", 0)
    token = enter("Ana", "ana@example.com")
    attendee = accounts.attendee_for_token(token)
    charla_client.post("/api/charla/admin/launch", headers=admin)

    events = charla_room.attendee_events(FakeRequest(), attendee)
    assert await events.__anext__() == "retry: 2000\n\n"
    first = parse(await events.__anext__())
    assert first["state"]["phase"] == "open" and first["me"]["username"] == "Ana"
    assert first["me"]["answer"] is None

    public = common.bus.public_version
    room.submit_answer(attendee["id"], 0, 1, None)  # step 0 is a poll
    assert common.bus.public_version == public  # only this attendee's stream should resend
    second = parse(await asyncio.wait_for(events.__anext__(), 2))
    assert second["me"]["answer"]["choice"] == 1
    assert second["me"]["result"] is None

    monkeypatch.setattr(charla_room, "HEARTBEAT_INTERVAL", 0)
    assert await asyncio.wait_for(events.__anext__(), 2) == ": keepalive\n\n"  # nothing changed
    await events.aclose()


async def test_admin_stream_refreshes_while_open(charla_client, admin, monkeypatch):
    monkeypatch.setattr(charla_room, "PUSH_INTERVAL", 0)
    monkeypatch.setattr(charla_room, "ADMIN_OPEN_REFRESH", 0)
    monkeypatch.setattr(charla_room, "HEARTBEAT_INTERVAL", 0)
    events = charla_room.admin_events(FakeRequest())
    assert await events.__anext__() == "retry: 2000\n\n"
    idle = parse(await events.__anext__())
    assert idle["state"]["phase"] == "idle" and len(idle["script"]) == content.STEPS
    assert await asyncio.wait_for(events.__anext__(), 2) == ": keepalive\n\n"  # idle: no resend

    charla_client.post("/api/charla/admin/launch", headers=admin)
    assert parse(await asyncio.wait_for(events.__anext__(), 2))["state"]["phase"] == "open"
    again = await asyncio.wait_for(events.__anext__(), 2)  # open: resent without a bus change
    assert parse(again)["state"]["phase"] == "open"
    await events.aclose()


def test_stream_rejects_a_bad_token_before_streaming(charla_client):
    res = charla_client.get("/api/charla/stream?t=nope")
    assert res.status_code == 401
    assert res.json() == {"detail": "Tu sesión expiró. Vuelve a registrarte."}
    assert charla_client.get("/api/charla/stream").status_code == 401


async def test_attendee_stream_over_asgi(charla_client, enter):
    token = enter("Ana", "ana@example.com")
    app = charla_client.app
    got_data = asyncio.Event()
    request_sent = False
    sent: list[dict] = []

    async def receive() -> dict:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await got_data.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and message.get("body", b"").startswith(b"data:"):
            got_data.set()

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/charla/stream",
        "raw_path": b"/api/charla/stream",
        "root_path": "",
        "query_string": f"t={token}".encode(),
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "app": app,
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=5)

    start = sent[0]
    assert start["status"] == 200
    assert (b"content-type", b"text/event-stream; charset=utf-8") in start["headers"]
    bodies = [m["body"] for m in sent[1:] if m.get("body")]
    assert bodies[0] == b"retry: 2000\n\n"
    payload = parse(bodies[1].decode())
    assert set(payload) == {"state", "me"}
    assert payload["me"]["username"] == "Ana" and payload["state"]["room_count"] == 1
