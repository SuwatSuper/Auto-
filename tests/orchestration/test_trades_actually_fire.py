# Layer 2 — Orchestration (tests/orchestration/test_trades_actually_fire)
"""Proves the end-to-end pipeline now OPENS trades (the reported 'agents never
trade' bug was the win-probability gate at 0.80 / 20-samples — effectively
unreachable). With the fee-aware day-trading profile a satisfied gate lets a BUY
flow signals → Supreme → risk gate → paper trader and open a position."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import orjson

from tests.conftest import make_test_runtime


async def _wait_mark(rt: object, timeout: float = 4.0) -> None:
    for _ in range(int(timeout / 0.02)):
        if rt._trader.mark_price is not None:  # type: ignore[attr-defined]
            return
        await asyncio.sleep(0.02)


async def _inject_timeline(rt: object, p_win: str, samples: int, regime: str) -> None:
    # Freeze the Timeline Analyst so its real analysis can't overwrite the
    # injected win-probability mid-test, then set a deterministic verdict.
    await rt.stop_agent("timeline_analyst")  # type: ignore[attr-defined]
    tl = rt._timeline  # type: ignore[attr-defined]
    tl.p_win = Decimal(p_win)
    tl.p_win_samples = samples
    tl.regime = regime
    rt.last_news = {"score": "0.2"}  # mild-positive: no sentiment veto


async def test_pipeline_opens_a_position_when_gate_passes() -> None:
    rt = make_test_runtime()
    await rt.start("live")
    try:
        await _wait_mark(rt)
        await _inject_timeline(rt, "0.70", 40, "TREND_UP")  # passes 0.55 / 8 gate
        bus = rt.bus
        mark = rt._trader.mark_price  # type: ignore[attr-defined]
        for _ in range(150):
            await bus.publish(
                "signals.v1", b"s",
                orjson.dumps({"signal": "BUY", "price": str(mark), "ts_ms": 1, "source": "tester"}),
            )
            if rt._trader.entries_opened > 0:  # type: ignore[attr-defined]
                break
            await asyncio.sleep(0.03)
        assert rt._trader.entries_opened > 0, "pipeline never opened a trade despite a passing gate"
        assert rt._trader.position is not None  # type: ignore[attr-defined]
    finally:
        await rt.stop()


async def test_low_win_probability_still_blocks_entries() -> None:
    rt = make_test_runtime()
    await rt.start("live")
    try:
        await _wait_mark(rt)
        await _inject_timeline(rt, "0.30", 40, "RANGE")  # below 0.55 floor → blocked
        bus = rt.bus
        mark = rt._trader.mark_price  # type: ignore[attr-defined]
        for _ in range(40):
            await bus.publish(
                "signals.v1", b"s",
                orjson.dumps({"signal": "BUY", "price": str(mark), "ts_ms": 1, "source": "tester"}),
            )
            await asyncio.sleep(0.02)
        assert rt._trader.entries_opened == 0  # type: ignore[attr-defined]
        # the gate recorded the real block reason
        assert rt._gate_block_reasons.get("P_WIN_BELOW_MIN", 0) > 0  # type: ignore[attr-defined]
    finally:
        await rt.stop()
