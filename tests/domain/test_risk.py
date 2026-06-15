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
from domain.risk.sizing import adaptive_kelly_size, fixed_fractional, kelly_fraction
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


# --- Adaptive Kelly sizing (U7) — always under the hard fence ---

def test_adaptive_kelly_basic_half_kelly() -> None:
    # kelly_fraction(0.6, 2) = 0.25; half-Kelly → 0.125 of equity at risk.
    # risk = 1,000,000 * 0.125 = 125,000; stop_distance 50,000 → qty 2.5
    qty = adaptive_kelly_size(
        _money("1000000"), entry_price=Decimal("1000000"),
        stop_price=Decimal("950000"), win_rate=Decimal("0.6"),
        win_loss_ratio=Decimal("2"),
    )
    assert qty == Decimal("2.50000000")


def test_adaptive_kelly_never_exceeds_cap_even_when_kelly_wants_more() -> None:
    # Strong edge would size 2.5 BTC (≈2.5M THB notional) but the cap is 100k THB.
    cap = Decimal("100000")
    qty = adaptive_kelly_size(
        _money("1000000"), entry_price=Decimal("1000000"),
        stop_price=Decimal("950000"), win_rate=Decimal("0.6"),
        win_loss_ratio=Decimal("2"), max_notional=cap,
    )
    assert qty * Decimal("1000000") <= cap        # notional never breaches the cap
    assert qty == Decimal("0.10000000")           # exactly cap / entry


def test_adaptive_kelly_negative_edge_sizes_nothing() -> None:
    qty = adaptive_kelly_size(
        _money("1000000"), entry_price=Decimal("1000000"),
        stop_price=Decimal("950000"), win_rate=Decimal("0.3"),
        win_loss_ratio=Decimal("0.5"),
    )
    assert qty == Decimal(0)


def test_adaptive_kelly_fraction_clamped_to_unit_interval() -> None:
    # fraction > 1 is clamped to 1 (full Kelly), not amplified beyond it.
    full = adaptive_kelly_size(
        _money("1000000"), entry_price=Decimal("1000000"),
        stop_price=Decimal("950000"), win_rate=Decimal("0.6"),
        win_loss_ratio=Decimal("2"), fraction=Decimal("5"),
    )
    # full Kelly 0.25 → risk 250,000 / 50,000 = 5.0
    assert full == Decimal("5.00000000")
    none = adaptive_kelly_size(
        _money("1000000"), entry_price=Decimal("1000000"),
        stop_price=Decimal("950000"), win_rate=Decimal("0.6"),
        win_loss_ratio=Decimal("2"), fraction=Decimal("-1"),
    )
    assert none == Decimal(0)


def test_adaptive_kelly_guards_bad_inputs() -> None:
    eq = _money("1000000")
    base = dict(win_rate=Decimal("0.6"), win_loss_ratio=Decimal("2"))
    assert adaptive_kelly_size(eq, Decimal("0"), Decimal("950000"), **base) == Decimal(0)
    assert adaptive_kelly_size(eq, Decimal("1000000"), Decimal("0"), **base) == Decimal(0)
    assert adaptive_kelly_size(eq, Decimal("1000000"), Decimal("1000000"), **base) == Decimal(0)
    assert adaptive_kelly_size(_money("0"), Decimal("1000000"), Decimal("950000"), **base) == Decimal(0)


# --- Extended evaluate() tests (Phase 1) ---

def test_circuit_breaker_open_blocks() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
        circuit_breaker_open=True,
    )
    assert decision.approved is False
    assert RiskReasonCode.CIRCUIT_BREAKER_OPEN in decision.reasons


def test_weekly_loss_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_weekly_loss=_money("30000")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("970000"),
        weekly_pnl=_money("-35000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.WEEKLY_LOSS_EXCEEDED in decision.reasons


def test_monthly_loss_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_monthly_loss=_money("50000")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("940000"),
        monthly_pnl=_money("-60000"),
    )
    assert decision.approved is False
    assert RiskReasonCode.MONTHLY_LOSS_EXCEEDED in decision.reasons


def test_consecutive_losses_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_consecutive_losses=3),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
        consecutive_losses=3,
    )
    assert decision.approved is False
    assert RiskReasonCode.CONSECUTIVE_LOSSES_EXCEEDED in decision.reasons


def test_max_open_positions_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_open_positions=2),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
        open_positions_count=3,
    )
    assert decision.approved is False
    assert RiskReasonCode.MAX_OPEN_POSITIONS_EXCEEDED in decision.reasons


def test_notional_exposure_exceeded() -> None:
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_notional_exposure_pct=Decimal("50")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("100000"),
        total_notional_exposure=_money("60000"),  # 60% > 50%
    )
    assert decision.approved is False
    assert RiskReasonCode.NOTIONAL_EXPOSURE_EXCEEDED in decision.reasons


def test_none_weekly_monthly_skips_checks() -> None:
    """None for weekly_pnl / monthly_pnl must skip those checks even with limits set."""
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_weekly_loss=_money("30000"), max_monthly_loss=_money("50000")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
        weekly_pnl=None,
        monthly_pnl=None,
    )
    assert decision.approved is True


def test_none_notional_skips_check() -> None:
    """None for total_notional_exposure must skip the notional check."""
    decision = evaluate(
        order=_order(),
        account=_account(),
        positions={},
        limits=_limits(max_notional_exposure_pct=Decimal("10")),
        daily_pnl=_money("0"),
        peak_equity=_money("1000000"),
        current_equity=_money("1000000"),
        total_notional_exposure=None,
    )
    assert decision.approved is True


def test_old_style_positional_call_still_works() -> None:
    """Original positional-arg call site must work unchanged after extension."""
    decision = evaluate(
        _order("0.01"),
        _account(),
        {},
        _limits(),
        _money("0"),
        _money("1000000"),
        _money("1000000"),
    )
    assert decision.approved is True



def test_startup_not_reconciled_reason_code_exists() -> None:
    """STARTUP_NOT_RECONCILED must be a member of RiskReasonCode (Phase 4 startup gate)."""
    from domain.risk.rules import RiskReasonCode

    assert "STARTUP_NOT_RECONCILED" in [r.value for r in RiskReasonCode]
    assert RiskReasonCode.STARTUP_NOT_RECONCILED == "STARTUP_NOT_RECONCILED"
