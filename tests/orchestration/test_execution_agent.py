# Layer 2 — Orchestration (tests/orchestration/test_execution_agent)
"""Tests for ExecutionAgent gate logic — no network, no real orders."""
from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from orchestration.agents.execution_agent import ExecutionAgent


def _settings(engine: str = "paper", confirm: str = "") -> object:
    s = MagicMock()
    s.execution_engine = engine
    s.live_trading_confirm = confirm
    return s


def _make_agent(
    bus: InMemoryEventBus,
    breaker: CircuitBreaker | None = None,
    engine: str = "paper",
    confirm: str = "",
    rest_gateway: object | None = None,
) -> ExecutionAgent:
    return ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="paper.decisions.v1",
        settings=_settings(engine, confirm),
        breaker=breaker or CircuitBreaker(),
        rate_limiter=TokenBucket(capacity=100, refill_per_sec=1000.0),
        logger=structlog.get_logger("test"),
        rest_gateway=rest_gateway,
    )


async def _run_agent_briefly(
    agent: ExecutionAgent,
    publish_fn: asyncio.coroutines.CoroutineType | None = None,
    settle: float = 0.2,
) -> None:
    """Start agent, optionally publish after it subscribes, then stop."""
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)  # let agent subscribe to its input topic
    try:
        if publish_fn is not None:
            await publish_fn
        await asyncio.sleep(settle)
    finally:
        await agent.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def _decision(signal: str = "BUY", decision_id: str = "dec-001") -> bytes:
    return orjson.dumps({"decision": "EXECUTE", "signal": signal, "decision_id": decision_id})


@pytest.mark.asyncio
async def test_veto_circuit_breaker_publishes_reasons() -> None:
    """When circuit breaker is open, agent publishes a EXECUTION_VETOED event."""
    bus = InMemoryEventBus()
    breaker = CircuitBreaker()
    breaker.trip("TEST", 0)

    veto_q = bus.subscribe("paper.decisions.v1")
    agent = _make_agent(bus, breaker=breaker)

    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", _decision()),
    )

    assert not veto_q.empty()
    msg = orjson.loads(veto_q.get_nowait())
    assert msg["type"] == "EXECUTION_VETOED"
    assert "CIRCUIT_BREAKER_OPEN" in msg["reasons"]


@pytest.mark.asyncio
async def test_duplicate_decision_id_suppressed() -> None:
    """Second message with same decision_id is silently dropped."""
    bus = InMemoryEventBus()
    approved_q = bus.subscribe("paper.decisions.v1")
    agent = _make_agent(bus)

    async def _pub() -> None:
        await bus.publish("decisions.v1", b"k", _decision(decision_id="dup-001"))
        await bus.publish("decisions.v1", b"k", _decision(decision_id="dup-001"))

    await _run_agent_briefly(agent, publish_fn=_pub())

    messages: list[dict[str, object]] = []
    while not approved_q.empty():
        messages.append(orjson.loads(approved_q.get_nowait()))
    # Only one approved message should have been published
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_distinct_decisions_without_id_are_not_falsely_suppressed() -> None:
    """Regression (money stops flowing): SupremeAgent emits decisions with NO
    decision_id. The gate must treat each as unique. Before the fix it fell
    back to id(data); CPython reuses the freed parsed-dict address, so every
    decision after the first collided and was dropped as a 'duplicate' — the
    bot opened one position and then never traded on a signal again.
    """
    bus = InMemoryEventBus()
    approved_q = bus.subscribe("paper.decisions.v1")
    agent = _make_agent(bus)

    n = 50

    async def _pub() -> None:
        for _ in range(n):
            # Exactly the SupremeAgent wire shape: no decision_id / event_id.
            await bus.publish(
                "decisions.v1", b"k",
                orjson.dumps({"decision": "EXECUTE", "signal": "BUY"}),
            )
            await asyncio.sleep(0.004)

    await _run_agent_briefly(agent, publish_fn=_pub(), settle=0.5)

    routed = 0
    while not approved_q.empty():
        approved_q.get_nowait()
        routed += 1
    assert routed == n, f"expected all {n} distinct decisions routed, got {routed}"


@pytest.mark.asyncio
async def test_paper_path_publishes_to_approved_topic() -> None:
    """In paper mode, approved decisions are re-published to the paper topic."""
    bus = InMemoryEventBus()
    approved_q = bus.subscribe("paper.decisions.v1")
    agent = _make_agent(bus, engine="paper")

    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", _decision()),
    )

    assert not approved_q.empty()
    msg = orjson.loads(approved_q.get_nowait())
    assert msg["decision"] == "EXECUTE"


# ── Parametrized live gate tests ─────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engine,confirm,kill_switch",
    [
        ("paper", "I_ACCEPT_REAL_MONEY_RISK", False),   # (a) wrong engine
        ("live", "", False),                             # (b) empty confirm
        ("live", "I_ACCEPT_REAL_MONEY_RISK", True),     # (c) kill switch present
        # (d) circuit breaker handled by veto test above
    ],
)
async def test_live_gate_individually_blocks(
    engine: str,
    confirm: str,
    kill_switch: bool,
    tmp_path: Path,
) -> None:
    """Each live gate individually blocks routing to the REST gateway."""
    mock_gw = MagicMock()
    mock_gw.place_bid = AsyncMock()
    mock_gw.place_ask = AsyncMock()

    bus = InMemoryEventBus()

    if kill_switch:
        # Temporarily create the kill-switch file in cwd
        ks_path = Path("data/KILL_SWITCH")
        ks_path.parent.mkdir(exist_ok=True)
        ks_path.touch()

    try:
        agent = _make_agent(bus, engine=engine, confirm=confirm, rest_gateway=mock_gw)
        dec = _decision(decision_id=f"gate-{engine}-{confirm}")
        await _run_agent_briefly(agent, publish_fn=bus.publish("decisions.v1", b"k", dec))
    finally:
        if kill_switch and ks_path.exists():
            ks_path.unlink()

    mock_gw.place_bid.assert_not_called()
    mock_gw.place_ask.assert_not_called()


@pytest.mark.asyncio
async def test_circuit_breaker_gate_blocks_live() -> None:
    """Gate (d): open circuit breaker vetoes before live routing."""
    mock_gw = MagicMock()
    mock_gw.place_bid = AsyncMock()

    bus = InMemoryEventBus()
    breaker = CircuitBreaker()
    breaker.trip("TEST", 0)  # open the breaker

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="paper.decisions.v1",
        settings=_settings("live", "I_ACCEPT_REAL_MONEY_RISK"),
        breaker=breaker,
        rate_limiter=TokenBucket(capacity=100, refill_per_sec=1000.0),
        logger=structlog.get_logger("test"),
        rest_gateway=mock_gw,
    )

    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", _decision()),
    )

    mock_gw.place_bid.assert_not_called()


@pytest.mark.asyncio
async def test_non_execute_decision_ignored() -> None:
    """Messages where decision != 'EXECUTE' are silently ignored."""
    bus = InMemoryEventBus()
    approved_q = bus.subscribe("paper.decisions.v1")
    agent = _make_agent(bus)

    other = orjson.dumps({"decision": "HOLD", "decision_id": "hold-001"})
    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", other),
    )

    assert approved_q.empty()


# ── Reconciliation gate (gate 0 — STARTUP_NOT_RECONCILED) ────────────

@pytest.mark.asyncio
async def test_reconciliation_gate_blocks_when_not_reconciled() -> None:
    """When reconciliation_gate returns False, decisions are vetoed with STARTUP_NOT_RECONCILED."""
    bus = InMemoryEventBus()
    vetoed_q = bus.subscribe("paper.decisions.v1")

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="paper.decisions.v1",
        settings=_settings("paper"),
        breaker=CircuitBreaker(),
        rate_limiter=TokenBucket(capacity=100, refill_per_sec=1000.0),
        logger=structlog.get_logger("test"),
        reconciliation_gate=lambda: False,  # not yet reconciled
    )

    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", _decision(decision_id="recon-001")),
    )

    assert not vetoed_q.empty()
    msg = orjson.loads(vetoed_q.get_nowait())
    assert msg["type"] == "EXECUTION_VETOED"
    assert "STARTUP_NOT_RECONCILED" in msg["reasons"]


@pytest.mark.asyncio
async def test_reconciliation_gate_passes_when_reconciled() -> None:
    """When reconciliation_gate returns True, decisions flow through normally."""
    bus = InMemoryEventBus()
    approved_q = bus.subscribe("paper.decisions.v1")

    agent = ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="paper.decisions.v1",
        settings=_settings("paper"),
        breaker=CircuitBreaker(),
        rate_limiter=TokenBucket(capacity=100, refill_per_sec=1000.0),
        logger=structlog.get_logger("test"),
        reconciliation_gate=lambda: True,  # already reconciled
    )

    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", _decision(decision_id="recon-pass-001")),
    )

    assert not approved_q.empty()
    msg = orjson.loads(approved_q.get_nowait())
    assert msg["decision"] == "EXECUTE"


@pytest.mark.asyncio
async def test_no_reconciliation_gate_defaults_to_passing() -> None:
    """Without reconciliation_gate (default None), decisions are not blocked."""
    bus = InMemoryEventBus()
    approved_q = bus.subscribe("paper.decisions.v1")
    agent = _make_agent(bus)  # no reconciliation_gate passed

    await _run_agent_briefly(
        agent,
        publish_fn=bus.publish("decisions.v1", b"k", _decision(decision_id="recon-default-001")),
    )

    assert not approved_q.empty()


# ── Integration (skipped by default) ─────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_integration_skipped_by_default() -> None:
    pytest.skip("Integration tests are skipped in default runs")
