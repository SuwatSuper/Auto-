# tests/domain/test_ta.py
"""Golden-value tests for domain.analytics.ta wrappers using the seeded fixture."""
from __future__ import annotations

import pytest

from domain.analytics import ta
from tests._fixtures.ohlcv import build_ohlcv

_DF = build_ohlcv(n=300, seed=42)


def test_ta_accessor_is_the_vendored_stub() -> None:
    """Determinism guard: the process-global pandas '.ta' accessor must be the
    vendored deterministic stub, never a pip-installed shadow (e.g. pandas_ta)."""
    import pandas as pd

    owner = getattr(getattr(pd.DataFrame, "ta", None), "__module__", "")
    assert owner.startswith("vendor_ta"), f"'.ta' accessor shadowed by {owner!r}"


def test_ema9_last_value() -> None:
    result = ta.ema(_DF, length=9)
    val = float(result["EMA_9"].iloc[-1])
    assert abs(val - 47803.938467) < 1.0


def test_ema21_last_value() -> None:
    result = ta.ema(_DF, length=21)
    val = float(result["EMA_21"].iloc[-1])
    assert abs(val - 47681.034223) < 1.0


def test_rsi14_last_value() -> None:
    result = ta.rsi(_DF, length=14)
    val = float(result["RSI_14"].iloc[-1])
    assert abs(val - 58.599038) < 1.0


def test_atr14_last_value() -> None:
    result = ta.atr(_DF, length=14)
    val = float(result.iloc[-1, 0])
    assert abs(val - 542.048026) < 10.0


def test_adx14_last_value() -> None:
    result = ta.adx(_DF, length=14)
    val = float(result.iloc[-1, 0])
    assert abs(val - 11.395545) < 1.0


def test_supertrend_direction_and_line() -> None:
    result = ta.supertrend(_DF)
    direction = float(result["trend"].iloc[-1])
    line = float(result["line"].iloc[-1])
    assert direction in (-1.0, 1.0)
    assert line > 0


def test_vwap_returns_positive() -> None:
    result = ta.vwap(_DF)
    val = float(result["VWAP"].iloc[-1])
    assert val > 0


def test_obv_returns_values() -> None:
    result = ta.obv(_DF)
    assert "OBV" in result.columns
    assert not result["OBV"].isna().all()


def test_stoch_rsi_shape() -> None:
    result = ta.stoch_rsi(_DF)
    assert result.shape[0] == len(_DF)
    assert result.shape[1] >= 2


def test_ema_insufficient_bars_raises() -> None:
    small = _DF.iloc[:5]
    with pytest.raises(ValueError, match="ema"):
        ta.ema(small, length=9)


def test_rsi_insufficient_bars_raises() -> None:
    small = _DF.iloc[:5]
    with pytest.raises(ValueError, match="rsi"):
        ta.rsi(small, length=14)


def test_atr_insufficient_bars_raises() -> None:
    small = _DF.iloc[:5]
    with pytest.raises(ValueError, match="atr"):
        ta.atr(small, length=14)


def test_ema_output_index_matches_input() -> None:
    result = ta.ema(_DF, length=9)
    assert list(result.index) == list(_DF.index)
