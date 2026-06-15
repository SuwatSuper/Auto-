# Layer 2 — Orchestration (tests/orchestration/test_gate_and_consensus)
"""Win-probability gate is operator-tunable live, and Supreme fires BUY on a
bullish majority instead of being cancelled vote-for-vote by sells."""
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import orjson
import pytest
import structlog

from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.supreme import SupremeAgent
from orchestration.runtime import PipelineRuntime


# ── C2: min_p_win runtime-tunable ────────────────────────────────────
@pytest.mark.asyncio
async def test_min_p_win_is_runtime_tunable() -> None:
    rt = PipelineRuntime(settings=Settings(persist_state=False), logger=structlog.get_logger("t"))
    rt.agents = rt._make_agents()
    ok, payload = await rt.update_risk_settings({"min_p_win": "0.40"})
    assert ok, payload
    assert rt.get_risk_settings()["min_p_win"] == "0.40"
    assert str(rt.settings.min_p_win) == "0.40"
    # applied to the Timeline Analyst's own threshold too
    assert rt._timeline._min_p_win == Decimal("0.40")  # type: ignore[union-attr]
    # out of range (must be 0..1) is rejected
    bad, _ = await rt.update_risk_settings({"min_p_win": "1.5"})
    assert not bad


# ── M2: Supreme BUY on bullish majority ──────────────────────────────
@pytest.mark.asyncio
async def test_supreme_buy_fires_on_majority_not_net() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("out")
    agent = SupremeAgent(
        bus=bus, topic_in="in", topic_out="out", logger=structlog.get_logger("t"),
        window_s=8.0, buy_votes=1, sell_votes=2,
    )
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    # one BUY and one SELL from distinct sources: net == 0 (old logic OBSERVE),
    # but bulls meet the floor and are not outnumbered → EXECUTE BUY now.
    await bus.publish("in", b"k", orjson.dumps({"signal": "BUY", "source": "bull", "ts_ms": 1}))
    await asyncio.sleep(0.03)
    await bus.publish("in", b"k", orjson.dumps({"signal": "SELL", "source": "bear", "ts_ms": 2}))
    await asyncio.sleep(0.08)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    decisions = []
    while not out.empty():
        decisions.append(orjson.loads(out.get_nowait()))
    assert decisions[-1]["decision"] == "EXECUTE"
    assert decisions[-1]["signal"] == "BUY"
