"""The link outbox: Resend calls, rate limit, 429 Retry-After, retries, stats and content (CONTRACT.md §4.3)."""

from __future__ import annotations

import asyncio
import json
import logging

import httpx
import pytest

from app.charla import common
from app.charla.email import RESEND_URL, EmailOutbox, compose

LINK = "https://charla.example.com/charla/entrar/#v=abc-123_x"


@pytest.fixture
def resend_env(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("CHARLA_EMAIL_FROM", "IA Revolutions <charla@iarevolutions.co>")
    monkeypatch.delenv("CHARLA_EMAIL_RPS", raising=False)


class FakeResend:
    """A MockTransport handler that answers from a script and records every request."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        reply = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(reply, Exception):
            raise reply
        return reply


def make_outbox(handler: FakeResend) -> tuple[EmailOutbox, list[float]]:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return EmailOutbox(transport=httpx.MockTransport(handler), sleep=fake_sleep), sleeps


def test_email_content():
    subject, html, text = compose("José <P>", LINK)
    assert subject == "Entra a la charla, José <P>"
    assert "José &lt;P&gt;" in html and "<P>" not in html
    for piece in (
        "Un toque y entras a la sala",
        "ENTRAR A LA SALA",
        "#070909",
        "#5eead4",
        "https://charla.example.com/charla/logo.png",
        f'href="{LINK}"',
        "Si no fuiste tú, ignora este correo.",
    ):
        assert piece in html, piece
    assert "<table" in html and "<style" not in html  # email-safe: tables and inline styles only
    assert LINK in text and "Si no fuiste tú, ignora este correo." in text


async def test_without_key_the_link_is_logged_and_counted(monkeypatch, caplog):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    handler = FakeResend(httpx.Response(500))
    outbox, sleeps = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    assert outbox.stats() == {"queued": 1, "sent": 0, "failed": 0, "last_error": None}

    with caplog.at_level(logging.INFO, logger="app.charla.email"):
        await outbox.drain()
    assert f"CHARLA LINK for ana@empresa.com: {LINK}" in caplog.text
    assert outbox.stats() == {"queued": 0, "sent": 1, "failed": 0, "last_error": None}
    assert handler.requests == [] and sleeps == []


async def test_sends_through_resend(resend_env):
    handler = FakeResend(httpx.Response(200, json={"id": "email-1"}))
    outbox, sleeps = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    await outbox.drain()

    assert outbox.stats() == {"queued": 0, "sent": 1, "failed": 0, "last_error": None}
    (request,) = handler.requests
    assert str(request.url) == RESEND_URL and request.method == "POST"
    assert request.headers["authorization"] == "Bearer re_test"
    payload = json.loads(request.content)
    assert payload["from"] == "IA Revolutions <charla@iarevolutions.co>"
    assert payload["to"] == ["ana@empresa.com"]
    assert payload["subject"] == "Entra a la charla, Ana"
    assert LINK in payload["html"] and LINK in payload["text"]
    assert sleeps == [0.5]  # CHARLA_EMAIL_RPS defaults to 2


async def test_rate_follows_charla_email_rps(resend_env, monkeypatch):
    monkeypatch.setenv("CHARLA_EMAIL_RPS", "4")
    outbox, sleeps = make_outbox(FakeResend(httpx.Response(200)))
    for i in range(3):
        outbox.enqueue(f"p{i}@empresa.com", f"P{i}", LINK)
    await outbox.drain()
    assert outbox.stats()["sent"] == 3
    assert sleeps == [0.25, 0.25, 0.25]


async def test_429_waits_for_retry_after_then_sends(resend_env):
    handler = FakeResend(httpx.Response(429, headers={"Retry-After": "3"}), httpx.Response(200))
    outbox, sleeps = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    await outbox.drain()
    assert len(handler.requests) == 2
    assert sleeps == [3.0, 0.5]
    assert outbox.stats() == {"queued": 0, "sent": 1, "failed": 0, "last_error": None}


async def test_gives_up_after_two_retries(resend_env):
    handler = FakeResend(httpx.Response(500, text="boom"))
    outbox, sleeps = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    outbox.enqueue("beto@empresa.com", "Beto", LINK)
    await outbox.drain()

    assert len(handler.requests) == 6  # 3 attempts each, and the queue keeps moving
    assert sleeps == [1.0, 1.0, 0.5, 1.0, 1.0, 0.5]
    stats = outbox.stats()
    assert stats["queued"] == 0 and stats["sent"] == 0 and stats["failed"] == 2
    assert stats["last_error"] == "Resend 500: boom"


async def test_429_retries_are_capped_too(resend_env):
    handler = FakeResend(httpx.Response(429, headers={"Retry-After": "999"}))
    outbox, sleeps = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    await outbox.drain()
    assert len(handler.requests) == 3
    assert sleeps == [30.0, 30.0, 0.5]
    assert outbox.stats()["failed"] == 1
    assert outbox.stats()["last_error"].startswith("Resend 429")


async def test_client_errors_are_not_retried(resend_env):
    handler = FakeResend(httpx.Response(403, json={"message": "domain not verified"}))
    outbox, _ = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    await outbox.drain()
    assert len(handler.requests) == 1
    assert outbox.stats()["failed"] == 1
    assert "domain not verified" in outbox.stats()["last_error"]


async def test_network_errors_are_retried(resend_env):
    handler = FakeResend(httpx.ConnectError("offline"), httpx.Response(200))
    outbox, sleeps = make_outbox(handler)
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    await outbox.drain()
    assert len(handler.requests) == 2
    assert outbox.stats()["sent"] == 1
    assert sleeps == [1.0, 0.5]


async def test_stats_changes_bump_the_admin_bus(resend_env):
    outbox, _ = make_outbox(FakeResend(httpx.Response(200)))
    outbox.enqueue("ana@empresa.com", "Ana", LINK)
    assert common.bus.admin_version == 1
    await outbox.drain()
    assert common.bus.admin_version == 2
    assert common.bus.public_version == 0


async def test_run_sends_in_the_background(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    outbox = EmailOutbox()
    task = asyncio.create_task(outbox.run())
    try:
        outbox.enqueue("ana@empresa.com", "Ana", LINK)
        for _ in range(100):
            if outbox.stats()["sent"]:
                break
            await asyncio.sleep(0.02)
        assert outbox.stats() == {"queued": 0, "sent": 1, "failed": 0, "last_error": None}
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
