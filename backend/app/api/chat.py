"""Chat routes (CONTRACTS.md §5.6)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.context import AppContext, get_ctx
from app.llm.service import LLMNotConfigured, LLMUnavailable, handle_chat

router = APIRouter()

MAX_MESSAGE_CHARS = 2_000
UNAVAILABLE = "The AI assistant is unavailable right now. Please try again."


class ChatRequest(BaseModel):
    message: str
    ticker: str | None = Field(default=None, max_length=8)
    timeframe: str | None = Field(default=None, max_length=3)
    indicators: list[str] = Field(default_factory=list, max_length=8)
    chart_levels: list[float] = Field(default_factory=list, max_length=12)


@router.post("/api/chat")
async def post_chat(body: ChatRequest, ctx: AppContext = Depends(get_ctx)) -> dict:
    message = body.message.strip()
    if not message:
        raise HTTPException(400, "Message must not be empty")
    if len(message) > MAX_MESSAGE_CHARS:
        raise HTTPException(400, f"Message can be at most {MAX_MESSAGE_CHARS:,} characters")
    try:
        return await handle_chat(ctx, message, body.model_dump(exclude={"message"}, exclude_none=True))
    except LLMNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except LLMUnavailable as exc:
        raise HTTPException(502, UNAVAILABLE) from exc


@router.get("/api/chat/history")
async def get_chat_history(limit: int = Query(50, ge=1, le=500)) -> dict:
    return {"messages": db.get_chat_messages(limit)}
