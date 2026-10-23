import sqlite3

import pytest

from app import db
from app.db.schema import SCHEMA_VERSION

DEFAULT_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
TABLES = {"users_profile", "watchlist", "positions", "trades", "portfolio_snapshots", "chat_messages", "price_marks", "pending_orders", "market_order_requests", "position_risk", "activity_events"}


def test_fresh_db_has_schema_and_settings(db_file):
    assert db_file.exists()  # parent directory was created
    conn = sqlite3.connect(db_file)
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert TABLES <= tables
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        conn.close()


def test_fresh_db_is_seeded():
    assert db.get_cash() == 10_000.0
    assert [w["ticker"] for w in db.get_watchlist()] == DEFAULT_TICKERS  # seed order is kept
    assert db.get_positions() == []
    assert db.get_trades() == []
    assert db.get_chat_messages() == []
    assert db.load_price_marks() == {}
    snapshots = db.get_snapshots()
    assert len(snapshots) == 1 and snapshots[0]["total_value"] == 10_000.0
    assert snapshots[0]["recorded_at"].endswith("Z")


def test_reinit_never_reseeds(db_file):
    db.apply_trade("AAPL", "buy", 10, 190.0)
    db.remove_watchlist_ticker("NFLX")
    db.add_watchlist_ticker("PYPL")
    db.init_db(db_file)
    db.init_db(db_file)
    assert db.get_cash() == 8_100.0
    tickers = [w["ticker"] for w in db.get_watchlist()]
    assert "NFLX" not in tickers and "PYPL" in tickers
    assert len(db.get_snapshots()) == 1
    assert db.get_position("AAPL")["quantity"] == 10.0


def test_calls_after_close_fail():
    db.close_db()
    with pytest.raises(RuntimeError, match="init_db"):
        db.get_cash()


def test_v2_migration_preserves_account_and_pending_orders(db_file):
    db.apply_trade("AAPL", "buy", 2, 100.0)
    db.close_db()
    conn = sqlite3.connect(db_file)
    try:
        conn.execute("DROP TABLE pending_orders")
        conn.execute("""CREATE TABLE pending_orders (
          id TEXT PRIMARY KEY, user_id TEXT NOT NULL, client_order_id TEXT NOT NULL,
          ticker TEXT NOT NULL, side TEXT NOT NULL, type TEXT NOT NULL,
          notional REAL NOT NULL, trigger_price REAL NOT NULL, stop_loss REAL,
          take_profit REAL, status TEXT NOT NULL, reason TEXT, created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL, UNIQUE(user_id,client_order_id))""")
        conn.execute("""INSERT INTO pending_orders
          (id,user_id,client_order_id,ticker,side,type,notional,trigger_price,status,created_at,updated_at)
          VALUES ('old','default','old-client','AAPL','buy','limit',100,90,'pending','2026-01-01','2026-01-01')""")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    finally:
        conn.close()
    db.init_db(db_file)
    assert db.get_cash() == 9800.0
    assert db.get_position("AAPL")["quantity"] == 2
    assert db.get_order("old")["trade_id"] is None
    assert db.get_order("old")["status"] == "pending"
    assert db.get_market_request("old-client") is None


def test_order_fill_and_retry_are_one_transaction():
    request = db.create_market_request("market-retry", "AAPL", "buy", 100)
    first = db.complete_market_request(request["id"], 1, 100, 90, 120)
    second = db.complete_market_request(request["id"], 1, 999, None, None)
    assert first == second
    assert db.get_cash() == 9900.0
    assert db.get_risk("AAPL")[0]["stop_loss"] == 90

    pending = db.create_order({"client_order_id": "limit-retry", "ticker": "AAPL", "side": "buy",
                               "type": "limit", "notional": 100, "trigger_price": 90})
    filled = db.complete_pending_order(pending["id"], 80)
    repeated = db.complete_pending_order(pending["id"], 70)
    assert filled == repeated
    assert len(db.get_trades()) == 2
    assert db.get_order(pending["id"])["trade_id"] == filled["id"]


def test_rejected_fill_rolls_back_order_and_account():
    pending = db.create_order({"client_order_id": "too-large", "ticker": "AAPL", "side": "buy",
                               "type": "limit", "notional": 20000, "trigger_price": 90})
    with pytest.raises(ValueError):
        db.complete_pending_order(pending["id"], 90)
    assert db.get_cash() == 10000.0
    assert db.get_order(pending["id"])["status"] == "pending"
    assert db.get_trades() == []
