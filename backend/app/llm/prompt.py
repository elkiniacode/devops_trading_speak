"""Builds the message list for one chat turn: system prompt, live context, recent history."""

from __future__ import annotations

from app.services.portfolio import STARTING_CASH, portfolio_view
from app.services.watchlist import watchlist_view

SYSTEM_PROMPT = """\
You are FinAlly, an AI trading assistant inside a simulated trading workstation. \
The user trades a paper portfolio with virtual money: market orders fill at current prices; \
limit and stop orders stay pending until triggered. No fees. Fractional shares use at most 4 decimals.

What you do:
- Analyze the portfolio: composition, concentration risk, unrealized P&L, cash level.
- Suggest trades with brief, data-driven reasoning.
- Execute trades only when the user asks for them or clearly agrees to one you proposed. \
Never trade on your own initiative.
- Manage the watchlist: add or remove tickers when the user asks, or when it clearly helps \
what they are doing (for example, adding a ticker they want to buy).
- If a request is ambiguous (no quantity, unclear ticker, "buy some tech"), ask a short \
clarifying question instead of guessing, and leave the action lists empty.

How actions work:
- Put each order in "trades" (ticker, side "buy" or "sell", quantity in shares > 0) and each \
watchlist edit in "watchlist_changes" (ticker, action "add" or "remove"). Use empty arrays when \
there is nothing to do. At most 10 of each.
- Use uppercase ticker symbols, e.g. AAPL or BRK.B.
- To spend a dollar amount, divide it by the current price and round the share count DOWN \
to 4 decimal places.
- Watchlist changes run before trades, so you can add a new ticker and buy it in the same reply.
- The system executes the actions after you reply and validates each one (enough cash for \
buys, enough shares for sells). So describe orders as intent, never in the past tense: \
"Placing a buy order for 10 AAPL", not "I bought 10 AAPL".
- In the conversation history, the system appends an [Action results] block to your earlier \
replies (never write one yourself). Use it to tell the user about any failed action and why, \
and do not assume a failed order went through.

Style: concise, specific, numbers first. Plain text, no markdown tables. Always respond \
with JSON matching the required schema: {"message": string, "trades": [...], \
"watchlist_changes": [...]}."""


SYSTEM_PROMPT += """

The terminal also supports pending limit/stop orders, closing a position, and long-position
stop-loss/take-profit. Use `orders` for explicit notional orders with ticker, side, type,
notional and (for limit/stop) trigger_price. Use `closes` for explicit requests to close
whole positions. Use `risks` for explicit requests to set or clear a position's levels.
Include empty arrays for these optional fields when there are no such requests. Never infer
trading actions from a question or commentary. Prices and sentiment may be simulated;
identify simulated data. Reply to the user in Spanish.
"""


def _money(v: float) -> str:
    return f"-${abs(v):,.2f}" if v < 0 else f"${v:,.2f}"


def _signed_money(v: float) -> str:
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _qty(q: float) -> str:
    return format(q, "f").rstrip("0").rstrip(".")


def _mode_note(mode: str) -> str:
    if mode == "simulator":
        return 'simulated prices; "change %" is since the simulation session started'
    if mode == "massive-eod":
        return 'END-OF-DAY closing prices, not live; "change %" is vs. the previous close'
    return 'live (possibly delayed) market prices; "change %" is vs. the previous close'


def build_context(ctx) -> str:
    """Fresh state for this request: mode, cash, totals, positions and watchlist prices."""
    p = portfolio_view(ctx)
    lines = [
        f"## Current state (as of {p['as_of']})",
        f"Market data: {ctx.market.mode} ({_mode_note(ctx.market.mode)})",
        f"Cash: {_money(p['cash_balance'])}",
        f"Total portfolio value: {_money(p['total_value'])} "
        f"(total P&L {_signed_money(p['total_pnl'])}, {_pct(p['total_pnl_percent'])} "
        f"vs. the {_money(STARTING_CASH)} start)",
    ]
    if not p["valuation_complete"]:
        lines.append("Note: some positions have no price yet and are valued at their average cost.")

    lines.append("")
    if p["positions"]:
        lines.append("Positions:")
        total = p["total_value"] or 1.0
        for pos in p["positions"]:
            head = f"- {pos['ticker']}: {_qty(pos['quantity'])} sh, avg cost {_money(pos['avg_cost'])}"
            if pos["current_price"] is None:
                lines.append(f"{head}, no current price")
                continue
            weight = pos["market_value"] / total * 100
            stale = " (price is stale)" if pos.get("stale") else ""
            lines.append(
                f"{head}, price {_money(pos['current_price'])}{stale}, value {_money(pos['market_value'])} "
                f"({weight:.1f}% of portfolio), unrealized P&L {_signed_money(pos['unrealized_pnl'])} "
                f"({_pct(pos['unrealized_pnl_percent'])})"
            )
    else:
        lines.append("Positions: none (all cash).")

    lines.append("")
    watchlist = watchlist_view(ctx)
    if watchlist:
        lines.append("Watchlist:")
        for item in watchlist:
            q = item["quote"]
            if q is None:
                lines.append(f"- {item['ticker']}: no price yet")
            else:
                lines.append(f"- {item['ticker']}: {_money(q['price'])} ({_pct(q['change_percent'])})")
    else:
        lines.append("Watchlist: empty.")
    return "\n".join(lines)


def format_action_results(actions: dict | None) -> str:
    """The [Action results] block appended to a stored assistant message in the history."""
    if not actions:
        return ""
    lines = []
    for c in actions.get("watchlist_changes", []):
        outcome = "ok" if c["status"] == "ok" else f"FAILED: {c['error']}"
        lines.append(f"- watchlist {c['action']} {c['ticker']}: {outcome}")
    for t in actions.get("trades", []):
        if t["status"] == "ok":
            outcome = f"filled at {_money(t['price'])}"
        else:
            outcome = f"FAILED: {t['error']}"
        lines.append(f"- {t['side']} {_qty(t['quantity'])} {t['ticker']}: {outcome}")
    for order in actions.get("orders", []):
        outcome = order.get("order_status") if order["status"] == "ok" else f"FAILED: {order['error']}"
        lines.append(f"- order {order['type']} {order['side']} {order['ticker']}: {outcome}")
    for close in actions.get("closes", []):
        lines.append(f"- close {close['ticker']}: {'ok' if close['status'] == 'ok' else 'FAILED: ' + str(close['error'])}")
    for risk in actions.get("risks", []):
        lines.append(f"- risk {risk['ticker']}: {'ok' if risk['status'] == 'ok' else 'FAILED: ' + str(risk['error'])}")
    if not lines:
        return ""
    return "\n\n[Action results]\n" + "\n".join(lines)


def build_messages(ctx, history: list[dict]) -> list[dict]:
    """System prompt plus live context, then the stored history (which ends with the new user message)."""
    messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{build_context(ctx)}"}]
    for m in history:
        content = m["content"]
        if m["role"] == "assistant":
            content += format_action_results(m.get("actions"))
        messages.append({"role": m["role"], "content": content})
    return messages
