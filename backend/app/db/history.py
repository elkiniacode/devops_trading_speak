"""Append-only records: portfolio snapshots, chat messages, and the last known price per ticker."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .connection import connect, new_id, now_iso, transaction
from .schema import USER_ID


def record_snapshot(total_value: float) -> dict:
    snapshot = {"total_value": round(total_value, 2), "recorded_at": now_iso()}
    with connect() as conn:
        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
            (new_id(), USER_ID, snapshot["total_value"], snapshot["recorded_at"]),
        )
    return snapshot


def get_snapshots(limit: int = 500) -> list[dict]:
    """The most recent `limit` snapshots, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT total_value, recorded_at FROM (
                 SELECT total_value, recorded_at, rowid AS seq FROM portfolio_snapshots WHERE user_id = ?
                 ORDER BY recorded_at DESC, rowid DESC LIMIT ?)
               ORDER BY recorded_at, seq""",
            (USER_ID, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def add_chat_message(role: str, content: str, actions: dict | None) -> dict:
    """Store a message; `actions` is kept as JSON (None for user messages)."""
    message = {"id": new_id(), "role": role, "content": content, "actions": actions, "created_at": now_iso()}
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                message["id"],
                USER_ID,
                role,
                content,
                None if actions is None else json.dumps(actions),
                message["created_at"],
            ),
        )
    return message


def get_chat_messages(limit: int = 50) -> list[dict]:
    """The most recent `limit` messages, oldest first, with `actions` parsed back into a dict."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT id, role, content, actions, created_at FROM (
                 SELECT *, rowid AS seq FROM chat_messages WHERE user_id = ?
                 ORDER BY created_at DESC, rowid DESC LIMIT ?)
               ORDER BY created_at, seq""",
            (USER_ID, limit),
        ).fetchall()
    return [{**dict(row), "actions": None if row["actions"] is None else json.loads(row["actions"])} for row in rows]


def load_price_marks() -> dict[str, float]:
    with connect() as conn:
        return {ticker: price for ticker, price in conn.execute("SELECT ticker, price FROM price_marks")}


def save_price_marks(prices: Mapping[str, float]) -> None:
    """Upsert the latest price for each ticker, so the simulator can resume from them after a restart."""
    updated_at = now_iso()
    with transaction() as conn:
        conn.executemany(
            """INSERT INTO price_marks (ticker, price, updated_at) VALUES (?, ?, ?)
               ON CONFLICT (ticker) DO UPDATE SET price = excluded.price, updated_at = excluded.updated_at""",
            [(ticker, price, updated_at) for ticker, price in prices.items()],
        )
