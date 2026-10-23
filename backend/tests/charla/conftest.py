"""Fixtures for the live-talk tests (CONTRACT.md §8). Owned by team-lead; ask before changing.

- ``charla_env``: admin key, secret, dev links on, Resend off, LLM mock, no automatic phone prompt.
- ``clock``: a fake ``common.now_ms`` you can move with ``clock.advance(ms)``.
- ``charla_client``: a TestClient for ``create_app(Settings(charla_only=True))`` on a temp DB.
- ``admin``: the admin header.
- ``enter``: ``enter(username, email) -> token`` registers and opens the dev link, returning a session token.
- ``bearer``: ``bearer(token) -> headers``.

Test files sit next to this conftest without an ``__init__.py`` (same as the other test folders).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.charla import common
from app.config import Settings

ADMIN_KEY = "test-admin"


@pytest.fixture(autouse=True)
def fresh_bus():
    """The bus is a module-level singleton; give every test a clean one."""
    common.bus.__init__()
    yield


@pytest.fixture
def charla_env(monkeypatch):
    monkeypatch.setenv("CHARLA_ADMIN_KEY", ADMIN_KEY)
    monkeypatch.setenv("CHARLA_SECRET", "test-secret")
    monkeypatch.setenv("CHARLA_DEV_LINKS", "true")
    monkeypatch.setenv("CHARLA_PHONE_AT", "off")
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("CHARLA_PUBLIC_URL", raising=False)


@dataclass
class FakeClock:
    now: int = 1_800_000_000_000

    def advance(self, ms: int) -> int:
        self.now += ms
        return self.now


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake = FakeClock()
    monkeypatch.setattr(common, "now_ms", lambda: fake.now)
    return fake


@pytest.fixture
def charla_settings(tmp_path) -> Settings:
    return Settings(db_path=tmp_path / "charla.db", static_dir=tmp_path / "no-frontend-build", charla_only=True)


@pytest.fixture
def charla_client(charla_env, charla_settings, make_app):
    with TestClient(make_app(charla_settings)) as test_client:
        yield test_client


@pytest.fixture
def admin() -> dict[str, str]:
    return {"X-Admin-Key": ADMIN_KEY}


@pytest.fixture
def enter(charla_client):
    """Register, open the one-tap link (dev mode returns its token) and return the session token."""

    def _enter(username: str, email: str) -> str:
        res = charla_client.post("/api/charla/register", json={"username": username, "email": email})
        assert res.status_code == 200, res.text
        body = res.json()
        if body["status"] == "in":
            return body["token"]
        verified = charla_client.post("/api/charla/verify", json={"v": body["dev_link_token"]})
        assert verified.status_code == 200, verified.text
        return verified.json()["token"]

    return _enter


@pytest.fixture
def bearer():
    """``bearer(token) -> headers`` for attendee calls."""
    return lambda token: {"Authorization": f"Bearer {token}"}
