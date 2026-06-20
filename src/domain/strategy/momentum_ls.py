# Layer 1 — Domain (strategy/momentum_ls)
"""Long/short momentum: EMA(9/21) crossover, ATR bracket, trades BOTH directions.

Profit can come from either side of the market: a cross UP opens a long (ride the
rise), a cross DOWN opens a short (ride the fall). Each side attaches a symmetric
ATR bracket so the downside is always capped.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.strategy.base import Signal, SignalAction, StrategyContext
from domain.strategy.trend_following import OhlcvSignal

_HOLD = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_setup")
_INSUF = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")


class MomentumLongShortStrategy:
    """EMA(fast) vs EMA(slow) crossover, long AND short.

    cross up   → BUY  (stop = entry − 2·ATR, take = entry + 3·ATR)
    cross down → SELL (stop = entry + 2·ATR, take = entry − 3·ATR)
    """

    _FAST = 9
    _SLOW = 21
    _MIN_BARS = 23  # EMA(21) warmup + 1 bar for crossover detection

    def decide(self, ctx: StrategyContext) -> Signal:
        """Protocol-compatible method: returns HOLD (context lacks OHLCV)."""
        return _HOLD

    def decide_df(self, df: pd.DataFrame) -> OhlcvSignal:
        """Return a long/short OhlcvSignal from the latest OHLCV data."""
        if len(df) < self._MIN_BARS:
            return _INSUF
        try:
            ema_fast = ta.ema(df, length=self._FAST)[f"EMA_{self._FAST}"]
            ema_slow = ta.ema(df, length=self._SLOW)[f"EMA_{self._SLOW}"]
            atr_df = ta.atr(df, length=14)
        except ValueError:
            return _INSUF

        curr_fast, prev_fast = float(ema_fast.iloc[-1]), float(ema_fast.iloc[-2])
        curr_slow, prev_slow = float(ema_slow.iloc[-1]), float(ema_slow.iloc[-2])
        atr_val = Decimal(str(round(float(atr_df.iloc[-1, 0]), 2)))
        if atr_val <= 0:
            return _HOLD
        entry = Decimal(str(round(float(df["close"].iloc[-1]), 2)))

        cross_up = prev_fast <= prev_slow and curr_fast > curr_slow
        cross_down = prev_fast >= prev_slow and curr_fast < curr_slow

        if cross_up:
            stop = entry - Decimal("2") * atr_val
            take = entry + Decimal("3") * atr_val
            if stop >= entry:
                return _HOLD
            return OhlcvSignal(
                action=SignalAction.BUY,
                confidence=Decimal("1"),
                reason="ema_cross_up",
                stop_price=stop,
                take_profit_price=take,
            )
        if cross_down:
            stop = entry + Decimal("2") * atr_val
            take = entry - Decimal("3") * atr_val
            if take <= 0 or stop <= entry:
                return _HOLD
            return OhlcvSignal(
                action=SignalAction.SELL,
                confidence=Decimal("1"),
                reason="ema_cross_down",
                stop_price=stop,
                take_profit_price=take,
            )
        return _HOLD
