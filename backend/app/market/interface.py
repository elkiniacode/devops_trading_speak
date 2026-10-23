"""The contract every market data source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable


class MarketDataSource(ABC):
    """Produces prices for a set of tickers and writes them into a PriceCache.

    Tickers passed in are already normalized (see ``normalize_ticker``).
    All methods are called from the event loop.
    """

    @property
    @abstractmethod
    def mode(self) -> str:
        """'simulator', 'massive-snapshot' or 'massive-eod'."""

    @property
    @abstractmethod
    def max_quote_age(self) -> float:
        """Seconds after which a cached price is too old to trade on."""

    @abstractmethod
    async def start(self, tickers: Iterable[str]) -> None:
        """Begin producing prices. On return, every ticker the source could price is in the cache."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop background work and release resources. Safe to call twice."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Track a ticker and cache its price before returning. Idempotent.

        Raises UnknownTickerError if the source knows the symbol does not exist.
        """

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Stop tracking a ticker and drop it from the cache. Idempotent."""

    @abstractmethod
    def get_tickers(self) -> list[str]:
        """The tickers currently tracked, sorted."""
