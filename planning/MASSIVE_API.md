# Massive API (formerly Polygon.io): Stock Prices Reference

Researched 2026-10-19 from Massive's official docs, knowledge base, pricing page and the source of the official Python client (`massive-com/client-python`, v2.9.0 released 2026-10-16). The Python examples were checked offline against `massive==2.8.0`: model field names, method signatures and return types are correct. No live API key was available, so nothing was called against the real API. Unverified points are listed in §10.

This document covers what FinAlly needs: current ("real-time") and end-of-day prices for **several tickers at once**. How FinAlly uses it is specified in `MARKET_INTERFACE.md`.

---

## 1. Key Findings

1. **The free plan cannot stream prices.** Stocks Basic ($0) is limited to end-of-day data and 5 requests per minute, and **does not include the snapshot endpoints**. A free key can fetch yesterday's closes, but prices will not move during the day. This answers PLAN.md R16.
2. **Paid plans need one request per poll.** The Full Market Snapshot endpoint accepts a comma-separated `tickers` list and returns price, today's bar and the previous close for all of them in one response. Plans from Starter ($29/mo) up include it and have no request cap.
3. **On the free plan, one request covers every ticker.** Grouped Daily (`/v2/aggs/grouped/...`) returns the close of every US stock for one date. Two requests (last two trading days) give each ticker's latest close and a previous close to compute the change from.
4. **Data is real-time only on Advanced ($199/mo).** Starter and Developer are 15 minutes delayed.
5. **Licensing:** individual plans cover personal, non-business use where **only you** see the data. Any app other people can see, including testers and demo environments, needs a Business plan. Keep this in mind before deploying FinAlly publicly with a Massive key.
6. **The official Python client is synchronous** (urllib3), hides HTTP status codes, and retries 429s on its own. FinAlly therefore calls the two REST endpoints it needs directly with `httpx` (§6). The client is still documented here (§5) because it is the easiest way to explore the API.

### What FinAlly uses, by plan

| Plan | Endpoint per poll | Price freshness | Requests | Poll interval |
|---|---|---|---|---|
| Stocks Basic (free) | Grouped Daily ×2 (latest two sessions), then today's date only | End of day | 5 / min | 1 hour (closes change once a day) |
| Stocks Starter | Full Market Snapshot (all tickers) | 15-min delayed | Unlimited | 15 s default |
| Stocks Developer | Full Market Snapshot (adds `lastTrade`) | 15-min delayed | Unlimited | 15 s default |
| Stocks Advanced | Full Market Snapshot (adds `lastTrade`, `lastQuote`) | Real-time | Unlimited | 2–5 s |

---

## 2. Basics

### Base URL and the rebrand

- Base URL: **`https://api.massive.com`**
- Polygon.io rebranded as Massive in late 2025. API keys, paths and response formats are unchanged. The client README says `api.polygon.io` "is still supported for an extended period", but new code should use `api.massive.com`.
- The PyPI package is now **`massive`** (`from massive import RESTClient`). The old `polygon-api-client` package is superseded.

### Authentication

Either form works. Prefer the header, so the key doesn't appear in logs and proxy URLs.

```http
GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT HTTP/1.1
Host: api.massive.com
Authorization: Bearer YOUR_API_KEY
```

```bash
curl "https://api.massive.com/v2/aggs/ticker/AAPL/prev?apiKey=YOUR_API_KEY"
```

### Response conventions

- JSON with a top-level `status` (`"OK"` on success) and usually a `request_id`. Always check the HTTP status code; don't rely on `status` alone.
- The data sits under `results` for most endpoints, `tickers` for the v2 snapshot list, and `ticker` for the single-ticker snapshot.
- **Tickers are case-sensitive and must be uppercase** (`AAPL`, `BRK.B`).
- Aggregate fields use one-letter keys: `o` open, `h` high, `l` low, `c` close, `v` volume, `vw` VWAP, `n` trade count, `t` timestamp, `T` ticker.
- **Timestamp units vary.** Aggregate bars (`t`) use Unix **milliseconds**. Trade, quote and snapshot `updated` timestamps use Unix **nanoseconds**.
- List endpoints (`/v3/...`) paginate with a `next_url`; the official client follows it for you. The endpoints FinAlly uses don't paginate.

### Errors and rate limits

| HTTP | Meaning | What to do |
|---|---|---|
| 401 | Missing or invalid API key | Configuration error. Log it clearly; retrying won't help. |
| 403 | Your plan doesn't include this endpoint (e.g. a snapshot on the free plan). Body: `{"status": "NOT_AUTHORIZED", "message": "You are not entitled to this data. ..."}` (see §10) | Switch strategy (FinAlly falls back to end-of-day mode). |
| 429 | Rate limit. Exact message: *"You've exceeded the maximum requests per minute, please wait or upgrade your subscription to continue."* | Wait. Never retry in a tight loop. |
| 5xx | Upstream problem | Keep the last prices and retry on the next poll. |

- **Limits are per asset class, not per account.** Every asset class you don't pay for stays on its free Basic tier (5 requests/min). A paid Options plan still leaves stock requests at 5/min. Paid stock plans have no request cap for stocks. Creating more API keys changes nothing.
- Massive's own advice for live data is WebSockets rather than tight REST polling. FinAlly sticks to REST polling (PLAN §6): one request per 15 s is far below any limit that applies to a paid plan.

---

## 3. Plans (Stocks, Individual)

From massive.com/pricing, 2026-10-19:

| | Basic | Starter | Developer | Advanced |
|---|---|---|---|---|
| Price | $0 | $29/mo | $79/mo | $199/mo |
| API calls | **5 / minute** | Unlimited | Unlimited | Unlimited |
| Timeliness | **End of day** | 15-min delayed | 15-min delayed | **Real-time** |
| History | 2 years | 5 years | 10 years | 20+ years |
| Aggregates (minute bars) | ✓ | ✓ | ✓ | ✓ |
| Second aggregates | – | ✓ | ✓ | ✓ |
| **Snapshots** | **–** | ✓ | ✓ | ✓ |
| WebSockets | – | ✓ | ✓ | ✓ |
| Trades (incl. last trade) | – | – | ✓ | ✓ |
| Quotes | – | – | – | ✓ |

All plans include all US tickers, reference data, corporate actions and technical indicators. These plans are for individual use. Business plans are priced separately (§1, item 5).

### Endpoint access by plan

| Endpoint | Basic | Starter | Developer | Advanced |
|---|---|---|---|---|
| Full Market Snapshot `/v2/snapshot/.../tickers` | – | delayed | delayed | real-time |
| Single Ticker Snapshot | – | delayed | delayed | real-time |
| Unified Snapshot `/v3/snapshot` | – | delayed | delayed | real-time |
| Last Trade `/v2/last/trade/{t}` | – | – | delayed | real-time |
| Grouped Daily `/v2/aggs/grouped/...` | EOD | delayed | delayed | real-time |
| Previous Day Bar `/v2/aggs/ticker/{t}/prev` | EOD | delayed | delayed | real-time |
| Daily Ticker Summary `/v1/open-close/{t}/{date}` | EOD | delayed | delayed | real-time |
| Market Status `/v1/marketstatus/now` | ✓ | ✓ | ✓ | ✓ |

---

## 4. Endpoints for Multi-Ticker Prices

### 4.1 Full Market Snapshot (main endpoint on paid plans)

`GET /v2/snapshot/locale/us/markets/stocks/tickers`

Returns the latest data for each requested ticker in one response. With no `tickers` parameter it returns **every** ticker (10,000+), which is far more than FinAlly needs.

| Query param | Type | Default | Notes |
|---|---|---|---|
| `tickers` | string | all tickers | Comma-separated and case-sensitive, e.g. `AAPL,TSLA,GOOG`. |
| `include_otc` | bool | `false` | Include OTC securities. |

Example response (from the docs):

```json
{
  "count": 1,
  "status": "OK",
  "tickers": [
    {
      "ticker": "BCAT",
      "day":       {"o": 20.64, "h": 20.64, "l": 20.506, "c": 20.506, "v": 37216, "vw": 20.616},
      "min":       {"o": 20.506, "h": 20.506, "l": 20.506, "c": 20.506, "v": 5000, "av": 37216, "n": 1, "t": 1684428600000},
      "prevDay":   {"o": 20.79, "h": 21, "l": 20.5, "c": 20.63, "v": 292738, "vw": 20.6939},
      "lastTrade": {"p": 20.506, "s": 2416, "x": 4, "c": [14, 41], "i": "71675577320245", "t": 1605192894630916600},
      "lastQuote": {"p": 20.5, "s": 13, "P": 20.6, "S": 22, "t": 1605192959994246100},
      "todaysChange": -0.124,
      "todaysChangePerc": -0.601,
      "updated": 1605192894630916600
    }
  ]
}
```

| Field | Meaning | Present on |
|---|---|---|
| `ticker` | Symbol | all |
| `day` | Today's bar so far (OHLC, volume, VWAP) | Starter+ |
| `min` | Latest one-minute bar; `av` = volume so far today, `t` = bar start in ms | Starter+ |
| `prevDay` | Previous session's bar. **`prevDay.c` is the previous close.** | Starter+ |
| `lastTrade` | `p` price, `s` size, `x` exchange ID, `t` SIP time in ns | Developer+ only |
| `lastQuote` | `p`/`s` bid price and size, `P`/`S` ask price and size | Advanced only |
| `todaysChange`, `todaysChangePerc` | Change from `prevDay.c` | Starter+ |
| `updated` | Last update, ns | Starter+ |
| `fmv` | Fair market value | Business plans only |

**Getting the current price:** use the first positive value in this order: `lastTrade.p`, then `min.c`, then `day.c`, then `prevDay.c`. `lastTrade` is only present on Developer and up. Before the first trade of the day, `day`/`min` can be empty or zero-filled. Treat 0 as "no data".

```python
def _positive(value):
    return float(value) if isinstance(value, (int, float)) and value > 0 else None


def parse_snapshot(item: dict) -> tuple[float, float] | None:
    """(price, previous_close) from one snapshot item, or None if it has no usable price."""
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
```

Timing notes from the docs:
- Snapshot data **is cleared daily at 3:30 AM ET** and fills again as exchanges report, from as early as 4:00 AM ET. (The client's docstring says "12am EST". Either way, expect an empty or zero-filled `day` bar early in the morning.)
- Tickers that don't exist are simply **absent** from `tickers[]`. There is no per-ticker error. If you ask for one ticker and get an empty list, the symbol is unknown (or has no data yet).
- With `include_otc=false` (the default), OTC symbols are absent too.

### 4.2 Single Ticker Snapshot

`GET /v2/snapshot/locale/us/markets/stocks/tickers/{stocksTicker}`, Starter and up. Returns the same object as above, under the key `ticker` (singular). FinAlly doesn't need it: the multi-ticker call with one symbol does the same job and has the same response shape.

### 4.3 Unified Snapshot (v3)

`GET /v3/snapshot?ticker.any_of=AAPL,MSFT&type=stocks`, Starter and up.

- Takes up to **250 tickers** per request (`ticker.any_of`). `limit` defaults to 10 and has a max of 250, so **set `limit` to at least the number of tickers**. Without `ticker.any_of` it paginates through every ticker.
- Uses snake_case fields: `last_trade.price`, `last_minute`, and `session.{open, high, low, close, previous_close, change, change_percent}`. It also returns `market_status` (`open`, `closed`, `early_trading`, `late_trading`) and `timeframe` (`"DELAYED"` / `"REAL-TIME"`).
- **Unknown tickers come back as items with an error** (`{"ticker": "XYZ", "error": "NOT_FOUND", "message": "Ticker not found."}`) instead of being left out.

It is a reasonable alternative to §4.1, and its `timeframe` field tells you whether data is delayed. FinAlly uses §4.1 because it is simpler, has no pagination or `limit` trap, and needs no prefix handling.

### 4.4 Last Trade

`GET /v2/last/trade/{stocksTicker}` is **Developer and up** only, and covers **one ticker per request**. It returns `results.p` (price), `results.s` (size) and `results.t` (SIP time in ns). Polling 10 tickers would take 10 requests, and the snapshot already contains `lastTrade` on the same plans, so FinAlly doesn't use it.

### 4.5 Grouped Daily: end-of-day prices for every ticker (main endpoint on the free plan)

`GET /v2/aggs/grouped/locale/us/market/stocks/{date}` is available on **all plans, including Basic**.

| Param | In | Default | Notes |
|---|---|---|---|
| `date` | path | – | `YYYY-MM-DD` |
| `adjusted` | query | `true` | Split-adjusted |
| `include_otc` | query | `false` | |

The response looks like this (values are illustrative):

```json
{
  "adjusted": true,
  "queryCount": 11021,
  "resultsCount": 11021,
  "status": "OK",
  "results": [
    {"T": "AAPL", "o": 189.9, "h": 192.1, "l": 189.2, "c": 191.0, "v": 51234567, "vw": 190.8, "n": 612345, "t": 1760731200000}
  ]
}
```

- A single request returns OHLCV for **every** US stock on that date: around 11k rows, roughly 1–2 MB of JSON. FinAlly keeps only `{T: c}`.
- A weekend or holiday returns `resultsCount: 0`. Massive's knowledge base recommends exactly this check to tell whether a session happened.
- On the free plan, the latest session's data appears only after the close, so "today" can be empty during the day. Walk back to the most recent date that has data.
- **Latest price plus daily change for any number of tickers takes 2 requests:** the latest session's closes and the previous session's closes.

### 4.6 Previous Day Bar

`GET /v2/aggs/ticker/{stocksTicker}/prev` is available on all plans and covers one ticker per request.

```json
{
  "ticker": "AAPL", "adjusted": true, "queryCount": 1, "resultsCount": 1, "status": "OK",
  "results": [{"T": "AAPL", "o": 115.55, "h": 117.59, "l": 114.13, "c": 115.97, "v": 131704427, "vw": 116.3058, "t": 1605042000000}]
}
```

This is useful for one-off lookups. Avoid it for a watchlist on the free plan: 10 tickers take 10 requests, which is two minutes of quota.

### 4.7 Daily Ticker Summary (open/close)

`GET /v1/open-close/{stocksTicker}/{date}` is available on all plans. It returns one ticker for one day and includes pre-market and after-hours prices:

```json
{"status": "OK", "from": "2023-01-09", "symbol": "AAPL", "open": 324.66, "high": 326.2,
 "low": 322.3, "close": 325.12, "volume": 26122646, "preMarket": 324.5, "afterHours": 322.1}
```

### 4.8 Custom Bars (historical OHLC)

`GET /v2/aggs/ticker/{t}/range/{multiplier}/{timespan}/{from}/{to}` returns bars for one ticker over a date range (`timespan` = `minute`, `hour`, `day`, …). `limit` defaults to 5,000 and has a max of 50,000. FinAlly doesn't use it, but it is how you would preload a chart with history (PLAN R28).

### 4.9 Market Status

`GET /v1/marketstatus/now` is available on all plans and updates in real time:

```json
{"market": "extended-hours", "earlyHours": false, "afterHours": true,
 "exchanges": {"nasdaq": "extended-hours", "nyse": "extended-hours", "otc": "closed"},
 "currencies": {"fx": "open", "crypto": "open"}, "serverTime": "2020-11-10T17:37:37-05:00"}
```

This is useful for an "open / closed" badge in the header. FinAlly doesn't need it for v1.

---

## 5. Official Python Client (`massive`)

```bash
uv add massive        # requires Python >= 3.10; depends on urllib3, websockets, certifi
```

```python
import os

from massive import RESTClient

client = RESTClient(api_key=os.environ["MASSIVE_API_KEY"])

# Current prices for several tickers in one request (Starter plan and up)
for s in client.get_snapshot_all("stocks", tickers=["AAPL", "MSFT", "NVDA"]):
    price = (s.last_trade and s.last_trade.price) or (s.min and s.min.close) or (s.day and s.day.close)
    print(s.ticker, price, "prev close", s.prev_day.close, f"{s.todays_change_percent:+.2f}%")

# End-of-day closes for every US stock on one date (all plans)
bars = client.get_grouped_daily_aggs("2026-10-16", adjusted=True)
closes = {b.ticker: b.close for b in bars}
print(closes["AAPL"], closes["MSFT"])

# Previous session's bar for one ticker (all plans). Returns a LIST despite its type hint.
prev = client.get_previous_close_agg("AAPL")[0]
print(prev.ticker, prev.close)

# Last trade for one ticker (Developer plan and up)
trade = client.get_last_trade("AAPL")
print(trade.price, trade.size, trade.sip_timestamp)  # sip_timestamp is in ns

# Unified snapshot: up to 250 tickers; raise `limit` or you get 10 per page
for snap in client.list_universal_snapshots(type="stocks", ticker_any_of=["AAPL", "MSFT"], limit=250):
    print(snap.ticker, snap.session.close if snap.session else None, snap.market_status)

# Open/closed status
print(client.get_market_status().market)
```

Model fields are snake_case versions of the JSON keys. `TickerSnapshot` has `.day`, `.min`, `.prev_day`, `.last_trade`, `.last_quote`, `.todays_change`, `.todays_change_percent` and `.updated`. `Agg`/`GroupedDailyAgg` have `.open`, `.high`, `.low`, `.close`, `.volume`, `.vwap`, `.timestamp` and `.ticker`.

### Things to know before using it in an async server

| Behavior | Consequence |
|---|---|
| **Synchronous** (urllib3). | In FastAPI, call it with `await asyncio.to_thread(client.get_snapshot_all, "stocks", tickers)`. A direct call blocks the event loop and every SSE stream with it. |
| The default `api_key` is `os.getenv("MASSIVE_API_KEY")`, **evaluated once at import time** (it's a default argument). | If `.env` is loaded after `massive` is imported, the default is `None`. Always pass `api_key=` explicitly. |
| Raises `massive.exceptions.AuthError` at construction if the key is `None`. | Only construct the client when a key is configured. |
| Any non-200 response raises `massive.exceptions.BadResponse(body_text)`. **The status code is not included.** | Telling 403 (plan) from 429 (rate limit) apart means string-matching the body (`"NOT_AUTHORIZED"`, `"exceeded the maximum requests"`). |
| Retries 3 times (backoff 0.1, 0.2, 0.4 s) on 413, 429, 499 and 5xx. | On the free plan, a 429 retried within a second just fails again. Use `RESTClient(api_key=..., retries=0)` and back off yourself. |
| If the expected result key is missing, or the JSON doesn't parse, it **returns `[]`** silently. | An empty result can mean "no data" or "unexpected response"; log raw responses when debugging (`trace=True`). |
| `list_*` methods return lazy iterators that follow `next_url`. | Each page is another request that counts toward the 5/min limit on the free plan. |
| Default timeouts: 10 s connect, 10 s read. | Fine for polling. |

Debugging: `RESTClient(api_key=..., trace=True, verbose=True)` logs every URL and the request/response headers, with the key redacted.

---

## 6. Raw HTTP with httpx (what FinAlly uses)

FinAlly needs two endpoints. Calling them with `httpx.AsyncClient` gives native async, real status codes (needed to tell "plan has no snapshots" apart from "rate limited"), and easy tests with `httpx.MockTransport`. It adds no dependency, since `httpx` already comes in with LiteLLM and FastAPI's test client.

```python
import asyncio
import os

import httpx

BASE_URL = "https://api.massive.com"


async def main() -> None:
    headers = {"Authorization": f"Bearer {os.environ['MASSIVE_API_KEY']}"}
    async with httpx.AsyncClient(base_url=BASE_URL, headers=headers, timeout=10.0) as client:
        # Real-time / delayed prices (Starter+): one request for all tickers
        r = await client.get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            params={"tickers": "AAPL,MSFT,NVDA"},
        )
        if r.status_code == 403:
            print("Plan has no snapshot access (free tier): use end-of-day data")
        else:
            r.raise_for_status()
            for item in r.json().get("tickers") or []:
                print(item["ticker"], parse_snapshot(item))  # parse_snapshot from §4.1

        # End-of-day closes for every ticker (all plans)
        r = await client.get("/v2/aggs/grouped/locale/us/market/stocks/2026-10-16", params={"adjusted": "true"})
        r.raise_for_status()
        closes = {row["T"]: row["c"] for row in r.json().get("results") or []}
        print(closes.get("AAPL"), closes.get("MSFT"))


asyncio.run(main())
```

### Free plan: latest close and previous close

```python
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo  # on Windows and slim Docker images, add the `tzdata` package

NEW_YORK = ZoneInfo("America/New_York")


async def last_two_sessions(client: httpx.AsyncClient) -> tuple[dict[str, float], dict[str, float]]:
    """Closes for the two most recent trading days with data. Uses 2-4 requests."""
    found: list[dict[str, float]] = []
    today = day = datetime.now(NEW_YORK).date()
    while len(found) < 2 and (today - day).days < 10:
        if day.weekday() < 5:  # weekends never have data; don't spend a request on them
            r = await client.get(f"/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}")
            r.raise_for_status()
            closes = {row["T"]: row["c"] for row in r.json().get("results") or []}
            if closes:  # empty = holiday, or today's close not published yet
                found.append(closes)
        day -= timedelta(days=1)
    if len(found) < 2:
        raise RuntimeError("No end-of-day data in the last 10 days")
    return found[0], found[1]
```

The production version of this code, with a rate limiter, caching of past days and a fallback from snapshot to end-of-day mode, is in `MARKET_INTERFACE.md` §6.

---

## 7. Market Hours and Timing

- **US stocks trade on Massive's feed from 4:00 AM to 8:00 PM ET** (pre-market, regular 9:30–16:00, after-hours). Outside those hours, and all weekend, polled prices stop changing. That is expected; it doesn't mean the feed is broken.
- **The 15-minute delay** on Starter and Developer applies to every price in the snapshot. FinAlly shows those prices as current. That is fine for a simulated portfolio, but the UI could show a "15-min delayed" badge.
- **The snapshot resets at 3:30 AM ET.** Until a ticker trades, `day` and `min` may be empty or zero. `prevDay` still holds the previous close, which `parse_snapshot` falls back to.
- **Daily change:** Massive measures `todaysChange` against `prevDay.c`, the previous session's close. FinAlly's `reference_price` uses the same baseline.
- **Holidays:** Grouped Daily returns `resultsCount: 0`. A future-holidays list is available at `/v1/marketstatus/upcoming`, but walking back day by day is simpler.

---

## 8. Recommendations for FinAlly

1. **Paid key:** poll the Full Market Snapshot every `MASSIVE_POLL_SECONDS` (default 15) with every tracked ticker in one `tickers=` parameter. Store `price` and `reference_price = prevDay.c`.
2. **Free key:** the first snapshot request returns 403. Log one clear warning and switch to **end-of-day mode**. Load the latest two sessions from Grouped Daily, refresh hourly, and cache past days, which never change. Throttle to at most 4 requests per minute, keeping 1 of the 5 spare. Prices are static during the day, which is honest for a free plan.
3. **Never switch silently to the simulator** when a key is set. A user who set a key expects real data, and mixing fake and real prices in one portfolio would be misleading.
4. **Adding a ticker:** on a paid plan, request a snapshot for just that ticker. An empty result means the ticker is unknown, so reject it. In end-of-day mode, look it up in the cached Grouped Daily map, which costs no request.
5. **Errors:** keep the last good price on any failure. Each source declares how old a price may be before trades are refused (`max_quote_age`). Log a 401 as a configuration error.
6. **Testing:** tests never call the real API. Use `httpx.MockTransport` with the documented JSON shapes (see `MARKET_INTERFACE.md` §11).

---

## 9. Quick Reference

```text
Base URL       https://api.massive.com
Auth           Authorization: Bearer <MASSIVE_API_KEY>      (or ?apiKey=<key>)

Snapshot       GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=AAPL,MSFT   Starter+
               -> tickers[].{ticker, lastTrade.p, min.c, day.c, prevDay.c, todaysChangePerc, updated(ns)}
Unified        GET /v3/snapshot?ticker.any_of=AAPL,MSFT&limit=250                    Starter+
Last trade     GET /v2/last/trade/{T}                     -> results.p                Developer+
Grouped daily  GET /v2/aggs/grouped/locale/us/market/stocks/{YYYY-MM-DD}             all plans
               -> results[].{T, o, h, l, c, v, vw, n, t(ms)}
Prev close     GET /v2/aggs/ticker/{T}/prev               -> results[0].c             all plans
Open/close     GET /v1/open-close/{T}/{YYYY-MM-DD}        -> close, preMarket, afterHours
Bars           GET /v2/aggs/ticker/{T}/range/1/day/{from}/{to}
Market status  GET /v1/marketstatus/now                   -> market, earlyHours, afterHours

Free plan      5 req/min per asset class, end-of-day only, no snapshots   -> 403 on snapshot
429 text       "You've exceeded the maximum requests per minute, ..."
```

---

## 10. Open Questions (verify with a real key)

These could not be checked without a key. None of them changes the design, because the code handles each case defensively.

1. **The exact 403 body for a missing entitlement.** It is assumed to match Polygon's `{"status": "NOT_AUTHORIZED", ...}`. FinAlly relies only on the **403 status code**, not on the body.
2. **How often `min`/`day` update on Starter**, which has no `lastTrade`. Expect a minute-level step at best. If prices move only once a minute, raising `MASSIVE_POLL_SECONDS` to 30–60 loses nothing.
3. **When the free plan publishes the day's Grouped Daily data** (same evening or next morning). The walk-back logic works either way.
4. **What the snapshot returns over a weekend** (Friday's data, or cleared). `parse_snapshot` falls back to `prevDay.c` either way.

To check them, run the §6 script with a real key and `trace=True` (client) or print `r.status_code` and `r.text` (httpx).

---

## Sources

- Full Market Snapshot: https://massive.com/docs/rest/stocks/snapshots/full-market-snapshot
- Unified Snapshot: https://massive.com/docs/rest/stocks/snapshots/unified-snapshot
- Last Trade: https://massive.com/docs/rest/stocks/trades-quotes/last-trade
- Grouped Daily (Daily Market Summary): https://massive.com/docs/rest/stocks/aggregates/daily-market-summary
- Previous Day Bar: https://massive.com/docs/rest/stocks/aggregates/previous-day-bar
- Daily Ticker Summary: https://massive.com/docs/rest/stocks/aggregates/daily-ticker-summary
- Market Status: https://massive.com/docs/rest/stocks/market-operations/market-status
- REST quickstart (base URL, auth): https://massive.com/docs/rest/quickstart
- Docs index for LLMs: https://massive.com/docs/llms.txt
- Pricing: https://massive.com/pricing
- Request limits and the 429 message: https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis
- Extended-hours coverage: https://massive.com/knowledge-base/article/market-data-outside-of-normal-hours
- Display licensing: https://massive.com/knowledge-base/article/which-plan-do-i-need-to-show-massive-data-in-my-app
- Python client source and examples: https://github.com/massive-com/client-python (`massive/rest/snapshot.py`, `aggs.py`, `base.py`, `__init__.py`, `examples/rest/stocks-*.py`)
