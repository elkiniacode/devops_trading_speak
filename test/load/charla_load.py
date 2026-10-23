"""Load test for the live-talk room (planning/charla/CONTRACT.md §10).

Simulates N phones answering one quiz question while the presenter drives the room:

1. turn email verification off (admin API), so register returns a session at once;
2. register N attendees at @example.invalid addresses;
3. open N attendee SSE streams (httpx streaming);
4. the presenter launches Q1 (step 0);
5. each attendee answers after a random 0.5-8 s delay;
6. close, reveal, and check that every stream saw the reveal (and its own correct result);
7. print p50/p95 for launch->event latency and answer POST time.
   PASS when p95 launch->event < 1.5 s and p95 answer POST < 500 ms, and nothing failed;
8. reset the room at the end, unless --no-reset (then verification is put back as it was).

Run from the repo root:

    uv run --project backend python test/load/charla_load.py --base http://localhost:8003 --key e2e --n 40

It refuses to run against a room that already has attendees unless --force: the final reset wipes them.
Exit code 0 on PASS, 1 on FAIL.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import random
import statistics
import string
import sys
import time
from dataclasses import dataclass, field

import httpx

LAUNCH_P95_LIMIT_S = 1.5
ANSWER_P95_LIMIT_S = 0.5
SSE_WAIT_S = 15.0


@dataclass
class Attendee:
    index: int
    username: str
    email: str
    token: str = ""
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    opened: asyncio.Event = field(default_factory=asyncio.Event)
    revealed: asyncio.Event = field(default_factory=asyncio.Event)
    opened_at: float | None = None  # perf_counter when the stream first showed Q1 open
    choice: int | None = None
    answer_s: float | None = None
    answer_error: str | None = None
    stream_error: str | None = None
    reveal_view: dict | None = None
    events: int = 0


def pct(values: list[float], p: float) -> float:
    """Nearest-rank percentile (p in 0..100)."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = max(1, math.ceil(p / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def ms(seconds: float) -> str:
    return "n/a" if seconds != seconds else f"{seconds * 1000:7.0f} ms"


class Room:
    """Admin calls."""

    def __init__(self, client: httpx.AsyncClient, key: str) -> None:
        self.client = client
        self.headers = {"X-Admin-Key": key}
        self.key = key

    async def post(self, action: str, body: dict | None = None, *, ok: tuple[int, ...] = (200,)) -> httpx.Response:
        res = await self.client.post(f"/api/charla/admin/{action}", json=body or {}, headers=self.headers)
        if res.status_code not in ok:
            raise RuntimeError(f"admin {action}: HTTP {res.status_code} {res.text}")
        return res

    async def snapshot(self) -> dict:
        """The first event of the admin stream (CONTRACT §6.2)."""
        async with self.client.stream("GET", "/api/charla/admin/stream", params={"key": self.key}) as res:
            if res.status_code != 200:
                raise RuntimeError(f"admin stream: HTTP {res.status_code} {(await res.aread()).decode()}")
            async for line in res.aiter_lines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        raise RuntimeError("admin stream closed before its first event")


async def register(client: httpx.AsyncClient, att: Attendee, timings: list[float]) -> None:
    started = time.perf_counter()
    res = await client.post("/api/charla/register", json={"username": att.username, "email": att.email})
    timings.append(time.perf_counter() - started)
    if res.status_code != 200:
        raise RuntimeError(f"register {att.username}: HTTP {res.status_code} {res.text}")
    body = res.json()
    if body.get("status") != "in" or not body.get("token"):
        raise RuntimeError(f"register {att.username}: expected status 'in' with verification off, got {body}")
    att.token = body["token"]


async def stream(client: httpx.AsyncClient, att: Attendee) -> None:
    """Follow one attendee's SSE stream until cancelled, recording when Q1 opens and when it is revealed."""
    try:
        async with client.stream("GET", "/api/charla/stream", params={"t": att.token}) as res:
            if res.status_code != 200:
                att.stream_error = f"HTTP {res.status_code}"
                return
            data: list[str] = []
            async for line in res.aiter_lines():
                if line.startswith("data:"):
                    data.append(line[5:].lstrip())
                    continue
                if line or not data:
                    continue
                view = json.loads("\n".join(data))
                data = []
                att.events += 1
                att.connected.set()
                state = view.get("state") or {}
                if state.get("step") == 0 and state.get("phase") == "open" and not att.opened.is_set():
                    att.opened_at = time.perf_counter()
                    att.opened.set()
                if state.get("step") == 0 and state.get("phase") == "revealed" and not att.revealed.is_set():
                    att.reveal_view = view
                    att.revealed.set()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - report every stream failure, keep the others running
        att.stream_error = f"{type(exc).__name__}: {exc}"


async def answer(client: httpx.AsyncClient, att: Attendee, rng: random.Random) -> None:
    try:
        await asyncio.wait_for(att.opened.wait(), SSE_WAIT_S)
    except TimeoutError:
        att.answer_error = "never saw Q1 open"
        return
    await asyncio.sleep(rng.uniform(0.5, 8.0))
    att.choice = rng.randrange(4)
    started = time.perf_counter()
    try:
        res = await client.post(
            "/api/charla/answer",
            json={"step": 0, "choice": att.choice},
            headers={"Authorization": f"Bearer {att.token}"},
        )
    except httpx.HTTPError as exc:
        att.answer_error = f"{type(exc).__name__}: {exc}"
        return
    att.answer_s = time.perf_counter() - started
    if res.status_code != 200 or res.json() != {"accepted": True}:
        att.answer_error = f"HTTP {res.status_code} {res.text}"


async def wait_all(events: list[asyncio.Event], timeout: float) -> int:
    """Wait until every event is set or the timeout passes; return how many are set."""
    try:
        await asyncio.wait_for(asyncio.gather(*(e.wait() for e in events)), timeout)
    except TimeoutError:
        pass
    return sum(e.is_set() for e in events)


async def run(args: argparse.Namespace) -> bool:
    rng = random.Random(args.seed)
    run_id = "".join(rng.choices(string.ascii_lowercase + string.digits, k=4))
    limits = httpx.Limits(max_connections=args.n * 3 + 20, max_keepalive_connections=args.n * 2 + 10)
    timeout = httpx.Timeout(30.0, read=None)  # SSE reads block between events
    problems: list[str] = []

    async with httpx.AsyncClient(base_url=args.base, limits=limits, timeout=timeout) as client:
        room = Room(client, args.key)

        health = await client.get("/api/health")
        print(f"[load] {args.base}  health={health.status_code}  n={args.n}  run={run_id}")
        before = await room.snapshot()
        registered = before["counts"]["registered"]
        verification_was_on = bool(before["state"].get("verification_on", True))
        print(
            f"[load] room before: step={before['state']['step']} phase={before['state']['phase']} "
            f"registered={registered} verification_on={verification_was_on}"
        )
        if registered and not args.no_reset and not args.force:
            print(
                f"[load] ABORT: the room already has {registered} attendees and the final reset would delete them. "
                "Use --no-reset to keep them, or --force to wipe them anyway."
            )
            return False

        attendees = [
            Attendee(i, f"Carga {i:02d} {run_id}", f"carga{i:02d}.{run_id}@example.invalid") for i in range(args.n)
        ]
        tasks: list[asyncio.Task] = []
        try:
            # 1. Verification off, room on Q1 idle with no answers (goto keeps other steps' answers).
            await room.post("verification", {"on": False})
            await room.post("close", ok=(200, 409))  # in case a question is still open
            await room.post("goto", {"step": 0})
            await room.post("reset-step", ok=(200, 409))

            # 2. Register N attendees (in parallel, like a room scanning the QR).
            reg_times: list[float] = []
            await asyncio.gather(*(register(client, a, reg_times) for a in attendees))
            print(f"[load] registered {len(attendees)}: register p50 {ms(pct(reg_times, 50))}  p95 {ms(pct(reg_times, 95))}")

            # 3. N SSE streams.
            tasks = [asyncio.create_task(stream(client, a)) for a in attendees]
            connected = await wait_all([a.connected for a in attendees], SSE_WAIT_S)
            print(f"[load] streams connected: {connected}/{args.n}")
            if connected < args.n:
                problems.append(f"only {connected}/{args.n} streams delivered a first event")

            # 4. Launch Q1; 5. everyone answers after 0.5-8 s.
            answer_tasks = [asyncio.create_task(answer(client, a, random.Random(rng.random()))) for a in attendees]
            launched_at = time.perf_counter()
            await room.post("launch")
            opened = await wait_all([a.opened for a in attendees], SSE_WAIT_S)
            launch_lat = [a.opened_at - launched_at for a in attendees if a.opened_at is not None]
            print(f"[load] streams saw Q1 open: {opened}/{args.n}")
            if opened < args.n:
                problems.append(f"only {opened}/{args.n} streams saw Q1 open")
            await asyncio.gather(*answer_tasks)
            answer_times = [a.answer_s for a in attendees if a.answer_s is not None]
            failed = [a for a in attendees if a.answer_error]
            print(f"[load] answers accepted: {args.n - len(failed)}/{args.n}")
            for a in failed[:5]:
                problems.append(f"answer from {a.username}: {a.answer_error}")
            if len(failed) > 5:
                problems.append(f"... and {len(failed) - 5} more answer failures")

            # 6. Close, reveal; every stream must see the reveal with its own result.
            await room.post("close")
            await room.post("reveal")
            revealed = await wait_all([a.revealed for a in attendees], SSE_WAIT_S)
            print(f"[load] streams saw the reveal: {revealed}/{args.n}")
            if revealed < args.n:
                problems.append(f"only {revealed}/{args.n} streams saw the reveal")

            problems.extend(check_reveal(attendees))
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            stream_errors = [a for a in attendees if a.stream_error]
            for a in stream_errors[:5]:
                problems.append(f"stream of {a.username}: {a.stream_error}")

            # 8. Clean up.
            try:
                if args.no_reset:
                    await room.post("verification", {"on": verification_was_on})
                    print(f"[load] --no-reset: kept the room; verification back to {verification_was_on}")
                else:
                    await room.post("reset", {"confirm": "RESET"})
                    print("[load] room reset")
            except Exception as exc:  # noqa: BLE001
                problems.append(f"cleanup failed: {exc}")

    # 7. Report.
    lp50, lp95 = pct(launch_lat, 50), pct(launch_lat, 95)
    ap50, ap95 = pct(answer_times, 50), pct(answer_times, 95)
    print()
    print(f"  launch -> stream event   p50 {ms(lp50)}   p95 {ms(lp95)}   max {ms(max(launch_lat, default=float('nan')))}   (limit p95 < {LAUNCH_P95_LIMIT_S * 1000:.0f} ms)")
    print(f"  answer POST              p50 {ms(ap50)}   p95 {ms(ap95)}   max {ms(max(answer_times, default=float('nan')))}   (limit p95 < {ANSWER_P95_LIMIT_S * 1000:.0f} ms)")
    if launch_lat:
        print(f"  launch -> event mean {statistics.mean(launch_lat) * 1000:.0f} ms over {len(launch_lat)} streams")
    if not (lp95 < LAUNCH_P95_LIMIT_S):
        problems.append(f"launch->event p95 {lp95 * 1000:.0f} ms is not under {LAUNCH_P95_LIMIT_S * 1000:.0f} ms")
    if not (ap95 < ANSWER_P95_LIMIT_S):
        problems.append(f"answer POST p95 {ap95 * 1000:.0f} ms is not under {ANSWER_P95_LIMIT_S * 1000:.0f} ms")

    print()
    if problems:
        print("FAIL")
        for p in problems:
            print(f"  - {p}")
        return False
    print("PASS")
    return True


def check_reveal(attendees: list[Attendee]) -> list[str]:
    """Each revealed view: the distribution matches our answers and `me.result` matches our own choice."""
    problems: list[str] = []
    views = [a for a in attendees if a.reveal_view]
    if not views:
        return problems
    reveal = views[0].reveal_view["state"].get("reveal") or {}
    correct = reveal.get("answer")
    expected = [0, 0, 0, 0]
    for a in attendees:
        if a.choice is not None and not a.answer_error:
            expected[a.choice] += 1
    if reveal.get("distribution") != expected:
        problems.append(f"reveal distribution {reveal.get('distribution')} != answers sent {expected}")
    wrong = 0
    for a in views:
        result = (a.reveal_view.get("me") or {}).get("result")
        if a.choice is None or a.answer_error:
            continue
        if not result or result.get("correct") != (a.choice == correct):
            wrong += 1
            if wrong <= 3:
                problems.append(f"{a.username} chose {a.choice}, correct {correct}, but me.result = {result}")
        elif result["correct"] and not 500 <= result["points"] <= 1000:
            problems.append(f"{a.username}: correct answer scored {result['points']} points (want 500-1000)")
    if wrong > 3:
        problems.append(f"... {wrong} attendees in total had a wrong me.result")
    print(f"[load] reveal: correct option {correct}, distribution {reveal.get('distribution')}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Charla room load test (CONTRACT §10).")
    parser.add_argument("--base", default="http://localhost:8003", help="app origin, e.g. https://<app>.up.railway.app")
    parser.add_argument("--key", default=os.getenv("CHARLA_ADMIN_KEY", "e2e"), help="presenter key (CHARLA_ADMIN_KEY)")
    parser.add_argument("--n", type=int, default=40, help="number of simulated attendees")
    parser.add_argument("--seed", type=int, default=None, help="random seed (answer delays and choices)")
    parser.add_argument("--no-reset", action="store_true", help="keep the attendees and answers at the end")
    parser.add_argument("--force", action="store_true", help="run even if the room already has attendees")
    args = parser.parse_args()
    args.base = args.base.rstrip("/")
    ok = asyncio.run(run(args))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
