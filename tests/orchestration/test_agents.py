# Layer 2 — Orchestration (tests/orchestration/test_agents)
"""B5 regression tests for SampleAgent clean consume loop."""
from __future__ import annotations

import asyncio
import time

import orjson
import pytest
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.sample_agent import SampleAgent


def _make_agent(bus: InMemoryEventBus, topic: str = "prices.test") -> SampleAgent:
    logger = structlog.get_logger("test")
    return SampleAgent("test_agent", bus, topic, logger)


@pytest.mark.asyncio
async def test_agent_stops_cleanly_within_1s() -> None:
    """B5: agent must stop within 1s, process all messages, no warnings."""
    bus = InMemoryEventBus()
    topic = "prices.test"
    agent = _make_agent(bus, topic)

    task = asyncio.create_task(agent.start())

    # Give agent time to start
    await asyncio.sleep(0.05)

    # Publish 5 messages
    for i in range(5):
        msg = orjson.dumps({"price": str(1_500_000 + i * 100), "ts_ms": 1_700_000_000_000})
        await bus.publish(topic, key=b"BTC", value=msg)

    # Wait for messages to be processed
    await asyncio.sleep(0.2)

    # Stop agent
    start = time.monotonic()
    await agent.stop()
    await asyncio.wait_for(task, timeout=1.0)
    elapsed = time.monotonic() - start

    assert elapsed <= 1.0, f"Agent took {elapsed:.2f}s to stop"
    assert agent.msg_count == 5
    assert task.done()
    assert not task.cancelled()


@pytest.mark.asyncio
async def test_agent_parse_failures_counted() -> None:
    """B5: parse failures must be counted, not swallowed silently."""
    bus = InMemoryEventBus()
    topic = "prices.test"
    agent = _make_agent(bus, topic)

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)

    # Publish invalid JSON
    await bus.publish(topic, key=b"BTC", value=b"NOT VALID JSON!!!")
    await asyncio.sleep(0.1)

    await agent.stop()
    await asyncio.wait_for(task, timeout=1.0)

    assert agent.parse_failures == 1


@pytest.mark.asyncio
async def test_agent_status_includes_parse_failures() -> None:
    """B5: parse_failures must be exposed in status()."""
    bus = InMemoryEventBus()
    agent = _make_agent(bus)
    status = agent.status()
    assert "parse_failures" in status
