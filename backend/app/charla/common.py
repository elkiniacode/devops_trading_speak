"""Helpers shared by every charla module (CONTRACT.md §4.1).

Call the clock as ``common.now_ms()`` (module attribute), never ``from .common import now_ms``:
tests monkeypatch it to control time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from fastapi import HTTPException, Request

from app.config import charla_admin_key, charla_secret
from app.db.connection import connect, now_iso


def now_ms() -> int:
    """Wall clock in epoch milliseconds."""
    return int(time.time() * 1000)


def new_secret() -> str:
    """A random URL-safe secret (link tokens, pending secrets, session tokens)."""
    return secrets.token_urlsafe(32)


def hash_secret(value: str) -> str:
    """What we store instead of a secret: HMAC-SHA256 keyed with CHARLA_SECRET."""
    return hmac.new(charla_secret().encode(), value.encode(), hashlib.sha256).hexdigest()


class Bus:
    """Version counters the SSE streams poll.

    ``public_version`` changes when what phones see changes (room state, reveals).
    ``admin_version`` changes on every change, including registrations, answers and themes.
    """

    def __init__(self) -> None:
        self.public_version = 0
        self.admin_version = 0

    def bump(self, *, public: bool = True) -> None:
        self.admin_version += 1
        if public:
            self.public_version += 1


bus = Bus()


def ensure_state_row() -> None:
    """Create the single charla_state row (id = 1) if it is missing."""
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO charla_state (id, updated_at) VALUES (1, ?)", (now_iso(),))


def verification_on() -> bool:
    """Whether registration requires the email link (the presenter's kill switch turns it off)."""
    with connect() as conn:
        row = conn.execute("SELECT verification_on FROM charla_state WHERE id = 1").fetchone()
    return True if row is None else bool(row["verification_on"])


def bearer_token(request: Request) -> str | None:
    """The attendee's session token: ``Authorization: Bearer <t>``, or ``?t=`` (EventSource can't set headers)."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
        if token:
            return token
    return request.query_params.get("t") or None


def require_admin(request: Request) -> None:
    """FastAPI dependency for /api/charla/admin/*: ``X-Admin-Key`` header or ``?key=``."""
    expected = charla_admin_key()
    if not expected:
        raise HTTPException(503, "El panel no está configurado: falta CHARLA_ADMIN_KEY.")
    given = request.headers.get("x-admin-key") or request.query_params.get("key") or ""
    if not hmac.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(401, "Clave de presentador incorrecta.")
