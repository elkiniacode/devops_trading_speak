"""Build runs from transcripts without starting the server, and optionally write contract examples.

    uv run python -m monitor.importer                 # every team under ~/.claude/teams
    uv run python -m monitor.importer --examples examples --run session-14057a58
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

from .config import load_settings
from .watcher import Monitor, RunHandle


def main() -> None:
    parser = argparse.ArgumentParser(prog="monitor.importer")
    parser.add_argument("--claude-dir", type=Path)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--examples", type=Path, help="write example JSON for CONTRACT.md into this folder")
    parser.add_argument("--run", help="run to take the examples from (default: the newest)")
    args = parser.parse_args()
    monitor = Monitor(load_settings(claude_dir=args.claude_dir, runs_dir=args.runs_dir))
    monitor.discover()
    for handle in monitor.runs.values():
        snap = handle.snapshot
        types = collections.Counter(e["type"] for e in handle.events)
        print(f"{handle.id}: {len(snap.agents)} agents, {len(snap.tasks)} tasks, {len(snap.steps)} steps, "
              f"{len(snap.messages)} messages, {len(handle.events)} events, status {snap.run['status']}")
        print("   ", dict(types))
    if args.examples:
        summaries = monitor.summaries()
        run_id = args.run or summaries[0]["id"]
        write_examples(monitor.runs[run_id], summaries, args.examples)
        print(f"Examples written to {args.examples}")


def write_examples(handle: RunHandle, summaries: list[dict], folder: Path) -> None:
    """Real payloads for every endpoint and event type, taken from one run."""
    snap = handle.snapshot
    folder.mkdir(parents=True, exist_ok=True)

    def save(name: str, value) -> None:
        (folder / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    save("GET_runs.json", {"runs": summaries})
    view = snap.view()
    save("GET_run.json", view)
    agents = [a for a in view["agents"] if not a["is_lead"]]
    agent = max(agents, key=lambda a: a["counts"]["messages_sent"])["name"] if agents else view["agents"][0]["name"]
    tasks = [t for t in view["tasks"] if t["agent"] == agent]
    task = max(tasks, key=lambda t: len(snap.steps_for(agent, t["id"])))
    save("GET_steps.json", {"steps": snap.steps_for(agent, task["id"])})
    for kind in ("edit", "test", "message_out", "message_in", "read", "command", "note", "plan"):
        step = next((s for s in snap.steps.values() if s["kind"] == kind and (kind != "test" or s.get("tests"))), None)
        if step:
            save(f"GET_step_{kind}.json", snap.step_detail(step["id"]))
    threads = snap.threads()
    save("GET_threads.json", {"threads": threads})
    peer = next((t for t in threads if snap.run["lead"] not in t["agents"] and "user" not in t["agents"]), threads[0])
    save("GET_thread.json", snap.thread(peer["id"]))
    seen, sample = set(), []
    for event in handle.events:
        if event["type"] not in seen:
            seen.add(event["type"])
            sample.append(event)
    sample += [
        {"type": "clock", "ts": "2026-10-19T20:05:01.000Z", "data": {"now": "2026-10-19T20:05:01.000Z"}},
        {"type": "replay.finished", "ts": snap.last_event_at, "data": {}},
    ]
    (folder / "events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in sample), encoding="utf-8")


if __name__ == "__main__":
    main()
