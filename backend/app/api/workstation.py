"""Supplementary workstation APIs and simulated order processing."""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app import db
from app.context import AppContext, get_ctx
from app.market.candles import TIMEFRAME_SECONDS, history
from app.services.portfolio import portfolio_view

router = APIRouter()


class OrderBody(BaseModel):
    ticker: str
    side: str
    type: str
    notional: float = Field(gt=0, le=1_000_000)
    trigger_price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    client_order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class RiskBody(BaseModel):
    stop_loss: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    take_profit: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class OrderEditBody(BaseModel):
    trigger_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    stop_loss: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    take_profit: float | None = Field(default=None, gt=0, allow_inf_nan=False)


@router.get("/api/workstation")
def get_workstation(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"health": {"status": "ok", "market_data": ctx.market.mode}, "portfolio": portfolio_view(ctx),
            "watchlist": db.get_watchlist(), "orders": db.get_orders(status=None), "risk": db.get_risk(),
            "trades": db.get_trades(100), "activity": db.get_activity(100), "account_version": ctx.account_version}


@router.get("/api/market/candles")
def candles(ticker: str, timeframe: str = "H1", limit: int = Query(150, ge=1, le=500), ctx: AppContext = Depends(get_ctx)) -> dict:
    symbol = ticker.strip().upper()
    if timeframe not in TIMEFRAME_SECONDS:
        raise HTTPException(400, "Intervalo inválido")
    quote = ctx.cache.get(symbol)
    if quote is None:
        raise HTTPException(404, f"No hay precios disponibles para {symbol}")
    simulated = ctx.market.mode == "simulator"
    rows = history(symbol, timeframe, quote.price, limit) if simulated else ctx.cache.get_candles(symbol, timeframe, limit)
    return {"ticker": symbol, "timeframe": timeframe, "candles": rows,
            "source": "simulator" if simulated else "collected", "synthetic": simulated,
            "complete": simulated, "latest_timestamp": rows[-1]["time"] if rows else None}


@router.post("/api/orders")
async def place_order(body: OrderBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    ticker, side, kind = body.ticker.strip().upper(), body.side.lower(), body.type.lower()
    if side not in {"buy", "sell"} or kind not in {"market", "limit", "stop"}:
        raise HTTPException(400, "Orden o lado no válido")
    async with ctx.trade_lock:
        existing = db.get_market_request(body.client_order_id) if kind == "market" else db.get_order_by_client_id(body.client_order_id)
        if existing:
            if existing["ticker"] != ticker or existing["side"] != side or existing["notional"] != body.notional or (kind != "market" and existing["type"] != kind):
                raise HTTPException(409, "El identificador ya se utilizó para otra orden")
            if kind != "market":
                return {"status": existing["status"], "order": existing}
            if existing["status"] == "filled":
                trade = db.complete_market_request(existing["id"], 0, 0, None, None)
                return {"status": "filled", "trade": trade, "portfolio": portfolio_view(ctx)}
        try:
            await ctx.market.add_ticker(ticker)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        quote = ctx.cache.get_fresh(ticker, ctx.market.max_quote_age)
        if quote is None:
            raise HTTPException(400, f"No hay un precio vigente para {ticker}")
        quantity = round(body.notional / quote.price, 4)
        if quantity <= 0:
            raise HTTPException(400, "El monto es demasiado pequeño para operar")
        if side == "sell" and (body.stop_loss is not None or body.take_profit is not None):
            raise HTTPException(400, "Los niveles de riesgo se configuran sobre posiciones abiertas, no sobre órdenes de venta")
        entry_price = body.trigger_price if kind != "market" and body.trigger_price is not None else quote.price
        if body.stop_loss is not None and body.stop_loss >= entry_price:
            raise HTTPException(400, "El stop loss debe estar debajo del precio de entrada")
        if body.take_profit is not None and body.take_profit <= entry_price:
            raise HTTPException(400, "El take profit debe estar encima del precio de entrada")
        if kind == "market":
            request = existing or db.create_market_request(body.client_order_id, ticker, side, body.notional)
            try:
                trade = db.complete_market_request(request["id"], quantity, quote.price, body.stop_loss, body.take_profit)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            db.record_snapshot(portfolio_view(ctx)["total_value"])
            ctx.account_version += 1
            return {"status": "filled", "trade": trade, "portfolio": portfolio_view(ctx)}
        price = body.trigger_price
        if price is None:
            raise HTTPException(400, "Define el precio de activación")
        if kind == "limit" and ((side == "buy" and price >= quote.price) or (side == "sell" and price <= quote.price)):
            raise HTTPException(400, "La orden límite debe quedar al otro lado del precio actual")
        if kind == "stop" and ((side == "buy" and price <= quote.price) or (side == "sell" and price >= quote.price)):
            raise HTTPException(400, "La orden stop debe quedar al otro lado del precio actual")
        if side == "sell":
            position = db.get_position(ticker)
            if not position or quantity > position["quantity"]:
                raise HTTPException(400, "No tienes suficientes acciones para esta orden")
        order = db.create_order({"client_order_id": body.client_order_id, "ticker": ticker, "side": side,
                                 "type": kind, "notional": body.notional, "trigger_price": price,
                                 "stop_loss": body.stop_loss, "take_profit": body.take_profit})
        db.add_activity("order", f"Orden {kind.upper()} {side.upper()} {ticker} creada", ticker)
        ctx.account_version += 1
        return {"status": order["status"], "order": order}


@router.patch("/api/orders/{order_id}")
async def edit_order(order_id: str, body: OrderEditBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    async with ctx.trade_lock:
        current = db.get_order(order_id)
        if current is None or current["status"] != "pending":
            raise HTTPException(409, "La orden ya no está pendiente")
        changes = body.model_dump(exclude_unset=True)
        price = changes.get("trigger_price", current["trigger_price"])
        if price is None:
            raise HTTPException(400, "Define el precio de activación")
        quote = ctx.cache.get_fresh(current["ticker"], ctx.market.max_quote_age)
        if not quote:
            raise HTTPException(400, "No hay un precio vigente para editar la orden")
        side, kind = current["side"], current["type"]
        if kind == "limit" and ((side == "buy" and price >= quote.price) or (side == "sell" and price <= quote.price)):
            raise HTTPException(400, "Precio límite inválido")
        if kind == "stop" and ((side == "buy" and price <= quote.price) or (side == "sell" and price >= quote.price)):
            raise HTTPException(400, "Precio stop inválido")
        stop_loss = changes.get("stop_loss", current["stop_loss"])
        take_profit = changes.get("take_profit", current["take_profit"])
        if side == "sell" and (stop_loss is not None or take_profit is not None):
            raise HTTPException(400, "Los niveles de riesgo solo se admiten en compras")
        if stop_loss is not None and stop_loss >= price:
            raise HTTPException(400, "El stop loss debe estar debajo de la entrada")
        if take_profit is not None and take_profit <= price:
            raise HTTPException(400, "El take profit debe estar encima de la entrada")
        order = db.update_order(order_id, changes)
        db.add_activity("order", f"Orden {order_id[:8]} actualizada", order["ticker"])
        ctx.account_version += 1
        return {"order": order}


@router.delete("/api/orders/{order_id}")
async def cancel_order(order_id: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    async with ctx.trade_lock:
        order = db.get_order(order_id)
        if not order or not db.finish_order(order_id, "cancelled"):
            raise HTTPException(409, "La orden ya no está pendiente")
        db.add_activity("order", f"Orden {order_id[:8]} cancelada", order["ticker"])
        ctx.account_version += 1
        return {"ok": True}


@router.put("/api/positions/{ticker}/risk")
async def set_position_risk(ticker: str, body: RiskBody, ctx: AppContext = Depends(get_ctx)) -> dict:
    symbol = ticker.strip().upper()
    async with ctx.trade_lock:
        position = db.get_position(symbol)
        quote = ctx.cache.get_fresh(symbol, ctx.market.max_quote_age)
        if not position or not quote:
            raise HTTPException(404, "No hay una posición vigente para actualizar")
        if body.stop_loss is not None and body.stop_loss >= quote.price:
            raise HTTPException(400, "El stop loss debe quedar debajo del precio actual")
        if body.take_profit is not None and body.take_profit <= quote.price:
            raise HTTPException(400, "El take profit debe quedar encima del precio actual")
        result = db.set_risk(symbol, body.stop_loss, body.take_profit)
        db.add_activity("risk", f"Niveles de riesgo actualizados para {symbol}", symbol)
        ctx.account_version += 1
        return result


@router.post("/api/positions/{ticker}/close")
async def close_position(ticker: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    symbol = ticker.strip().upper()
    async with ctx.trade_lock:
        position = db.get_position(symbol)
        quote = ctx.cache.get_fresh(symbol, ctx.market.max_quote_age)
        if not position or not quote:
            raise HTTPException(404, "No hay una posición vigente para cerrar")
        trade = db.apply_trade(symbol, "sell", position["quantity"], quote.price)
        db.set_risk(symbol, None, None)
        db.record_snapshot(portfolio_view(ctx)["total_value"])
        db.add_activity("trade", f"Posición {symbol} cerrada", symbol)
        ctx.account_version += 1
        return {"trade": trade, "portfolio": portfolio_view(ctx)}


@router.get("/api/portfolio/trades")
def trades(limit: int = Query(100, ge=1, le=500)) -> dict:
    return {"trades": db.get_trades(limit)}


@router.get("/api/activity")
def activity(limit: int = Query(100, ge=1, le=500)) -> dict:
    return {"activity": db.get_activity(limit)}


@router.get("/api/stream/workstation")
async def stream_workstation(request: Request, account_only: bool = False) -> StreamingResponse:
    ctx: AppContext = request.app.state.ctx
    async def events():
        last_prices = last_account = -1
        last_write = time.monotonic()
        while not await request.is_disconnected():
            if not account_only and ctx.cache.version != last_prices:
                last_prices = ctx.cache.version
                payload = {symbol: quote.to_dict() for symbol, quote in ctx.cache.get_all().items()}
                yield f"event: prices\ndata: {json.dumps(payload)}\n\n"
                last_write = time.monotonic()
            if ctx.account_version != last_account:
                last_account = ctx.account_version
                yield f"event: account\ndata: {{\"version\":{last_account}}}\n\n"
                last_write = time.monotonic()
            if time.monotonic() - last_write > 15:
                yield ": keepalive\n\n"
                last_write = time.monotonic()
            await asyncio.sleep(0.5)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def order_monitor(ctx: AppContext, interval: float = 0.5) -> None:
    while True:
        await asyncio.sleep(interval)
        for candidate in db.get_orders():
            async with ctx.trade_lock:
                order = db.get_order(candidate["id"])
                if not order or order["status"] != "pending":
                    continue
                quote = ctx.cache.get_fresh(order["ticker"], ctx.market.max_quote_age)
                if not quote:
                    continue
                if order["type"] == "limit":
                    hit = quote.price <= order["trigger_price"] if order["side"] == "buy" else quote.price >= order["trigger_price"]
                else:
                    hit = quote.price >= order["trigger_price"] if order["side"] == "buy" else quote.price <= order["trigger_price"]
                if not hit:
                    continue
                try:
                    db.complete_pending_order(order["id"], quote.price)
                except ValueError as exc:
                    db.finish_order(order["id"], "rejected", str(exc))
                    db.add_activity("rejected", f"Orden rechazada: {exc}", order["ticker"])
                except Exception:
                    # Keep the monitor alive if an individual order encounters a transient DB error.
                    continue
                else:
                    db.record_snapshot(portfolio_view(ctx)["total_value"])
                ctx.account_version += 1
        for risk in db.get_risk():
            async with ctx.trade_lock:
                position = db.get_position(risk["ticker"])
                quote = ctx.cache.get_fresh(risk["ticker"], ctx.market.max_quote_age)
                if not position or not quote:
                    continue
                sl = risk["stop_loss"] is not None and quote.price <= risk["stop_loss"]
                tp = risk["take_profit"] is not None and quote.price >= risk["take_profit"]
                if sl or tp:
                    db.apply_trade(risk["ticker"], "sell", position["quantity"], quote.price)
                    db.set_risk(risk["ticker"], None, None)
                    db.record_snapshot(portfolio_view(ctx)["total_value"])
                    db.add_activity("risk", f"Posición {risk['ticker']} cerrada por nivel de riesgo", risk["ticker"])
                    ctx.account_version += 1
