"""Agents' to-do lists: markdown checklists at <project>/.agent-monitor/plans/<agent>.md
(or .agent-monitor/<team>/plans/<agent>.md when a lead knows its team name)."""

from __future__ import annotations

import re
from dataclasses import dataclass

MARKS = {" ": "pending", "~": "in_progress", "x": "completed", "X": "completed", "!": "failed", "-": "cancelled"}
LINE = re.compile(
    r"^\s*[-*+]\s*\[(?P<mark>[ ~xX!\-])\]\s+(?:(?P<id>[A-Za-z]{1,3}\d+)\s*[.:)]?\s+)?(?P<title>\S.*?)\s*$"
)
NOTE = re.compile(r"\s+(?:—|--)\s+")
PLAN_PATH = re.compile(r"[\\/]\.agent-monitor[\\/](?:(?P<team>[^\\/]+)[\\/])?plans[\\/](?P<agent>[^\\/]+)\.md$", re.I)
LAYOUT_PATH = re.compile(r"[\\/]\.agent-monitor[\\/](?:(?P<team>[^\\/]+)[\\/])?layout\.json$", re.I)


@dataclass(frozen=True)
class PlanItem:
    key: str
    title: str
    status: str
    note: str | None
    order: int


def parse_plan(text: str) -> list[PlanItem]:
    items: list[PlanItem] = []
    seen: dict[str, int] = {}
    for line in text.splitlines():
        match = LINE.match(line)
        if not match:
            continue
        title, note = (NOTE.split(match["title"], maxsplit=1) + [None])[:2]
        key = match["id"].upper() if match["id"] else " ".join(title.lower().split())
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            key = f"{key}#{seen[key]}"
        items.append(PlanItem(key=key, title=title.strip(), status=MARKS[match["mark"]], note=note, order=len(items)))
    return items
