"""The current state of one run, rebuilt by applying its events in order."""

from __future__ import annotations

from collections import defaultdict

from .sources import now_iso


class Snapshot:
    def __init__(self):
        self.seq = 0
        self.run: dict | None = None
        self.layout: dict | None = None
        self.agents: dict[str, dict] = {}
        self.tasks: dict[str, dict] = {}
        self.steps: dict[str, dict] = {}
        self.agent_steps: dict[str, list[str]] = defaultdict(list)
        self.items: dict[str, list[dict]] = defaultdict(list)
        self.messages: dict[str, dict] = {}
        self.last_event_at: str | None = None
        self._files: dict[str, set] = defaultdict(set)

    def apply(self, event: dict) -> None:
        self.seq = event["seq"]
        self.last_event_at = event["ts"]
        etype, data = event["type"], event["data"]
        if etype in ("run.started", "run.updated"):
            self.run = data["run"]
        elif etype == "layout.updated":
            self.layout = data["layout"]
        elif etype == "agent.joined":
            agent = dict(data["agent"])
            agent.update(
                status="idle",
                active_ms=0,
                working_since=None,
                activity=None,
                activity_at=None,
                counts={"steps": 0, "messages_sent": 0, "messages_received": 0, "files_changed": 0},
                last_test=None,
            )
            self.agents[agent["name"]] = agent
        elif etype == "agent.status":
            agent = self.agents.get(data["agent"])
            if agent:
                agent.update(status=data["status"], active_ms=data["active_ms"], working_since=data["working_since"])
        elif etype in ("task.created", "task.updated"):
            self.tasks[data["task"]["id"]] = data["task"]
        elif etype in ("step.added", "step.updated"):
            self._apply_step(data["step"], event["ts"])
        elif etype == "step.interaction":
            self.items[data["step_id"]].extend(data["items"])
        elif etype in ("message.sent", "message.updated"):
            self._apply_message(data["message"])

    def _apply_step(self, step: dict, ts: str) -> None:
        name = step["agent"]
        agent = self.agents.get(name)
        if step["id"] not in self.steps:
            self.agent_steps[name].append(step["id"])
            if agent:
                agent["counts"]["steps"] += 1
        self.steps[step["id"]] = step
        if not agent:
            return
        if self.agent_steps[name][-1] == step["id"]:
            agent.update(activity=step["title"], activity_at=ts)
        if step["kind"] == "edit":
            self._files[name].update(step["files"])
            agent["counts"]["files_changed"] = len(self._files[name])
        if step["kind"] == "test" and step.get("tests"):
            agent["last_test"] = {**step["tests"], "at": step["ended_at"] or ts, "step_id": step["id"]}

    def _apply_message(self, msg: dict) -> None:
        if msg["id"] not in self.messages:
            if msg["from"] in self.agents:
                self.agents[msg["from"]]["counts"]["messages_sent"] += 1
            if msg["to"] in self.agents:
                self.agents[msg["to"]]["counts"]["messages_received"] += 1
        self.messages[msg["id"]] = msg

    # ----- views ----------------------------------------------------------------------------

    def view(self) -> dict:
        return {
            "run": self.run,
            "layout": self.layout,
            "agents": list(self.agents.values()),
            "tasks": list(self.tasks.values()),
            "seq": self.seq,
            "now": now_iso(),
        }

    def summary(self) -> dict:
        return {
            **(self.run or {}),
            "agent_count": len(self.agents),
            "message_count": len(self.messages),
            "task_count": len(self.tasks),
            "step_count": len(self.steps),
            "last_event_at": self.last_event_at,
        }

    def steps_for(self, agent: str, task: str | None = None) -> list[dict]:
        steps = (self.steps[i] for i in self.agent_steps.get(agent, []))
        return [s for s in steps if task is None or s["task_id"] == task]

    def step_detail(self, step_id: str) -> dict | None:
        step = self.steps.get(step_id)
        return {"step": step, "items": self.items.get(step_id, [])} if step else None

    def messages_for(self, agent: str | None = None) -> list[dict]:
        msgs = self.messages.values()
        return [m for m in msgs if agent is None or agent in (m["from"], m["to"])]

    def threads(self) -> list[dict]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        for msg in self.messages.values():
            grouped[msg["thread_id"]].append(msg)
        threads = [self._thread_summary(tid, msgs) for tid, msgs in grouped.items()]
        return sorted(threads, key=lambda t: t["last_at"], reverse=True)

    def thread(self, thread_id: str) -> dict | None:
        msgs = [m for m in self.messages.values() if m["thread_id"] == thread_id]
        if not msgs:
            return None
        return {"thread": self._thread_summary(thread_id, msgs), "messages": sorted(msgs, key=lambda m: m["sent_at"])}

    @staticmethod
    def _thread_summary(thread_id: str, msgs: list[dict]) -> dict:
        ordered = sorted(msgs, key=lambda m: m["sent_at"])
        last = ordered[-1]
        return {
            "id": thread_id,
            "agents": thread_id.split("~"),
            "count": len(ordered),
            "first_at": ordered[0]["sent_at"],
            "last_at": last["sent_at"],
            "last_from": last["from"],
            "last_summary": last["summary"] or (last["body"] or "")[:120],
        }
