from concurrent.futures import ThreadPoolExecutor

import pytest

from app import db
from app.db import InsufficientCashError, InsufficientSharesError, TradeRejected


def state():
    """Everything a rejected trade must leave untouched."""
    return db.get_cash(), db.get_positions(), db.get_trades()


def test_error_hierarchy():
    assert issubclass(InsufficientCashError, TradeRejected)
    assert issubclass(InsufficientSharesError, TradeRejected)
    assert issubclass(TradeRejected, ValueError)


def test_buy_creates_position_and_spends_cash():
    trade = db.apply_trade("AAPL", "buy", 10, 190.12)
    assert set(trade) == {"id", "ticker", "side", "quantity", "price", "total", "executed_at"}
    assert (trade["ticker"], trade["side"], trade["quantity"], trade["price"], trade["total"]) == (
        "AAPL", "buy", 10.0, 190.12, 1901.2,
    )
    assert trade["executed_at"].endswith("Z")
    assert db.get_cash() == 8098.8
    pos = db.get_position("AAPL")
    assert (pos["quantity"], pos["avg_cost"]) == (10.0, 190.12)
    assert db.get_trades() == [trade]


def test_buys_use_weighted_average_cost():
    db.apply_trade("AAPL", "buy", 10, 100.0)
    db.apply_trade("AAPL", "buy", 30, 120.0)
    pos = db.get_position("AAPL")
    assert pos["quantity"] == 40.0
    assert pos["avg_cost"] == pytest.approx(115.0)
    assert db.get_cash() == 10_000 - 1000 - 3600


def test_partial_sell_keeps_avg_cost():
    db.apply_trade("AAPL", "buy", 10, 100.0)
    trade = db.apply_trade("AAPL", "sell", 4, 90.0)  # selling at a loss
    assert trade["total"] == 360.0
    pos = db.get_position("AAPL")
    assert (pos["quantity"], pos["avg_cost"]) == (6.0, 100.0)
    assert db.get_cash() == 10_000 - 1000 + 360


def test_full_sell_deletes_position():
    db.apply_trade("PYPL", "buy", 5, 60.0)
    assert "PYPL" in db.tracked_tickers()
    db.apply_trade("PYPL", "sell", 5, 61.0)
    assert db.get_position("PYPL") is None
    assert db.get_positions() == []
    assert "PYPL" not in db.tracked_tickers()
    assert db.get_cash() == 10_005.0
    assert [t["side"] for t in db.get_trades()] == ["sell", "buy"]  # newest first


def test_oversell_is_rejected_and_writes_nothing():
    db.apply_trade("AAPL", "buy", 2, 190.0)
    before = state()
    with pytest.raises(InsufficientSharesError, match=r"^Insufficient shares: you have 2 AAPL, tried to sell 5$"):
        db.apply_trade("AAPL", "sell", 5, 190.0)
    assert state() == before


def test_selling_without_a_position_is_rejected():
    with pytest.raises(InsufficientSharesError, match=r"you have 0 TSLA, tried to sell 0\.5$"):
        db.apply_trade("TSLA", "sell", 0.5, 250.0)
    assert db.get_trades() == []


def test_insufficient_cash_is_rejected_and_writes_nothing():
    db.apply_trade("AAPL", "buy", 50, 190.0)  # leaves $500.00
    before = state()
    with pytest.raises(InsufficientCashError, match=r"^Insufficient cash: need \$1,901\.20, have \$500\.00$"):
        db.apply_trade("AAPL", "buy", 10, 190.12)
    assert state() == before


def test_spending_exactly_all_cash_is_allowed():
    db.apply_trade("NVDA", "buy", 50, 200.0)
    assert db.get_cash() == 0.0


def test_fractional_quantities():
    trade = db.apply_trade("AAPL", "buy", 0.5, 190.12)
    assert (trade["quantity"], trade["total"]) == (0.5, 95.06)
    assert db.get_cash() == 9904.94

    trade = db.apply_trade("MSFT", "buy", 1.23456, 100.0)  # rounded to 4 dp
    assert trade["quantity"] == 1.2346
    assert db.get_position("MSFT")["quantity"] == 1.2346

    db.apply_trade("MSFT", "sell", 1.2345, 100.0)  # leaves 0.0001, above the dust threshold
    assert db.get_position("MSFT")["quantity"] == pytest.approx(0.0001)
    db.apply_trade("MSFT", "sell", 0.0001, 100.0)
    assert db.get_position("MSFT") is None


def test_cash_is_rounded_to_cents():
    trade = db.apply_trade("AAPL", "buy", 3, 33.333)  # 99.999 -> $100.00
    assert trade["total"] == 100.0
    assert db.get_cash() == 9_900.0
    db.apply_trade("AAPL", "buy", 0.1, 0.3)  # 0.03
    assert db.get_cash() == 9_899.97


def test_tiny_order_is_rejected():
    with pytest.raises(TradeRejected, match=r"^Order value must be at least \$0\.01$"):
        db.apply_trade("AAPL", "buy", 0.0001, 10.0)  # $0.001
    assert db.get_trades() == []


@pytest.mark.parametrize(
    "side, quantity, message",
    [("hold", 1, "Side must be 'buy' or 'sell'"), ("buy", 0, "greater than 0"), ("sell", -1, "greater than 0"),
     ("buy", 0.00001, "greater than 0")],
)
def test_invalid_orders_are_rejected(side, quantity, message):
    with pytest.raises(TradeRejected, match=message):
        db.apply_trade("AAPL", side, quantity, 190.0)
    assert db.get_trades() == []


def test_concurrent_trades_from_threads_are_serialized():
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: db.apply_trade("AAPL", "buy", 1, 10.0), range(100)))
    assert db.get_cash() == 9_000.0
    assert db.get_position("AAPL")["quantity"] == 100.0
    assert len(db.get_trades(limit=1000)) == 100


def test_get_trades_limit_newest_first():
    for qty in (1, 2, 3):
        db.apply_trade("AAPL", "buy", qty, 10.0)
    trades = db.get_trades(limit=2)
    assert [t["quantity"] for t in trades] == [3.0, 2.0]
    assert trades[0]["total"] == 30.0
