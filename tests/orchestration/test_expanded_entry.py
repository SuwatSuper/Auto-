# Layer 2 — Orchestration (tests/orchestration/test_expanded_entry)
"""The Market Analyst can reason over the expanded 9-line confluence."""
from __future__ import annotations

import asyncio

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.entry_exit import EntryExitAgent


def _logger() -> structlog.BoundLogger:
    return structlog.get_logger()


async def test_expanded_agent_emits_buy_on_uptrend_and_labels_detail() -> None:
    bus = InMemoryEventBus()
    out_q = bus.subscribe("signals")
    agent = EntryExitAgent(
        bus=bus, topic_in="prices", topic_out="signals", logger=_logger(), expanded=True
    )
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    # Feed a steady up-trend long enough to clear the expanded warm-up window.
    for i in range(120):
        msg = orjson.dumps({"price": str(1_000_000 + i * 1_000), "ts_ms": i * 1_000})
        await bus.publish("prices", b"key", msg)
    await asyncio.sleep(0.2)

    assert agent.detail.startswith("Confluence+")
    # An unambiguous up-trend should produce at least one BUY signal.
    saw_buy = False
    while not out_q.empty():
        data = orjson.loads(out_q.get_nowait())
        if data["signal"] == "BUY":
            saw_buy = True
    assert saw_buy

    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
