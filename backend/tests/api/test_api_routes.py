import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

DEFAULTS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]
PORTFOLIO_KEYS = {
    "cash_balance",
    "positions",
    "positions_value",
    "total_value",
    "total_pnl",
    "total_pnl_percent",
    "valuation_complete",
    "as_of",
}


def buy(client, ticker, quantity, side="buy"):
    return client.post("/api/portfolio/trade", json={"ticker": ticker, "quantity": quantity, "side": side})


# ---------------------------------------------------------------- health


def test_health_reports_market_and_llm_modes(client, monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "true")
    assert client.get("/api/health").json() == {"status": "ok", "market_data": "simulator", "llm": "mock"}

    monkeypatch.setenv("LLM_MOCK", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert client.get("/api/health").json()["llm"] == "openrouter"

    monkeypatch.delenv("OPENROUTER_API_KEY")
    assert client.get("/api/health").json()["llm"] == "unconfigured"


# ---------------------------------------------------------------- watchlist


def test_watchlist_lists_defaults_with_quotes(client):
    response = client.get("/api/watchlist")
    assert response.status_code == 200
    rows = response.json()["watchlist"]
    assert [r["ticker"] for r in rows] == DEFAULTS
    assert set(rows[0]) == {"ticker", "added_at", "quote"}
    assert rows[0]["added_at"].endswith("Z")
    quote = rows[0]["quote"]
    assert quote == {
        "ticker": "AAPL",
        "price": 100.0,
        "previous_price": 100.0,
        "reference_price": 100.0,
        "change": 0.0,
        "change_percent": 0.0,
        "direction": "flat",
        "timestamp": quote["timestamp"],
    }


def test_watchlist_add_and_remove_are_idempotent(client, api_ctx):
    for _ in range(2):
        response = client.post("/api/watchlist", json={"ticker": "pypl"})
        assert response.status_code == 200
        rows = response.json()["watchlist"]
        assert [r["ticker"] for r in rows] == [*DEFAULTS, "PYPL"]
        assert rows[-1]["quote"]["price"] == 50.0
    assert "PYPL" in api_ctx.market.get_tickers()

    for _ in range(2):
        response = client.delete("/api/watchlist/pypl")
        assert response.status_code == 200
        assert [r["ticker"] for r in response.json()["watchlist"]] == DEFAULTS
    assert "PYPL" not in api_ctx.market.get_tickers()


def test_unpriced_watchlist_ticker_has_null_quote(client):
    rows = client.post("/api/watchlist", json={"ticker": "ZZZZ"}).json()["watchlist"]
    assert rows[-1]["ticker"] == "ZZZZ" and rows[-1]["quote"] is None


@pytest.mark.parametrize(
    ("body", "status", "detail"),
    [
        ({"ticker": "A$"}, 400, "Invalid ticker symbol: 'A$'"),
        ({"ticker": "XYZQ"}, 400, "Unknown ticker: XYZQ"),
        ({}, 422, None),
        ({"ticker": 5}, 422, None),
    ],
)
def test_watchlist_add_errors(client, api_ctx, body, status, detail):
    response = client.post("/api/watchlist", json=body)
    assert response.status_code == status
    if detail:
        assert response.json() == {"detail": detail}
    assert [r["ticker"] for r in client.get("/api/watchlist").json()["watchlist"]] == DEFAULTS
    assert "XYZQ" not in api_ctx.market.get_tickers()


def test_watchlist_remove_malformed_ticker_is_400(client):
    response = client.delete("/api/watchlist/TOOLONG")
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid ticker symbol: 'TOOLONG'"}


# ---------------------------------------------------------------- portfolio


def test_fresh_portfolio(client):
    body = client.get("/api/portfolio").json()
    assert set(body) == PORTFOLIO_KEYS
    assert (body["cash_balance"], body["positions"], body["total_value"], body["total_pnl"]) == (10000.0, [], 10000.0, 0.0)
    assert body["valuation_complete"] is True


def test_trade_returns_the_trade_and_the_updated_portfolio(client, api_ctx):
    response = buy(client, "aapl", 10)
    assert response.status_code == 200
    body = response.json()
    trade = body["trade"]
    assert set(trade) == {"id", "ticker", "side", "quantity", "price", "total", "executed_at"}
    assert (trade["ticker"], trade["side"], trade["quantity"], trade["price"], trade["total"]) == (
        "AAPL",
        "buy",
        10.0,
        100.0,
        1000.0,
    )
    assert trade["executed_at"].endswith("Z")
    portfolio = body["portfolio"]
    assert set(portfolio) == PORTFOLIO_KEYS
    assert portfolio["cash_balance"] == 9000.0
    assert portfolio["positions"] == [
        {
            "ticker": "AAPL",
            "quantity": 10.0,
            "avg_cost": 100.0,
            "current_price": 100.0,
            "market_value": 1000.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_percent": 0.0,
            "stale": False,
        }
    ]

    api_ctx.cache.update("AAPL", 101.2)
    body = client.get("/api/portfolio").json()
    assert body["positions"][0]["unrealized_pnl"] == 12.0
    assert body["positions"][0]["unrealized_pnl_percent"] == 1.2
    assert (body["total_value"], body["total_pnl"], body["total_pnl_percent"]) == (10012.0, 12.0, 0.12)


def test_selling_out_removes_the_position(client):
    buy(client, "AAPL", 3)
    response = buy(client, "AAPL", 3, side="sell")
    assert response.status_code == 200
    assert response.json()["portfolio"]["positions"] == []
    assert response.json()["portfolio"]["cash_balance"] == 10000.0


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"ticker": "A$", "quantity": 1, "side": "buy"}, "Invalid ticker symbol: 'A$'"),
        ({"ticker": "XYZQ", "quantity": 1, "side": "buy"}, "Unknown ticker: XYZQ"),
        ({"ticker": "AAPL", "quantity": 0, "side": "buy"}, "Quantity must be greater than 0"),
        ({"ticker": "AAPL", "quantity": 1.23456, "side": "buy"}, "Quantity can have at most 4 decimal places"),
        ({"ticker": "AAPL", "quantity": 1, "side": "short"}, "Side must be 'buy' or 'sell'"),
        ({"ticker": "ZZZZ", "quantity": 1, "side": "buy"}, "No current price for ZZZZ; try again shortly"),
        ({"ticker": "PENY", "quantity": 0.0001, "side": "buy"}, "Order value must be at least $0.01"),
        ({"ticker": "AAPL", "quantity": 101, "side": "buy"}, "Insufficient cash"),
        ({"ticker": "AAPL", "quantity": 5, "side": "sell"}, "Insufficient shares"),
    ],
)
def test_trade_business_errors_are_400(client, body, detail):
    response = client.post("/api/portfolio/trade", json=body)
    assert response.status_code == 400
    assert response.json()["detail"].startswith(detail)
    assert client.get("/api/portfolio").json()["cash_balance"] == 10000.0


@pytest.mark.parametrize(
    "body",
    [{}, {"ticker": "AAPL", "side": "buy"}, {"ticker": "AAPL", "quantity": "lots", "side": "buy"}],
)
def test_malformed_trade_body_is_422(client, body):
    assert client.post("/api/portfolio/trade", json=body).status_code == 422


# ---------------------------------------------------------------- history


def test_history_starts_with_the_seed_snapshot_and_grows_per_trade(client):
    snapshots = client.get("/api/portfolio/history").json()["snapshots"]
    assert snapshots == [{"total_value": 10000.0, "recorded_at": snapshots[0]["recorded_at"]}]

    buy(client, "AAPL", 1)
    buy(client, "MSFT", 1)
    snapshots = client.get("/api/portfolio/history").json()["snapshots"]
    assert len(snapshots) == 3
    times = [s["recorded_at"] for s in snapshots]
    assert times == sorted(times)

    assert client.get("/api/portfolio/history?limit=2").json()["snapshots"] == snapshots[-2:]


@pytest.mark.parametrize(("limit", "status"), [(0, 422), (1, 200), (5000, 200), (5001, 422), ("x", 422)])
def test_history_limit_bounds(client, limit, status):
    assert client.get(f"/api/portfolio/history?limit={limit}").status_code == status


# ---------------------------------------------------------------- app wiring


def test_unknown_api_route_is_a_json_404(client):
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_static_frontend_is_served_after_the_api(tmp_path, make_app):
    static = tmp_path / "out"
    static.mkdir()
    (static / "index.html").write_text("<html>FinAlly</html>")
    settings = Settings(db_path=tmp_path / "static.db", static_dir=static)
    with TestClient(make_app(settings)) as client:
        assert "FinAlly" in client.get("/").text
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/nope").headers["content-type"] == "application/json"


def test_cors_only_when_configured(tmp_path, client, make_app):
    origin = {"Origin": "http://localhost:3000"}
    assert "access-control-allow-origin" not in client.get("/api/health", headers=origin).headers

    settings = Settings(db_path=tmp_path / "cors.db", static_dir=tmp_path / "none", cors_origins=["http://localhost:3000"])
    with TestClient(make_app(settings)) as cors_client:
        response = cors_client.get("/api/health", headers=origin)
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_restart_restores_prices_and_tracks_held_tickers(tmp_path, make_app):
    settings = Settings(db_path=tmp_path / "restart.db", static_dir=tmp_path / "none")
    with TestClient(make_app(settings)) as client:
        assert buy(client, "PYPL", 2).status_code == 200  # held, not on the watchlist
        client.delete("/api/watchlist/MSFT")
        client.app.state.ctx.cache.update("PYPL", 55.5)
        first_market = client.app.state.ctx.market
    assert first_market.stopped

    with TestClient(make_app(settings)) as client:
        market = client.app.state.ctx.market
        assert market.initial_prices["PYPL"] == 55.5
        assert market.started_with == sorted([t for t in DEFAULTS if t != "MSFT"] + ["PYPL"])
        body = client.get("/api/portfolio").json()
        assert body["cash_balance"] == 9900.0 and body["positions"][0]["ticker"] == "PYPL"


def test_runs_with_the_real_simulator(tmp_path, monkeypatch):
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.setenv("SIM_SEED", "42")
    settings = Settings(db_path=tmp_path / "sim.db", static_dir=tmp_path / "none")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["market_data"] == "simulator"
        rows = client.get("/api/watchlist").json()["watchlist"]
        assert all(r["quote"] and r["quote"]["price"] > 0 for r in rows)
        response = buy(client, "AAPL", 1)
        assert response.status_code == 200
        assert response.json()["trade"]["price"] > 0


@pytest.mark.parametrize(("mock", "key", "preloads"), [("true", None, 0), ("false", "sk-test", 1), ("false", None, 0)])
def test_litellm_is_preloaded_only_for_the_real_llm(settings, make_app, monkeypatch, mock, key, preloads):
    from app.llm import client as llm_client

    calls = []

    async def fake_preload():
        calls.append(1)
        raise RuntimeError("import failed")  # a failed preload must not break startup

    monkeypatch.setattr(llm_client, "preload", fake_preload)
    monkeypatch.setenv("LLM_MOCK", mock)
    if key:
        monkeypatch.setenv("OPENROUTER_API_KEY", key)
    else:
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with TestClient(make_app(settings)) as client:
        assert client.get("/api/health").status_code == 200
    assert len(calls) == preloads
