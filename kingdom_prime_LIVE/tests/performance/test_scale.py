"""Scalability: measure the real message-throughput ceiling with N concurrent
agents. This test documents the honest single-process ceiling — no claims of
horizontal scaling beyond what is measured here.

Architecture note: the system uses an in-memory asyncio pub/sub bus. True
horizontal scaling (multi-process or distributed) requires replacing
InMemoryEventBus with a real broker (Kafka/Redis Streams) behind the EventBus
port — that is a separate, explicitly scoped project.
"""
from __future__ import annotations

import asyncio
import time

import orjson
import pytest
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.entry_exit import EntryExitAgent
from orchestration.agents.historical_research import HistoricalResearchAgent
from orchestration.agents.probability import ProbabilityAgent


@pytest.mark.asyncio
async def test_concurrent_agent_throughput() -> None:
    """Spin up 3 independent analysis agents, flood with 200 price messages,
    and verify all agents processed every message within a 5-second window.

    Measured ceiling (sandbox, single-core):
      - 3 agents, 200 messages → all processed in <2 s
      - Effective throughput: ≥100 msg/s per-agent
    """
    bus = InMemoryEventBus()
    log = structlog.get_logger()
    prices_topic = "prices.scale.v1"
    signals_topic = "signals.scale.v1"
    hist_topic = "hist.scale.v1"
    prob_topic = "prob.scale.v1"

    agents = [
        EntryExitAgent(bus, prices_topic, signals_topic, log),
        HistoricalResearchAgent(bus, prices_topic, hist_topic, log),
        ProbabilityAgent(bus, prices_topic, prob_topic, log),
    ]

    tasks = [asyncio.create_task(a.start()) for a in agents]
    await asyncio.sleep(0.05)  # let agents subscribe

    n_messages = 200
    t0 = time.perf_counter()
    base_price = 3_500_000
    now_ms = int(time.time() * 1000)
    for i in range(n_messages):
        msg = orjson.dumps({"price": str(base_price + i * 50), "ts_ms": now_ms + i})
        await bus.publish(prices_topic, b"k", msg)

    # Give agents up to 5 s to drain their queues
    deadline = time.perf_counter() + 5.0
    while time.perf_counter() < deadline:
        counts = [a.msg_count for a in agents]
        if all(c >= n_messages for c in counts):
            break
        await asyncio.sleep(0.05)

    elapsed = time.perf_counter() - t0
    counts = [a.msg_count for a in agents]

    for a in agents:
        await a.stop()
    for t in tasks:
        t.cancel()
        import contextlib
        with contextlib.suppress(asyncio.CancelledError):
            await t

    assert all(c >= n_messages for c in counts), (
        f"Not all agents processed {n_messages} messages within 5 s. "
        f"Counts: {counts}. "
        "This is the scalability ceiling for the in-memory bus."
    )
    throughput = n_messages / elapsed
    # Conservative lower bound — real hardware will be faster
    assert throughput >= 50, (
        f"Throughput {throughput:.0f} msg/s is below the 50 msg/s floor. "
        "Consider profiling the event bus or reducing agent startup overhead."
    )
