"""Market orders, for the trade bar and the LLM alike."""

from __future__ import annotations

import logging
import math

from app import db
from app.context import AppContext
from app.db import TradeRejected

from .portfolio import total_value
from .tracking import parse_ticker, track, untrack_if_unused

logger = logging.getLogger(__name__)

MAX_QUANTITY = 1_000_000
QTY_DP = 4  # fractional shares, at most 4 decimal places (R19)


def parse_side(side: object) -> str:
    value = side.strip().lower() if isinstance(side, str) else None
    if value not in ("buy", "sell"):
        raise TradeRejected("Side must be 'buy' or 'sell'")
    return value


def parse_quantity(quantity: object) -> float:
    if isinstance(quantity, bool) or not isinstance(quantity, (int, float)) or not math.isfinite(quantity):
        raise TradeRejected("Quantity must be a number")
    if quantity <= 0:
        raise TradeRejected("Quantity must be greater than 0")
    if quantity > MAX_QUANTITY:
        raise TradeRejected(f"Quantity can be at most {MAX_QUANTITY:,}")
    rounded = round(float(quantity), QTY_DP)
    if abs(quantity - rounded) > 1e-9:  # slack absorbs float noise such as 0.1 + 0.2
        raise TradeRejected(f"Quantity can have at most {QTY_DP} decimal places")
    return rounded


async def execute_trade(ctx: AppContext, ticker: str, side: str, quantity: float) -> dict:
    """Fill a market order at the current price and return the trade object (CONTRACTS.md §5.4).

    Raises ValueError subclasses with user-facing messages: invalid ticker, side or quantity,
    UnknownTickerError, no fresh price, insufficient cash or shares, order value under $0.01.
    """
    ticker = parse_ticker(ticker)
    side = parse_side(side)
    quantity = parse_quantity(quantity)
    async with ctx.trade_lock:
        await track(ctx, ticker)  # a symbol typed in the trade bar may not be tracked yet
        try:
            quote = ctx.cache.get_fresh(ticker, ctx.market.max_quote_age)
            if quote is None:
                raise TradeRejected(f"No current price for {ticker}; try again shortly")
            trade = db.apply_trade(ticker, side, quantity, quote.price)
            try:
                db.record_snapshot(total_value(ctx))
            except Exception:  # the trade is committed; a missed snapshot is not worth failing it
                logger.exception("Snapshot after trade %s failed", trade["id"])
        finally:
            await untrack_if_unused(ctx, ticker)  # closed out, or rejected before it was held
    return trade
