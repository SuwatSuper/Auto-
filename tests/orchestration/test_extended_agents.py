# Tests — Phase-2 extended agents (all real, data-driven)
from __future__ import annotations

from decimal import Decimal

import orjson
import pytest
import structlog

from orchestration.agents.extended import (
    BreakoutSpecialistAgent,
    DrawdownGuardianAgent,
    FeeOptimizerAgent,
    GarbageCollectorAgent,
    MeanReversionAgent,
    TrendFollowerAgent,
    VolatilityOracleAgent,
)

_LOG = structlog.get_logger("test")


class _RecBus:
    """Records publishes; hands out throwaway queues for subscribe()."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict]] = []

    def subscribe(self, topic: str, maxsize: int = 10_000):  # type: ignore[no-untyped-def]
        import asyncio

        return asyncio.Queue()

    def unsubscribe(self, topic: str, queue) -> None:  # type: ignore[no-untyped-def]
        pass

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        self.published.append((topic, orjson.loads(value)))


async def _feed(agent, prices) -> None:  # type: ignore[no-untyped-def]
    """Drive on_price the way the real loop does (append then handle)."""
    for p in prices:
        d = Decimal(str(p))
        agent._prices.append(d)
        if len(agent._prices) > 600:
            agent._prices = agent._prices[-600:]
        await agent.on_price(d, 1_000)


@pytest.mark.asyncio
async def test_volatility_oracle_computes_real_value() -> None:
    bus = _RecBus()
    agent = VolatilityOracleAgent("vol", bus, "prices", _LOG)  # type: ignore[arg-type]
    await _feed(agent, [100, 101, 99, 103, 97, 105, 95, 108, 92] * 3)
    assert agent.vol_pct > 0
    assert "ความผันผวน" in agent.detail


@pytest.mark.asyncio
async def test_mean_reversion_emits_buy_when_oversold() -> None:
    bus = _RecBus()
    agent = MeanReversionAgent("mr", bus, "prices", "signals", _LOG)  # type: ignore[arg-type]
    # A steadily falling series drives RSI well below 30 → BUY.
    await _feed(agent, [100 - i for i in range(30)])
    signals = [m for t, m in bus.published if t == "signals"]
    assert any(s["signal"] == "BUY" for s in signals)
    assert agent.signal_count >= 1


@pytest.mark.asyncio
async def test_breakout_emits_on_new_high() -> None:
    bus = _RecBus()
    agent = BreakoutSpecialistAgent("bo", bus, "prices", "signals", _LOG)  # type: ignore[arg-type]
    await _feed(agent, list(range(100, 120)))   # 20 priors in [100,119]
    await _feed(agent, [300])                    # blows past the channel high
    signals = [m for t, m in bus.published if t == "signals"]
    assert signals and signals[-1]["signal"] == "BUY"


@pytest.mark.asyncio
async def test_trend_follower_warms_up_then_reports() -> None:
    bus = _RecBus()
    agent = TrendFollowerAgent("tf", bus, "prices", "signals", _LOG)  # type: ignore[arg-type]
    await _feed(agent, [100 + i * 0.5 for i in range(60)])
    assert "EMA" in agent.detail  # real EMA detail, no crash


class _FakeRuntime:
    def __init__(self, status: dict) -> None:
        self._status = status
        self.tripped: list[str] = []
        self.alerts: list[str] = []

    def status(self) -> dict:
        return self._status

    def trip_breaker(self, reason: str = "MANUAL") -> dict:
        self.tripped.append(reason)
        return {"ok": True, "is_open": True}

    async def send_alert(self, message: str, level: str = "info") -> bool:
        self.alerts.append(message)
        return True


@pytest.mark.asyncio
async def test_drawdown_guardian_trips_on_breach() -> None:
    rt = _FakeRuntime({"drawdown_pct": 12.0, "daily_loss_pct": 8.0, "treasury_halted": False})
    agent = DrawdownGuardianAgent("dg", rt, limit_pct=5.0, log=_LOG)  # type: ignore[arg-type]
    await agent.tick()
    assert rt.tripped and "DRAWDOWN_GUARD" in rt.tripped[0]
    assert agent.guards_triggered == 1


@pytest.mark.asyncio
async def test_drawdown_guardian_quiet_when_within_limit() -> None:
    rt = _FakeRuntime({"drawdown_pct": 1.0, "daily_loss_pct": 0.5, "treasury_halted": False})
    agent = DrawdownGuardianAgent("dg", rt, limit_pct=100.0, log=_LOG)  # type: ignore[arg-type]
    await agent.tick()
    assert not rt.tripped
    assert "เพดาน 100%" in agent.detail


@pytest.mark.asyncio
async def test_fee_optimizer_recommends_maker() -> None:
    agent = FeeOptimizerAgent("fee", maker_bps=10.0, taker_bps=25.0, log=_LOG)
    await agent.tick()
    assert "MAKER" in agent.detail


@pytest.mark.asyncio
async def test_garbage_collector_runs() -> None:
    agent = GarbageCollectorAgent("gc", _LOG)
    await agent.tick()
    assert agent.collections == 1
    assert "gc" in agent.detail


# ── self-improvement loop: real outcome grading + self-tuning ────────

def test_learner_grades_real_outcomes() -> None:
    from orchestration.agents.learning import Learner

    learner = Learner("x", "strategy")
    learner.predict("BUY", Decimal("100"), 1_000)
    learner.resolve(Decimal("102"), 1_000 + 61_000)  # matured, +2% → BUY win
    assert learner.resolved == 1 and learner.correct == 1
    assert learner.hit_rate() == 1.0
    learner.predict("SELL", Decimal("100"), 200_000)
    learner.resolve(Decimal("103"), 200_000 + 61_000)  # price rose → SELL loss
    assert learner.resolved == 2 and learner.correct == 1
    assert learner.hit_rate() == 0.5
    assert any(e.kind == "outcome" for e in learner.journal)


def test_learner_ignores_unmatured_and_ambiguous() -> None:
    from orchestration.agents.learning import Learner

    learner = Learner("x", "strategy")
    learner.predict("BUY", Decimal("100"), 1_000)
    learner.resolve(Decimal("105"), 1_000 + 10_000)  # not matured yet (<60s)
    assert learner.resolved == 0
    learner.resolve(Decimal("100.05"), 1_000 + 61_000)  # matured but <edge → ambiguous
    assert learner.resolved == 0  # never fabricated


def test_mean_reversion_self_tightens_on_losses() -> None:
    bus = _RecBus()
    agent = MeanReversionAgent("mr", bus, "prices", "signals", _LOG)  # type: ignore[arg-type]
    agent.learner.today_resolved = 8
    agent.learner.today_correct = 2  # 25% hit-rate → should tighten
    o, ob = agent._strat.oversold, agent._strat.overbought
    agent._maybe_adapt()
    assert agent._strat.oversold < o and agent._strat.overbought > ob
    assert agent.learner.adapt_count == 1
    assert any(e.kind == "adapt" for e in agent.learner.journal)


def test_trend_follower_coaching_tightens() -> None:
    bus = _RecBus()
    agent = TrendFollowerAgent("tf", bus, "prices", "signals", _LOG)  # type: ignore[arg-type]
    before = agent._min_gap_pct
    agent.coach_tighten("breakout_specialist")
    assert agent._min_gap_pct > before
    assert any(e.kind == "coach" for e in agent.learner.journal)
