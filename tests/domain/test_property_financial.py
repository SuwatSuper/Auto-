# Layer 1 — Domain (tests/domain/test_property_financial)
"""Property-based tests (hypothesis) pinning financial invariants that must hold
for ALL inputs — not just the hand-picked golden cases. These guard the money
core against regressions in arithmetic, fees, slippage and position sizing."""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from domain.shared.money import BTC, THB, CurrencyMismatchError, Money
from domain.trading.paper import fee_for, size_order, slip_buy, slip_sell

# Bounded, finite Decimal strategies (no NaN/Infinity, sane magnitudes).
_amount = st.decimals(
    min_value=Decimal("-1000000000"), max_value=Decimal("1000000000"),
    allow_nan=False, allow_infinity=False, places=2,
)
_positive = st.decimals(
    min_value=Decimal("0.01"), max_value=Decimal("100000000"),
    allow_nan=False, allow_infinity=False, places=2,
)
_bps = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("1000"),
    allow_nan=False, allow_infinity=False, places=2,
)
_PROP = settings(deadline=None, max_examples=200)


# ── Money: a currency-safe additive group ────────────────────────────
@_PROP
@given(a=_amount, b=_amount, c=_amount)
def test_money_addition_is_associative(a: Decimal, b: Decimal, c: Decimal) -> None:
    A, B, C = (Money(amount=x, currency=THB) for x in (a, b, c))
    assert (A + B) + C == A + (B + C)


@_PROP
@given(a=_amount, b=_amount)
def test_money_addition_is_commutative(a: Decimal, b: Decimal) -> None:
    A, B = Money(amount=a, currency=THB), Money(amount=b, currency=THB)
    assert A + B == B + A


@_PROP
@given(a=_amount)
def test_money_sub_is_add_inverse(a: Decimal) -> None:
    A = Money(amount=a, currency=THB)
    zero = Money(amount=Decimal("0"), currency=THB)
    assert zero == A - A
    assert zero == A + (-A)


@_PROP
@given(a=_amount, b=_amount)
def test_money_cross_currency_is_rejected(a: Decimal, b: Decimal) -> None:
    thb, btc = Money(amount=a, currency=THB), Money(amount=b, currency=BTC)
    with pytest.raises(CurrencyMismatchError):
        _ = thb + btc
    with pytest.raises(CurrencyMismatchError):
        _ = thb < btc


# ── Fees: non-negative and monotonic in notional ────────────────────
@_PROP
@given(notional=_positive, fee=_bps)
def test_fee_is_non_negative(notional: Decimal, fee: Decimal) -> None:
    assert fee_for(notional, fee) >= 0


@_PROP
@given(n1=_positive, n2=_positive, fee=_bps)
def test_fee_is_monotonic_in_notional(n1: Decimal, n2: Decimal, fee: Decimal) -> None:
    lo, hi = sorted((n1, n2))
    assert fee_for(lo, fee) <= fee_for(hi, fee)


# ── Slippage: buy never below mark, sell never above ─────────────────
@_PROP
@given(price=_positive, slip=_bps)
def test_slippage_brackets_the_price(price: Decimal, slip: Decimal) -> None:
    assert slip_buy(price, slip) >= price >= slip_sell(price, slip)


# ── Sizing: never spends more than cash, never negative ──────────────
@_PROP
@given(
    cash=st.decimals(min_value=Decimal("100"), max_value=Decimal("100000000"),
                     allow_nan=False, allow_infinity=False, places=2),
    entry=st.decimals(min_value=Decimal("1"), max_value=Decimal("10000000"),
                      allow_nan=False, allow_infinity=False, places=2),
    stop_frac=st.decimals(min_value=Decimal("0.001"), max_value=Decimal("0.5"),
                          allow_nan=False, allow_infinity=False, places=4),
    risk=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100"),
                     allow_nan=False, allow_infinity=False, places=2),
    fee=_bps, slip=_bps,
)
def test_size_order_never_exceeds_cash(
    cash: Decimal, entry: Decimal, stop_frac: Decimal,
    risk: Decimal, fee: Decimal, slip: Decimal,
) -> None:
    stop = entry * (Decimal("1") - stop_frac)
    assume(stop > 0)
    qty = size_order(cash, entry, stop, risk, fee, slip)
    assert qty >= 0
    # the FULL cost (fill price + taker fee) must fit inside cash — no leverage
    fill = slip_buy(entry, slip)
    cost = qty * fill * (Decimal("1") + fee / Decimal("10000"))
    assert cost <= cash
