# tests/domain/test_regime.py
"""One-frame-per-regime tests for domain.analytics.regime.classify."""
from __future__ import annotations

import numpy as np
import pandas as pd

from domain.analytics.regime import MarketRegime, classify
from tests._fixtures.ohlcv import build_ohlcv


def _make_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    return build_ohlcv(n=n, seed=seed)


def test_classify_returns_range_on_insufficient_bars() -> None:
    df = _make_df(n=30)
    assert classify(df) == MarketRegime.RANGE


def test_classify_default_fixture_returns_a_regime() -> None:
    df = _make_df(n=300)
    result = classify(df)
    assert result in list(MarketRegime)


def test_classify_high_vol_when_atr_large() -> None:
    """Force HIGH_VOL by making ATR/close very large."""
    df = _make_df(n=200).copy()
    # Exaggerate high/low spread to force large ATR
    df["high"] = df["close"] * 1.5
    df["low"] = df["close"] * 0.5
    result = classify(df, atr_pct_highvol_threshold=3.0)
    assert result == MarketRegime.HIGH_VOL


def test_classify_trend_up_when_adx_high_and_close_above_ema50() -> None:
    """Force TREND_UP: close far above EMA50, high ADX via strong trending data."""
    rng = np.random.RandomState(0)
    n = 200
    # Strong uptrend: price always increasing
    close = np.linspace(10000.0, 80000.0, n) + rng.randn(n) * 50
    high = close * 1.001
    low = close * 0.999
    open_ = close * (1.0 + rng.randn(n) * 0.0005)
    volume = np.abs(rng.randn(n)) * 1000 + 100
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
    result = classify(df, adx_trend_threshold=10.0, atr_pct_highvol_threshold=5.0)
    assert result == MarketRegime.TREND_UP


def test_classify_trend_down_when_adx_high_and_close_below_ema50() -> None:
    """Force TREND_DOWN: price always decreasing."""
    rng = np.random.RandomState(1)
    n = 200
    close = np.linspace(80000.0, 10000.0, n) + rng.randn(n) * 50
    high = close * 1.001
    low = close * 0.999
    open_ = close * (1.0 + rng.randn(n) * 0.0005)
    volume = np.abs(rng.randn(n)) * 1000 + 100
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
    result = classify(df, adx_trend_threshold=10.0, atr_pct_highvol_threshold=5.0)
    assert result == MarketRegime.TREND_DOWN


def test_classify_range_when_adx_low() -> None:
    """Force RANGE: sideways chop, low ADX."""
    rng = np.random.RandomState(7)
    n = 200
    close = np.ones(n) * 50000.0 + rng.randn(n) * 10  # tiny random noise
    high = close + 5
    low = close - 5
    open_ = close + rng.randn(n) * 2
    volume = np.abs(rng.randn(n)) * 1000 + 100
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume})
    result = classify(df, adx_trend_threshold=50.0, atr_pct_highvol_threshold=5.0)
    assert result == MarketRegime.RANGE


def test_classify_market_regime_str_values() -> None:
    assert str(MarketRegime.TREND_UP) == "TREND_UP"
    assert str(MarketRegime.TREND_DOWN) == "TREND_DOWN"
    assert str(MarketRegime.RANGE) == "RANGE"
    assert str(MarketRegime.HIGH_VOL) == "HIGH_VOL"
