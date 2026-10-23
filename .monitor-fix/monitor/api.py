"""REST + SSE API (CONTRACT.md) and the static pages."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager, suppress
from datetime import timedelta

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .sources import iso, now_iso, parse_iso
from .watcher import Monitor, RunHandle

KEEPALIVE_SECONDS = 15


def create_app(settings: Settings | None = None, monitor: Monitor | None = None, watch: bool = True) -> FastAPI:
    settings = settings or load_settings()
    monitor = monitor or Monitor(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(monitor.run_forever()) if watch else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Agent Monitor", lifespan=lifespan)
    app.state.monitor = monitor

    def handle_for(run_id: str) -> RunHandle:
        handle = monitor.runs.get(run_id)
        if handle is None or handle.snapshot.run is None:
            raise HTTPException(404, f"Unknown run: {run_id}")
        return handle

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "runs": len(monitor.runs)}

    @app.get("/api/runs")
    def list_runs() -> dict:
        return {"runs": monitor.summaries()}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        return handle_for(run_id).snapshot.view()

    @app.get("/api/runs/{run_id}/agents/{agent}/steps")
    def get_steps(run_id: str, agent: str, task: str | None = None) -> dict:
        snapshot = handle_for(run_id).snapshot
        if agent not in snapshot.agents:
            raise HTTPException(404, f"Unknown agent: {agent}")
        return {"steps": snapshot.steps_for(agent, task)}

    @app.get("/api/runs/{run_id}/steps/{step_id}")
    def get_step(run_id: str, step_id: str) -> dict:
        detail = handle_for(run_id).snapshot.step_detail(step_id)
        if detail is None:
            raise HTTPException(404, f"Unknown step: {step_id}")
        return detail

    @app.get("/api/runs/{run_id}/messages")
    def get_messages(run_id: str, agent: str | None = None) -> dict:
        return {"messages": handle_for(run_id).snapshot.messages_for(agent)}

    @app.get("/api/runs/{run_id}/threads")
    def get_threads(run_id: str) -> dict:
        return {"threads": handle_for(run_id).snapshot.threads()}

    @app.get("/api/runs/{run_id}/threads/{thread_id}")
    def get_thread(run_id: str, thread_id: str) -> dict:
        thread = handle_for(run_id).snapshot.thread(thread_id)
        if thread is None:
            raise HTTPException(404, f"Unknown thread: {thread_id}")
        return thread

    @app.get("/api/runs/{run_id}/log")
    def get_log(run_id: str, start: int = Query(1, alias="from", ge=1), limit: int = Query(5000, ge=1, le=50000)) -> dict:
        """Stored events as plain JSON, for pages that replay or scrub on their own."""
        events = handle_for(run_id).events_since(start)
        return {"events": events[:limit], "more": len(events) > limit}

    @app.put("/api/runs/{run_id}/layout")
    def put_layout(run_id: str, layout: dict = Body(...)) -> dict:
        if not isinstance(layout.get("layers"), list):
            raise HTTPException(400, "A layout needs a 'layers' list")
        handle = handle_for(run_id)
        handle.set_user_layout(layout)
        return {"layout": handle.snapshot.layout}

    @app.delete("/api/runs/{run_id}/layout")
    def reset_layout(run_id: str) -> dict:
        handle = handle_for(run_id)
        handle.set_user_layout(None)
        return {"layout": handle.snapshot.layout}

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        request: Request,
        start: int = Query(1, alias="from", ge=1),
        speed: float | None = Query(None, ge=0),
        max_gap: float = Query(2.0, ge=0),
        keepalive: bool = True,
    ) -> StreamingResponse:
        handle = handle_for(run_id)
        last_id = request.headers.get("last-event-id", "")
        if last_id.isdigit():
            start = int(last_id) + 1
        if speed is None:
            body = _live(handle, request, start)
        else:
            body = _replay(handle, request, start, speed, max_gap, keepalive)
        return StreamingResponse(body, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/debug")
    def debug_page() -> FileResponse:
        return FileResponse(settings.web_dir / "debug.html")

    if settings.web_dir.exists():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


def _sse(event: dict) -> str:
    return f"id: {event['seq']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


def _signal(etype: str, ts: str, data: dict | None = None) -> str:
    """Stream-only events (clock, replay.finished): no id, so they never move Last-Event-ID."""
    return f"data: {json.dumps({'type': etype, 'ts': ts, 'data': data or {}})}\n\n"


async def _live(handle: RunHandle, request: Request, start: int):
    queue = handle.subscribe()
    try:
        yield "retry: 3000\n\n"
        last = start - 1
        for event in handle.events_since(start):
            yield _sse(event)
            last = event["seq"]
        while not await request.is_disconnected():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=1.0)
            except TimeoutError:
                now = now_iso()
                yield _signal("clock", now, {"now": now})
                continue
            if event["seq"] > last:
                yield _sse(event)
                last = event["seq"]
    finally:
        handle.unsubscribe(queue)


async def _replay(handle: RunHandle, request: Request, start: int, speed: float, max_gap: float, keepalive: bool):
    """Re-sends stored events with their original spacing divided by `speed` (0 = no waiting).
    Gaps are capped at `max_gap` real seconds; a clock event ticks every second during waits."""
    yield "retry: 3000\n\n"
    loop = asyncio.get_running_loop()
    previous, last_clock = None, loop.time()
    for event in handle.events_since(start):
        if previous is not None and speed > 0:
            base = parse_iso(previous)
            gap = (parse_iso(event["ts"]) - base).total_seconds() / speed
            wait, waited = min(max(gap, 0.0), max_gap), 0.0
            while waited < wait:
                step = min(1.0, wait - waited)
                await asyncio.sleep(step)
                waited += step
                if await request.is_disconnected():
                    return
                if loop.time() - last_clock >= 1.0:
                    last_clock = loop.time()
                    now = min(iso(base + timedelta(seconds=waited * speed)), event["ts"])
                    yield _signal("clock", now, {"now": now})
        yield _sse(event)
        previous = max(previous or event["ts"], event["ts"])
    yield _signal("replay.finished", previous or now_iso())
    while keepalive and not await request.is_disconnected():
        await asyncio.sleep(KEEPALIVE_SECONDS)
        yield ": keepalive\n\n"
