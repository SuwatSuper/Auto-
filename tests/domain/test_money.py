# Layer 1 — Domain (tests/domain/test_money)
"""Tests for Money value object and quantize helpers."""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from domain.shared.money import (
    THB,
    CurrencyMismatchError,
    Money,
    quantize_price,
    quantize_qty,
)

# --- Unit tests ---

def test_quantize_price_2dp() -> None:
    assert quantize_price(Decimal("1234.5678")) == Decimal("1234.57")


def test_quantize_qty_8dp() -> None:
    assert quantize_qty(Decimal("1.123456789")) == Decimal("1.12345679")


def test_quantize_price_idempotent() -> None:
    v = Decimal("1234.56")
    assert quantize_price(v) == v


def test_quantize_qty_idempotent() -> None:
    v = Decimal("0.12345678")
    assert quantize_qty(v) == v


def test_money_add_same_currency() -> None:
    a = Money(amount=Decimal("100.00"), currency=THB)
    b = Money(amount=Decimal("50.00"), currency=THB)
    assert (a + b).amount == Decimal("150.00")


def test_money_add_currency_mismatch_raises() -> None:
    a = Money(amount=Decimal("100"), currency="THB")
    b = Money(amount=Decimal("1"), currency="BTC")
    with pytest.raises(CurrencyMismatchError):
        _ = a + b


def test_money_sub() -> None:
    a = Money(amount=Decimal("100"), currency=THB)
    b = Money(amount=Decimal("30"), currency=THB)
    assert (a - b).amount == Decimal("70")


def test_money_neg() -> None:
    a = Money(amount=Decimal("100"), currency=THB)
    assert (-a).amount == Decimal("-100")
    assert (-a).currency == THB


def test_money_mul() -> None:
    a = Money(amount=Decimal("100"), currency=THB)
    assert a.mul(Decimal("2")).amount == Decimal("200")


def test_money_comparison() -> None:
    a = Money(amount=Decimal("100"), currency=THB)
    b = Money(amount=Decimal("50"), currency=THB)
    assert a > b
    assert b < a
    assert a >= a
    assert b <= b


def test_money_sub_currency_mismatch_raises() -> None:
    a = Money(amount=Decimal("100"), currency="THB")
    b = Money(amount=Decimal("1"), currency="BTC")
    with pytest.raises(CurrencyMismatchError):
        _ = a - b


def test_money_comparison_currency_mismatch_raises() -> None:
    a = Money(amount=Decimal("100"), currency="THB")
    b = Money(amount=Decimal("100"), currency="BTC")
    with pytest.raises(CurrencyMismatchError):
        _ = a < b
    with pytest.raises(CurrencyMismatchError):
        _ = a <= b
    with pytest.raises(CurrencyMismatchError):
        _ = a > b
    with pytest.raises(CurrencyMismatchError):
        _ = a >= b


# --- Hypothesis tests ---

_decimal_st = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
).map(quantize_price)


@given(a=_decimal_st, b=_decimal_st)
def test_add_commutative(a: Decimal, b: Decimal) -> None:
    ma = Money(amount=a, currency=THB)
    mb = Money(amount=b, currency=THB)
    assert (ma + mb).amount == (mb + ma).amount


@given(a=_decimal_st, b=_decimal_st, c=_decimal_st)
def test_add_associative(a: Decimal, b: Decimal, c: Decimal) -> None:
    ma = Money(amount=a, currency=THB)
    mb = Money(amount=b, currency=THB)
    mc = Money(amount=c, currency=THB)
    assert ((ma + mb) + mc).amount == (ma + (mb + mc)).amount


@given(a=_decimal_st, b=_decimal_st)
def test_sub_then_add_roundtrip(a: Decimal, b: Decimal) -> None:
    ma = Money(amount=a, currency=THB)
    mb = Money(amount=b, currency=THB)
    assert ((ma - mb) + mb).amount == a
