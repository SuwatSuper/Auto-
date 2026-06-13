# Layer 1 — Domain (strategy/trend_following)
"""Trend-following strategy: EMA(9/21) crossover confirmed by SuperTrend."""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.strategy.base import Signal, SignalAction, StrategyContext


class OhlcvSignal(Signal, frozen=True):
    """Signal extended with optional stop and take-profit prices."""

    stop_price: Decimal | None = None
    take_profit_price: Decimal | None = None


_HOLD = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_setup")
_INSUF = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")


class TrendFollowingStrategy:
    """Long when EMA(9) crosses above EMA(21) AND SuperTrend is bullish.

    stop        = SuperTrend line
    take_profit = entry + 1.5 * (entry - stop)
    Long-only (Bitkub spot).
    """

    _MIN_BARS = 22  # EMA(21) warmup + 1 for crossover detection

    def decide(self, ctx: StrategyContext) -> Signal:
        """Protocol-compatible method: returns HOLD (context lacks OHLCV)."""
        return _HOLD

    def decide_df(self, df: pd.DataFrame) -> OhlcvSignal:
        """Return an OhlcvSignal from the latest OHLCV data."""
        if len(df) < self._MIN_BARS:
            return _INSUF

        try:
            ema9 = ta.ema(df, length=9)["EMA_9"]
            ema21 = ta.ema(df, length=21)["EMA_21"]
            st = ta.supertrend(df)
        except ValueError:
            return _INSUF

        curr_fast, prev_fast = float(ema9.iloc[-1]), float(ema9.iloc[-2])
        curr_slow, prev_slow = float(ema21.iloc[-1]), float(ema21.iloc[-2])
        st_direction = float(st["trend"].iloc[-1])
        st_line = Decimal(str(round(st["line"].iloc[-1], 2)))

        cross_up = prev_fast <= prev_slow and curr_fast > curr_slow
        bullish = st_direction == 1.0

        if not (cross_up and bullish):
            return _HOLD

        entry = Decimal(str(round(df["close"].iloc[-1], 2)))
        stop = st_line
        if stop >= entry:
            return _HOLD

        take_profit = entry + Decimal("1.5") * (entry - stop)
        return OhlcvSignal(
            action=SignalAction.BUY,
            confidence=Decimal("1"),
            reason="ema_cross_supertrend",
            stop_price=stop,
            take_profit_price=take_profit,
        )
