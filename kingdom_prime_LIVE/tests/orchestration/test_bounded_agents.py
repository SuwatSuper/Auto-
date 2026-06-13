"""P0-2: Verify that EntryExitAgent and ProbabilityAgent cap their price windows
to ≤ 500 entries even when fed far more than 500 ticks.
"""
from __future__ import annotations

import asyncio

import orjson
import pytest
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.entry_exit import EntryExitAgent
from orchestration.agents.probability import ProbabilityAgent

_TICKS = 10_000
_MAX_WINDOW = 500


def _price_msg(px: float, i: int) -> bytes:
    return orjson.dumps({"price": str(px), "ts_ms": i * 1000})


@pytest.mark.asyncio
async def test_entry_exit_price_window_bounded() -> None:
    """EntryExitAgent must keep at most 500 prices after 10 000 ticks."""
    bus = InMemoryEventBus()
    log = structlog.get_logger("test")
    agent = EntryExitAgent(bus, "prices.v1", "signals.v1", log)

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.01)

    for i in range(_TICKS):
        await bus.publish("prices.v1", b"k", _price_msg(1_500_000.0 + i, i))

    await asyncio.sleep(0.2)
    await agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(agent._prices) <= _MAX_WINDOW, (
        f"EntryExitAgent kept {len(agent._prices)} prices (max {_MAX_WINDOW})"
    )
    # Signals must still be computed (agent ran without crash)
    assert agent.msg_count >= _TICKS // 2


@pytest.mark.asyncio
async def test_probability_price_window_bounded() -> None:
    """ProbabilityAgent must keep at most 500 prices after 10 000 ticks."""
    bus = InMemoryEventBus()
    log = structlog.get_logger("test")
    agent = ProbabilityAgent(bus, "prices.v1", "prob.v1", log)

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.01)

    for i in range(_TICKS):
        await bus.publish("prices.v1", b"k", _price_msg(1_500_000.0 + i, i))

    await asyncio.sleep(0.2)
    await agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert len(agent._prices) <= _MAX_WINDOW, (
        f"ProbabilityAgent kept {len(agent._prices)} prices (max {_MAX_WINDOW})"
    )
    assert agent.msg_count >= _TICKS // 2
