# Layer 1 — Domain (tests/domain/test_risk)
"""Tests for risk rules and sizing functions."""
from __future__ import annotations

from decimal import Decimal

from domain.portfolio.models import Account, Position
from domain.risk.rules import (
    RiskLimits,
    RiskReasonCode,
    evaluate,
)
from domain.risk.sizing import fixed_fractional, kelly_fraction
from domain.shared.money import THB, Money
from domain.trading.orders import Order, OrderStatus, Side


def _order(qty: str = "0.01") -> Order:
    return Order(
        order_id="o1",
        symbol="THB_BTC",
        side=Side.BUY,
        qty=Decimal(qty),
        limit_price=None,
        status=OrderStatus.NEW,
        created_ms=1_700_000_000_000,
    )


def _account(cash: str = "1000000") -> Account:
    return Account(
        account_id="test",
        cash=Money(amount=Decimal(cash), currency=THB),
        realized_pnl=Money(amount=Decimal(0), currency=THB),
    )


def _limits(**kwargs: object) -> RiskLimits:
    defaults: dict[str, object] = {
        "max_order_qty": Decimal("1"),
        "max_position_qty": Decimal("1"),
        "max_daily_loss": Money(amount=Decimal("100000"), currency=THB),
        "max_drawdown_pct": Decimal("10"),
        "kill_switch": False,
    }
    defaults.update(kwargs)
    return RiskLimits(**defaults)  # type: ignore[arg-type]


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency=THB)


# --- Tests ---

def test_approved_order() -> None:
    decision = evaluate(
        order=_order("0.01"),
        account=_account(),
        positions={},
        limits=_limits(),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
    )
    assert decision.approved is True
    assert len(decision.reasons) == 0


def test_kill_switch_blocks() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(kill_switch=True),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.KILL_SWITCH_ACTIVE in decision.reasons


def test_order_qty_exceeded() -> None:
    decision = evaluate(
        order=_order("2.0"),
        account=_account(),
        positions={},
        limits=_limits(max_order_qty=Decimal("1")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.ORDER_QTY_EXCEEDED in decision.reasons


def test_position_qty_exceeded() -> None:
    positions = {
        "THB_BTC": Position(symbol="THB_BTC", qty=Decimal("0.9"), avg_entry_price=Decimal("1500000"))
    }
    decision = evaluate(
        order=_order("0.5"),  # would make total 1.4 > max 1
        account=_account(),
        positions=positions,
        limits=_limits(max_position_qty=Decimal("1")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.POSITION_QTY_EXCEEDED in decision.reasons


def test_daily_loss_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_daily_loss=_money("50000")),
        daily_pnl=_money("-60000"),
        peak_equity=_money("1000000"),
        current_equity=_money("940000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.DAILY_LOSS_EXCEEDED in decision.reasons


def test_drawdown_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_drawdown_pct=Decimal("10")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("850000"),  # 15% drawdown > 10% limit
    )
    assert decision.approved is False
    assert RiskReasonCode.DRAWDOWN_EXCEEDED in decision.reasons


def test_multiple_violations_all_returned() -> None:
    decision = evaluate(
        order=_order("2.0"),  # qty exceeded
        account=_account(),
        positions={},
        limits=_limits(max_order_qty=Decimal("1"), kill_switch=True),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.KILL_SWITCH_ACTIVE in decision.reasons
    assert RiskReasonCode.ORDER_QTY_EXCEEDED in decision.reasons


# --- Sizing tests ---

def test_fixed_fractional_basic() -> None:
    equity = _money("1000000")
    result = fixed_fractional(equity, risk_pct=Decimal("1"), stop_distance=Decimal("50000"))
    # size = (1,000,000 * 1/100) / 50,000 = 10,000 / 50,000 = 0.2
    assert result == Decimal("0.20000000")


def test_fixed_fractional_zero_stop() -> None:
    equity = _money("1000000")
    result = fixed_fractional(equity, risk_pct=Decimal("1"), stop_distance=Decimal("0"))
    assert result == Decimal(0)


def test_kelly_basic() -> None:
    # kelly = 0.6 - (1-0.6)/2.0 = 0.6 - 0.2 = 0.4 → clamped to 0.25
    result = kelly_fraction(win_rate=Decimal("0.6"), win_loss_ratio=Decimal("2"))
    assert result == Decimal("0.25")


def test_kelly_negative_clamped_to_zero() -> None:
    # negative expectancy → clamp to 0
    result = kelly_fraction(win_rate=Decimal("0.3"), win_loss_ratio=Decimal("0.5"))
    assert result == Decimal(0)


def test_kelly_zero_win_loss_ratio() -> None:
    result = kelly_fraction(win_rate=Decimal("0.6"), win_loss_ratio=Decimal("0"))
    assert result == Decimal(0)
