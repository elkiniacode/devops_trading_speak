import asyncio
from collections.abc import Iterable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import db
from app.api.chat import router as chat_router
from app.context import AppContext
from app.market import MarketDataSource, PriceCache, UnknownTickerError

PRICES = {
    "AAPL": 190.0,
    "GOOGL": 175.0,
    "MSFT": 420.0,
    "AMZN": 185.0,
    "TSLA": 250.0,
    "NVDA": 130.0,
    "META": 560.0,
    "JPM": 205.0,
    "V": 280.0,
    "NFLX": 700.0,
    "PYPL": 70.0,
    "BRK.B": 450.0,
}


class StubMarket(MarketDataSource):
    """Fixed prices, no background task. Symbols outside ``prices`` are unknown."""

    def __init__(self, cache: PriceCache, prices: dict[str, float] | None = None, mode: str = "simulator"):
        self._cache = cache
        self._prices = dict(PRICES if prices is None else prices)
        self._mode = mode
        self._tracked: set[str] = set()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def max_quote_age(self) -> float:
        return 1e9

    def track(self, tickers: Iterable[str]) -> None:
        for t in tickers:
            if t not in self._prices:
                raise UnknownTickerError(t)
            if t not in self._tracked:
                self._tracked.add(t)
                self._cache.update(t, self._prices[t], reference_price=round(self._prices[t] / 1.01, 2))

    async def start(self, tickers: Iterable[str]) -> None:
        self.track(tickers)

    async def stop(self) -> None:
        pass

    async def add_ticker(self, ticker: str) -> None:
        self.track([ticker])

    async def remove_ticker(self, ticker: str) -> None:
        self._tracked.discard(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return sorted(self._tracked)


@pytest.fixture(autouse=True)
def llm_env(monkeypatch):
    """Mock mode by default; tests of the real path flip it and patch app.llm.client.complete."""
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)


@pytest.fixture
def real_llm(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "llm.db"
    db.init_db(path)
    yield path
    db.close_db()


@pytest.fixture
def ctx(db_file) -> AppContext:
    cache = PriceCache()
    market = StubMarket(cache)
    market.track(db.tracked_tickers())
    return AppContext(cache=cache, market=market, trade_lock=asyncio.Lock())


@pytest.fixture
def stub_market_factory():
    """A market_factory for app.main.create_app."""
    return lambda cache, **kwargs: StubMarket(cache)


@pytest.fixture
def api(ctx) -> TestClient:
    app = FastAPI()
    app.include_router(chat_router)
    app.state.ctx = ctx
    with TestClient(app) as client:
        yield client
