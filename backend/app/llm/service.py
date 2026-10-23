"""One chat turn: store, prompt, call the model (or the mock), validate, execute, store (CONTRACTS §3.4)."""

from __future__ import annotations

import logging
import re

from fastapi import HTTPException

from app import db
from app.config import llm_mode
from app.context import AppContext
from app.api.workstation import OrderBody, RiskBody, close_position, place_order, set_position_risk
from app.services.trading import execute_trade
from app.services.watchlist import add_to_watchlist, remove_from_watchlist
from app.services.portfolio import portfolio_view

from . import client
from .mock import mock_reply
from .prompt import build_messages
from .schemas import ChatReply, InvalidReply, parse_reply

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 20  # messages sent to the model, including the new one (R26)
ATTEMPTS = 2  # the first try plus one retry after an invalid reply


class LLMNotConfigured(RuntimeError):
    """No OPENROUTER_API_KEY and LLM_MOCK is off (-> 503)."""


class LLMUnavailable(RuntimeError):
    """The model failed or kept returning invalid output; nothing was executed (-> 502)."""


async def handle_chat(ctx: AppContext, message: str, chart_context: dict | None = None) -> dict:
    """Run one turn for an already-trimmed user message and return the stored assistant message."""
    mode = llm_mode()
    if mode == "unconfigured":
        raise LLMNotConfigured("AI chat is not configured: set OPENROUTER_API_KEY or LLM_MOCK=true")

    db.add_chat_message("user", message, None)
    messages = build_messages(ctx, db.get_chat_messages(HISTORY_LIMIT))
    if chart_context:
        selected = str(chart_context.get("ticker") or "")[:8].upper()
        timeframe = str(chart_context.get("timeframe") or "")[:3].upper()
        indicators = ", ".join(str(item)[:16] for item in chart_context.get("indicators", [])[:8])
        messages[0]["content"] += f"\nSelected chart: {selected or 'none'} {timeframe}; indicators: {indicators or 'none'}."
    reply = await _get_reply(messages, mock=mode == "mock", user_message=message)
    if mode == "mock" and not (reply.trades or reply.watchlist_changes or reply.orders or reply.closes or reply.risks):
        if re.search(r"portfolio|portafolio|cartera", message, re.IGNORECASE):
            state = portfolio_view(ctx)
            reply.message = f"Portafolio simulado: valor ${state['total_value']:,.2f}, efectivo ${state['cash_balance']:,.2f}, P/L ${state['total_pnl']:,.2f}."
        elif re.search(r"chart|gr[aá]fico", message, re.IGNORECASE):
            symbol = str((chart_context or {}).get("ticker") or "la acción seleccionada")
            reply.message = f"Gráfico de {symbol}: observa tendencia, soporte, resistencia y volumen. Los precios pueden ser simulados."
    actions = await _execute(ctx, reply)
    return db.add_chat_message("assistant", reply.message, actions)


async def _get_reply(messages: list[dict], *, mock: bool, user_message: str) -> ChatReply:
    for attempt in range(1, ATTEMPTS + 1):
        if mock:
            raw = mock_reply(user_message)
        else:
            try:
                raw = await client.complete(messages)
            except Exception as exc:  # timeout, HTTP, auth or provider error: not worth retrying
                logger.warning("LLM call failed: %r", exc)
                raise LLMUnavailable("LLM call failed") from exc
        try:
            return parse_reply(raw)
        except InvalidReply as exc:
            logger.warning("Invalid LLM reply (attempt %d/%d): %s", attempt, ATTEMPTS, exc)
            if raw:
                messages = [*messages, {"role": "assistant", "content": raw}]
            messages = [
                *messages,
                {
                    "role": "user",
                    "content": f"Your last reply was invalid ({exc}). Reply again with only JSON matching the schema.",
                },
            ]
    raise LLMUnavailable("LLM returned invalid output twice")


async def _execute(ctx: AppContext, reply: ChatReply) -> dict:
    """Watchlist changes first, then trades, each in order; one failure never stops the rest."""
    watchlist_results = []
    for change in reply.watchlist_changes:
        result = {"ticker": change.ticker, "action": change.action, "status": "ok", "error": None}
        try:
            fn = add_to_watchlist if change.action == "add" else remove_from_watchlist
            result["ticker"] = await fn(ctx, change.ticker)
            db.add_activity("watchlist", f"Asistente: {change.action} {result['ticker']}", result["ticker"])
            ctx.account_version += 1
        except Exception as exc:
            result |= {"status": "failed", "error": _user_error(exc)}
        watchlist_results.append(result)

    trade_results = []
    for order in reply.trades:
        result = {
            "ticker": order.ticker,
            "side": order.side,
            "quantity": order.quantity,
            "status": "ok",
            "price": None,
            "error": None,
        }
        try:
            trade = await execute_trade(ctx, order.ticker, order.side, order.quantity)
            result |= {"ticker": trade["ticker"], "quantity": trade["quantity"], "price": trade["price"]}
            db.add_activity("trade", f"Asistente: {order.side.upper()} {order.quantity:g} {order.ticker}", order.ticker)
            ctx.account_version += 1
        except Exception as exc:
            result |= {"status": "failed", "error": _user_error(exc)}
        trade_results.append(result)

    actions = {"watchlist_changes": watchlist_results, "trades": trade_results}
    if reply.orders:
        actions["orders"] = []
        for instruction in reply.orders:
            result = {"ticker": instruction.ticker, "side": instruction.side, "type": instruction.type, "status": "ok", "error": None}
            try:
                outcome = await place_order(OrderBody(**instruction.model_dump()), ctx)
                result["order_status"] = outcome["status"]
            except Exception as exc:
                result |= {"status": "failed", "error": _user_error(exc)}
            actions["orders"].append(result)
    if reply.closes:
        actions["closes"] = []
        for ticker in reply.closes:
            result = {"ticker": ticker, "status": "ok", "error": None}
            try:
                await close_position(ticker, ctx)
            except Exception as exc:
                result |= {"status": "failed", "error": _user_error(exc)}
            actions["closes"].append(result)
    if reply.risks:
        actions["risks"] = []
        for instruction in reply.risks:
            result = {"ticker": instruction.ticker, "status": "ok", "error": None}
            try:
                await set_position_risk(instruction.ticker, RiskBody(**instruction.model_dump(exclude={"ticker"})), ctx)
            except Exception as exc:
                result |= {"status": "failed", "error": _user_error(exc)}
            actions["risks"].append(result)
    return actions


def _user_error(exc: Exception) -> str:
    if isinstance(exc, HTTPException):
        return str(exc.detail)
    if isinstance(exc, ValueError):  # the services' errors are written for users
        return str(exc)
    logger.exception("Unexpected error executing a chat action", exc_info=exc)
    return "Unexpected error while executing this action"
