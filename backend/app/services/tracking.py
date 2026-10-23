"""Keeps the market source's tickers equal to watchlist ∪ open positions (R9)."""

from __future__ import annotations

from app import db
from app.context import AppContext
from app.market import UnknownTickerError, normalize_ticker


def parse_ticker(raw: object) -> str:
    """Uppercase and validate a symbol. Raises ValueError('Invalid ticker symbol: ...')."""
    if not isinstance(raw, str):
        raise ValueError(f"Invalid ticker symbol: {raw!r}")
    return normalize_ticker(raw)


async def track(ctx: AppContext, ticker: str) -> None:
    """Start pricing ``ticker``; its price is cached on return if the source has one.

    Raises UnknownTickerError('Unknown ticker: T') when the source knows the symbol doesn't exist.
    """
    try:
        await ctx.market.add_ticker(ticker)
    except UnknownTickerError:
        raise UnknownTickerError(f"Unknown ticker: {ticker}") from None


async def untrack_if_unused(ctx: AppContext, ticker: str) -> None:
    """Stop pricing ``ticker`` unless it is on the watchlist or held."""
    if db.get_position(ticker) is None and all(row["ticker"] != ticker for row in db.get_watchlist()):
        await ctx.market.remove_ticker(ticker)
