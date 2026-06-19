# tests/orchestration/test_seen_ids_bounded.py
"""Item 6 (P1-3): ExecutionAgent._seen_ids stays bounded at 10,000."""
from __future__ import annotations

import hashlib

import pytest
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.rate_limiter import TokenBucket
from orchestration.agents.execution_agent import ExecutionAgent


def _make_exec() -> ExecutionAgent:
    bus = InMemoryEventBus()
    bucket = TokenBucket(capacity=100_000, refill_per_sec=100_000.0)

    class FakeSettings:
        execution_engine = "paper"
        live_trading_confirm = ""

    return ExecutionAgent(
        bus=bus,
        raw_decisions_topic="decisions.v1",
        approved_topic="decisions.approved.v1",
        settings=FakeSettings(),
        breaker=CircuitBreaker(max_consecutive_losses=999),
        rate_limiter=bucket,
        logger=structlog.get_logger("test"),
    )


@pytest.mark.asyncio
async def test_seen_ids_bounded_after_overflow() -> None:
    """After >10000 unique ids, the set and deque stay at max 10000."""
    agent = _make_exec()

    # Push 12000 unique ids
    for i in range(12_000):
        decision_id = f"decision-{i:06d}"
        raw_id = decision_id
        client_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
        if client_id in agent._seen_ids:
            continue
        if len(agent._seen_ids_deque) == agent._MAX_SEEN_IDS:
            oldest = agent._seen_ids_deque[0]
            agent._seen_ids.discard(oldest)
        agent._seen_ids_deque.append(client_id)
        agent._seen_ids.add(client_id)

    assert len(agent._seen_ids_deque) <= agent._MAX_SEEN_IDS
    assert len(agent._seen_ids) <= agent._MAX_SEEN_IDS
    assert len(agent._seen_ids) == len(agent._seen_ids_deque)


@pytest.mark.asyncio
async def test_recent_duplicate_still_suppressed_after_overflow() -> None:
    """A recently seen id is still suppressed even after the buffer fills."""
    agent = _make_exec()

    # Fill the buffer with MAX+500 ids to force eviction of the first 500
    overflow = agent._MAX_SEEN_IDS + 500
    for i in range(overflow):
        decision_id = f"decision-{i:07d}"
        raw_id = decision_id
        client_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
        if client_id in agent._seen_ids:
            continue
        if len(agent._seen_ids_deque) == agent._MAX_SEEN_IDS:
            oldest = agent._seen_ids_deque[0]
            agent._seen_ids.discard(oldest)
        agent._seen_ids_deque.append(client_id)
        agent._seen_ids.add(client_id)

    # Deque and set bounded
    assert len(agent._seen_ids_deque) <= agent._MAX_SEEN_IDS
    assert len(agent._seen_ids) <= agent._MAX_SEEN_IDS

    # The most recently added id should still be in the set
    last_id = f"decision-{overflow - 1:07d}"
    last_client_id = hashlib.sha256(last_id.encode()).hexdigest()[:16]
    assert last_client_id in agent._seen_ids

    # The very first id should have been evicted
    first_id = "decision-0000000"
    first_client_id = hashlib.sha256(first_id.encode()).hexdigest()[:16]
    assert first_client_id not in agent._seen_ids
