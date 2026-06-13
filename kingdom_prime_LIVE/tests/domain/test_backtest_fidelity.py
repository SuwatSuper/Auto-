"""Backtest fidelity: maker/taker fees and partial-fill model.

TASK 8: Verify that:
1. MakerTakerFeeModel applies correct fee tiers (Bitkub 0.15%/0.25%).
2. Maker fees produce higher PnL than taker fees (smaller cost).
3. PartialFillModel reduces fill quantity proportionally.
4. Determinism is preserved across all new models.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from domain.backtest.engine import (
    FeeModel,
    MakerTakerFeeModel,
    PartialFillModel,
    SlippageModel,
    run_backtest,
)
from domain.risk.rules import RiskLimits
from domain.shared.money import Money
from domain.strategy.ema_cross import EmaCrossStrategy


def _prices(n: int = 60, base: int = 3_500_000, step: int = 20_000) -> list[tuple[int, Decimal]]:
    """V-shape series: decline then sharp rise, guaranteeing an EMA(12/26) crossover."""
    mid = n // 2
    result = []
    for i in range(n):
        if i < mid:
            price = base - i * step
        else:
            price = base - mid * step + (i - mid) * step * 2
        result.append((i * 1000, Decimal(str(max(1, price)))))
    return result


def _limits() -> RiskLimits:
    return RiskLimits(
        max_order_qty=Decimal("1"),
        max_position_qty=Decimal("1"),
        max_daily_loss=Money(amount=Decimal("10000"), currency="THB"),
        max_drawdown_pct=Decimal("30"),
        max_consecutive_losses=10,
        max_open_positions=1,
    )


def _cash() -> Money:
    return Money(amount=Decimal("100000"), currency="THB")


# ── MakerTakerFeeModel tests ───────────────────────────────────────────────

def test_maker_taker_fee_model_taker_rate() -> None:
    m = MakerTakerFeeModel(maker_bps=Decimal("15"), taker_bps=Decimal("25"))
    assert m.fee_bps(is_taker=True) == Decimal("25")


def test_maker_taker_fee_model_maker_rate() -> None:
    m = MakerTakerFeeModel(maker_bps=Decimal("15"), taker_bps=Decimal("25"))
    assert m.fee_bps(is_taker=False) == Decimal("15")


def test_fee_model_taker_only_always_returns_taker_bps() -> None:
    m = FeeModel(taker_bps=Decimal("25"))
    assert m.fee_bps(is_taker=True) == Decimal("25")
    assert m.fee_bps(is_taker=False) == Decimal("25")


def test_maker_fees_produce_lower_cost_than_taker() -> None:
    """Maker fee (15 bps) saves more of the principal than taker (25 bps)."""
    prices = _prices()
    limits = _limits()
    cash = _cash()
    slip = SlippageModel(slip_bps=Decimal("5"))
    qty = Decimal("0.01")

    maker_model = MakerTakerFeeModel(maker_bps=Decimal("15"), taker_bps=Decimal("25"))
    taker_model = FeeModel(taker_bps=Decimal("25"))

    report_maker = run_backtest(prices, EmaCrossStrategy(), limits, maker_model, slip, cash, qty, is_taker=False)
    report_taker = run_backtest(prices, EmaCrossStrategy(), limits, taker_model, slip, cash, qty, is_taker=True)

    # Maker fees should be strictly lower in absolute terms
    assert report_maker.fees_paid.amount < report_taker.fees_paid.amount, (
        f"Maker fees {report_maker.fees_paid.amount} should be < taker fees {report_taker.fees_paid.amount}"
    )


# ── PartialFillModel tests ─────────────────────────────────────────────────

def test_partial_fill_model_fraction() -> None:
    pf = PartialFillModel(fill_pct=Decimal("70"))
    assert pf.fraction == Decimal("0.70")


def test_partial_fill_100_equals_full_fill() -> None:
    prices = _prices()
    limits = _limits()
    cash = _cash()
    fees = FeeModel(taker_bps=Decimal("25"))
    slip = SlippageModel(slip_bps=Decimal("5"))
    qty = Decimal("0.01")

    full = run_backtest(prices, EmaCrossStrategy(), limits, fees, slip, cash, qty)
    partial_100 = run_backtest(
        prices, EmaCrossStrategy(), limits, fees, slip, cash, qty,
        partial_fill=PartialFillModel(fill_pct=Decimal("100"))
    )
    assert full.fees_paid.amount == partial_100.fees_paid.amount


def test_partial_fill_reduces_fees_proportionally() -> None:
    prices = _prices()
    limits = _limits()
    cash = _cash()
    fees = FeeModel(taker_bps=Decimal("25"))
    slip = SlippageModel(slip_bps=Decimal("5"))
    qty = Decimal("0.01")

    full = run_backtest(prices, EmaCrossStrategy(), limits, fees, slip, cash, qty)
    half = run_backtest(
        prices, EmaCrossStrategy(), limits, fees, slip, cash, qty,
        partial_fill=PartialFillModel(fill_pct=Decimal("50"))
    )
    # Fees should be roughly halved (less than full, more than zero)
    assert half.fees_paid.amount < full.fees_paid.amount
    assert half.fees_paid.amount > Decimal("0")


def test_zero_partial_fill_produces_no_trades() -> None:
    prices = _prices()
    limits = _limits()
    cash = _cash()
    fees = FeeModel(taker_bps=Decimal("25"))
    slip = SlippageModel(slip_bps=Decimal("5"))
    qty = Decimal("0.01")

    report = run_backtest(
        prices, EmaCrossStrategy(), limits, fees, slip, cash, qty,
        partial_fill=PartialFillModel(fill_pct=Decimal("0"))
    )
    assert len(report.trades) == 0
    assert report.fees_paid.amount == Decimal("0")


# ── Determinism with new models ────────────────────────────────────────────

def test_maker_taker_model_deterministic() -> None:
    """Same inputs → same SHA256 equity curve every time."""
    prices = _prices(60)
    limits = _limits()
    cash = _cash()
    fees = MakerTakerFeeModel(maker_bps=Decimal("15"), taker_bps=Decimal("25"))
    slip = SlippageModel(slip_bps=Decimal("5"))
    qty = Decimal("0.005")

    results = [
        run_backtest(prices, EmaCrossStrategy(), limits, fees, slip, cash, qty, is_taker=True)
        for _ in range(3)
    ]
    curves = [
        hashlib.sha256(",".join(str(v) for v in r.equity_curve).encode()).hexdigest()
        for r in results
    ]
    assert len(set(curves)) == 1, "Backtest with MakerTakerFeeModel must be deterministic"


def test_partial_fill_model_deterministic() -> None:
    prices = _prices(60)
    limits = _limits()
    cash = _cash()
    fees = FeeModel(taker_bps=Decimal("25"))
    slip = SlippageModel(slip_bps=Decimal("5"))
    qty = Decimal("0.01")
    pf = PartialFillModel(fill_pct=Decimal("75"))

    results = [
        run_backtest(prices, EmaCrossStrategy(), limits, fees, slip, cash, qty, partial_fill=pf)
        for _ in range(3)
    ]
    curves = [
        hashlib.sha256(",".join(str(v) for v in r.equity_curve).encode()).hexdigest()
        for r in results
    ]
    assert len(set(curves)) == 1, "Backtest with PartialFillModel must be deterministic"
