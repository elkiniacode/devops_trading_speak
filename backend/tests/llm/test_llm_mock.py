import json

import pytest

from app.llm.mock import FALLBACK_MESSAGE, mock_reply
from app.llm.schemas import parse_reply


def run(message: str) -> dict:
    return json.loads(mock_reply(message))


def test_fallback_text_is_exact():
    assert FALLBACK_MESSAGE == (
        "I'm FinAlly, running in mock mode. "
        'Try "buy 1 AAPL", "sell 1 AAPL", "add PYPL" or "remove PYPL".'
    )
    assert run("hello there") == {"message": FALLBACK_MESSAGE, "trades": [], "watchlist_changes": []}


@pytest.mark.parametrize(
    "message, expected",
    [
        ("buy 5 AAPL", {"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5.0}], "watchlist_changes": []}),
        ("sell 2 TSLA", {"trades": [{"ticker": "TSLA", "side": "sell", "quantity": 2.0}], "watchlist_changes": []}),
        ("add PYPL", {"trades": [], "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}),
        ("remove NFLX", {"trades": [], "watchlist_changes": [{"ticker": "NFLX", "action": "remove"}]}),
    ],
)
def test_each_pattern(message, expected):
    out = run(message)
    assert {k: out[k] for k in ("trades", "watchlist_changes")} == expected


@pytest.mark.parametrize(
    "message, text",
    [
        ("buy 5 AAPL", "Placing a buy order for 5 AAPL."),
        ("sell 2 TSLA", "Placing a sell order for 2 TSLA."),
        ("add PYPL", "Adding PYPL to your watchlist."),
        ("remove PYPL", "Removing PYPL from your watchlist."),
        ("buy 0.5 NVDA", "Placing a buy order for 0.5 NVDA."),
        ("buy 1.2500 NVDA", "Placing a buy order for 1.25 NVDA."),
    ],
)
def test_reply_phrases(message, text):
    assert run(message)["message"] == text


def test_keywords_are_case_insensitive():
    out = run("BUY 1 AAPL, Sell 2 MSFT, ADD PYPL, Remove V")
    assert [(t["side"], t["ticker"]) for t in out["trades"]] == [("buy", "AAPL"), ("sell", "MSFT")]
    assert [(c["action"], c["ticker"]) for c in out["watchlist_changes"]] == [("add", "PYPL"), ("remove", "V")]


@pytest.mark.parametrize(
    "message",
    [
        "buy 5 aapl",  # tickers must be uppercase
        "add pypl",
        "buy AAPL",  # no quantity
        "buy -5 AAPL",
        "address PYPL",  # keyword must be a whole word
        "rebuy 5 AAPL",
        "add TOOLONG",  # more than 5 letters
        "buy 5 AAPL1",
    ],
)
def test_non_matches_fall_back(message):
    assert run(message)["message"] == FALLBACK_MESSAGE


def test_every_match_applies_watchlist_first_then_trades_in_message_order():
    out = run("Buy 5 AAPL, add PYPL, sell 2 TSLA, then remove NFLX and add BRK.B.")
    assert out["watchlist_changes"] == [
        {"ticker": "PYPL", "action": "add"},
        {"ticker": "NFLX", "action": "remove"},
        {"ticker": "BRK.B", "action": "add"},
    ]
    assert out["trades"] == [
        {"ticker": "AAPL", "side": "buy", "quantity": 5.0},
        {"ticker": "TSLA", "side": "sell", "quantity": 2.0},
    ]
    assert out["message"] == (
        "Adding PYPL to your watchlist. Removing NFLX from your watchlist. Adding BRK.B to your watchlist. "
        "Placing a buy order for 5 AAPL. Placing a sell order for 2 TSLA."
    )


def test_trailing_punctuation_is_not_part_of_the_ticker():
    assert run("add PYPL.")["watchlist_changes"] == [{"ticker": "PYPL", "action": "add"}]
    assert run("buy 3 MSFT!")["trades"] == [{"ticker": "MSFT", "side": "buy", "quantity": 3.0}]


@pytest.mark.parametrize("message", ["hello", "buy 5 AAPL and add PYPL", "remove V"])
def test_mock_output_is_a_valid_reply(message):
    parse_reply(mock_reply(message))
