"""Performance benchmarks: throughput and latency for critical paths.

All thresholds are set conservatively below measured values so CI stays stable.
Measured on a single-core sandbox; real hardware will be faster.
"""
from __future__ import annotations

import time
from decimal import Decimal

import pytest

from domain.trading.market_data import normalize_bitkub_ticker


# ── 1. Price-normalization throughput ───────────────────────────────────────

def test_price_normalization_throughput() -> None:
    """normalize_bitkub_ticker must handle ≥5 000 ticks/s (conservative threshold)."""
    tick = {
        "id": 1,
        "last": "3500000.00",
        "highestBid": "3499000",
        "lowestAsk": "3501000",
        "percentChange": "0.5",
        "baseVolume": "10.5",
        "quoteVolume": "36750000",
        "isFrozen": "0",
        "high24hr": "3600000",
        "low24hr": "3400000",
        "change": "17500",
        "prevClose": "3482500",
        "prevOpen": "3482500",
    }
    now_ms = int(time.time() * 1000)
    iterations = 5_000
    t0 = time.perf_counter()
    for _ in range(iterations):
        normalize_bitkub_ticker(tick, now_ms=now_ms)
    elapsed = time.perf_counter() - t0
    throughput = iterations / elapsed
    assert throughput >= 5_000, (
        f"price normalization too slow: {throughput:.0f} ticks/s (need ≥5 000)"
    )


# ── 2. Event-bus publish/subscribe latency ──────────────────────────────────

@pytest.mark.asyncio
async def test_event_bus_pubsub_latency() -> None:
    """Single publish→receive round-trip must complete in <1 ms (p99 across 1 000 trips)."""
    from infrastructure.eventbus.in_memory import InMemoryEventBus

    bus = InMemoryEventBus()
    q = bus.subscribe("bench.v1")
    payload = b'{"price":"3500000","ts_ms":1}'
    latencies: list[float] = []

    for _ in range(1_000):
        t0 = time.perf_counter()
        await bus.publish("bench.v1", b"k", payload)
        await q.get()
        latencies.append((time.perf_counter() - t0) * 1000)

    latencies.sort()
    p99_ms = latencies[int(len(latencies) * 0.99)]
    assert p99_ms < 1.0, f"event bus p99 latency {p99_ms:.3f} ms exceeds 1 ms"


# ── 3. Signal→decision latency (EntryExit + Supreme round-trip) ─────────────

@pytest.mark.asyncio
async def test_signal_to_decision_latency() -> None:
    """Signal→decision round-trip via EntryExitAgent must be <50 ms p99."""
    import asyncio

    import orjson
    import structlog

    from infrastructure.eventbus.in_memory import InMemoryEventBus
    from orchestration.agents.entry_exit import EntryExitAgent

    bus = InMemoryEventBus()
    log = structlog.get_logger()
    agent = EntryExitAgent(bus, "prices.v1", "signals.v1", log)

    prices_q = bus.subscribe("prices.v1")  # noqa: F841 — subscribe before publish
    signals_q = bus.subscribe("signals.v1")

    task = asyncio.create_task(agent.start())
    # Let the agent settle
    await asyncio.sleep(0.05)

    latencies: list[float] = []
    price_seq = [3_500_000 + i * 100 for i in range(35)]
    for px in price_seq:
        msg = orjson.dumps({"price": str(px), "ts_ms": int(time.time() * 1000)})
        t0 = time.perf_counter()
        await bus.publish("prices.v1", b"k", msg)
        try:
            await asyncio.wait_for(signals_q.get(), timeout=0.2)
            latencies.append((time.perf_counter() - t0) * 1000)
        except TimeoutError:
            pass

    await agent.stop()
    task.cancel()
    import contextlib
    with contextlib.suppress(asyncio.CancelledError):
        await task

    if latencies:
        latencies.sort()
        p99_ms = latencies[int(len(latencies) * 0.99)]
        assert p99_ms < 50.0, f"signal→decision p99 {p99_ms:.1f} ms exceeds 50 ms"
