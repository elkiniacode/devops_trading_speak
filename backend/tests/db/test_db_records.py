import time

from app import db


def freeze_clock(monkeypatch, ts=1_800_000_000.0):
    """Give every new row the same timestamp, so ordering has to fall back to insertion order."""
    monkeypatch.setattr(time, "time", lambda: ts)


# ---------------------------------------------------------------- watchlist


def test_watchlist_add_and_remove_are_idempotent():
    assert db.add_watchlist_ticker("PYPL") is True
    assert db.add_watchlist_ticker("PYPL") is False
    assert db.add_watchlist_ticker("AAPL") is False  # seeded
    watchlist = db.get_watchlist()
    assert watchlist[-1]["ticker"] == "PYPL" and len(watchlist) == 11
    assert set(watchlist[-1]) == {"ticker", "added_at"}

    assert db.remove_watchlist_ticker("PYPL") is True
    assert db.remove_watchlist_ticker("PYPL") is False
    assert "PYPL" not in [w["ticker"] for w in db.get_watchlist()]


def test_tracked_tickers_is_sorted_union_of_watchlist_and_positions():
    for ticker in [w["ticker"] for w in db.get_watchlist()]:
        db.remove_watchlist_ticker(ticker)
    assert db.tracked_tickers() == []
    db.add_watchlist_ticker("MSFT")
    db.add_watchlist_ticker("AAPL")
    db.apply_trade("AAPL", "buy", 1, 100.0)  # held and watched: listed once
    db.apply_trade("PYPL", "buy", 1, 50.0)  # held only
    assert db.tracked_tickers() == ["AAPL", "MSFT", "PYPL"]
    db.remove_watchlist_ticker("AAPL")
    assert db.tracked_tickers() == ["AAPL", "MSFT", "PYPL"]  # still held


# ---------------------------------------------------------------- snapshots


def test_snapshots_are_rounded_and_returned_oldest_first():
    snapshot = db.record_snapshot(10_123.456)
    assert snapshot["total_value"] == 10_123.46 and snapshot["recorded_at"].endswith("Z")
    db.record_snapshot(9_000.0)
    assert [s["total_value"] for s in db.get_snapshots()] == [10_000.0, 10_123.46, 9_000.0]
    assert set(db.get_snapshots()[-1]) == {"total_value", "recorded_at"}


def test_snapshot_limit_keeps_the_most_recent(monkeypatch):
    freeze_clock(monkeypatch)
    for value in range(1, 6):
        db.record_snapshot(float(value))
    assert [s["total_value"] for s in db.get_snapshots(limit=3)] == [3.0, 4.0, 5.0]


# ---------------------------------------------------------------- chat


def test_chat_messages_round_trip_actions():
    actions = {
        "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "ok", "error": None}],
        "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5.0, "status": "failed", "price": None,
                    "error": "Insufficient cash"}],
    }
    user = db.add_chat_message("user", "Buy 5 AAPL and add PYPL", None)
    assistant = db.add_chat_message("assistant", "Placing a buy order for 5 AAPL.", actions)
    assert set(assistant) == {"id", "role", "content", "actions", "created_at"}
    assert db.get_chat_messages() == [user, assistant]
    assert db.get_chat_messages()[0]["actions"] is None
    assert db.get_chat_messages()[1]["actions"] == actions


def test_chat_limit_returns_most_recent_oldest_first(monkeypatch):
    freeze_clock(monkeypatch)  # a mock reply can land in the same millisecond as the question
    for i in range(6):
        db.add_chat_message("user" if i % 2 == 0 else "assistant", f"m{i}", None if i % 2 == 0 else {"trades": []})
    assert [m["content"] for m in db.get_chat_messages(limit=4)] == ["m2", "m3", "m4", "m5"]
    assert [m["content"] for m in db.get_chat_messages()] == [f"m{i}" for i in range(6)]


# ---------------------------------------------------------------- price marks


def test_price_marks_upsert():
    db.save_price_marks({"AAPL": 190.5, "MSFT": 410.0})
    db.save_price_marks({"AAPL": 191.25, "PYPL": 61.0})
    db.save_price_marks({})
    assert db.load_price_marks() == {"AAPL": 191.25, "MSFT": 410.0, "PYPL": 61.0}
