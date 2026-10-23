"""Start the monitor: `uv run python -m monitor [--port 4800]`."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import uvicorn

from .api import create_app
from .config import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-monitor", description="Live and replay view of Claude Code agent teams.")
    parser.add_argument("--host", help="default 127.0.0.1")
    parser.add_argument("--port", type=int, help="default 4800")
    parser.add_argument("--claude-dir", type=Path, help="Claude config folder (default ~/.claude)")
    parser.add_argument("--runs-dir", type=Path, help="where runs are stored (default ./runs)")
    args = parser.parse_args()
    settings = load_settings(host=args.host, port=args.port, claude_dir=args.claude_dir, runs_dir=args.runs_dir)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    print(f"Agent Monitor on http://{settings.host}:{settings.port}  (watching {settings.claude_dir / 'teams'})")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
