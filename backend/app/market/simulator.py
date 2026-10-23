"""Simulated prices: correlated geometric Brownian motion with occasional jumps.

See planning/MARKET_SIMULATOR.md for the model and the reasoning behind the constants.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import random
import zlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)

# --- Tuning knobs (R15): each is a single constant -------------------------------

TICK_SECONDS = 0.5  # wall-clock time between price updates
TIME_SCALE = 20.0  # simulated trading seconds per wall-clock second: a 6.5h day passes in ~20 min
EVENT_PROBABILITY = 0.0008  # per ticker per tick: ~1 event a minute across 10 tickers
EVENT_SIZE = (0.02, 0.05)  # an event moves the price 2-5%, up or down
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600


@dataclass(frozen=True)
class TickerProfile:
    price: float  # seed price in dollars
    volatility: float  # annualized sigma, e.g. 0.25 = 25%
    sector: str | None = None  # key into SECTORS; None = market factor only
    drift: float = 0.05  # annualized mu


# How strongly each sector follows the market and its own sector factor. Each ticker's
# shock is market_w * M + sector_w * S + idio_w * e with idio_w = sqrt(1 - market_w^2 - sector_w^2),
# so its variance stays 1 and its volatility stays exactly `TickerProfile.volatility`.
SECTORS: dict[str, tuple[float, float]] = {
    "tech": (0.55, 0.55),  # same-sector correlation ~0.60
    "consumer": (0.50, 0.45),  # ~0.45
    "finance": (0.50, 0.60),  # ~0.61
}
MARKET_ONLY_WEIGHT = 0.50  # tickers without a sector: correlation ~0.25 with everything

# Seed prices are illustrative; only their rough size matters.
PROFILES: dict[str, TickerProfile] = {
    "AAPL": TickerProfile(190.00, 0.25, "tech"),
    "GOOGL": TickerProfile(175.00, 0.28, "tech"),
    "MSFT": TickerProfile(420.00, 0.24, "tech"),
    "AMZN": TickerProfile(185.00, 0.30, "consumer"),
    "TSLA": TickerProfile(250.00, 0.55, "consumer"),
    "NVDA": TickerProfile(130.00, 0.50, "tech"),
    "META": TickerProfile(560.00, 0.35, "tech"),
    "JPM": TickerProfile(205.00, 0.22, "finance"),
    "V": TickerProfile(280.00, 0.20, "finance"),
    "NFLX": TickerProfile(700.00, 0.38, "consumer"),
    # Common extras so "add AMD" looks realistic.
    "AMD": TickerProfile(160.00, 0.50, "tech"),
    "INTC": TickerProfile(25.00, 0.40, "tech"),
    "ORCL": TickerProfile(170.00, 0.30, "tech"),
    "PYPL": TickerProfile(70.00, 0.35, "finance"),
    "BAC": TickerProfile(40.00, 0.25, "finance"),
    "GS": TickerProfile(500.00, 0.27, "finance"),
    "DIS": TickerProfile(100.00, 0.28, "consumer"),
    "WMT": TickerProfile(80.00, 0.18, "consumer"),
}


def fallback_profile(ticker: str) -> TickerProfile:
    """A stable made-up profile for symbols not in PROFILES (same ticker -> same profile)."""
    rng = random.Random(zlib.crc32(ticker.encode()))  # str hash() is salted per process
    return TickerProfile(price=round(rng.uniform(50, 300), 2), volatility=round(rng.uniform(0.25, 0.50), 2))


class GBMSimulator:
    """Pure price model: no asyncio, no cache. Call ``step()`` once per tick."""

    def __init__(
        self,
        *,
        tick_seconds: float = TICK_SECONDS,
        time_scale: float = TIME_SCALE,
        event_probability: float = EVENT_PROBABILITY,
        event_size: tuple[float, float] = EVENT_SIZE,
        seed: int | None = None,
        profiles: Mapping[str, TickerProfile] = PROFILES,
    ) -> None:
        self._dt = tick_seconds * time_scale / TRADING_SECONDS_PER_YEAR  # one tick, in years
        self._event_probability = event_probability
        self._event_size = event_size
        self._rng = random.Random(seed)
        self._known = profiles
        self._profiles: dict[str, TickerProfile] = {}
        self._prices: dict[str, float] = {}

    def add(self, ticker: str, price: float | None = None) -> float:
        """Start simulating a ticker, from ``price`` if given, else its seed price. Returns its price."""
        if ticker not in self._prices:
            profile = self._known.get(ticker) or fallback_profile(ticker)
            self._profiles[ticker] = profile
            self._prices[ticker] = price if price is not None else profile.price
        return self._prices[ticker]

    def remove(self, ticker: str) -> None:
        self._profiles.pop(ticker, None)
        self._prices.pop(ticker, None)

    def tickers(self) -> list[str]:
        return sorted(self._prices)

    def __contains__(self, ticker: object) -> bool:
        return ticker in self._prices

    def step(self) -> dict[str, float]:
        """Advance every ticker by one tick and return the new prices."""
        market = self._rng.gauss(0.0, 1.0)
        sector_shocks = {name: self._rng.gauss(0.0, 1.0) for name in SECTORS}
        sqrt_dt = math.sqrt(self._dt)
        for ticker, price in self._prices.items():
            profile = self._profiles[ticker]
            market_w, sector_w = SECTORS.get(profile.sector, (MARKET_ONLY_WEIGHT, 0.0))
            idio_w = math.sqrt(1.0 - market_w**2 - sector_w**2)
            z = market_w * market + idio_w * self._rng.gauss(0.0, 1.0)
            if sector_w:
                z += sector_w * sector_shocks[profile.sector]
            sigma = profile.volatility
            price *= math.exp((profile.drift - 0.5 * sigma**2) * self._dt + sigma * sqrt_dt * z)
            if self._rng.random() < self._event_probability:
                price *= 1 + self._rng.choice((-1, 1)) * self._rng.uniform(*self._event_size)
            self._prices[ticker] = price
        return dict(self._prices)


class SimulatorDataSource(MarketDataSource):
    """Runs a GBMSimulator on a background task and publishes its prices to the cache."""

    def __init__(
        self,
        cache: PriceCache,
        *,
        simulator: GBMSimulator | None = None,
        tick_seconds: float = TICK_SECONDS,
        initial_prices: Mapping[str, float] | None = None,
    ) -> None:
        self._cache = cache
        self._sim = simulator or GBMSimulator(tick_seconds=tick_seconds)
        self._tick_seconds = tick_seconds
        self._initial_prices = dict(initial_prices or {})
        self._task: asyncio.Task | None = None

    @property
    def mode(self) -> str:
        return "simulator"

    @property
    def max_quote_age(self) -> float:
        return 10 * self._tick_seconds

    async def start(self, tickers: Iterable[str]) -> None:
        for ticker in tickers:
            self._add(ticker)
        self._task = asyncio.create_task(self._run(), name="market-simulator")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker not in self._sim:
            self._add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self._sim.remove(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return self._sim.tickers()

    def _add(self, ticker: str) -> None:
        price = round(self._sim.add(ticker, self._initial_prices.get(ticker)), 2)
        self._cache.update(ticker, price, reference_price=price)  # change is measured from here

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        next_tick = loop.time()
        while True:
            next_tick += self._tick_seconds
            await asyncio.sleep(max(0.0, next_tick - loop.time()))
            try:
                for ticker, price in self._sim.step().items():
                    self._cache.update(ticker, round(price, 2))
            except Exception:  # never let one bad tick kill the feed
                logger.exception("Simulator tick failed")
