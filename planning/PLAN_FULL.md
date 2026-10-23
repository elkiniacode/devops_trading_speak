# IA Revolutions Trading Terminal — Greenfield Implementation Plan

This document is self-contained. It may be copied into an empty repository and used to build the trading terminal without access to the original design package or this repository. The product and technical requirements below are the implementation contract.

## Product Goal

Build a Spanish-language, desktop-first simulated stock-trading workstation matching the IA Revolutions Terminal v3 reference: a compact financial header, searchable watchlist, interactive technical chart, positions and account dock, staged order ticket, clearly labeled sample sentiment, and an AI assistant. Include a prediction mini-game that cannot affect account state.

Acceptance viewport is 1440×810; supported workstation widths are 1200 CSS pixels and wider. Under 1200px, show a Spanish desktop-size notice and do not initialize charting or full-screen dialogs. The distinct `/charla` application, when present in a destination project, is outside this plan and must be preserved without behavior or route changes.

## Scope and Locked Decisions

- First release supports US stocks from the configured catalog and long-only simulated positions. Default account cash is USD 10,000; fractional shares allow up to four decimal places.
- Simulator data is the default and works without credentials. An optional Massive (Polygon.io) adapter may provide equity quotes and candles when configured. Assistant credentials are optional; deterministic mock replies support offline development and tests.
- Sentiment is deterministic sample data generated in the browser. Every sentiment summary and source detail clearly says `DATOS DE MUESTRA` and `FUENTE SIMULADA`; no sentiment requests or backend service are added.
- Prediction is an isolated browser exercise: it freezes a chart copy, scores ten generated candles against one ATR, and never mutates real quotes, portfolio, orders, or account history.
- Crypto, forex, gold, shorts, margin, leverage, authentication, multi-user accounts, and real brokerage execution are deferred. Keep instrument types extensible, but do not expose deferred assets or capabilities in v1.
- Spanish is used throughout the trading experience, validation, status, accessibility names, and errors. Technical code identifiers and API enums use English.

## Greenfield Stack and Repository

Bootstrap from an empty repository with Node 24, Next.js 16 App Router, React 19, strict TypeScript, static export, Tailwind CSS 4, Lightweight Charts 5, local Archivo Variable and JetBrains Mono fonts, Vitest, React Testing Library, and jsdom. Use Python 3.12, FastAPI, Pydantic 2, Uvicorn, SQLite/WAL, `uv`, HTTPX, optional LiteLLM/OpenRouter, Pytest, and pytest-asyncio. Use Playwright/Chromium for browser acceptance.

Create `frontend/`, `backend/`, `test/`, `db/`, `planning/`, and `scripts/`, plus a multi-stage root Dockerfile, `.env.example`, README, and ignore files. FastAPI serves `/api/*`, SSE, and the built frontend from the same origin on port 8000. Use one Uvicorn worker because the market cache and coordination locks are process-local. Include Windows PowerShell and macOS/Linux start and stop scripts. Required commands: frontend `dev`, `build`, `test`, `typecheck`; backend `uv run uvicorn app.main:app --reload`, `uv run pytest`; E2E build and Playwright test commands. Production starts without any API keys.

The root environment template defines `OPENROUTER_API_KEY`, `LLM_MOCK`, `MASSIVE_API_KEY`, `MASSIVE_POLL_SECONDS`, `SIM_SEED`, `DB_PATH`, `STATIC_DIR`, and `CORS_ORIGINS`. Secrets never enter the frontend bundle.

## Visual Contract

Build a dense 1440×810 desktop workspace with 8–12px gutters, a 54–60px account header, a 250–280px watchlist, a flexible center chart/dock, and a 300–330px right assistant/order column. At 1280px, allow the center column to shrink while keeping controls usable. Keep document-level scrolling off at supported heights; scroll long watchlist/dock/modal content inside its panel.

Use these tokens: page `#070909`, cards `#0d1211`, inner panels `#0a0d0c`, borders `#1f2523` and `#2a312f`, primary text `#f2f5f4`, muted text `#8b9491`, teal `#5eead4`, red `#ff7a7a`, amber `#f5a524`, cyan `#22d3ee`, purple `#a78bfa`, and magenta `#ff2bd6`. Use Archivo for prominent headings and JetBrains Mono for dense UI and figures. Use whole-pixel chart overlay coordinates, visible keyboard focus, and reduced-motion behavior. Use the supplied IA Revolutions logo if included in the destination project; otherwise render a text/mark fallback without relying on an external asset.

Header fields: portfolio value, total P/L, open P/L, available cash, `CUENTA SIMULADA`, and live/reconnecting/disconnected status. Watchlist rows show ticker, short name, sparkline, price, percent change, selected state, held-position marker, and remove control. Center chart includes ticker quote, timeframe controls M1/M5/M15/H1/H4/D1, candles/line toggle, indicators, drawing toolbar, prediction action, and lower indicator panes. Dock tabs are `POSICIONES`, `ÓRDENES`, `PORTAFOLIO`, `HISTORIAL`, `JOURNAL`. Right column stacks the sequential order flow, sentiment summary, and assistant preview.

## Architecture and Data Ownership

Frontend state is divided into a market store and an account store. Market events update only the affected symbol row and active chart; account state is replaced only after bootstrap, mutation success, or an account-version event. The server is authoritative for cash, holdings, trades, pending orders, SL/TP, chat history, snapshots, and journal activity. Local storage contains only versioned display preferences and drawings, never portfolio state or credentials.

Backend layers: API routes validate and map errors; services own market/order/account rules; a market-source interface has simulator and optional Massive implementations; SQLite repositories own transactions; an application context owns market cache, candle cache, account event version, and one async mutation lock. Database startup applies ordered, versioned, additive migrations in transactions. Existing databases must retain user cash, positions, watchlist, and history; migration failure must stop startup without resetting data.

Instrument catalog fields: ticker, display name, asset class (initially `stock` only), price precision, and enabled state. Normalize ticker casing and validate against the enabled catalog before trading or watchlist mutation.

Persist profile, watchlist order, positions, trades, pending orders, position risk levels, portfolio snapshots, chat messages/action results, activity events, and last simulator price marks. Use `default` as the sole v1 user key. Monetary totals round at the transaction boundary to cents; share quantities round to four decimals. One trade lock serializes watchlist tracking, market executions, pending-order triggers, stop/take-profit closes, and position-risk updates.

## Market Data and Candles

Simulator uses a reproducible seed when `SIM_SEED` is set, stock-specific price/volatility profiles, and a 500ms quote cadence. It produces 150 OHLCV candles for M1/M5/M15/H1/H4/D1 using deterministic seeded history anchored to current simulated prices. Keep a bounded rolling buffer per tracked ticker/timeframe. Update the forming candle from each quote; roll at timeframe boundaries; ensure timestamps strictly increase and OHLC invariants hold. Restart persistence resumes last prices, but historical candles may be regenerated deterministically rather than growing the database without bound.

Massive mode reports provider source and quote freshness. Use available aggregates for candle history. If provider history is unavailable, show only locally collected candles and label them as incomplete; never pass synthetic history off as provider history. Market orders reject missing or stale quotes. Simulator is explicitly labeled simulated; no UI claims that mock prices are real-time exchange data.

## API Contract

Keep JSON response types aligned in Pydantic and TypeScript. Return consistent error objects with Spanish user-facing `detail` for expected validation and trading failures.

- `GET /api/health`: server, market mode, assistant mode.
- `GET /api/workstation`: initial health, portfolio, watchlist with quotes, active orders, position risk, recent executions, latest snapshots, and bounded activity page.
- `GET /api/market/candles?ticker=&timeframe=&limit=`: ordered OHLCV, ticker, timeframe, `source`, `synthetic`, and latest candle timestamp; timeframe enum M1/M5/M15/H1/H4/D1; limit 1–500.
- `GET/POST/DELETE /api/watchlist[/{ticker}]`: ordered watchlist; add is idempotent; remove cannot untrack a held symbol.
- `GET /api/portfolio`: cash, positions, valuations, total/open P/L, completeness, as-of timestamp.
- `POST /api/portfolio/trade`: preserve quantity-based market trade compatibility.
- `GET /api/portfolio/history?limit=` and `GET /api/portfolio/trades?limit=`: bounded chronological results.
- `POST /api/orders`: `{ticker, side, type, notional, trigger_price?, stop_loss?, take_profit?, client_order_id}`; side buy/sell; type market/limit/stop. Market fills immediately; limit/stop persist pending.
- `PATCH /api/orders/{id}` updates permitted pending fields; `DELETE /api/orders/{id}` cancels a pending order. Terminal orders cannot be edited or cancelled.
- `PUT /api/positions/{ticker}/risk`: set or clear SL/TP with directional and current-price validation.
- `POST /api/positions/{ticker}/close`: atomically close the full long position at a fresh quote.
- `GET /api/activity?limit=&before=`: newest-first bounded cursor page.
- `POST /api/chat`: message and optional selected ticker/timeframe/indicator/chart-level context; `GET /api/chat/history?limit=`. Structured actions can modify watchlist, place supported orders, close a position, and set risk levels. Do not execute trades without explicit user intent; report each action result individually.
- Keep `GET /api/stream/prices` backward compatible. Add `GET /api/stream/workstation` with named `prices` events and `account` events containing a monotonically increasing account version. Send initial state/version promptly, heartbeat comments, and support normal EventSource reconnect.

## Order and Account Rules

Market order notional must be positive and within the configured per-order ceiling; converted quantity must be at least one cent of notional and round to 4dp. Buy checks available cash inside the same SQLite transaction that changes cash/position and records the trade. Sell checks held shares and cannot cross through zero into a short. Weighted average cost is updated on buys; sells preserve remaining basis. No fees or leverage.

Limit buy must be below current price; limit sell above it. Stop buy must be above current price; stop sell below. Pending orders do not reserve cash or shares. At trigger, revalidate account resources against the then-current quote. Rejected triggered orders transition to `rejected`, retain an explanatory reason, and add a journal event. Fills transition exactly once to `filled` and record execution atomically. `client_order_id` is unique per user and makes retries return the original result without duplicate fills.

Position SL for a long must be below the current quote; TP above. Validate edits against the latest fresh quote, and recheck during execution. If a gap crosses the level, execute at the current tradable quote and record both configured trigger and actual fill price. Removing a position clears risk settings. Every account mutation increments the event version after commit and writes an activity item; no event may advertise an uncommitted transaction.

## Chart, Tools, and Performance

Use Lightweight Charts imperative series updates, not React rerenders, for quote ticks. Load 150 candles on symbol/timeframe selection and update the last candle in O(1). Keep chart instances stable through resizing using `ResizeObserver`; destroy chart, observers, listeners, timers, and stream subscriptions on unmount. Bound data and avoid repeated `fitContent()` on every tick.

Implement candle/line mode; SMA20/SMA50, EMA21/EMA50, volume, RSI14, MACD12·26·9; crosshair OHLC readout; current/entry/order/SL/TP price levels; support/resistance, trend, zone, and measurement drawings; snap/magnet; select, drag, delete, clear. Throttle pointer work with `requestAnimationFrame`. Persist drawings and chart settings by symbol/timeframe with a versioned storage key and debounced writes. If saved data fails validation/version parsing, discard only that preference record and continue with defaults. Avoid overlapping price-axis labels with deterministic nearest-label spacing and hidden/deduplicated labels where needed.

Price SSE buffers, chart candles, snapshots, and activity lists have explicit caps. Use per-ticker subscriptions/selectors; never put the full quote map in broad app context. Memoize watchlist and dock rows. Lazy-load sentiment detail and full chat modal. Avoid chart construction and heavy chunk loading below the supported viewport. Production performance acceptance uses fixed simulator seed, pinned browser viewport, production build, and recorded browser version: Lighthouse desktop Performance >=90; no >50ms main-thread task during a 30-second quote trace; control feedback <=100ms; unrelated symbol updates do not rerender the entire workstation.

## Sentiment, Assistant, Prediction

Mock sentiment uses a stable ticker hash to produce repeatable score, band, confidence, source sample counts, and Spanish sample posts. It is presentation-only and never affects trading/account logic.

Compact assistant preview shows last response and contextual prompts; full chat loads on demand. Persist message history and structured action results. In mock mode provide deterministic responses for portfolio summary, chart explanation, watchlist changes, market buy/sell, order placement, close, and SL/TP. In LLM mode include only bounded account and selected-chart context, validate structured output, cap action counts, and independently report failures. A failed model call executes no actions. All trading actions must be traceable to the user request.

Prediction stores a copy of the displayed candle series and ATR when started. Accept target by input, ±1%/±2% chips, or chart click. Generate ten seeded candles at 700ms display cadence; score within one captured ATR. Live data continues in the market store while the visible chart is frozen. On completion, cancellation, or exit, restore the latest live series. Prediction cannot call account mutation APIs.

## Delivery Waves

1. Scaffold empty-project stack, static export, same-origin FastAPI/static serving, configuration, scripts, Docker, and concise setup instructions.
2. Add versioned SQLite schema, stock catalog, simulator, quote cache, watchlist, portfolio, market trade, health/bootstrap API, and price SSE; deliver one vertical slice from fresh start through live quote and buy.
3. Add bounded OHLCV candle service/API, responsive desktop shell, account/market stores, watchlist, header, and chart.
4. Add timeframe controls, indicators, drawing tools, price-level overlays, and preference persistence.
5. Add atomic market/limit/stop order workflow, pending monitor, SL/TP, idempotency, risk-level dragging, executions, and journal.
6. Add dock portfolio visuals, history, mocked sentiment, and isolated prediction.
7. Add optional assistant integration and deterministic mock action handling.
8. Finish visual/accessibility checks, performance measurement, Docker and end-to-end acceptance, and documentation.

Each wave leaves a runnable application. Do not begin another wave while the prior wave’s focused checks are failing.

## Test and Acceptance Plan

Backend tests cover fresh install and in-place migration preserving cash/positions/watchlist/history; simulator reproducibility; candle ordering and OHLC invariants; timeframe and symbol validation; market-buy accounting; partial/full sell and short rejection; invalid limit/stop direction; order retry idempotency; exact-once triggers; insufficient resources at trigger; SL/TP directional validation and gap fill; transaction rollback; concurrent trade/order lock behavior; restart persistence; SSE initial event/version/reconnect; assistant action validation and all-or-none model failure.

Frontend tests cover API contracts/errors, store subscription isolation, bounded buffers, candle merge/roll behavior, indicator results, chart cleanup, drawing CRUD/storage recovery, ticket math/validation, server failure presentation, mocked sentiment stability/disclosure, action-result messages, and prediction isolation. Tests should assert behavior at interfaces rather than mirror implementation details.

Playwright uses a fresh temporary SQLite database and `LLM_MOCK=true`, `SIM_SEED=42`, pinned viewport 1440×810 by default. Cover fresh $10,000 state, live connection, watchlist add/remove, market trade, pending limit/stop fill and cancel, SL/TP close, reload persistence, history/journal, assistant actions, SSE interruption/recovery, prediction with unchanged account totals, desktop screenshot at 1440×810 and 1280×720, and unsupported-width notice. If a destination contains `/charla`, run its pre-existing regression suite and compare its routes/styles before and after.

Release gate: frontend tests, frontend typecheck, production build, backend pytest, Playwright suite, Docker build, health check, visual comparison, accessibility check, and reproducible 30-second performance trace all pass. Document commands, configuration, and any provider-plan limitations in README.

## Portable Execution Rules

Treat this file as the source of truth when placed in a different repository. First inspect the destination tree and preserve existing code, user changes, and unrelated products. If the repository is empty, scaffold the layout and stack specified here. If equivalent infrastructure exists, adapt to it while preserving the API and product behaviors in this contract; do not overwrite it with this document or reset data. Never require access to the original Downloads folder, screenshot, prototype HTML, or engine source to implement the product.

