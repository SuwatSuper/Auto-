# Layer 1 — Domain (tests/domain/test_portfolio)
"""Portfolio engine tests: 6 golden cases + invariant hypothesis test."""
from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from domain.portfolio.engine import apply_fill, equity, unrealized_pnl
from domain.portfolio.models import Account, Position, Trade
from domain.shared.money import THB, Money


def _account(cash: str) -> Account:
    return Account(
        account_id="test",
        cash=Money(amount=Decimal(cash), currency=THB),
        realized_pnl=Money(amount=Decimal(0), currency=THB),
    )


def _trade(
    side: str,
    qty: str,
    price: str,
    fee: str = "0",
    symbol: str = "THB_BTC",
) -> Trade:
    return Trade(
        trade_id="t1",
        order_id="o1",
        symbol=symbol,
        side=side,
        qty=Decimal(qty),
        price=Decimal(price),
        fee=Money(amount=Decimal(fee), currency=THB),
        ts_ms=1_700_000_000_000,
    )


# =====================================================================
# 6 golden cases (computed by hand, shown in comments)
# =====================================================================

def test_case1_open_long() -> None:
    """Case 1: Open long 0.1 BTC @ 1,500,000 THB, fee 150 THB.
    cash_after = 1,000,000 - 150 = 999,850
    position: qty=0.1, avg_entry=1,500,000
    realized_pnl = 0
    """
    acct = _account("1000000")
    t = _trade("BUY", "0.1", "1500000", "150")
    acct2, pos = apply_fill(acct, {}, t)
    assert acct2.cash.amount == Decimal("999850")
    assert pos["THB_BTC"].qty == Decimal("0.1")
    assert pos["THB_BTC"].avg_entry_price == Decimal("1500000")
    assert acct2.realized_pnl.amount == Decimal("0")


def test_case2_add_to_long() -> None:
    """Case 2: Add 0.1 BTC @ 1,600,000 to existing 0.1 BTC @ 1,500,000, fee 160.
    new_avg = (0.1*1,500,000 + 0.1*1,600,000) / 0.2 = 310,000/0.2 = 1,550,000
    cash_after = 999,850 - 160 = 999,690
    """
    acct = _account("999850")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.1"), avg_entry_price=Decimal("1500000"))
    }
    t = _trade("BUY", "0.1", "1600000", "160")
    acct2, pos = apply_fill(acct, positions, t)
    assert pos["THB_BTC"].qty == Decimal("0.2")
    assert pos["THB_BTC"].avg_entry_price == Decimal("1550000")
    assert acct2.cash.amount == Decimal("999690")


def test_case3_partial_close_with_profit() -> None:
    """Case 3: Close 0.1 of 0.2 long @ 1,700,000 (entry=1,550,000), fee 170.
    realized = 0.1 * (1,700,000 - 1,550,000) = 0.1 * 150,000 = 15,000
    cash_after = 999,690 - 170 + 15,000 = 1,014,520
    remaining position: 0.1 @ 1,550,000
    """
    acct = _account("999690")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.2"), avg_entry_price=Decimal("1550000"))
    }
    t = _trade("SELL", "0.1", "1700000", "170")
    acct2, pos = apply_fill(acct, positions, t)
    assert acct2.cash.amount == Decimal("1014520")
    assert pos["THB_BTC"].qty == Decimal("0.1")
    assert acct2.realized_pnl.amount == Decimal("15000")


def test_case4_full_close_with_loss() -> None:
    """Case 4: Close remaining 0.1 long @ 1,400,000 (entry=1,550,000), fee 140.
    realized = 0.1 * (1,400,000 - 1,550,000) = -15,000
    cash_after = 1,014,520 - 140 + (-15,000) = 999,380
    position closed
    """
    acct = Account(
        account_id="test",
        cash=Money(amount=Decimal("1014520"), currency=THB),
        realized_pnl=Money(amount=Decimal("15000"), currency=THB),
    )
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.1"), avg_entry_price=Decimal("1550000"))
    }
    t = _trade("SELL", "0.1", "1400000", "140")
    acct2, pos = apply_fill(acct, positions, t)
    assert acct2.cash.amount == Decimal("999380")
    assert "THB_BTC" not in pos
    assert acct2.realized_pnl.amount == Decimal("0")  # 15000 + (-15000)


def test_case5_flip_long_to_short() -> None:
    """Case 5: Sell 0.2 when holding 0.1 long @ 1,500,000. Fill @ 1,600,000, fee 0.
    Close 0.1 long: realized = 0.1 * (1,600,000 - 1,500,000) = 10,000
    Open 0.1 short @ 1,600,000
    """
    acct = _account("1000000")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.1"), avg_entry_price=Decimal("1500000"))
    }
    t = _trade("SELL", "0.2", "1600000", "0")
    acct2, pos = apply_fill(acct, positions, t)
    # Should have short position of -0.1
    assert pos["THB_BTC"].qty == Decimal("-0.1")
    assert pos["THB_BTC"].avg_entry_price == Decimal("1600000")
    assert acct2.realized_pnl.amount == Decimal("10000")


def test_case6_fee_accounting() -> None:
    """Case 6: Fee is always deducted from cash regardless of direction.
    Open short 0.1 @ 1,500,000, fee=200 THB.
    cash_after = 1,000,000 - 200 = 999,800
    """
    acct = _account("1000000")
    t = _trade("SELL", "0.1", "1500000", "200")
    acct2, pos = apply_fill(acct, {}, t)
    assert acct2.cash.amount == Decimal("999800")
    assert pos["THB_BTC"].qty == Decimal("-0.1")


# =====================================================================
# unrealized_pnl
# =====================================================================

def test_unrealized_pnl_long() -> None:
    pos = Position(symbol="THB_BTC", qty=Decimal("0.1"), avg_entry_price=Decimal("1500000"))
    pnl = unrealized_pnl(pos, Decimal("1600000"))
    assert pnl.amount == Decimal("10000")


def test_unrealized_pnl_short() -> None:
    pos = Position(symbol="THB_BTC", qty=Decimal("-0.1"), avg_entry_price=Decimal("1500000"))
    pnl = unrealized_pnl(pos, Decimal("1400000"))
    assert pnl.amount == Decimal("10000")


def test_equity_with_positions() -> None:
    acct = _account("900000")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.1"), avg_entry_price=Decimal("1000000"))
    }
    eq = equity(acct, positions, {"THB_BTC": Decimal("1500000")})
    # equity = cash + unrealized = 900,000 + 0.1*(1,500,000-1,000,000) = 950,000
    assert eq.amount == Decimal("950000")


def test_unrealized_pnl_zero_qty() -> None:
    """Position with qty=0 returns 0 PnL."""
    pos = Position(symbol="THB_BTC", qty=Decimal("0"), avg_entry_price=Decimal("1500000"))
    pnl = unrealized_pnl(pos, Decimal("1600000"))
    assert pnl.amount == Decimal(0)


def test_buy_into_short_to_zero_clears_entry() -> None:
    """Buying exactly enough to flatten a short should clear entry price."""
    acct = _account("1000000")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("-0.1"), avg_entry_price=Decimal("1500000"))
    }
    # Buy 0.1 to fully close the short (no flip)
    t = _trade("BUY", "0.1", "1500000", "0")
    acct2, pos = apply_fill(acct, positions, t)
    assert "THB_BTC" not in pos


def test_sell_into_long_to_zero_clears_entry() -> None:
    """Selling exactly enough to flatten a long should clear entry price."""
    acct = _account("1000000")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.1"), avg_entry_price=Decimal("1500000"))
    }
    t = _trade("SELL", "0.1", "1500000", "0")
    acct2, pos = apply_fill(acct, positions, t)
    assert "THB_BTC" not in pos


def test_buy_covering_short_with_open() -> None:
    """Buying more than needed to cover short opens a long position."""
    acct = _account("1000000")
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("-0.1"), avg_entry_price=Decimal("1500000"))
    }
    # Buy 0.2 - covers 0.1 short, opens 0.1 long
    t = _trade("BUY", "0.2", "1600000", "0")
    acct2, pos = apply_fill(acct, positions, t)
    assert pos["THB_BTC"].qty == Decimal("0.1")
    assert pos["THB_BTC"].avg_entry_price == Decimal("1600000")


# =====================================================================
# Hypothesis invariant test
# =====================================================================

_price_st = st.decimals(
    min_value=Decimal("1000"),
    max_value=Decimal("3000000"),
    allow_nan=False,
    allow_infinity=False,
    places=2,
)
_qty_st = st.decimals(
    min_value=Decimal("0.001"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=8,
)
_side_st = st.sampled_from(["BUY", "SELL"])


@given(
    trades=st.lists(
        st.tuples(_side_st, _qty_st, _price_st),
        min_size=1,
        max_size=20,
    )
)
@hyp_settings(max_examples=100)
def test_portfolio_invariant(trades: list[tuple[str, Decimal, Decimal]]) -> None:
    """Invariant: cash_start - total_fees + total_realized_pnl == cash_now + open_cost_basis.

    Holds regardless of trade sequence.
    """
    initial_cash = Decimal("10000000")
    acct = Account(
        account_id="hyp",
        cash=Money(amount=initial_cash, currency=THB),
        realized_pnl=Money(amount=Decimal(0), currency=THB),
    )
    positions: dict[str, Position] = {}
    total_fees = Decimal(0)
    symbol = "THB_BTC"

    for side, qty, price in trades:
        fee_amount = (qty * price * Decimal("0.0025")).quantize(Decimal("0.01"))
        total_fees += fee_amount
        t = Trade(
            trade_id="t",
            order_id="o",
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            fee=Money(amount=fee_amount, currency=THB),
            ts_ms=1_700_000_000_000,
        )
        acct, positions = apply_fill(acct, positions, t)

    # Invariant (paper trading): cash changes ONLY from fees and realized PnL.
    # cash_now = initial_cash - total_fees + total_realized_pnl
    expected_cash = initial_cash - total_fees + acct.realized_pnl.amount
    diff = abs(acct.cash.amount - expected_cash)
    assert diff < Decimal("0.01"), (
        f"Cash invariant violated: cash={acct.cash.amount} "
        f"expected={expected_cash} diff={diff}"
    )
