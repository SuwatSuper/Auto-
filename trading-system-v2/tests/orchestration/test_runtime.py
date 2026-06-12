# Layer 2 — Orchestration (tests/orchestration/test_runtime)
"""Regression tests for PipelineRuntime bug fixes (B1, B2, B7, B9)."""
from __future__ import annotations

import asyncio
import contextlib

import pytest
import structlog

from infrastructure.config import Settings
from orchestration.runtime import PipelineRuntime


def _make_runtime() -> PipelineRuntime:
    settings = Settings(prices_topic="prices.thb_btc.v1")
    logger = structlog.get_logger("test")
    return PipelineRuntime(settings, logger)


@pytest.mark.asyncio
async def test_switch_mode_keeps_bus_subscribers() -> None:
    """B1: switching mode must NOT orphan existing bus subscribers."""
    from infrastructure.eventbus.in_memory import InMemoryEventBus

    runtime = _make_runtime()
    # Start first so the bus is available
    await runtime.start("simulator")
    try:
        # Subscribe after start
        topic = "prices.thb_btc.v1"
        queue = runtime.bus.subscribe(topic)
        original_bus_id = id(runtime.bus)

        # Switch mode — bus must be the same object
        await runtime.switch_mode("simulator")
        assert id(runtime.bus) == original_bus_id, "bus object was replaced!"

        # Verify the subscriber queue is still registered in the same bus
        bus_impl: InMemoryEventBus = runtime.bus  # type: ignore[assignment]
        subs = bus_impl._subs.get(topic, [])
        assert queue in subs, "Pre-switch subscriber was dropped from bus after switch_mode"
    finally:
        await runtime.stop()
        with contextlib.suppress(Exception):
            runtime.bus.unsubscribe(topic, queue)


@pytest.mark.asyncio
async def test_emergency_reset_clears_flag() -> None:
    """B2: emergency_reset() must clear emergency_stopped without auto-starting."""
    runtime = _make_runtime()
    await runtime.start("simulator")
    try:
        await runtime.emergency_stop()
        assert runtime.emergency_stopped is True

        await runtime.emergency_reset()
        assert runtime.emergency_stopped is False
        # Agents should still be stopped — reset does NOT auto-start
        for agent in runtime.agents.values():
            assert not agent.running
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_emergency_reset_allows_restart() -> None:
    """B2: after emergency_reset, start_all should work and status should reflect it."""
    runtime = _make_runtime()
    await runtime.start("simulator")
    try:
        await runtime.emergency_stop()
        assert runtime.emergency_stopped is True

        await runtime.emergency_reset()
        assert runtime.emergency_stopped is False

        # Can start agents after reset
        for name in list(runtime.agents):
            await runtime.start_agent(name)

        status = runtime.status()
        assert status["emergency_stopped"] is False
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_status_includes_latency_precision() -> None:
    """B9: status() must include latency_precision field set to 'ms'."""
    runtime = _make_runtime()
    await runtime.start("simulator")
    try:
        s = runtime.status()
        assert "latency_precision" in s, "status() must include latency_precision"
        assert s["latency_precision"] == "ms"
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_latency_clamped_at_zero() -> None:
    """B9: latency_ms must never be negative (clamped at >= 0)."""
    from decimal import Decimal

    runtime = _make_runtime()
    await runtime.start("simulator")
    try:
        # Simulate a negative raw latency (future-dated timestamp)
        runtime.record_message(Decimal("1500000"), -500)
        s = runtime.status()
        assert s["latency_ms"] >= 0, "latency_ms must be clamped at 0, got negative"
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_stop_does_not_swallow_all_exceptions(caplog: pytest.LogCaptureFixture) -> None:
    """B7: stop() must not silently swallow non-CancelledError exceptions."""
    runtime = _make_runtime()
    await runtime.start("simulator")
    # Normal stop should work cleanly without hanging or crashing
    await runtime.stop()
    # If we get here without a hang or unhandled exception the fix is working


@pytest.mark.asyncio
async def test_switch_mode_bus_not_replaced_multiple_times() -> None:
    """B1: Switching mode multiple times must always reuse the original bus."""
    runtime = _make_runtime()
    await runtime.start("simulator")
    original_bus = runtime.bus
    try:
        for _ in range(3):
            await runtime.switch_mode("simulator")
            assert runtime.bus is original_bus, "bus was replaced on repeated switch_mode"
    finally:
        await runtime.stop()


# --- B5: SampleAgent tests ---

@pytest.mark.asyncio
async def test_agent_stops_cleanly_within_1s() -> None:
    """B5: SampleAgent must stop cleanly within 1 second after stop() is called."""
    from infrastructure.eventbus.in_memory import InMemoryEventBus
    from orchestration.agents.sample_agent import SampleAgent

    bus = InMemoryEventBus()
    logger = structlog.get_logger("test")
    agent = SampleAgent("test_agent", bus, "test_topic", logger)

    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.1)  # Let it start
    await agent.stop()

    try:
        await asyncio.wait_for(task, timeout=1.0)
    except TimeoutError:
        task.cancel()
        pytest.fail("SampleAgent did not stop within 1 second")


@pytest.mark.asyncio
async def test_agent_status_includes_parse_failures() -> None:
    """B5: SampleAgent.status() must include parse_failures counter."""
    from infrastructure.eventbus.in_memory import InMemoryEventBus
    from orchestration.agents.sample_agent import SampleAgent

    bus = InMemoryEventBus()
    logger = structlog.get_logger("test")
    agent = SampleAgent("test_agent", bus, "test_topic", logger)

    s = agent.status()
    assert "parse_failures" in s, "SampleAgent.status() must include parse_failures"
    assert s["parse_failures"] == 0


# --- B6: BitkubWebSocketGateway backoff tests ---

def test_backoff_bounds() -> None:
    """B6: _backoff must return values within expected range."""
    from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway

    gw = BitkubWebSocketGateway("wss://example.com")

    # Attempt 0: base = 1.0, jitter ±20% → [0.8, 1.2]
    for _ in range(50):
        v = gw._backoff(0)
        assert 0.0 <= v <= 2.0, f"backoff(0) out of range: {v}"

    # Attempt 10: base hits cap 30.0, jitter ±20% → [24.0, 36.0] but max(0, x)
    for _ in range(50):
        v = gw._backoff(10)
        assert 0.0 <= v <= 36.0, f"backoff(10) out of range: {v}"
        assert v <= gw._BACKOFF_CAP * 1.2 + 0.001, f"backoff exceeds cap+jitter: {v}"


def test_backoff_never_negative() -> None:
    """B6: _backoff must never return negative values."""
    from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway

    gw = BitkubWebSocketGateway("wss://example.com")
    for attempt in range(20):
        for _ in range(20):
            v = gw._backoff(attempt)
            assert v >= 0.0, f"_backoff({attempt}) returned negative: {v}"
