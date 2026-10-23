"""Live-talk accounts: usernames, registration, one-tap links and /me (planning/charla/CONTRACT.md §5.1–§5.5)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.charla import accounts
from app.config import charla_public_url

router = APIRouter()


class RegisterBody(BaseModel):
    # Defaults instead of required fields, so a missing value gets the Spanish 400, not a 422.
    username: str = ""
    email: str = ""


class VerifyBody(BaseModel):
    v: str = ""


def link_base(request: Request) -> str:
    """Origin for email links: CHARLA_PUBLIC_URL, else this request's base URL.

    Behind an HTTPS proxy (Railway) uvicorn may see plain http; trust X-Forwarded-Proto for the
    scheme only (never a forwarded host, which would let anyone point links elsewhere).
    """
    configured = charla_public_url()
    if configured:
        return configured
    base = str(request.base_url).rstrip("/")
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    if proto == "https" and base.startswith("http://"):
        base = "https://" + base[len("http://"):]
    return base


@router.get("/api/charla/username")
async def check_username(u: str = "", email: str | None = None) -> dict:
    return accounts.check_username(u, email)


@router.post("/api/charla/register")
async def register(body: RegisterBody, request: Request) -> dict:
    return accounts.register(body.username, body.email, base_url=link_base(request))


@router.get("/api/charla/register/status")
async def register_status(p: str = "") -> dict:
    return accounts.pending_status(p)


@router.post("/api/charla/verify")
async def verify(body: VerifyBody) -> dict:
    return accounts.verify_link(body.v)


@router.get("/api/charla/me")
async def me(attendee: sqlite3.Row = Depends(accounts.current_attendee)) -> dict:
    from app.charla import room  # owned by backend-room; imported late so this module loads without it

    return room.public_view(attendee)
