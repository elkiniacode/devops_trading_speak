# Market Simulator

This doc covers how FinAlly simulates stock prices when no `MASSIVE_API_KEY` is set, which is the default for most users. It explains the model, the constants and why they were chosen, and gives the code structure. The simulator plugs into the `MarketDataSource` interface defined in `MARKET_INTERFACE.md`.

The code in §8 and the tests in §10 were run on Python 3.12, and every number in §3–§5 was measured or computed from that code.

---

## 1. Goals

| Goal | How |
|---|---|
| Looks like a real market | Geometric Brownian motion (GBM): log-normal, always positive, percentage-based moves |
| Lively enough for a 10-minute demo | Simulated time runs **20× faster** than wall-clock time (§3) |
| Tickers move together | One market factor plus one sector factor per ticker (§4; PLAN S5) |
| Drama | About one sudden 2–5% jump per minute across the default watchlist (§5) |
| Any ticker works | Unknown symbols get a stable, made-up profile (§6) |
| Reproducible | `SIM_SEED` makes every run identical (§7) |
| Cheap and simple | Standard library only, about 11 µs per tick for 10 tickers, one asyncio task |

Non-goals: no order book, bid/ask spread or volume; no market hours (the simulated market never closes); no mean reversion; no intraday seasonality.

---

## 2. The Price Model

Each tick, every ticker moves by the exact GBM step:

```
S(t + Δt) = S(t) · exp( (μ − σ²/2)·Δt + σ·√Δt·Z )
```

| Symbol | Meaning | Value |
|---|---|---|
| `S` | Price | Seed price at start (§6) |
| `μ` | Annual drift | 0.05 for all tickers |
| `σ` | Annual volatility | Per ticker, 0.20–0.55 (§6) |
| `Δt` | One tick, in **trading years** | `0.5 s × 20 / (252 × 6.5 × 3600 s)` = 1.6958e-6 |
| `Z` | Standard normal shock, correlated across tickers | §4 |

Why this form:
- **The exponential keeps prices positive.** Unlike the additive `S·(1 + σ√Δt·Z)` approximation, the price can never cross zero.
- **The `−σ²/2` term (Itô correction)** makes the *expected* price grow at exactly μ. Without it, high-volatility tickers would drift upward on their own.
- **Drift hardly matters at demo time scales.** One wall-clock hour is 20 trading hours, about 0.012 trading years, so μ = 5% adds about 0.06% per hour. It is kept for correctness, not for its effect.

---

## 3. Time Scale and Calibration (R15)

Real-time GBM with realistic volatility is very calm: AAPL (σ = 25%) moves about 0.25% in 10 minutes. That's too little to see on a heatmap or a P&L chart during a demo. The simulator therefore runs simulated time **20× faster** (`TIME_SCALE = 20`): one wall-clock minute is 20 trading minutes, and a full 6.5-hour trading day passes in about 20 minutes. Each ticker's volatility parameter stays realistic; only the clock is faster.

The table shows typical moves (one standard deviation) at `TIME_SCALE = 20` with 0.5 s ticks, excluding events:

| σ (annual) | Example | Per tick | 1 min | 10 min | 1 hour |
|---|---|---|---|---|---|
| 0.20 | V | 0.026% | 0.29% | 0.90% | 2.2% |
| 0.25 | AAPL | 0.033% (≈ $0.06) | 0.36% | 1.13% | 2.8% |
| 0.35 | META | 0.046% | 0.50% | 1.58% | 3.9% |
| 0.55 | TSLA | 0.072% | 0.79% | 2.48% | 6.1% |

What this means in practice:
- **Most ticks change the displayed price.** For a typical stock above about $30, one tick's standard deviation is at least a cent, so the watchlist flashes continuously.
- **After 10 minutes, positions show P&L of ±1–2.5%.** That is visible on a heatmap whose color scale is clamped at ±5% (R30). Events add occasional ±2–5% jumps.
- **The pace is plausible:** one wall-clock hour equals about three trading days, and TSLA's 6% hourly move matches its real three-day volatility.

To make the market calmer or wilder, change `TIME_SCALE`. Moves scale with its square root: `TIME_SCALE = 5` halves every move in the table, and `80` doubles it.

---

## 4. Correlated Moves (PLAN S5)

Real stocks move together: the market as a whole, then each sector, then each company on its own. Instead of a covariance matrix and a Cholesky decomposition, each tick draws **one market shock M, one shock S_k per sector, and one idiosyncratic shock ε_i per ticker**, all independent standard normals. They are then combined:

```
Z_i = a·M + b·S_sector(i) + c·ε_i         with  c = √(1 − a² − b²)
```

Because a² + b² + c² = 1, each `Z_i` has variance 1, so **each ticker's volatility is exactly its `σ`** no matter how correlated it is. Two tickers' correlation is just the sum of their shared loadings:

- Same sector: `a_i·a_j + b_i·b_j`
- Different sectors: `a_i·a_j`

| Sector | Market weight `a` | Sector weight `b` | Idiosyncratic weight `c` | Correlation within the sector |
|---|---|---|---|---|
| `tech` | 0.55 | 0.55 | 0.63 | **0.61** |
| `consumer` | 0.50 | 0.45 | 0.74 | **0.45** |
| `finance` | 0.50 | 0.60 | 0.62 | **0.61** |
| no sector (unknown tickers) | 0.50 | 0 | 0.87 | — |

Correlations across sectors come out at about 0.25–0.28 (for example tech × finance = 0.55 × 0.50 = 0.275), and an unknown ticker correlates at about 0.25–0.28 with everything. The tests confirm these values empirically over 20,000 ticks (§10).

Adding a sector means adding one line to `SECTORS`. The weights must satisfy `a² + b² ≤ 1`.

---

## 5. Events

Each tick, each ticker independently has a probability of `EVENT_PROBABILITY = 0.0008` of an **event**: an instant jump of a random 2–5% (`EVENT_SIZE`), up or down with equal probability, applied after the GBM step.

- **Frequency:** a given ticker jumps about once every 10 minutes. Across the 10 default tickers, that is **about one jump per minute** somewhere on the watchlist.
- **Jumps are permanent.** There is no snap-back; the price continues from the new level, like a real news move.
- **Jumps hit one ticker at a time.** Sector-wide shocks are already covered by the sector factor.
- **Jumps make the demo show what the product does:** a 3% jump on a held stock produces a bright red flash, a recolored heatmap tile and a visible step in the P&L chart. It also gives the AI assistant something to comment on.

---

## 6. Ticker Profiles

The ten defaults from PLAN §7, plus a few common extras, so that "add AMD" looks realistic. Seed prices are illustrative; only their rough size matters, since they drift from the first tick.

| Ticker | Seed $ | σ | Sector | | Ticker | Seed $ | σ | Sector |
|---|---|---|---|---|---|---|---|---|
| AAPL | 190 | 0.25 | tech | | AMD | 160 | 0.50 | tech |
| GOOGL | 175 | 0.28 | tech | | INTC | 25 | 0.40 | tech |
| MSFT | 420 | 0.24 | tech | | ORCL | 170 | 0.30 | tech |
| AMZN | 185 | 0.30 | consumer | | PYPL | 70 | 0.35 | finance |
| TSLA | 250 | 0.55 | consumer | | BAC | 40 | 0.25 | finance |
| NVDA | 130 | 0.50 | tech | | GS | 500 | 0.27 | finance |
| META | 560 | 0.35 | tech | | DIS | 100 | 0.28 | consumer |
| JPM | 205 | 0.22 | finance | | WMT | 80 | 0.18 | consumer |
| V | 280 | 0.20 | finance | | | | | |
| NFLX | 700 | 0.38 | consumer | | | | | |

**Unknown tickers** (R12) get a profile derived from the symbol itself: a `random.Random` seeded with `zlib.crc32(ticker)` draws a price in $50–$300 and a σ in 0.25–0.50, with no sector. The same symbol therefore always gets the same profile across restarts and machines. Python's built-in `hash()` can't be used for this, because it is randomized per process for strings.

Ticker format validation (`^[A-Z]{1,5}(\.[A-Z])?$`) happens at the API boundary, before the simulator sees the symbol (`MARKET_INTERFACE.md` §8.2).

---

## 7. Reference Price, Restarts and Determinism

- **`reference_price`** is set when a ticker is added: the seed price, or the restored price (below). It never changes after that. The watchlist's change % is therefore **change since the session started**, and the UI should label it that way in simulator mode (R11 correction).
- **Restarts (R14):** without help, a restart sends every price back to its seed. Someone who bought NVDA after it drifted to $150 would see an instant loss when it reset to $130. `SimulatorDataSource(initial_prices=...)` restarts each ticker from a given price. The backend persists the cache's latest prices and passes them back in at startup (`MARKET_INTERFACE.md` §8.5).
- **`SIM_SEED`** (an integer) seeds the single `random.Random` behind every draw. Same seed and same ticker add order means the same price path, tick for tick. That's useful for demos and for checking the heatmap's colors in E2E tests. It does **not** make wall-clock tests deterministic, because the number of ticks before an assertion depends on timing (REVIEW's R36 correction). Tests that check money should write fixed prices into a `PriceCache` instead (`MARKET_INTERFACE.md` §11).

---

## 8. Code: `backend/app/market/simulator.py`

The file has two classes with separate jobs:

- **`GBMSimulator`** is the pure model. It has no asyncio and no cache. `step()` advances every ticker by one tick and returns the prices. All the math lives here, and it is unit-tested directly and synchronously.
- **`SimulatorDataSource`** is the `MarketDataSource` adapter. It owns the asyncio task, calls `step()` every 0.5 s, rounds prices to cents and writes them to the `PriceCache`.

```python
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
```

### Implementation notes

- **The internal price keeps full precision.** Only the published price is rounded to cents, so rounding never feeds back into the random walk. A $20 stock with σ = 0.25 moves only about $0.007 per tick, so it often publishes the same cent twice. That shows as `direction: "flat"`, with no flash.
- **One RNG for everything.** Draws happen in a fixed order: market, then sectors in `SECTORS` order, then tickers in insertion order. That makes a seeded run reproducible. Adding or removing a ticker changes the sequence from that point on, as expected.
- **The tick loop doesn't drift.** It schedules against `loop.time()` targets (`next_tick += 0.5`) rather than sleeping 0.5 s after each step, so the loop's own work never stretches the interval. If the event loop is blocked for a while, the missed ticks are skipped rather than replayed in a burst.
- **`add_ticker` is synchronous in effect.** The price is in the cache before the call returns, so "add PYPL and buy 5 PYPL" in one LLM response works (R12, R25).
- **Removing a ticker** deletes it from both the model and the cache. Adding it back later restarts it from its seed price, or from `initial_prices`.
- **Performance:** `step()` takes about **11 µs for 10 tickers and 51 µs for 50** (measured on CPython 3.12). Each cache write adds a few microseconds. The 0.5 s tick uses about 0.01% of one core, so there's no need for numpy or a thread.

---

## 9. Lifecycle

```
lifespan startup
  └─ create_market_data_source(cache, initial_prices=marks)   # SIM_SEED read here
       └─ SimulatorDataSource(GBMSimulator(seed))
  └─ await source.start(watchlist ∪ positions)
       ├─ each ticker: sim.add() → cache.update(price, reference_price=price)   # cache full before return
       └─ create_task(_run)  ── every 0.5 s ──▶ sim.step() → cache.update(...) ──▶ SSE picks up cache.version
API: add_ticker / remove_ticker  (watchlist, trades, LLM actions)
lifespan shutdown
  └─ persist marks → await source.stop()  (cancels the task)
```

---

## 10. Tests

These are the simulator tests from the prototype run, written for pytest with `pytest-asyncio` (`asyncio_mode = auto`). All of them passed; the statistical ones take a few seconds.

```python
import asyncio
import math
import statistics

import pytest

from app.market import PriceCache
from app.market.simulator import (
    PROFILES, TRADING_SECONDS_PER_YEAR, GBMSimulator, SimulatorDataSource, TickerProfile, fallback_profile,
)


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
    assert statistics.correlation(r["AAPL"], r["MSFT"]) == pytest.approx(0.605, abs=0.03)  # tech x tech
    assert statistics.correlation(r["AAPL"], r["JPM"]) == pytest.approx(0.275, abs=0.03)  # tech x finance


def test_events_jump_two_to_five_percent():
    calm = {"X": TickerProfile(100.0, 1e-9)}
    sim = GBMSimulator(seed=1, event_probability=1.0, profiles=calm)
    sim.add("X")
    prev = 100.0
    for _ in range(200):
        cur = sim.step()["X"]
        assert 0.0199 < abs(cur / prev - 1) < 0.0501
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
    assert cache.get_price("PYPL") == 70.0  # priced before add_ticker returns
    v = cache.version
    await asyncio.sleep(0.1)
    assert cache.version > v  # the background task is ticking
    await source.remove_ticker("GOOGL")
    assert source.get_tickers() == ["AAPL", "PYPL"] and "GOOGL" not in cache
    await source.stop()
    await source.stop()  # idempotent
```

Run the statistical tests with `event_probability=0.0`. Jumps would make the variance and correlation estimates noisy and the tests flaky. The `TickerProfile(100.0, 1e-9)` trick isolates events from diffusion.

---

## 11. Tuning Guide

| You want | Change |
|---|---|
| A calmer or wilder market overall | `TIME_SCALE`; moves scale with √`TIME_SCALE` (5 halves them, 80 doubles them) |
| One stock to be more volatile | Its `σ` in `PROFILES` |
| More or fewer jumps | `EVENT_PROBABILITY` (jumps per minute ≈ `EVENT_PROBABILITY × 120 × number of tickers`) |
| Bigger jumps | `EVENT_SIZE` |
| Stocks less tied to the market | Lower the sector's `a` in `SECTORS`; `c` adjusts automatically |
| A new sector | Add a `SECTORS` entry (keep `a² + b² ≤ 1`) and tag profiles with it |
| Smoother sparklines | Keep `TIME_SCALE` and lower `TICK_SECONDS`. Per-tick moves shrink with √tick, but the frontend receives more points. 0.5 s matches PLAN §6. |
| Identical runs | Set `SIM_SEED` |

Every knob is a module-level constant or a constructor argument, so tests can override them without patching.
