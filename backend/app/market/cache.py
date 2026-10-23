"""In-memory store of the latest price per ticker."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from .models import PriceUpdate
from .candles import TIMEFRAME_SECONDS


class PriceCache:
    """Latest price per ticker. The active data source writes; everything else reads.

    ``version`` goes up on every change, so a reader such as the SSE stream can
    tell cheaply whether anything changed since it last looked.
    """

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._prices: dict[str, PriceUpdate] = {}
        self._lock = threading.Lock()
        self._clock = clock
        self._version = 0
        self._candles: dict[tuple[str, str], deque[dict]] = {}

    def update(self, ticker: str, price: float, *, reference_price: float | None = None) -> PriceUpdate:
        """Record a new price. ``previous_price`` and, unless given, ``reference_price`` carry over."""
        with self._lock:
            last = self._prices.get(ticker)
            if reference_price is None:
                reference_price = last.reference_price if last else price
            entry = PriceUpdate(
                ticker=ticker,
                price=price,
                previous_price=last.price if last else price,
                reference_price=reference_price,
                timestamp=self._clock(),
            )
            self._prices[ticker] = entry
            for timeframe, seconds in TIMEFRAME_SECONDS.items():
                key = (ticker, timeframe)
                bucket = int(entry.timestamp) // seconds * seconds
                series = self._candles.setdefault(key, deque(maxlen=500))
                if series and series[-1]["time"] == bucket:
                    candle = series[-1]
                    candle["high"] = max(candle["high"], price)
                    candle["low"] = min(candle["low"], price)
                    candle["close"] = price
                elif not series or bucket > series[-1]["time"]:
                    series.append({"time": bucket, "open": price, "high": price, "low": price, "close": price, "volume": 0})
            self._version += 1
            return entry

    def remove(self, ticker: str) -> None:
        with self._lock:
            if self._prices.pop(ticker, None) is not None:
                for timeframe in TIMEFRAME_SECONDS:
                    self._candles.pop((ticker, timeframe), None)
                self._version += 1

    def get_candles(self, ticker: str, timeframe: str, limit: int = 150) -> list[dict]:
        with self._lock:
            return [dict(item) for item in list(self._candles.get((ticker, timeframe), ()))[-limit:]]

    def get(self, ticker: str) -> PriceUpdate | None:
        return self._prices.get(ticker)

    def get_price(self, ticker: str) -> float | None:
        entry = self._prices.get(ticker)
        return entry.price if entry else None

    def get_fresh(self, ticker: str, max_age: float) -> PriceUpdate | None:
        """The entry if it is at most ``max_age`` seconds old, else None. Trades must fill from this."""
        entry = self._prices.get(ticker)
        if entry is None or self._clock() - entry.timestamp > max_age:
            return None
        return entry

    def get_all(self) -> dict[str, PriceUpdate]:
        with self._lock:
            return dict(self._prices)

    @property
    def version(self) -> int:
        return self._version

    def __contains__(self, ticker: object) -> bool:
        return ticker in self._prices

    def __len__(self) -> int:
        return len(self._prices)
