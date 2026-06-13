# tests/orchestration/test_reconciliation_agent.py
"""Tests for ReconciliationAgent — no network, deterministic."""
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import orjson
import pytest
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.reconciliation_agent import ReconciliationAgent
from orchestration.ports.balance_source import NullBalanceSource


class _FailingSource:
    """Simulates a balance source that always raises."""

    async def get_balance(self) -> dict[str, Decimal]:
        raise RuntimeError("network error")


class _FixedSource:
    """Returns a pre-set balance."""

    def __init__(self, balances: dict[str, Decimal]) -> None:
        self._balances = balances

    async def get_balance(self) -> dict[str, Decimal]:
        return self._balances


async def _run_one_poll(agent: ReconciliationAgent, settle: float = 0.3) -> None:
    """Start agent, wait for one poll, stop it."""
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(settle)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_null_source_reconciles_immediately() -> None:
    """NullBalanceSource immediately sets is_reconciled=True."""
    bus = InMemoryEventBus()
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=NullBalanceSource(),
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    assert not agent.is_reconciled
    await _run_one_poll(agent)
    assert agent.is_reconciled


@pytest.mark.asyncio
async def test_reconciliation_publishes_event() -> None:
    """Successful poll publishes a RECONCILIATION event on the topic."""
    bus = InMemoryEventBus()
    q = bus.subscribe("reconciliation.v1")
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=NullBalanceSource(),
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    await _run_one_poll(agent)

    assert not q.empty()
    msg = orjson.loads(q.get_nowait())
    assert msg["type"] == "RECONCILIATION"
    assert msg["reconciled"] is True
    assert "ts_ms" in msg
    assert "balances" in msg


@pytest.mark.asyncio
async def test_fixed_source_includes_balances() -> None:
    """FixedSource balances appear in the published event."""
    bus = InMemoryEventBus()
    q = bus.subscribe("reconciliation.v1")
    source = _FixedSource({"THB": Decimal("5000"), "BTC": Decimal("0.001")})
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=source,
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    await _run_one_poll(agent)

    msg = orjson.loads(q.get_nowait())
    assert msg["balances"]["THB"] == "5000"
    assert msg["balances"]["BTC"] == "0.001"


@pytest.mark.asyncio
async def test_failing_source_does_not_reconcile() -> None:
    """When balance source raises, is_reconciled stays False."""
    bus = InMemoryEventBus()
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=_FailingSource(),
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    await _run_one_poll(agent)
    assert not agent.is_reconciled


@pytest.mark.asyncio
async def test_failing_source_publishes_failed_event() -> None:
    """Failed poll publishes a RECONCILIATION event with reconciled=False."""
    bus = InMemoryEventBus()
    q = bus.subscribe("reconciliation.v1")
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=_FailingSource(),
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    await _run_one_poll(agent)

    assert not q.empty()
    msg = orjson.loads(q.get_nowait())
    assert msg["type"] == "RECONCILIATION"
    assert msg["reconciled"] is False


@pytest.mark.asyncio
async def test_agent_agentlike_fields() -> None:
    """ReconciliationAgent exposes running/msg_count/last_beat_ms (AgentLike)."""
    bus = InMemoryEventBus()
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=NullBalanceSource(),
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    assert agent.running is False
    assert agent.msg_count == 0
    assert agent.last_beat_ms == 0
    await _run_one_poll(agent)
    assert agent.msg_count >= 1
    assert agent.last_beat_ms > 0


@pytest.mark.asyncio
async def test_custom_topic() -> None:
    """Reconciliation events go to the configured topic."""
    bus = InMemoryEventBus()
    q = bus.subscribe("custom.recon.topic")
    agent = ReconciliationAgent(
        bus=bus,
        balance_source=NullBalanceSource(),
        reconciliation_topic="custom.recon.topic",
        poll_interval_s=999.0,
        logger=structlog.get_logger("test"),
    )
    await _run_one_poll(agent)
    assert not q.empty()
