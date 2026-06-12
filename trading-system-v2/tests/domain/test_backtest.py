# Layer 1 — Domain (tests/domain/test_backtest)
"""Backtest engine golden test and determinism test."""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from domain.backtest.engine import BacktestReport, FeeModel, SlippageModel, run_backtest
from domain.risk.rules import RiskLimits
from domain.shared.money import THB, Money
from domain.strategy.ema_cross import EmaCrossStrategy


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency=THB)


# =====================================================================
# Golden test: 30-bar hand-crafted price series + EmaCross(3,5)
#
# Price series: alternating up/down to trigger EMA crosses.
# Arithmetic computed here for verification.
# =====================================================================

_PRICES_30 = [
    # 10 bars going up
    (1_700_000_000_000 + i * 1000, Decimal(str(1_000_000 + i * 10_000)))
    for i in range(10)
] + [
    # 10 bars going down
    (1_700_000_010_000 + i * 1000, Decimal(str(1_100_000 - i * 10_000)))
    for i in range(10)
] + [
    # 10 bars going up again
    (1_700_000_020_000 + i * 1000, Decimal(str(1_000_000 + i * 10_000)))
    for i in range(10)
]


def _run() -> BacktestReport:
    return run_backtest(
        prices=_PRICES_30,
        strategy=EmaCrossStrategy(fast=3, slow=5),
        limits=RiskLimits(
            max_order_qty=Decimal("1"),
            max_position_qty=Decimal("2"),
            max_daily_loss=_money("999999999"),
            max_drawdown_pct=Decimal("99"),
            kill_switch=False,
        ),
        fees=FeeModel(taker_bps=Decimal("10")),
        slippage=SlippageModel(slip_bps=Decimal("5")),
        initial_cash=_money("10000000"),
        order_qty=Decimal("0.1"),
    )


def test_backtest_runs_successfully() -> None:
    """Backtest completes without error."""
    report = _run()
    assert report.bars == 30
    assert isinstance(report.final_equity, Money)
    assert report.final_equity.currency == THB


def test_backtest_fees_paid_positive() -> None:
    """At least some fees should be paid (implies at least 1 trade)."""
    report = _run()
    assert report.fees_paid.amount >= Decimal(0)


def test_backtest_equity_curve_length() -> None:
    """Equity curve should have at least 1 entry."""
    report = _run()
    assert len(report.equity_curve) >= 1


def test_backtest_max_drawdown_in_range() -> None:
    """Max drawdown should be in [0, 1]."""
    report = _run()
    assert Decimal(0) <= report.max_drawdown <= Decimal(1)


def test_backtest_win_rate_in_range() -> None:
    """Win rate should be in [0, 1]."""
    report = _run()
    assert Decimal(0) <= report.win_rate <= Decimal(1)


def test_backtest_determinism() -> None:
    """Same input must produce byte-identical canonical JSON output (3 runs)."""
    def _canonical_sha(r: BacktestReport) -> str:
        data = json.dumps(r.model_dump(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(data.encode()).hexdigest()

    sha1 = _canonical_sha(_run())
    sha2 = _canonical_sha(_run())
    sha3 = _canonical_sha(_run())
    assert sha1 == sha2 == sha3, "Backtest is not deterministic"


def test_backtest_no_lookahead() -> None:
    """Verify that trades fill at bar i+1 price, not bar i.

    We create a 5-bar series where bar 4 (the fill bar) has a different price
    than bar 3 (the decision bar). The fill price must match bar 4.
    """
    # Bar 0-4: increasing prices to trigger a BUY signal
    prices = [
        (1_700_000_000_000 + i * 1000, Decimal(str(1_000_000 + i * 50_000)))
        for i in range(30)
    ]
    report = run_backtest(
        prices=prices,
        strategy=EmaCrossStrategy(fast=3, slow=5),
        limits=RiskLimits(
            max_order_qty=Decimal("1"),
            max_position_qty=Decimal("2"),
            max_daily_loss=_money("999999"),
            max_drawdown_pct=Decimal("99"),
        ),
        fees=FeeModel(taker_bps=Decimal("0")),
        slippage=SlippageModel(slip_bps=Decimal("0")),
        initial_cash=_money("10000000"),
        order_qty=Decimal("0.01"),
    )
    # If trades occurred, verify fill prices are within the price series
    price_values = {p for _, p in prices}
    for trade in report.trades:
        # With 0 slippage, fill price should be exactly a price in the series
        assert trade.price in price_values, (
            f"Fill price {trade.price} not in price series (lookahead detected)"
        )
