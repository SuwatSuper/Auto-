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


class RiskLimits(BaseModel, frozen=True):
    """Risk configuration for a single account."""

    max_order_qty: Decimal
    max_position_qty: Decimal
    max_daily_loss: Money
    max_drawdown_pct: Decimal
    kill_switch: bool = False


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
) -> RiskDecision:
    """Evaluate an order against risk limits.

    Returns ALL violated reasons; approved only when the reasons tuple is empty.
    Pure function: no I/O, no side effects.
    """
    reasons: list[RiskReasonCode] = []

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

    return RiskDecision(approved=len(reasons) == 0, reasons=tuple(reasons))
