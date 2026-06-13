# Layer 1 — Domain (strategy/breakout)
"""Breakout strategy: close > 20-bar high AND volume > 1.5 × SMA(volume, 20)."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.strategy.base import Signal, SignalAction, StrategyContext
from domain.strategy.trend_following import OhlcvSignal

_HOLD = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_setup")
_INSUF = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")

_MIN_BARS = 21  # 20-bar lookback + current bar


class BreakoutStrategy:
    """Long when close breaks above the 20-bar high AND volume confirms.

    stop        = entry - 2 * ATR(14)
    take_profit = entry + 3 * ATR(14)
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
            atr_df = ta.atr(df, length=14)
        except ValueError:
            return _INSUF

        # 20-bar high uses bars [-21:-1] (exclude current bar)
        prev_high = float(df["high"].iloc[-21:-1].max())
        curr_close = float(df["close"].iloc[-1])

        # Volume SMA(20) over previous 20 bars (exclude current)
        vol_sma20 = float(df["volume"].iloc[-21:-1].mean())
        curr_vol = float(df["volume"].iloc[-1])

        breakout = curr_close > prev_high
        vol_confirm = curr_vol > 1.5 * vol_sma20

        if not (breakout and vol_confirm):
            return _HOLD

        atr_val = Decimal(str(round(float(atr_df.iloc[-1, 0]), 2)))
        entry = Decimal(str(round(curr_close, 2)))
        stop = entry - Decimal("2") * atr_val
        if stop >= entry:
            return _HOLD

        take_profit = entry + Decimal("3") * atr_val
        return OhlcvSignal(
            action=SignalAction.BUY,
            confidence=Decimal("1"),
            reason="breakout_volume",
            stop_price=stop,
            take_profit_price=take_profit,
        )
