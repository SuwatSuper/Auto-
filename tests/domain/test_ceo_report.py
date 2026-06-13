"""Tests for Layer-1 domain.reporting.ceo_report — pure, no I/O."""
from __future__ import annotations

from decimal import Decimal

from domain.reporting.ceo_report import (
    AgentHealth,
    AgentSnapshot,
    DataAvailability,
    PositionSnapshot,
    RiskLevel,
    SystemSnapshot,
    build_executive_summary,
    classify_agent,
)


def _agent(
    name: str = "supreme",
    *,
    running: bool = True,
    last_beat_ms: int = 0,
    crashed: bool = False,
    stale: bool = False,
    crash_reason: str | None = None,
    restarts: int = 0,
) -> AgentSnapshot:
    return AgentSnapshot(
        name=name, role=f"{name}-role", running=running,
        last_beat_ms=last_beat_ms, msg_count=10, stale=stale,
        crashed=crashed, crash_reason=crash_reason, restarts=restarts,
    )


def _snap(
    *,
    cash: Decimal | None = Decimal("1000"),
    positions: tuple[PositionSnapshot, ...] = (),
    initial_capital: Decimal = Decimal("1000"),
    peak_equity: Decimal = Decimal("1000"),
    realized_pnl_today: Decimal | None = Decimal("0"),
    latest_price: Decimal | None = Decimal("1500000"),
    feed_connected: bool = True,
    feed_last_msg_ms: int | None = 1_000,
    agents: tuple[AgentSnapshot, ...] = (),
    treasury_halted: bool = False,
    emergency_stopped: bool = False,
    now_ms: int = 1_100,
) -> SystemSnapshot:
    return SystemSnapshot(
        now_ms=now_ms,
        initial_capital=initial_capital,
        cash=cash,
        peak_equity=peak_equity,
        realized_pnl_today=realized_pnl_today,
        positions=positions,
        latest_price=latest_price,
        feed_connected=feed_connected,
        feed_last_msg_ms=feed_last_msg_ms,
        agents=agents,
        treasury_halted=treasury_halted,
        emergency_stopped=emergency_stopped,
    )


# ── classify_agent ───────────────────────────────────────────────

def test_classify_running_agent() -> None:
    a = _agent(last_beat_ms=1_050)
    r = classify_agent(a, now_ms=1_100)
    assert r.health == AgentHealth.RUNNING


def test_classify_stopped_agent() -> None:
    a = _agent(running=False)
    assert classify_agent(a, now_ms=1_100).health == AgentHealth.STOPPED


def test_classify_crashed_agent_includes_reason() -> None:
    a = _agent(crashed=True, crash_reason="ZeroDivisionError")
    r = classify_agent(a, now_ms=1_100)
    assert r.health == AgentHealth.WARNING
    assert "ZeroDivisionError" in r.detail


def test_classify_stale_agent() -> None:
    r = classify_agent(_agent(stale=True), now_ms=1_100)
    assert r.health == AgentHealth.WARNING
    assert "stale" in r.detail


def test_classify_idle_when_no_heartbeat_yet() -> None:
    r = classify_agent(_agent(last_beat_ms=0), now_ms=1_100)
    assert r.health == AgentHealth.IDLE


def test_classify_idle_when_heartbeat_too_old() -> None:
    a = _agent(last_beat_ms=1_000)
    r = classify_agent(a, now_ms=100_000, idle_threshold_ms=30_000)
    assert r.health == AgentHealth.IDLE


# ── BusinessReport ───────────────────────────────────────────────

def test_portfolio_value_unavailable_when_cash_missing() -> None:
    s = _snap(cash=None)
    summary = build_executive_summary(s)
    assert summary.business.portfolio_value is None
    assert summary.business.portfolio_value_availability == DataAvailability.UNAVAILABLE
    assert summary.business.cash_availability == DataAvailability.UNAVAILABLE
    assert summary.business.pnl_total is None


def test_portfolio_value_sums_cash_plus_positions() -> None:
    positions = (
        PositionSnapshot(symbol="BTC", qty=Decimal("0.001"),
                         entry_price=Decimal("1500000"), mark_price=Decimal("1600000")),
    )
    s = _snap(cash=Decimal("500"), positions=positions, initial_capital=Decimal("1000"))
    summary = build_executive_summary(s)
    # 500 + 0.001*1_600_000 = 500 + 1600 = 2100
    assert summary.business.portfolio_value == Decimal("2100.000")
    # pnl_total = 2100 - 1000 = 1100
    assert summary.business.pnl_total == Decimal("1100.000")


def test_allocation_percentage_sums_correctly() -> None:
    positions = (
        PositionSnapshot(symbol="BTC", qty=Decimal("1"),
                         entry_price=Decimal("100"), mark_price=Decimal("100")),
        PositionSnapshot(symbol="ETH", qty=Decimal("1"),
                         entry_price=Decimal("100"), mark_price=Decimal("100")),
    )
    # cash=0, positions = 100 + 100 = 200, total = 200 → 50% each
    s = _snap(cash=Decimal("0"), positions=positions,
              initial_capital=Decimal("200"), peak_equity=Decimal("200"))
    summary = build_executive_summary(s)
    assert dict(summary.business.allocation_pct) == {
        "BTC": Decimal("50.00"),
        "ETH": Decimal("50.00"),
    }


def test_allocation_empty_when_no_positions() -> None:
    summary = build_executive_summary(_snap())
    assert summary.business.allocation_pct == ()


# ── RiskReport ───────────────────────────────────────────────────

def test_risk_low_when_no_drawdown() -> None:
    summary = build_executive_summary(_snap())
    assert summary.risk.risk_level == RiskLevel.LOW
    assert summary.risk.drawdown_pct == Decimal("0.00")


def test_risk_moderate_at_2pct_drawdown() -> None:
    s = _snap(cash=Decimal("980"), peak_equity=Decimal("1000"))
    summary = build_executive_summary(s)
    assert summary.risk.drawdown_pct == Decimal("2.00")
    assert summary.risk.risk_level == RiskLevel.MODERATE


def test_risk_high_at_5pct_drawdown() -> None:
    s = _snap(cash=Decimal("950"), peak_equity=Decimal("1000"))
    assert build_executive_summary(s).risk.risk_level == RiskLevel.HIGH


def test_risk_critical_at_10pct_drawdown() -> None:
    s = _snap(cash=Decimal("900"), peak_equity=Decimal("1000"))
    assert build_executive_summary(s).risk.risk_level == RiskLevel.CRITICAL


def test_concentration_alert_above_40_pct() -> None:
    positions = (
        PositionSnapshot(symbol="BTC", qty=Decimal("1"),
                         entry_price=Decimal("100"), mark_price=Decimal("60")),
        PositionSnapshot(symbol="ETH", qty=Decimal("1"),
                         entry_price=Decimal("100"), mark_price=Decimal("40")),
    )
    # cash=0, BTC=60 (60%), ETH=40 (40%) — BTC breaches, ETH does not
    s = _snap(cash=Decimal("0"), positions=positions,
              initial_capital=Decimal("100"), peak_equity=Decimal("100"))
    summary = build_executive_summary(s)
    assert summary.risk.concentration_alerts == ("BTC",)


def test_daily_loss_pct_zero_when_pnl_positive() -> None:
    s = _snap(realized_pnl_today=Decimal("50"))
    assert build_executive_summary(s).risk.daily_loss_pct == Decimal("0")


def test_daily_loss_pct_computed_when_pnl_negative() -> None:
    s = _snap(realized_pnl_today=Decimal("-30"), initial_capital=Decimal("1000"))
    # 30/1000 = 3.00%
    assert build_executive_summary(s).risk.daily_loss_pct == Decimal("3.00")


def test_emergency_and_halt_flags_propagate() -> None:
    s = _snap(treasury_halted=True, emergency_stopped=True)
    r = build_executive_summary(s).risk
    assert r.emergency_stopped is True
    assert r.treasury_halted is True


# ── SystemHealthReport ───────────────────────────────────────────

def test_health_counts_running_excludes_crashed() -> None:
    agents = (
        _agent("a", running=True),
        _agent("b", running=True, crashed=True, crash_reason="x"),
        _agent("c", running=False),
    )
    summary = build_executive_summary(_snap(agents=agents))
    assert summary.health.total_agents == 3
    assert summary.health.running_agents == 1
    assert summary.health.crashed_agents == ("b",)


def test_health_lists_stale_excluding_crashed() -> None:
    agents = (
        _agent("a", running=True, stale=True),
        _agent("b", running=True, stale=True, crashed=True, crash_reason="x"),
    )
    summary = build_executive_summary(_snap(agents=agents))
    assert summary.health.stale_agents == ("a",)


def test_health_feed_age_ms_when_known() -> None:
    s = _snap(now_ms=2_000, feed_last_msg_ms=1_500)
    assert build_executive_summary(s).health.feed_age_ms == 500


def test_health_feed_age_none_when_never_seen() -> None:
    s = _snap(feed_connected=False, feed_last_msg_ms=None)
    assert build_executive_summary(s).health.feed_age_ms is None
    assert build_executive_summary(s).health.feed_connected is False


# ── Determinism ──────────────────────────────────────────────────

def test_summary_is_deterministic() -> None:
    snap = _snap()
    a = build_executive_summary(snap)
    b = build_executive_summary(snap)
    assert a == b
