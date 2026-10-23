"""Portfolio valuation from cached prices (R17, R18).

Used by GET /api/portfolio, the snapshots and the LLM context, so they always agree.
"""

from __future__ import annotations

import time

from app import db
from app.context import AppContext
from app.market.models import iso_utc

STARTING_CASH = 10_000.0


def portfolio_view(ctx: AppContext) -> dict:
    """The GET /api/portfolio object (CONTRACTS.md §5.3).

    A position that has never been priced has null price and P&L fields, counts at its
    average cost in the totals, and makes ``valuation_complete`` false. A price older than
    the source's ``max_quote_age`` is still used, flagged ``stale``.
    """
    cash = db.get_cash()
    positions = []
    positions_value = 0.0
    for pos in db.get_positions():
        view, value = _position_view(ctx, pos)
        positions.append(view)
        positions_value += value
    # Sum the rounded per-position values so the totals add up to the cent.
    positions_value = round(positions_value, 2)
    total = round(cash + positions_value, 2)
    total_pnl = round(total - STARTING_CASH, 2)
    return {
        "cash_balance": round(cash, 2),
        "positions": positions,
        "positions_value": positions_value,
        "total_value": total,
        "total_pnl": total_pnl,
        "total_pnl_percent": round(total_pnl / STARTING_CASH * 100, 2),
        "valuation_complete": all(p["current_price"] is not None for p in positions),
        "as_of": iso_utc(time.time()),
    }


def total_value(ctx: AppContext) -> float:
    """Cash plus positions at cached prices (average cost where never priced)."""
    return portfolio_view(ctx)["total_value"]


def _position_view(ctx: AppContext, pos: dict) -> tuple[dict, float]:
    """(position object, value counted toward the totals)."""
    ticker, quantity, avg_cost = pos["ticker"], pos["quantity"], pos["avg_cost"]
    view = {"ticker": ticker, "quantity": round(quantity, 4), "avg_cost": round(avg_cost, 4)}
    quote = ctx.cache.get(ticker)
    if quote is None:
        view |= {
            "current_price": None,
            "market_value": None,
            "unrealized_pnl": None,
            "unrealized_pnl_percent": None,
            "stale": False,
        }
        return view, round(quantity * avg_cost, 2)
    price = quote.price
    market_value = round(quantity * price, 2)
    view |= {
        "current_price": price,  # unrounded, exactly what the SSE stream shows and trades fill at
        "market_value": market_value,
        "unrealized_pnl": round((price - avg_cost) * quantity, 2),
        "unrealized_pnl_percent": round((price - avg_cost) / avg_cost * 100, 2) if avg_cost else 0.0,
        "stale": ctx.cache.get_fresh(ticker, ctx.market.max_quote_age) is None,
    }
    return view, market_value
