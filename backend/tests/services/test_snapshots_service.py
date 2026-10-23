import asyncio
import contextlib

from app import db
from app.services.snapshots import save_price_marks, snapshot_loop
from app.services.trading import execute_trade


async def run_loop_briefly(ctx, seconds: float = 0.2) -> None:
    task = asyncio.create_task(snapshot_loop(ctx, interval=0.02))
    await asyncio.sleep(seconds)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def test_loop_records_value_and_price_marks(ctx):
    await execute_trade(ctx, "AAPL", "buy", 10)
    ctx.cache.update("AAPL", 120.0)
    before = len(db.get_snapshots())
    await run_loop_briefly(ctx)
    snapshots = db.get_snapshots()
    assert len(snapshots) > before
    assert snapshots[-1]["total_value"] == 10200.0
    assert db.load_price_marks()["AAPL"] == 120.0


async def test_loop_survives_a_failing_round(ctx, monkeypatch):
    record = db.record_snapshot
    calls = []

    def flaky(total):
        calls.append(total)
        if len(calls) == 1:
            raise RuntimeError("disk full")
        return record(total)

    monkeypatch.setattr(db, "record_snapshot", flaky)
    await run_loop_briefly(ctx)
    assert len(calls) >= 2
    assert len(db.get_snapshots()) >= 2


async def test_save_price_marks_persists_every_cached_price(ctx):
    save_price_marks(ctx)
    assert db.load_price_marks() == {t: u.price for t, u in ctx.cache.get_all().items()}
