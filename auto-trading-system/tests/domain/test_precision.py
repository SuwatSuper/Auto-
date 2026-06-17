# Layer 1 — Domain (tests/domain/test_precision)
"""Tests for pure precision helpers."""
from __future__ import annotations

from decimal import Decimal

from domain.trading.precision import (
    floor_qty_to_step,
    is_dust,
    meets_min_notional,
    round_price_to_tick,
)


def test_round_price_to_tick_floors_down() -> None:
    # 30_005 with tick 100 → 30_000
    assert round_price_to_tick(Decimal("30005"), Decimal("100")) == Decimal("30000")


def test_round_price_to_tick_exact_multiple() -> None:
    assert round_price_to_tick(Decimal("30000"), Decimal("100")) == Decimal("30000")


def test_round_price_to_tick_small_remainder() -> None:
    # 30_099 with tick 100 → 30_000 (not 30_100)
    assert round_price_to_tick(Decimal("30099"), Decimal("100")) == Decimal("30000")


def test_floor_qty_to_step_basic() -> None:
    assert floor_qty_to_step(Decimal("0.06677796"), Decimal("0.00000001")) == Decimal("0.06677796")


def test_floor_qty_to_step_truncates() -> None:
    # 0.0667779962 with step 0.00000001 → 0.06677799 (floor, not round)
    result = floor_qty_to_step(Decimal("0.06677799"), Decimal("0.0001"))
    assert result == Decimal("0.0667")


def test_floor_qty_to_step_coarse() -> None:
    result = floor_qty_to_step(Decimal("1.567"), Decimal("0.5"))
    assert result == Decimal("1.5")


def test_meets_min_notional_true() -> None:
    # qty=0.001, price=1_000_000 → notional=1000 >= min=100
    assert meets_min_notional(Decimal("0.001"), Decimal("1000000"), Decimal("100")) is True


def test_meets_min_notional_false() -> None:
    assert meets_min_notional(Decimal("0.00001"), Decimal("1000"), Decimal("100")) is False


def test_meets_min_notional_exact() -> None:
    assert meets_min_notional(Decimal("1"), Decimal("100"), Decimal("100")) is True


def test_is_dust_below_threshold() -> None:
    assert is_dust(Decimal("0.000001"), Decimal("1000"), Decimal("10")) is True  # 0.001 < 10


def test_is_dust_above_threshold() -> None:
    assert is_dust(Decimal("0.1"), Decimal("1000000"), Decimal("10")) is False  # 100000 >= 10


def test_is_dust_default_threshold() -> None:
    # default threshold is 10 THB
    assert is_dust(Decimal("0.000001"), Decimal("1000")) is True  # 0.001 THB — dust
    assert is_dust(Decimal("1"), Decimal("1000")) is False         # 1000 THB — not dust
