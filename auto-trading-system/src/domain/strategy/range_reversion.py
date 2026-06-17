# Layer 1 — Domain (strategy/range_reversion)
"""Range-reversion strategy: RSI(14) < 30 when market regime is RANGE."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.analytics.regime import MarketRegime, classify
from domain.strategy.base import Signal, SignalAction, StrategyContext
from domain.strategy.trend_following import OhlcvSignal

_HOLD = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_setup")
_INSUF = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")

_MIN_BARS = 51  # regime.classify requires 51 bars


class RangeReversionStrategy:
    """Long when RSI(14) < 30 and market regime is RANGE.

    stop        = min(low of last 10 bars) - 0.5 * ATR(14)
    take_profit = EMA(21)
    Long-only (Bitkub spot).
    """

    def decide(self, ctx: StrategyContext) -> Signal:
        """Protocol-compatible method: returns HOLD (context lacks OHLCV)."""
        return _HOLD

    def decide_df(self, df: pd.DataFrame) -> OhlcvSignal:
        """Return an OhlcvSignal from the latest OHLCV data."""
        if len(df) < _MIN_BARS:
            return _INSUF

        try:
            rsi_df = ta.rsi(df, length=14)
            atr_df = ta.atr(df, length=14)
            ema21_df = ta.ema(df, length=21)
        except ValueError:
            return _INSUF

        regime = classify(df)
        if regime != MarketRegime.RANGE:
            return _HOLD

        rsi_val = float(rsi_df["RSI_14"].iloc[-1])
        if rsi_val >= 30.0:
            return _HOLD

        entry = Decimal(str(round(float(df["close"].iloc[-1]), 2)))
        atr_val = Decimal(str(round(float(atr_df.iloc[-1, 0]), 2)))
        low10 = Decimal(str(round(float(df["low"].iloc[-10:].min()), 2)))
        stop = low10 - Decimal("0.5") * atr_val
        if stop >= entry:
            return _HOLD

        take_profit = Decimal(str(round(float(ema21_df["EMA_21"].iloc[-1]), 2)))
        if take_profit <= entry:
            return _HOLD

        return OhlcvSignal(
            action=SignalAction.BUY,
            confidence=Decimal("1"),
            reason="range_rsi_oversold",
            stop_price=stop,
            take_profit_price=take_profit,
        )
