"""P1-2: ExecutionAgent _seen_ids stays bounded at 10 000 entries.
P1-3: InMemoryEventBus exposes a dropped_messages counter.
"""
from __future__ import annotations

import asyncio

import orjson
import pytest

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from orchestration.agents.execution_agent import _SEEN_IDS_MAX, ExecutionAgent

# ── P1-2: bounded _seen_ids ────────────────────────────────────────────────

def _make_exec_agent(bus: InMemoryEventBus) -> ExecutionAgent:
    import structlog
    breaker = CircuitBreaker()
    bucket = TokenBucket(capacity=100_000, refill_per_sec=1_000_000.0)
    return ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=type("S", (), {"execution_engine": "paper", "live_trading_confirm": ""})(),
        breaker=breaker,
        rate_limiter=bucket,
        logger=structlog.get_logger("test"),
    )


@pytest.mark.asyncio
async def test_seen_ids_stays_bounded_after_overflow() -> None:
    """Pushing more than _SEEN_IDS_MAX unique IDs must not exceed the cap."""
    bus = InMemoryEventBus()
    agent = _make_exec_agent(bus)
    q = bus.subscribe("decisions.approved.v1")

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.02)

    n = _SEEN_IDS_MAX + 500  # deliberately exceed the window

    for i in range(n):
        msg = orjson.dumps({
            "decision": "EXECUTE",
            "signal": "BUY",
            "decision_id": f"unique-{i:08d}",
        })
        await bus.publish("decisions.v1", b"k", msg)

    # Drain processed messages briefly
    await asyncio.sleep(0.3)
    await agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(agent._seen_ids_deque) <= _SEEN_IDS_MAX
    assert len(agent._seen_ids_set) <= _SEEN_IDS_MAX


@pytest.mark.asyncio
async def test_duplicate_suppression_still_works_within_window() -> None:
    """Duplicate IDs within the current window are suppressed."""
    bus = InMemoryEventBus()
    agent = _make_exec_agent(bus)
    approved_q = bus.subscribe("decisions.approved.v1")

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.02)

    dup_msg = orjson.dumps({
        "decision": "EXECUTE",
        "signal": "BUY",
        "decision_id": "dup-id-999",
    })
    # Send same message twice
    await bus.publish("decisions.v1", b"k", dup_msg)
    await bus.publish("decisions.v1", b"k", dup_msg)
    await asyncio.sleep(0.1)

    await agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    # Only 1 forwarded message (second is duplicate-suppressed)
    forwarded = 0
    while not approved_q.empty():
        msg = orjson.loads(approved_q.get_nowait())
        if msg.get("decision") == "EXECUTE":
            forwarded += 1
    assert forwarded == 1, f"Expected 1 forwarded (duplicate suppressed), got {forwarded}"


# ── P1-3: dropped_messages counter ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_event_bus_dropped_counter_increments_on_full_queue() -> None:
    """Flooding a tiny queue increments InMemoryEventBus.dropped_messages."""
    bus = InMemoryEventBus()
    q = bus.subscribe("flood.v1", maxsize=2)  # tiny queue

    msg = orjson.dumps({"x": 1})
    # Publish more than queue capacity without consuming — oldest should be dropped
    for _ in range(10):
        await bus.publish("flood.v1", b"k", msg)

    assert bus.dropped_messages > 0, (
        "Expected dropped_messages > 0 after flooding a tiny queue"
    )


@pytest.mark.asyncio
async def test_dropped_messages_surfaced_in_runtime_status() -> None:
    """runtime.status() must include 'dropped_messages' key."""
    from tests.conftest import make_test_runtime

    rt = make_test_runtime()
    await rt.start("live")
    try:
        status = rt.status()
        assert "dropped_messages" in status, "status() must expose dropped_messages"
        assert isinstance(status["dropped_messages"], int)
    finally:
        await rt.stop()
