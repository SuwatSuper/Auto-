# Layer 2 — Orchestration (tests/orchestration/test_bus_confluence)
"""Task 1: strict bus connectivity for the entry gate.

Proves every Group-A (research_dept, probability_lab, news_intelligence) and
Group-B (timeline_analyst, execution_agent/Sim, division chiefs) department
reaches the entry gate ONLY through the Event Bus — folded into the runtime's
confluence cache — with no hidden attribute coupling, and that the integrated
reads actually gate entries when their veto is enabled.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.historical_research import HistoricalResearchAgent
from orchestration.runtime import PipelineRuntime


class _S:
    prices_topic = "prices.thb_btc.v1"
    bitkub_ws_url = ""
    persist_state = False
    initial_capital = "1000000"
    price_feed_mode = "rest"
    bitkub_api_key = None
    bitkub_api_secret = None
    max_consecutive_losses = 5
    max_open_positions = 1
    min_p_win = "0.55"
    gate_min_samples = 8
    entry_gate_enabled = True
    max_trades_per_day = 1000
    target_daily_profit_pct = "5"


def _rt(**over: object) -> PipelineRuntime:
    for k, v in over.items():
        setattr(_S, k, v)
    rt = PipelineRuntime(_S(), structlog.get_logger("t"))
    rt._ensure_bus()
    rt.agents = rt._make_agents()
    return rt


# ── research_dept now publishes a quantified, usable read ────────────
async def test_research_dept_publishes_price_percentile() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("research.v1")
    agent = HistoricalResearchAgent(bus, "prices", "research.v1", structlog.get_logger("t"))
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    # Feed 40 rising prices: the latest sits at the very TOP of its range.
    for i in range(40):
        await bus.publish("prices", b"p", orjson.dumps({"price": str(100 + i), "ts_ms": i}))
    await asyncio.sleep(0.2)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    last = None
    while not out.empty():
        last = orjson.loads(out.get_nowait())
    assert last is not None
    assert Decimal(last["price_pctl"]) == Decimal("1")        # top of the window
    assert Decimal(last["pct_from_mean"]) > 0                 # above the mean
    assert last["samples"] >= 30


async def test_research_dept_warms_up_quietly() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("research.v1")
    agent = HistoricalResearchAgent(bus, "prices", "research.v1", structlog.get_logger("t"))
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    for i in range(5):  # below the 30-sample floor
        await bus.publish("prices", b"p", orjson.dumps({"price": str(100 + i), "ts_ms": i}))
    await asyncio.sleep(0.15)
    await agent.stop()
    await asyncio.wait_for(task, timeout=2.0)
    last = None
    while not out.empty():
        last = orjson.loads(out.get_nowait())
    assert last is not None
    assert last["price_pctl"] == "-1"  # "no read" → gate stays inert


# ── the runtime confluence loop folds EVERY department topic ─────────
def test_confluence_apply_folds_all_departments() -> None:
    rt = _rt()
    rt._apply_confluence_message(
        "timeline.v1",
        {"p_win": "0.7", "p_win_samples": 30, "regime": "TREND_UP", "past_win_rate": "0.6"},
    )
    rt._apply_confluence_message("sim.results.v1", {"win_rate": "0.42", "total_trades": 12})
    rt._apply_confluence_message("probability.v1", {"prob_bull": "0.8", "rsi": "20"})
    rt._apply_confluence_message("sentiment.v1", {"sentiment_score": "-0.7"})
    rt._apply_confluence_message("research.v1", {"price_pctl": "0.99", "pct_from_mean": "5"})
    rt._apply_confluence_message("analysis.v1", {"division": "live_chief", "bias": "-0.8"})
    rt._apply_confluence_message("analysis.v1", {"division": "historical_chief", "bias": "-0.2"})

    c = rt._confluence
    assert c["p_win"] == "0.7" and c["regime"] == "TREND_UP"
    assert c["sim_win_rate"] == "0.42"
    assert c["prob_bull"] == "0.8"
    assert c["sentiment"] == "-0.7"
    assert c["price_pctl"] == "0.99"
    # swarm_bias is the mean of the two division biases
    assert abs(float(c["swarm_bias"]) - (-0.5)) < 1e-9


# ── each integrated read actually gates (when its veto is enabled) ───
def test_sentiment_from_bus_vetoes_buy() -> None:
    rt = _rt()
    # pass the win-prob floor first so only sentiment can block
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.9", "p_win_samples": 30, "regime": "RANGE"})
    rt._apply_confluence_message("sentiment.v1", {"sentiment_score": "-0.7"})  # strongly bearish news
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert not approved and "SENTIMENT_OPPOSED" in reasons


def test_swarm_consensus_from_bus_vetoes_buy() -> None:
    rt = _rt()
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.9", "p_win_samples": 30, "regime": "RANGE"})
    # both divisions strongly bearish → swarm_bias ≤ -0.5 → BUY vetoed (default ON)
    rt._apply_confluence_message("analysis.v1", {"division": "live_chief", "bias": "-0.9"})
    rt._apply_confluence_message("analysis.v1", {"division": "historical_chief", "bias": "-0.9"})
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert not approved and "SWARM_CONSENSUS_OPPOSED" in reasons


def test_probability_veto_opt_in_blocks_overbought_buy() -> None:
    rt = _rt(gate_probability_veto=True)
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.9", "p_win_samples": 30, "regime": "RANGE"})
    rt._apply_confluence_message("probability.v1", {"prob_bull": "0.10"})  # deep overbought
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert not approved and "PROBABILITY_OPPOSED" in reasons
    delattr(_S, "gate_probability_veto")


def test_research_veto_opt_in_blocks_overextended_buy() -> None:
    rt = _rt(gate_research_veto=True)
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.9", "p_win_samples": 30, "regime": "RANGE"})
    rt._apply_confluence_message("research.v1", {"price_pctl": "0.99", "pct_from_mean": "5"})
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert not approved and "PRICE_OVEREXTENDED" in reasons
    delattr(_S, "gate_research_veto")


def test_sim_veto_opt_in_blocks_losing_backtest() -> None:
    rt = _rt(gate_sim_veto=True)
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.9", "p_win_samples": 30, "regime": "RANGE"})
    rt._apply_confluence_message("sim.results.v1", {"win_rate": "0.05", "total_trades": 20})
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert not approved and "SIM_WIN_RATE_LOW" in reasons
    delattr(_S, "gate_sim_veto")


def test_neutral_confluence_passes_default_gate() -> None:
    rt = _rt()
    # Only the win-prob proven; every other bus read is neutral/absent → passes.
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.9", "p_win_samples": 30, "regime": "TREND_UP"})
    approved, reasons = rt._entry_gate({"signal": "BUY"})
    assert approved and reasons == []


# ── end-to-end: the runtime's async consumers actually run on the bus ─
async def test_confluence_and_weighting_loops_consume_the_bus() -> None:
    from tests.conftest import make_test_runtime

    rt = make_test_runtime(entry_gate_enabled=True)
    await rt.start("live")
    try:
        bus = rt.bus
        # 1) The confluence loop folds a department message off the live bus.
        for _ in range(50):
            await bus.publish(
                "timeline.v1", b"t",
                orjson.dumps({
                    "type": "TIMELINE_ANALYSIS", "p_win": "0.66",
                    "p_win_samples": 25, "regime": "TREND_UP",
                }),
            )
            if rt._confluence["p_win"] == "0.66":
                break
            await asyncio.sleep(0.03)
        assert rt._confluence["p_win"] == "0.66"
        assert rt._confluence["regime"] == "TREND_UP"

        # 2) The weighting loop routes a paper.events CLOSE back into source perf.
        for _ in range(50):
            await bus.publish(
                "paper.events.v1", b"p",
                orjson.dumps({"type": "CLOSE", "voters": ["probe_src"], "pnl_net": "12"}),
            )
            if rt._source_perf.samples("probe_src") >= 1:
                break
            await asyncio.sleep(0.03)
        assert rt._source_perf.samples("probe_src") >= 1
    finally:
        await rt.stop()


# ── status surfaces the bus-fed confluence (single source of truth) ──
def test_status_exposes_confluence_and_weighting() -> None:
    rt = _rt()
    rt._apply_confluence_message("timeline.v1", {"p_win": "0.7", "p_win_samples": 30, "regime": "TREND_UP"})
    st = rt.status()
    assert st["confluence"]["regime"] == "TREND_UP"
    assert st["confluence"]["p_win"] == "0.7"
    assert "swarm_bias" in st["confluence"]
    assert "dynamic_weighting" in st
    assert "sources" in st["dynamic_weighting"]
    # the timeline status now reads from the same cache the gate uses
    assert st["timeline"]["p_win"] == "0.7"
