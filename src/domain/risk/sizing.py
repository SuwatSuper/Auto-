# Layer 1 — Domain (risk/sizing)
"""Pure position-sizing functions."""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

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


def adaptive_kelly_size(
    equity: Money,
    entry_price: Decimal,
    stop_price: Decimal,
    win_rate: Decimal,
    win_loss_ratio: Decimal,
    *,
    fraction: Decimal = Decimal("0.5"),
    max_notional: Decimal | None = None,
) -> Decimal:
    """Size a position from the agent's MEASURED edge — but never above the cap.

    Risk a fractional-Kelly slice of equity per trade:
        risk_amount = equity * (kelly_fraction * fraction)   # half-Kelly default
        qty         = risk_amount / |entry - stop|
    then HARD-cap the notional at ``max_notional``. This consumes the risk
    fence as a ceiling; it never moves it. When Kelly recommends more than the
    cap allows, the cap wins — the returned qty's notional is always
    ``<= max_notional``. A non-positive edge, stop distance, equity, or price
    sizes nothing (Decimal 0), so a thin/negative track record never over-bets.

    ``fraction`` (the fractional-Kelly multiplier) is clamped to [0, 1]: full
    Kelly is famously over-aggressive, so callers default to half-Kelly.
    """
    if entry_price <= 0 or stop_price <= 0 or equity.amount <= 0:
        return Decimal(0)
    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return Decimal(0)
    mult = max(Decimal(0), min(Decimal(1), fraction))
    edge = kelly_fraction(win_rate, win_loss_ratio) * mult
    if edge <= 0:
        return Decimal(0)
    qty = equity.amount * edge / stop_distance
    if max_notional is not None and max_notional > 0:
        max_qty = max_notional / entry_price
        if qty > max_qty:
            qty = max_qty
    return qty.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
