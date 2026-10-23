import asyncio
import json
import math
import statistics
import time
from datetime import datetime

import httpx
import pytest

from app.market import PriceCache, UnknownTickerError, normalize_ticker
from app.market.massive_source import NEW_YORK, MassiveDataSource, RateLimiter, parse_snapshot
from app.market.simulator import (
    PROFILES,
    TRADING_SECONDS_PER_YEAR,
    GBMSimulator,
    SimulatorDataSource,
    TickerProfile,
    fallback_profile,
)
from app.market.stream import price_events

# ---------------------------------------------------------------- models / cache


def test_normalize_ticker():
    assert normalize_ticker(" aapl ") == "AAPL"
    assert normalize_ticker("brk.b") == "BRK.B"
    for bad in ["", "TOOLONG", "AA1", "A-B", "$AAPL"]:
        with pytest.raises(ValueError):
            normalize_ticker(bad)


def test_cache_carries_previous_and_reference():
    now = [1000.0]
    cache = PriceCache(clock=lambda: now[0])
    first = cache.update("AAPL", 190.0, reference_price=189.0)
    assert (first.previous_price, first.reference_price, first.direction) == (190.0, 189.0, "flat")
    second = cache.update("AAPL", 190.5)
    assert (second.previous_price, second.reference_price, second.direction) == (190.0, 189.0, "up")
    assert cache.version == 2
    d = second.to_dict()
    assert d["change"] == 1.5 and d["change_percent"] == 0.79
    assert d["timestamp"] == "1970-01-01T00:16:40.000Z"
    now[0] += 6
    assert cache.get_fresh("AAPL", max_age=5) is None
    assert cache.get_fresh("AAPL", max_age=10) is second
    cache.remove("AAPL")
    assert "AAPL" not in cache and cache.version == 3


# ---------------------------------------------------------------- simulator


def make_sim(**kw):
    sim = GBMSimulator(seed=42, **kw)
    for t in ["AAPL", "MSFT", "NVDA", "JPM", "V"]:
        sim.add(t)
    return sim


def test_simulator_is_deterministic_and_positive():
    a, b = make_sim(), make_sim()
    for _ in range(2000):
        pa, pb = a.step(), b.step()
    assert pa == pb
    assert all(p > 0 for p in pa.values())


def test_volatility_matches_profile():
    sim = make_sim(event_probability=0.0)
    prev = sim.step()
    returns = []
    for _ in range(20000):
        cur = sim.step()
        returns.append(math.log(cur["AAPL"] / prev["AAPL"]))
        prev = cur
    dt = 0.5 * 20 / TRADING_SECONDS_PER_YEAR
    expected = PROFILES["AAPL"].volatility * math.sqrt(dt)
    assert statistics.stdev(returns) == pytest.approx(expected, rel=0.05)


def test_same_sector_moves_together_more():
    sim = make_sim(event_probability=0.0)
    prev = sim.step()
    r = {t: [] for t in prev}
    for _ in range(20000):
        cur = sim.step()
        for t in cur:
            r[t].append(math.log(cur[t] / prev[t]))
        prev = cur
    tech = statistics.correlation(r["AAPL"], r["MSFT"])
    cross = statistics.correlation(r["AAPL"], r["JPM"])
    assert tech == pytest.approx(0.605, abs=0.03)
    assert cross == pytest.approx(0.275, abs=0.03)


def test_events_jump_two_to_five_percent():
    calm = {"X": TickerProfile(100.0, 1e-9)}
    sim = GBMSimulator(seed=1, event_probability=1.0, profiles=calm)
    sim.add("X")
    prev = 100.0
    for _ in range(200):
        cur = sim.step()["X"]
        move = abs(cur / prev - 1)
        assert 0.0199 < move < 0.0501
        prev = cur


def test_fallback_profile_is_stable():
    assert fallback_profile("PLTR") == fallback_profile("PLTR")
    p = fallback_profile("ZZZZ")
    assert 50 <= p.price <= 300 and 0.25 <= p.volatility <= 0.5


async def test_simulator_source_lifecycle():
    cache = PriceCache()
    source = SimulatorDataSource(cache, tick_seconds=0.01, initial_prices={"AAPL": 201.5})
    await source.start(["AAPL", "GOOGL"])
    assert cache.get("AAPL").price == 201.5 and cache.get("AAPL").reference_price == 201.5
    await source.add_ticker("PYPL")
    assert cache.get_price("PYPL") == 70.0
    v = cache.version
    await asyncio.sleep(0.1)
    assert cache.version > v
    await source.remove_ticker("GOOGL")
    assert source.get_tickers() == ["AAPL", "PYPL"] and "GOOGL" not in cache
    await source.stop()
    await source.stop()


# ---------------------------------------------------------------- massive

DOC_SAMPLE = {
    "day": {"c": 20.506, "h": 20.64, "l": 20.506, "o": 20.64, "v": 37216, "vw": 20.616},
    "lastQuote": {"P": 20.6, "S": 22, "p": 20.5, "s": 13, "t": 1605192959994246100},
    "lastTrade": {"c": [14, 41], "i": "71675577320245", "p": 20.506, "s": 2416, "t": 1605192894630916600, "x": 4},
    "min": {"av": 37216, "c": 20.506, "h": 20.506, "l": 20.506, "n": 1, "o": 20.506, "t": 1684428600000, "v": 5000},
    "prevDay": {"c": 20.63, "h": 21, "l": 20.5, "o": 20.79, "v": 292738, "vw": 20.6939},
    "ticker": "BCAT",
    "todaysChange": -0.124,
    "todaysChangePerc": -0.601,
    "updated": 1605192894630916600,
}


def test_parse_snapshot():
    assert parse_snapshot(DOC_SAMPLE) == (20.506, 20.63)
    starter = {k: v for k, v in DOC_SAMPLE.items() if k not in ("lastTrade", "lastQuote")}
    starter["min"] = {**starter["min"], "c": 20.55}
    assert parse_snapshot(starter) == (20.55, 20.63)
    pre_open = {"ticker": "X", "day": {"c": 0}, "min": {}, "prevDay": {"c": 50.0}}
    assert parse_snapshot(pre_open) == (50.0, 50.0)
    assert parse_snapshot({"ticker": "X"}) is None


def snapshot_item(ticker, price, prev):
    return {"ticker": ticker, "lastTrade": {"p": price}, "prevDay": {"c": prev}, "day": {"c": price}}


def mock_client(handler):
    return httpx.AsyncClient(base_url="https://api.massive.com", transport=httpx.MockTransport(handler))


async def test_massive_snapshot_mode():
    calls = []

    def handler(request: httpx.Request):
        calls.append(request)
        tickers = request.url.params["tickers"].split(",")
        known = {"AAPL": (190.1, 189.0), "MSFT": (420.0, 421.0), "PYPL": (70.0, 69.0)}
        items = [snapshot_item(t, *known[t]) for t in tickers if t in known]
        return httpx.Response(200, json={"status": "OK", "count": len(items), "tickers": items})

    cache = PriceCache()
    source = MassiveDataSource(cache, api_key="k", client=mock_client(handler))
    await source.start(["MSFT", "AAPL"])
    assert calls[0].url.params["tickers"] == "AAPL,MSFT"
    assert cache.get("AAPL").price == 190.1 and cache.get("AAPL").reference_price == 189.0
    await source.add_ticker("PYPL")
    assert cache.get_price("PYPL") == 70.0
    with pytest.raises(UnknownTickerError):
        await source.add_ticker("ZZZZZ")
    assert "ZZZZZ" not in source.get_tickers()
    assert source.mode == "massive-snapshot"
    await source.stop()


async def test_massive_free_tier_falls_back_to_end_of_day():
    requested = []

    def handler(request: httpx.Request):
        path = request.url.path
        requested.append(path)
        if path.startswith("/v2/snapshot"):
            return httpx.Response(403, json={"status": "NOT_AUTHORIZED", "message": "You are not entitled to this data."})
        day = path.rsplit("/", 1)[1]
        closes = {
            "2026-10-16": {"AAPL": 191.0, "MSFT": 418.0, "PYPL": 71.0},
            "2026-10-15": {"AAPL": 189.5, "MSFT": 420.0, "PYPL": 70.0},
        }.get(day, {})
        results = [{"T": t, "c": c, "o": c, "h": c, "l": c, "v": 1} for t, c in closes.items()]
        return httpx.Response(200, json={"status": "OK", "resultsCount": len(results), "results": results})

    monday = datetime(2026, 10, 19, 10, 0, tzinfo=NEW_YORK)
    cache = PriceCache()
    source = MassiveDataSource(cache, api_key="k", client=mock_client(handler), now=lambda: monday)
    await source.start(["AAPL", "MSFT"])
    assert source.mode == "massive-eod"
    days = [p.rsplit("/", 1)[1] for p in requested if "grouped" in p]
    assert days == ["2026-10-19", "2026-10-16", "2026-10-15"]  # weekend skipped for free
    aapl = cache.get("AAPL")
    assert (aapl.price, aapl.reference_price) == (191.0, 189.5)
    await source.add_ticker("PYPL")  # no request: already in the grouped data
    assert cache.get_price("PYPL") == 71.0 and len(requested) == 4
    with pytest.raises(UnknownTickerError):
        await source.add_ticker("ZZZZZ")
    requested.clear()
    await source._poll()  # refresh: only today is re-requested
    assert [p.rsplit("/", 1)[1] for p in requested] == ["2026-10-19"]
    await source.stop()


async def test_massive_failure_keeps_last_price():
    fail = [False]

    def handler(request):
        if fail[0]:
            return httpx.Response(429, json={"status": "ERROR", "error": "You've exceeded the maximum requests per minute"})
        return httpx.Response(200, json={"tickers": [snapshot_item("AAPL", 190.0, 189.0)]})

    cache = PriceCache()
    source = MassiveDataSource(cache, api_key="k", client=mock_client(handler))
    await source.start(["AAPL"])
    fail[0] = True
    assert await source._safe_poll() is False
    assert cache.get_price("AAPL") == 190.0
    await source.stop()


async def test_rate_limiter_spaces_calls():
    limiter = RateLimiter(calls=2, period=0.2)
    start = time.monotonic()
    for _ in range(3):
        await limiter.acquire()
    assert time.monotonic() - start >= 0.19


# ---------------------------------------------------------------- SSE


class FakeRequest:
    def __init__(self, polls):
        self.polls = polls

    async def is_disconnected(self):
        self.polls -= 1
        return self.polls < 0


async def test_sse_sends_snapshot_immediately():
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    events = [e async for e in price_events(FakeRequest(polls=1), cache)]
    assert events[0] == "retry: 1000\n\n"
    payload = json.loads(events[1].removeprefix("data: "))
    assert payload["AAPL"]["price"] == 190.0 and payload["AAPL"]["direction"] == "flat"
