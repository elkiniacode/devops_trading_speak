"""GET /api/stream/prices: Server-Sent Events fed from the PriceCache."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

router = APIRouter()

PUSH_INTERVAL = 0.5  # seconds between cache checks
HEARTBEAT_INTERVAL = 15.0  # comment line so proxies don't close an idle stream


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    cache: PriceCache = request.app.state.ctx.cache  # AppContext, set in main.py's lifespan
    return StreamingResponse(
        price_events(request, cache),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def price_events(request: Request, cache: PriceCache) -> AsyncIterator[str]:
    """One event per change, carrying every ticker. The first event goes out immediately."""
    yield "retry: 1000\n\n"  # EventSource reconnect delay, ms
    sent_version = -1
    last_write = time.monotonic()
    while not await request.is_disconnected():
        if cache.version != sent_version:
            sent_version = cache.version
            payload = {ticker: update.to_dict() for ticker, update in cache.get_all().items()}
            yield f"data: {json.dumps(payload)}\n\n"
            last_write = time.monotonic()
        elif time.monotonic() - last_write >= HEARTBEAT_INTERVAL:
            yield ": keepalive\n\n"
            last_write = time.monotonic()
        await asyncio.sleep(PUSH_INTERVAL)
