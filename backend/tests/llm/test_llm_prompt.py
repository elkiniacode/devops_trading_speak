from app import db
from app.llm.prompt import SYSTEM_PROMPT, build_context, build_messages, format_action_results


def test_system_prompt_covers_the_contract_rules():
    text = SYSTEM_PROMPT
    assert "FinAlly, an AI trading assistant" in text
    assert "Placing a buy order for 10 AAPL" in text  # intent, not past tense
    assert "clarifying question" in text
    assert "only when the user asks" in text
    assert "[Action results]" in text
    assert '"watchlist_changes"' in text


def test_context_with_cash_only(ctx):
    text = build_context(ctx)
    assert "Market data: simulator (simulated prices" in text
    assert "Cash: $10,000.00" in text
    assert "Total portfolio value: $10,000.00 (total P&L +$0.00, +0.00%" in text
    assert "Positions: none (all cash)." in text
    assert "- AAPL: $190.00 (+1.00%)" in text
    assert text.count("\n- ") == 10  # the seeded watchlist


def test_context_with_positions(ctx):
    db.apply_trade("AAPL", "buy", 10, 180.0)  # now priced at 190 -> +$100, +5.56%
    db.apply_trade("PYPL", "buy", 2.5, 80.0)  # held, not on the watchlist: priced at 70 -> -$25
    ctx.market.track(["PYPL"])
    text = build_context(ctx)
    assert "Cash: $8,000.00" in text
    assert "Total portfolio value: $10,075.00 (total P&L +$75.00, +0.75%" in text
    assert (
        "- AAPL: 10 sh, avg cost $180.00, price $190.00, value $1,900.00 (18.9% of portfolio), "
        "unrealized P&L +$100.00 (+5.56%)"
    ) in text
    assert "- PYPL: 2.5 sh, avg cost $80.00, price $70.00, value $175.00 (1.7% of portfolio), " in text
    assert "unrealized P&L -$25.00 (-12.50%)" in text


def test_context_flags_unpriced_positions_and_eod_mode(ctx):
    db.apply_trade("XYZ", "buy", 1, 50.0)  # never priced
    ctx.market._mode = "massive-eod"
    ctx.cache.remove("NFLX")
    text = build_context(ctx)
    assert "Market data: massive-eod (END-OF-DAY closing prices, not live" in text
    assert "some positions have no price yet" in text
    assert "- XYZ: 1 sh, avg cost $50.00, no current price" in text
    assert "- NFLX: no price yet" in text


def test_action_results_block():
    actions = {
        "watchlist_changes": [
            {"ticker": "PYPL", "action": "add", "status": "ok", "error": None},
            {"ticker": "ZZZZ", "action": "add", "status": "failed", "error": "Unknown ticker: ZZZZ"},
        ],
        "trades": [
            {"ticker": "AAPL", "side": "buy", "quantity": 5.0, "status": "ok", "price": 190.12, "error": None},
            {
                "ticker": "TSLA",
                "side": "sell",
                "quantity": 2.0,
                "status": "failed",
                "price": None,
                "error": "Insufficient shares: you have 0 TSLA, tried to sell 2",
            },
        ],
    }
    assert format_action_results(actions) == (
        "\n\n[Action results]\n"
        "- watchlist add PYPL: ok\n"
        "- watchlist add ZZZZ: FAILED: Unknown ticker: ZZZZ\n"
        "- buy 5 AAPL: filled at $190.12\n"
        "- sell 2 TSLA: FAILED: Insufficient shares: you have 0 TSLA, tried to sell 2"
    )
    assert format_action_results(None) == ""
    assert format_action_results({"watchlist_changes": [], "trades": []}) == ""


def test_messages_are_system_then_history(ctx):
    db.add_chat_message("user", "buy 5 AAPL", None)
    db.add_chat_message(
        "assistant",
        "Placing a buy order for 5 AAPL.",
        {
            "watchlist_changes": [],
            "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5.0, "status": "ok", "price": 190.0, "error": None}],
        },
    )
    db.add_chat_message("user", "how am I doing?", None)
    messages = build_messages(ctx, db.get_chat_messages(20))
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[0]["content"].startswith(SYSTEM_PROMPT)
    assert "## Current state" in messages[0]["content"]
    assert messages[1]["content"] == "buy 5 AAPL"
    assert messages[2]["content"] == (
        "Placing a buy order for 5 AAPL.\n\n[Action results]\n- buy 5 AAPL: filled at $190.00"
    )
    assert messages[3]["content"] == "how am I doing?"
