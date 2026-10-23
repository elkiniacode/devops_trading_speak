"""Periodic portfolio snapshots (R21) and price marks for restarts (R14)."""

from __future__ import annotations

import asyncio
import logging

from app import db
from app.context import AppContext

from .portfolio import total_value

logger = logging.getLogger(__name__)

SNAPSHOT_INTERVAL = 30.0  # seconds


async def snapshot_loop(ctx: AppContext, interval: float = SNAPSHOT_INTERVAL) -> None:
    """Every ``interval`` seconds: record the portfolio value and persist the cached prices."""
    while True:
        await asyncio.sleep(interval)
        try:
            db.record_snapshot(total_value(ctx))
            save_price_marks(ctx)
        except Exception:  # keep the loop alive; the next round tries again
            logger.exception("Periodic portfolio snapshot failed")


def save_price_marks(ctx: AppContext) -> None:
    """Persist every cached price so the simulator resumes from it after a restart."""
    db.save_price_marks({ticker: update.price for ticker, update in ctx.cache.get_all().items()})
