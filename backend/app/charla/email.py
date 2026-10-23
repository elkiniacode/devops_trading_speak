"""The one-tap link outbox (planning/charla/CONTRACT.md §4.3).

``register`` queues an email and returns at once; ``run()`` (a lifespan task) sends the queue
through Resend at ``CHARLA_EMAIL_RPS``. Without RESEND_API_KEY the link is logged instead.
"""

from __future__ import annotations

import asyncio
import html
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from app.charla import common
from app.config import charla_email_rps, resend_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
MAX_RETRIES = 2  # after the first attempt
MAX_RETRY_AFTER_S = 30.0
RETRY_WAIT_S = 1.0  # network errors and 5xx
IDLE_POLL_S = 0.1
TIMEOUT_S = 10.0


@dataclass(frozen=True)
class LinkEmail:
    to: str
    username: str
    link: str


def compose(username: str, link: str) -> tuple[str, str, str]:
    """(subject, html, text) for one link email. The logo is served next to the link's origin."""
    base = link.split("/charla/entrar/", 1)[0]
    name, href = html.escape(username), html.escape(link, quote=True)
    logo = html.escape(f"{base}/charla/logo.png", quote=True)
    font = "font-family:Arial,Helvetica,sans-serif;"
    subject = f"Entra a la charla, {username}"
    body = f"""<!doctype html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark"><title>{html.escape(subject)}</title></head>
<body style="margin:0;padding:0;background:#070909;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#070909" style="background:#070909;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#0d1211" style="max-width:480px;background:#0d1211;border:1px solid #1f2523;border-radius:12px;">
<tr><td align="center" style="padding:32px 24px 8px;"><img src="{logo}" width="120" alt="IA Revolutions" style="display:block;width:120px;height:auto;border:0;outline:none;text-decoration:none;"></td></tr>
<tr><td align="center" style="padding:16px 24px 4px;{font}font-size:13px;letter-spacing:2px;text-transform:uppercase;color:#8b9491;">Hola, {name}</td></tr>
<tr><td align="center" style="padding:4px 24px 24px;{font}font-size:26px;line-height:32px;font-weight:bold;color:#f2f5f4;">Un toque y entras a la sala</td></tr>
<tr><td align="center" style="padding:0 24px 24px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td align="center" bgcolor="#5eead4" style="background:#5eead4;border-radius:8px;">
<a href="{href}" target="_blank" style="display:inline-block;padding:18px 36px;{font}font-size:17px;font-weight:bold;letter-spacing:1px;color:#070909;text-decoration:none;border-radius:8px;">ENTRAR A LA SALA</a>
</td></tr></table>
</td></tr>
<tr><td align="center" style="padding:0 24px 8px;{font}font-size:12px;color:#8b9491;">Si el botón no funciona, abre este enlace:</td></tr>
<tr><td align="center" style="padding:0 24px 24px;font-family:'Courier New',Courier,monospace;font-size:12px;line-height:18px;word-break:break-all;"><a href="{href}" target="_blank" style="color:#5eead4;text-decoration:underline;">{href}</a></td></tr>
<tr><td align="center" style="padding:16px 24px 32px;border-top:1px solid #1f2523;{font}font-size:12px;line-height:18px;color:#8b9491;">El enlace vence en 30 minutos.<br>Si no fuiste tú, ignora este correo.</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""
    text = (
        f"Hola, {username}:\n\n"
        "Un toque y entras a la sala. Abre este enlace en tu celular:\n\n"
        f"{link}\n\n"
        "El enlace vence en 30 minutos.\n"
        "Si no fuiste tú, ignora este correo.\n\n"
        "IA Revolutions\n"
    )
    return subject, body, text


class EmailOutbox:
    """Queue of link emails, sent in the background by ``run()``.

    ``transport`` (e.g. ``httpx.MockTransport``) and ``sleep`` are injectable for tests.
    """

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
    ) -> None:
        self.transport = transport
        self.sleep = sleep or asyncio.sleep
        self._queue: deque[LinkEmail] = deque()
        self.sent = 0
        self.failed = 0
        self.last_error: str | None = None

    def enqueue(self, to: str, username: str, link: str) -> None:
        """Queue one link email. Never blocks, never raises."""
        try:
            self._queue.append(LinkEmail(to, username, link))
            common.bus.bump(public=False)
        except Exception:
            logger.exception("Could not queue the link email for %s", to)

    async def run(self) -> None:
        """Background task: send queued emails until cancelled."""
        async with self._client() as client:
            while True:
                if not await self.send_next(client):
                    await asyncio.sleep(IDLE_POLL_S)

    async def drain(self) -> None:
        """Send everything queued now (tests; ``run()`` does the same forever)."""
        async with self._client() as client:
            while await self.send_next(client):
                pass

    async def send_next(self, client: httpx.AsyncClient) -> bool:
        """Send the oldest queued email, then wait out the send rate. False when the queue is empty."""
        if not self._queue:
            return False
        item = self._queue[0]
        api_key, sender = resend_settings()
        if not api_key:
            logger.info("CHARLA LINK for %s: %s", item.to, item.link)
            error = None
        else:
            try:
                error = await self._deliver(client, item, api_key, sender)
            except Exception as exc:  # one bad email must never stop the outbox
                logger.exception("Sending the link email to %s failed", item.to)
                error = f"{type(exc).__name__}: {exc}"
        self._queue.popleft()
        if error is None:
            self.sent += 1
        else:
            self.failed += 1
            self.last_error = error
            logger.warning("CHARLA LINK not sent to %s (%s): %s", item.to, error, item.link)
        common.bus.bump(public=False)
        if api_key:
            await self.sleep(1 / charla_email_rps())
        return True

    async def _deliver(self, client: httpx.AsyncClient, item: LinkEmail, api_key: str, sender: str) -> str | None:
        """POST to Resend with up to MAX_RETRIES retries. None on success, else the last error."""
        subject, body, text = compose(item.username, item.link)
        payload = {"from": sender, "to": [item.to], "subject": subject, "html": body, "text": text}
        headers = {"Authorization": f"Bearer {api_key}"}
        error = "sin respuesta"
        for attempt in range(MAX_RETRIES + 1):
            try:
                res = await client.post(RESEND_URL, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                error, wait = f"{type(exc).__name__}: {exc}", RETRY_WAIT_S
            else:
                if res.is_success:
                    return None
                error = f"Resend {res.status_code}: {res.text[:200]}"
                if res.status_code == 429:
                    wait = _retry_after(res)
                elif res.status_code >= 500:
                    wait = RETRY_WAIT_S
                else:  # other 4xx (bad sender, unverified domain): retrying won't help
                    return error
            if attempt < MAX_RETRIES:
                await self.sleep(wait)
        return error

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, timeout=TIMEOUT_S)

    def stats(self) -> dict:
        return {"queued": len(self._queue), "sent": self.sent, "failed": self.failed, "last_error": self.last_error}


def _retry_after(res: httpx.Response) -> float:
    """Seconds from a 429's Retry-After header (1 s when missing), capped at MAX_RETRY_AFTER_S."""
    try:
        return min(max(float(res.headers.get("retry-after", "1")), 0.0), MAX_RETRY_AFTER_S)
    except ValueError:
        return RETRY_WAIT_S


outbox = EmailOutbox()
