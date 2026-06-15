# Layer 2 — Orchestration (control)
"""Pure validation/normalization for operator control settings.

No I/O, no infrastructure — just turns raw dashboard input into validated
Decimal/int values or a list of human-readable errors. Used by the runtime
control plane and unit-tested directly.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# field -> (min_inclusive, max_inclusive); None means unbounded on that side.
_PCT_FIELDS: dict[str, tuple[Decimal, Decimal]] = {
    # Operator can dial per-trade risk all the way to 100% (ความเสี่ยงสูงสุด 100%).
    "risk_per_trade_pct": (Decimal("0.01"), Decimal("100")),
    "stop_pct": (Decimal("0.05"), Decimal("99")),
    "take_profit_pct": (Decimal("0.05"), Decimal("1000")),
    "max_daily_loss_pct": (Decimal("0.1"), Decimal("100")),
}
# max_consecutive_losses: 0 = UNLIMITED (breaker never auto-trips on a losing
# streak — ปลดลิมิตเบรกเกอร์เป็นไม่จำกัด). Upper bound kept huge so any finite
# threshold the operator types is accepted.
_INT_FIELDS: dict[str, tuple[int, int]] = {
    "max_consecutive_losses": (0, 1_000_000),
    "max_open_positions": (1, 50),
}
# ── Hard-coded real-money ceilings (defense-in-depth, B1/T5) ───────────────
# Absolute caps enforced IN CODE. No operator setting may exceed them, so a
# fat-finger on the dashboard or a config bug can never authorise an unbounded
# real order. Operators set their own (lower) caps within these ceilings; the
# live order placement boundary (execution_agent._route_live /
# runtime._place_manual_live_bid) REJECTS + logs CRITICAL any BUY notional above
# HARD_CAP_SINGLE_ORDER_THB — it is never silently trimmed.
# Owner-set value (D2): 1,000 THB per order.
HARD_CAP_SINGLE_ORDER_THB = Decimal("1000")     # 1,000 THB per single order
HARD_CAP_DEPLOYABLE_THB = Decimal("10000")      # 10,000 THB total deployable


def order_over_hard_cap(notional_thb: object) -> str | None:
    """Return a CRITICAL rejection reason when a live BUY notional (THB) exceeds
    the hard per-order ceiling, else None.

    Enforced at the order-placement boundary so a real order can never exceed the
    ceiling — even if config/sizing somehow produced one. Protective EXITS are
    never gated here (you must always be able to close a position)."""
    try:
        value = Decimal(str(notional_thb))
    except (InvalidOperation, ValueError):
        return f"unparseable order notional {notional_thb!r} — rejected"
    if value > HARD_CAP_SINGLE_ORDER_THB:
        return (
            f"order notional {value} THB exceeds hard cap "
            f"{HARD_CAP_SINGLE_ORDER_THB} THB — rejected"
        )
    return None

_THB_FIELDS: dict[str, tuple[Decimal, Decimal]] = {
    # field -> (minimum >=, maximum <= hard cap)
    "max_deployable_thb": (Decimal("0"), HARD_CAP_DEPLOYABLE_THB),
    "max_single_order_thb": (Decimal("0"), HARD_CAP_SINGLE_ORDER_THB),
}
# Fraction fields (0..1). min_p_win is the win-probability gate the operator can
# relax/tighten live — lower → more trades, higher → fewer/stronger entries.
_FRAC_FIELDS: dict[str, tuple[Decimal, Decimal]] = {
    "min_p_win": (Decimal("0"), Decimal("1")),
}


@dataclass(frozen=True)
class RiskSettings:
    """Validated operator risk settings (all present, correct types)."""

    risk_per_trade_pct: Decimal
    stop_pct: Decimal
    take_profit_pct: Decimal
    max_daily_loss_pct: Decimal
    max_consecutive_losses: int
    max_open_positions: int
    max_deployable_thb: Decimal
    max_single_order_thb: Decimal
    # Win-probability entry gate (0..1). Default at the end so existing callers
    # that build RiskSettings with the first 8 fields keep working.
    min_p_win: Decimal = Decimal("0.55")

    def as_str_dict(self) -> dict[str, str]:
        return {
            "risk_per_trade_pct": str(self.risk_per_trade_pct),
            "stop_pct": str(self.stop_pct),
            "take_profit_pct": str(self.take_profit_pct),
            "max_daily_loss_pct": str(self.max_daily_loss_pct),
            "max_consecutive_losses": str(self.max_consecutive_losses),
            "max_open_positions": str(self.max_open_positions),
            "max_deployable_thb": str(self.max_deployable_thb),
            "max_single_order_thb": str(self.max_single_order_thb),
            "min_p_win": str(self.min_p_win),
        }


def validate_risk_settings(
    current: RiskSettings, patch: dict[str, object]
) -> tuple[RiskSettings | None, list[str]]:
    """Merge ``patch`` onto ``current`` and validate. Returns (settings, errors).

    Only keys present in ``patch`` are changed; everything else keeps its
    current value. Any invalid field collects an error and yields settings=None.
    """
    errors: list[str] = []
    values: dict[str, object] = {**current.as_str_dict()}

    for key, raw in patch.items():
        if (
            key not in _PCT_FIELDS and key not in _INT_FIELDS
            and key not in _THB_FIELDS and key not in _FRAC_FIELDS
        ):
            errors.append(f"unknown field: {key}")
            continue
        values[key] = raw

    def _dec(name: str) -> Decimal | None:
        try:
            return Decimal(str(values[name]))
        except (InvalidOperation, ValueError):
            errors.append(f"{name}: not a number ({values[name]!r})")
            return None

    # Typed accumulators so the RiskSettings construction is checked without casts.
    dec_out: dict[str, Decimal] = {}
    int_out: dict[str, int] = {}

    for name, (lo, hi) in _PCT_FIELDS.items():
        d = _dec(name)
        if d is None:
            continue
        if d < lo or d > hi:
            errors.append(f"{name}: must be between {lo} and {hi} (got {d})")
        else:
            dec_out[name] = d

    for name, (ilo, ihi) in _INT_FIELDS.items():
        try:
            iv = int(str(values[name]))
        except (ValueError, TypeError):
            errors.append(f"{name}: not an integer ({values[name]!r})")
            continue
        if iv < ilo or iv > ihi:
            errors.append(f"{name}: must be between {ilo} and {ihi} (got {iv})")
        else:
            int_out[name] = iv

    for name, (tmin, tmax) in _THB_FIELDS.items():
        d = _dec(name)
        if d is None:
            continue
        if d < tmin:
            errors.append(f"{name}: must be >= {tmin} (got {d})")
        elif d > tmax:
            errors.append(
                f"{name}: exceeds the hard cap {tmax} (got {d}) — "
                "real-money ceiling enforced in code"
            )
        else:
            dec_out[name] = d

    for name, (lo, hi) in _FRAC_FIELDS.items():
        d = _dec(name)
        if d is None:
            continue
        if d < lo or d > hi:
            errors.append(f"{name}: must be between {lo} and {hi} (got {d})")
        else:
            dec_out[name] = d

    if errors:
        return None, errors

    return (
        RiskSettings(
            risk_per_trade_pct=dec_out["risk_per_trade_pct"],
            stop_pct=dec_out["stop_pct"],
            take_profit_pct=dec_out["take_profit_pct"],
            max_daily_loss_pct=dec_out["max_daily_loss_pct"],
            max_consecutive_losses=int_out["max_consecutive_losses"],
            max_open_positions=int_out["max_open_positions"],
            max_deployable_thb=dec_out["max_deployable_thb"],
            max_single_order_thb=dec_out["max_single_order_thb"],
            min_p_win=dec_out["min_p_win"],
        ),
        [],
    )
