"""Chooses the market data source from the environment. The only module that reads env vars."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

from .cache import PriceCache
from .interface import MarketDataSource
from .massive_source import MassiveDataSource
from .simulator import GBMSimulator, SimulatorDataSource

logger = logging.getLogger(__name__)


def create_market_data_source(
    cache: PriceCache, *, initial_prices: Mapping[str, float] | None = None
) -> MarketDataSource:
    """Massive if MASSIVE_API_KEY is set and non-empty, otherwise the simulator.

    ``initial_prices`` (e.g. marks persisted at the last shutdown) let the simulator
    continue where it stopped instead of jumping back to its seed prices.
    """
    api_key = os.getenv("MASSIVE_API_KEY", "").strip()
    if api_key:
        poll_interval = float(os.getenv("MASSIVE_POLL_SECONDS", "15"))
        logger.info("Market data: Massive API, polling every %ss", poll_interval)
        return MassiveDataSource(cache, api_key=api_key, poll_interval=poll_interval)

    seed = os.getenv("SIM_SEED", "").strip()
    logger.info("Market data: simulator%s", f" (seed {seed})" if seed else "")
    return SimulatorDataSource(
        cache,
        simulator=GBMSimulator(seed=int(seed) if seed else None),
        initial_prices=initial_prices,
    )
