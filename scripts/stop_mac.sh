#!/usr/bin/env bash
# Stop FinAlly (macOS and Linux). Safe to run repeatedly.
# Removes the container but never the 'finally-data' volume, so your portfolio is kept.
set -euo pipefail

CONTAINER=finally

if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker is not running." >&2
  exit 1
fi

if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Stopping FinAlly..."
  # Give the app time to shut down cleanly (some Docker installs default to 1 s).
  docker stop -t 10 "$CONTAINER" >/dev/null 2>&1 || true
  docker rm "$CONTAINER" >/dev/null
  echo "Stopped. Data is kept in the 'finally-data' volume."
else
  echo "FinAlly is not running."
fi
