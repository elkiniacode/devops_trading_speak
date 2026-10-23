"""Room endpoints (CONTRACT.md §5.6–§5.9, §6.3, §7): the attendee stream, answers, phone and the presenter API.

The streams follow app/market/stream.py: a ``retry`` line, then a poll every 0.5 s that sends the
view whenever the bus version moves, with a keepalive comment every 15 s.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.charla import accounts, classify, common, room

router = APIRouter()

PUSH_INTERVAL = 0.5  # seconds between version checks
HEARTBEAT_INTERVAL = 15.0  # comment line so proxies don't close an idle stream
ADMIN_OPEN_REFRESH = 1.0  # resend the admin view at least this often while a question is open
RETRY_LINE = "retry: 2000\n\n"  # EventSource reconnect delay, ms
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
OK = {"ok": True}
ADMIN = [Depends(common.require_admin)]
RESET_CONFIRM = "Escribe RESET para confirmar."

_background: set[asyncio.Task] = set()  # keeps fire-and-forget tasks referenced until they finish


class AnswerBody(BaseModel):
    step: int
    choice: int | None = None
    text: str | None = None


class PhoneBody(BaseModel):
    phone: str | None = None
    consent: bool = False
    skip: bool = False


class GotoBody(BaseModel):
    step: int


class VerificationBody(BaseModel):
    on: bool


class HideBody(BaseModel):
    answer_id: str | None = None
    attendee_id: str | None = None
    hidden: bool = True


class ResetBody(BaseModel):
    confirm: str = ""


def sse_data(payload: dict) -> str:
    """One SSE data event (compact JSON, UTF-8 kept as is)."""
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


# --- attendee ----------------------------------------------------------------------------------


@router.get("/api/charla/stream")
async def attendee_stream(request: Request) -> StreamingResponse:
    """§6.1 views for one attendee (token in ``?t=`` since EventSource can't send headers)."""
    attendee = accounts.attendee_for_token(common.bearer_token(request))
    if attendee is None:
        raise HTTPException(401, accounts.SESSION_EXPIRED)
    return StreamingResponse(
        attendee_events(request, attendee), media_type="text/event-stream", headers=SSE_HEADERS
    )


async def attendee_events(request: Request, attendee: sqlite3.Row) -> AsyncIterator[str]:
    """Send the view now, then whenever the room changes or this attendee answers or gives a phone."""
    yield RETRY_LINE
    sent: tuple[int, int] | None = None
    last_write = time.monotonic()
    while not await request.is_disconnected():
        version = (common.bus.public_version, room.attendee_version(attendee["id"]))
        if version != sent:
            sent = version
            yield sse_data(room.public_view(attendee))
            last_write = time.monotonic()
        elif time.monotonic() - last_write >= HEARTBEAT_INTERVAL:
            yield ": keepalive\n\n"
            last_write = time.monotonic()
        await asyncio.sleep(PUSH_INTERVAL)


@router.post("/api/charla/answer")
async def answer(body: AnswerBody, attendee: sqlite3.Row = Depends(accounts.current_attendee)) -> dict:
    room.submit_answer(attendee["id"], body.step, body.choice, body.text)
    return {"accepted": True}  # never says whether it was right (§5.7)


@router.post("/api/charla/phone")
async def phone(body: PhoneBody, attendee: sqlite3.Row = Depends(accounts.current_attendee)) -> dict:
    room.submit_phone(attendee["id"], body.phone, body.consent, body.skip)
    return OK


# --- presenter ---------------------------------------------------------------------------------


@router.post("/api/charla/admin/launch", dependencies=ADMIN)
async def admin_launch() -> dict:
    room.launch()
    return OK


@router.post("/api/charla/admin/close", dependencies=ADMIN)
async def admin_close() -> dict:
    room.close()
    return OK


@router.post("/api/charla/admin/reveal", dependencies=ADMIN)
async def admin_reveal() -> dict:
    room.reveal()
    return OK


@router.post("/api/charla/admin/next", dependencies=ADMIN)
async def admin_next() -> dict:
    room.next_step()
    return OK


@router.post("/api/charla/admin/goto", dependencies=ADMIN)
async def admin_goto(body: GotoBody) -> dict:
    room.goto(body.step)
    return OK


@router.post("/api/charla/admin/reset-step", dependencies=ADMIN)
async def admin_reset_step() -> dict:
    room.reset_step()
    return OK


@router.post("/api/charla/admin/phone-now", dependencies=ADMIN)
async def admin_phone_now() -> dict:
    room.phone_now()
    return OK


@router.post("/api/charla/admin/reclassify", dependencies=ADMIN)
async def admin_reclassify() -> dict:
    """Classify open answers still without a theme; themes arrive over the admin stream."""
    task = asyncio.create_task(classify.reclassify_pending(), name="charla-reclassify")
    _background.add(task)
    task.add_done_callback(_background.discard)
    return OK


@router.post("/api/charla/admin/verification", dependencies=ADMIN)
async def admin_verification(body: VerificationBody) -> dict:
    room.set_verification(body.on)
    return OK


@router.post("/api/charla/admin/hide", dependencies=ADMIN)
async def admin_hide(body: HideBody) -> dict:
    room.set_hidden(answer_id=body.answer_id, attendee_id=body.attendee_id, hidden=body.hidden)
    return OK


@router.post("/api/charla/admin/reset", dependencies=ADMIN)
async def admin_reset(body: ResetBody) -> dict:
    if body.confirm != "RESET":
        raise HTTPException(400, RESET_CONFIRM)
    room.reset_all()
    return OK


@router.get("/api/charla/admin/stream", dependencies=ADMIN)
async def admin_stream(request: Request) -> StreamingResponse:
    return StreamingResponse(admin_events(request), media_type="text/event-stream", headers=SSE_HEADERS)


async def admin_events(request: Request) -> AsyncIterator[str]:
    """§6.2 views: on every admin bus change, and at least every second while a question is open."""
    yield RETRY_LINE
    sent = -1
    question_open = False
    last_data = last_write = time.monotonic()
    while not await request.is_disconnected():
        now = time.monotonic()
        if common.bus.admin_version != sent or (question_open and now - last_data >= ADMIN_OPEN_REFRESH):
            sent = common.bus.admin_version
            view = room.admin_view()
            question_open = view["state"]["phase"] == "open"
            yield sse_data(view)
            last_data = last_write = now
        elif now - last_write >= HEARTBEAT_INTERVAL:
            yield ": keepalive\n\n"
            last_write = now
        await asyncio.sleep(PUSH_INTERVAL)


@router.get("/api/charla/admin/export.csv", dependencies=ADMIN)
async def admin_export() -> Response:
    return Response(
        room.export_csv().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{room.csv_filename()}"'},
    )
