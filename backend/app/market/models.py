"""Price data types shared by every market data source."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

TICKER_PATTERN = re.compile(r"[A-Z]{1,5}(\.[A-Z])?")  # AAPL, BRK.B


class UnknownTickerError(ValueError):
    """The data source knows this symbol does not exist."""


def normalize_ticker(raw: str) -> str:
    """Uppercase and validate a ticker symbol. Raises ValueError if it is malformed."""
    ticker = raw.strip().upper()
    if not TICKER_PATTERN.fullmatch(ticker):
        raise ValueError(f"Invalid ticker symbol: {raw!r}")
    return ticker


def iso_utc(ts: float) -> str:
    """Unix seconds -> '2026-10-19T14:03:12.500Z'."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class PriceUpdate:
    """The latest known price for one ticker."""

    ticker: str
    price: float  # the price trades fill at
    previous_price: float  # price before this update; drives the green/red flash
    reference_price: float  # baseline for "daily change": previous close (Massive) or session start (simulator)
    timestamp: float  # unix seconds when this price entered the cache

    @property
    def change(self) -> float:
        return self.price - self.reference_price

    @property
    def change_percent(self) -> float:
        if not self.reference_price:
            return 0.0
        return self.change / self.reference_price * 100

    @property
    def direction(self) -> str:
        if self.price > self.previous_price:
            return "up"
        if self.price < self.previous_price:
            return "down"
        return "flat"

    def to_dict(self) -> dict:
        """JSON shape used by the SSE stream, REST responses and the LLM context."""
        return {
            "ticker": self.ticker,
            "price": self.price,
            "previous_price": self.previous_price,
            "reference_price": self.reference_price,
            "change": round(self.change, 4),
            "change_percent": round(self.change_percent, 2),
            "direction": self.direction,
            "timestamp": iso_utc(self.timestamp),
        }
