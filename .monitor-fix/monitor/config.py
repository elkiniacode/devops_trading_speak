"""Settings, from environment variables with command-line overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    claude_dir: Path
    runs_dir: Path
    web_dir: Path
    host: str = "127.0.0.1"
    port: int = 4800
    poll_seconds: float = 0.3
    discover_seconds: float = 2.0
    # A run ends after this long without teammate activity; a teammate joining later starts a new run.
    idle_end_seconds: float = 30 * 60
    # The lead's work just before the first teammate joins (back to its last user prompt) is part of the run.
    lead_lookback_seconds: float = 3 * 60 * 60


def load_settings(**overrides) -> Settings:
    env = os.environ
    settings = Settings(
        claude_dir=Path(env.get("AGENT_MONITOR_CLAUDE_DIR") or env.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"),
        runs_dir=Path(env.get("AGENT_MONITOR_RUNS_DIR") or ROOT / "runs"),
        web_dir=Path(env.get("AGENT_MONITOR_WEB_DIR") or ROOT / "web"),
        host=env.get("AGENT_MONITOR_HOST", "127.0.0.1"),
        port=int(env.get("AGENT_MONITOR_PORT", "4800")),
    )
    return replace(settings, **{k: v for k, v in overrides.items() if v is not None})
