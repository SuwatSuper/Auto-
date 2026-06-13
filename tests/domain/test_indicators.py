# Layer 1 — Domain (tests/domain/test_indicators)
"""Tests for pure analytics indicators."""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.indicators import (
    ema,
    expectancy,
    macd,
    max_drawdown,
    rsi_wilder,
    win_rate,
)


def _d(s: str) -> Decimal:
    return Decimal(s)


# --- EMA ---

def test_ema_single_value() -> None:
    result = ema([_d("100")], period=5)
    assert result == [_d("100")]


def test_ema_constant_series() -> None:
    prices = [_d("100")] * 10
    result = ema(prices, period=3)
    # EMA of constant series is the constant itself
    assert all(abs(v - _d("100")) < _d("0.001") for v in result)


def test_ema_increasing_series() -> None:
    prices = [Decimal(str(i * 100)) for i in range(1, 11)]
    result = ema(prices, period=3)
    assert len(result) == 10
    # Last EMA should be close to last prices
    assert result[-1] > result[0]


# --- RSI ---

def test_rsi_all_up_is_100() -> None:
    # 15 values all increasing
    prices = [Decimal(str(100 + i * 10)) for i in range(15)]
    result = rsi_wilder(prices, period=14)
    assert result[-1] == _d("100")


def test_rsi_length_matches_input() -> None:
    prices = [Decimal(str(i)) for i in range(1, 20)]
    result = rsi_wilder(prices, period=14)
    assert len(result) == len(prices)


def test_rsi_insufficient_data_returns_nans() -> None:
    prices = [Decimal("100"), Decimal("101"), Decimal("99")]
    result = rsi_wilder(prices, period=14)
    assert all(str(v) == "NaN" for v in result)


def test_rsi_known_value() -> None:
    """RSI for a known 15-value series.
    Last 14 changes: 10 gains of 1, then 4 losses of -1.
    seed avg_gain=10/14, avg_loss=0 → RSI=100 for first RSI.
    Then one loss: avg_gain=(10/14*13+0)/14=..., avg_loss=(0*13+1)/14=1/14
    """
    # Simple test: equal gains and losses → RSI ~50
    prices = []
    for i in range(16):
        prices.append(Decimal(str(1000 + (10 if i % 2 == 0 else -10))))
    result = rsi_wilder(prices, period=14)
    last = result[-1]
    assert str(last) != "NaN"
    assert _d("40") <= last <= _d("60")  # near 50 for equal up/down


# --- MACD ---

def test_macd_lengths() -> None:
    prices = [Decimal(str(1000 + i * 10)) for i in range(50)]
    ml, sl, hist = macd(prices)
    assert len(ml) == len(sl) == len(hist) == 50


# --- max_drawdown ---

def test_max_drawdown_no_drawdown() -> None:
    prices = [Decimal(str(i * 100)) for i in range(1, 11)]
    assert max_drawdown(prices) == Decimal(0)


def test_max_drawdown_50_pct() -> None:
    prices = [_d("1000"), _d("500"), _d("1000")]
    # drawdown = (1000-500)/1000 = 0.5
    result = max_drawdown(prices)
    assert result == _d("0.5")


def test_max_drawdown_single_value() -> None:
    assert max_drawdown([_d("100")]) == Decimal(0)


# --- win_rate ---

def test_win_rate_all_wins() -> None:
    pnls = [_d("100"), _d("200"), _d("50")]
    assert win_rate(pnls) == Decimal(1)


def test_win_rate_mixed() -> None:
    pnls = [_d("100"), _d("-50"), _d("200"), _d("-100")]
    assert win_rate(pnls) == _d("0.5")


def test_win_rate_empty() -> None:
    assert win_rate([]) == Decimal(0)


# --- expectancy ---

def test_expectancy_positive() -> None:
    pnls = [_d("100"), _d("200"), _d("-50")]
    assert expectancy(pnls) == _d("250") / _d("3")


def test_expectancy_empty() -> None:
    assert expectancy([]) == Decimal(0)
