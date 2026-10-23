# FinAlly: AI Trading Workstation

A Bloomberg-style trading terminal with an AI copilot. It streams live (simulated) prices, lets you trade a $10,000 virtual portfolio and includes a chat assistant that can analyze your positions and place trades for you.

**Architecture:** one Docker container on port 8000. FastAPI (Python, uv) serves the REST API under `/api`, a Server-Sent Events price stream at `/api/stream/prices` and the static Next.js export at `/`. State lives in SQLite (`/app/db/finally.db`, on the `finally-data` volume). Prices come from a built-in simulator, or from the Massive (Polygon.io) API if you set a key. Chat uses LiteLLM → OpenRouter (Cerebras). The full spec is in [planning/PLAN.md](planning/PLAN.md); the binding contracts are in [planning/CONTRACTS.md](planning/CONTRACTS.md).

## Quick start

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (running).

```bash
# macOS / Linux
bash scripts/start_mac.sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy Bypass -File scripts\start_windows.ps1
```

Then open <http://localhost:8000> (the script opens it for you).

- The first run builds the `finally` image, which takes a few minutes. Later runs reuse it.
- If `.env` doesn't exist, the script creates it from `.env.example` and warns you. Add your `OPENROUTER_API_KEY` there to enable AI chat, then restart with the start script.
- Options: `--build` / `-Build` rebuilds the image (and replaces a running container), `--no-open` / `-NoOpen` skips the browser, `PORT=8001` / `-Port 8001` changes the host port.
- The scripts are idempotent: running start twice leaves one container running.

Stop the app with `bash scripts/stop_mac.sh` or `powershell -ExecutionPolicy Bypass -File scripts\stop_windows.ps1`. Your portfolio is kept in the `finally-data` volume. To start over from $10,000, stop the app and run `docker volume rm finally-data`.

The app has no authentication, so the port is bound to `127.0.0.1` only. Don't expose it publicly.

Without the scripts:

```bash
docker build -t finally .
docker run -d --name finally --stop-timeout 10 -v finally-data:/app/db -p 127.0.0.1:8000:8000 --env-file .env finally
```

`--stop-timeout 10` gives the app time to save its state on `docker stop`, since some Docker installs default to 1 second.

## Configuration

Set these in `.env` at the repo root (see `.env.example`). Docker reads the file literally, so don't quote values.

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | empty | Enables AI chat. Without it (and without `LLM_MOCK=true`) everything else works and chat returns 503. |
| `LLM_MOCK` | `false` | `true` gives deterministic mock chat replies with no network (used by E2E tests). |
| `MASSIVE_API_KEY` | empty | Real market data from Massive (Polygon.io). Empty uses the simulator. |
| `MASSIVE_POLL_SECONDS` | `15` | Massive poll interval. The free tier allows 5 calls/min. |
| `SIM_SEED` | empty | Integer seed for reproducible simulator prices. |
| `DB_PATH` | `<repo>/db/finally.db` | SQLite file. The image sets `/app/db/finally.db`. |
| `STATIC_DIR` | `<repo>/backend/static` | Built frontend served at `/`. The image sets `/app/backend/static`. |
| `CORS_ORIGINS` | unset | Development only, e.g. `http://localhost:3000`. CORS is off when unset. |

## Local development

The backend is a uv project in `backend/`; the frontend is a Next.js project in `frontend/`. Use your own database file while developing, not `db/finally.db`.

```bash
# Backend API on :8000 (loads the root .env)
cd backend
uv sync
DB_PATH=db/dev.db CORS_ORIGINS=http://localhost:3000 uv run uvicorn app.main:app --reload --port 8000

# Frontend dev server on :3000, calling the backend above
cd frontend
npm install
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000 npm run dev
```

In PowerShell, set the variables first, e.g. `$env:DB_PATH='db\dev.db'; $env:CORS_ORIGINS='http://localhost:3000'`. You can also put `NEXT_PUBLIC_API_BASE` in `frontend/.env.local`, which is gitignored and never copied into the Docker build. Relative `DB_PATH` and `STATIC_DIR` values are taken from the repo root, whichever directory you start in.

Stop the Docker container first (`scripts/stop_windows.ps1` or `scripts/stop_mac.sh`). It also publishes port 8000, and uvicorn only binds `127.0.0.1`, so a browser that resolves `localhost` to `::1` reaches the container instead of your dev server. That is why the API base above uses `127.0.0.1`.

To serve the production build from the backend without Docker, run `npm run build` in `frontend/`, then start uvicorn with `STATIC_DIR=frontend/out`.

## Tests

```bash
cd backend && uv run pytest     # backend unit tests
cd frontend && npm test         # frontend unit tests (Vitest + React Testing Library)
```

End-to-end tests are a Playwright project in `test/`. They run against the Docker image with `LLM_MOCK=true` and a fresh database:

```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit
```

## Project layout

```
backend/     FastAPI app (app/), unit tests (tests/), pyproject.toml + uv.lock
frontend/    Next.js + TypeScript, static export to frontend/out
test/        Playwright E2E tests and docker-compose.test.yml
scripts/     start/stop scripts for macOS/Linux and Windows
db/          runtime SQLite location for local runs (the container uses the finally-data volume)
planning/    project spec and agent contracts
Dockerfile   multi-stage build: node:24-slim (frontend) -> python:3.12-slim (runtime)
```
