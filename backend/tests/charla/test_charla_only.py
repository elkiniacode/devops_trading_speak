"""CHARLA_ONLY (CONTRACT.md §0, §4.6): only health and charla routes; / redirects to /charla/."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings


def test_finally_routes_are_gone(charla_client):
    assert charla_client.get("/api/portfolio").status_code == 404
    assert charla_client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 1, "side": "buy"}).status_code == 404
    assert charla_client.post("/api/chat", json={"message": "hola"}).status_code == 404
    assert charla_client.get("/api/watchlist").status_code == 404
    assert charla_client.get("/api/stream/prices").status_code == 404
    assert charla_client.get("/api/health").json()["status"] == "ok"
    assert charla_client.get("/api/charla/me").status_code == 401


def test_root_redirects_to_charla(charla_client):
    res = charla_client.get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/charla/"


def test_root_redirect_wins_over_the_static_build(charla_env, tmp_path, make_app):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<h1>FinAlly</h1>", encoding="utf-8")
    settings = Settings(db_path=tmp_path / "c.db", static_dir=static, charla_only=True)
    with TestClient(make_app(settings)) as client:
        assert client.get("/", follow_redirects=False).status_code == 307


def test_finally_still_works_without_charla_only(client):
    assert client.get("/api/portfolio").status_code == 200
    assert client.get("/api/watchlist").status_code == 200
    assert client.get("/", follow_redirects=False).status_code == 404  # no frontend build in tests
    assert client.get("/api/charla/me").status_code == 401  # charla routes are always mounted
