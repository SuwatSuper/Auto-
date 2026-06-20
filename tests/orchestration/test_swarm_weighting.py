# Layer 2 — Orchestration (tests/orchestration/test_swarm_weighting)
"""Task 3: meaningful consensus for the 150-agent parameter grid.

The grid already spans distinct (timeframe, method, window) slices. This proves
the division chiefs now apply REGIME-AWARE dynamic weighting (the previously
dead SwarmMetaLearner): a chief weights each worker by its method's measured
reliability in the current regime, and feeds real graded outcomes back into the
shared meta-learner — so the swarm prioritises whoever is actually winning now.
"""
from __future__ import annotations

from decimal import Decimal

import orjson
import structlog

from domain.analytics.swarm_meta import SwarmMetaLearner
from domain.analytics.swarm_methods import BEAR, BULL, AnalysisRead
from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.swarm import (
    ChartAnalystAgent,
    DivisionChiefAgent,
    MarketDataHub,
    build_swarm_agents,
)


def _log() -> structlog.BoundLogger:
    return structlog.get_logger("test")


def _workers(hub: MarketDataHub, methods: list[str]) -> list[ChartAnalystAgent]:
    return [
        ChartAnalystAgent(f"w{i}_{m}", hub, "1s", m, "historical", _log())
        for i, m in enumerate(methods)
    ]


# ── weighted bias reflects per-method reliability ────────────────────
async def test_chief_weights_reliable_method_more() -> None:
    hub = MarketDataHub()
    meta = SwarmMetaLearner()
    # Two methods disagree: "good" is bullish, "bad" is bearish.
    workers = _workers(hub, ["good", "bad"])
    workers[0].read = AnalysisRead(BULL, Decimal("0.8"), "up")
    workers[1].read = AnalysisRead(BEAR, Decimal("0.8"), "down")
    chief = DivisionChiefAgent(
        "c", list(workers), InMemoryEventBus(), "analysis.v1", "lab", _log(),
        meta=meta, regime_provider=lambda: "TREND_UP",
    )
    # With equal reliability the bias would be 0.0 (one bull, one bear).
    # Make "good" highly reliable and "bad" unreliable IN THIS REGIME.
    for _ in range(20):
        meta.record("good", "TREND_UP", won=True)
        meta.record("bad", "TREND_UP", won=False)
    await chief.tick()
    assert chief.bias > 0.0  # the reliable bull is heard louder than the bear


async def test_chief_equal_weight_without_meta() -> None:
    hub = MarketDataHub()
    workers = _workers(hub, ["a", "b"])
    workers[0].read = AnalysisRead(BULL, Decimal("0.8"), "up")
    workers[1].read = AnalysisRead(BEAR, Decimal("0.8"), "down")
    chief = DivisionChiefAgent("c", list(workers), InMemoryEventBus(), "analysis.v1", "lab", _log())
    await chief.tick()
    assert chief.bias == 0.0  # back-compat: equal-weight headcount


# ── chief feeds real graded outcomes into the shared meta-learner ────
async def test_chief_records_worker_outcomes_into_meta() -> None:
    hub = MarketDataHub()
    meta = SwarmMetaLearner()
    workers = _workers(hub, ["ema_cross"])
    chief = DivisionChiefAgent(
        "c", list(workers), InMemoryEventBus(), "analysis.v1", "lab", _log(),
        meta=meta, regime_provider=lambda: "RANGE",
    )
    # Simulate the worker having graded 3 predictions (2 wins, 1 loss).
    workers[0].learner.resolved = 3
    workers[0].learner.correct = 2
    await chief.tick()
    stats = meta.stats[("ema_cross", "RANGE")]
    assert stats.total == 3 and stats.wins == 2


async def test_analysis_payload_marks_weighting_and_regime() -> None:
    hub = MarketDataHub()
    meta = SwarmMetaLearner()
    bus = InMemoryEventBus()
    q = bus.subscribe("analysis.v1")
    workers = _workers(hub, ["ema_cross"])
    chief = DivisionChiefAgent(
        "c", list(workers), bus, "analysis.v1", "lab", _log(),
        meta=meta, regime_provider=lambda: "HIGH_VOL",
    )
    await chief.tick()
    msg = orjson.loads(q.get_nowait())
    assert msg["weighted"] is True and msg["regime"] == "HIGH_VOL"


# ── factory wires the shared meta-learner into all three chiefs ──────
def test_build_swarm_passes_meta_to_chiefs() -> None:
    bus = InMemoryEventBus()
    meta = SwarmMetaLearner()
    agents = build_swarm_agents(
        bus, "prices", "signals.v1", "analysis.v1", _log(),
        meta=meta, regime_provider=lambda: "RANGE",
    )
    for name in ("historical_chief", "live_chief", "entry_chief"):
        assert agents[name].meta is meta  # type: ignore[attr-defined]
    # the grid is still the full 150 distinct workers + 3 chiefs + hub
    assert len(agents) == 1 + 3 + 150
    # workers expose their method (the grid key for weighting)
    assert agents["hist_01_1s_ema_cross"].method == "ema_cross"  # type: ignore[attr-defined]
