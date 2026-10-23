"""Cash, positions and trades. apply_trade is the only code that changes them."""

from __future__ import annotations

import sqlite3
from contextlib import nullcontext

from .connection import connect, new_id, now_iso, transaction
from .errors import InsufficientCashError, InsufficientSharesError, TradeRejected
from .schema import USER_ID

QTY_DP = 4  # fractional shares, at most 4 decimal places
DUST = 1e-6  # a position at or below this quantity is closed
TOLERANCE = 1e-9  # float slack when comparing quantities


def get_cash() -> float:
    with connect() as conn:
        return conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)).fetchone()[0]


def get_positions() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions WHERE user_id = ? ORDER BY ticker",
            (USER_ID,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_position(ticker: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT ticker, quantity, avg_cost, updated_at FROM positions WHERE user_id = ? AND ticker = ?",
            (USER_ID, ticker),
        ).fetchone()
    return dict(row) if row else None


def apply_trade(ticker: str, side: str, quantity: float, price: float, *, conn: sqlite3.Connection | None = None) -> dict:
    """Fill a market order at `price` in one transaction and return the trade object.

    Buys update the weighted average cost; sells leave it unchanged. Raises a TradeRejected
    subclass, writing nothing, when the order breaks a rule.
    """
    if side not in ("buy", "sell"):
        raise TradeRejected("Side must be 'buy' or 'sell'")
    qty = round(quantity, QTY_DP)
    if qty <= 0:
        raise TradeRejected("Quantity must be greater than 0")
    total = round(qty * price, 2)
    if total < 0.01:
        raise TradeRejected("Order value must be at least $0.01")

    executed_at = now_iso()
    with (transaction() if conn is None else nullcontext(conn)) as conn:
        cash = conn.execute("SELECT cash_balance FROM users_profile WHERE id = ?", (USER_ID,)).fetchone()[0]
        pos = conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, ticker)
        ).fetchone()
        held, avg_cost = (pos["quantity"], pos["avg_cost"]) if pos else (0.0, 0.0)

        if side == "buy":
            if round(total - cash, 2) > 0:
                raise InsufficientCashError(f"Insufficient cash: need ${total:,.2f}, have ${cash:,.2f}")
            new_qty = round(held + qty, QTY_DP)
            avg_cost = (held * avg_cost + qty * price) / new_qty
            cash = round(cash - total, 2)
        else:
            if qty > held + TOLERANCE:
                raise InsufficientSharesError(
                    f"Insufficient shares: you have {_fmt_qty(held)} {ticker}, tried to sell {_fmt_qty(qty)}"
                )
            new_qty = round(held - qty, QTY_DP)
            cash = round(cash + total, 2)

        conn.execute("UPDATE users_profile SET cash_balance = ? WHERE id = ?", (cash, USER_ID))
        if new_qty <= DUST:
            conn.execute("DELETE FROM positions WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))
            conn.execute("DELETE FROM position_risk WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))
        else:
            conn.execute(
                """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (user_id, ticker) DO UPDATE SET
                     quantity = excluded.quantity, avg_cost = excluded.avg_cost, updated_at = excluded.updated_at""",
                (new_id(), USER_ID, ticker, new_qty, avg_cost, executed_at),
            )
        trade = {
            "id": new_id(),
            "ticker": ticker,
            "side": side,
            "quantity": qty,
            "price": price,
            "total": total,
            "executed_at": executed_at,
        }
        conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade["id"], USER_ID, ticker, side, qty, price, executed_at),
        )
    return trade


def get_trades(limit: int = 50) -> list[dict]:
    """The most recent `limit` trades, newest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, ticker, side, quantity, price, executed_at FROM trades WHERE user_id = ?
               ORDER BY executed_at DESC, rowid DESC LIMIT ?""",
            (USER_ID, limit),
        ).fetchall()
    return [{**dict(row), "total": round(row["quantity"] * row["price"], 2)} for row in rows]


def _fmt_qty(qty: float) -> str:
    """2.0 -> '2', 0.5 -> '0.5', 1500 -> '1,500'."""
    return f"{qty:,.{QTY_DP}f}".rstrip("0").rstrip(".")
