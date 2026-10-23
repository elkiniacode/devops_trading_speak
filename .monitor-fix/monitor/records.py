"""Normalize raw Claude Code transcript records into a few item kinds the parser understands."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass, field

TEAMMATE = re.compile(r"<teammate-message\s+([^>]*)>(.*?)</teammate-message>", re.S)
AGENT_MESSAGE = re.compile(r'<agent-message\s+from="([^"]+)"[^>]*>(.*?)</agent-message>', re.S)
ATTR = re.compile(r'([\w-]+)="([^"]*)"')
# Blocks Claude Code injects into user turns; they are not things a person typed.
SYSTEM_BLOCKS = re.compile(
    r"<(system-reminder|task-notification|local-command-stdout|local-command-stderr|local-command-caveat|"
    r"bash-input|bash-stdout|bash-stderr)>.*?</\1>",
    re.S,
)
IGNORED_PROMPTS = ("[Request interrupted", "Caveat:", "Base directory for this skill")


@dataclass
class Item:
    """One thing an agent did or received.

    kind is one of: text, tool_use, tool_result, inbox, idle, prompt, notice, turn_end, join.
    """

    kind: str
    ts: str
    uid: str
    data: dict = field(default_factory=dict)


def parse_record(rec: dict) -> list[Item]:
    rtype = rec.get("type")
    if rtype not in ("user", "assistant"):
        return []
    ts = rec.get("timestamp") or ""
    uid = rec.get("uuid") or ""
    content = (rec.get("message") or {}).get("content")
    # Meta records are injected context, except that messages from other sessions arrive as meta too.
    if rec.get("isMeta") and not (isinstance(content, str) and ("<agent-message" in content or "<teammate-message" in content)):
        return []
    if rtype == "assistant":
        return _assistant_items(rec, ts, uid, content)
    if isinstance(content, str):
        return _user_string_items(ts, uid, content)
    return _user_list_items(rec, ts, uid, content or [])


def _assistant_items(rec: dict, ts: str, uid: str, content) -> list[Item]:
    items = []
    for i, block in enumerate(content or []):
        btype = block.get("type")
        if btype == "text" and block.get("text", "").strip():
            items.append(Item("text", ts, f"{uid}:{i}", {"text": block["text"].strip()}))
        elif btype == "tool_use":
            items.append(
                Item("tool_use", ts, f"{uid}:{i}", {"id": block["id"], "name": block["name"], "input": block.get("input") or {}})
            )
    if (rec.get("message") or {}).get("stop_reason") == "end_turn":
        items.append(Item("turn_end", ts, f"{uid}:end"))
    return items


def _user_string_items(ts: str, uid: str, content: str) -> list[Item]:
    items = []
    for i, (attrs, body) in enumerate(TEAMMATE.findall(content)):
        meta = {k: html.unescape(v) for k, v in ATTR.findall(attrs)}
        body = body.strip()
        sender = meta.get("teammate_id", "")
        control = _json_object(body)
        if control is not None:
            kind = control.get("type")
            if kind == "idle_notification":
                items.append(Item("idle", ts, f"{uid}:{i}", {"from": control.get("from") or sender}))
            continue
        items.append(
            Item("inbox", ts, f"{uid}:{i}", {"from": sender, "summary": meta.get("summary"), "body": body, "color": meta.get("color")})
        )
    for i, (sender, body) in enumerate(AGENT_MESSAGE.findall(content)):
        body = body.strip()
        if body.startswith(f"{sender}:"):
            body = body[len(sender) + 1 :].strip()
        items.append(Item("inbox", ts, f"{uid}:a{i}", {"from": sender, "summary": None, "body": body}))
    if items:
        return items
    text = SYSTEM_BLOCKS.sub("", content).strip()
    if not text:
        return [Item("notice", ts, uid)]
    if text.startswith(IGNORED_PROMPTS) or text.startswith("Another Claude session sent a message"):
        return []
    return [Item("prompt", ts, uid, {"text": text})]


def _user_list_items(rec: dict, ts: str, uid: str, content: list) -> list[Item]:
    items = []
    texts = []
    for i, block in enumerate(content):
        btype = block.get("type")
        if btype == "tool_result":
            extra = rec.get("toolUseResult")
            items.append(
                Item(
                    "tool_result",
                    ts,
                    f"{uid}:{i}",
                    {
                        "tool_use_id": block.get("tool_use_id"),
                        "is_error": bool(block.get("is_error")),
                        "text": _flatten(block.get("content")),
                        "extra": extra if isinstance(extra, dict) else {},
                    },
                )
            )
        elif btype == "text":
            texts.append(block.get("text", ""))
        elif btype == "image":
            texts.append("[image]")
    if items:
        return items
    text = SYSTEM_BLOCKS.sub("", "\n".join(texts)).strip()
    if not text or text.startswith(IGNORED_PROMPTS):
        return []
    return [Item("prompt", ts, uid, {"text": text})]


def _flatten(content) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "image":
            parts.append("[image]")
    return "\n".join(parts)


def _json_object(body: str) -> dict | None:
    if not body.startswith("{"):
        return None
    try:
        value = json.loads(body)
    except ValueError:
        return None
    return value if isinstance(value, dict) and "type" in value else None
