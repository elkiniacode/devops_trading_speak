"""Cross-endpoint order idempotency must not silently replay a different intent."""


def test_market_retry_returns_one_fill_and_rejects_reused_id(client):
    body = {"ticker": "AAPL", "side": "buy", "type": "market", "notional": 100,
            "client_order_id": "market-1"}
    first = client.post("/api/orders", json=body)
    assert first.status_code == 200
    again = client.post("/api/orders", json=body)
    assert again.status_code == 200
    assert again.json()["trade"]["id"] == first.json()["trade"]["id"]
    assert client.post("/api/orders", json={**body, "type": "limit", "trigger_price": 90}).status_code == 409
    assert client.post("/api/orders", json={**body, "notional": 200}).status_code == 409
    assert len(client.get("/api/portfolio/trades").json()["trades"]) == 1


def test_pending_retry_rejects_changed_trigger_or_market_kind(client):
    body = {"ticker": "AAPL", "side": "buy", "type": "limit", "notional": 100,
            "trigger_price": 90, "client_order_id": "pending-1"}
    first = client.post("/api/orders", json=body)
    assert first.status_code == 200
    again = client.post("/api/orders", json=body)
    assert again.status_code == 200
    assert again.json()["order"]["id"] == first.json()["order"]["id"]
    assert client.post("/api/orders", json={**body, "trigger_price": 80}).status_code == 409
    assert client.post("/api/orders", json={**body, "type": "market", "trigger_price": None}).status_code == 409
    assert len(client.get("/api/workstation").json()["orders"]) == 1
