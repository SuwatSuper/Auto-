"""Minimal pandas_ta stub implementing only the indicators used by this project.

Registers the `.ta` accessor on pandas DataFrames exactly as real pandas_ta does.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

__version__ = "0.3.14b-stub"


def _wilder_rma(series: pd.Series, length: int) -> pd.Series:
    """Wilder's smoothing (used by RSI/ATR)."""
    alpha = 1.0 / length
    result = series.copy().astype(float)
    # Find first valid index
    first_valid = series.first_valid_index()
    if first_valid is None:
        return result
    start = series.index.get_loc(first_valid)
    # Seed with simple mean
    seed = series.iloc[start : start + length].mean()
    result.iloc[start + length - 1] = seed
    for i in range(start + length, len(series)):
        result.iloc[i] = alpha * series.iloc[i] + (1 - alpha) * result.iloc[i - 1]
    result.iloc[start : start + length - 1] = float("nan")
    return result


class TaAccessor:
    def __init__(self, df: pd.DataFrame) -> None:
        self._df = df

    def rsi(self, length: int = 14, **_kw) -> pd.Series:
        close = self._df["close"].astype(float)
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_gain = _wilder_rma(gain, length)
        avg_loss = _wilder_rma(loss, length)
        rs = avg_gain / avg_loss.replace(0, float("nan"))
        rsi = 100 - 100 / (1 + rs)
        rsi.name = f"RSI_{length}"
        return rsi

    def stochrsi(self, length: int = 14, rsi_length: int = 14, k: int = 3, d: int = 3, **_kw) -> pd.DataFrame:
        rsi_series = self.rsi(length=rsi_length)
        rsi_min = rsi_series.rolling(length).min()
        rsi_max = rsi_series.rolling(length).max()
        stoch = (rsi_series - rsi_min) / (rsi_max - rsi_min).replace(0, float("nan"))
        stoch_k = stoch.rolling(k).mean() * 100
        stoch_d = stoch_k.rolling(d).mean()
        return pd.DataFrame(
            {f"STOCHRSIk_{length}_{rsi_length}_{k}_{d}": stoch_k,
             f"STOCHRSId_{length}_{rsi_length}_{k}_{d}": stoch_d},
            index=self._df.index,
        )

    def supertrend(self, length: int = 10, multiplier: float = 3.0, **_kw) -> pd.DataFrame:
        high = self._df["high"].astype(float)
        low = self._df["low"].astype(float)
        close = self._df["close"].astype(float)
        hl2 = (high + low) / 2
        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = _wilder_rma(tr, length)
        upper_band = hl2 + multiplier * atr
        lower_band = hl2 - multiplier * atr
        supertrend = pd.Series(float("nan"), index=close.index)
        direction = pd.Series(float("nan"), index=close.index)

        prev_st = float("nan")
        prev_dir = 1.0

        for i in range(len(close)):
            if math.isnan(atr.iloc[i]):
                continue
            ub = upper_band.iloc[i]
            lb = lower_band.iloc[i]
            c = close.iloc[i]
            # Keep bands from widening
            if not math.isnan(prev_st):
                if prev_dir == 1:
                    lb = max(lb, prev_st)
                else:
                    ub = min(ub, prev_st)
            if math.isnan(prev_st):
                d = 1.0
                st = lb
            elif prev_dir == 1:
                if c < prev_st:
                    d = -1.0
                    st = ub
                else:
                    d = 1.0
                    st = lb
            else:
                if c > prev_st:
                    d = 1.0
                    st = lb
                else:
                    d = -1.0
                    st = ub
            supertrend.iloc[i] = st
            direction.iloc[i] = d
            prev_st = st
            prev_dir = d

        col_s = f"SUPERT_{length}_{multiplier}"
        col_d = f"SUPERTd_{length}_{multiplier}"
        return pd.DataFrame({col_s: supertrend, col_d: direction}, index=close.index)

    def obv(self, **_kw) -> pd.Series:
        close = self._df["close"].astype(float)
        volume = self._df["volume"].astype(float)
        sign = np.sign(close.diff())
        sign.iloc[0] = 0
        obv = (sign * volume).cumsum()
        obv.name = "OBV"
        return obv

    def atr(self, length: int = 14, **_kw) -> pd.Series:
        high = self._df["high"].astype(float)
        low = self._df["low"].astype(float)
        close = self._df["close"].astype(float)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        result = _wilder_rma(tr, length)
        result.name = f"ATRr_{length}"
        return result

    def adx(self, length: int = 14, **_kw) -> pd.DataFrame:
        high = self._df["high"].astype(float)
        low = self._df["low"].astype(float)
        close = self._df["close"].astype(float)
        # True Range
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        # Directional movement
        up_move = high - high.shift()
        down_move = low.shift() - low
        plus_dm = pd.Series(0.0, index=close.index)
        minus_dm = pd.Series(0.0, index=close.index)
        plus_dm[up_move > down_move] = up_move[up_move > down_move].clip(lower=0)
        minus_dm[down_move > up_move] = down_move[down_move > up_move].clip(lower=0)

        atr14 = _wilder_rma(tr, length)
        plus_di = 100 * _wilder_rma(plus_dm, length) / atr14
        minus_di = 100 * _wilder_rma(minus_dm, length) / atr14
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, float("nan"))
        adx_series = _wilder_rma(dx, length)
        adx_series.name = f"ADX_{length}"
        return pd.DataFrame({
            f"ADX_{length}": adx_series,
            f"DMP_{length}": plus_di,
            f"DMN_{length}": minus_di,
        }, index=close.index)


@pd.api.extensions.register_dataframe_accessor("ta")
class _TaDataFrameAccessor(TaAccessor):
    def __init__(self, pandas_obj: pd.DataFrame) -> None:
        super().__init__(pandas_obj)
