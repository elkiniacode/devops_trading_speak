"""Shared fixtures: temp databases and a stub market source with fixed prices.

Money assertions never depend on the simulator: prices come from the stub's fixed table,
or are written straight into the PriceCache (MARKET_INTERFACE.md §11).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.context import AppContext
from app.main import create_app
from app.market import MarketDataSource, PriceCache, UnknownTickerError

PRICES = {
    "AAPL": 100.0,
    "GOOGL": 150.0,
    "MSFT": 400.0,
    "AMZN": 180.0,
    "TSLA": 250.0,
    "NVDA": 120.0,
    "META": 500.0,
    "JPM": 200.0,
    "V": 275.0,
    "NFLX": 650.0,
    "PYPL": 50.0,
    "PENY": 1.0,  # cheap enough for an order under $0.01
}
UNKNOWN = {"XYZQ"}  # the source says these don't exist
# Any other well-formed symbol (e.g. ZZZZ) is tracked but never priced, like Massive after a network error.


class StubMarket(MarketDataSource):
    """Prices tickers from a fixed table the moment they are added; never ticks."""

    def __init__(self, cache: PriceCache, initial_prices: Mapping[str, float] | None = None) -> None:
        self.cache = cache
        self.initial_prices = dict(initial_prices or {})
        self.quote_age = 60.0  # set to -1 to make every cached price stale
        self.tickers: set[str] = set()
        self.started_with: list[str] | None = None
        self.stopped = False

    @property
    def mode(self) -> str:
        return "simulator"

    @property
    def max_quote_age(self) -> float:
        return self.quote_age

    async def start(self, tickers: Iterable[str]) -> None:
        self.started_with = sorted(tickers)
        for ticker in self.started_with:
            await self.add_ticker(ticker)

    async def stop(self) -> None:
        self.stopped = True

    async def add_ticker(self, ticker: str) -> None:
        if ticker in UNKNOWN:
            raise UnknownTickerError(ticker)
        if ticker not in self.tickers and ticker in PRICES:
            self.cache.update(ticker, PRICES[ticker])
        self.tickers.add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.tickers.discard(ticker)
        self.cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return sorted(self.tickers)


def stub_factory(cache: PriceCache, *, initial_prices: Mapping[str, float] | None = None) -> StubMarket:
    return StubMarket(cache, initial_prices)


@pytest.fixture
async def ctx(tmp_path) -> AppContext:
    """A seeded temp database plus a started stub source, for calling services directly."""
    db.init_db(tmp_path / "services.db")
    cache = PriceCache()
    market = StubMarket(cache)
    await market.start(db.tracked_tickers())
    yield AppContext(cache=cache, market=market)
    db.close_db()


@pytest.fixture
def market_factory():
    """``(cache, *, initial_prices=None) -> StubMarket``, the signature create_app expects."""
    return stub_factory


@pytest.fixture
def make_app():
    """``make_app(settings)``: an app wired to the stub source (run it with TestClient)."""
    return lambda settings: create_app(settings, market_factory=stub_factory)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "api.db", static_dir=tmp_path / "no-frontend-build")


@pytest.fixture
def client(settings):
    """A TestClient with the lifespan running against a temp DB and the stub source."""
    with TestClient(create_app(settings, market_factory=stub_factory)) as test_client:
        yield test_client


@pytest.fixture
def api_ctx(client) -> AppContext:
    """The running app's AppContext (its cache and stub source)."""
    return client.app.state.ctx
