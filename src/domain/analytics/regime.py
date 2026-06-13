# Layer 1 — Domain (analytics/regime)
"""Market regime classification from OHLCV data."""
from __future__ import annotations

from enum import StrEnum

import pandas as pd

from domain.analytics import ta


class MarketRegime(StrEnum):
    """Classified market regime."""

    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"


def classify(
    df: pd.DataFrame,
    adx_trend_threshold: float = 25.0,
    atr_pct_highvol_threshold: float = 3.0,
) -> MarketRegime:
    """Classify the current market regime from OHLCV data.

    Evaluation order (first match wins):
      1. HIGH_VOL  — if ATR/close*100 > atr_pct_highvol_threshold
      2. TREND_UP  — if ADX > threshold and close > EMA(50)
      3. TREND_DOWN — if ADX > threshold and close < EMA(50)
      4. RANGE     — otherwise
    """
    # Minimum 51 bars required (EMA(50) needs 50 + ATR needs 15)
    if len(df) < 51:
        return MarketRegime.RANGE

    close = float(df["close"].iloc[-1])

    atr_df = ta.atr(df, length=14)
    atr_val = float(atr_df.iloc[-1, 0])
    if close > 0 and (atr_val / close * 100) > atr_pct_highvol_threshold:
        return MarketRegime.HIGH_VOL

    adx_df = ta.adx(df, length=14)
    adx_val = float(adx_df.iloc[-1, 0])

    ema50_df = ta.ema(df, length=50)
    ema50_val = float(ema50_df.iloc[-1, 0])

    if adx_val > adx_trend_threshold:
        if close > ema50_val:
            return MarketRegime.TREND_UP
        return MarketRegime.TREND_DOWN

    return MarketRegime.RANGE
