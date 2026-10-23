"""Opening the SQLite file, creating the schema and seeding a fresh database.

The module keeps one connection, shared under a re-entrant lock, so the functions are safe to
call from the event loop thread, worker threads and tests alike (opening a connection per call
costs milliseconds on Windows; a query on an open one costs microseconds). The connection runs
in autocommit mode; code that needs several statements to succeed or fail together uses
`transaction()`.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.market.models import iso_utc

from .schema import DEFAULT_WATCHLIST, SCHEMA, SCHEMA_VERSION, STARTING_CASH, USER_ID

_conn: sqlite3.Connection | None = None  # opened by init_db()
_lock = threading.RLock()


def init_db(path: str | Path) -> None:
    """Open the database at `path`, create the schema, and seed it if it is a new database.

    Safe to call on an existing database: seeding only happens when the default profile is
    missing, so cash, the watchlist and history are never reset. Calling it again switches to
    `path` (tests use this).
    """
    global _conn
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        close_db()
        _conn = sqlite3.connect(path, timeout=10, isolation_level=None, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        _conn.execute("PRAGMA journal_mode = WAL")
        current_version = _conn.execute("PRAGMA user_version").fetchone()[0]
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(f"Database schema {current_version} is newer than this application")
        existing_columns = {row[1] for row in _conn.execute("PRAGMA table_info(pending_orders)")}
        migration = "ALTER TABLE pending_orders ADD COLUMN trade_id TEXT;" if existing_columns and "trade_id" not in existing_columns else ""
        try:
            _conn.executescript(f"BEGIN IMMEDIATE;\n{SCHEMA}\n{migration}\nPRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;")
        except Exception:
            if _conn.in_transaction:
                _conn.execute("ROLLBACK")
            close_db()
            raise
        with transaction() as conn:
            _seed(conn)


def close_db() -> None:
    """Close the connection, if open. Further calls fail until init_db() runs again."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None


def _seed(conn: sqlite3.Connection) -> None:
    if conn.execute("SELECT 1 FROM users_profile WHERE id = ?", (USER_ID,)).fetchone():
        return
    ts = time.time()
    conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        (USER_ID, STARTING_CASH, iso_utc(ts)),
    )
    # The watchlist sorts by added_at: give the seed rows distinct times, 1 ms apart and all
    # before `ts`, so they keep this order and anything added later sorts after them.
    count = len(DEFAULT_WATCHLIST)
    conn.executemany(
        "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        [(new_id(), USER_ID, ticker, iso_utc(ts - (count - i) / 1000)) for i, ticker in enumerate(DEFAULT_WATCHLIST)],
    )
    conn.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (new_id(), USER_ID, STARTING_CASH, iso_utc(ts)),
    )


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """The shared connection, held exclusively for the duration of the block."""
    with _lock:
        if _conn is None:
            raise RuntimeError("Database not initialized: call init_db(path) first")
        yield _conn


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    """Run the block as one write transaction: committed on success, rolled back on any error."""
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")


def now_iso() -> str:
    return iso_utc(time.time())


def new_id() -> str:
    return str(uuid.uuid4())
