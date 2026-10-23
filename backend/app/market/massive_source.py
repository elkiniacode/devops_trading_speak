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
