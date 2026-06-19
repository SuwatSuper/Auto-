# Regression — the runtime MUST record closed paper trades to data/trades_*.csv.
"""Release-gate bug [R1]: TradeCsvLogger existed and was unit-tested but was never
wired into the runtime, so a live/paper run produced NO trades_*.csv. That breaks
the owner's "screen reconciles with trades_*.csv" check, the data-recording
provenance requirement, and starves the ML win-probability loop (which trains on
data/trades_*.csv). This test fails before the wiring fix and passes after.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import UTC, datetime

import orjson
import structlog

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from orchestration.runtime_base import _TOPIC_PAPER_EVENTS
from tests._fixtures import FakePriceFeed


async def test_runtime_records_closed_trades_to_csv(tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings = Settings(
        persist_state=True, news_enabled=False, initial_capital="1000",
        state_db_path=str(tmp_path / "state.db"), prices_topic="prices.thb_btc.v1",
    )
    deps = RuntimeDeps(
        bus=InMemoryEventBus(), clock=SystemClock(), state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(), feed_factory=lambda _m: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    rt = PipelineRuntime(settings, structlog.get_logger("t"), deps=deps)
    await rt.start("live")  # deps feed_factory supplies a fake feed (no network)
    try:
        await asyncio.sleep(0.2)  # let the recorder subscribe (avoid publish-before-subscribe)
        now_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        await rt.bus.publish(_TOPIC_PAPER_EVENTS, b"k", orjson.dumps({
            "type": "FILL", "qty": "0.001", "entry": "1000000", "symbol": "THB_BTC",
            "strategy_id": "trend_follower", "regime": "TREND_UP", "win_prob_est": "0.62",
        }))
        await rt.bus.publish(_TOPIC_PAPER_EVENTS, b"k", orjson.dumps({
            "type": "CLOSE", "exit": "1010000", "reason": "TAKE_PROFIT", "pnl": "5",
            "pnl_gross": "7.5", "pnl_net": "5", "fee_paid": "2.5", "cash": "1005",
            "slippage_bps": "5", "ts_ms": now_ms,
        }))
        files: list = []
        for _ in range(60):
            files = list(tmp_path.glob("trades_*.csv"))
            if files:
                break
            await asyncio.sleep(0.05)
    finally:
        await rt.stop()

    assert files, "runtime did not write data/trades_*.csv (CSV recorder not wired)"
    rows = list(csv.DictReader(files[0].open(encoding="utf-8")))
    assert rows, "trades CSV is empty"
    assert rows[0]["pnl_net"] == "5"
    assert rows[0]["strategy_id"] == "trend_follower"
    assert rows[0]["regime"] == "TREND_UP"
    assert rows[0]["win_prob_est"] == "0.62"
