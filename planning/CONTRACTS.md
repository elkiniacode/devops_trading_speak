# FinAlly Build Contract

This is the binding contract for the agent team building FinAlly. It turns PLAN.md's open questions (§13, R1–R38, S1–S9) and REVIEW.md into concrete decisions, exact payloads, internal Python signatures, test IDs and file ownership.

- **Where documents disagree:** this doc > `MARKET_INTERFACE.md` / `MARKET_SIMULATOR.md` > PLAN.md §1–12 > PLAN.md §13 suggestions.
- **If something you need is missing or wrong here:** message the lead (`team-lead`). Don't invent a different contract. The lead updates this doc and tells everyone affected.

---

## 1. Team and File Ownership

**Only edit files you own.** If you need a change in someone else's file, message its owner with the exact change.

| Teammate | Owns |
|---|---|
| **frontend** (Frontend Engineer) | `frontend/**` |
| **backend** (Backend API Engineer) | `backend/app/main.py`, `config.py`, `context.py`, `api/__init__.py`, `api/health.py`, `api/portfolio.py`, `api/watchlist.py`, `services/**`, `market/**`; `backend/tests/{api,services,market}/**`; `backend/tests/conftest.py` |
| **database** (Database Engineer) | `backend/app/db/**`, `backend/tests/db/**` |
| **llm** (LLM Engineer) | `backend/app/llm/**`, `backend/app/api/chat.py`, `backend/tests/llm/**` |
| **tester** (Integration Tester) | `test/**` (Playwright project, `docker-compose.test.yml`, E2E reports) |
| **devops** (DevOps Engineer) | `Dockerfile`, `.dockerignore`, `scripts/**`, `.env.example`, `.gitignore`, `README.md`, `db/.gitkeep` |
| **lead** | `planning/**`, `backend/pyproject.toml`, `backend/uv.lock`, `CLAUDE.md`, `memory/**` |

### Rules for everyone

- **Never write to `memory/`.** Every file written there starts a billed automated review. Only the lead writes there, once, at the end.
- **Dependencies:** `backend/pyproject.toml` is lead-owned. If you need a Python package, message the lead.
  - Installed now: `fastapi`, `uvicorn[standard]`, `httpx`, `tzdata`, `python-dotenv`, `litellm`, `pydantic`, plus `pytest` and `pytest-asyncio` (dev).
  - Run backend commands from `backend/`: `uv run pytest`, `uv run uvicorn app.main:app --port 8001`.
- **Environment:** Windows 11, PowerShell 5.1 plus Git Bash, Python 3.12 via uv, Node 25 / npm 11.
  - Docker is installed, but the engine may not be running; ask the lead if you need it.
  - Use absolute paths. Don't kill processes you didn't start.
- **Ports.** Use only your assigned port, to avoid collisions:

  | Port | Who |
  |---|---|
  | 8000 | the user's own dev server (README default); no agent uses it |
  | 8003 | tester (local E2E runs) |
  | 8001 | backend |
  | 8002 | llm |
  | 3000 | frontend dev server, pointed at 8001 |
  | 8080 | devops (container testing) |

- **Databases:** never use `db/finally.db` while developing. Set `DB_PATH` to your own file (e.g. `db/dev-backend.db`). Unit tests use pytest's `tmp_path`.
- **Unit tests are part of your job.** Run them before you report done.
- **Reporting:** when you finish a milestone, message the lead with a short summary of what changed, the test results and anything left open. Message other teammates directly when a contract between you matters.

---

## 2. Decisions

| Item | Decision |
|---|---|
| R2/S2 | Initialize the DB at startup, in the FastAPI lifespan. No lazy init. |
| R3 | `OPENROUTER_API_KEY` is optional. Without it, and without `LLM_MOCK=true`, the app runs normally and `/api/chat` returns 503. |
| R5 | Docker build stage uses `node:24-slim`; runtime stage uses `python:3.12-slim`. |
| R6/S1 | No root `docker-compose.yml`. The only compose file is `test/docker-compose.test.yml`. |
| R8 | Watchlist add/remove are idempotent (200). A trade returns the trade plus the updated portfolio. History is ascending with `?limit`. |
| R9 | Tracked tickers = watchlist ∪ open positions (`MARKET_INTERFACE.md` §8.2). |
| R10–R16 | Implemented exactly as in `MARKET_INTERFACE.md` and `MARKET_SIMULATOR.md`. The code is already in `backend/app/market/` (14 tests pass). |
| R17 | The frontend values the portfolio live from SSE prices. `/api/portfolio` also returns server-side values at request time. |
| R18 | Unrealized P&L = `(price − avg_cost) × qty`. P&L % = `(price − avg_cost) / avg_cost × 100`. Total P&L = `total_value − 10000`. `avg_cost` is a weighted average on buys and unchanged on sells. Realized P&L isn't tracked. |
| R19 / REVIEW #3 | Fractional shares are allowed, with at most 4 decimal places. Order value = `round(qty × price, 2)` and must be ≥ $0.01. Cash is rounded to cents after every trade. Overselling is rejected, not clamped. A position is deleted when its quantity reaches 0. Each trade is one DB transaction. |
| R20 | Single uvicorn worker. Every trade, manual or LLM, runs under one `asyncio.Lock`. |
| R21 | A $10,000 snapshot is recorded when the DB is created. Then one every 30 s and one after each trade. |
| R22–R26 | One LLM call per message. `trades` and `watchlist_changes` are **required** arrays. Watchlist changes run before trades. Per-action results are returned and stored. History = last 20 messages. Parse failure: retry once, then 502. |
| R24 | `GET /api/chat/history` exists. |
| R27 | Mock rules are fixed in §7.3. |
| R28 | The main chart uses the frontend's per-ticker buffer since page load, capped at 1,000 points. Empty after reload is accepted. |
| R29 / REVIEW #5 | Refetch portfolio, watchlist and history after every trade, watchlist change or chat reply that has actions. Also poll `/api/portfolio/history` every 30 s. |
| R30 | Heatmap color = P&L % clamped to ±5%, red → neutral gray → green. No cash tile. With no positions, show "No positions yet". |
| R31 | Clicking a watchlist ticker selects it for the main chart **and** pre-fills the trade bar's ticker field. Trade results appear as an inline message under the trade bar. Fractional quantities are allowed. |
| R32 | `NEXT_PUBLIC_API_BASE` (default `""` = same origin) for development. The backend enables CORS only when `CORS_ORIGINS` is set. |
| R33 | The container uses `/app/backend` for code and `/app/db` for data. `DB_PATH` comes from the environment (default `<repo>/db/finally.db`). The DB code lives at `backend/app/db/`, a package with no collision. |
| R34 | Start scripts create `.env` from `.env.example` when it's missing, and warn. The backend loads `<repo>/.env` with python-dotenv. `.env` is never baked into the image. |
| R36 | E2E runs use a fresh DB, `LLM_MOCK=true` and `SIM_SEED=42`. Color assertions check that each tile's color matches the sign of its P&L, not exact values. |
| R37 | The Docker `HEALTHCHECK` uses `python -c "import urllib.request ..."`. |
| R38 / REVIEW | Local only: bind to `127.0.0.1:8000`. Public deployment is out of scope. |
| S4 | Lightweight Charts for the main chart and the P&L chart. SVG `<polyline>` sparklines. Heatmap divs laid out with `d3-hierarchy`'s `treemap`. |
| S8 | Fractional shares stay. |
| S9 | Unit-test the connection indicator. The tester's reconnect E2E loads the app through an in-test TCP relay, cuts the live stream there and uses `context.setOffline` to keep reconnects failing until back online. `setOffline` alone doesn't interrupt an already-open EventSource in Chromium. Never kill the server. |
| Out of scope | Request idempotency keys (REVIEW #2), auth, cloud deployment, realized P&L. |

---

## 3. Backend Layout and Internal Interfaces

```
backend/
├── pyproject.toml, uv.lock          (lead)
├── app/
│   ├── __init__.py
│   ├── main.py        (backend)   create app, lifespan, include routers, CORS, static mount LAST
│   ├── config.py      (backend)   load <repo>/.env, read env vars (§8)
│   ├── context.py     (backend)   AppContext
│   ├── api/           (backend: health, portfolio, watchlist; llm: chat.py)
│   ├── services/      (backend)   trading.py, watchlist.py, portfolio.py, snapshots.py
│   ├── market/        (backend)   DONE; see MARKET_INTERFACE.md
│   ├── db/            (database)
│   └── llm/           (llm)
└── tests/{api,services,market,db,llm}/
```

### 3.1 `app/context.py` (backend)

```python
@dataclass
class AppContext:
    cache: PriceCache            # app.market.PriceCache
    market: MarketDataSource     # app.market.MarketDataSource
    trade_lock: asyncio.Lock

# main.py sets app.state.ctx = AppContext(...) in the lifespan.
def get_ctx(request: Request) -> AppContext: return request.app.state.ctx   # FastAPI dependency
```

### 3.2 `app/db` (database)

Use stdlib `sqlite3`, synchronous. Calls are sub-millisecond, so calling them from async code is fine. Every function opens a short connection (or uses a module connection) and commits its own transaction. Turn on WAL mode and `foreign_keys`.

```python
def init_db(path: str | Path) -> None
    # Remember `path`; create the parent directory, the schema (§6) and PRAGMA user_version = 1.
    # If users_profile has no 'default' row: insert it ($10,000), seed the 10 default watchlist
    # tickers and record one $10,000 snapshot. Idempotent: never reseeds an existing DB.

def close_db() -> None                            # optional: lifespan shutdown / test teardown
def get_cash() -> float
def get_watchlist() -> list[dict]                 # [{"ticker", "added_at"}], ordered by added_at, ticker
def add_watchlist_ticker(ticker: str) -> bool     # True if newly added
def remove_watchlist_ticker(ticker: str) -> bool  # True if it was present
def get_positions() -> list[dict]                 # [{"ticker", "quantity", "avg_cost", "updated_at"}], ordered by ticker
def get_position(ticker: str) -> dict | None
def tracked_tickers() -> list[str]                # sorted(watchlist ∪ positions)
def apply_trade(ticker: str, side: str, quantity: float, price: float) -> dict
    # ONE transaction (BEGIN IMMEDIATE). Rules in §2 R19. Returns the trade object (§5.4).
    # Raises InsufficientCashError / InsufficientSharesError / TradeRejected (value < $0.01).
def get_trades(limit: int = 50) -> list[dict]     # newest first
def record_snapshot(total_value: float) -> dict   # {"total_value", "recorded_at"}
def get_snapshots(limit: int = 500) -> list[dict] # the most recent `limit`, returned oldest -> newest
def add_chat_message(role: str, content: str, actions: dict | None) -> dict   # §5.6 message object
def get_chat_messages(limit: int = 50) -> list[dict]                           # most recent `limit`, oldest -> newest
def load_price_marks() -> dict[str, float]
def save_price_marks(prices: Mapping[str, float]) -> None                      # upsert

# app/db/errors.py, re-exported from app.db
class TradeRejected(ValueError)                    # str(exc) is shown to users
class InsufficientCashError(TradeRejected)         # "Insufficient cash: need $1,901.20, have $500.00"
class InsufficientSharesError(TradeRejected)       # "Insufficient shares: you have 2 AAPL, tried to sell 5"
```

Timestamps are stored and returned as ISO-8601 UTC with milliseconds and a `Z` (use `app.market.models.iso_utc(time.time())`), so they sort correctly as strings. IDs are `uuid4` strings.

### 3.3 `app/services` (backend)

The REST routes **and** the LLM call these. No other code path may change trades or the watchlist.

```python
# trading.py
async def execute_trade(ctx, ticker: str, side: str, quantity: float) -> dict
    # normalize_ticker -> validate side in {buy, sell}, 0 < quantity <= 1_000_000 with <= 4 dp
    # -> await ctx.market.add_ticker(t) -> async with ctx.trade_lock:
    #    quote = ctx.cache.get_fresh(t, ctx.market.max_quote_age) (None -> TradeRejected "No current price for X")
    #    trade = db.apply_trade(...) -> db.record_snapshot(total_value(ctx))
    # -> if no position and not on watchlist: await ctx.market.remove_ticker(t)  (also when rejected)
    # Returns the trade object (§5.4). Raises ValueError subclasses with user-facing messages.

# watchlist.py
async def add_to_watchlist(ctx, ticker: str) -> str        # normalize -> market.add_ticker -> db add; returns the ticker
async def remove_from_watchlist(ctx, ticker: str) -> str   # db remove -> untrack if not held; returns the ticker
def watchlist_view(ctx) -> list[dict]                      # §5.2 items

# portfolio.py
def portfolio_view(ctx) -> dict                            # §5.3 object
def total_value(ctx) -> float

# snapshots.py
async def snapshot_loop(ctx) -> None    # every 30 s: db.record_snapshot(total_value) + db.save_price_marks(cache prices)
```

All raise `ValueError` subclasses (including `UnknownTickerError` and `TradeRejected`) whose message is safe to show users. Routes map them to 400 `{"detail": str(exc)}`.

### 3.4 `app/llm` (llm)

`schemas.py` (Pydantic structured-output models), `prompt.py`, `client.py` (LiteLLM → OpenRouter → Cerebras via the `cerebras` skill; async through `litellm.acompletion` or `asyncio.to_thread`; 30 s timeout), `mock.py` (§7.3), `service.py`:

```python
async def handle_chat(ctx, message: str) -> dict
    # 1 store the user message  2 load the last 20 messages  3 build the prompt with portfolio_view(ctx),
    # watchlist_view(ctx), ctx.market.mode  4 call mock or real  5 validate the WHOLE response
    # (retry once on parse/validation failure, then raise LLMUnavailable -> 502)  6 run watchlist
    # changes, then trades, via app.services (catch ValueError per action -> status "failed")
    # 7 store the assistant message with its actions  8 return the §5.6 message object
```

`api/chat.py` defines `router` with `POST /api/chat` and `GET /api/chat/history`. backend's `main.py` includes it.

---

## 4. Conventions for Every Endpoint

- JSON keys are snake_case. Timestamps are ISO-8601 UTC strings like `"2026-10-19T14:03:12.500Z"`.
- Money values are rounded to 2 dp in responses, percentages to 2 dp, quantities to 4 dp. `avg_cost` is rounded to 4 dp.
- **Errors** use FastAPI's `{"detail": "..."}`:

  | Status | Meaning |
  |---|---|
  | 400 | Business-rule failure (bad ticker, unknown ticker, insufficient cash or shares, no price) |
  | 422 | Malformed body (FastAPI default) |
  | 404 | Unknown route. Unknown `/api/*` paths return JSON, not the static site. |
  | 502 | LLM upstream failure |
  | 503 | LLM not configured |

- All routes are under `/api`. The static frontend is mounted at `/` **after** all routers (`StaticFiles(directory=STATIC_DIR, html=True)`, only if the directory exists).

---

## 5. REST API

### 5.1 `GET /api/health`

```json
{"status": "ok", "market_data": "simulator", "llm": "mock"}
```

- `market_data`: `simulator` | `massive-snapshot` | `massive-eod`
- `llm`: `mock` | `openrouter` | `unconfigured`

### 5.2 Watchlist

`GET /api/watchlist` returns:

```json
{"watchlist": [
  {"ticker": "AAPL", "added_at": "2026-10-19T14:00:00.000Z",
   "quote": {"ticker": "AAPL", "price": 190.12, "previous_price": 190.05, "reference_price": 189.5,
             "change": 0.62, "change_percent": 0.33, "direction": "up", "timestamp": "2026-10-19T14:03:12.500Z"}}
]}
```

`quote` is `PriceUpdate.to_dict()`, or `null` if the ticker isn't priced yet.

- **`POST /api/watchlist`** takes `{"ticker": "pypl"}` and returns 200 with the full `GET` body. It's idempotent. A bad format or unknown ticker returns 400.
- **`DELETE /api/watchlist/{ticker}`** returns 200 with the full `GET` body. It's idempotent.

### 5.3 `GET /api/portfolio`

```json
{
  "cash_balance": 8098.8,
  "positions": [
    {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 190.12, "current_price": 191.2,
     "market_value": 1912.0, "unrealized_pnl": 10.8, "unrealized_pnl_percent": 0.57, "stale": false}
  ],
  "positions_value": 1912.0,
  "total_value": 10010.8,
  "total_pnl": 10.8,
  "total_pnl_percent": 0.11,
  "valuation_complete": true,
  "as_of": "2026-10-19T14:03:12.500Z"
}
```

- **Never priced:** `current_price`, `market_value` and the P&L fields are `null`. That position counts at `avg_cost` in the totals, and `valuation_complete` is `false`.
- **Older than `max_quote_age`:** the position is still valued, with `stale: true`.
- **Order:** positions are sorted by ticker.

### 5.4 `POST /api/portfolio/trade`

Request: `{"ticker": "AAPL", "quantity": 10, "side": "buy"}`

```json
{"trade": {"id": "6f1c…", "ticker": "AAPL", "side": "buy", "quantity": 10.0, "price": 190.12,
           "total": 1901.2, "executed_at": "2026-10-19T14:03:12.900Z"},
 "portfolio": { "...": "same object as GET /api/portfolio" }}
```

400 messages (exact wording may vary):
- `Invalid ticker symbol: 'A$'`
- `Unknown ticker: XYZQ`
- `Quantity must be greater than 0`
- `Quantity can have at most 4 decimal places`
- `Quantity can be at most 1,000,000`
- `Quantity must be a number`
- `Side must be 'buy' or 'sell'` (case-insensitive)
- `No current price for AAPL; try again shortly`
- `Insufficient cash: need $1,901.20, have $500.00`
- `Insufficient shares: you have 2 AAPL, tried to sell 5`
- `Order value must be at least $0.01`

### 5.5 `GET /api/portfolio/history?limit=500`

`limit` defaults to 500. Values outside 1–5,000 return 422; they aren't clamped.

```json
{"snapshots": [{"total_value": 10000.0, "recorded_at": "2026-10-19T14:00:00.000Z"}]}
```

The list is the most recent `limit` snapshots, oldest first.

### 5.6 Chat

**`POST /api/chat`** takes `{"message": "Buy 5 AAPL and add PYPL"}`. The message must be 1–2,000 characters after trimming, otherwise 400.

```json
{"id": "9a2e…", "role": "assistant",
 "content": "Adding PYPL to your watchlist and placing a buy order for 5 AAPL.",
 "actions": {
   "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "ok", "error": null}],
   "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 5.0, "status": "ok", "price": 190.12, "error": null}]
 },
 "created_at": "2026-10-19T14:03:13.100Z"}
```

- A failed action has `"status": "failed"` and an `"error"` string; a failed trade has `"price": null`.
- `actions` is always present on assistant messages, with both arrays (possibly empty). It's `null` on user messages.
- **502** `{"detail": "The AI assistant is unavailable right now. Please try again."}`: nothing was executed, and the user message is still stored.
- **503** `{"detail": "AI chat is not configured: set OPENROUTER_API_KEY or LLM_MOCK=true"}`

**`GET /api/chat/history?limit=50`** returns `{"messages": [<message object>, ...]}`, oldest first. User messages have `role: "user"` and `actions: null`.

### 5.7 `GET /api/stream/prices` (SSE)

Exactly as `MARKET_INTERFACE.md` §9: unnamed events whose `data` is a map `{TICKER: PriceUpdate}` of every tracked ticker. The first event is sent immediately on connect, with keepalive comments every 15 s.

---

## 6. Database Schema (database)

```sql
CREATE TABLE IF NOT EXISTS users_profile (
  id TEXT PRIMARY KEY DEFAULT 'default',
  cash_balance REAL NOT NULL DEFAULT 10000.0,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watchlist (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  added_at TEXT NOT NULL, UNIQUE (user_id, ticker));
CREATE TABLE IF NOT EXISTS positions (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  quantity REAL NOT NULL, avg_cost REAL NOT NULL, updated_at TEXT NOT NULL, UNIQUE (user_id, ticker));
CREATE TABLE IF NOT EXISTS trades (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('buy', 'sell')), quantity REAL NOT NULL, price REAL NOT NULL,
  executed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default', total_value REAL NOT NULL,
  recorded_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_time ON portfolio_snapshots (user_id, recorded_at);
CREATE TABLE IF NOT EXISTS chat_messages (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL DEFAULT 'default',
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')), content TEXT NOT NULL,
  actions TEXT, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_chat_user_time ON chat_messages (user_id, created_at);
CREATE TABLE IF NOT EXISTS price_marks (
  ticker TEXT PRIMARY KEY, price REAL NOT NULL, updated_at TEXT NOT NULL);
```

- **Seed:** the profile `default` ($10,000); watchlist `AAPL GOOGL MSFT AMZN TSLA NVDA META JPM V NFLX`; one $10,000 snapshot.
- **Single user:** all queries use `user_id = 'default'` (a module constant).

---

## 7. LLM

### 7.1 Structured output, sent to the model

```json
{"message": "string",
 "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
 "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]}
```

- All three keys are required, and the arrays may be empty.
- `side` is `buy` or `sell`; `action` is `add` or `remove`; `quantity` must be a number.
- **Validate the whole response's structure before executing anything:** keys, types, enums, a non-empty message, and at most 10 trades and 10 watchlist changes. A structural failure gets one retry, then 502.
- **Business rules are checked per action by the services** and fail only that action, with an inline ✗. These include quantity > 0, at most 4 dp, ticker format, cash and shares. For example, "buy 0 AAPL" gives a failed trade, not a 502.

### 7.2 Prompt

- The system prompt presents the model as "FinAlly, an AI trading assistant" and follows PLAN §9's guidance.
- **Describe trades as intent** ("Placing a buy order for 10 AAPL"), never in the past tense.
- **Put fresh context in each request:** cash, positions with P&L, watchlist prices with change %, total value, and market mode. If the mode is `massive-eod`, prices are end-of-day closes.
- **Include stored action results in history**, so the model learns about failures.
- **Ask clarifying questions** instead of guessing when the user is ambiguous.
- **Execute only what the user asked for or agreed to.**

### 7.3 Mock mode (`LLM_MOCK=true`): deterministic, no network

Keywords are case-insensitive. **Tickers must be written in uppercase** in the user's message. Every match in the message is applied: all watchlist changes first, then all trades, each in message order.

| Pattern (regex, keyword case-insensitive) | Action |
|---|---|
| `\bbuy\s+(\d+(?:\.\d+)?)\s+([A-Z]{1,5}(?:\.[A-Z])?)\b` | trade: buy qty ticker |
| `\bsell\s+(\d+(?:\.\d+)?)\s+([A-Z]{1,5}(?:\.[A-Z])?)\b` | trade: sell qty ticker |
| `\badd\s+([A-Z]{1,5}(?:\.[A-Z])?)\b` | watchlist add |
| `\bremove\s+([A-Z]{1,5}(?:\.[A-Z])?)\b` | watchlist remove |

The reply `message`:

- **For actions:** join phrases in order:
  - "Adding PYPL to your watchlist."
  - "Removing PYPL from your watchlist."
  - "Placing a buy order for 5 AAPL."
  - "Placing a sell order for 5 AAPL."
- **For no match:** exactly `I'm FinAlly, running in mock mode. Try "buy 1 AAPL", "sell 1 AAPL", "add PYPL" or "remove PYPL".`

The mock goes through the same validation and execution path as the real LLM.

---

## 8. Environment Variables (read in `app/config.py`, except where noted)

| Variable | Default | Notes |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Optional (R3) |
| `LLM_MOCK` | `false` | `true` = deterministic mock |
| `MASSIVE_API_KEY` | — | Read by `app.market.factory` |
| `MASSIVE_POLL_SECONDS` | `15` | Read by `app.market.factory` |
| `SIM_SEED` | — | Read by `app.market.factory` |
| `DB_PATH` | `<repo>/db/finally.db` | `/app/db/finally.db` in Docker |
| `STATIC_DIR` | `<repo>/backend/static` | Docker copies `frontend/out` here. Local E2E: `<repo>/frontend/out` |
| `CORS_ORIGINS` | — | e.g. `http://localhost:3000`; CORS is enabled only when set |

`config.py` calls `load_dotenv(<repo>/.env)` (without overriding variables that are already set) **before** the market factory runs.

---

## 9. Frontend (frontend)

- **Stack:**
  - Next.js (App Router, TypeScript) with `output: 'export'` and `images: { unoptimized: true }`. The build goes to `frontend/out/`.
  - Tailwind with a custom dark theme (PLAN §2 colors).
  - `lightweight-charts`, `d3-hierarchy`.
  - Vitest with React Testing Library.
  - Scripts: `npm run dev`, `npm run build`, `npm test`.
- **API base:** `process.env.NEXT_PUBLIC_API_BASE ?? ""`. EventSource is pointed at `${base}/api/stream/prices`.
- **Live valuation (R17):** `cash + Σ qty × live SSE price`. Fall back to the REST `current_price`, then `avg_cost` (flagged).
- **Price flash:** add class `flash-up` or `flash-down` on change and remove it after about 500 ms (CSS transition).
- **Sparklines and main chart:** buffer per ticker, capped at 1,000 points. Main chart uses 1 s buckets.
- **Labels:**
  - Watchlist change %: "Chg %". In `simulator` mode, add a tooltip: "since session start".
  - Positions table: "P&L %".
  - Header badge from `/api/health`: `SIM` / `DELAYED` (massive-snapshot) / `EOD`.

### 9.1 `data-testid` contract (the tester depends on these; don't rename)

| Element | testid | Extra attributes / content |
|---|---|---|
| Header total value | `header-total-value` | text like `$10,000.00` |
| Header cash | `header-cash` | text like `$10,000.00` |
| Connection dot | `connection-status` | `data-status="connected\|reconnecting\|disconnected"` |
| Watchlist container | `watchlist` | |
| Watchlist row | `watchlist-row-{TICKER}` | `data-direction="up\|down\|flat"` |
| Row price | `watchlist-price-{TICKER}` | |
| Row change % | `watchlist-change-{TICKER}` | |
| Row sparkline | `sparkline-{TICKER}` | `data-points="N"` |
| Row remove button | `watchlist-remove-{TICKER}` | |
| Add-ticker input / button | `watchlist-add-input` / `watchlist-add-button` | |
| Watchlist error | `watchlist-error` | |
| Main chart | `main-chart` | `data-ticker="AAPL"` |
| Trade inputs | `trade-ticker-input`, `trade-quantity-input` | |
| Trade buttons | `trade-buy-button`, `trade-sell-button` | |
| Trade result | `trade-message` | `data-status="success\|error"` |
| Positions table | `positions-table` | |
| Position row | `position-row-{TICKER}` | cells `position-qty-{T}`, `position-avg-cost-{T}`, `position-price-{T}`, `position-pnl-{T}`, `position-pnl-percent-{T}` |
| Heatmap | `heatmap` | `heatmap-empty` when there are no positions |
| Heatmap tile | `heatmap-tile-{TICKER}` | `data-pnl-sign="positive\|negative\|zero"` |
| P&L chart | `pnl-chart` | `data-points="N"` |
| Chat panel / toggle | `chat-panel` / `chat-toggle` | |
| Chat input / send | `chat-input` / `chat-send-button` | |
| Chat message | `chat-message` | `data-role="user\|assistant"` |
| Chat action line | `chat-action` | `data-status="ok\|failed"`, `data-kind="trade\|watchlist"` |
| Chat loading / error | `chat-loading` / `chat-error` | |

---

## 10. Docker and Scripts (devops)

### Dockerfile

- **Stage 1 (`node:24-slim`):** `npm ci && npm run build` in `/build/frontend`, producing `out/`.
- **Stage 2 (`python:3.12-slim`):**
  - Get uv with `COPY --from=ghcr.io/astral-sh/uv:<pinned> /uv /uvx /bin/`.
  - Set `WORKDIR /app/backend`. Copy `pyproject.toml` and `uv.lock`, then run `uv sync --frozen --no-dev`.
  - Copy `backend/app`, then copy the stage 1 `out/` into `/app/backend/static`.
  - Set `ENV DB_PATH=/app/db/finally.db STATIC_DIR=/app/backend/static`.
  - `EXPOSE 8000`, add the Python `HEALTHCHECK`.
  - `CMD ["/app/backend/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "3"]` (one worker). Open SSE streams never end on their own, so without the timeout the shutdown cleanup (saving price marks, stopping the market source) never runs.

### Run command

```
docker run -d --name finally --stop-timeout 10 -v finally-data:/app/db -p 127.0.0.1:8000:8000 --env-file .env finally
```

`--stop-timeout 10` (and `docker stop -t 10`) is needed because this Docker install defaults containers to a 1 s stop timeout, which kills the app mid-shutdown.

### Scripts

- `start_mac.sh` / `stop_mac.sh` / `start_windows.ps1` / `stop_windows.ps1`
- All are idempotent.
- `--build` (or `-Build`) forces a rebuild.
- If `.env` is missing, copy it from `.env.example` and warn.
- Print the URL and optionally open the browser.
- Stopping never removes the volume.

### Other files

- `.env.example`: every variable in §8 with comments. `LLM_MOCK=false`. `OPENROUTER_API_KEY=` empty.
- `.gitignore` (R35).
- `README.md`: quick start, environment setup, tests.

---

## 11. E2E (tester)

- **Location:** `test/`, a Playwright TypeScript project (`package.json`, `playwright.config.ts`, `tests/*.spec.ts`).
  - `baseURL` comes from the `BASE_URL` env var (default `http://localhost:8000`).
  - Use `data-testid` selectors (§9.1).
- **Local run:**
  1. Build the frontend (`npm run build` in `frontend/`).
  2. Start the backend on port 8003 with `LLM_MOCK=true`, `SIM_SEED=42`, `DB_PATH=<temp file>` and `STATIC_DIR=<repo>/frontend/out`. Delete the temp DB before each run.
  3. Run `npx playwright test`.
- **Docker run:** `test/docker-compose.test.yml` runs the app (built from the root Dockerfile, no volume, `LLM_MOCK=true`, `SIM_SEED=42`) plus a `mcr.microsoft.com/playwright` container with `BASE_URL=http://app:8000`.
- **Scenarios:**
  - Fresh start: 10 tickers, $10,000, prices streaming.
  - Watchlist add and remove.
  - Buy.
  - Sell.
  - Heatmap tile color sign matches P&L, and the P&L chart has points.
  - Mock chat: trade and watchlist action shown inline.
  - SSE reconnect via an in-test relay plus `context.setOffline` (see S9).
  - Error paths: insufficient cash, unknown ticker.
- **Isolation:** tests must not depend on each other's state. Use fresh state or relative assertions.
- **Reporting bugs:** message the **owner** (§1) with the scenario, the expected and actual result, and the test file. Send the lead a summary. Re-run after a fix.
