# Layer 2 — Orchestration (tests/orchestration/test_dynamic_weighting)
"""Task 2: non-LLM self-learning via dynamic vote-weighting.

paper.events Win/Loss is routed back to the decision agents; each source's vote
weight in the Supreme commander is adjusted from its measured win-rate (>55%
boosted, <45% muted). Proven here end-to-end: Supreme weights, the paper trader's
voter provenance, and the runtime feedback loop that closes the loop.
"""
from __future__ import annotations

import asyncio
import contextlib
from decimal import Decimal

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus
from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
from orchestration.agents.supreme import MAX_WEIGHT, MUTED_WEIGHT, SupremeAgent
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.runtime import PipelineRuntime

D = Decimal
_LOG = structlog.get_logger("test")


# ── Supreme weighted consensus ───────────────────────────────────────
async def _run_supreme(agent: SupremeAgent, msgs: list[dict], out: asyncio.Queue) -> list[dict]:
    task = asyncio.create_task(agent.start())
    await asyncio.sleep(0.05)
    for m in msgs:
        await agent._bus.publish("in", b"k", orjson.dumps(m))  # type: ignore[attr-defined]
        await asyncio.sleep(0.03)
    await asyncio.sleep(0.05)
    await agent.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    decisions = []
    while not out.empty():
        decisions.append(orjson.loads(out.get_nowait()))
    return decisions


async def test_muted_source_vote_is_ignored() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("out")
    agent = SupremeAgent(bus, "in", "out", _LOG, window_s=8.0, buy_votes=1, sell_votes=1)
    agent.set_source_weight("loser", 0.0)  # win-rate < 45% → muted
    decisions = await _run_supreme(
        agent, [{"signal": "BUY", "source": "loser", "ts_ms": 1}], out
    )
    # A muted source's lone BUY carries zero weight → never executes.
    assert decisions[-1]["decision"] == "OBSERVE"


async def test_boosted_source_drives_execution_and_reports_voters() -> None:
    bus = InMemoryEventBus()
    out = bus.subscribe("out")
    agent = SupremeAgent(bus, "in", "out", _LOG, window_s=8.0, buy_votes=2, sell_votes=2)
    agent.set_source_weight("star", 2.0)  # one proven source meets a 2-vote floor alone
    decisions = await _run_supreme(
        agent, [{"signal": "BUY", "source": "star", "ts_ms": 1}], out
    )
    assert decisions[-1]["decision"] == "EXECUTE" and decisions[-1]["signal"] == "BUY"
    assert decisions[-1]["voters"] == ["star"]


def test_weight_setters_clamp() -> None:
    bus = InMemoryEventBus()
    agent = SupremeAgent(bus, "in", "out", _LOG)
    agent.set_source_weight("a", 99.0)
    agent.update_weights({"b": -5.0})
    assert agent.weight_of("a") == MAX_WEIGHT
    assert agent.weight_of("b") == MUTED_WEIGHT
    assert agent.weight_of("never_set") == 1.0
    assert agent.weights_snapshot() == {"a": MAX_WEIGHT, "b": MUTED_WEIGHT}


# ── paper trader carries the voter provenance onto FILL + CLOSE ──────
async def test_paper_trader_propagates_voters_to_events() -> None:
    from domain.portfolio.treasury import TreasuryLimits
    bus = InMemoryEventBus()
    events = bus.subscribe("paper.events.v1")
    treasury = TreasuryAgent(
        bus, "treasury.v1", _LOG, TreasuryLimits(initial_capital=D("100000")), None
    )
    trader = PaperTraderAgent(
        bus, "decisions.v1", "prices.v1", "paper.events.v1", _LOG, treasury, TradeParams(), None
    )
    task = asyncio.create_task(trader.start())
    await asyncio.sleep(0.05)
    # establish a mark price
    deadline = asyncio.get_event_loop().time() + 3.0
    while trader.mark_price is None and asyncio.get_event_loop().time() < deadline:
        await bus.publish("prices.v1", b"p", orjson.dumps({"price": "1000000", "ts_ms": 1}))
        await asyncio.sleep(0.03)
    # a BUY decision carrying Supreme voters + decision id
    await bus.publish(
        "decisions.v1", b"d",
        orjson.dumps({
            "decision": "EXECUTE", "signal": "BUY",
            "voters": ["entry_chief", "market_analyst"], "decision_id": "sup-1",
        }),
    )
    while trader.entries_opened == 0 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.03)
    assert trader.entries_opened == 1
    await trader.manual_close(D("1010000"))  # close in profit
    await asyncio.sleep(0.05)
    await trader.stop()
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    fills = []
    closes = []
    while not events.empty():
        ev = orjson.loads(events.get_nowait())
        if ev.get("type") == "FILL":
            fills.append(ev)
        elif ev.get("type") == "CLOSE":
            closes.append(ev)
    assert fills and fills[-1]["voters"] == ["entry_chief", "market_analyst"]
    assert closes and closes[-1]["voters"] == ["entry_chief", "market_analyst"]
    assert closes[-1]["decision_id"] == "sup-1"


# ── runtime feedback loop: paper.events → source weights → Supreme ───
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
    entry_gate_enabled = True


def _rt() -> PipelineRuntime:
    rt = PipelineRuntime(_S(), structlog.get_logger("t"))
    rt._ensure_bus()
    rt.agents = rt._make_agents()
    return rt


def test_losing_source_gets_muted_via_feedback() -> None:
    rt = _rt()
    supreme = rt.agents["supreme_commander"]
    # 6 losing trades attributed to "bad_bot" → win-rate 0% → muted in Supreme.
    for i in range(6):
        rt._record_trade_outcome({"type": "CLOSE", "voters": ["bad_bot"], "pnl_net": "-50", "decision_id": f"d{i}"})
    assert supreme.weight_of("bad_bot") == MUTED_WEIGHT  # type: ignore[attr-defined]
    assert rt._source_perf.win_rate("bad_bot") == 0.0


def test_winning_source_gets_boosted_via_feedback() -> None:
    rt = _rt()
    supreme = rt.agents["supreme_commander"]
    for i in range(6):
        rt._record_trade_outcome({"type": "CLOSE", "voters": ["good_bot"], "pnl_net": "100", "decision_id": f"d{i}"})
    assert supreme.weight_of("good_bot") > 1.0  # type: ignore[attr-defined]


def test_feedback_ignores_non_close_and_voterless_events() -> None:
    rt = _rt()
    rt._record_trade_outcome({"type": "FILL", "voters": ["x"]})       # not a CLOSE
    rt._record_trade_outcome({"type": "CLOSE", "pnl_net": "10"})       # no voters
    assert rt._source_perf.weights() == {}


# ── learned weights survive a restart (durable self-learning) ────────
async def test_learned_weights_persist_and_restore() -> None:
    from tests.conftest import make_test_runtime

    rt = make_test_runtime()
    rt._ensure_bus()
    rt.agents = rt._make_agents()
    for i in range(6):  # "bad" loses every trade → muted
        rt._record_trade_outcome({"type": "CLOSE", "voters": ["bad"], "pnl_net": "-1", "decision_id": f"d{i}"})
    rt._swarm_meta.record("ema_cross", "TREND_UP", won=True)
    await rt._persist_memories()

    # A fresh runtime sharing the SAME state store reloads what was learned.
    rt2 = PipelineRuntime(rt.settings, structlog.get_logger("t2"), deps=rt._deps)
    rt2._ensure_bus()
    rt2.agents = rt2._make_agents()
    await rt2._restore_memories()
    assert rt2._source_perf.win_rate("bad") == 0.0
    assert rt2.agents["supreme_commander"].weight_of("bad") == MUTED_WEIGHT  # type: ignore[attr-defined]
    assert rt2._swarm_meta.stats[("ema_cross", "TREND_UP")].total == 1
