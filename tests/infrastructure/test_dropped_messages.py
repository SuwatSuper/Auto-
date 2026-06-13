# tests/infrastructure/test_dropped_messages.py
"""Item 7 (P1-4): InMemoryEventBus counts dropped messages."""
from __future__ import annotations

import pytest

from infrastructure.eventbus.in_memory import InMemoryEventBus


@pytest.mark.asyncio
async def test_dropped_counter_increments_on_full_queue() -> None:
    """Flooding a small queue increments dropped_messages."""
    bus = InMemoryEventBus()
    bus.subscribe("test.topic", maxsize=3)

    # Fill queue beyond capacity
    for i in range(10):
        await bus.publish("test.topic", b"k", f"msg-{i}".encode())

    assert bus.dropped_messages > 0


@pytest.mark.asyncio
async def test_dropped_counter_zero_when_no_overflow() -> None:
    """No drops when queue is never full."""
    bus = InMemoryEventBus()
    _queue = bus.subscribe("test.topic", maxsize=100)

    for i in range(5):
        await bus.publish("test.topic", b"k", f"msg-{i}".encode())

    assert bus.dropped_messages == 0


@pytest.mark.asyncio
async def test_dropped_messages_in_runtime_status() -> None:
    """Runtime status() includes dropped_messages field."""
    import structlog

    from infrastructure.clocks.system_clock import SystemClock
    from infrastructure.config import Settings
    from infrastructure.eventbus.in_memory import InMemoryEventBus
    from infrastructure.events.in_memory_event_store import InMemoryEventStore
    from infrastructure.state.in_memory_store import InMemoryStateStore
    from orchestration.runtime import PipelineRuntime, RuntimeDeps
    from tests._fixtures import FakePriceFeed

    settings = Settings(training_mode=False, persist_state=False, initial_capital="1000")
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _: FakePriceFeed(),
    )
    runtime = PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)
    await runtime.start("live")
    try:
        status = runtime.status()
        assert "dropped_messages" in status
        assert isinstance(status["dropped_messages"], int)
    finally:
        await runtime.stop()
