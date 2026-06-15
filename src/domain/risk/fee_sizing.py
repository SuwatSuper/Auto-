# Layer 1 — Domain (risk/fee_sizing)
"""Bitkub fee-aware position sizing — pure Decimal arithmetic, long-only spot."""
from __future__ import annotations

from decimal import Decimal


def size_with_fees(
    equity_thb: Decimal,
    risk_pct: Decimal,
    entry: Decimal,
    stop: Decimal,
    fee_rate: Decimal = Decimal("0.0025"),
    qty_step: Decimal = Decimal("0.00000001"),
) -> Decimal:
    """Compute the maximum position size after accounting for taker fees.

    Both entry and exit legs pay the fee, so per-unit risk includes fee cost on
    both sides.  The result is floored (ROUND_DOWN) to the nearest qty_step.

    Returns Decimal(0) when any input is non-positive, when entry <= stop,
    or when the floored quantity is zero.
    """
    if (
        entry <= stop
        or equity_thb <= Decimal(0)
        or risk_pct <= Decimal(0)
        or entry <= Decimal(0)
        or stop <= Decimal(0)
        or fee_rate <= Decimal(0)
        or qty_step <= Decimal(0)
    ):
        return Decimal(0)

    risk_amount = equity_thb * risk_pct / Decimal("100")
    per_unit_risk = (entry - stop) + entry * fee_rate + stop * fee_rate

    if per_unit_risk <= Decimal(0):
        return Decimal(0)

    qty = risk_amount / per_unit_risk
    # Floor to qty_step using integer-multiple truncation
    qty_floored = (qty // qty_step) * qty_step

    if qty_floored <= Decimal(0):
        return Decimal(0)

    return qty_floored
