"""Usernames, registration, one-tap email links and sessions (planning/charla/CONTRACT.md §4.2).

Every time comes from ``common.now_ms()`` so tests can move the clock. Times are stored as
fixed-width UTC ISO strings (``2026-10-23T20:00:00.000Z``) and converted back to ms to compare.
Secrets (link, pending, session) are stored only as ``common.hash_secret()``.
"""

from __future__ import annotations

import math
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone

from fastapi import HTTPException, Request

from app.charla import common
from app.charla import email as mailer
from app.config import charla_dev_links
from app.db.connection import connect, new_id, transaction

LINK_TTL_MS = 30 * 60 * 1000  # a link, and the pending that waits for it, lives 30 min after the last register
RESEND_COOLDOWN_MS = 30 * 1000
SEND_WINDOW_MS = 60 * 60 * 1000
SENDS_PER_WINDOW = 5
USERNAME_MIN, USERNAME_MAX = 2, 24
EMAIL_MAX = 254

USERNAME_RE = re.compile(r"[\w .\-]+")  # \w is Unicode-aware: letters (accents, ñ), digits and _
EMAIL_RE = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]{2,}")

MSG_LENGTH = "Usa entre 2 y 24 caracteres."
MSG_CHARS = "Usa solo letras, números, espacios, punto, guion o guion bajo."
MSG_EMAIL = "Revisa el correo: necesitamos uno válido para el enlace."
MSG_TOO_MANY = "Ya pediste varios enlaces. Intenta en unos minutos."
MSG_PENDING = "Este registro expiró. Vuelve a escribir tu correo."
MSG_LINK = "Este enlace expiró o no es válido. Pide uno nuevo."
SESSION_EXPIRED = "Tu sesión expiró. Vuelve a registrarte."


# --- usernames ---------------------------------------------------------------------------------


def clean_username(raw: str) -> str:
    """The name as shown: composed accents (NFC), trimmed, inner whitespace collapsed to one space."""
    return " ".join(unicodedata.normalize("NFC", raw or "").split())


def normalize_username(raw: str) -> str:
    """Uniqueness key: accents stripped (NFKD minus combining marks), casefolded, spaces collapsed."""
    decomposed = unicodedata.normalize("NFKD", clean_username(raw))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.casefold().split())


def username_error(raw: str) -> str | None:
    """The §5.1 Spanish message for an invalid name, or None."""
    name = clean_username(raw)
    if not USERNAME_MIN <= len(name) <= USERNAME_MAX:
        return MSG_LENGTH
    if not USERNAME_RE.fullmatch(name):
        return MSG_CHARS
    return None


def taken_message(suggestion: str | None) -> str:
    if suggestion:
        return f"Ese nombre ya está en uso. Prueba con otro, por ejemplo «{suggestion}»."
    return "Ese nombre ya está en uso. Prueba con otro."


def check_username(raw: str, email: str | None = None) -> dict:
    """§5.1 body. ``email`` lets someone re-registering keep their own name."""
    error = username_error(raw)
    if error:
        return {"valid": False, "available": False, "message": error, "suggestion": None}
    name = clean_username(raw)
    owner_email = clean_email(email) if email else None
    now = common.now_ms()
    with connect() as conn:
        if _name_free(conn, normalize_username(name), owner_email, now):
            return {"valid": True, "available": True, "message": None, "suggestion": None}
        suggestion = _suggest(conn, name, owner_email, now)
    return {"valid": True, "available": False, "message": taken_message(suggestion), "suggestion": suggestion}


def _is_active(conn: sqlite3.Connection, row: sqlite3.Row, now: int) -> bool:
    """Verified, or has a session, or still has an unexpired link (§4.2)."""
    if row["verified_at"] or _alive(row["link_expires_at"], now):
        return True
    return conn.execute("SELECT 1 FROM charla_sessions WHERE attendee_id = ? LIMIT 1", (row["id"],)).fetchone() is not None


def _name_free(conn: sqlite3.Connection, key: str, email: str | None, now: int) -> bool:
    row = conn.execute("SELECT * FROM charla_attendees WHERE username_key = ?", (key,)).fetchone()
    return row is None or row["email"] == email or not _is_active(conn, row, now)


def _suggest(conn: sqlite3.Connection, name: str, email: str | None, now: int) -> str | None:
    """The first free ``<name>2`` … ``<name>99`` that fits in 24 characters."""
    for n in range(2, 100):
        suffix = str(n)
        candidate = clean_username(name[: USERNAME_MAX - len(suffix)] + suffix)
        if username_error(candidate) is None and _name_free(conn, normalize_username(candidate), email, now):
            return candidate
    return None


# --- registration and links --------------------------------------------------------------------


def clean_email(raw: str | None) -> str:
    return (raw or "").strip().lower()


def register(username: str, email: str, *, base_url: str) -> dict:
    """§5.2: claim the name for this email, then send a one-tap link (or let them in if verification is off)."""
    error = username_error(username)
    if error:
        raise HTTPException(400, error)
    name = clean_username(username)
    key = normalize_username(name)
    email = clean_email(email)
    if len(email) > EMAIL_MAX or not EMAIL_RE.fullmatch(email):
        raise HTTPException(400, MSG_EMAIL)

    verify = common.verification_on()
    now = common.now_ms()
    link: str | None = None
    with transaction() as conn:
        holder = conn.execute("SELECT * FROM charla_attendees WHERE username_key = ?", (key,)).fetchone()
        if holder is not None and holder["email"] != email:
            if _is_active(conn, holder, now):
                raise HTTPException(409, taken_message(_suggest(conn, name, email, now)))
            conn.execute("DELETE FROM charla_attendees WHERE id = ?", (holder["id"],))  # stale reservation

        row = conn.execute("SELECT * FROM charla_attendees WHERE email = ?", (email,)).fetchone()
        if row is None:
            attendee_id = new_id()
            conn.execute(
                "INSERT INTO charla_attendees (id, username, username_key, email, created_at) VALUES (?, ?, ?, ?, ?)",
                (attendee_id, name, key, email, _iso(now)),
            )
        else:
            attendee_id = row["id"]
            conn.execute(
                "UPDATE charla_attendees SET username = ?, username_key = ? WHERE id = ?", (name, key, attendee_id)
            )

        if not verify:  # the presenter's kill switch: straight in, still unverified
            token = _new_session(conn, attendee_id, now)
            result: dict = {"status": "in", "token": token, "username": name}
        else:
            sends_count, window_start = _check_send_limits(row, now)
            link_token, pending = common.new_secret(), common.new_secret()
            conn.execute(
                "UPDATE charla_attendees SET link_hash = ?, link_expires_at = ?, link_sent_at = ?,"
                " sends_count = ?, sends_window_start = ?, pending_hash = ?, pending_approved_at = NULL"
                " WHERE id = ?",
                (
                    common.hash_secret(link_token),
                    _iso(now + LINK_TTL_MS),
                    _iso(now),
                    sends_count,
                    _iso(window_start),
                    common.hash_secret(pending),
                    attendee_id,
                ),
            )
            result = {
                "status": "link_sent",
                "pending": pending,
                "email": email,
                "username": name,
                "resend_in_s": RESEND_COOLDOWN_MS // 1000,
            }
            if charla_dev_links():
                result["dev_link_token"] = link_token
            link = f"{base_url.rstrip('/')}/charla/entrar/#v={link_token}"

    if link:
        mailer.outbox.enqueue(email, name, link)
    common.bus.bump(public=False)
    return result


def _check_send_limits(row: sqlite3.Row | None, now: int) -> tuple[int, int]:
    """Raise 429 inside the 30 s cooldown or past 5 sends this hour; else (new sends_count, window start ms)."""
    if row is None:
        return 1, now
    if row["link_sent_at"]:
        wait_ms = _ms(row["link_sent_at"]) + RESEND_COOLDOWN_MS - now
        if wait_ms > 0:
            raise HTTPException(429, f"Espera {max(1, math.ceil(wait_ms / 1000))} s para pedir otro enlace.")
    if not row["sends_window_start"] or now - _ms(row["sends_window_start"]) >= SEND_WINDOW_MS:
        return 1, now
    if row["sends_count"] >= SENDS_PER_WINDOW:
        raise HTTPException(429, MSG_TOO_MANY)
    return row["sends_count"] + 1, _ms(row["sends_window_start"])


def pending_status(pending: str) -> dict:
    """§5.3: the registering tab polls this; once the link is opened it gets its own new session.

    If the presenter turns verification off while someone waits, they are let in too (unverified).
    """
    now = common.now_ms()
    with connect() as conn:
        row = None
        if pending:
            row = conn.execute(
                "SELECT * FROM charla_attendees WHERE pending_hash = ?", (common.hash_secret(pending),)
            ).fetchone()
    if row is None or not _alive(row["link_expires_at"], now):
        raise HTTPException(404, MSG_PENDING)
    if row["pending_approved_at"] is None and common.verification_on():
        return {"status": "waiting"}
    with transaction() as conn:
        token = _new_session(conn, row["id"], now)
    common.bus.bump(public=False)
    return {"status": "in", "token": token, "username": row["username"]}


def verify_link(link_token: str) -> dict:
    """§5.4: the email's button. Reusable until it expires; every call opens a new session."""
    now = common.now_ms()
    with transaction() as conn:
        row = None
        if link_token:
            row = conn.execute(
                "SELECT * FROM charla_attendees WHERE link_hash = ?", (common.hash_secret(link_token),)
            ).fetchone()
        if row is None or not _alive(row["link_expires_at"], now):
            raise HTTPException(400, MSG_LINK)
        stamp = _iso(now)
        conn.execute(
            "UPDATE charla_attendees SET verified_at = COALESCE(verified_at, ?),"
            " pending_approved_at = COALESCE(pending_approved_at, ?) WHERE id = ?",
            (stamp, stamp, row["id"]),
        )
        token = _new_session(conn, row["id"], now)
    common.bus.bump(public=False)
    return {"token": token, "username": row["username"]}


# --- sessions ----------------------------------------------------------------------------------


def _new_session(conn: sqlite3.Connection, attendee_id: str, now: int) -> str:
    token = common.new_secret()
    conn.execute(
        "INSERT INTO charla_sessions (id, attendee_id, token_hash, created_at) VALUES (?, ?, ?, ?)",
        (new_id(), attendee_id, common.hash_secret(token), _iso(now)),
    )
    return token


def attendee_for_token(token: str | None) -> sqlite3.Row | None:
    """The attendee a session token belongs to, or None."""
    if not token:
        return None
    with connect() as conn:
        return conn.execute(
            "SELECT a.* FROM charla_sessions s JOIN charla_attendees a ON a.id = s.attendee_id"
            " WHERE s.token_hash = ?",
            (common.hash_secret(token),),
        ).fetchone()


def current_attendee(request: Request) -> sqlite3.Row:
    """FastAPI dependency: the attendee behind the Bearer token (or ``?t=``); 401 otherwise."""
    attendee = attendee_for_token(common.bearer_token(request))
    if attendee is None:
        raise HTTPException(401, SESSION_EXPIRED)
    return attendee


def reset_accounts() -> None:
    """Delete every attendee and session (their answers go with them: ON DELETE CASCADE)."""
    with transaction() as conn:
        conn.execute("DELETE FROM charla_sessions")
        conn.execute("DELETE FROM charla_attendees")


# --- time helpers ------------------------------------------------------------------------------


def _iso(ms: int) -> str:
    """Epoch ms -> '2026-10-23T20:00:00.123Z' (exact to the millisecond)."""
    moment = datetime.fromtimestamp(ms // 1000, tz=timezone.utc).replace(microsecond=ms % 1000 * 1000)
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _ms(iso: str) -> int:
    moment = datetime.fromisoformat(iso)
    return int(moment.replace(microsecond=0).timestamp()) * 1000 + moment.microsecond // 1000


def _alive(expires_at: str | None, now: int) -> bool:
    return bool(expires_at) and now < _ms(expires_at)
