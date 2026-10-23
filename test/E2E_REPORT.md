# FinAlly E2E Report

Owner: tester. Running log of Playwright E2E status (CONTRACTS §11).

## How to run

Local (Windows/macOS/Linux). The runner uses port **8003** (`E2E_PORT`); 8000 is the user's own dev server.

```
cd test
npm install
npx playwright install chromium
npm run build:frontend          # builds frontend/out
npx playwright test             # starts the backend on :8003 itself (fresh DB, LLM_MOCK, SIM_SEED=42), then stops it
```

- Against an already-running server instead: `BASE_URL=http://localhost:<port> npx playwright test` (the server must have a fresh DB for `01-fresh-start`).
- The throwaway DB lives at `%TEMP%/finally-e2e/finally-e2e.db` (or `$TMPDIR/...`) and is deleted at the start of each run.
- Report: `npm run report`. Failure traces, screenshots and videos: `test/test-results/`.

Docker:

```
docker compose -f test/docker-compose.test.yml up --build --exit-code-from playwright
docker compose -f test/docker-compose.test.yml down
```

## Design notes

- **Serial, one worker.** FinAlly is single-user, so all tests share one portfolio. Each test arranges its own preconditions through the REST API, uses its own tickers, makes relative assertions and cleans up. Only `01-fresh-start` needs the untouched seed; it sorts first.
- **Random prices.** Assertions never use exact prices: trade checks read the fill price from the trade response, heatmap checks compare tile color and `data-pnl-sign` with the P&L shown at the same instant.
- **Unknown tickers.** In simulator mode every well-formed symbol is tradeable (the simulator invents a price), so the "unknown ticker" error path uses malformed symbols (`1234`, `A$`). Massive-only `Unknown ticker` errors are left to backend unit tests.
- **SSE reconnect.** `context.setOffline(true)` alone does **not** break an EventSource that is already streaming in Chromium (verified with a probe: events kept arriving while offline). `sse.spec.ts` therefore loads the app through an in-test TCP relay (OS-assigned ephemeral port on 127.0.0.1), cuts the live stream there and uses `setOffline` to keep reconnect attempts failing until the network returns. The server is never killed.

## Scenarios

Latest local run: 2026-10-23, port 8003, fresh DB, `LLM_MOCK=true`, `SIM_SEED=42`. **36/36 pass** in 50 seconds, including the full charla browser journey.

Local Docker verification on 2026-10-23: fresh `finally` image built successfully; `/api/health`, `/`, and all five `/charla/` routes returned 200; register -> enter -> answer -> reveal passed; the 40-attendee load test passed with launch p95 722 ms and answer p95 61 ms. The load harness reset the room afterward.

| Scenario (CONTRACTS §11) | Spec | Local | Docker |
|---|---|---|---|
| Fresh start: 10 tickers, $10,000, prices streaming (values change, sparklines grow, rows flash) | `01-fresh-start.spec.ts` | PASS | not run |
| API contract smoke (health, watchlist, portfolio, trade errors, history, chat failed action, SSE first event) | `api.spec.ts` | PASS (11) | not run |
| Watchlist add/remove, reload persistence, row click selects chart and pre-fills trade bar | `watchlist.spec.ts` | PASS (2) | not run |
| Buy | `trading.spec.ts` | PASS | not run |
| Sell (partial, then close) | `trading.spec.ts` | PASS | not run |
| Trade a ticker not on the watchlist | `trading.spec.ts` | PASS | not run |
| Heatmap: tiles match positions, sized by weight, color and `data-pnl-sign` match the P&L sign | `heatmap.spec.ts` | PASS | not run |
| P&L chart has points | `heatmap.spec.ts` | PASS | not run |
| Mock chat: trade + watchlist inline; failed trades inline (insufficient shares, qty 0); no-match reply; outage error (stubbed 502); loading indicator; history after reload | `chat.spec.ts` | PASS (7) | not run |
| SSE reconnect (relay + `setOffline`) | `sse.spec.ts` | PASS | not run |
| Error paths: insufficient cash, insufficient shares, malformed ticker (trade bar + watchlist), zero quantity | `errors.spec.ts` | PASS (5) | not run |

## Open issues

None yet.

## Run log

- 2026-10-19: E2E project created (Playwright 1.64.1, chromium). 30 tests in 8 files, typecheck clean.
- 2026-10-19: backend ready. API-only run (no frontend build): `api.spec.ts` 10/10 and the fresh-start API test pass. UI specs wait for frontend.
- 2026-10-19: llm ready. Added the 502 path ("buy 0 AAPL" fails whole-reply validation) to `api.spec.ts` and `chat.spec.ts`. API-only run: `api.spec.ts` 11/11 pass.
- 2026-10-19: contract change §7.1: mock "buy 0 AAPL" is now a failed action in a 200 reply, not a 502. Rewrote the API and chat-panel tests. The chat-error display is checked with a stubbed 502 (`page.route`), since mock mode can't produce one.
- 2026-10-19: llm's §7.1 change landed. API-only run: `api.spec.ts` 11/11 and the fresh-start API test pass (12/12).
- 2026-10-19: frontend ready. Port 8000 belongs to the user's dev server, so the local runner moved to 8003 (lead's decision).
  - Run 1: 32/33. The heatmap color check failed: TSLA at -$0.02 with `data-pnl-sign="negative"` read as rgb(57, 82, 88). This was a **test bug**: `.heat-tile` fades `background-color` over 500 ms and `getComputedStyle` caught the fade from green to red. The test now emulates `prefers-reduced-motion: reduce`, which the app's CSS honors by dropping the transition. It then passed 5/5 repeats.
  - Runs 2 and 3: 33/33 each. `--repeat-each 2` over every spec except fresh-start: 62/62. No app bugs open.
- 2026-10-23: full regression rerun: 36/36 Playwright tests passed; backend 357/357, frontend Vitest 249/249, and frontend/test typechecks passed. Fresh Docker build and local charla smoke/load checks passed.
