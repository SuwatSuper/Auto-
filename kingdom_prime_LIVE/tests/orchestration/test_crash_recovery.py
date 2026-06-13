"""Integration tests: crash recovery, state persistence, and emergency flatten.

TASK 6: Verify that:
1. State (position + cash) saved to SQLite survives a simulated restart.
2. status() reports state_restored=True after a successful load.
3. emergency_stop() flattens all open paper positions and status() shows 0 positions.
"""
from __future__ import annotations

import asyncio
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
import structlog

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.sqlite_store import SqliteStateStore
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed


def _make_runtime_with_sqlite(db_path: str, **overrides: object) -> PipelineRuntime:
    """Build a runtime backed by a real SQLite store at db_path."""
    bus = InMemoryEventBus()
    store = SqliteStateStore(Path(db_path))
    settings = Settings(  # type: ignore[call-arg]
        persist_state=True,
        state_db_path=db_path,
        initial_capital="1000",
        **overrides,  # type: ignore[arg-type]
    )
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=store,
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)


@pytest.mark.asyncio
async def test_state_restored_after_restart() -> None:
    """Write position state to SQLite; new runtime instance loads it."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "state.db")

        # ── 1. First runtime: start then stop clean ─────────────────────────────
        rt1 = _make_runtime_with_sqlite(db_path)
        await rt1.start("live")
        await rt1.stop()

        # Write state AFTER rt1 is fully stopped so nothing can overwrite it.
        import orjson as _orjson

        # Use prices matching FakePriceFeed range (~1,500,000) so the restored
        # position is not immediately stopped out when test prices arrive.
        pos_data = {
            "position": {
                "symbol": "THB_BTC",
                "qty": "0.00010000",
                "entry_price": "1500000.00",
                "stop_price": "1485000.00",
                "take_profit_price": "1600000.00",
                "entry_fee": "37.50",
                "opened_ms": 1_700_000_000_000,
            },
            "trades_closed": 3,
            "entries_opened": 4,
        }
        store_writer = SqliteStateStore(Path(db_path))
        await store_writer.set("paper.position.v1", _orjson.dumps(pos_data))

        # ── 2. Second runtime: loads from the same SQLite ───────────────────
        rt2 = _make_runtime_with_sqlite(db_path)
        await rt2.start("live")
        await asyncio.sleep(0.1)  # give paper_trader.start() time to call _load()

        status = rt2.status()
        await rt2.stop()

    assert status["state_restored"] is True, (
        "state_restored should be True when position was loaded from SQLite"
    )
    assert status["positions"] == 1, (
        "Paper trader should have 1 open position restored from SQLite"
    )


@pytest.mark.asyncio
async def test_fresh_runtime_state_restored_false() -> None:
    """A brand-new runtime with no saved state reports state_restored=False."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "empty_state.db")
        rt = _make_runtime_with_sqlite(db_path)
        await rt.start("live")
        await asyncio.sleep(0.05)
        status = rt.status()
        await rt.stop()

    assert status["state_restored"] is False


@pytest.mark.asyncio
async def test_emergency_stop_flattens_positions_and_halts() -> None:
    """After emergency_stop(), portfolio shows 0 positions and kill_switch=True."""
    from tests.conftest import make_test_runtime

    rt = make_test_runtime()
    await rt.start("live")
    await asyncio.sleep(0.05)

    # Inject a fake position directly into the paper trader (no real order needed)
    from domain.trading.paper import PaperPosition

    if rt._trader is not None:
        rt._trader.position = PaperPosition(
            symbol="THB_BTC",
            qty=Decimal("0.00010000"),
            entry_price=Decimal("3500000"),
            stop_price=Decimal("3465000"),
            take_profit_price=Decimal("3552500"),
            entry_fee=Decimal("87.50"),
            opened_ms=1_700_000_000_000,
        )
        rt._trader.mark_price = Decimal("3510000")

    assert rt.status()["positions"] == 1

    await rt.emergency_stop()

    status = rt.status()
    assert status["kill_switch"] is True
    assert status["positions"] == 0, (
        "emergency_stop() must flatten all open paper positions"
    )
