"""Adding and removing watchlist tickers, and the watchlist as the API returns it."""

from __future__ import annotations

from app import db
from app.context import AppContext

from .tracking import parse_ticker, track, untrack_if_unused


async def add_to_watchlist(ctx: AppContext, ticker: str) -> str:
    """Track and store ``ticker``; idempotent. Returns the normalized ticker.

    The source prices the symbol before the row is written, so unknown symbols never
    reach the database (ValueError / UnknownTickerError).
    """
    ticker = parse_ticker(ticker)
    async with ctx.trade_lock:
        await track(ctx, ticker)
        db.add_watchlist_ticker(ticker)
    return ticker


async def remove_from_watchlist(ctx: AppContext, ticker: str) -> str:
    """Remove ``ticker``; idempotent. It keeps streaming while a position is open."""
    ticker = parse_ticker(ticker)
    async with ctx.trade_lock:
        db.remove_watchlist_ticker(ticker)
        await untrack_if_unused(ctx, ticker)
    return ticker


def watchlist_view(ctx: AppContext) -> list[dict]:
    """Watchlist rows with their latest quote, or ``quote: None`` if not priced yet."""
    rows = []
    for row in db.get_watchlist():
        quote = ctx.cache.get(row["ticker"])
        rows.append({"ticker": row["ticker"], "added_at": row["added_at"], "quote": quote.to_dict() if quote else None})
    return rows
