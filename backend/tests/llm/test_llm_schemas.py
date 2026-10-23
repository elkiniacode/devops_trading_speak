import json

import pytest
from openai.lib._pydantic import to_strict_json_schema

from app.llm.schemas import MAX_ACTIONS, ChatReply, InvalidReply, parse_reply


def reply(**overrides) -> str:
    body = {"message": "Placing a buy order for 10 AAPL.", "trades": [], "watchlist_changes": []}
    body.update(overrides)
    return json.dumps(body)


def trade(ticker="AAPL", side="buy", quantity=1):
    return {"ticker": ticker, "side": side, "quantity": quantity}


def change(ticker="PYPL", action="add"):
    return {"ticker": ticker, "action": action}


def test_valid_reply_parses_and_tidies_tickers():
    r = parse_reply(
        reply(
            message="  Buying.  ",
            trades=[trade(" aapl ", "buy", 10), trade("TSLA", "sell", 0.5)],
            watchlist_changes=[change("pypl", "add"), change("NFLX", "remove")],
        )
    )
    assert r.message == "Buying."
    assert [(t.ticker, t.side, t.quantity) for t in r.trades] == [("AAPL", "buy", 10.0), ("TSLA", "sell", 0.5)]
    assert isinstance(r.trades[0].quantity, float)
    assert [(c.ticker, c.action) for c in r.watchlist_changes] == [("PYPL", "add"), ("NFLX", "remove")]


def test_empty_action_lists_are_fine():
    r = parse_reply(reply())
    assert r.trades == [] and r.watchlist_changes == []


def test_code_fenced_json_is_accepted():
    assert parse_reply(f"```json\n{reply()}\n```").message == "Placing a buy order for 10 AAPL."


@pytest.mark.parametrize("raw", [None, "", "   ", "not json", '{"message": "hi"', "[]", "```json\n```"])
def test_malformed_output_is_invalid(raw):
    with pytest.raises(InvalidReply):
        parse_reply(raw)


def test_invalid_json_reason_is_short():
    with pytest.raises(InvalidReply, match="not valid JSON"):
        parse_reply("Sure! Here you go: {")


@pytest.mark.parametrize("missing", ["message", "trades", "watchlist_changes"])
def test_every_key_is_required(missing):
    body = json.loads(reply())
    del body[missing]
    with pytest.raises(InvalidReply, match=missing):
        parse_reply(json.dumps(body))


@pytest.mark.parametrize(
    "overrides",
    [
        {"message": "   "},
        {"message": 5},
        {"extra": 1},
        {"trades": None},
        {"trades": [trade(side="short")]},
        {"trades": [trade(quantity="5")]},
        {"trades": [trade(quantity=True)]},
        {"trades": [trade(quantity=None)]},
        {"trades": [trade(ticker=5)]},
        {"trades": [{**trade(), "price": 190}]},
        {"trades": [{"ticker": "AAPL", "side": "buy"}]},
        {"watchlist_changes": [change(action="toggle")]},
        {"watchlist_changes": [{"ticker": "PYPL"}]},
    ],
)
def test_bad_fields_make_the_whole_reply_invalid(overrides):
    with pytest.raises(InvalidReply):
        parse_reply(reply(**overrides))


def test_one_bad_trade_invalidates_the_good_ones_too():
    with pytest.raises(InvalidReply, match="trades.1.side"):
        parse_reply(reply(trades=[trade(), trade(side="short")]))


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_non_finite_quantity_is_a_type_error(token):
    raw = reply(trades=[trade()]).replace('"quantity": 1', f'"quantity": {token}')
    with pytest.raises(InvalidReply, match="finite number"):
        parse_reply(raw)


def test_business_rules_are_left_to_the_services():
    """Quantity sign, decimal places and ticker format fail one action later, not the whole reply."""
    r = parse_reply(
        reply(
            trades=[trade(quantity=0), trade(quantity=-3), trade(quantity=1.23456), trade(ticker="  "), trade(ticker="A$")],
            watchlist_changes=[change(ticker=""), change(ticker="TOOLONG")],
        )
    )
    assert [(t.ticker, t.quantity) for t in r.trades] == [("AAPL", 0), ("AAPL", -3), ("AAPL", 1.23456), ("", 1), ("A$", 1)]
    assert [c.ticker for c in r.watchlist_changes] == ["", "TOOLONG"]


def test_action_caps():
    assert len(parse_reply(reply(trades=[trade()] * MAX_ACTIONS)).trades) == MAX_ACTIONS
    assert len(parse_reply(reply(watchlist_changes=[change()] * MAX_ACTIONS)).watchlist_changes) == MAX_ACTIONS
    with pytest.raises(InvalidReply, match="at most 10"):
        parse_reply(reply(trades=[trade()] * (MAX_ACTIONS + 1)))
    with pytest.raises(InvalidReply, match="at most 10"):
        parse_reply(reply(watchlist_changes=[change()] * (MAX_ACTIONS + 1)))


def test_schema_sent_to_the_model_is_strict_and_plain():
    schema = to_strict_json_schema(ChatReply)  # what litellm sends for response_format=ChatReply
    assert schema["required"] == ["message", "trades", "watchlist_changes", "orders", "closes", "risks"]
    assert schema["additionalProperties"] is False
    defs = schema["$defs"]
    assert defs["TradeRequest"]["required"] == ["ticker", "side", "quantity"]
    assert defs["TradeRequest"]["properties"]["side"]["enum"] == ["buy", "sell"]
    assert defs["WatchlistChange"]["properties"]["action"]["enum"] == ["add", "remove"]
    assert all(d["additionalProperties"] is False for d in defs.values())
    # Rules live in validators; keywords some strict providers reject stay out of the schema.
    text = json.dumps(schema)
    for keyword in ["exclusiveMinimum", "minimum", "maxItems", "minLength", "pattern", "default"]:
        assert f'"{keyword}"' not in text
