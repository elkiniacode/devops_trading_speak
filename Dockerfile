# syntax=docker/dockerfile:1
#
# FinAlly: one container, one port. FastAPI serves /api/* and the static Next.js export.
#
#   docker build -t finally .
#   docker run -d --name finally -v finally-data:/app/db -p 127.0.0.1:8000:8000 --env-file .env finally

# ---------------------------------------------------------------------------
# Stage 1: build the Next.js static export (frontend/out)
# ---------------------------------------------------------------------------
FROM node:24-slim AS frontend

WORKDIR /build/frontend

# Same-origin API in production; overrides any NEXT_PUBLIC_API_BASE from a frontend .env file.
ENV NEXT_PUBLIC_API_BASE="" \
    NEXT_TELEMETRY_DISABLED=1 \
    NPM_CONFIG_UPDATE_NOTIFIER=false

# Dependencies first, so source edits don't invalidate the npm ci layer.
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/usr/local/bin/python3.12 \
    LITELLM_LOCAL_MODEL_COST_MAP=True

# Unprivileged user. /app/db is the volume mount point: a new named volume copies this
# directory's ownership, so the app can create and write the SQLite file there.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin finally \
    && mkdir -p /app/db \
    && chown finally:finally /app/db

WORKDIR /app/backend

# Dependencies first (cached until pyproject.toml or uv.lock change).
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY --from=frontend /build/frontend/out ./static

ENV PATH="/app/backend/.venv/bin:$PATH" \
    DB_PATH=/app/db/finally.db \
    STATIC_DIR=/app/backend/static

USER finally

EXPOSE 8000

# python:3.12-slim has no curl; the stdlib is enough (R37).
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]

# Exactly one worker (R20): the simulator, price cache and trade lock live in this process.
# Open SSE streams never end on their own, so cap graceful shutdown; the lifespan then
# runs its cleanup before `docker stop` (10 s) escalates to SIGKILL.
CMD ["/app/backend/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "3"]
