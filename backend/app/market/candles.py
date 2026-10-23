"""Bounded deterministic OHLCV history for the workstation chart."""

from __future__ import annotations

import hashlib
import random
import time

TIMEFRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


def history(ticker: str, timeframe: str, price: float, limit: int = 150, seed: int = 0) -> list[dict]:
    seconds = TIMEFRAME_SECONDS[timeframe]
    now = int(time.time())
    end = now - now % seconds
    digest = hashlib.sha256(f"{seed}:{ticker}:{timeframe}".encode()).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    scale = max(price * 0.003 * (seconds / 3600) ** 0.5, price * 0.0002)
    close = price
    candles = []
    for index in range(limit - 1, -1, -1):
        open_price = close
        close = max(0.01, open_price + rng.gauss(0, scale))
        high = max(open_price, close) + rng.random() * scale * 0.45
        low = max(0.01, min(open_price, close) - rng.random() * scale * 0.45)
        candles.append({"time": end - index * seconds, "open": round(open_price, 4), "high": round(high, 4),
                        "low": round(low, 4), "close": round(close, 4), "volume": int(1000 + rng.random() * 90000)})
    shift = price - candles[-1]["close"]
    for candle in candles:
        candle["open"] = round(candle["open"] + shift, 4)
        candle["high"] = round(candle["high"] + shift, 4)
        candle["low"] = round(max(0.01, candle["low"] + shift), 4)
        candle["close"] = round(candle["close"] + shift, 4)
    return candles
