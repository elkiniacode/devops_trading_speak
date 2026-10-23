import json

import pytest

from app import db
from app.llm import client, service
from app.llm.mock import FALLBACK_MESSAGE
from app.llm.service import LLMNotConfigured, LLMUnavailable, handle_chat


def reply(message="On it.", trades=(), watchlist_changes=()) -> str:
    return json.dumps({"message": message, "trades": list(trades), "watchlist_changes": list(watchlist_changes)})


class FakeModel:
    """Stands in for client.complete: returns queued outputs and records the prompts."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls: list[list[dict]] = []

    async def __call__(self, messages):
        self.calls.append(messages)
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


@pytest.fixture
def model(monkeypatch, real_llm):
    def install(*outputs) -> FakeModel:
        fake = FakeModel(*outputs)
        monkeypatch.setattr(client, "complete", fake)
        return fake

    return install


# ---------------------------------------------------------------- mock mode, end to end


async def test_mock_buy_executes_and_is_stored(ctx):
    msg = await handle_chat(ctx, "buy 5 AAPL")
    assert set(msg) == {"id", "role", "content", "actions", "created_at"}
    assert msg["role"] == "assistant"
    assert msg["content"] == "Placing a buy order for 5 AAPL."
    assert msg["actions"] == {
        "watchlist_changes": [],
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5.0, "status": "ok", "price": 190.0, "error": None}],
    }
    assert db.get_cash() == 10_000 - 950
    assert db.get_position("AAPL")["quantity"] == 5.0
    assert db.get_snapshots()[-1]["total_value"] == 10_000.0  # snapshot recorded after the trade

    history = db.get_chat_messages(50)
    assert [(m["role"], m["content"], m["actions"]) for m in history] == [
        ("user", "buy 5 AAPL", None),
        ("assistant", "Placing a buy order for 5 AAPL.", msg["actions"]),
    ]
    assert history[1]["id"] == msg["id"]


async def test_mock_fallback_has_empty_actions(ctx):
    msg = await handle_chat(ctx, "what's up?")
    assert msg["content"] == FALLBACK_MESSAGE
    assert msg["actions"] == {"watchlist_changes": [], "trades": []}


async def test_mock_pending_order_risk_and_close_are_recorded(ctx):
    pending = await handle_chat(ctx, "limit buy $500 AAPL at $180")
    assert pending["actions"]["orders"][0]["order_status"] == "pending"
    assert db.get_orders()[0]["trigger_price"] == 180.0

    await handle_chat(ctx, "buy 1 AAPL")
    risk = await handle_chat(ctx, "risk AAPL SL 170 TP 220")
    assert risk["actions"]["risks"][0]["status"] == "ok"
    assert db.get_risk("AAPL")[0]["take_profit"] == 220.0

    closed = await handle_chat(ctx, "close AAPL")
    assert closed["actions"]["closes"][0]["status"] == "ok"
    assert db.get_position("AAPL") is None
    assert db.get_risk("AAPL") == []


async def test_mock_portfolio_summary_uses_current_account(ctx):
    msg = await handle_chat(ctx, "How is my portfolio doing?", {"ticker": "AAPL"})
    assert "Portafolio simulado" in msg["content"]
    assert "$10,000.00" in msg["content"]
    assert msg["actions"] == {"watchlist_changes": [], "trades": []}


async def test_mixed_success_and_failure(ctx):
    db.apply_trade("TSLA", "buy", 1, 250.0)
    msg = await handle_chat(ctx, "add PYPL, add ZZZZ, remove NFLX, buy 1 AAPL, sell 5 TSLA, buy 1000 NVDA, buy 1 PYPL")
    assert msg["actions"]["watchlist_changes"] == [
        {"ticker": "PYPL", "action": "add", "status": "ok", "error": None},
        {"ticker": "ZZZZ", "action": "add", "status": "failed", "error": "Unknown ticker: ZZZZ"},
        {"ticker": "NFLX", "action": "remove", "status": "ok", "error": None},
    ]
    trades = msg["actions"]["trades"]
    assert [(t["ticker"], t["side"], t["status"], t["price"]) for t in trades] == [
        ("AAPL", "buy", "ok", 190.0),
        ("TSLA", "sell", "failed", None),
        ("NVDA", "buy", "failed", None),
        ("PYPL", "buy", "ok", 70.0),
    ]
    assert trades[1]["error"].startswith("Insufficient shares")
    assert trades[2]["error"].startswith("Insufficient cash")
    assert all(t["error"] is None for t in trades if t["status"] == "ok")

    watchlist = [w["ticker"] for w in db.get_watchlist()]
    assert "PYPL" in watchlist and "NFLX" not in watchlist and "ZZZZ" not in watchlist
    assert {p["ticker"]: p["quantity"] for p in db.get_positions()} == {"AAPL": 1.0, "PYPL": 1.0, "TSLA": 1.0}
    assert db.get_chat_messages(1)[0]["actions"] == msg["actions"]  # stored exactly as returned


async def test_watchlist_changes_run_before_trades(ctx, monkeypatch):
    order = []

    async def add(ctx, ticker):
        order.append(("add", ticker))
        return ticker

    async def trade(ctx, ticker, side, quantity):
        order.append((side, ticker))
        return {"ticker": ticker, "quantity": quantity, "price": 1.0}

    monkeypatch.setattr(service, "add_to_watchlist", add)
    monkeypatch.setattr(service, "execute_trade", trade)
    await handle_chat(ctx, "buy 1 AAPL then add PYPL then sell 1 MSFT then add V")
    assert order == [("add", "PYPL"), ("add", "V"), ("buy", "AAPL"), ("sell", "MSFT")]


async def test_unexpected_error_fails_one_action_and_the_rest_continue(ctx, monkeypatch):
    real_trade = service.execute_trade

    async def flaky(ctx, ticker, side, quantity):
        if ticker == "MSFT":
            raise RuntimeError("database is locked")
        return await real_trade(ctx, ticker, side, quantity)

    monkeypatch.setattr(service, "execute_trade", flaky)
    msg = await handle_chat(ctx, "buy 1 MSFT and buy 1 AAPL")
    assert [(t["ticker"], t["status"]) for t in msg["actions"]["trades"]] == [("MSFT", "failed"), ("AAPL", "ok")]
    assert msg["actions"]["trades"][0]["error"] == "Unexpected error while executing this action"
    assert "database is locked" not in json.dumps(msg)


async def test_mock_zero_quantity_fails_only_that_trade(ctx):
    msg = await handle_chat(ctx, "buy 0 MSFT and buy 1 AAPL")
    assert msg["content"] == "Placing a buy order for 0 MSFT. Placing a buy order for 1 AAPL."
    assert msg["actions"]["trades"] == [
        {"ticker": "MSFT", "side": "buy", "quantity": 0.0, "status": "failed", "price": None,
         "error": "Quantity must be greater than 0"},
        {"ticker": "AAPL", "side": "buy", "quantity": 1.0, "status": "ok", "price": 190.0, "error": None},
    ]
    assert {p["ticker"] for p in db.get_positions()} == {"AAPL"}


async def test_mock_structural_failure_executes_nothing(ctx):
    with pytest.raises(LLMUnavailable):
        await handle_chat(ctx, "add PYPL " + "buy 1 AAPL " * 11)  # more than 10 trades: the whole reply is invalid
    assert db.get_cash() == 10_000
    assert db.get_positions() == []
    assert "PYPL" not in [w["ticker"] for w in db.get_watchlist()]
    assert [m["role"] for m in db.get_chat_messages(50)] == ["user"]


async def test_unconfigured_stores_nothing(ctx, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    with pytest.raises(LLMNotConfigured, match="OPENROUTER_API_KEY or LLM_MOCK=true"):
        await handle_chat(ctx, "hi")
    assert db.get_chat_messages(50) == []


# ---------------------------------------------------------------- real path with a fake model


async def test_real_reply_is_executed(ctx, model):
    fake = model(
        reply(
            "Adding PYPL to your watchlist and placing a buy order for 2 PYPL.",
            trades=[{"ticker": "pypl", "side": "buy", "quantity": 2}],
            watchlist_changes=[{"ticker": "PYPL", "action": "add"}],
        )
    )
    msg = await handle_chat(ctx, "add paypal and buy 2")
    assert len(fake.calls) == 1
    assert msg["actions"] == {
        "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "ok", "error": None}],
        "trades": [{"ticker": "PYPL", "side": "buy", "quantity": 2.0, "status": "ok", "price": 70.0, "error": None}],
    }


async def test_business_rule_failures_from_the_model_are_per_action(ctx, model):
    model(
        reply(
            "Placing orders.",
            trades=[
                {"ticker": "AAPL", "side": "buy", "quantity": -2},
                {"ticker": "AAPL", "side": "buy", "quantity": 1.23456},
                {"ticker": "", "side": "buy", "quantity": 1},
                {"ticker": "nvda", "side": "buy", "quantity": 2000000},
                {"ticker": "MSFT", "side": "buy", "quantity": 0.5},
            ],
            watchlist_changes=[{"ticker": "BAD$", "action": "add"}],
        )
    )
    msg = await handle_chat(ctx, "do it")
    assert msg["actions"]["watchlist_changes"] == [
        {"ticker": "BAD$", "action": "add", "status": "failed", "error": "Invalid ticker symbol: 'BAD$'"}
    ]
    assert [(t["ticker"], t["status"], t["error"]) for t in msg["actions"]["trades"]] == [
        ("AAPL", "failed", "Quantity must be greater than 0"),
        ("AAPL", "failed", "Quantity can have at most 4 decimal places"),
        ("", "failed", "Invalid ticker symbol: ''"),
        ("NVDA", "failed", "Quantity can be at most 1,000,000"),
        ("MSFT", "ok", None),
    ]
    assert db.get_position("MSFT")["quantity"] == 0.5


async def test_prompt_has_context_and_last_20_messages(ctx, model):
    for i in range(15):
        db.add_chat_message("user", f"question {i}", None)
        db.add_chat_message(
            "assistant",
            f"answer {i}",
            {
                "watchlist_changes": [],
                "trades": [
                    {"ticker": "TSLA", "side": "sell", "quantity": 1.0, "status": "failed", "price": None,
                     "error": "Insufficient shares: you have 0 TSLA, tried to sell 1"}
                ],
            },
        )
    fake = model(reply())
    await handle_chat(ctx, "latest")
    (messages,) = fake.calls
    assert messages[0]["role"] == "system" and "Cash: $10,000.00" in messages[0]["content"]
    history = messages[1:]
    assert len(history) == 20
    assert history[-1] == {"role": "user", "content": "latest"}
    assert history[0] == {"role": "assistant", "content": history[0]["content"]}
    assert history[0]["content"].startswith("answer 5\n\n[Action results]\n- sell 1 TSLA: FAILED: Insufficient shares")


async def test_retry_once_after_invalid_output(ctx, model):
    fake = model("not json at all", reply("Placing a buy order for 1 AAPL.", trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1}]))
    msg = await handle_chat(ctx, "buy one apple")
    assert msg["actions"]["trades"][0]["status"] == "ok"
    assert len(fake.calls) == 2
    retry = fake.calls[1]
    assert retry[:-2] == fake.calls[0]
    assert retry[-2] == {"role": "assistant", "content": "not json at all"}
    assert retry[-1]["role"] == "user" and "not valid JSON" in retry[-1]["content"]


async def test_two_invalid_outputs_raise_and_execute_nothing(ctx, model):
    too_many = reply(trades=[{"ticker": "AAPL", "side": "buy", "quantity": 1}] * 11)
    fake = model(too_many, too_many)
    with pytest.raises(LLMUnavailable):
        await handle_chat(ctx, "buy 11 lots of AAPL")
    assert len(fake.calls) == 2
    assert db.get_cash() == 10_000 and db.get_positions() == []
    assert [(m["role"], m["content"]) for m in db.get_chat_messages(50)] == [("user", "buy 11 lots of AAPL")]


async def test_empty_content_counts_as_invalid(ctx, model):
    fake = model(None, reply("Hello."))
    assert (await handle_chat(ctx, "hi"))["content"] == "Hello."
    assert len(fake.calls) == 2
    assert fake.calls[1][-1]["role"] == "user"  # no empty assistant turn was added


async def test_upstream_error_is_not_retried(ctx, model):
    fake = model(TimeoutError(), reply())
    with pytest.raises(LLMUnavailable):
        await handle_chat(ctx, "hi")
    assert len(fake.calls) == 1
    assert [m["role"] for m in db.get_chat_messages(50)] == ["user"]
