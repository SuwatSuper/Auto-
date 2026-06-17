# Layer 2 — Orchestration (tests/orchestration/test_load_scaling)
"""Honest scalability (re-scoped): we do NOT claim distributed or 'thousands'.
We MEASURE what ONE process sustains — N analyst agents started + processing a
burst within a budget — and pin it so a regression is caught. The number any
doc may claim must trace to this test."""
from __future__ import annotations

import asyncio
import time

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.swarm import build_swarm_agents


async def test_one_process_runs_154_agents_and_a_burst_within_budget() -> None:
    bus = InMemoryEventBus()
    log = structlog.get_logger("load")
    agents = build_swarm_agents(
        bus, "prices.thb_btc.v1", "signals.v1", "analysis.v1", log, per_division=50,
    )
    n = len(agents)
    assert n == 154  # market-data hub + 3 chiefs + 150 workers, all in one process

    t0 = time.perf_counter()
    tasks = [asyncio.create_task(a.start()) for a in agents.values()]
    await asyncio.sleep(0.15)  # let every agent subscribe / enter its loop
    startup_s = time.perf_counter() - t0

    # Publish a burst of REAL price ticks; the hub ingests and the swarm ticks.
    ticks = 500
    t1 = time.perf_counter()
    for i in range(ticks):
        await bus.publish(
            "prices.thb_btc.v1", b"k",
            orjson.dumps({"price": str(1_500_000 + i * 5), "ts_ms": i}),
        )
    publish_s = time.perf_counter() - t1
    await asyncio.sleep(0.3)  # let the swarm process/tick on the burst
    running = sum(1 for a in agents.values() if a.running)

    for a in agents.values():
        await a.stop()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    # Measured, conservative budgets (dev box: startup ≈0.15s, ≫100k ticks/s).
    assert running == n, f"only {running}/{n} agents alive under load"
    assert startup_s < 3.0, f"startup {startup_s:.2f}s for {n} agents (budget 3s)"
    tick_rate = ticks / publish_s if publish_s > 0 else 0.0
    assert tick_rate >= 5_000, f"tick publish rate {tick_rate:,.0f}/s too low (budget 5k)"
