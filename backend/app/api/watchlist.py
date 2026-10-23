"""Watchlist routes (CONTRACTS.md §5.2). Add and remove are idempotent and return the full list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.context import AppContext, get_ctx
from app.services.watchlist import add_to_watchlist, remove_from_watchlist, watchlist_view

router = APIRouter()


class WatchlistAdd(BaseModel):
    ticker: str


@router.get("/api/watchlist")
def get_watchlist(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"watchlist": watchlist_view(ctx)}


@router.post("/api/watchlist")
async def add_ticker(body: WatchlistAdd, ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        await add_to_watchlist(ctx, body.ticker)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"watchlist": watchlist_view(ctx)}


@router.delete("/api/watchlist/{ticker}")
async def remove_ticker(ticker: str, ctx: AppContext = Depends(get_ctx)) -> dict:
    try:
        await remove_from_watchlist(ctx, ticker)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"watchlist": watchlist_view(ctx)}
