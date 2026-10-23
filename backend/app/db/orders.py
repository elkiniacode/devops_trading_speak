"""Persistence helpers for pending orders, risk levels, and workstation activity."""

from __future__ import annotations

from .connection import connect, new_id, now_iso, transaction
from .errors import TradeRejected
from .portfolio import apply_trade
from .schema import USER_ID


def create_order(order: dict) -> dict:
    now = now_iso()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM pending_orders WHERE user_id=? AND client_order_id=?",
            (USER_ID, order["client_order_id"]),
        ).fetchone()
        if row:
            return dict(row)
        order_id = new_id()
        conn.execute(
            """INSERT INTO pending_orders
               (id,user_id,client_order_id,ticker,side,type,notional,trigger_price,stop_loss,take_profit,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,'pending',?,?)""",
            (order_id, USER_ID, order["client_order_id"], order["ticker"], order["side"], order["type"],
             order["notional"], order["trigger_price"], order.get("stop_loss"), order.get("take_profit"), now, now),
        )
        return dict(conn.execute("SELECT * FROM pending_orders WHERE id=?", (order_id,)).fetchone())


def get_order(order_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM pending_orders WHERE user_id=? AND id=?", (USER_ID, order_id)).fetchone()
    return dict(row) if row else None


def get_order_by_client_id(client_order_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM pending_orders WHERE user_id=? AND client_order_id=?", (USER_ID, client_order_id)).fetchone()
    return dict(row) if row else None


def get_market_request(client_order_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM market_order_requests WHERE user_id=? AND client_order_id=?", (USER_ID, client_order_id)).fetchone()
    return dict(row) if row else None


def create_market_request(client_order_id: str, ticker: str, side: str, notional: float) -> dict:
    now = now_iso()
    with transaction() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO market_order_requests
               (id,user_id,client_order_id,ticker,side,notional,status,created_at,updated_at)
               VALUES (?,?,?,?,?,?,'pending',?,?)""",
            (new_id(), USER_ID, client_order_id, ticker, side, notional, now, now),
        )
        row = conn.execute("SELECT * FROM market_order_requests WHERE user_id=? AND client_order_id=?", (USER_ID, client_order_id)).fetchone()
        return dict(row)


def _trade_by_id(conn, trade_id: str) -> dict:
    row = conn.execute("SELECT id,ticker,side,quantity,price,executed_at FROM trades WHERE user_id=? AND id=?", (USER_ID, trade_id)).fetchone()
    return {**dict(row), "total": round(row["quantity"] * row["price"], 2)}


def complete_market_request(request_id: str, quantity: float, price: float, stop_loss: float | None, take_profit: float | None) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM market_order_requests WHERE user_id=? AND id=?", (USER_ID, request_id)).fetchone()
        if not row:
            raise TradeRejected("Solicitud de orden no encontrada")
        if row["status"] == "filled":
            return _trade_by_id(conn, row["trade_id"])
        if row["status"] != "pending":
            raise TradeRejected(row["reason"] or "La orden fue rechazada")
        trade = apply_trade(row["ticker"], row["side"], quantity, price, conn=conn)
        conn.execute("UPDATE market_order_requests SET status='filled',trade_id=?,updated_at=? WHERE id=?", (trade["id"], now_iso(), request_id))
        if row["side"] == "buy" and (stop_loss is not None or take_profit is not None):
            conn.execute("""INSERT INTO position_risk(user_id,ticker,stop_loss,take_profit,updated_at) VALUES (?,?,?,?,?)
                ON CONFLICT(user_id,ticker) DO UPDATE SET stop_loss=excluded.stop_loss,take_profit=excluded.take_profit,updated_at=excluded.updated_at""",
                (USER_ID, row["ticker"], stop_loss, take_profit, now_iso()))
        conn.execute("INSERT INTO activity_events(id,user_id,kind,ticker,message,created_at) VALUES(?,?,?,?,?,?)",
                     (new_id(), USER_ID, "trade", row["ticker"], f"{row['side'].upper()} {trade['quantity']:g} {row['ticker']} a {price:.2f}", now_iso()))
        return trade


def complete_pending_order(order_id: str, price: float) -> dict:
    with transaction() as conn:
        row = conn.execute("SELECT * FROM pending_orders WHERE user_id=? AND id=?", (USER_ID, order_id)).fetchone()
        if not row:
            raise TradeRejected("Orden no encontrada")
        if row["status"] == "filled":
            return _trade_by_id(conn, row["trade_id"])
        if row["status"] != "pending":
            raise TradeRejected("La orden ya no está pendiente")
        if row["side"] == "buy" and ((row["stop_loss"] is not None and row["stop_loss"] >= price) or
                                     (row["take_profit"] is not None and row["take_profit"] <= price)):
            raise TradeRejected("Los niveles de riesgo ya no son válidos para el precio de ejecución")
        quantity = round(row["notional"] / price, 4)
        trade = apply_trade(row["ticker"], row["side"], quantity, price, conn=conn)
        conn.execute("UPDATE pending_orders SET status='filled',trade_id=?,updated_at=? WHERE id=?", (trade["id"], now_iso(), order_id))
        if row["side"] == "buy" and (row["stop_loss"] is not None or row["take_profit"] is not None):
            conn.execute("""INSERT INTO position_risk(user_id,ticker,stop_loss,take_profit,updated_at) VALUES (?,?,?,?,?)
                ON CONFLICT(user_id,ticker) DO UPDATE SET stop_loss=excluded.stop_loss,take_profit=excluded.take_profit,updated_at=excluded.updated_at""",
                (USER_ID, row["ticker"], row["stop_loss"], row["take_profit"], now_iso()))
        conn.execute("INSERT INTO activity_events(id,user_id,kind,ticker,message,created_at) VALUES(?,?,?,?,?,?)",
                     (new_id(), USER_ID, "trade", row["ticker"], f"Orden ejecutada: {row['side'].upper()} {row['ticker']}", now_iso()))
        return trade


def get_orders(status: str | None = "pending", limit: int = 100) -> list[dict]:
    with connect() as conn:
        if status is None:
            rows = conn.execute("SELECT * FROM pending_orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (USER_ID, limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pending_orders WHERE user_id=? AND status=? ORDER BY created_at DESC LIMIT ?",
                (USER_ID, status, limit),
            ).fetchall()
    return [dict(row) for row in rows]


def update_order(order_id: str, fields: dict) -> dict | None:
    allowed = {key: value for key, value in fields.items() if key in {"trigger_price", "stop_loss", "take_profit"}}
    if not allowed:
        return get_order(order_id)
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM pending_orders WHERE user_id=? AND id=? AND status='pending'", (USER_ID, order_id)).fetchone():
            return None
        allowed["updated_at"] = now_iso()
        assignments = ",".join(f"{key}=?" for key in allowed)
        conn.execute(f"UPDATE pending_orders SET {assignments} WHERE user_id=? AND id=?", (*allowed.values(), USER_ID, order_id))
    return get_order(order_id)


def finish_order(order_id: str, status: str, reason: str | None = None) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE pending_orders SET status=?,reason=?,updated_at=? WHERE user_id=? AND id=? AND status='pending'",
            (status, reason, now_iso(), USER_ID, order_id),
        )
    return cur.rowcount == 1


def set_risk(ticker: str, stop_loss: float | None, take_profit: float | None) -> dict:
    now = now_iso()
    with connect() as conn:
        if stop_loss is None and take_profit is None:
            conn.execute("DELETE FROM position_risk WHERE user_id=? AND ticker=?", (USER_ID, ticker))
        else:
            conn.execute(
                """INSERT INTO position_risk(user_id,ticker,stop_loss,take_profit,updated_at) VALUES(?,?,?,?,?)
                   ON CONFLICT(user_id,ticker) DO UPDATE SET stop_loss=excluded.stop_loss,
                   take_profit=excluded.take_profit,updated_at=excluded.updated_at""",
                (USER_ID, ticker, stop_loss, take_profit, now),
            )
    return {"ticker": ticker, "stop_loss": stop_loss, "take_profit": take_profit, "updated_at": now}


def get_risk(ticker: str | None = None) -> list[dict]:
    with connect() as conn:
        if ticker:
            rows = conn.execute("SELECT ticker,stop_loss,take_profit,updated_at FROM position_risk WHERE user_id=? AND ticker=?", (USER_ID, ticker)).fetchall()
        else:
            rows = conn.execute("SELECT ticker,stop_loss,take_profit,updated_at FROM position_risk WHERE user_id=?", (USER_ID,)).fetchall()
    return [dict(row) for row in rows]


def add_activity(kind: str, message: str, ticker: str | None = None) -> dict:
    item = {"id": new_id(), "kind": kind, "ticker": ticker, "message": message, "created_at": now_iso()}
    with connect() as conn:
        conn.execute("INSERT INTO activity_events(id,user_id,kind,ticker,message,created_at) VALUES(?,?,?,?,?,?)",
                     (item["id"], USER_ID, kind, ticker, message, item["created_at"]))
    return item


def get_activity(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT id,kind,ticker,message,created_at FROM activity_events WHERE user_id=? ORDER BY created_at DESC,rowid DESC LIMIT ?", (USER_ID, limit)).fetchall()
    return [dict(row) for row in rows]
