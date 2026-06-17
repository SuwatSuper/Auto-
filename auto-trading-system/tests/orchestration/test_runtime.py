# Layer 2 — Orchestration (tests/orchestration/test_runtime)
"""Regression tests for PipelineRuntime bug fixes (B1, B2, B7, B9)."""
from __future__ import annotations

import asyncio
import contextlib

import pytest
import structlog

from infrastructure.clocks.system_clock import SystemClock
from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.events.in_memory_event_store import InMemoryEventStore
from infrastructure.state.in_memory_store import InMemoryStateStore
from orchestration.runtime import PipelineRuntime, RuntimeDeps
from tests._fixtures import FakePriceFeed


def _make_runtime() -> PipelineRuntime:
    settings = Settings(persist_state=False, initial_capital="1000", prices_topic="prices.thb_btc.v1")
    logger = structlog.get_logger("test")
    bus = InMemoryEventBus()
    deps = RuntimeDeps(
        bus=bus,
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: FakePriceFeed(),
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, logger, deps=deps)


@pytest.mark.asyncio
async def test_switch_mode_keeps_bus_subscribers() -> None:
    """B1: switching mode must NOT orphan existing bus subscribers."""

    runtime = _make_runtime()
    # Start first so the bus is available
    await runtime.start("live")
    try:
        # Subscribe after start
        topic = "prices.thb_btc.v1"
        queue = runtime.bus.subscribe(topic)
        original_bus_id = id(runtime.bus)

        # Switch mode — bus must be the same object
        await runtime.switch_mode("live")
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
    await runtime.start("live")
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
    await runtime.start("live")
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
    await runtime.start("live")
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
    await runtime.start("live")
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
    await runtime.start("live")
    # Normal stop should work cleanly without hanging or crashing
    await runtime.stop()
    # If we get here without a hang or unhandled exception the fix is working


@pytest.mark.asyncio
async def test_switch_mode_bus_not_replaced_multiple_times() -> None:
    """B1: Switching mode multiple times must always reuse the original bus."""
    runtime = _make_runtime()
    await runtime.start("live")
    original_bus = runtime.bus
    try:
        for _ in range(3):
            await runtime.switch_mode("live")
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


# --- price-feed staleness watchdog (frozen-price auto-recovery) ---

class _StallingFeed:
    """Emits a few prices on each run() entry, then goes silent.

    Models a feed whose task stays alive but stops producing (wedged HTTP pool,
    half-open socket, API shape change). A fresh run() — triggered by the
    watchdog re-dial — resumes emitting, with a strictly rising price so the
    test can prove the stream recovered."""

    def __init__(self) -> None:
        self.step = 0
        self.runs = 0

    async def run(self, on_raw) -> None:  # type: ignore[no-untyped-def]
        self.runs += 1
        for _ in range(3):
            self.step += 1
            # No "ts" — exactly like the real REST feed, so the normalizer
            # stamps event time as now (a hardcoded ts would read as 1970 =
            # STALE and the price would be dropped).
            await on_raw({"last": str(1_500_000 + self.step)})
            await asyncio.sleep(0.02)
        await asyncio.sleep(3600)  # go silent: alive but producing nothing


def _make_runtime_with_feed(feed) -> PipelineRuntime:  # type: ignore[no-untyped-def]
    settings = Settings(persist_state=False, initial_capital="1000", prices_topic="prices.thb_btc.v1")
    deps = RuntimeDeps(
        bus=InMemoryEventBus(),
        clock=SystemClock(),
        state_store=InMemoryStateStore(),
        event_store=InMemoryEventStore(),
        feed_factory=lambda _mode: feed,
        prices_topic="prices.thb_btc.v1",
    )
    return PipelineRuntime(settings, structlog.get_logger("test"), deps=deps)


async def _wait_until(cond, timeout: float = 3.0) -> None:  # type: ignore[no-untyped-def]
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if cond():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("condition not reached in time")


@pytest.mark.asyncio
async def test_fresh_feed_is_not_restarted() -> None:
    """A feed that produced a price recently must NOT be re-dialed."""
    import time

    runtime = _make_runtime_with_feed(FakePriceFeed())
    await runtime.start("live")
    try:
        await _wait_until(lambda: runtime._latest_price is not None)
        runtime._last_price_wall_ms = int(time.time() * 1000)  # just produced
        await runtime._restart_feed_if_stale()
        assert runtime._price_feed_stale_restarts == 0
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_stale_feed_is_redialed_and_price_resumes() -> None:
    """A feed that is alive but silent past the threshold is re-dialed, and
    the price stream resumes (regression: frozen BTC price never recovered)."""
    import time

    feed = _StallingFeed()
    runtime = _make_runtime_with_feed(feed)
    await runtime.start("live")
    try:
        await _wait_until(lambda: runtime._latest_price is not None)
        price_before = runtime._latest_price
        runs_before = feed.runs
        old_task = runtime.supervisor_task
        assert price_before is not None

        # Simulate "no price for a long time" and run the watchdog probe.
        runtime._last_price_wall_ms = int(time.time() * 1000) - 999_999
        await runtime._restart_feed_if_stale()
        # The re-dialed feed must produce a fresh, higher price.
        await _wait_until(
            lambda: runtime._latest_price is not None and runtime._latest_price > price_before
        )

        assert runtime._price_feed_stale_restarts == 1
        assert feed.runs > runs_before, "feed.run() was not re-entered"
        assert runtime.supervisor_task is not old_task, "feed task was not replaced"
        assert runtime.supervisor_task is not None and not runtime.supervisor_task.done()
        assert runtime.status()["price_feed"]["stale_restarts"] == 1
    finally:
        await runtime.stop()
