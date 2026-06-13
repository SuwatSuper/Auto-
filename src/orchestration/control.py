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
    "risk_per_trade_pct": (Decimal("0.01"), Decimal("50")),
    "stop_pct": (Decimal("0.05"), Decimal("99")),
    "take_profit_pct": (Decimal("0.05"), Decimal("1000")),
    "max_daily_loss_pct": (Decimal("0.1"), Decimal("100")),
}
_INT_FIELDS: dict[str, tuple[int, int]] = {
    "max_consecutive_losses": (1, 100),
    "max_open_positions": (1, 50),
}
_THB_FIELDS: dict[str, Decimal] = {
    # field -> minimum (>=); unbounded above
    "max_deployable_thb": Decimal("0"),
    "max_single_order_thb": Decimal("0"),
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
        if key not in _PCT_FIELDS and key not in _INT_FIELDS and key not in _THB_FIELDS:
            errors.append(f"unknown field: {key}")
            continue
        values[key] = raw

    def _dec(name: str) -> Decimal | None:
        try:
            return Decimal(str(values[name]))
        except (InvalidOperation, ValueError):
            errors.append(f"{name}: not a number ({values[name]!r})")
            return None

    out: dict[str, object] = {}

    for name, (lo, hi) in _PCT_FIELDS.items():
        d = _dec(name)
        if d is None:
            continue
        if d < lo or d > hi:
            errors.append(f"{name}: must be between {lo} and {hi} (got {d})")
        else:
            out[name] = d

    for name, (ilo, ihi) in _INT_FIELDS.items():
        try:
            iv = int(str(values[name]))
        except (ValueError, TypeError):
            errors.append(f"{name}: not an integer ({values[name]!r})")
            continue
        if iv < ilo or iv > ihi:
            errors.append(f"{name}: must be between {ilo} and {ihi} (got {iv})")
        else:
            out[name] = iv

    for name, tmin in _THB_FIELDS.items():
        d = _dec(name)
        if d is None:
            continue
        if d < tmin:
            errors.append(f"{name}: must be >= {tmin} (got {d})")
        else:
            out[name] = d

    if errors:
        return None, errors

    return (
        RiskSettings(
            risk_per_trade_pct=out["risk_per_trade_pct"],  # type: ignore[arg-type]
            stop_pct=out["stop_pct"],  # type: ignore[arg-type]
            take_profit_pct=out["take_profit_pct"],  # type: ignore[arg-type]
            max_daily_loss_pct=out["max_daily_loss_pct"],  # type: ignore[arg-type]
            max_consecutive_losses=out["max_consecutive_losses"],  # type: ignore[arg-type]
            max_open_positions=out["max_open_positions"],  # type: ignore[arg-type]
            max_deployable_thb=out["max_deployable_thb"],  # type: ignore[arg-type]
            max_single_order_thb=out["max_single_order_thb"],  # type: ignore[arg-type]
        ),
        [],
    )
