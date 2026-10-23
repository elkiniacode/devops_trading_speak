"""SQLite persistence (CONTRACTS.md §3.2). Call init_db(path) once at startup, then use the functions below."""

from .connection import close_db, init_db
from .errors import InsufficientCashError, InsufficientSharesError, TradeRejected
from .history import (
    add_chat_message,
    get_chat_messages,
    get_snapshots,
    load_price_marks,
    record_snapshot,
    save_price_marks,
)
from .portfolio import apply_trade, get_cash, get_position, get_positions, get_trades
from .orders import add_activity, complete_market_request, complete_pending_order, create_market_request, create_order, finish_order, get_activity, get_market_request, get_order, get_order_by_client_id, get_orders, get_risk, set_risk, update_order
from .watchlist import add_watchlist_ticker, get_watchlist, remove_watchlist_ticker, tracked_tickers

__all__ = [
    "InsufficientCashError",
    "InsufficientSharesError",
    "TradeRejected",
    "add_chat_message",
    "add_activity",
    "add_watchlist_ticker",
    "apply_trade",
    "close_db",
    "complete_market_request",
    "complete_pending_order",
    "create_market_request",
    "create_order",
    "finish_order",
    "get_activity",
    "get_cash",
    "get_chat_messages",
    "get_position",
    "get_positions",
    "get_order",
    "get_market_request",
    "get_order_by_client_id",
    "get_orders",
    "get_risk",
    "get_snapshots",
    "get_trades",
    "get_watchlist",
    "init_db",
    "load_price_marks",
    "record_snapshot",
    "remove_watchlist_ticker",
    "save_price_marks",
    "set_risk",
    "update_order",
    "tracked_tickers",
]
