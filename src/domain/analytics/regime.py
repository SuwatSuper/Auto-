# Layer 1 — Domain (analytics/regime)
"""Market regime classification from OHLCV data."""
from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class RegimeRead:
    """A regime call with a [0, 1] confidence and the raw drivers behind it.

    Confidence lets the runtime size its conviction in the regime itself — a
    barely-trending tape (ADX just over threshold) should switch the playbook
    less aggressively than an unmistakable one."""

    regime: MarketRegime
    confidence: float
    adx: float
    atr_pct: float


def classify_with_confidence(
    df: pd.DataFrame,
    adx_trend_threshold: float = 25.0,
    atr_pct_highvol_threshold: float = 3.0,
) -> RegimeRead:
    """Same decision as :func:`classify`, plus a confidence and the drivers.

    Confidence scales with how decisively the deciding metric clears its
    threshold (ATR/ADX), capped at 1.0. Insufficient history → RANGE at 0.0.
    """
    if len(df) < 51:
        return RegimeRead(MarketRegime.RANGE, 0.0, 0.0, 0.0)

    close = float(df["close"].iloc[-1])
    atr_val = float(ta.atr(df, length=14).iloc[-1, 0])
    atr_pct = (atr_val / close * 100) if close > 0 else 0.0
    adx_val = float(ta.adx(df, length=14).iloc[-1, 0])
    ema50_val = float(ta.ema(df, length=50).iloc[-1, 0])

    if atr_pct > atr_pct_highvol_threshold:
        conf = min(1.0, atr_pct / (atr_pct_highvol_threshold * 2))
        return RegimeRead(MarketRegime.HIGH_VOL, conf, adx_val, atr_pct)

    if adx_val > adx_trend_threshold:
        conf = min(1.0, (adx_val - adx_trend_threshold) / adx_trend_threshold)
        regime = MarketRegime.TREND_UP if close > ema50_val else MarketRegime.TREND_DOWN
        return RegimeRead(regime, conf, adx_val, atr_pct)

    # Ranging: most confident when ADX is far BELOW the trend threshold.
    conf = min(1.0, (adx_trend_threshold - adx_val) / adx_trend_threshold)
    return RegimeRead(MarketRegime.RANGE, max(0.0, conf), adx_val, atr_pct)
