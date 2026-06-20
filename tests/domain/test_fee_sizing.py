# Layer 1 — Domain (tests/domain/test_fee_sizing)
"""Tests for Bitkub fee-aware position sizing."""
from __future__ import annotations

from decimal import Decimal

from domain.risk.fee_sizing import size_with_fees


def test_golden_case() -> None:
    """Golden test — computed by hand:
    risk_amount = 100000 * 1 / 100 = 1000
    per_unit_risk = (1000000-990000) + 1000000*0.0025 + 990000*0.0025
                 = 10000 + 2500 + 2475 = 14975
    qty = 1000 / 14975 = 0.06677796... → floored to 0.06677796
    """
    result = size_with_fees(
        equity_thb=Decimal("100000"),
        risk_pct=Decimal("1"),
        entry=Decimal("1000000"),
        stop=Decimal("990000"),
        fee_rate=Decimal("0.0025"),
        qty_step=Decimal("0.00000001"),
    )
    assert result == Decimal("0.06677796")


def test_stop_equal_entry_returns_zero() -> None:
    result = size_with_fees(
        equity_thb=Decimal("100000"),
        risk_pct=Decimal("1"),
        entry=Decimal("990000"),
        stop=Decimal("990000"),
        fee_rate=Decimal("0.0025"),
    )
    assert result == Decimal(0)


def test_stop_above_entry_returns_zero() -> None:
    result = size_with_fees(
        equity_thb=Decimal("100000"),
        risk_pct=Decimal("1"),
        entry=Decimal("980000"),
        stop=Decimal("990000"),
        fee_rate=Decimal("0.0025"),
    )
    assert result == Decimal(0)


def test_zero_equity_returns_zero() -> None:
    result = size_with_fees(
        equity_thb=Decimal("0"),
        risk_pct=Decimal("1"),
        entry=Decimal("1000000"),
        stop=Decimal("990000"),
    )
    assert result == Decimal(0)


def test_zero_risk_pct_returns_zero() -> None:
    result = size_with_fees(
        equity_thb=Decimal("100000"),
        risk_pct=Decimal("0"),
        entry=Decimal("1000000"),
        stop=Decimal("990000"),
    )
    assert result == Decimal(0)


def test_qty_step_flooring_coarse() -> None:
    """With step=0.0001:
    qty = 1000/14975 = 0.06677796...
    floored to 0.0001 step: floor(667.7796...) * 0.0001 = 667 * 0.0001 = 0.0667
    """
    result = size_with_fees(
        equity_thb=Decimal("100000"),
        risk_pct=Decimal("1"),
        entry=Decimal("1000000"),
        stop=Decimal("990000"),
        fee_rate=Decimal("0.0025"),
        qty_step=Decimal("0.0001"),
    )
    assert result == Decimal("0.0667")


def test_qty_step_flooring_truncates_not_rounds() -> None:
    """Verify floor (not round) behaviour: result must be strictly below the raw qty."""
    result = size_with_fees(
        equity_thb=Decimal("100000"),
        risk_pct=Decimal("1"),
        entry=Decimal("1000000"),
        stop=Decimal("990000"),
        fee_rate=Decimal("0.0025"),
        qty_step=Decimal("0.00000001"),
    )
    # 0.06677796 * 14975 < 1000 — verify we did not round up
    assert result * Decimal("14975") < Decimal("1000")
