#!/usr/bin/env bash
# Start FinAlly in Docker (macOS and Linux). Safe to run repeatedly.
#
# Usage: scripts/start_mac.sh [--build] [--no-open]
#   --build    rebuild the image (and replace a running container with the new one)
#   --no-open  don't open the browser
# Env: PORT (default 8000) is the host port, bound to 127.0.0.1 only.
set -euo pipefail

IMAGE=finally
CONTAINER=finally
VOLUME=finally-data
PORT="${PORT:-8000}"
# Seconds `docker stop` waits before SIGKILL. Some Docker installs default to 1 s, which kills
# the app before it saves its state (uvicorn needs ~4 s with an open price stream).
STOP_TIMEOUT=10

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUILD=0
OPEN=1
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --no-open) OPEN=0 ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running. Start Docker and try again." >&2
  exit 1
fi

if [ ! -f "$ROOT/.env" ]; then
  if [ -f "$ROOT/.env.example" ]; then
    cp "$ROOT/.env.example" "$ROOT/.env"
  else
    : > "$ROOT/.env"
  fi
  echo "Warning: no .env found; created $ROOT/.env from .env.example." >&2
  echo "         Set OPENROUTER_API_KEY there to enable AI chat (or LLM_MOCK=true for mock replies)." >&2
fi

REBUILT=0
if [ "$BUILD" = 1 ] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building image '$IMAGE'..."
  docker build -t "$IMAGE" "$ROOT"
  REBUILT=1
fi

running="$(docker container inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null || true)"
if [ "$running" = "true" ] && [ "$REBUILT" = 0 ]; then
  echo "FinAlly is already running."
else
  if [ -n "$running" ]; then
    echo "Replacing existing container '$CONTAINER'..."
    docker stop -t "$STOP_TIMEOUT" "$CONTAINER" >/dev/null 2>&1 || true
    docker rm "$CONTAINER" >/dev/null
  fi
  echo "Starting container '$CONTAINER'..."
  docker run -d --name "$CONTAINER" \
    --stop-timeout "$STOP_TIMEOUT" \
    -v "$VOLUME:/app/db" \
    -p "127.0.0.1:$PORT:8000" \
    --env-file "$ROOT/.env" \
    "$IMAGE" >/dev/null
fi

# The actual host port (it differs from $PORT if an already-running container used another).
mapped="$(docker port "$CONTAINER" 8000/tcp 2>/dev/null | head -n 1 || true)"
host_port="${mapped##*:}"
URL="http://localhost:${host_port:-$PORT}"

printf 'Waiting for FinAlly to become healthy'
status=""
for _ in $(seq 1 60); do
  status="$(docker container inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$CONTAINER" 2>/dev/null || echo missing)"
  case "$status" in
    healthy) break ;;
    exited|dead|missing) break ;;
  esac
  printf '.'
  sleep 1
done
echo

if [ "$status" != "healthy" ]; then
  echo "FinAlly did not become healthy (status: $status). Recent logs:" >&2
  docker logs --tail 40 "$CONTAINER" >&2 || true
  exit 1
fi

echo "FinAlly is running at $URL"
echo "Stop it with: scripts/stop_mac.sh (your data is kept in the '$VOLUME' volume)"

if [ "$OPEN" = 1 ]; then
  if command -v open >/dev/null 2>&1 && [ "$(uname -s)" = "Darwin" ]; then
    open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
