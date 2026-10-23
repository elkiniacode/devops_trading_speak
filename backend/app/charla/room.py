"""The room: the quiz state machine, scoring, ranking, views and the CSV export (CONTRACT.md §4.4, §6, §7).

All room state lives in the single ``charla_state`` row, so it survives a restart. Every function
here is synchronous and runs on the shared connection; the async routes call them directly, so a
check and the write that follows it can't interleave with another request.

Read the clock as ``common.now_ms()`` (tests move it).
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import sqlite3
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.config import charla_phone_at
from app.db.connection import connect, new_id, now_iso, transaction

from . import accounts, classify, common, content
from .email import outbox

logger = logging.getLogger(__name__)

BOGOTA = ZoneInfo("America/Bogota")
TICK_SECONDS = 0.25
RANKING_LIMIT = 100
OPEN_MIN_CHARS = 8
LETTERS = "ABCD"

# Messages (§5.7–§5.9)
ALREADY_OPEN = "La pregunta ya está abierta."
ALREADY_LAUNCHED = "Esta pregunta ya se lanzó. Usa reiniciar pregunta."
CLOSE_FIRST = "Primero cierra la pregunta."
NOT_OPEN = "No hay pregunta abierta."
QUESTION_CLOSED = "La pregunta ya está cerrada."
ALREADY_ANSWERED = "Ya respondiste esta pregunta."
BAD_CHOICE = "Elige una opción válida."
SHORT_TEXT = "Escribe al menos 8 caracteres."
LONG_TEXT = f"Escribe máximo {content.OPEN_MAX_CHARS} caracteres."
BAD_PHONE = "Escribe un celular colombiano de 10 dígitos."
NO_CONSENT = "Necesitamos tu autorización para escribirte por WhatsApp."
BAD_STEP = "Ese paso no existe."
HIDE_TARGET = "Indica la respuesta o la persona que quieres ocultar."
NOT_FOUND = "No encontramos ese registro."

# An attendee is in the room once verified or holding a session (verification off).
ACTIVE = "(a.verified_at IS NOT NULL OR EXISTS (SELECT 1 FROM charla_sessions s WHERE s.attendee_id = a.id))"

_attendee_versions: dict[str, int] = {}  # bumped on an attendee's own answer/phone; their stream resends `me`


# --- state row ---------------------------------------------------------------------------------


def _state(conn: sqlite3.Connection) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM charla_state WHERE id = 1").fetchone()
    if row is None:  # startup() creates it; be forgiving if something runs first
        common.ensure_state_row()
        row = conn.execute("SELECT * FROM charla_state WHERE id = 1").fetchone()
    return row


def _load_state() -> sqlite3.Row:
    with connect() as conn:
        return _state(conn)


def _write_state(conn: sqlite3.Connection, **fields: Any) -> None:
    fields["updated_at"] = now_iso()
    columns = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(f"UPDATE charla_state SET {columns} WHERE id = 1", tuple(fields.values()))


def _set_state(**fields: Any) -> None:
    """Write state fields and tell every phone (public bump)."""
    with connect() as conn:
        _write_state(conn, **fields)
    common.bus.bump()


def attendee_version(attendee_id: str) -> int:
    return _attendee_versions.get(attendee_id, 0)


def _bump_attendee(attendee_id: str) -> None:
    _attendee_versions[attendee_id] = _attendee_versions.get(attendee_id, 0) + 1


def _expired(state: sqlite3.Row, now: int) -> bool:
    """Past the deadline plus the grace window (answers in flight still count until then)."""
    deadline = state["deadline_ms"]
    return deadline is None or now >= deadline + content.GRACE_MS


# --- lifecycle ---------------------------------------------------------------------------------


def startup() -> None:
    """Create the state row; a question left open past its deadline (server was down) becomes closed."""
    common.ensure_state_row()
    state = _load_state()
    if state["phase"] == "open" and _expired(state, common.now_ms()):
        _set_state(phase="closed")


async def tick_loop() -> None:
    """Background task: tick() every 0.25 s for the life of the app."""
    while True:
        try:
            tick()
        except Exception:
            logger.exception("charla tick failed")
        await asyncio.sleep(TICK_SECONDS)


def tick() -> None:
    """Close the open question once its time (plus grace) is up; raise the WhatsApp prompt on time."""
    state = _load_state()
    now = common.now_ms()
    if state["phase"] == "open" and _expired(state, now):
        _set_state(phase="closed")
    if not state["phone_prompt"] and _phone_time_reached(now):
        _set_state(phone_prompt=1)


def _phone_time_reached(now: int) -> bool:
    at = charla_phone_at()
    if at is None:
        return False
    return datetime.fromtimestamp(now / 1000, BOGOTA).time() >= at


# --- presenter transitions (§4.4, §5.9) --------------------------------------------------------


def launch() -> None:
    """idle -> open with a fresh deadline. At the closing step it raises the WhatsApp prompt instead."""
    state = _load_state()
    step = state["step"]
    if content.kind_of(step) == "closing":
        _set_state(phone_prompt=1)
        return
    if state["phase"] == "open":
        raise HTTPException(409, ALREADY_OPEN)
    if state["phase"] != "idle":
        raise HTTPException(409, ALREADY_LAUNCHED)
    now = common.now_ms()
    _set_state(phase="open", opened_at_ms=now, deadline_ms=now + (content.duration_ms(step) or 0))


def close() -> None:
    if _load_state()["phase"] != "open":
        raise HTTPException(409, NOT_OPEN)
    _set_state(phase="closed")


def reveal() -> None:
    phase = _load_state()["phase"]
    if phase == "open":
        raise HTTPException(409, CLOSE_FIRST)
    if phase == "idle":
        raise HTTPException(409, NOT_OPEN)
    if phase == "closed":  # when already revealed, pressing R again does nothing
        _set_state(phase="revealed")


def next_step() -> None:
    state = _load_state()
    _move_to(min(state["step"] + 1, content.CLOSING_STEP), state)


def goto(step: int) -> None:
    """Jump to any step (answers are kept)."""
    if not 0 <= step <= content.CLOSING_STEP:
        raise HTTPException(400, BAD_STEP)
    _move_to(step, _load_state())


def _move_to(step: int, state: sqlite3.Row) -> None:
    if state["phase"] == "open":
        raise HTTPException(409, CLOSE_FIRST)
    _set_state(step=step, phase="idle", opened_at_ms=None, deadline_ms=None)


def reset_step() -> None:
    """Delete the current step's answers and put it back to idle, ready to launch again."""
    with transaction() as conn:
        step = _state(conn)["step"]
        conn.execute("DELETE FROM charla_answers WHERE step = ?", (step,))
        _write_state(conn, phase="idle", opened_at_ms=None, deadline_ms=None)
    common.bus.bump()


def phone_now() -> None:
    _set_state(phone_prompt=1)


def set_verification(on: bool) -> None:
    _set_state(verification_on=int(on))


def set_hidden(*, answer_id: str | None, attendee_id: str | None, hidden: bool) -> None:
    """Hide a quote (answer) or a person (quotes and projected ranking) from the projection."""
    if answer_id:
        table, key = "charla_answers", answer_id
    elif attendee_id:
        table, key = "charla_attendees", attendee_id
    else:
        raise HTTPException(400, HIDE_TARGET)
    with connect() as conn:
        updated = conn.execute(f"UPDATE {table} SET hidden = ? WHERE id = ?", (int(hidden), key)).rowcount
    if not updated:
        raise HTTPException(404, NOT_FOUND)
    # Hiding a person changes everyone's rank, so phones refresh too; a hidden quote is presenter-only.
    common.bus.bump(public=table == "charla_attendees")


def reset_all() -> None:
    """Start over: no attendees, no answers, step 0 idle, verification on, no phone prompt."""
    with transaction() as conn:
        conn.execute("DELETE FROM charla_answers")
        _write_state(
            conn, step=0, phase="idle", opened_at_ms=None, deadline_ms=None, verification_on=1, phone_prompt=0
        )
    accounts.reset_accounts()
    _attendee_versions.clear()
    common.bus.bump()


# --- attendee actions (§5.7, §5.8) -------------------------------------------------------------


def submit_answer(attendee_id: str, step: int, choice: int | None, text: str | None) -> None:
    """Store an answer to the open question. Points are fixed now but only shown once settled."""
    state = _load_state()
    now = common.now_ms()
    if step != state["step"] or state["phase"] != "open" or now > (state["deadline_ms"] or 0) + content.GRACE_MS:
        raise HTTPException(409, QUESTION_CLOSED)
    kind = content.kind_of(step)
    elapsed = max(0, now - (state["opened_at_ms"] or now))
    open_text: str | None = None
    if kind in ("quiz", "poll"):
        options = content.SCRIPT[step].options
        if not isinstance(choice, int) or isinstance(choice, bool) or not 0 <= choice < len(options):
            raise HTTPException(400, BAD_CHOICE)
        correct = choice == content.SCRIPT[step].answer
        points = content.quiz_points(correct, elapsed) if kind == "quiz" else 0
    else:  # an open question (the closing step never opens)
        open_text = (text or "").strip()
        if len(open_text) < OPEN_MIN_CHARS:
            raise HTTPException(400, SHORT_TEXT)
        if len(open_text) > content.OPEN_MAX_CHARS:
            raise HTTPException(400, LONG_TEXT)
        choice, correct, points = None, False, content.OPEN_POINTS

    answer_id = new_id()
    with connect() as conn:
        if conn.execute(
            "SELECT 1 FROM charla_answers WHERE attendee_id = ? AND step = ?", (attendee_id, step)
        ).fetchone():
            raise HTTPException(409, ALREADY_ANSWERED)
        try:
            conn.execute(
                "INSERT INTO charla_answers (id, attendee_id, step, choice, open_text, correct, points, ms, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (answer_id, attendee_id, step, choice, open_text, int(correct), points, elapsed, now_iso()),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, ALREADY_ANSWERED) from None
    common.bus.bump(public=False)
    _bump_attendee(attendee_id)
    if step == content.THEMED_STEP:
        _schedule_classify(answer_id)


def _schedule_classify(answer_id: str) -> None:
    """Theme classification runs in the background and must never fail the answer."""
    try:
        classify.schedule(answer_id)
    except Exception:  # reclassify_pending() picks it up at the next startup or "reclassify"
        logger.warning("Could not schedule theme classification for %s", answer_id, exc_info=True)


def submit_phone(attendee_id: str, phone: str | None, consent: bool, skip: bool) -> None:
    """Save the WhatsApp number (10 digits starting with 3, consent required) or record a skip."""
    with connect() as conn:
        if skip:
            conn.execute("UPDATE charla_attendees SET phone_skipped_at = ? WHERE id = ?", (now_iso(), attendee_id))
        else:
            digits = re.sub(r"\D", "", phone or "")
            if len(digits) == 12 and digits.startswith("57"):  # typed with the +57 country code
                digits = digits[2:]
            if len(digits) != 10 or not digits.startswith("3"):
                raise HTTPException(400, BAD_PHONE)
            if not consent:
                raise HTTPException(400, NO_CONSENT)
            conn.execute(
                "UPDATE charla_attendees SET phone = ?, phone_consent_at = ?, phone_skipped_at = NULL WHERE id = ?",
                (digits, now_iso(), attendee_id),
            )
    common.bus.bump(public=False)
    _bump_attendee(attendee_id)


# --- scoring and ranking (§4.4) ----------------------------------------------------------------


def _ordered(conn: sqlite3.Connection, state: sqlite3.Row, *, settled_only: bool, active_only: bool) -> list[dict]:
    """Attendees by score desc, then total ms of correct answers asc, then registration time.

    With ``settled_only`` a step counts once it is behind the current one, or is the current one
    and revealed, so a score never leaks correctness before the reveal.
    """
    settled = "(ans.step < :step OR (ans.step = :step AND :revealed))" if settled_only else "1"
    rows = conn.execute(
        f"""SELECT a.id, a.username, a.verified_at, a.hidden, a.created_at,
                   COALESCE(SUM(CASE WHEN {settled} THEN ans.points END), 0) AS score,
                   COALESCE(SUM(CASE WHEN {settled} AND ans.correct = 1 THEN 1 END), 0) AS correct,
                   COALESCE(SUM(CASE WHEN {settled} AND ans.correct = 1 THEN ans.ms END), 0) AS correct_ms
            FROM charla_attendees a LEFT JOIN charla_answers ans ON ans.attendee_id = a.id
            WHERE {ACTIVE if active_only else "1"}
            GROUP BY a.id
            ORDER BY score DESC, correct_ms ASC, a.created_at ASC, a.id ASC""",
        {"step": state["step"], "revealed": int(state["phase"] == "revealed")},
    ).fetchall()
    return [
        {
            "attendee_id": row["id"],
            "username": row["username"],
            "score": row["score"],
            "correct": row["correct"],
            "verified": row["verified_at"] is not None,
            "hidden": bool(row["hidden"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _ranking(conn: sqlite3.Connection, state: sqlite3.Row) -> list[dict]:
    """Settled ranking of active attendees. Hidden people go last, so visible ranks run 1..n without gaps."""
    ordered = _ordered(conn, state, settled_only=True, active_only=True)
    rows = [r for r in ordered if not r["hidden"]] + [r for r in ordered if r["hidden"]]
    return [
        {"rank": i, **{k: r[k] for k in ("attendee_id", "username", "score", "correct", "verified", "hidden")}}
        for i, r in enumerate(rows, 1)
    ]


# --- views (§6) --------------------------------------------------------------------------------


def _distribution(conn: sqlite3.Connection, step: int) -> list[int]:
    counts = [0] * len(LETTERS)
    for row in conn.execute(
        "SELECT choice, COUNT(*) AS n FROM charla_answers WHERE step = ? AND choice IS NOT NULL GROUP BY choice",
        (step,),
    ):
        if 0 <= row["choice"] < len(counts):
            counts[row["choice"]] = row["n"]
    return counts


def _question(step: int) -> dict | None:
    q = content.SCRIPT[step]
    if q.kind == "closing":
        return None
    return {"text": q.text, "options": list(q.options), "placeholder": q.placeholder}


def _public_state(conn: sqlite3.Connection, state: sqlite3.Row, now: int) -> dict:
    step, phase = state["step"], state["phase"]
    kind = content.kind_of(step)
    reveal = None
    if phase == "revealed":
        if kind in ("quiz", "poll"):
            q = content.SCRIPT[step]
            reveal = {"answer": q.answer, "why": q.why, "distribution": _distribution(conn, step)}
        else:
            reveal = {"answer": None, "why": None, "distribution": None}
    remaining = None
    if phase == "open":
        remaining = max(0, (state["deadline_ms"] or now) - now)
    room_count = conn.execute(f"SELECT COUNT(*) FROM charla_attendees a WHERE {ACTIVE}").fetchone()[0]
    return {
        "version": common.bus.public_version,
        "server_now_ms": now,
        "step": step,
        "kind": kind,
        "phase": phase,
        "number": step + 1 if kind != "closing" else None,
        "total_quiz": content.QUESTION_COUNT,
        "remaining_ms": remaining,
        "duration_ms": content.duration_ms(step),
        "question": _question(step),
        "reveal": reveal,
        "phone_prompt": bool(state["phone_prompt"]),
        "room_count": room_count,
    }


def _me(conn: sqlite3.Connection, state: sqlite3.Row, attendee_id: str) -> dict | None:
    person = conn.execute("SELECT * FROM charla_attendees WHERE id = ?", (attendee_id,)).fetchone()
    if person is None:  # removed by a reset
        return None
    step, kind = state["step"], content.kind_of(state["step"])
    mine = next((r for r in _ranking(conn, state) if r["attendee_id"] == attendee_id), None)
    row = conn.execute(
        "SELECT choice, open_text, correct, points FROM charla_answers WHERE attendee_id = ? AND step = ?",
        (attendee_id, step),
    ).fetchone()
    answer = {"step": step, "choice": row["choice"], "text": row["open_text"]} if row else None
    result = None
    if state["phase"] == "revealed" and kind != "closing":
        points = row["points"] if row else 0
        correct = bool(row and row["correct"]) if kind == "quiz" else None
        result = {"correct": correct, "points": points}
    if person["phone"]:
        phone_status = "given"
    elif person["phone_skipped_at"]:
        phone_status = "skipped"
    else:
        phone_status = "none"
    return {
        "attendee_id": attendee_id,
        "username": person["username"],
        "verified": person["verified_at"] is not None,
        "score": mine["score"] if mine else 0,
        "rank": mine["rank"] if mine and not mine["hidden"] else None,
        "answer": answer,
        "result": result,
        "phone_status": phone_status,
    }


def public_view(attendee: sqlite3.Row | None) -> dict:
    """§6.1: the room state plus this attendee's own view (``me`` is null without an attendee)."""
    now = common.now_ms()
    with connect() as conn:
        state = _state(conn)
        return {
            "state": _public_state(conn, state, now),
            "me": _me(conn, state, attendee["id"]) if attendee is not None else None,
        }


def admin_view() -> dict:
    """§6.2: everything the presenter sees."""
    now = common.now_ms()
    phone_at = charla_phone_at()
    with connect() as conn:
        state = _state(conn)
        step = state["step"]
        public = _public_state(conn, state, now)
        public.update(
            verification_on=bool(state["verification_on"]),
            phone_prompt_at=phone_at.strftime("%H:%M") if phone_at else None,
            deadline_ms=state["deadline_ms"],
            opened_at_ms=state["opened_at_ms"],
        )
        people = conn.execute(
            f"""SELECT COUNT(*) AS registered,
                       COALESCE(SUM(CASE WHEN {ACTIVE} THEN 1 ELSE 0 END), 0) AS active,
                       COALESCE(SUM(a.verified_at IS NOT NULL), 0) AS verified,
                       COALESCE(SUM(a.phone IS NOT NULL), 0) AS with_phone
                FROM charla_attendees a"""
        ).fetchone()
        answers = conn.execute(
            "SELECT COUNT(*) AS answered, COALESCE(SUM(correct), 0) AS correct FROM charla_answers WHERE step = ?",
            (step,),
        ).fetchone()
        theme_counts = dict.fromkeys(content.THEMES, 0)
        for row in conn.execute(
            "SELECT theme, COUNT(*) AS n FROM charla_answers"
            " WHERE step = ? AND theme IS NOT NULL AND hidden = 0 GROUP BY theme",
            (content.THEMED_STEP,),
        ):
            name = row["theme"] if row["theme"] in theme_counts else "Otro"
            theme_counts[name] += row["n"]
        quotes = [
            {
                "answer_id": row["id"],
                "attendee_id": row["attendee_id"],
                "username": row["username"],
                "text": row["open_text"],
                "theme": row["theme"],
                "hidden": bool(row["hidden"] or row["attendee_hidden"]),
                "created_at": row["created_at"],
            }
            for row in conn.execute(
                """SELECT ans.id, ans.attendee_id, a.username, ans.open_text, ans.theme, ans.hidden,
                          a.hidden AS attendee_hidden, ans.created_at
                   FROM charla_answers ans JOIN charla_attendees a ON a.id = ans.attendee_id
                   WHERE ans.step = ? AND ans.open_text IS NOT NULL
                   ORDER BY ans.created_at DESC, ans.rowid DESC""",
                (step,),
            )
        ]
        ranking = _ranking(conn, state)[:RANKING_LIMIT]
        return {
            "version": common.bus.admin_version,
            "server_now_ms": now,
            "state": public,
            "script": [_script_step(i) for i in range(content.STEPS)],
            "counts": {
                "registered": people["registered"],
                "active": people["active"],
                "verified": people["verified"],
                "pending": people["registered"] - people["active"],
                "with_phone": people["with_phone"],
                "answered": answers["answered"],
                "correct": answers["correct"],
            },
            "distribution": _distribution(conn, step) if content.kind_of(step) in ("quiz", "poll") else None,
            "themes": [{"name": n, "count": c} for n, c in theme_counts.items()] if step == content.THEMED_STEP else [],
            "quotes": quotes,
            "ranking": ranking,
            "email": _email_stats(),
        }


def _script_step(step: int) -> dict:
    q = content.SCRIPT[step]
    return {"step": step, "kind": q.kind, "title": q.text, "options": list(q.options), "answer": q.answer, "why": q.why}


def _email_stats() -> dict:
    try:
        return outbox.stats()
    except Exception:
        logger.warning("Email stats unavailable", exc_info=True)
        return {"queued": 0, "sent": 0, "failed": 0, "last_error": None}


# --- CSV export (§7) ---------------------------------------------------------------------------

CSV_HEADER = [
    "puesto", "usuario", "correo", "verificado", "celular", "autoriza_whatsapp", "puntaje", "correctas",
    *(f"p{i}" for i in range(1, content.QUESTION_COUNT + 1)),
    "registrado",
]


def export_csv() -> str:
    """Everyone registered, ranked on all their points: UTF-8 with BOM, ';' separated, CRLF (Excel-friendly)."""
    with connect() as conn:
        state = _state(conn)
        ordered = _ordered(conn, state, settled_only=False, active_only=False)
        people = {row["id"]: row for row in conn.execute("SELECT * FROM charla_attendees")}
        answers: dict[str, dict[int, sqlite3.Row]] = {}
        for row in conn.execute("SELECT attendee_id, step, choice, correct, open_text, theme FROM charla_answers"):
            answers.setdefault(row["attendee_id"], {})[row["step"]] = row

    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_HEADER)
    for position, entry in enumerate(ordered, 1):
        person = people[entry["attendee_id"]]
        mine = answers.get(entry["attendee_id"], {})
        cells = [_answer_cell(step, mine.get(step)) for step in range(content.QUESTION_COUNT)]
        writer.writerow([
            position,
            _cell(person["username"]),
            _cell(person["email"]),
            "sí" if person["verified_at"] else "no",
            person["phone"] or "",
            "sí" if person["phone_consent_at"] else "no",
            entry["score"],
            entry["correct"],
            *cells,
            person["created_at"],
        ])
    return "﻿" + out.getvalue()


def _answer_cell(step: int, row: sqlite3.Row | None) -> str:
    """Letter for a poll, letter plus check/cross for a quiz, the text for an open question."""
    if row is None:
        return ""
    if row["choice"] is None:
        return _cell(row["open_text"] or "")
    mark = ("✓" if row["correct"] else "✗") if content.kind_of(step) == "quiz" else ""
    return LETTERS[row["choice"]] + mark


def _cell(value: str) -> str:
    """Neutralise spreadsheet formulas in free text (=, +, -, @ at the start)."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


def csv_filename() -> str:
    """charla-YYYYMMDD-HHMM.csv in Bogotá time."""
    return f"charla-{datetime.fromtimestamp(common.now_ms() / 1000, BOGOTA):%Y%m%d-%H%M}.csv"
