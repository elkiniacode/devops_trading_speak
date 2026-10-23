# FinAlly — AI Trading Workstation

## Project Specification

## 1. Vision

FinAlly (Finance Ally) is a visually stunning AI-powered trading workstation that streams live market data, lets users trade a simulated portfolio, and integrates an LLM chat assistant that can analyze positions and execute trades on the user's behalf. It looks and feels like a modern Bloomberg terminal with an AI copilot.

This is the capstone project for an agentic AI coding course. It is built entirely by Coding Agents demonstrating how orchestrated AI agents can produce a production-quality full-stack application. Agents interact through files in `planning/`.

## 2. User Experience

### First Launch

The user runs a single Docker command (or a provided start script). A browser opens to `http://localhost:8000`. No login, no signup. They immediately see:

- A watchlist of 10 default tickers with live-updating prices in a grid
- $10,000 in virtual cash
- A dark, data-rich trading terminal aesthetic
- An AI chat panel ready to assist

### What the User Can Do

- **Watch prices stream** — prices flash green (uptick) or red (downtick) with subtle CSS animations that fade
- **View sparkline mini-charts** — price action beside each ticker in the watchlist, accumulated on the frontend from the SSE stream since page load (sparklines fill in progressively)
- **Click a ticker** to see a larger detailed chart in the main chart area
- **Buy and sell shares** — market orders only, instant fill at current price, no fees, no confirmation dialog
- **Monitor their portfolio** — a heatmap (treemap) showing positions sized by weight and colored by P&L, plus a P&L chart tracking total portfolio value over time
- **View a positions table** — ticker, quantity, average cost, current price, unrealized P&L, % change
- **Chat with the AI assistant** — ask about their portfolio, get analysis, and have the AI execute trades and manage the watchlist through natural language
- **Manage the watchlist** — add/remove tickers manually or via the AI chat

### Visual Design

- **Dark theme**: backgrounds around `#0d1117` or `#1a1a2e`, muted gray borders, no pure black
- **Price flash animations**: brief green/red background highlight on price change, fading over ~500ms via CSS transitions
- **Connection status indicator**: a small colored dot (green = connected, yellow = reconnecting, red = disconnected) visible in the header
- **Professional, data-dense layout**: inspired by Bloomberg/trading terminals — every pixel earns its place
- **Responsive but desktop-first**: optimized for wide screens, functional on tablet

### Color Scheme
- Accent Yellow: `#ecad0a`
- Blue Primary: `#209dd7`
- Purple Secondary: `#753991` (submit buttons)

## 3. Architecture Overview

### Single Container, Single Port

```
┌─────────────────────────────────────────────────┐
│  Docker Container (port 8000)                   │
│                                                 │
│  FastAPI (Python/uv)                            │
│  ├── /api/*          REST endpoints             │
│  ├── /api/stream/*   SSE streaming              │
│  └── /*              Static file serving         │
│                      (Next.js export)            │
│                                                 │
│  SQLite database (volume-mounted)               │
│  Background task: market data polling/sim        │
└─────────────────────────────────────────────────┘
```

- **Frontend**: Next.js with TypeScript, built as a static export (`output: 'export'`), served by FastAPI as static files
- **Backend**: FastAPI (Python), managed as a `uv` project
- **Database**: SQLite, single file at `db/finally.db`, volume-mounted for persistence
- **Real-time data**: Server-Sent Events (SSE) — simpler than WebSockets, one-way server→client push, works everywhere
- **AI integration**: LiteLLM → OpenRouter (Cerebras for fast inference), with structured outputs for trade execution
- **Market data**: Environment-variable driven — simulator by default, real data via Massive API if key provided

### Why These Choices

| Decision | Rationale |
|---|---|
| SSE over WebSockets | One-way push is all we need; simpler, no bidirectional complexity, universal browser support |
| Static Next.js export | Single origin, no CORS issues, one port, one container, simple deployment |
| SQLite over Postgres | No auth = no multi-user = no need for a database server; self-contained, zero config |
| Single Docker container | Students run one command; no docker-compose for production, no service orchestration |
| uv for Python | Fast, modern Python project management; reproducible lockfile; what students should learn |
| Market orders only | Eliminates order book, limit order logic, partial fills — dramatically simpler portfolio math |

---

## 4. Directory Structure

```
finally/
├── frontend/                 # Next.js TypeScript project (static export)
├── backend/                  # FastAPI uv project (Python)
│   └── db/                   # Schema definitions, seed data, migration logic
├── planning/                 # Project-wide documentation for agents
│   ├── PLAN.md               # This document
│   └── ...                   # Additional agent reference docs
├── scripts/
│   ├── start_mac.sh          # Launch Docker container (macOS/Linux)
│   ├── stop_mac.sh           # Stop Docker container (macOS/Linux)
│   ├── start_windows.ps1     # Launch Docker container (Windows PowerShell)
│   └── stop_windows.ps1      # Stop Docker container (Windows PowerShell)
├── test/                     # Playwright E2E tests + docker-compose.test.yml
├── db/                       # Volume mount target (SQLite file lives here at runtime)
│   └── .gitkeep              # Directory exists in repo; finally.db is gitignored
├── Dockerfile                # Multi-stage build (Node → Python)
├── docker-compose.yml        # Optional convenience wrapper
├── .env                      # Environment variables (gitignored, .env.example committed)
└── .gitignore
```

### Key Boundaries

- **`frontend/`** is a self-contained Next.js project. It knows nothing about Python. It talks to the backend via `/api/*` endpoints and `/api/stream/*` SSE endpoints. Internal structure is up to the Frontend Engineer agent.
- **`backend/`** is a self-contained uv project with its own `pyproject.toml`. It owns all server logic including database initialization, schema, seed data, API routes, SSE streaming, market data, and LLM integration. Internal structure is up to the Backend/Market Data agents.
- **`backend/db/`** contains schema SQL definitions and seed logic. The backend lazily initializes the database on first request — creating tables and seeding default data if the SQLite file doesn't exist or is empty.
- **`db/`** at the top level is the runtime volume mount point. The SQLite file (`db/finally.db`) is created here by the backend and persists across container restarts via Docker volume.
- **`planning/`** contains project-wide documentation, including this plan. All agents reference files here as the shared contract.
- **`test/`** contains Playwright E2E tests and supporting infrastructure (e.g., `docker-compose.test.yml`). Unit tests live within `frontend/` and `backend/` respectively, following each framework's conventions.
- **`scripts/`** contains start/stop scripts that wrap Docker commands.

---

## 5. Environment Variables

```bash
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used (recommended for most users)
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing)
LLM_MOCK=false
```

### Behavior

- If `MASSIVE_API_KEY` is set and non-empty → backend uses Massive REST API for market data
- If `MASSIVE_API_KEY` is absent or empty → backend uses the built-in market simulator
- If `LLM_MOCK=true` → backend returns deterministic mock LLM responses (for E2E tests)
- The backend reads `.env` from the project root (mounted into the container or read via docker `--env-file`)

---

## 6. Market Data

### Two Implementations, One Interface

Both the simulator and the Massive client implement the same abstract interface. The backend selects which to use based on the environment variable. All downstream code (SSE streaming, price cache, frontend) is agnostic to the source.

### Simulator (Default)

- Generates prices using geometric Brownian motion (GBM) with configurable drift and volatility per ticker
- Updates at ~500ms intervals
- Correlated moves across tickers (e.g., tech stocks move together)
- Occasional random "events" — sudden 2-5% moves on a ticker for drama
- Starts from realistic seed prices (e.g., AAPL ~$190, GOOGL ~$175, etc.)
- Runs as an in-process background task — no external dependencies

### Massive API (Optional)

- REST API polling (not WebSocket) — simpler, works on all tiers
- Polls for the union of all watched tickers on a configurable interval
- Free tier (5 calls/min): poll every 15 seconds
- Paid tiers: poll every 2-15 seconds depending on tier
- Parses REST response into the same format as the simulator

### Shared Price Cache

- A single background task (simulator or Massive poller) writes to an in-memory price cache
- The cache holds the latest price, previous price, and timestamp for each ticker
- SSE streams read from this cache and push updates to connected clients
- This architecture supports future multi-user scenarios without changes to the data layer

### SSE Streaming

- Endpoint: `GET /api/stream/prices`
- Long-lived SSE connection; client uses native `EventSource` API
- Server pushes price updates for all tickers known to the system at a regular cadence (~500ms) — in the single-user model this is equivalent to the user's watchlist
- Each SSE event contains ticker, price, previous price, timestamp, and change direction
- Client handles reconnection automatically (EventSource has built-in retry)

---

## 7. Database

### SQLite with Lazy Initialization

The backend checks for the SQLite database on startup (or first request). If the file doesn't exist or tables are missing, it creates the schema and seeds default data. This means:

- No separate migration step
- No manual database setup
- Fresh Docker volumes start with a clean, seeded database automatically

### Schema

All tables include a `user_id` column defaulting to `"default"`. This is hardcoded for now (single-user) but enables future multi-user support without schema migration.

**users_profile** — User state (cash balance)
- `id` TEXT PRIMARY KEY (default: `"default"`)
- `cash_balance` REAL (default: `10000.0`)
- `created_at` TEXT (ISO timestamp)

**watchlist** — Tickers the user is watching
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `added_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**positions** — Current holdings (one row per ticker per user)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `quantity` REAL (fractional shares supported)
- `avg_cost` REAL
- `updated_at` TEXT (ISO timestamp)
- UNIQUE constraint on `(user_id, ticker)`

**trades** — Trade history (append-only log)
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `ticker` TEXT
- `side` TEXT (`"buy"` or `"sell"`)
- `quantity` REAL (fractional shares supported)
- `price` REAL
- `executed_at` TEXT (ISO timestamp)

**portfolio_snapshots** — Portfolio value over time (for P&L chart). Recorded every 30 seconds by a background task, and immediately after each trade execution.
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `total_value` REAL
- `recorded_at` TEXT (ISO timestamp)

**chat_messages** — Conversation history with LLM
- `id` TEXT PRIMARY KEY (UUID)
- `user_id` TEXT (default: `"default"`)
- `role` TEXT (`"user"` or `"assistant"`)
- `content` TEXT
- `actions` TEXT (JSON — trades executed, watchlist changes made; null for user messages)
- `created_at` TEXT (ISO timestamp)

### Default Seed Data

- One user profile: `id="default"`, `cash_balance=10000.0`
- Ten watchlist entries: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX

---

## 8. API Endpoints

### Market Data
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/stream/prices` | SSE stream of live price updates |

### Portfolio
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/portfolio` | Current positions, cash balance, total value, unrealized P&L |
| POST | `/api/portfolio/trade` | Execute a trade: `{ticker, quantity, side}` |
| GET | `/api/portfolio/history` | Portfolio value snapshots over time (for P&L chart) |

### Watchlist
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/watchlist` | Current watchlist tickers with latest prices |
| POST | `/api/watchlist` | Add a ticker: `{ticker}` |
| DELETE | `/api/watchlist/{ticker}` | Remove a ticker |

### Chat
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Send a message, receive complete JSON response (message + executed actions) |

### System
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check (for Docker/deployment) |

---

## 9. LLM Integration

When writing code to make calls to LLMs, use cerebras-inference skill to use LiteLLM via OpenRouter to the `openrouter/openai/gpt-oss-120b` model with Cerebras as the inference provider. Structured Outputs should be used to interpret the results.

There is an OPENROUTER_API_KEY in the .env file in the project root.

### How It Works

When the user sends a chat message, the backend:

1. Loads the user's current portfolio context (cash, positions with P&L, watchlist with live prices, total portfolio value)
2. Loads recent conversation history from the `chat_messages` table
3. Constructs a prompt with a system message, portfolio context, conversation history, and the user's new message
4. Calls the LLM via LiteLLM → OpenRouter, requesting structured output, using the cerebras-inference skill
5. Parses the complete structured JSON response
6. Auto-executes any trades or watchlist changes specified in the response
7. Stores the message and executed actions in `chat_messages`
8. Returns the complete JSON response to the frontend (no token-by-token streaming — Cerebras inference is fast enough that a loading indicator is sufficient)

### Structured Output Schema

The LLM is instructed to respond with JSON matching this schema:

```json
{
  "message": "Your conversational response to the user",
  "trades": [
    {"ticker": "AAPL", "side": "buy", "quantity": 10}
  ],
  "watchlist_changes": [
    {"ticker": "PYPL", "action": "add"}
  ]
}
```

- `message` (required): The conversational text shown to the user
- `trades` (optional): Array of trades to auto-execute. Each trade goes through the same validation as manual trades (sufficient cash for buys, sufficient shares for sells)
- `watchlist_changes` (optional): Array of watchlist modifications

### Auto-Execution

Trades specified by the LLM execute automatically — no confirmation dialog. This is a deliberate design choice:
- It's a simulated environment with fake money, so the stakes are zero
- It creates an impressive, fluid demo experience
- It demonstrates agentic AI capabilities — the core theme of the course

If a trade fails validation (e.g., insufficient cash), the error is included in the chat response so the LLM can inform the user.

### System Prompt Guidance

The LLM should be prompted as "FinAlly, an AI trading assistant" with instructions to:
- Analyze portfolio composition, risk concentration, and P&L
- Suggest trades with reasoning
- Execute trades when the user asks or agrees
- Manage the watchlist proactively
- Be concise and data-driven in responses
- Always respond with valid structured JSON

### LLM Mock Mode

When `LLM_MOCK=true`, the backend returns deterministic mock responses instead of calling OpenRouter. This enables:
- Fast, free, reproducible E2E tests
- Development without an API key
- CI/CD pipelines

---

## 10. Frontend Design

### Layout

The frontend is a single-page application with a dense, terminal-inspired layout. The specific component architecture and layout system is up to the Frontend Engineer, but the UI should include these elements:

- **Watchlist panel** — grid/table of watched tickers with: ticker symbol, current price (flashing green/red on change), daily change %, and a sparkline mini-chart (accumulated from SSE since page load)
- **Main chart area** — larger chart for the currently selected ticker, with at minimum price over time. Clicking a ticker in the watchlist selects it here.
- **Portfolio heatmap** — treemap visualization where each rectangle is a position, sized by portfolio weight, colored by P&L (green = profit, red = loss)
- **P&L chart** — line chart showing total portfolio value over time, using data from `portfolio_snapshots`
- **Positions table** — tabular view of all positions: ticker, quantity, avg cost, current price, unrealized P&L, % change
- **Trade bar** — simple input area: ticker field, quantity field, buy button, sell button. Market orders, instant fill.
- **AI chat panel** — docked/collapsible sidebar. Message input, scrolling conversation history, loading indicator while waiting for LLM response. Trade executions and watchlist changes shown inline as confirmations.
- **Header** — portfolio total value (updating live), connection status indicator, cash balance

### Technical Notes

- Use `EventSource` for SSE connection to `/api/stream/prices`
- Canvas-based charting library preferred (Lightweight Charts or Recharts) for performance
- Price flash effect: on receiving a new price, briefly apply a CSS class with background color transition, then remove it
- All API calls go to the same origin (`/api/*`) — no CORS configuration needed
- Tailwind CSS for styling with a custom dark theme

---

## 11. Docker & Deployment

### Multi-Stage Dockerfile

```
Stage 1: Node 20 slim
  - Copy frontend/
  - npm install && npm run build (produces static export)

Stage 2: Python 3.12 slim
  - Install uv
  - Copy backend/
  - uv sync (install Python dependencies from lockfile)
  - Copy frontend build output into a static/ directory
  - Expose port 8000
  - CMD: uvicorn serving FastAPI app
```

FastAPI serves the static frontend files and all API routes on port 8000.

### Docker Volume

The SQLite database persists via a named Docker volume:

```bash
docker run -v finally-data:/app/db -p 8000:8000 --env-file .env finally
```

The `db/` directory in the project root maps to `/app/db` in the container. The backend writes `finally.db` to this path.

### Start/Stop Scripts

**`scripts/start_mac.sh`** (macOS/Linux):
- Builds the Docker image if not already built (or if `--build` flag passed)
- Runs the container with the volume mount, port mapping, and `.env` file
- Prints the URL to access the app
- Optionally opens the browser

**`scripts/stop_mac.sh`** (macOS/Linux):
- Stops and removes the running container
- Does NOT remove the volume (data persists)

**`scripts/start_windows.ps1`** / **`scripts/stop_windows.ps1`**: PowerShell equivalents for Windows.

All scripts should be idempotent — safe to run multiple times.

### Optional Cloud Deployment

The container is designed to deploy to AWS App Runner, Render, or any container platform. A Terraform configuration for App Runner may be provided in a `deploy/` directory as a stretch goal, but is not part of the core build.

---

## 12. Testing Strategy

### Unit Tests (within `frontend/` and `backend/`)

**Backend (pytest)**:
- Market data: simulator generates valid prices, GBM math is correct, Massive API response parsing works, both implementations conform to the abstract interface
- Portfolio: trade execution logic, P&L calculations, edge cases (selling more than owned, buying with insufficient cash, selling at a loss)
- LLM: structured output parsing handles all valid schemas, graceful handling of malformed responses, trade validation within chat flow
- API routes: correct status codes, response shapes, error handling

**Frontend (React Testing Library or similar)**:
- Component rendering with mock data
- Price flash animation triggers correctly on price changes
- Watchlist CRUD operations
- Portfolio display calculations
- Chat message rendering and loading state

### E2E Tests (in `test/`)

**Infrastructure**: A separate `docker-compose.test.yml` in `test/` that spins up the app container plus a Playwright container. This keeps browser dependencies out of the production image.

**Environment**: Tests run with `LLM_MOCK=true` by default for speed and determinism.

**Key Scenarios**:
- Fresh start: default watchlist appears, $10k balance shown, prices are streaming
- Add and remove a ticker from the watchlist
- Buy shares: cash decreases, position appears, portfolio updates
- Sell shares: cash increases, position updates or disappears
- Portfolio visualization: heatmap renders with correct colors, P&L chart has data points
- AI chat (mocked): send a message, receive a response, trade execution appears inline
- SSE resilience: disconnect and verify reconnection

---

## 13. Review: Questions, Clarifications & Feedback

*Reviewed 2026-10-18, before any code exists. Items are numbered so agents can cite them (e.g., "per R22"). Each one has a suggested resolution. Once a decision is made, fold it into the relevant section above and remove the item from here.*

### 13.1 Top Priorities

Resolve these first. They block parallel agent work or are likely to cause bugs:

1. **R7**: There are no exact JSON contracts for the API or SSE. The frontend and backend agents build in parallel, so this is the biggest integration risk.
2. **R22**: As written, the chat flow can't let the LLM report trade failures, because it makes a single LLM call.
3. **R9**: The set of tickers that receive prices (watchlist, positions or trade bar) isn't defined.
4. **R17**: Portfolio values that are "updating live" need a stated mechanism. `/api/portfolio` only returns a point-in-time snapshot.
5. **R11**: "Daily change %" has no reference price in the simulator.
6. **R33**: `backend/db/` collides with the `/app/db` volume mount in the container.

### 13.2 Inconsistencies in the Current Text

- **R1, charting library.** §10 says "Canvas-based charting library preferred (Lightweight Charts or Recharts)". Recharts renders SVG, not canvas, and Lightweight Charts has no treemap. See S4.
- **R2, DB init timing.** §4 says the database is initialized lazily on first request. §7 says "on startup (or first request)". Recommend startup only (S2).
- **R3, `OPENROUTER_API_KEY` is marked "Required".** Everything except chat works without it, and §9 says mock mode enables "development without an API key". Recommend making it optional. If the key is missing and `LLM_MOCK` isn't `true`, the app starts normally and `/api/chat` returns a clear "LLM not configured" error.
- **R4, trade-failure reporting.** §9 says failed-trade errors are passed back "so the LLM can inform the user". The LLM writes its message before any trade is validated, so it can't. See R22.
- **R5, Node 20 reached end-of-life in April 2026.** Use `node:22-slim` or `node:24-slim` (current LTS) for Stage 1.
- **R6, docker-compose.** §3 says "no docker-compose for production", but §4 lists an optional root `docker-compose.yml`. See S1.

### 13.3 API Contract

- **R7: add an "API Contract" section.** Give example request and response JSON for every endpoint, the SSE event and errors. Suggested conventions:
  - Use snake_case keys everywhere. This is the Python default, and the frontend adapts to it.
  - Write timestamps as ISO-8601 UTC strings, for example `2026-10-18T14:03:12.500Z`.
  - Errors use FastAPI's default `{"detail": "..."}`, with 400 for validation, 404 for not found and 502 for an LLM upstream failure.
  - Round money to 2 decimals in responses.
- **R8: endpoint details to decide.**
  - `POST /api/watchlist` for a ticker already on the list, and `DELETE` for one that isn't: recommend an idempotent `200` for both. This is simplest for LLM-driven changes.
  - `POST /api/portfolio/trade`: return the executed trade *and* the updated portfolio, so the frontend doesn't need to refetch.
  - `GET /api/portfolio/history`: ascending order, with an optional `?limit=`.
  - `GET /api/health`: return `{"status": "ok"}`.

### 13.4 Market Data & SSE

- **R9: which tickers get prices?** Recommend pricing every ticker that is on the watchlist or has an open position. Otherwise, removing a held ticker from the watchlist freezes its valuation. Reject a trade with a 400 when its ticker has no cached price.
- **R10: define the interface.** §6 says "one interface" but never defines it. Suggested methods are `start()`, `stop()`, `add_ticker(t)` and `remove_ticker(t)` on the source, and `get(t)` and `get_all()` on the cache. Each cache entry holds `price`, `previous_price`, `open_price` and `timestamp`.
- **R11: reference price for "daily change %".** The simulator has no trading day. Recommend that the cache store an `open_price` and that the SSE event include it. For the simulator this is its starting price; for Massive it is the previous close from the snapshot. If the frontend instead used the first price it received, the value would reset on every page reload.
- **R12: adding unknown tickers.**
  - Specify format validation, for example `^[A-Z]{1,5}$`.
  - The simulator needs a default seed price and volatility for symbols it doesn't know, for example a random price between $50 and $300.
  - Adding a ticker should put a price in the cache immediately, so it can be traded right away. This matters when the LLM adds and buys a ticker in one response.
  - With Massive, an invalid symbol only shows up on the next poll. Decide whether to remove it or show "no data".
- **R13: SSE payload.** Recommend one event per tick that carries a map of *all* priced tickers. Send it as soon as a client connects so the UI is never blank. For example:
  `data: {"AAPL": {"price": 190.12, "previous_price": 190.05, "open_price": 189.50, "timestamp": "..."}, ...}`
  With this format, newly added tickers appear without the client reconnecting.
- **R14: price jump after a restart.** On restart the simulator goes back to its seed prices. Positions that were bought at drifted prices then show a sudden P&L jump, and the P&L chart shows a step. A cheap fix is to start each held ticker from its most recent price in `trades`.
- **R15: volatility calibration.** Real-time GBM with an annual σ of 30% at 500 ms ticks moves about 0.01% per tick and about 0.3% over 10 minutes. That is realistic but calm. Decide whether the demo uses a speed-up multiplier and how often "events" fire. Make each of these a single constant.
- **R16: Massive free tier.** Confirm that the free tier includes intraday data and the multi-ticker snapshot endpoint, which needs only one call per poll. Polygon's free tier used to be limited to end-of-day data. If that's still true, prices won't move and the 15 s poll does nothing useful. Also define what happens while the market is closed.

### 13.5 Portfolio & Trades

- **R17: live valuation.** The header total, positions table and heatmap all update "live", but `/api/portfolio` only returns a REST snapshot. Recommend:
  - `/api/portfolio` supplies cash, quantities and average costs.
  - The frontend computes `cash + Σ quantity × live price` using SSE prices.
  - When a ticker has no cached price, it falls back to `avg_cost`.
  - The backend uses the same formula for snapshots and for the LLM context.
- **R18: metric definitions.**
  - Unrealized P&L is `(price − avg_cost) × quantity`.
  - The positions table's "% change" is `(price − avg_cost) / avg_cost`. Rename it "P&L %" so it isn't confused with the watchlist's daily change.
  - Total P&L is `total_value − 10,000`.
  - `avg_cost` is a weighted average on buys and stays the same on sells.
  - Realized P&L isn't tracked separately. Confirm that's acceptable.
- **R19: trade validation and rounding.**
  - Require `quantity > 0` and a side of `buy` or `sell`. Convert the ticker to uppercase.
  - Reject a sale of more shares than the user owns rather than clamping it.
  - Round quantities to, for example, 4 decimal places and cash to 2.
  - Delete the position row once its quantity drops below a tiny threshold, for example `1e-6`. Otherwise floating-point error leaves leftover positions like `0.0000000001`.
  - Run each trade in a single DB transaction.
- **R20: concurrency.** Run uvicorn with a **single worker**. With more workers, each one would run its own simulator, price cache and snapshot task. Chat trades and manual trades can overlap, so run trades one at a time; an `asyncio.Lock` is enough.
- **R21: snapshots.** Record one snapshot ($10,000) when the database is first created, so the P&L chart has a starting point on first load. At one snapshot every 30 s the table grows by 2,880 rows a day. That's fine for SQLite, but the history endpoint should support `?limit` or downsampling for databases that run for a long time.

### 13.6 LLM Chat

- **R22: reporting action results.** With a single LLM call, the message can't reflect whether trades succeeded. Recommend handling this without a second call:
  - Execute the actions, then return each action's result alongside the message.
  - The UI shows each result inline as ✓, or ✗ with the error.
  - Store the results in `actions` and include them in the next turn's history, so the LLM learns about failures.
  - Prompt the LLM to describe trades as intent ("Placing an order for 10 AAPL") rather than in the past tense.
- **R23: chat response shape.** Define it, and store the same `actions` object in `chat_messages.actions`. For example:
  ```json
  {"message": "Buying 10 AAPL and adding PYPL.",
   "actions": {
     "watchlist_changes": [{"ticker": "PYPL", "action": "add", "status": "ok"}],
     "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10, "price": 190.12,
                 "status": "failed", "error": "Insufficient cash"}]}}
  ```
- **R24: no way to load chat history.** After a page reload the chat panel is blank, even though the LLM still has the conversation in its history. Add `GET /api/chat/history`, returning the last N messages with their actions.
- **R25: schema and execution order.** Make `trades` and `watchlist_changes` **required** arrays that may be empty, not optional fields. Strict structured-output modes generally require every property, and parsing is simpler. Apply watchlist changes before trades so that a request like "add PYPL and buy 5" works.
- **R26: history size and error handling.** Specify N for the history, for example the last 20 messages. Also specify what happens on a timeout, malformed JSON or an upstream error. Suggested:
  - Retry once on a parse failure, then return a 502.
  - Execute nothing.
  - Still store the user's message.
  - Show an inline error in the UI.
- **R27: mock-mode contract.** The E2E agent needs fixed, documented mock behavior to test "trade execution appears inline". For example:
  - A message that contains "buy" buys 1 AAPL.
  - A message that contains "sell" sells 1 AAPL.
  - "add XYZ" adds XYZ to the watchlist.
  - Any other message gets a fixed reply with no actions.

  Put these rules in this plan.

### 13.7 Frontend

- **R28: main chart data source.** The plan doesn't say where the main chart's data comes from. Recommend reusing the sparkline buffer: per ticker, collected since page load and capped at, for example, 1,000 points. Either accept that the chart is empty after a reload, or add a backend endpoint that keeps recent prices, which is more work. Lightweight Charts doesn't officially support time steps shorter than one second, so 500 ms ticks need to be grouped into 1 s buckets.
- **R29: state refresh.** After a manual trade, a watchlist change or a chat response with actions, refetch `/api/portfolio`, `/api/watchlist` and `/api/portfolio/history`. No other polling is needed, since SSE drives prices.
- **R30: heatmap details.**
  - Define the color scale, for example P&L % clamped to ±5% and running red → neutral gray → green.
  - Decide whether cash appears as a tile. Recommend not.
  - Define what the heatmap shows when there are no positions.
- **R31: trade bar behavior.**
  - Should clicking a watchlist ticker pre-fill the trade bar? Recommend yes.
  - Specify how success and errors are shown, either as an inline message or a toast.
  - Specify whether the quantity input accepts fractions.
- **R32: development setup.** `next dev` (port 3000) and uvicorn (port 8000) are different origins, and Next `rewrites` aren't supported with `output: 'export'`. Recommend a `NEXT_PUBLIC_API_BASE` env var for development, plus CORS for `localhost:3000` that is turned on only in a dev mode. Production stays same-origin.

### 13.8 Docker, Deployment & Testing

- **R33: `/app/db` collision.** If the Dockerfile copies `backend/` to `/app`, the schema and seed code in `backend/db/` ends up at `/app/db`, which is also the volume mount point. Either the volume hides the code, or, because Docker fills an empty named volume from the image, the schema files get copied into the volume and are never updated on rebuild.
  - Fix: copy the backend to `/app/backend`, and read the DB path from an env var (`DB_PATH`, default `<repo root>/db/finally.db`).
  - Also consider renaming `backend/db/` so there aren't two different "db" directories.
- **R34: `.env` handling.** `docker run --env-file .env` fails if `.env` doesn't exist. The start scripts should copy `.env.example` to `.env` and print a warning. When running locally outside Docker, the backend loads the root `.env` with `python-dotenv`. Never bake `.env` into the image.
- **R35: repo housekeeping.** `.env.example` is mentioned but missing from the §4 directory tree. `.gitignore` is currently empty and needs `.env`, `db/*.db`, `node_modules/`, `.next/`, `out/`, `.venv/` and `__pycache__/`.
- **R36: E2E determinism.**
  - Tests change state (trades, watchlist), so `docker-compose.test.yml` should start each run with a fresh, throwaway DB, and tests shouldn't depend on running in a particular order.
  - Random prices mean the "heatmap renders with correct colors" result changes from run to run. Either add a `SIM_SEED` env var, or assert that each tile's color matches the sign of its displayed P&L.
- **R37: health check.** The slim Python image has no `curl`, so a Docker `HEALTHCHECK` should use `python -c "import urllib.request; ..."`.
- **R38: public deployment.** With no auth and the OpenRouter key on the server, anyone with the URL can trade and spend your credits. If the deployment stretch goal goes ahead, add basic auth or force `LLM_MOCK=true`. Hosted platforms also often limit how long a request can stay open, which cuts off SSE periodically. EventSource reconnects on its own, but the status dot shouldn't alarm on brief drops.

### 13.9 Opportunities to Simplify

- **S1: one way to run the app.** Drop the root `docker-compose.yml`. The start scripts that wrap `docker run` already cover it, and §3 rules out compose for production. Keep only `test/docker-compose.test.yml`.
- **S2: initialize the DB only at startup**, in the FastAPI lifespan. The background tasks need the DB at startup anyway, and initializing on first request adds a code path with no benefit.
- **S3: one batched SSE event per tick** (see R13). Drop the "change direction" field, since it can be worked out from `price` and `previous_price`.
- **S4: pick one charting approach.** Two options:
  - Use Lightweight Charts (canvas) for the main chart and P&L chart. Draw sparklines as an inline SVG `<polyline>`, about 20 lines with no library. Draw the heatmap as divs positioned by `d3-hierarchy`'s treemap layout, a small dependency that keeps full Tailwind styling.
  - Use Recharts for everything. SVG is fine at this data volume.

  Either way, drop the "canvas-based preferred" wording.
- **S5: simpler correlation model.** Instead of a full covariance matrix and a Cholesky decomposition, give each ticker a random move made of three parts: a market-wide move scaled by the ticker's beta, a move shared by its sector, and noise of its own. Unknown tickers get only the market-wide part.
- **S6: make Massive a stretch goal.** Keep the interface, but build the Massive client last. It brings network handling, rate limits and tests against recorded responses, and may only provide end-of-day data (R16), all for a path that isn't the default.
- **S7: single LLM call with action results returned directly** (see R22). This avoids a second LLM round trip.
- **S8: consider whole shares only.** This removes the rounding and leftover-position handling in R19, and the LLM can round `dollars / price` down itself. The cost is that "buy $500 of NVDA" is no longer exact. This one is optional.
- **S9: trim the tests.**
  - Drop the SSE-resilience E2E test, because killing the server mid-test is hard to make reliable. Instead, unit-test how the connection indicator changes on EventSource `onopen` and `onerror`.
  - Drop the frontend "Watchlist CRUD" unit tests, which repeat the E2E scenario.

### 13.10 Minor Notes

- `start_mac.sh` and `stop_mac.sh` also serve Linux. Consider naming them `start.sh` and `stop.sh`.
- §7 says every table has a `user_id` column, but `users_profile` uses `id` as the user key. Reword.
- The §4 tree's root is `finally/`, but the repo is `finally_final/`.
- Next.js static export:
  - Set `images: { unoptimized: true }` if `next/image` is used.
  - API routes and middleware aren't available.
  - Mount FastAPI's `StaticFiles(html=True)` at `/` *after* the API routers, so it doesn't capture `/api/*` requests.
- Name the frontend unit-test runner. Suggest Vitest with React Testing Library.
- Use `uv sync --frozen --no-dev` in the Dockerfile and commit `uv.lock`.
- `README.md` is empty. It needs quick-start instructions: the scripts, `.env` setup and the URL.
