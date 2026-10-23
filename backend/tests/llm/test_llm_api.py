import re

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.llm import client
from app.llm.mock import FALLBACK_MESSAGE

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")


def test_post_chat_returns_the_assistant_message(api):
    r = api.post("/api/chat", json={"message": "  Buy 5 AAPL and add PYPL  "})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"id", "role", "content", "actions", "created_at"}
    assert body["role"] == "assistant" and ISO.match(body["created_at"])
    assert body["content"] == "Adding PYPL to your watchlist. Placing a buy order for 5 AAPL."
    assert body["actions"] == {
        "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "ok", "error": None}],
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5.0, "status": "ok", "price": 190.0, "error": None}],
    }
    assert db.get_chat_messages(1)[0]["id"] == body["id"]
    assert db.get_chat_messages(2)[0]["content"] == "Buy 5 AAPL and add PYPL"  # stored trimmed


def test_failed_actions_still_return_200(api):
    r = api.post("/api/chat", json={"message": "sell 1 AAPL"})
    assert r.status_code == 200
    (trade,) = r.json()["actions"]["trades"]
    assert trade["status"] == "failed" and trade["price"] is None
    assert trade["error"] == "Insufficient shares: you have 0 AAPL, tried to sell 1"


def test_zero_quantity_is_a_failed_trade_not_a_502(api):
    r = api.post("/api/chat", json={"message": "buy 0 AAPL"})
    assert r.status_code == 200
    assert r.json()["actions"]["trades"] == [
        {"ticker": "AAPL", "side": "buy", "quantity": 0.0, "status": "failed", "price": None,
         "error": "Quantity must be greater than 0"}
    ]


@pytest.mark.parametrize("message", ["", "   ", "\n\t"])
def test_empty_message_is_400(api, message):
    r = api.post("/api/chat", json={"message": message})
    assert r.status_code == 400 and r.json()["detail"] == "Message must not be empty"
    assert db.get_chat_messages(50) == []


def test_message_length_limit(api):
    assert api.post("/api/chat", json={"message": "x" * 2000}).status_code == 200
    assert api.post("/api/chat", json={"message": " " + "x" * 2000 + " "}).status_code == 200  # trimmed first
    r = api.post("/api/chat", json={"message": "x" * 2001})
    assert r.status_code == 400 and "2,000" in r.json()["detail"]


@pytest.mark.parametrize("body", [{}, {"message": 5}, {"message": None}, {"text": "hi"}])
def test_malformed_body_is_422(api, body):
    assert api.post("/api/chat", json=body).status_code == 422


def test_unconfigured_is_503(api, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    r = api.post("/api/chat", json={"message": "hi"})
    assert r.status_code == 503
    assert r.json() == {"detail": "AI chat is not configured: set OPENROUTER_API_KEY or LLM_MOCK=true"}


def test_upstream_failure_is_502_and_keeps_the_user_message(api, monkeypatch, real_llm):
    async def down(messages):
        raise ConnectionError("openrouter unreachable")

    monkeypatch.setattr(client, "complete", down)
    r = api.post("/api/chat", json={"message": "buy 1 AAPL"})
    assert r.status_code == 502
    assert r.json() == {"detail": "The AI assistant is unavailable right now. Please try again."}
    assert [(m["role"], m["content"]) for m in db.get_chat_messages(50)] == [("user", "buy 1 AAPL")]
    assert db.get_positions() == []


def test_history_is_oldest_first_with_actions(api):
    api.post("/api/chat", json={"message": "buy 1 AAPL"})
    api.post("/api/chat", json={"message": "hello"})
    r = api.get("/api/chat/history")
    assert r.status_code == 200
    messages = r.json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "buy 1 AAPL"),
        ("assistant", "Placing a buy order for 1 AAPL."),
        ("user", "hello"),
        ("assistant", FALLBACK_MESSAGE),
    ]
    assert messages[0]["actions"] is None and messages[2]["actions"] is None
    assert messages[1]["actions"]["trades"][0]["status"] == "ok"
    assert messages[3]["actions"] == {"watchlist_changes": [], "trades": []}
    assert all(set(m) == {"id", "role", "content", "actions", "created_at"} for m in messages)

    last_two = api.get("/api/chat/history", params={"limit": 2}).json()["messages"]
    assert [m["content"] for m in last_two] == ["hello", FALLBACK_MESSAGE]


def test_history_empty_and_limit_bounds(api):
    assert api.get("/api/chat/history").json() == {"messages": []}
    assert api.get("/api/chat/history", params={"limit": 0}).status_code == 422
    assert api.get("/api/chat/history", params={"limit": 501}).status_code == 422
    assert api.get("/api/chat/history", params={"limit": "x"}).status_code == 422


def test_routes_are_included_by_main(tmp_path, stub_market_factory):
    from app.main import create_app

    settings = Settings(db_path=tmp_path / "main.db", static_dir=tmp_path / "no-static", cors_origins=[])
    app = create_app(settings, market_factory=stub_market_factory)
    with TestClient(app) as http:
        r = http.post("/api/chat", json={"message": "buy 1 AAPL"})
        assert r.status_code == 200 and r.json()["actions"]["trades"][0]["status"] == "ok"
        assert len(http.get("/api/chat/history").json()["messages"]) == 2
        assert http.get("/api/health").json()["llm"] == "mock"
