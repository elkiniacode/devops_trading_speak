"""Shared runtime state handed to routes and services (CONTRACTS.md §3.1)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from fastapi import Request

from app.market import MarketDataSource, PriceCache


@dataclass
class AppContext:
    cache: PriceCache
    market: MarketDataSource
    # Serializes trades and watchlist changes (R20). The service functions take it
    # themselves; callers such as the LLM must NOT hold it when calling them.
    trade_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    account_version: int = 0
    account_version: int = 0


def get_ctx(request: Request) -> AppContext:
    """FastAPI dependency: the AppContext the lifespan stored on ``app.state.ctx``."""
    return request.app.state.ctx
