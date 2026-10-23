import asyncio
import re

import pytest

from app import db
from app.db import InsufficientCashError, InsufficientSharesError, TradeRejected
from app.market import UnknownTickerError
from app.services.trading import execute_trade
from app.services.watchlist import remove_from_watchlist


async def test_buy_fills_at_the_cached_price_and_records_a_snapshot(ctx):
    trade = await execute_trade(ctx, " aapl ", "BUY", 10)
    assert set(trade) == {"id", "ticker", "side", "quantity", "price", "total", "executed_at"}
    assert (trade["ticker"], trade["side"], trade["quantity"], trade["price"], trade["total"]) == (
        "AAPL",
        "buy",
        10.0,
        100.0,
        1000.0,
    )
    assert db.get_cash() == 9000.0
    assert db.get_position("AAPL")["quantity"] == 10.0
    assert [s["total_value"] for s in db.get_snapshots()] == [10000.0, 10000.0]  # seed + post-trade


async def test_average_cost_is_weighted_on_buys_and_unchanged_on_sells(ctx):
    await execute_trade(ctx, "AAPL", "buy", 10)  # @ 100
    ctx.cache.update("AAPL", 110.0)
    await execute_trade(ctx, "AAPL", "buy", 10)  # @ 110
    assert db.get_position("AAPL")["avg_cost"] == pytest.approx(105.0)

    await execute_trade(ctx, "AAPL", "sell", 5)  # @ 110
    position = db.get_position("AAPL")
    assert position["quantity"] == 15.0
    assert position["avg_cost"] == pytest.approx(105.0)
    assert db.get_cash() == 10000 - 1000 - 1100 + 550


async def test_selling_everything_closes_the_position(ctx):
    await execute_trade(ctx, "AAPL", "buy", 2.5)
    ctx.cache.update("AAPL", 90.0)
    trade = await execute_trade(ctx, "AAPL", "sell", 2.5)  # a sale at a loss
    assert trade["total"] == 225.0
    assert db.get_position("AAPL") is None
    assert db.get_cash() == 10000 - 250 + 225


async def test_fractional_quantities(ctx):
    trade = await execute_trade(ctx, "AAPL", "buy", 0.1234)
    assert (trade["quantity"], trade["total"]) == (0.1234, 12.34)
    trade = await execute_trade(ctx, "AAPL", "buy", 0.1 + 0.2)  # float noise is not a 5th decimal
    assert trade["quantity"] == 0.3


@pytest.mark.parametrize(
    ("ticker", "side", "quantity", "message"),
    [
        ("A$", "buy", 1, "Invalid ticker symbol: 'A$'"),
        (None, "buy", 1, "Invalid ticker symbol: None"),
        ("AAPL", "hold", 1, "Side must be 'buy' or 'sell'"),
        ("AAPL", "buy", 0, "Quantity must be greater than 0"),
        ("AAPL", "sell", -3, "Quantity must be greater than 0"),
        ("AAPL", "buy", 0.12345, "Quantity can have at most 4 decimal places"),
        ("AAPL", "buy", float("nan"), "Quantity must be a number"),
        ("AAPL", "buy", "10", "Quantity must be a number"),
        ("AAPL", "buy", 2_000_000, "Quantity can be at most 1,000,000"),
        ("PENY", "buy", 0.0001, "Order value must be at least $0.01"),
        ("ZZZZ", "buy", 1, "No current price for ZZZZ; try again shortly"),
        ("XYZQ", "buy", 1, "Unknown ticker: XYZQ"),
    ],
)
async def test_rejected_trades_change_nothing(ctx, ticker, side, quantity, message):
    with pytest.raises(ValueError, match=re.escape(message)):
        await execute_trade(ctx, ticker, side, quantity)
    assert db.get_cash() == 10000.0
    assert db.get_positions() == []
    assert len(db.get_snapshots()) == 1


async def test_insufficient_cash(ctx):
    with pytest.raises(InsufficientCashError, match=r"^Insufficient cash"):
        await execute_trade(ctx, "AAPL", "buy", 100.01)


async def test_overselling_is_rejected_not_clamped(ctx):
    await execute_trade(ctx, "AAPL", "buy", 2)
    with pytest.raises(InsufficientSharesError, match=r"^Insufficient shares"):
        await execute_trade(ctx, "AAPL", "sell", 5)
    assert db.get_position("AAPL")["quantity"] == 2.0


async def test_stale_price_is_rejected(ctx):
    ctx.market.quote_age = -1
    with pytest.raises(TradeRejected, match=re.escape("No current price for AAPL; try again shortly")):
        await execute_trade(ctx, "AAPL", "buy", 1)


async def test_unknown_ticker_is_never_tracked(ctx):
    with pytest.raises(UnknownTickerError):
        await execute_trade(ctx, "xyzq", "buy", 1)
    assert "XYZQ" not in ctx.market.get_tickers()


async def test_rejected_trade_untracks_a_symbol_that_is_neither_watched_nor_held(ctx):
    with pytest.raises(TradeRejected):
        await execute_trade(ctx, "ZZZZ", "buy", 1)
    assert "ZZZZ" not in ctx.market.get_tickers()


async def test_trading_off_the_watchlist_tracks_until_closed(ctx):
    await execute_trade(ctx, "PYPL", "buy", 4)
    assert "PYPL" in ctx.market.get_tickers() and "PYPL" in ctx.cache
    await execute_trade(ctx, "PYPL", "sell", 1)
    assert "PYPL" in ctx.market.get_tickers()
    await execute_trade(ctx, "PYPL", "sell", 3)
    assert "PYPL" not in ctx.market.get_tickers() and "PYPL" not in ctx.cache


async def test_closing_a_watched_position_keeps_it_tracked(ctx):
    await execute_trade(ctx, "AAPL", "buy", 1)
    await execute_trade(ctx, "AAPL", "sell", 1)
    assert "AAPL" in ctx.market.get_tickers()


async def test_held_ticker_removed_from_watchlist_is_untracked_once_sold(ctx):
    await execute_trade(ctx, "AAPL", "buy", 1)
    await remove_from_watchlist(ctx, "AAPL")
    assert "AAPL" in ctx.market.get_tickers()
    await execute_trade(ctx, "AAPL", "sell", 1)
    assert "AAPL" not in ctx.market.get_tickers()


async def test_fills_happen_under_the_trade_lock(ctx, monkeypatch):
    apply_trade = db.apply_trade
    locked = []

    def spy(*args):
        locked.append(ctx.trade_lock.locked())
        return apply_trade(*args)

    monkeypatch.setattr(db, "apply_trade", spy)
    await execute_trade(ctx, "AAPL", "buy", 1)
    assert locked == [True]


async def test_concurrent_buys_cannot_overspend(ctx):
    results = await asyncio.gather(
        execute_trade(ctx, "AAPL", "buy", 60), execute_trade(ctx, "AAPL", "buy", 60), return_exceptions=True
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, InsufficientCashError) for r in results) == 1
    assert db.get_cash() == 4000.0
