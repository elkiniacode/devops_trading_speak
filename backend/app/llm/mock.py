"""Deterministic replies for LLM_MOCK=true (CONTRACTS §7.3). No network.

The E2E tests depend on these exact rules and wording, so change them only together
with the contract.
"""

from __future__ import annotations

import json
import re

# Keywords are case-insensitive; tickers must be written in uppercase.
_TICKER = r"([A-Z]{1,5}(?:\.[A-Z])?)\b"
_QTY = r"(\d+(?:\.\d+)?)"
_TRADE = re.compile(rf"\b(?i:(buy|sell))\s+{_QTY}\s+{_TICKER}")
_WATCHLIST = re.compile(rf"\b(?i:(add|remove))\s+{_TICKER}")
_ORDER = re.compile(rf"\b(?i:(limit|stop))\s+(?i:(buy|sell))\s+\$?{_QTY}\s+{_TICKER}\s+(?i:at)\s+\$?{_QTY}")
_CLOSE = re.compile(rf"\b(?i:(close|cierra))\s+{_TICKER}")
_RISK = re.compile(rf"\b(?i:(risk|riesgo))\s+{_TICKER}\s+(?i:(?:SL|stop\s+loss))\s+{_QTY}\s+(?i:(?:TP|take\s+profit))\s+{_QTY}")

FALLBACK_MESSAGE = (
    "I'm FinAlly, running in mock mode. "
    'Try "buy 1 AAPL", "sell 1 AAPL", "add PYPL" or "remove PYPL".'
)


def _fmt_qty(q: float) -> str:
    return format(q, "f").rstrip("0").rstrip(".")


def mock_reply(user_message: str) -> str:
    """The raw JSON a model would return for this message. It is then validated like a real reply."""
    changes = [{"ticker": t, "action": a.lower()} for a, t in _WATCHLIST.findall(user_message)]
    trades = [
        {"ticker": t, "side": s.lower(), "quantity": float(q)} for s, q, t in _TRADE.findall(user_message)
    ]
    orders = [{"ticker": ticker, "side": side.lower(), "type": kind.lower(), "notional": float(notional),
               "trigger_price": float(trigger)} for kind, side, notional, ticker, trigger in _ORDER.findall(user_message)]
    closes = [ticker for _, ticker in _CLOSE.findall(user_message)]
    risks = [{"ticker": ticker, "stop_loss": float(stop), "take_profit": float(take)}
             for _, ticker, stop, take in _RISK.findall(user_message)]

    phrases = [
        f"Adding {c['ticker']} to your watchlist."
        if c["action"] == "add"
        else f"Removing {c['ticker']} from your watchlist."
        for c in changes
    ]
    phrases += [f"Placing a {t['side']} order for {_fmt_qty(t['quantity'])} {t['ticker']}." for t in trades]
    phrases += [f"Creando orden {o['type']} de {o['side']} para {o['ticker']}." for o in orders]
    phrases += [f"Cerrando la posición {ticker}." for ticker in closes]
    phrases += [f"Actualizando riesgo de {item['ticker']}." for item in risks]

    result = {
            "message": " ".join(phrases) if phrases else FALLBACK_MESSAGE,
            "trades": trades,
            "watchlist_changes": changes,
        }
    if orders:
        result["orders"] = orders
    if closes:
        result["closes"] = closes
    if risks:
        result["risks"] = risks
    return json.dumps(result)
