"""The FastAPI app: startup/shutdown wiring, API routers and the static frontend.

Run with a single worker (R20): ``uv run uvicorn app.main:app --port 8001``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings, llm_mode  # loads <repo>/.env before the market factory runs

from app import db
from app.api import charla_auth, charla_room, chat, health, portfolio, watchlist, workstation
from app.charla import classify, room
from app.charla.email import outbox
from app.context import AppContext
from app.llm import client as llm_client
from app.market import MarketDataSource, PriceCache, create_market_data_source
from app.market.stream import router as stream_router
from app.services.snapshots import save_price_marks, snapshot_loop

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
logger = logging.getLogger(__name__)

MarketFactory = Callable[..., MarketDataSource]  # (cache, *, initial_prices) -> source


def create_app(
    settings: Settings | None = None, *, market_factory: MarketFactory = create_market_data_source
) -> FastAPI:
    """Build the app. Tests pass their own settings and a stub ``market_factory``."""
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db.init_db(settings.db_path)
        cache = PriceCache()
        market = market_factory(cache, initial_prices=db.load_price_marks())
        tracked = set(db.tracked_tickers()) | {order["ticker"] for order in db.get_orders()}
        await market.start(sorted(tracked))  # watchlist, holdings, and pending orders survive restarts
        ctx = AppContext(cache=cache, market=market, trade_lock=asyncio.Lock())
        app.state.ctx = ctx
        room.startup()  # an open question whose deadline passed while we were down becomes closed
        tasks = [
            asyncio.create_task(snapshot_loop(ctx), name="portfolio-snapshots"),
            asyncio.create_task(workstation.order_monitor(ctx), name="trading-order-monitor"),
            asyncio.create_task(room.tick_loop(), name="charla-tick"),
            asyncio.create_task(outbox.run(), name="charla-email"),
            asyncio.create_task(_reclassify_on_start(), name="charla-reclassify"),
        ]
        if llm_mode() == "openrouter":  # litellm takes seconds to import; don't make the first chat wait
            tasks.append(asyncio.create_task(_preload_llm(), name="litellm-preload"))
        logger.info(
            "FinAlly started: db=%s market=%s llm=%s charla_only=%s",
            settings.db_path, market.mode, llm_mode(), settings.charla_only,
        )
        try:
            yield
        finally:
            try:
                save_price_marks(ctx)
            except Exception:
                logger.exception("Could not save price marks on shutdown")
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await market.stop()
            db.close_db()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.state.settings = settings

    if settings.cors_origins:  # development only: next dev on :3000 calling the API (R32)
        app.add_middleware(
            CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"]
        )

    app.include_router(health.router)
    app.include_router(charla_auth.router)
    app.include_router(charla_room.router)
    if settings.charla_only:  # public talk deploy: no trading, no chat (planning/charla/CONTRACT.md §0)

        @app.get("/", include_in_schema=False)
        async def charla_home() -> RedirectResponse:
            return RedirectResponse("/charla/")

    else:
        app.include_router(watchlist.router)
        app.include_router(portfolio.router)
        app.include_router(stream_router)
        app.include_router(chat.router)
        app.include_router(workstation.router)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
    def api_not_found(path: str) -> None:
        """Unknown /api routes get a JSON 404 instead of falling through to the static files."""
        raise HTTPException(404, "Not Found")

    # Mounted last, so it never shadows /api/* (PLAN §13.10).
    if settings.static_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="static")
    else:
        logger.info("No frontend build at %s; serving the API only", settings.static_dir)

    return app


async def _reclassify_on_start() -> None:
    """Open answers left without a theme by a restart get one now."""
    try:
        await classify.reclassify_pending()
    except Exception:
        logger.exception("Reclassifying open answers failed")


async def _preload_llm() -> None:
    try:
        await llm_client.preload()
    except Exception:  # the first chat retries the import and reports its own error
        logger.exception("Preloading litellm failed")


app = create_app()
