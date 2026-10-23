"""Portfolio routes (CONTRACTS.md §5.3-5.5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app import db
from app.context import AppContext, get_ctx
from app.services.portfolio import portfolio_view
from app.services.trading import execute_trade

router = APIRouter()


class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str


@router.get("/api/portfolio")
def get_portfolio(ctx: AppContext = Depends(get_ctx)) -> dict:
    return portfolio_view(ctx)


@router.post("/api/portfolio/trade")
async def trade(body: TradeRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        executed = await execute_trade(ctx, body.ticker, body.side, body.quantity)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"trade": executed, "portfolio": portfolio_view(ctx)}


@router.get("/api/portfolio/history")
def history(limit: int = Query(500, ge=1, le=5000)) -> dict:
    """The most recent ``limit`` snapshots, oldest first."""
    return {"snapshots": db.get_snapshots(limit)}
