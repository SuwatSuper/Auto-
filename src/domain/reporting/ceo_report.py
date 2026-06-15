# Layer 1 — Domain (reporting/ceo_report)
"""Pure CEO-level aggregation of the trading platform's state.

Takes plain, pre-extracted facts (a snapshot of the world at one instant)
and computes the Executive Summary that the dashboard renders. No I/O,
no time, no frameworks — fully deterministic and testable.

The CEO Agent (Layer 2) is responsible for *gathering* the snapshot from
the live system; this module is responsible for *interpreting* it.
"""
from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Final


class AgentHealth(StrEnum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    WARNING = "WARNING"
    STOPPED = "STOPPED"


class DataAvailability(StrEnum):
    """Whether a piece of data was sourced from a real feed/store or is missing."""

    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"   # explicitly absent — UI must NOT fabricate


class RiskLevel(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Risk thresholds (drawdown % of peak equity). Stable contract — tests pin them.
_RISK_MODERATE: Final[Decimal] = Decimal("2.0")
_RISK_HIGH: Final[Decimal] = Decimal("5.0")
_RISK_CRITICAL: Final[Decimal] = Decimal("10.0")

# Concentration threshold — if any single symbol > this % of equity, raise concentration alert.
_CONCENTRATION_ALERT_PCT: Final[Decimal] = Decimal("40.0")


@dataclasses.dataclass(frozen=True, slots=True)
class AgentSnapshot:
    """Layer-2 hands us this for every running agent."""

    name: str
    role: str
    running: bool
    last_beat_ms: int
    msg_count: int
    stale: bool
    crashed: bool
    crash_reason: str | None
    restarts: int


@dataclasses.dataclass(frozen=True, slots=True)
class PositionSnapshot:
    symbol: str
    qty: Decimal
    entry_price: Decimal
    mark_price: Decimal

    @property
    def market_value(self) -> Decimal:
        return self.qty * self.mark_price

    @property
    def unrealized_pnl(self) -> Decimal:
        return (self.mark_price - self.entry_price) * self.qty


@dataclasses.dataclass(frozen=True, slots=True)
class SystemSnapshot:
    """Everything the CEO needs to know, in one immutable bundle.

    Use `None` for fields that genuinely cannot be retrieved (e.g. price feed
    down). DO NOT pass placeholder values — the report distinguishes between
    "zero" and "unknown".
    """

    now_ms: int
    initial_capital: Decimal
    cash: Decimal | None
    peak_equity: Decimal
    realized_pnl_today: Decimal | None
    positions: tuple[PositionSnapshot, ...]
    latest_price: Decimal | None
    feed_connected: bool
    feed_last_msg_ms: int | None
    agents: tuple[AgentSnapshot, ...]
    treasury_halted: bool
    emergency_stopped: bool


@dataclasses.dataclass(frozen=True, slots=True)
class AgentReport:
    name: str
    role: str
    health: AgentHealth
    detail: str            # short human-readable description
    restarts: int
    msg_count: int


@dataclasses.dataclass(frozen=True, slots=True)
class BusinessReport:
    """Money facts. Fields are None when the corresponding data is unavailable."""

    portfolio_value: Decimal | None
    portfolio_value_availability: DataAvailability
    cash: Decimal | None
    cash_availability: DataAvailability
    pnl_total: Decimal | None
    pnl_today: Decimal | None
    allocation_pct: tuple[tuple[str, Decimal], ...]  # symbol → % of equity (sorted)


@dataclasses.dataclass(frozen=True, slots=True)
class RiskReport:
    drawdown_pct: Decimal
    daily_loss_pct: Decimal
    risk_level: RiskLevel
    concentration_alerts: tuple[str, ...]    # symbols breaching the concentration threshold
    emergency_stopped: bool
    treasury_halted: bool


@dataclasses.dataclass(frozen=True, slots=True)
class SystemHealthReport:
    feed_connected: bool
    feed_age_ms: int | None     # ms since last feed message; None if never seen
    crashed_agents: tuple[str, ...]
    stale_agents: tuple[str, ...]
    total_agents: int
    running_agents: int


@dataclasses.dataclass(frozen=True, slots=True)
class ExecutiveSummary:
    """Top-level CEO view — composed of the four sub-reports."""

    ts_ms: int
    agents: tuple[AgentReport, ...]
    business: BusinessReport
    risk: RiskReport
    health: SystemHealthReport


# ── pure computations ───────────────────────────────────────────

def classify_agent(snap: AgentSnapshot, now_ms: int, idle_threshold_ms: int = 30_000) -> AgentReport:
    """Map a raw AgentSnapshot to one of the four health buckets."""
    if not snap.running:
        return AgentReport(
            name=snap.name, role=snap.role, health=AgentHealth.STOPPED,
            detail="agent not running", restarts=snap.restarts, msg_count=snap.msg_count,
        )
    if snap.crashed:
        return AgentReport(
            name=snap.name, role=snap.role, health=AgentHealth.WARNING,
            detail=f"crashed: {snap.crash_reason or 'unknown'}",
            restarts=snap.restarts, msg_count=snap.msg_count,
        )
    if snap.stale:
        return AgentReport(
            name=snap.name, role=snap.role, health=AgentHealth.WARNING,
            detail="heartbeat stale", restarts=snap.restarts, msg_count=snap.msg_count,
        )
    age_ms = now_ms - snap.last_beat_ms if snap.last_beat_ms > 0 else 0
    if snap.last_beat_ms == 0 or age_ms > idle_threshold_ms:
        return AgentReport(
            name=snap.name, role=snap.role, health=AgentHealth.IDLE,
            detail=f"idle for {age_ms}ms" if snap.last_beat_ms > 0 else "no heartbeat yet",
            restarts=snap.restarts, msg_count=snap.msg_count,
        )
    return AgentReport(
        name=snap.name, role=snap.role, health=AgentHealth.RUNNING,
        detail=f"last beat {age_ms}ms ago", restarts=snap.restarts, msg_count=snap.msg_count,
    )


def _portfolio_value(snap: SystemSnapshot) -> Decimal | None:
    """Cash + sum(market values). None if cash is unknown."""
    if snap.cash is None:
        return None
    mv = sum((p.market_value for p in snap.positions), Decimal("0"))
    return snap.cash + mv


def _allocation_pct(
    snap: SystemSnapshot, portfolio_value: Decimal | None
) -> tuple[tuple[str, Decimal], ...]:
    if portfolio_value is None or portfolio_value <= 0 or not snap.positions:
        return ()
    pct = tuple(
        (p.symbol, (p.market_value / portfolio_value * Decimal("100")).quantize(Decimal("0.01")))
        for p in snap.positions
    )
    return tuple(sorted(pct, key=lambda kv: kv[0]))


def _drawdown_pct(peak: Decimal, value: Decimal | None) -> Decimal:
    if value is None or peak <= 0:
        return Decimal("0")
    return ((peak - value) / peak * Decimal("100")).max(Decimal("0")).quantize(Decimal("0.01"))


def _daily_loss_pct(snap: SystemSnapshot) -> Decimal:
    if snap.realized_pnl_today is None or snap.initial_capital <= 0:
        return Decimal("0")
    if snap.realized_pnl_today >= 0:
        return Decimal("0")
    return (
        (-snap.realized_pnl_today / snap.initial_capital * Decimal("100"))
        .quantize(Decimal("0.01"))
    )


def _classify_risk(drawdown_pct: Decimal) -> RiskLevel:
    if drawdown_pct >= _RISK_CRITICAL:
        return RiskLevel.CRITICAL
    if drawdown_pct >= _RISK_HIGH:
        return RiskLevel.HIGH
    if drawdown_pct >= _RISK_MODERATE:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def _concentration_alerts(allocation: Sequence[tuple[str, Decimal]]) -> tuple[str, ...]:
    return tuple(s for s, pct in allocation if pct > _CONCENTRATION_ALERT_PCT)


def build_executive_summary(snap: SystemSnapshot) -> ExecutiveSummary:
    """Pure aggregator — the single entry point for CEO dashboard rendering."""

    agent_reports = tuple(classify_agent(a, snap.now_ms) for a in snap.agents)

    pv = _portfolio_value(snap)
    pv_avail = DataAvailability.AVAILABLE if pv is not None else DataAvailability.UNAVAILABLE
    cash_avail = (
        DataAvailability.AVAILABLE if snap.cash is not None else DataAvailability.UNAVAILABLE
    )
    pnl_total = (pv - snap.initial_capital) if pv is not None else None
    allocation = _allocation_pct(snap, pv)

    business = BusinessReport(
        portfolio_value=pv,
        portfolio_value_availability=pv_avail,
        cash=snap.cash,
        cash_availability=cash_avail,
        pnl_total=pnl_total,
        pnl_today=snap.realized_pnl_today,
        allocation_pct=allocation,
    )

    drawdown = _drawdown_pct(snap.peak_equity, pv)
    risk = RiskReport(
        drawdown_pct=drawdown,
        daily_loss_pct=_daily_loss_pct(snap),
        risk_level=_classify_risk(drawdown),
        concentration_alerts=_concentration_alerts(allocation),
        emergency_stopped=snap.emergency_stopped,
        treasury_halted=snap.treasury_halted,
    )

    crashed = tuple(a.name for a in snap.agents if a.crashed)
    stale = tuple(a.name for a in snap.agents if a.stale and not a.crashed)
    running = sum(1 for a in snap.agents if a.running and not a.crashed)
    feed_age = (
        snap.now_ms - snap.feed_last_msg_ms
        if snap.feed_last_msg_ms is not None
        else None
    )
    health = SystemHealthReport(
        feed_connected=snap.feed_connected,
        feed_age_ms=feed_age,
        crashed_agents=crashed,
        stale_agents=stale,
        total_agents=len(snap.agents),
        running_agents=running,
    )

    return ExecutiveSummary(
        ts_ms=snap.now_ms,
        agents=agent_reports,
        business=business,
        risk=risk,
        health=health,
    )
