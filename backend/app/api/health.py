"""GET /api/health (CONTRACTS.md §5.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import llm_mode
from app.context import AppContext, get_ctx

router = APIRouter()


@router.get("/api/health")
def health(ctx: AppContext = Depends(get_ctx)) -> dict:
    return {"status": "ok", "market_data": ctx.market.mode, "llm": llm_mode()}
