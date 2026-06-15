# Layer 1 — Domain (trading/precision)
"""Pure Decimal precision helpers for price ticks and quantity steps."""
from __future__ import annotations

from decimal import Decimal


def round_price_to_tick(price: Decimal, tick: Decimal) -> Decimal:
    """Floor price DOWN to the nearest tick increment."""
    return (price // tick) * tick


def floor_qty_to_step(qty: Decimal, step: Decimal) -> Decimal:
    """Floor quantity DOWN to the nearest step increment."""
    return (qty // step) * step


def meets_min_notional(qty: Decimal, price: Decimal, min_thb: Decimal) -> bool:
    """Return True when qty * price >= min_thb (order meets the minimum notional)."""
    return qty * price >= min_thb


def is_dust(
    qty: Decimal,
    price: Decimal,
    dust_threshold_thb: Decimal = Decimal("10"),
) -> bool:
    """Return True when qty * price is below the dust threshold (not worth trading)."""
    return qty * price < dust_threshold_thb
