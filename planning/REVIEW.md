# Plan review

Reviewed 2026-10-19 against `planning/PLAN.md`, including its existing R1–R38 and S1–S9 feedback. The application directories currently contain no implementation files, so this is a specification review, not a code review. External provider capabilities and package compatibility were not verified.

The architecture is appropriately scoped for a local, single-user simulator. The main obstacle to implementation is that section 13 contains proposals while sections 1–12 still specify conflicting behavior. Resolve the high-priority items below before treating the plan as a shared implementation contract. Preserve the intended simulated trading, fractional shares, and automatic execution without confirmation dialogs.

## High-priority findings

### 1. Promote decisions into the specification

**References:** Sections 4, 7–10; R2, R7–R13, R17, R22–R26, R33.

An implementer cannot tell whether to follow the original text or the suggested resolutions. For example, initialization is both lazy and startup-based, and the chat failure flow still requires information unavailable to the single LLM response.

**Recommended change:** Incorporate accepted decisions into the owning sections and publish exact request, success, error, and SSE schemas before frontend/backend work diverges. Include nullability, numeric precision, timestamp semantics, status codes, and action results. Distinguish malformed input, unavailable prices, insufficient funds, and upstream failures. Keep unresolved choices in a short decision list rather than leaving two specifications in force.

**Acceptance:** A client can render initial state, execute a trade, reconnect to prices, and display a failed chat action using documented payloads alone.

### 2. Trade retries can execute the same intent twice

**References:** Sections 8–9; R19–R20, R22–R26.

Transactions and a single-process lock prevent overlapping balance updates, but do not prevent duplicate execution. If a trade commits and the response is lost, retrying the request can buy again. Retrying a chat turn can repeat an entire action batch. A crash between executing an action and storing the chat result also leaves the conversation inconsistent with the account.

**Recommended change:** Add client-generated request IDs to manual trades and chat turns. Persist execution status and results, enforce uniqueness, and return the stored outcome on replay. Reject reuse of an ID with a different payload. Commit each trade and its durable action result together. For chat batches, define ordered partial success or all-or-nothing semantics explicitly; ordered per-action results are sufficient for this project. Never hold a database transaction while waiting for the model.

**Acceptance:** Replaying a request after a lost response changes cash and holdings only once. Concurrent buys cannot overspend. A failed second action does not conceal the outcome of the first.

### 3. Fractional-share rounding needs an accounting rule

**References:** Section 7; R7, R18–R20; S8.

Using `REAL`, rounding quantities to four decimals, and rounding each cash change to cents can permit positive shares to be credited for a purchase whose debit rounds to zero. Display rounding is not an accounting specification. Tiny-position deletion also needs to respect the permitted quantity increment.

**Recommended change:** Specify fixed precision for quantities, prices, cost basis, and ledger amounts. Use scaled integers or consistently serialized decimals for authoritative accounting. Define when rounding occurs and reject orders below the minimum executable notional or preserve their sub-cent value internally. Validate finite positive quantities and prices; reject NaN, infinity, and quantities outside supported precision and bounds. Use the same execution service for manual and model-generated orders.

**Acceptance:** Repeated minimum-size buys cannot create holdings without debiting value; a full sell removes the holding exactly; weighted average cost and partial sales remain consistent. Keep presentation formatting separate from stored precision.

### 4. Cached prices need freshness and availability semantics

**References:** Section 6; R9–R14, R16–R17.

Pricing watchlist symbols plus open positions is necessary, but insufficient. A timestamped cache can still supply a stale fill during an upstream outage. R17's fallback to average cost silently makes an unpriced holding appear to have zero unrealized P&L. An immediate synthetic seed for an unknown symbol would also be inappropriate in real-data mode.

**Recommended change:** Define quote source, quote timestamp, freshness status, and a mode-specific execution eligibility rule. Keep held symbols subscribed after watchlist removal. In real-data mode, show pending/unavailable quotes and reject trades until an eligible quote exists. Retain the last known valuation with a visible stale flag, or mark valuation incomplete; do not silently substitute cost basis. Specify behavior for market closure, rate limits, timeouts, and failed symbols without switching sources silently.

**Acceptance:** Removing a held symbol does not freeze its price. A stale or missing quote cannot fill a trade. Portfolio displays and snapshots expose incomplete/stale valuation consistently.

### 5. Snapshot history will stop updating in an idle session

**References:** Sections 7, 10; R21, R29.

The backend records portfolio snapshots every 30 seconds, but R29 refreshes history only after mutations and says no other polling is needed. Price SSE does not contain those snapshots. A user who simply watches the workstation will see an outdated P&L chart despite new database samples.

**Recommended change:** Either include snapshot notifications/data in SSE or poll the history endpoint at the snapshot cadence. Define bounded incremental retrieval and ascending ordering. Separately document that cash and quantities need refreshing after mutations; quote events alone cannot propagate an account change from another browser tab.

**Acceptance:** Leaving the app open without trading adds chart samples. Reconnection reconciles authoritative portfolio state as well as current quotes.

## Corrections to the existing review

- **R11 — distinguish previous close from opening price.** These are different reference values. Name the field according to the chosen metric, such as `reference_price`, and document its meaning for each source. Label simulated change as change since session start if that is the intended baseline.
- **R14 — the last trade price is not the last market price.** Restarting from a potentially old execution still creates a valuation jump. Persist simulator marks and its reference baseline if continuity is required, or explicitly accept session resets. Restoring the last trade price does not solve the stated issue.
- **R25 — separate arrays limit execution order.** Applying every watchlist change before every trade may work for “add and buy,” but not every requested sequence. Define supported ordering, or use an ordered action list. Preserve subscriptions for held symbols regardless of watchlist operations.
- **R33 — the code/volume collision is conditional.** It occurs if backend code is copied directly into `/app`. Make the proposed `/app/backend` code path and separate `/app/db` data path explicit in the Docker specification.
- **Section 11 — a named volume is not a repository bind mount.** The provided `-v finally-data:/app/db` command does not map the repository's `db/` directory into the container. Choose and document the storage model so users know where persistence lives.
- **S9 — retain an actual reconnect test.** Testing indicator callbacks alone cannot prove reconnection restores data. Simulate a dropped stream in a controlled test server or browser fixture; killing the production server is unnecessary.
- **R36 — a seed alone does not ensure deterministic tests.** Wall-clock tick counts and request timing can still vary. Use fixed quotes or a controllable clock for accounting assertions and isolate mutable state between tests.

## Remaining implementation decisions

1. **Model actions:** Treat the complete structured response as untrusted input. Validate the entire response before executing any action, cap action counts, and enforce server-side trade rules. Distinguish advice from execution intent in prompts and tests. Return actual action outcomes separately from model prose, as R22 proposes.
2. **Chat context:** Define ordering for simultaneous turns and how failed requests appear in history. Include stored action outcomes in future context. Resolve the referenced `cerebras-inference` skill dependency or document a self-contained integration contract; it is not listed among the skills available in this review session.
3. **Startup and upgrades:** Initialize before background tasks start, seed idempotently, and add a schema-version policy. “Create missing tables” alone cannot evolve an existing persisted database. Test restarting with an existing volume without resetting cash or duplicating seeds.
4. **SSE lifecycle:** Specify initial state, heartbeat/reconnect behavior, stale indicators, bounded buffering, and cleanup when clients disconnect. A full quote snapshot on reconnect avoids needing durable replay for quotes.
5. **Local deployment:** Since the application has no authentication, make the local launch command bind to `127.0.0.1:8000:8000`. Keep public deployment outside the core acceptance criteria until access and persistence requirements are defined.

## Suggested delivery gates

1. **Contract gate:** Resolve the findings above and integrate accepted section 13 decisions into sections 1–12.
2. **Core gate:** Startup initialization, deterministic quotes, atomic/idempotent trading, and authoritative portfolio calculations pass backend tests.
3. **Integration gate:** UI state, live prices, periodic history updates, and mock chat actions work end to end, including failures and reconnects.
4. **Packaging gate:** A fresh container starts without API keys, data survives restart, and start/stop scripts are idempotent.
5. **Provider gate:** Verify real LLM structured-output behavior and market-data entitlements separately. Keep deterministic tests independent of paid services.

The existing design and default simulator provide a clear capstone scope. Finalizing these contracts and failure behaviors will make implementation substantially more reliable without expanding the product.
