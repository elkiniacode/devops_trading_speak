"""Settings from the environment (CONTRACTS.md §8).

Importing this module loads ``<repo>/.env`` first, without overriding variables that are
already set, so it must be imported before anything reads the environment (the market
factory reads it when the app starts).
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env", override=False)

TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Values fixed when the app is created."""

    db_path: Path = REPO_ROOT / "db" / "finally.db"
    static_dir: Path = REPO_ROOT / "backend" / "static"
    cors_origins: list[str] = field(default_factory=list)  # empty = CORS disabled
    charla_only: bool = False  # public talk deploy: only /api/health and /api/charla/* (planning/charla/CONTRACT.md)


def get_settings() -> Settings:
    """Read DB_PATH, STATIC_DIR and CORS_ORIGINS (comma-separated) from the environment now.

    Relative paths are taken from the repo root, so ``DB_PATH=db/dev.db`` means
    ``<repo>/db/dev.db`` whichever directory the server starts in.
    """
    defaults = Settings()
    return Settings(
        db_path=_repo_path(os.getenv("DB_PATH"), defaults.db_path),
        static_dir=_repo_path(os.getenv("STATIC_DIR"), defaults.static_dir),
        cors_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
        charla_only=_is_true(os.getenv("CHARLA_ONLY")),
    )


def _repo_path(value: str | None, default: Path) -> Path:
    return REPO_ROOT / value.strip() if value and value.strip() else default


def llm_mode() -> str:
    """'mock' if LLM_MOCK=true, 'openrouter' if OPENROUTER_API_KEY is set, else 'unconfigured'.

    Read on every call, so /api/health and /api/chat always agree with the environment.
    """
    if os.getenv("LLM_MOCK", "").strip().lower() in TRUE_VALUES:
        return "mock"
    if os.getenv("OPENROUTER_API_KEY", "").strip():
        return "openrouter"
    return "unconfigured"


def _is_true(value: str | None) -> bool:
    return (value or "").strip().lower() in TRUE_VALUES


# --- Live talk ("charla") settings, read on every call like llm_mode() -------------------------

_DEV_CHARLA_SECRET = secrets.token_hex(32)  # links stop working on restart; set CHARLA_SECRET in production


def charla_admin_key() -> str:
    """The presenter's key. Empty means the admin API answers 503."""
    return os.getenv("CHARLA_ADMIN_KEY", "").strip()


def charla_secret() -> str:
    """HMAC key for link tokens, pending secrets and session tokens."""
    return os.getenv("CHARLA_SECRET", "").strip() or _DEV_CHARLA_SECRET


def resend_settings() -> tuple[str, str]:
    """(api_key, from_address). An empty key means emails are logged instead of sent."""
    sender = os.getenv("CHARLA_EMAIL_FROM", "").strip() or "IA Revolutions <onboarding@resend.dev>"
    return os.getenv("RESEND_API_KEY", "").strip(), sender


def charla_email_rps() -> float:
    try:
        return max(0.2, float(os.getenv("CHARLA_EMAIL_RPS", "2")))
    except ValueError:
        return 2.0


def charla_phone_at() -> time | None:
    """Bogotá wall-clock time when the WhatsApp prompt appears by itself ("HH:MM"); "off" disables it."""
    value = os.getenv("CHARLA_PHONE_AT", "15:50").strip().lower()
    if value in {"", "off", "none", "false"}:
        return None
    try:
        hours, minutes = value.split(":")
        return time(int(hours), int(minutes))
    except ValueError:
        return None


def charla_dev_links() -> bool:
    """Return the link token in the register response (tests only). Never when Resend is configured."""
    return _is_true(os.getenv("CHARLA_DEV_LINKS")) and not resend_settings()[0]


def charla_public_url() -> str:
    """Origin used in email links, e.g. https://x.up.railway.app. Empty: derive it from the request."""
    return os.getenv("CHARLA_PUBLIC_URL", "").strip().rstrip("/")
