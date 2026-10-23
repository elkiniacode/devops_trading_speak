"""Group tool calls into readable steps: what kind they are, how they are titled, what tests reported."""

from __future__ import annotations

import re
from urllib.parse import urlparse

READ_TOOLS = {"Read", "Glob", "Grep", "LS", "NotebookRead"}
SEARCH_TOOLS = {"Glob", "Grep"}
EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
COMMAND_TOOLS = {"Bash", "PowerShell", "BashOutput", "TaskStop", "KillShell", "Monitor"}
RESEARCH_TOOLS = {"WebSearch", "WebFetch"}
HIDDEN_TOOLS = {"ToolSearch", "ListAgents", "TodoWrite", "TaskList", "TaskGet"}
# Consecutive calls of these kinds (in the same task) become one step.
MERGEABLE = {"read", "edit", "research", "browser", "command"}

TEST_COMMAND = re.compile(
    r"\b(pytest|vitest|jest|mocha|playwright\s+test|(?:npm|pnpm|yarn)\s+(?:run\s+)?test|go\s+test|cargo\s+test|unittest)\b"
)
TEST_COUNT = re.compile(r"\b(\d+)\s+(passed|failed|errors?|skipped|flaky)\b", re.I)


def classify(name: str, inp: dict) -> str:
    if name in HIDDEN_TOOLS:
        return "hidden"
    if name == "SendMessage":
        return "message_out"
    if name in ("Agent", "Task") and inp.get("name"):
        return "spawn"
    if name in READ_TOOLS:
        return "read"
    if name in EDIT_TOOLS:
        return "edit"
    if name in COMMAND_TOOLS:
        return "test" if TEST_COMMAND.search(str(inp.get("command", ""))) else "command"
    if name in RESEARCH_TOOLS or name.startswith("mcp__plugin_context7") or name.startswith("mcp__context7"):
        return "research"
    if "playwright" in name or "browser" in name:
        return "browser"
    return "tool"


def parse_test_counts(output: str) -> dict | None:
    """The last count reported for each outcome (pytest, vitest, jest and Playwright summaries)."""
    counts: dict[str, int] = {}
    for number, word in TEST_COUNT.findall(output or ""):
        word = word.lower()
        word = "failed" if word.startswith("error") else word
        counts[word] = int(number)
    if not counts:
        return None
    return {"passed": counts.get("passed", 0), "failed": counts.get("failed", 0), "skipped": counts.get("skipped", 0)}


def command_label(inp: dict) -> str:
    label = inp.get("description")
    if not label:
        lines = str(inp.get("command", "")).strip().splitlines()
        label = lines[0] if lines else "a command"
    if inp.get("run_in_background"):
        label = f"Started in background: {label}"
    return clip_line(label, 90)


def lookup_label(name: str, inp: dict) -> str:
    if name == "WebSearch":
        return f"searched “{clip_line(inp.get('query', ''), 60)}”"
    if name == "WebFetch":
        return f"read {urlparse(inp.get('url', '')).netloc or 'a web page'}"
    return f"looked up docs ({name.split('__')[-1]})"


def pretty_tool(name: str) -> str:
    if name.startswith("mcp__"):
        parts = name.split("__")
        return f"{parts[1].replace('plugin_', '')}: {parts[-1].replace('_', ' ')}"
    return name


def clip_line(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def short_list(names: list[str], limit: int = 3) -> str:
    unique = list(dict.fromkeys(names))
    shown = ", ".join(unique[:limit])
    return shown + (f" +{len(unique) - limit} more" if len(unique) > limit else "")


def basename(path: str) -> str:
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] if path else "?"


def headline(text: str | None, limit: int = 100) -> str:
    """The first non-empty line, without markdown markers."""
    for line in (text or "").splitlines():
        line = re.sub(r"^[\s#>*\-]+", "", line).replace("**", "").replace("`", "").strip()
        if line:
            return clip_line(line, limit)
    return ""


def note_title(text: str) -> str:
    return headline(text) or "Note"


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else ("es" if word.endswith("h") else "s"))


def step_title(kind: str, meta: dict) -> str:
    if kind == "read":
        reads, searches = meta.get("reads", []), meta.get("searches", 0)
        if not searches:
            return f"Read {plural(len(reads), 'file')}: {short_list([basename(p) for p in reads])}"
        if not reads:
            return f"Searched the code ({plural(searches, 'search')})"
        return f"Explored the code: read {plural(len(reads), 'file')}, {plural(searches, 'search')}"
    if kind == "edit":
        files = meta.get("files", {})
        names = [basename(p) for p in files]
        if files and meta.get("failed", 0) >= sum(info["changes"] for info in files.values()):
            return f"Couldn't save {short_list(names)}"
        if len(files) == 1:
            (path, info), = files.items()
            if info.get("created") and info["changes"] == 1:
                return f"Created {basename(path)}"
            changes = info["changes"]
            return f"Edited {basename(path)}" + (f" ({changes} changes)" if changes > 1 else "")
        created = sum(1 for info in files.values() if info.get("created"))
        verb = "Created" if created == len(files) else "Edited"
        return f"{verb} {plural(len(files), 'file')}: {short_list(names)}"
    if kind == "command":
        commands = meta.get("commands", [])
        first = commands[0] if commands else "a command"
        return first if len(commands) <= 1 else f"{first} (+{len(commands) - 1} more)"
    if kind == "test":
        label = meta.get("label") or "Ran tests"
        counts = meta.get("tests")
        if meta.get("running"):
            return f"{label}…"
        if not counts:
            return label
        parts = [f"{counts['failed']} failed"] if counts["failed"] else []
        parts.append(f"{counts['passed']} passed")
        return f"{label} → {', '.join(parts)}"
    if kind == "research":
        lookups = meta.get("lookups", [])
        if len(lookups) == 1:
            return "Researched: " + lookups[0]
        return f"Researched the web ({plural(len(lookups), 'lookup')})"
    if kind == "browser":
        return f"Checked the app in a browser ({plural(meta.get('actions', 0), 'action')})"
    if kind == "message_out":
        return f"Message to {meta.get('to')}: {clip_line(meta.get('summary') or meta.get('body') or '', 80)}"
    if kind == "message_in":
        word = "Assignment" if meta.get("assignment") else "Message"
        return f"{word} from {meta.get('from')}: {clip_line(meta.get('summary') or meta.get('body') or '', 80)}"
    if kind == "spawn":
        return f"Started teammate {meta.get('name')}"
    if kind == "plan":
        return meta.get("label") or "Updated plan"
    if kind == "note":
        return note_title(meta.get("text", ""))
    return f"Used {pretty_tool(meta.get('tool', 'a tool'))}"
