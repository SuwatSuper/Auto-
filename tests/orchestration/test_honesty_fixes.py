# Layer 2 — Orchestration (tests/orchestration/test_honesty_fixes)
"""Regressions for the 'no fake data' hardening:
- RiskAgent vets drawdown against REAL injected equity (not a constant).
- ProbabilityAgent stays silent during RSI warm-up instead of emitting 0.5."""
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.probability import ProbabilityAgent
from orchestration.agents.risk_agent import RiskAgent


def _log() -> structlog.BoundLogger:
    return structlog.get_logger("test")


async def _drain(agent: object, settle: float = 0.15) -> None:
    task = asyncio.create_task(agent.start())  # type: ignore[attr-defined]
    await asyncio.sleep(settle)
    await agent.stop()  # type: ignore[attr-defined]
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


# ── RiskAgent: real drawdown veto ────────────────────────────────────
async def test_risk_agent_vetoes_on_real_drawdown() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("risk.out")
    # Inject a REAL 30% drawdown (peak 1,000,000 → current 700,000); default
    # limit is 20%, so the agent must reject — proving it uses live equity.
    agent = RiskAgent(
        bus, "dec.in", "risk.out", _log(),
        equity_fn=lambda: (Decimal("1000000"), Decimal("700000"), Decimal("0")),
    )
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("dec.in", b"k", orjson.dumps({"qty": "0.01"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    data = orjson.loads(out.get_nowait())
    assert data["approved"] is False
    assert "DRAWDOWN_EXCEEDED" in data["reasons"]
    assert agent.rejected_count == 1


async def test_risk_agent_approves_when_no_drawdown() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("risk.out")
    agent = RiskAgent(
        bus, "dec.in", "risk.out", _log(),
        equity_fn=lambda: (Decimal("1000000"), Decimal("1000000"), Decimal("0")),
    )
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    await bus.publish("dec.in", b"k", orjson.dumps({"qty": "0.01"}))
    await asyncio.sleep(0.1)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    data = orjson.loads(out.get_nowait())
    assert data["approved"] is True


# ── ProbabilityAgent: silent during warm-up ──────────────────────────
async def test_probability_stays_silent_until_rsi_is_real() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("prob.out")
    agent = ProbabilityAgent(bus, "px.in", "prob.out", _log())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    # 3 prices < RSI(14) warm-up → must NOT publish a fabricated 0.5
    for p in (100, 101, 102):
        await bus.publish("px.in", b"k", orjson.dumps({"price": str(p)}))
    await asyncio.sleep(0.1)
    assert out.empty()  # honest silence, no fake probability
    # enough rising prices → RSI computable → publishes a REAL value
    for p in range(103, 125):
        await bus.publish("px.in", b"k", orjson.dumps({"price": str(p)}))
    await asyncio.sleep(0.15)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert not out.empty()
    data = orjson.loads(out.get_nowait())
    assert data["rsi"] != "NaN"
    assert 0.0 <= float(data["prob_bull"]) <= 1.0
