# Layer 1 — Domain (analytics/ta)
"""Thin deterministic wrappers over the vendored TA stub (src/vendor_ta).

Each function validates minimum bar count and ensures no NaN at the last
(decision) row.  Raises ValueError naming the indicator and required bars.
"""
from __future__ import annotations

import warnings

import pandas as pd

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    # Vendored, deterministic TA stub (src/vendor_ta). Imported under a
    # collision-proof name so a pip-installed ``pandas_ta`` can never shadow it
    # via sys.path ordering — guarantees identical indicator values in every
    # environment (Predictability / Backtest-Fidelity mandate).
    import vendor_ta  # noqa: F401 — registers the .ta accessor

# Defence-in-depth: the import name is collision-proof, but the ``.ta`` DataFrame
# accessor is a PROCESS-GLOBAL singleton — pandas only emits a UserWarning (not an
# error) if some other package (e.g. a pip-installed ``pandas_ta``) re-registers
# it AFTER us, silently swapping the indicator math. Assert the live owner is the
# vendored stub so a shadow fails loudly instead of corrupting backtest fidelity.
_ta_owner = getattr(getattr(pd.DataFrame, "ta", None), "__module__", "")
if not _ta_owner.startswith("vendor_ta"):  # pragma: no cover - defensive
    raise RuntimeError(
        f"pandas '.ta' accessor was shadowed by {_ta_owner!r}; expected the "
        "vendored deterministic stub (vendor_ta) — indicator math is unsafe"
    )


def _require(df: pd.DataFrame, min_bars: int, name: str) -> None:
    if len(df) < min_bars:
        raise ValueError(
            f"{name} requires at least {min_bars} bars, got {len(df)}"
        )


def _assert_last_valid(series: pd.Series, name: str) -> None:
    if pd.isna(series.iloc[-1]):
        raise ValueError(f"{name}: last row is NaN — insufficient warmup data")


def ema(df: pd.DataFrame, length: int) -> pd.DataFrame:
    """Exponential moving average of close prices."""
    _require(df, length, f"ema({length})")
    result = df["close"].ewm(span=length, adjust=False).mean()
    _assert_last_valid(result, f"ema({length})")
    return pd.DataFrame({f"EMA_{length}": result}, index=df.index)


def rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Relative Strength Index."""
    _require(df, length + 1, f"rsi({length})")
    result = df.ta.rsi(length=length)
    _assert_last_valid(result, f"rsi({length})")
    return pd.DataFrame({f"RSI_{length}": result}, index=df.index)


def stoch_rsi(df: pd.DataFrame) -> pd.DataFrame:
    """Stochastic RSI (default pandas_ta parameters: length=14, rsi_length=14)."""
    _require(df, 32, "stoch_rsi")
    result = df.ta.stochrsi()
    if result is None or result.empty:
        raise ValueError("stoch_rsi: pandas_ta returned no data")
    _assert_last_valid(result.iloc[:, 0], "stoch_rsi")
    return result


def supertrend(df: pd.DataFrame, length: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """SuperTrend indicator.

    Returns DataFrame with columns 'trend' (direction: 1=bullish, -1=bearish)
    and 'line' (the actual SuperTrend value).
    """
    _require(df, length + 1, f"supertrend({length})")
    result = df.ta.supertrend(length=length, multiplier=multiplier)
    if result is None or result.empty:
        raise ValueError("supertrend: pandas_ta returned no data")
    # pandas_ta column naming: SUPERT_<l>_<m>, SUPERTd_<l>_<m>
    line_col = result.columns[0]
    dir_col = result.columns[1]
    _assert_last_valid(result[line_col], "supertrend")
    return pd.DataFrame(
        {"line": result[line_col], "trend": result[dir_col]}, index=df.index
    )


def vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Volume-Weighted Average Price — cumulative, session-based approximation."""
    _require(df, 1, "vwap")
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_tp_vol = (typical * df["volume"]).cumsum()
    cum_vol = df["volume"].cumsum()
    result = cum_tp_vol / cum_vol
    _assert_last_valid(result, "vwap")
    return pd.DataFrame({"VWAP": result}, index=df.index)


def obv(df: pd.DataFrame) -> pd.DataFrame:
    """On Balance Volume."""
    _require(df, 2, "obv")
    result = df.ta.obv()
    _assert_last_valid(result, "obv")
    return pd.DataFrame({"OBV": result}, index=df.index)


def atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Average True Range."""
    _require(df, length + 1, f"atr({length})")
    result = df.ta.atr(length=length)
    _assert_last_valid(result, f"atr({length})")
    return pd.DataFrame({f"ATR_{length}": result}, index=df.index)


def adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
    """Average Directional Index."""
    _require(df, length + 1, f"adx({length})")
    result = df.ta.adx(length=length)
    if result is None or result.empty:
        raise ValueError("adx: pandas_ta returned no data")
    # pandas_ta returns ADX_14, ADXR_14_2, DMP_14, DMN_14
    adx_col = result.columns[0]
    _assert_last_valid(result[adx_col], f"adx({length})")
    return pd.DataFrame({f"ADX_{length}": result[adx_col]}, index=df.index)
