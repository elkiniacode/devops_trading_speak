"""The real model call: LiteLLM -> OpenRouter -> Cerebras (see the `cerebras` skill)."""

from __future__ import annotations

import asyncio
import importlib
import os

from pydantic import BaseModel

from .schemas import ChatReply

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}
TIMEOUT_SECONDS = 30.0  # for the whole call, including the HTTP client's own retries

# Use the model cost map bundled with litellm instead of downloading it on import.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")


async def _litellm():
    # Imported lazily and off the event loop: it takes seconds and is unused in mock mode.
    return await asyncio.to_thread(importlib.import_module, "litellm")


async def preload() -> None:
    """Import litellm in the background at startup, so the first chat doesn't wait for it."""
    await _litellm()


async def complete(messages: list[dict], *, response_format: type[BaseModel] = ChatReply) -> str | None:
    """One structured-output completion. Returns the raw JSON text; the caller validates it.

    ``response_format`` is the schema the model must follow (chat by default; charla themes pass their own).
    Raises TimeoutError after TIMEOUT_SECONDS, and whatever litellm raises on HTTP or provider errors.
    """
    litellm = await _litellm()
    response = await asyncio.wait_for(
        litellm.acompletion(
            model=MODEL,
            messages=messages,
            response_format=response_format,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
            timeout=TIMEOUT_SECONDS,
        ),
        TIMEOUT_SECONDS,
    )
    return response.choices[0].message.content
