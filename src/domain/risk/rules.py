# Layer 1 — Domain (risk/rules)
"""Pure risk evaluation: checks order against risk limits."""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from domain.portfolio.models import Account, Position
from domain.shared.money import Money
from domain.trading.orders import Order


class RiskReasonCode(StrEnum):
    """Machine-readable risk rejection codes."""

    KILL_SWITCH_ACTIVE = "KILL_SWITCH_ACTIVE"
    ORDER_QTY_EXCEEDED = "ORDER_QTY_EXCEEDED"
    POSITION_QTY_EXCEEDED = "POSITION_QTY_EXCEEDED"
    DAILY_LOSS_EXCEEDED = "DAILY_LOSS_EXCEEDED"
    DRAWDOWN_EXCEEDED = "DRAWDOWN_EXCEEDED"
    WEEKLY_LOSS_EXCEEDED = "WEEKLY_LOSS_EXCEEDED"
    MONTHLY_LOSS_EXCEEDED = "MONTHLY_LOSS_EXCEEDED"
    CONSECUTIVE_LOSSES_EXCEEDED = "CONSECUTIVE_LOSSES_EXCEEDED"
    MAX_OPEN_POSITIONS_EXCEEDED = "MAX_OPEN_POSITIONS_EXCEEDED"
    NOTIONAL_EXPOSURE_EXCEEDED = "NOTIONAL_EXPOSURE_EXCEEDED"
    CIRCUIT_BREAKER_OPEN = "CIRCUIT_BREAKER_OPEN"
    STARTUP_NOT_RECONCILED = "STARTUP_NOT_RECONCILED"


class RiskLimits(BaseModel, frozen=True):
    """Risk configuration for a single account."""

    max_order_qty: Decimal
    max_position_qty: Decimal
    max_daily_loss: Money
    max_drawdown_pct: Decimal
    kill_switch: bool = False
    max_weekly_loss: Money | None = None
    max_monthly_loss: Money | None = None
    max_consecutive_losses: int = 5
    max_open_positions: int = 3
    max_notional_exposure_pct: Decimal = Decimal("50")


class RiskDecision(BaseModel, frozen=True):
    """Result of a risk evaluation."""

    approved: bool
    reasons: tuple[RiskReasonCode, ...]


def evaluate(
    order: Order,
    account: Account,
    positions: dict[str, Position],
    limits: RiskLimits,
    daily_pnl: Money,
    peak_equity: Money,
    current_equity: Money,
    *,
    weekly_pnl: Money | None = None,
    monthly_pnl: Money | None = None,
    consecutive_losses: int = 0,
    open_positions_count: int = 0,
    total_notional_exposure: Money | None = None,
    circuit_breaker_open: bool = False,
) -> RiskDecision:
    """Evaluate an order against risk limits.

    Returns ALL violated reasons; approved only when the reasons tuple is empty.
    Pure function: no I/O, no side effects.
    A None input for optional money params skips that check.
    """
    reasons: list[RiskReasonCode] = []

    if circuit_breaker_open:
        reasons.append(RiskReasonCode.CIRCUIT_BREAKER_OPEN)

    if limits.kill_switch:
        reasons.append(RiskReasonCode.KILL_SWITCH_ACTIVE)

    if order.qty > limits.max_order_qty:
        reasons.append(RiskReasonCode.ORDER_QTY_EXCEEDED)

    current_pos = positions.get(order.symbol)
    current_qty = current_pos.qty if current_pos else Decimal(0)
    projected_qty = abs(current_qty + order.qty)
    if projected_qty > limits.max_position_qty:
        reasons.append(RiskReasonCode.POSITION_QTY_EXCEEDED)

    if daily_pnl < -limits.max_daily_loss:
        reasons.append(RiskReasonCode.DAILY_LOSS_EXCEEDED)

    if peak_equity.amount > 0:
        drawdown_pct = (peak_equity.amount - current_equity.amount) / peak_equity.amount * 100
        if drawdown_pct > limits.max_drawdown_pct:
            reasons.append(RiskReasonCode.DRAWDOWN_EXCEEDED)

    if weekly_pnl is not None and limits.max_weekly_loss is not None and weekly_pnl < -limits.max_weekly_loss:
        reasons.append(RiskReasonCode.WEEKLY_LOSS_EXCEEDED)

    if monthly_pnl is not None and limits.max_monthly_loss is not None and monthly_pnl < -limits.max_monthly_loss:
        reasons.append(RiskReasonCode.MONTHLY_LOSS_EXCEEDED)

    # 0 = UNLIMITED, matching the CircuitBreaker / config / control convention
    # (consecutive_losses starts at 0, so a naive ``0 >= 0`` would reject EVERY
    # order when the threshold is set to "unlimited"). M2.
    if limits.max_consecutive_losses > 0 and consecutive_losses >= limits.max_consecutive_losses:
        reasons.append(RiskReasonCode.CONSECUTIVE_LOSSES_EXCEEDED)

    # ``>=`` so the cap is binding (was ``>``, which silently permitted cap+1),
    # consistent with the live ExecutionAgent open-position rail. L1.
    if open_positions_count >= limits.max_open_positions:
        reasons.append(RiskReasonCode.MAX_OPEN_POSITIONS_EXCEEDED)

    if total_notional_exposure is not None and current_equity.amount > 0:
        exposure_pct = (
            total_notional_exposure.amount / current_equity.amount * Decimal("100")
        )
        if exposure_pct > limits.max_notional_exposure_pct:
            reasons.append(RiskReasonCode.NOTIONAL_EXPOSURE_EXCEEDED)

    return RiskDecision(approved=len(reasons) == 0, reasons=tuple(reasons))
