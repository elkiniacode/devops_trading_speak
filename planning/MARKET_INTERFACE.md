# Market Data Interface

This is the unified Python API that FinAlly's backend uses for stock prices. One `PriceCache` is fed by one `MarketDataSource`: the **Massive API** when `MASSIVE_API_KEY` is set, the **simulator** otherwise. Nothing outside `backend/app/market/` knows which source is running.

Related docs: `MASSIVE_API.md` (the upstream API), `MARKET_SIMULATOR.md` (the simulator's model and code).

The code below is complete. A prototype of every module passed 14 pytest tests (cache, simulator, Massive snapshot mode, the free-plan fallback, rate limiting, SSE) on Python 3.12 before this doc was written.

---

## 1. Decisions

This design settles these open items from PLAN.md §13 and REVIEW.md:

| Item | Decision |
|---|---|
| R9: which tickers get prices | Every ticker on the watchlist **or** held in a position. The trade path calls `add_ticker` before filling, so it can trade any valid symbol (§8). |
| R10: the interface | `MarketDataSource` with `start`, `stop`, `add_ticker`, `remove_ticker`, `get_tickers`, plus `mode` and `max_quote_age` (§5). Cache methods are `update`, `get`, `get_price`, `get_fresh`, `get_all` and `remove` (§4). |
| R11 and REVIEW's correction: daily change baseline | The field is **`reference_price`**. For Massive it is the **previous session's close** (`prevDay.c`), the same baseline as Massive's own `todaysChange`. For the simulator it is the **price at simulator start**, so the UI should label simulated change as "since session start". |
| R12: unknown tickers | Format check `^[A-Z]{1,5}(\.[A-Z])?$` at the API boundary (`normalize_ticker`). The simulator accepts any well-formed symbol and invents a stable profile for it. Massive raises `UnknownTickerError` when the symbol has no data, and the API turns that into a 400. `add_ticker` puts a price in the cache **before it returns**. |
| R13 / S3: SSE payload | One event whenever the cache changes, containing a **map of every tracked ticker**. The first event is sent immediately on connect. `change`, `change_percent` and `direction` are computed once on the server, so the SSE stream, REST and the LLM context always agree. |
| R14 and REVIEW's correction: restart price jump | The simulator accepts `initial_prices`. The backend should persist the cache's prices periodically and on shutdown, and pass them back in on startup (§8.5). |
| R16: Massive free plan | The free plan has no snapshot access. The source detects the 403 and switches to **end-of-day closes** from Grouped Daily (`MASSIVE_API.md` §4.5). It **never** falls back to the simulator silently. |
| R20: concurrency | Single uvicorn worker. All cache writes happen on the event loop; the cache's lock is a safety net. |
| REVIEW #4: freshness | Every cache entry has a `timestamp`. Each source declares `max_quote_age`. **Trades must fill from `cache.get_fresh(ticker, source.max_quote_age)`** and are rejected when it returns `None`. Display code may show older prices, marked as stale. |
| S6: build order | Build the simulator first. The Massive source is self-contained and can follow at any time. |

---

## 2. Module Layout

```
backend/app/market/
├── __init__.py         # public API (below)
├── models.py           # PriceUpdate, normalize_ticker, UnknownTickerError
├── cache.py            # PriceCache
├── interface.py        # MarketDataSource (ABC)
├── simulator.py        # GBMSimulator + SimulatorDataSource   -> MARKET_SIMULATOR.md
├── massive_source.py   # MassiveDataSource
├── factory.py          # create_market_data_source(): the only module that reads env vars
└── stream.py           # FastAPI router: GET /api/stream/prices
backend/tests/market/   # test_cache.py, test_simulator.py, test_massive.py, test_stream.py
```

```python
# backend/app/market/__init__.py
"""Market data: one PriceCache, fed by either the simulator or the Massive API."""

from .cache import PriceCache
from .factory import create_market_data_source
from .interface import MarketDataSource
from .models import PriceUpdate, UnknownTickerError, normalize_ticker

__all__ = [
    "MarketDataSource",
    "PriceCache",
    "PriceUpdate",
    "UnknownTickerError",
    "create_market_data_source",
    "normalize_ticker",
]
```

Code outside this package imports only from `app.market`. The router comes from `app.market.stream`.

**Dependencies:** `fastapi`, `httpx` (Massive client and tests), `tzdata` (Massive's end-of-day mode needs the America/New_York time zone, which Windows and slim Docker images don't ship). The simulator uses only the standard library; there is no numpy.

---

## 3. Data Model: `PriceUpdate`

```python
# backend/app/market/models.py
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
```

| JSON field | Type | Meaning |
|---|---|---|
| `ticker` | string | Uppercase symbol |
| `price` | number | Current price. This is exactly what a trade fills at. The simulator publishes cents; Massive passes exchange prices through unchanged. |
| `previous_price` | number | Price before the latest update. `price > previous_price` means flash green. |
| `reference_price` | number | Baseline for the watchlist's change %: previous close (Massive) or price at session start (simulator) |
| `change` | number | `price - reference_price`, 4 dp |
| `change_percent` | number | `change / reference_price * 100`, 2 dp (e.g. `0.79` means +0.79%) |
| `direction` | `"up"` \| `"down"` \| `"flat"` | Tick direction versus `previous_price` |
| `timestamp` | string | ISO-8601 UTC time **when FinAlly received the price**, e.g. `2026-10-19T14:03:12.500Z`. This is the freshness clock, not the exchange's trade time. |

The `previous_price` (last tick) and `reference_price` (daily baseline) names are deliberately distinct, so the two are hard to confuse.

---

## 4. `PriceCache`

```python
# backend/app/market/cache.py
"""In-memory store of the latest price per ticker."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .models import PriceUpdate


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
            self._version += 1
            return entry

    def remove(self, ticker: str) -> None:
        with self._lock:
            if self._prices.pop(ticker, None) is not None:
                self._version += 1

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
```

Semantics:
- **The first write** for a ticker sets `previous_price = price`, so `direction` is `"flat"` and nothing flashes. If no `reference_price` is given, it defaults to `price`.
- **Later writes** carry `reference_price` forward unless the caller passes a new one. The simulator sets it once, when a ticker is added; Massive passes `prevDay.c` on every poll.
- **`PriceUpdate` is immutable** (`frozen=True`), so readers can hold entries without copying them. `get_all()` returns a new dict.
- **`clock` is injectable**, so tests control freshness without sleeping.

---

## 5. `MarketDataSource`

```python
# backend/app/market/interface.py
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
```

### How each implementation behaves

| | `SimulatorDataSource` | `MassiveDataSource`, paid plan | `MassiveDataSource`, free plan |
|---|---|---|---|
| `mode` | `simulator` | `massive-snapshot` | `massive-eod` |
| Update cadence | every 0.5 s | every `MASSIVE_POLL_SECONDS` (15 s) | hourly (closes change once a day) |
| `max_quote_age` | 5 s | 3 × max(poll, 10 s) = 45 s | 3 h |
| `start()` | Seeds every ticker synchronously | First snapshot request (up to 30 s timeout) | Probe returns 403, then 2–4 Grouped Daily requests |
| `add_ticker()` | Immediate, any well-formed symbol | One snapshot request for that ticker. Empty result raises `UnknownTickerError`. A network error keeps the ticker tracked and logs a warning. | Looks it up in the cached closes (no request). Missing raises `UnknownTickerError`. |
| `reference_price` | Price when the ticker was added (or `initial_prices`) | `prevDay.c` | Previous session's close |
| On upstream error | n/a | Keeps last prices; retries next poll | Keeps last prices; retries after 60 s |

---

## 6. `MassiveDataSource`

The simulator's implementation is in `MARKET_SIMULATOR.md` §8. Endpoint details are in `MASSIVE_API.md`.

```python
# backend/app/market/massive_source.py
"""Real prices from the Massive (formerly Polygon.io) REST API.

See planning/MASSIVE_API.md for the endpoints, plans and response formats.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .cache import PriceCache
from .interface import MarketDataSource
from .models import UnknownTickerError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.massive.com"
SNAPSHOT_PATH = "/v2/snapshot/locale/us/markets/stocks/tickers"
GROUPED_DAILY_PATH = "/v2/aggs/grouped/locale/us/market/stocks/{day}"
NEW_YORK = ZoneInfo("America/New_York")  # needs the `tzdata` package on Windows / slim images


class NotEntitledError(Exception):
    """HTTP 403: the API key's plan does not include this endpoint."""


def _positive(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def parse_snapshot(item: dict) -> tuple[float, float] | None:
    """(price, reference_price) from one Full Market Snapshot item, or None if it has no price.

    Price precedence: last trade (Developer plan and up) > latest minute bar > today's
    bar > previous close. Zeros mean "no data yet" (e.g. before the first trade of the day).
    """
    prev_close = _positive((item.get("prevDay") or {}).get("c"))
    price = (
        _positive((item.get("lastTrade") or {}).get("p"))
        or _positive((item.get("min") or {}).get("c"))
        or _positive((item.get("day") or {}).get("c"))
        or prev_close
    )
    if price is None:
        return None
    return price, prev_close or price


class RateLimiter:
    """Allows at most ``calls`` acquisitions in any ``period`` seconds."""

    def __init__(self, calls: int, period: float) -> None:
        self._calls = calls
        self._period = period
        self._sent: deque[float] = deque()

    async def acquire(self) -> None:
        while True:
            now = time.monotonic()
            while self._sent and now - self._sent[0] >= self._period:
                self._sent.popleft()
            if len(self._sent) < self._calls:
                self._sent.append(now)
                return
            await asyncio.sleep(self._period - (now - self._sent[0]))


class MassiveDataSource(MarketDataSource):
    """Polls Massive and writes prices into the cache.

    Paid plans (Starter and up): one Full Market Snapshot request per poll prices every
    tracked ticker. Free plan: the snapshot returns 403, so the source switches, once and
    with a warning, to end-of-day closes from the Grouped Daily endpoint, throttled to
    the free tier's 5 requests/minute. It never falls back to the simulator.
    """

    def __init__(
        self,
        cache: PriceCache,
        *,
        api_key: str,
        poll_interval: float = 15.0,
        eod_refresh: float = 3600.0,
        retry_delay: float = 60.0,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(NEW_YORK),
    ) -> None:
        self._cache = cache
        self._poll_interval = poll_interval
        self._eod_refresh = eod_refresh
        self._retry_delay = retry_delay
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0
        )
        self._now = now
        self._tickers: set[str] = set()
        self._eod = False
        self._sessions: dict[date, dict[str, float]] = {}  # past grouped-daily closes; they never change
        self._latest: tuple[dict[str, float], dict[str, float]] | None = None  # (last close, close before)
        self._limiter = RateLimiter(calls=4, period=60.0)  # free tier allows 5; keep one spare
        self._request_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    @property
    def mode(self) -> str:
        return "massive-eod" if self._eod else "massive-snapshot"

    @property
    def max_quote_age(self) -> float:
        return 3 * (self._eod_refresh if self._eod else max(self._poll_interval, 10.0))

    async def start(self, tickers: Iterable[str]) -> None:
        self._tickers.update(tickers)
        try:
            await asyncio.wait_for(self._safe_poll(), timeout=30.0)
        except TimeoutError:
            logger.warning("Initial Massive poll timed out; prices will appear on the next poll")
        self._task = asyncio.create_task(self._run(), name="massive-poller")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self._client.aclose()

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        if self._eod:
            if self._latest:
                latest, prior = self._latest
                if ticker not in latest:
                    raise UnknownTickerError(ticker)
                self._cache.update(ticker, latest[ticker], reference_price=prior.get(ticker, latest[ticker]))
        else:
            try:
                items = await self._snapshot([ticker])
            except (httpx.HTTPError, NotEntitledError) as exc:
                logger.warning("Could not price %s yet (%s); the next poll will retry", ticker, exc)
            else:
                parsed = parse_snapshot(items[0]) if items else None
                if parsed is None:
                    raise UnknownTickerError(ticker)
                self._cache.update(ticker, parsed[0], reference_price=parsed[1])
        self._tickers.add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return sorted(self._tickers)

    # --- polling ------------------------------------------------------------------

    async def _run(self) -> None:
        ok = True
        while True:
            if self._eod:
                delay = self._eod_refresh if ok else self._retry_delay
            else:
                delay = self._poll_interval
            await asyncio.sleep(delay)
            ok = await self._safe_poll()

    async def _safe_poll(self) -> bool:
        try:
            await self._poll()
            return True
        except Exception as exc:  # keep polling; stale prices age out via max_quote_age
            logger.warning("Massive poll failed: %r", exc)
            return False

    async def _poll(self) -> None:
        if not self._tickers:
            return
        if not self._eod:
            try:
                items = await self._snapshot(sorted(self._tickers))
            except NotEntitledError:
                logger.warning("Massive plan has no snapshot access (free tier?); using end-of-day closes")
                self._eod = True
            else:
                for item in items:
                    ticker, parsed = item.get("ticker"), parse_snapshot(item)
                    if ticker in self._tickers and parsed:
                        self._cache.update(ticker, parsed[0], reference_price=parsed[1])
                return
        latest, prior = await self._last_two_sessions()
        self._latest = (latest, prior)
        for ticker in self._tickers:
            if ticker in latest:
                self._cache.update(ticker, latest[ticker], reference_price=prior.get(ticker, latest[ticker]))

    async def _snapshot(self, tickers: list[str]) -> list[dict]:
        data = await self._get(SNAPSHOT_PATH, {"tickers": ",".join(tickers)})
        return data.get("tickers") or []

    async def _last_two_sessions(self) -> tuple[dict[str, float], dict[str, float]]:
        """Closing prices for the two most recent trading days that have data."""
        today = self._now().date()
        found: list[tuple[date, dict[str, float]]] = []
        day = today
        while len(found) < 2 and (today - day).days < 10:
            if day.weekday() < 5:  # skip weekends without spending a request
                closes = await self._grouped_closes(day, today)
                if closes:
                    found.append((day, closes))
            day -= timedelta(days=1)
        if len(found) < 2:
            raise RuntimeError("No end-of-day data in the last 10 days")
        self._sessions = {d: c for d, c in self._sessions.items() if d >= found[1][0]}  # drop old days
        return found[0][1], found[1][1]

    async def _grouped_closes(self, day: date, today: date) -> dict[str, float]:
        if day in self._sessions:
            return self._sessions[day]
        data = await self._get(GROUPED_DAILY_PATH.format(day=day.isoformat()), {"adjusted": "true"})
        closes = {row["T"]: row["c"] for row in data.get("results") or [] if _positive(row.get("c"))}
        if day < today:  # a past day (even an empty holiday) never changes; today's may still arrive
            self._sessions[day] = closes
        return closes

    async def _get(self, path: str, params: dict) -> dict:
        async with self._request_lock:
            if self._eod:
                await self._limiter.acquire()
            response = await self._client.get(path, params=params)
        if response.status_code == 403:
            raise NotEntitledError(response.text)
        response.raise_for_status()  # 401 bad key, 429 rate limit, 5xx: the poll fails and is retried
        return response.json()
```

Design notes:
- **The poll interval doesn't depend on the number of tickers.** One snapshot request prices the whole tracked set, whether that's 10 tickers or 100. The ticker list goes in the query string; past roughly 500 symbols, split it into chunks.
- **Every poll rewrites every returned ticker**, even when its price hasn't changed. This refreshes the freshness clock: a quiet stock is still tradeable as long as the feed is healthy. When the price is unchanged, `direction` is `"flat"` and nothing flashes.
- **Unknown symbols** are absent from a snapshot response, which is how `add_ticker` detects them. A symbol that stops appearing, for example after a delisting, simply ages out via `max_quote_age`.
- **Requests are serialized** by `_request_lock`, so `add_ticker` and the poller never make concurrent calls. That matters for the free tier's rate limit.
- **Free-plan quota:** the probe request plus 2–4 Grouped Daily requests at startup, then one request per hour (today's date; past days are cached). The limiter allows 4 per minute, leaving 1 of the 5 spare.

---

## 7. Factory and Environment

```python
# backend/app/market/factory.py
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
```

| Variable | Default | Effect |
|---|---|---|
| `MASSIVE_API_KEY` | empty | Non-empty selects Massive; empty or unset selects the simulator |
| `MASSIVE_POLL_SECONDS` | `15` | Snapshot poll interval on paid plans. Use 2–5 on Advanced (real-time); 15–60 is plenty on 15-minute-delayed plans |
| `SIM_SEED` | unset | Integer for a reproducible simulator run (demos, E2E tests) |

Load `.env` (with `python-dotenv`) **before** calling the factory. Add `MASSIVE_POLL_SECONDS` and `SIM_SEED` to `.env.example` as commented-out lines.

---

## 8. Wiring Into the Backend

### 8.1 Startup and shutdown (FastAPI lifespan)

```python
# backend/app/main.py (excerpt)
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import db  # owned by the backend/DB agent; helper names below are suggestions
from app.market import PriceCache, create_market_data_source
from app.market.stream import router as stream_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()                                     # schema + seed (PLAN S2)
    cache = PriceCache()
    market = create_market_data_source(cache, initial_prices=db.load_price_marks())
    await market.start(db.tracked_tickers())      # watchlist ∪ open positions
    app.state.price_cache = cache
    app.state.market = market
    # ... start the 30 s portfolio-snapshot task here; it should also call
    #     db.save_price_marks({t: u.price for t, u in cache.get_all().items()})
    yield
    db.save_price_marks({t: u.price for t, u in cache.get_all().items()})
    await market.stop()


app = FastAPI(lifespan=lifespan)
app.include_router(stream_router)  # before the static-files mount (PLAN §13.10)
```

`db.tracked_tickers()` is `SELECT ticker FROM watchlist UNION SELECT ticker FROM positions WHERE quantity > 0`.

### 8.2 Which tickers are tracked (R9)

Rule: **tracked = watchlist ∪ open positions.** Code that changes either set keeps the source in step:

| Event | Market call |
|---|---|
| `POST /api/watchlist` | `t = normalize_ticker(body.ticker)` (a `ValueError` becomes a 400). Then `await market.add_ticker(t)` (an `UnknownTickerError` becomes a 400 `{"detail": "Unknown ticker: XYZ"}`). **Then** insert the row, so unknown symbols never reach the database. |
| `DELETE /api/watchlist/{t}` | Delete the row. If there's no open position in `t`: `await market.remove_ticker(t)`. |
| `POST /api/portfolio/trade` | `await market.add_ticker(t)` (idempotent; tracks a symbol traded from the trade bar) and then **fill from `get_fresh`** (§8.3). |
| A sell closes a position, or a trade is rejected | If `t` is neither on the watchlist nor held: `await market.remove_ticker(t)`. |
| LLM actions | Run through the same service functions as the REST endpoints, never through separate code paths. |

### 8.3 Trade fills (freshness)

```python
from fastapi import HTTPException, Request

from app.market import UnknownTickerError, normalize_ticker


async def current_fill_price(request: Request, raw_ticker: str) -> float:
    market, cache = request.app.state.market, request.app.state.price_cache
    try:
        ticker = normalize_ticker(raw_ticker)
        await market.add_ticker(ticker)
    except UnknownTickerError:
        raise HTTPException(400, f"Unknown ticker: {raw_ticker}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    quote = cache.get_fresh(ticker, market.max_quote_age)
    if quote is None:
        raise HTTPException(400, f"No current price for {ticker}; try again shortly")
    return quote.price
```

Run the trade itself under the trade lock (R20), using this price.

### 8.4 Portfolio valuation, watchlist and LLM context

- **Valuation** (header, positions table, heatmap, snapshots and the LLM context) uses `cache.get(t)`. If a held ticker has **no** cache entry, mark the position `"price": null` and the portfolio `"valuation_complete": false`. **Don't quietly substitute `avg_cost`** (REVIEW #4). If the entry is older than `max_quote_age`, value it anyway but flag it `"stale": true`.
- **`GET /api/watchlist`** returns each row merged with `cache.get(t).to_dict()`, or `null` price fields if it isn't priced yet.
- **LLM context:** include `{t: u.to_dict() for t, u in cache.get_all().items()}` and the mode (`market.mode`), so the assistant can say "prices are end-of-day" when relevant.
- **`GET /api/health`** returns `{"status": "ok", "market_data": market.mode}`. The header can show a badge such as **SIM**, **DELAYED** or **EOD** from this.

### 8.5 Restarts (R14)

The simulator restarts from its seed prices unless it receives `initial_prices`. Persist the latest cache prices, both on shutdown and from the 30-second snapshot task, so crashes are covered too. Pass them back in at startup. A small key-value table is enough, e.g. `price_marks(ticker TEXT PRIMARY KEY, price REAL, updated_at TEXT)`. With marks, held positions keep their value across `docker stop`/`start`. The simulator's `reference_price` resets to the restored price, so "change since session start" restarts at 0%. Massive ignores `initial_prices`: real prices need no restoring.

---

## 9. SSE Stream: `GET /api/stream/prices`

```python
# backend/app/market/stream.py
"""GET /api/stream/prices: Server-Sent Events fed from the PriceCache."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from .cache import PriceCache

router = APIRouter()

PUSH_INTERVAL = 0.5  # seconds between cache checks
HEARTBEAT_INTERVAL = 15.0  # comment line so proxies don't close an idle stream


@router.get("/api/stream/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    cache: PriceCache = request.app.state.price_cache
    return StreamingResponse(
        price_events(request, cache),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def price_events(request: Request, cache: PriceCache) -> AsyncIterator[str]:
    """One event per change, carrying every ticker. The first event goes out immediately."""
    yield "retry: 1000\n\n"  # EventSource reconnect delay, ms
    sent_version = -1
    last_write = time.monotonic()
    while not await request.is_disconnected():
        if cache.version != sent_version:
            sent_version = cache.version
            payload = {ticker: update.to_dict() for ticker, update in cache.get_all().items()}
            yield f"data: {json.dumps(payload)}\n\n"
            last_write = time.monotonic()
        elif time.monotonic() - last_write >= HEARTBEAT_INTERVAL:
            yield ": keepalive\n\n"
            last_write = time.monotonic()
        await asyncio.sleep(PUSH_INTERVAL)
```

The stream on the wire:

```text
retry: 1000

data: {"AAPL": {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "reference_price": 189.5, "change": 0.62, "change_percent": 0.33, "direction": "up", "timestamp": "2026-10-19T14:03:12.500Z"}, "MSFT": {"ticker": "MSFT", "price": 419.8, "previous_price": 419.91, "reference_price": 420.0, "change": -0.2, "change_percent": -0.05, "direction": "down", "timestamp": "2026-10-19T14:03:12.500Z"}}

: keepalive
```

- **Unnamed events**, so the browser's `onmessage` handler receives them.
- **The full map is sent every time.** With the simulator, every ticker changes on every tick anyway. A reconnecting client gets the complete state in its first event, so nothing needs replaying.
- **Tickers added or removed** appear in or disappear from the map on the next event, with no reconnect needed. The frontend should drop any ticker that is missing from the latest map.
- **Sending rate:** simulator, every 0.5 s. Massive, after each poll (every 15 s or hourly), with keepalives in between.
- **Load:** each client's loop is one integer comparison per 0.5 s while nothing has changed.

Frontend consumption (TypeScript):

```ts
export interface PriceUpdate {
  ticker: string;
  price: number;
  previous_price: number;
  reference_price: number;
  change: number;
  change_percent: number;
  direction: "up" | "down" | "flat";
  timestamp: string; // ISO-8601 UTC
}

const es = new EventSource("/api/stream/prices");
es.onopen = () => setStatus("connected");
es.onerror = () => setStatus(es.readyState === EventSource.CLOSED ? "disconnected" : "reconnecting");
es.onmessage = (event) => {
  const prices: Record<string, PriceUpdate> = JSON.parse(event.data);
  // replace the price map, append each price to its sparkline buffer, flash by `direction`
};
```

---

## 10. Failure Behavior

| Situation | What happens | What the user sees |
|---|---|---|
| Simulator tick throws | Exception logged; the next tick runs | Nothing |
| Massive timeout, 5xx or 429 | Poll logged as failed; last prices kept; retried next interval (60 s in end-of-day mode) | Prices pause. After `max_quote_age` they're flagged stale and trades are refused |
| Massive 401 (bad key) | Every poll fails and logs a warning | No prices for any ticker (a configuration error; check the logs) |
| Massive 403 on snapshot (free plan) | One-time switch to `massive-eod` | Static closing prices; `/api/health` reports `massive-eod` |
| Unknown ticker added | `UnknownTickerError` returns a 400 (Massive only) | An error message; the watchlist is unchanged |
| Market closed or weekend | Polls succeed; prices don't move | Static prices that remain fresh and tradeable |
| Client disconnects from SSE | Generator stops (`is_disconnected` or cancellation) | n/a |

---

## 11. Tests (`backend/tests/market/`)

These tests passed against the prototype. All of them run offline in about 15 s.

| Test | Checks |
|---|---|
| `normalize_ticker` | Upper-casing, `BRK.B` accepted, rejects empty, `TOOLONG`, digits, `$AAPL` |
| Cache semantics | `previous_price` and `reference_price` carry over, `direction`, `version` increments, `get_fresh` with an injected clock, `to_dict` rounding and ISO timestamp |
| Simulator | See `MARKET_SIMULATOR.md` §10 (determinism, volatility, correlation, events, lifecycle) |
| `parse_snapshot` | Documented sample → `(20.506, 20.63)`; Starter-shaped item (no `lastTrade`) uses `min.c`; zero `day` falls back to `prevDay.c`; empty item → `None` |
| Snapshot mode | `httpx.MockTransport`: one request with `tickers=AAPL,MSFT`; cache filled with prices and previous closes; `add_ticker("PYPL")` prices immediately; unknown symbol raises `UnknownTickerError` and isn't tracked |
| Free-plan fallback | Snapshot returns 403 → `mode == "massive-eod"`; Grouped Daily requested for Mon, then Fri and Thu (weekend skipped); price = Friday close, reference = Thursday close; `add_ticker` makes no request; a refresh re-requests only today |
| Failure | After a 429, the last price stays in the cache |
| `RateLimiter` | A third call within the window waits |
| SSE | `retry:` line first, then a `data:` event containing the cached tickers, sent immediately |

For the Massive tests, build the client with `httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))` and pass it as `client=`. Inject `now=` for date logic. Use `pytest-asyncio` with `asyncio_mode = auto`.

For **accounting tests** (portfolio, trades, LLM actions), don't use either real source: a seed alone doesn't make prices deterministic, because tick timing varies (REVIEW's R36 correction). Write the prices you need straight into a `PriceCache`, e.g. `cache.update("AAPL", 100.0)`, and give the app a stub source whose `add_ticker` does nothing and whose `max_quote_age` is large.
