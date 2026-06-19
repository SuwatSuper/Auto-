# Layer 1 — Domain (strategy/reversion_ls)
"""Long/short mean reversion: RSI(14) extremes, ATR bracket, BOTH directions.

Oversold (RSI < oversold) → buy the dip (long); overbought (RSI > overbought) →
sell the rip (short). "Buy low, sell high" in either order. Thresholds are
tunable so the same engine can be re-fit per market.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.strategy.base import Signal, SignalAction, StrategyContext
from domain.strategy.trend_following import OhlcvSignal

_HOLD = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_setup")
_INSUF = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")


class ReversionLongShortStrategy:
    """RSI(14) reversion, long AND short.

    RSI < oversold   → BUY  (stop = entry − 1.5·ATR, take = entry + 2·ATR)
    RSI > overbought → SELL (stop = entry + 1.5·ATR, take = entry − 2·ATR)
    """

    _MIN_BARS = 16  # RSI(14) needs 15 bars; +1 for a stable last value

    def __init__(
        self, oversold: Decimal = Decimal("30"), overbought: Decimal = Decimal("70")
    ) -> None:
        self.oversold = oversold
        self.overbought = overbought

    def decide(self, ctx: StrategyContext) -> Signal:
        """Protocol-compatible method: returns HOLD (context lacks OHLCV)."""
        return _HOLD

    def decide_df(self, df: pd.DataFrame) -> OhlcvSignal:
        """Return a long/short OhlcvSignal from the latest OHLCV data."""
        if len(df) < self._MIN_BARS:
            return _INSUF
        try:
            rsi_df = ta.rsi(df, length=14)
            atr_df = ta.atr(df, length=14)
        except ValueError:
            return _INSUF

        rsi_val = Decimal(str(round(float(rsi_df["RSI_14"].iloc[-1]), 4)))
        atr_val = Decimal(str(round(float(atr_df.iloc[-1, 0]), 2)))
        if atr_val <= 0:
            return _HOLD
        entry = Decimal(str(round(float(df["close"].iloc[-1]), 2)))

        if rsi_val < self.oversold:
            stop = entry - Decimal("1.5") * atr_val
            take = entry + Decimal("2") * atr_val
            if stop >= entry:
                return _HOLD
            return OhlcvSignal(
                action=SignalAction.BUY,
                confidence=Decimal("1"),
                reason="rsi_oversold",
                stop_price=stop,
                take_profit_price=take,
            )
        if rsi_val > self.overbought:
            stop = entry + Decimal("1.5") * atr_val
            take = entry - Decimal("2") * atr_val
            if take <= 0 or stop <= entry:
                return _HOLD
            return OhlcvSignal(
                action=SignalAction.SELL,
                confidence=Decimal("1"),
                reason="rsi_overbought",
                stop_price=stop,
                take_profit_price=take,
            )
        return _HOLD
