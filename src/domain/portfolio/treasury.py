# Layer 1 — Domain (portfolio/treasury)
"""Pure money-control rules for the account-guardian agent. No I/O, Decimal only.

The treasury is the single authority over cash:
- SURVIVAL_FLOOR: never let worst-case equity fall below floor% of initial capital.
- DAILY_LOSS_LIMIT: realized daily loss beyond limit% halts new entries for the day.
- INSUFFICIENT_CASH: an order may never cost more than available cash.
No rule here can be overridden by any other component.
"""
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

_HUNDRED = Decimal("100")


class VetoReason(StrEnum):
    SURVIVAL_FLOOR = "SURVIVAL_FLOOR"
    DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
    INSUFFICIENT_CASH = "INSUFFICIENT_CASH"
    HALTED = "HALTED"


class TreasuryLimits(BaseModel, frozen=True):
    initial_capital: Decimal
    survival_floor_pct: Decimal = Decimal("70")
    max_daily_loss_pct: Decimal = Decimal("5")

    def floor_equity(self) -> Decimal:
        return self.initial_capital * self.survival_floor_pct / _HUNDRED

    def daily_loss_cap(self) -> Decimal:
        return self.initial_capital * self.max_daily_loss_pct / _HUNDRED


class TreasuryDecision(BaseModel, frozen=True):
    approved: bool
    reasons: tuple[VetoReason, ...] = ()


def review_open(
    cash: Decimal,
    equity: Decimal,
    realized_today: Decimal,
    order_cost: Decimal,
    worst_case_loss: Decimal,
    limits: TreasuryLimits,
    halted: bool,
) -> TreasuryDecision:
    """Veto chain for a proposed entry. All checks run; all reasons reported."""
    reasons: list[VetoReason] = []
    if halted:
        reasons.append(VetoReason.HALTED)
    if order_cost > cash:
        reasons.append(VetoReason.INSUFFICIENT_CASH)
    if equity - worst_case_loss < limits.floor_equity():
        reasons.append(VetoReason.SURVIVAL_FLOOR)
    if -realized_today >= limits.daily_loss_cap():
        reasons.append(VetoReason.DAILY_LOSS_LIMIT)
    return TreasuryDecision(approved=not reasons, reasons=tuple(reasons))


def should_halt(realized_today: Decimal, equity: Decimal, limits: TreasuryLimits) -> bool:
    """Standing halt condition, evaluated after every realized result."""
    if -realized_today >= limits.daily_loss_cap():
        return True
    return equity < limits.floor_equity()


def worst_case_loss(qty: Decimal, entry_price: Decimal, stop_price: Decimal, entry_fee: Decimal, exit_fee_est: Decimal) -> Decimal:
    """Worst-case loss of a bracketed long = stop distance + both fees."""
    return qty * (entry_price - stop_price) + entry_fee + exit_fee_est
