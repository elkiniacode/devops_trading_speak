"""The watchlist, and the set of tickers that need live prices."""

from __future__ import annotations

from .connection import connect, new_id, now_iso
from .schema import USER_ID


def get_watchlist() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at, ticker", (USER_ID,)
        ).fetchall()
    return [dict(row) for row in rows]


def add_watchlist_ticker(ticker: str) -> bool:
    """Add `ticker`; True if it was not already on the watchlist."""
    with connect() as conn:
        cur = conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (new_id(), USER_ID, ticker, now_iso()),
        )
    return cur.rowcount == 1


def remove_watchlist_ticker(ticker: str) -> bool:
    """Remove `ticker`; True if it was on the watchlist."""
    with connect() as conn:
        cur = conn.execute("DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (USER_ID, ticker))
    return cur.rowcount == 1


def tracked_tickers() -> list[str]:
    """Every ticker that needs a live price: the watchlist plus open positions, sorted."""
    with connect() as conn:
        rows = conn.execute(
            """SELECT ticker FROM watchlist WHERE user_id = ?
               UNION SELECT ticker FROM positions WHERE user_id = ? AND quantity > 0""",
            (USER_ID, USER_ID),
        ).fetchall()
    return sorted(row[0] for row in rows)
