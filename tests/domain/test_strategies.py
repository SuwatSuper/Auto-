# Layer 1 — Domain (tests/domain/test_strategies)
"""Tests for EMA cross and RSI reversion strategies."""
from __future__ import annotations

from decimal import Decimal

from domain.strategy.base import SignalAction, StrategyContext
from domain.strategy.ema_cross import EmaCrossStrategy
from domain.strategy.rsi_reversion import RsiReversionStrategy


def _ctx(prices: list[str], position: str = "0") -> StrategyContext:
    return StrategyContext(
        prices=tuple(Decimal(p) for p in prices),
        position_qty=Decimal(position),
    )


# --- EMA Cross ---

def test_ema_cross_insufficient_data_returns_hold() -> None:
    strategy = EmaCrossStrategy(fast=3, slow=5)
    ctx = _ctx(["100", "101", "102"])  # only 3 bars, need slow+1=6
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.HOLD


def test_ema_cross_buy_signal() -> None:
    """Fast EMA crosses above slow EMA → BUY.

    Present exactly 7 bars: 6 flat then 1 spike up.
    At bar 5: fast=slow=100 (prev_fast<=prev_slow is True since equal).
    At bar 6: fast jumps above slow → cross detected.
    """
    strategy = EmaCrossStrategy(fast=3, slow=5)
    prices = ["100", "100", "100", "100", "100", "100", "1000000"]
    ctx = _ctx(prices)
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.BUY


def test_ema_cross_sell_signal() -> None:
    """Fast EMA crosses below slow EMA → SELL.

    Present exactly 7 bars: 6 flat at high price then 1 crash.
    At bar 5: fast=slow=400 (prev_fast>=prev_slow is True since equal).
    At bar 6: fast drops below slow → cross detected.
    """
    strategy = EmaCrossStrategy(fast=3, slow=5)
    prices = ["400", "400", "400", "400", "400", "400", "1"]
    ctx = _ctx(prices)
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.SELL


def test_ema_cross_confidence_between_0_and_1() -> None:
    strategy = EmaCrossStrategy(fast=3, slow=5)
    prices = ["100", "100", "100", "100", "100", "100", "200", "300", "400"]
    ctx = _ctx(prices)
    signal = strategy.decide(ctx)
    assert Decimal(0) <= signal.confidence <= Decimal(1)


# --- RSI Reversion ---

def test_rsi_insufficient_data_returns_hold() -> None:
    strategy = RsiReversionStrategy(period=14)
    ctx = _ctx(["100"] * 5)
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.HOLD


def test_rsi_oversold_buy() -> None:
    """All-down series → RSI near 0 → BUY."""
    strategy = RsiReversionStrategy(period=14)
    prices = [str(1000 - i * 10) for i in range(20)]
    ctx = _ctx(prices)
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.BUY


def test_rsi_overbought_sell() -> None:
    """All-up series → RSI = 100 → SELL."""
    strategy = RsiReversionStrategy(period=14)
    prices = [str(1000 + i * 10) for i in range(20)]
    ctx = _ctx(prices)
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.SELL


def test_rsi_neutral_hold() -> None:
    """Prices alternating mildly → RSI around 50 → HOLD."""
    strategy = RsiReversionStrategy(period=14)
    # Alternating prices keep RSI near 50
    prices = [str(1000 + (i % 2) * 5) for i in range(30)]
    ctx = _ctx(prices)
    signal = strategy.decide(ctx)
    assert signal.action == SignalAction.HOLD
