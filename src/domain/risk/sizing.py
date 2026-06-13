# Layer 1 — Domain (risk/sizing)
"""Pure position-sizing functions."""
from __future__ import annotations

from decimal import Decimal

from domain.shared.money import Money


def fixed_fractional(equity: Money, risk_pct: Decimal, stop_distance: Decimal) -> Decimal:
    """Compute position size using fixed-fractional sizing.

    size = (equity * risk_pct / 100) / stop_distance

    Returns 0 if stop_distance is zero or negative to avoid division by zero.
    """
    if stop_distance <= 0:
        return Decimal(0)
    risk_amount = equity.amount * risk_pct / 100
    return (risk_amount / stop_distance).quantize(Decimal("0.00000001"))


def kelly_fraction(win_rate: Decimal, win_loss_ratio: Decimal) -> Decimal:
    """Compute Kelly fraction, clamped to [0, 0.25].

    Kelly = win_rate - (1 - win_rate) / win_loss_ratio

    Returns 0 for invalid inputs (win_loss_ratio <= 0).
    """
    if win_loss_ratio <= 0:
        return Decimal(0)
    kelly = win_rate - (Decimal(1) - win_rate) / win_loss_ratio
    return max(Decimal(0), min(Decimal("0.25"), kelly))
