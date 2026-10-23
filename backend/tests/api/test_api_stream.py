"""GET /api/stream/prices through the real routing, at the ASGI level.

TestClient and httpx's ASGITransport wait for the whole body, which never ends for SSE,
so this drives the app directly and disconnects after the first data event.
"""

import asyncio
import json

from app.config import Settings
from app.context import AppContext
from app.market import PriceCache


async def test_first_event_carries_every_tracked_price(tmp_path, make_app, market_factory):
    app = make_app(Settings(db_path=tmp_path / "sse.db", static_dir=tmp_path / "none"))
    cache = PriceCache()
    market = market_factory(cache)
    await market.start(["AAPL", "PYPL"])
    app.state.ctx = AppContext(cache=cache, market=market)

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
        "path": "/api/stream/prices",
        "raw_path": b"/api/stream/prices",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=5)

    start = sent[0]
    assert start["status"] == 200
    assert (b"content-type", b"text/event-stream; charset=utf-8") in start["headers"]
    bodies = [m["body"] for m in sent[1:] if m.get("body")]
    assert bodies[0] == b"retry: 1000\n\n"
    event = bodies[1].decode()
    assert event.startswith("data: ") and event.endswith("\n\n")
    payload = json.loads(event.removeprefix("data: "))
    assert set(payload) == {"AAPL", "PYPL"}
    assert payload["PYPL"] == cache.get("PYPL").to_dict()
