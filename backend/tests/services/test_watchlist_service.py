import pytest

from app import db
from app.market import UnknownTickerError
from app.services.trading import execute_trade
from app.services.watchlist import add_to_watchlist, remove_from_watchlist, watchlist_view

DEFAULTS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]


def watched() -> list[str]:
    return [row["ticker"] for row in db.get_watchlist()]


async def test_view_lists_seeded_tickers_with_quotes(ctx):
    rows = watchlist_view(ctx)
    assert [r["ticker"] for r in rows] == DEFAULTS
    assert set(rows[0]) == {"ticker", "added_at", "quote"}
    assert rows[0]["quote"] == ctx.cache.get("AAPL").to_dict()


async def test_add_normalizes_tracks_and_is_idempotent(ctx):
    assert await add_to_watchlist(ctx, " pypl ") == "PYPL"
    assert await add_to_watchlist(ctx, "PYPL") == "PYPL"
    assert watched() == [*DEFAULTS, "PYPL"]
    assert "PYPL" in ctx.market.get_tickers()
    assert watchlist_view(ctx)[-1]["quote"]["price"] == 50.0


async def test_add_rejects_malformed_and_unknown_symbols(ctx):
    with pytest.raises(ValueError, match="Invalid ticker symbol: 'TOOLONG'"):
        await add_to_watchlist(ctx, "TOOLONG")
    with pytest.raises(UnknownTickerError, match="^Unknown ticker: XYZQ$"):
        await add_to_watchlist(ctx, "xyzq")
    assert watched() == DEFAULTS
    assert "XYZQ" not in ctx.market.get_tickers()


async def test_unpriced_ticker_has_a_null_quote(ctx):
    await add_to_watchlist(ctx, "ZZZZ")
    assert watchlist_view(ctx)[-1] == {"ticker": "ZZZZ", "added_at": db.get_watchlist()[-1]["added_at"], "quote": None}


async def test_remove_untracks_and_is_idempotent(ctx):
    assert await remove_from_watchlist(ctx, "msft") == "MSFT"
    assert await remove_from_watchlist(ctx, "MSFT") == "MSFT"
    assert "MSFT" not in watched()
    assert "MSFT" not in ctx.market.get_tickers() and "MSFT" not in ctx.cache


async def test_removing_a_held_ticker_keeps_it_priced(ctx):
    await execute_trade(ctx, "NVDA", "buy", 3)
    await remove_from_watchlist(ctx, "NVDA")
    assert "NVDA" not in watched()
    assert "NVDA" in ctx.market.get_tickers() and "NVDA" in ctx.cache


async def test_remove_rejects_malformed_symbols(ctx):
    with pytest.raises(ValueError, match="Invalid ticker symbol"):
        await remove_from_watchlist(ctx, "A1")
