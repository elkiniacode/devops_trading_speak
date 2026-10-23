"""Structured output the model must return (CONTRACTS §7.1).

Only the reply's structure is checked here: keys, types, enums, a non-empty message and
at most 10 actions per list. Business rules (quantity > 0, at most 4 dp, ticker format,
cash, shares) belong to app.services and fail just that one action.

The JSON schema sent to the model is kept to plain types, enums and required keys,
which every strict structured-output provider accepts. The message and cap rules are
AfterValidators: Pydantic applies them on parse but leaves them out of the schema.
"""

from __future__ import annotations

import re
import json
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError

MAX_ACTIONS = 10  # per list; more than this makes the whole reply invalid

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


def _clean_ticker(v: str) -> str:
    # Only tidy it up: a malformed symbol fails that one action in app.services, not the reply.
    return v.strip().upper()


def _non_empty(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("message must not be empty")
    return v


def _capped(v: list) -> list:
    if len(v) > MAX_ACTIONS:
        raise ValueError(f"at most {MAX_ACTIONS} items allowed")
    return v


Ticker = Annotated[str, AfterValidator(_clean_ticker)]


class TradeRequest(BaseModel):
    # NaN and Infinity are not JSON numbers, so they are a type error, not a business rule.
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    ticker: Ticker
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistChange(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ticker: Ticker
    action: Literal["add", "remove"]


class OrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    ticker: Ticker
    side: Literal["buy", "sell"]
    type: Literal["market", "limit", "stop"]
    notional: float
    trigger_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    ticker: Ticker
    stop_loss: float | None = None
    take_profit: float | None = None


class ChatReply(BaseModel):
    """One model reply: the text shown to the user plus the actions to execute."""

    model_config = ConfigDict(extra="forbid", strict=True)

    message: Annotated[str, AfterValidator(_non_empty)]
    trades: Annotated[list[TradeRequest], AfterValidator(_capped)]
    watchlist_changes: Annotated[list[WatchlistChange], AfterValidator(_capped)]
    orders: Annotated[list[OrderRequest], AfterValidator(_capped)]
    closes: Annotated[list[Ticker], AfterValidator(_capped)]
    risks: Annotated[list[RiskRequest], AfterValidator(_capped)]


class InvalidReply(ValueError):
    """The model's output is not a valid ChatReply."""


def parse_reply(raw: str | None) -> ChatReply:
    """Validate raw model output as a whole. Raises InvalidReply with a short reason."""
    text = (raw or "").strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    if not text:
        raise InvalidReply("empty response")
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            for key in ("orders", "closes", "risks"):
                parsed.setdefault(key, [])
            text = json.dumps(parsed)
    except json.JSONDecodeError:
        pass
    try:
        return ChatReply.model_validate_json(text)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_input=False)
        if errors[0]["type"] == "json_invalid":
            raise InvalidReply("response is not valid JSON") from exc
        reasons = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in errors[:5])
        raise InvalidReply(reasons) from exc
