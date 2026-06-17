# Layer 2 — Orchestration (tests/orchestration/test_swarm)
"""Tests for the 150-agent analyst swarm: hub resampling, analysts, entry
hunters, division chiefs, and the factory that wires them together."""
from __future__ import annotations

import asyncio
from decimal import Decimal

import orjson
import structlog

from domain.analytics.swarm_methods import BEAR, BULL, AnalysisRead
from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.swarm import (
    ChartAnalystAgent,
    DivisionChiefAgent,
    EntryChiefAgent,
    EntryHunterAgent,
    MarketDataHub,
    MarketDataHubAgent,
    build_swarm_agents,
    make_specs,
)


def _log() -> structlog.BoundLogger:
    return structlog.get_logger("test")


def _feed_rising(hub: MarketDataHub, n: int = 60, base: int = 100, tf_ms: int = 1000) -> None:
    for i in range(n):
        hub.ingest(Decimal(str(base + i)), i * tf_ms)


# ── MarketDataHub ────────────────────────────────────────────────────
def test_hub_resamples_into_completed_candles() -> None:
    hub = MarketDataHub()
    hub.ingest(Decimal("100"), 0)
    hub.ingest(Decimal("101"), 1000)
    hub.ingest(Decimal("102"), 2000)
    counts = hub.candle_counts()
    assert counts["1s"] == 2  # buckets 0 and 1 completed; bucket 2 in progress
    price, ts = hub.latest()
    assert price == Decimal("102")
    assert ts == 2000


def test_hub_updates_ohlc_within_a_bucket() -> None:
    hub = MarketDataHub()
    # three ticks inside the same 1-minute bucket
    hub.ingest(Decimal("100"), 0)
    hub.ingest(Decimal("110"), 1000)
    hub.ingest(Decimal("95"), 2000)
    cur = hub.series("1m", include_current=True)[-1]
    assert cur.open == Decimal("100")
    assert cur.high == Decimal("110")
    assert cur.low == Decimal("95")
    assert cur.close == Decimal("95")


def test_hub_ignores_non_positive_price() -> None:
    hub = MarketDataHub()
    hub.ingest(Decimal("0"), 0)
    hub.ingest(Decimal("-5"), 1000)
    assert hub.latest() == (None, 0)


def test_hub_series_history_excludes_current_by_default() -> None:
    hub = MarketDataHub()
    _feed_rising(hub, n=5)
    past = hub.series("1s")
    live = hub.series("1s", include_current=True)
    assert len(live) == len(past) + 1


# ── specs ────────────────────────────────────────────────────────────
def test_make_specs_is_exactly_n_and_spans_timeframes() -> None:
    specs = make_specs(50)
    assert len(specs) == 50
    assert {tf for tf, _ in specs} == {"1s", "1m", "1h", "1d"}


# ── ChartAnalystAgent ────────────────────────────────────────────────
async def test_chart_analyst_reads_bullish_trend_and_predicts() -> None:
    hub = MarketDataHub()
    _feed_rising(hub, n=60)  # 59 completed 1s candles, strongly rising
    a = ChartAnalystAgent("hist_x", hub, "1s", "ema_cross", "historical", _log())
    await a.tick()
    assert a.read.direction == BULL
    assert "ema_cross" in a.detail
    assert a.signal_count == 1  # a strong directional read is recorded for grading


async def test_chart_analyst_grades_matured_prediction() -> None:
    hub = MarketDataHub()
    _feed_rising(hub, n=60)
    a = ChartAnalystAgent("hist_y", hub, "1s", "ema_cross", "historical", _log())
    await a.tick()  # records a BUY prediction at the latest price
    # price moves up well past the edge, 60s+ later → prediction should resolve
    hub.ingest(Decimal("100000"), 10_000_000)
    await a.tick()
    assert a.learner.resolved >= 1


async def test_chart_analyst_warms_up_quietly() -> None:
    hub = MarketDataHub()
    hub.ingest(Decimal("100"), 0)
    a = ChartAnalystAgent("hist_z", hub, "1h", "ema_cross", "historical", _log())
    await a.tick()
    assert a.read.direction == "NEUTRAL"
    assert a.signal_count == 0


# ── EntryHunterAgent (advisory scout — sets a ready flag) ────────────
async def test_entry_hunter_is_ready_when_bullish_and_bias_agrees() -> None:
    hub = MarketDataHub()
    _feed_rising(hub, n=60)
    hunter = EntryHunterAgent("entry_x", hub, "1s", "ema_cross", Decimal("0.5"), lambda: 1.0, _log())
    await hunter.tick()
    assert hunter.ready is True
    assert hunter.entries_found == 1  # edge-triggered self-prediction recorded


async def test_entry_hunter_holds_when_bias_disagrees() -> None:
    hub = MarketDataHub()
    _feed_rising(hub, n=60)
    hunter = EntryHunterAgent("entry_y", hub, "1s", "ema_cross", Decimal("0.5"), lambda: -1.0, _log())
    await hunter.tick()
    assert hunter.ready is False
    assert hunter.entries_found == 0


async def test_entry_chief_emits_one_consolidated_buy_on_quorum() -> None:
    bus = InMemoryEventBus()
    sig = bus.subscribe("signals.v1")
    hub = MarketDataHub()
    _feed_rising(hub, n=60)
    scouts: list[ChartAnalystAgent | EntryHunterAgent] = [
        EntryHunterAgent(f"entry_{i}", hub, "1s", "ema_cross", Decimal("0.5"), lambda: 1.0, _log())
        for i in range(8)
    ]
    for s in scouts:
        await s.tick()  # all become ready on the strong uptrend
    chief = EntryChiefAgent(
        "entry_chief", scouts, hub, bus, "analysis.v1", "signals.v1", "entries", _log(),
    )
    chief.read = AnalysisRead(BULL, Decimal("0.8"), "x")  # nudge chief bias > 0
    # force a bullish division bias by setting the scouts' reads bullish
    for s in scouts:
        s.read = AnalysisRead(BULL, Decimal("0.8"), "x")
    await chief.tick()
    assert chief.buys_emitted == 1            # ONE coordinated BUY, not 8
    data = orjson.loads(sig.get_nowait())
    assert data["signal"] == "BUY" and data["source"] == "entry_chief"
    # edge-triggered: a second tick with the same consensus does NOT re-fire
    await chief.tick()
    assert chief.buys_emitted == 1


# ── DivisionChiefAgent ───────────────────────────────────────────────
async def test_division_chief_aggregates_consensus_bias() -> None:
    bus = InMemoryEventBus()
    q = bus.subscribe("analysis.v1")
    workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    hub = MarketDataHub()
    for i in range(4):
        w = ChartAnalystAgent(f"w{i}", hub, "1s", "ema_cross", "historical", _log())
        workers.append(w)
    workers[0].read = AnalysisRead(BULL, Decimal("0.8"), "x")
    workers[1].read = AnalysisRead(BULL, Decimal("0.8"), "x")
    workers[2].read = AnalysisRead(BULL, Decimal("0.8"), "x")
    workers[3].read = AnalysisRead(BEAR, Decimal("0.8"), "x")
    chief = DivisionChiefAgent("chief_x", workers, bus, "analysis.v1", "lab", _log())
    await chief.tick()
    assert chief.bias_value() == 0.5  # (3 bull - 1 bear) / 4
    msg = orjson.loads(q.get_nowait())
    assert msg["division"] == "chief_x"
    assert msg["bulls"] == 3 and msg["bears"] == 1


# ── factory + lifecycle ──────────────────────────────────────────────
def test_build_swarm_agents_has_the_full_roster() -> None:
    bus = InMemoryEventBus()
    agents = build_swarm_agents(bus, "prices", "signals.v1", "analysis.v1", _log())
    names = set(agents)
    assert sum(1 for n in names if n.startswith("hist_")) == 50
    assert sum(1 for n in names if n.startswith("live_") and n != "live_chief") == 50
    assert sum(1 for n in names if n.startswith("entry_") and n != "entry_chief") == 50
    assert {"market_data_hub", "historical_chief", "live_chief", "entry_chief"} <= names
    assert len(agents) == 1 + 3 + 150


async def test_hub_agent_consumes_prices_over_the_bus() -> None:
    bus = InMemoryEventBus()
    hub = MarketDataHub()
    agent = MarketDataHubAgent("market_data_hub", bus, "prices", hub, _log())
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    for i in range(3):
        await bus.publish("prices", b"k", orjson.dumps({"price": str(1500000 + i), "ts_ms": i * 1000}))
    await asyncio.sleep(0.1)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert hub.latest()[0] is not None
    assert "แท่งเทียน" in agent.detail
