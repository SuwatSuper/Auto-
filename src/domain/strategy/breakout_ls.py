# Layer 1 — Domain (strategy/breakout_ls)
"""Long/short Donchian breakout — trend-following in BOTH directions.

A close above the prior N-bar high opens a long (ride the up-leg); a close below
the prior N-bar low opens a short (ride the down-leg). Because new highs cluster
in uptrends and new lows in downtrends, this trades *with* the trend on each
side — the natural way to profit from both rising and falling markets. Each side
attaches an ATR bracket so risk is always capped.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.strategy.base import Signal, SignalAction, StrategyContext
from domain.strategy.trend_following import OhlcvSignal

_HOLD = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_setup")
_INSUF = OhlcvSignal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")


class BreakoutLongShortStrategy:
    """Donchian breakout, long AND short.

    close > prior N-bar high → BUY  (stop = entry − 2·ATR, take = entry + 3·ATR)
    close < prior N-bar low  → SELL (stop = entry + 2·ATR, take = entry − 3·ATR)
    """

    def __init__(self, channel: int = 20) -> None:
        self._n = channel
        self._min_bars = channel + 15  # channel lookback + ATR(14) warmup

    def decide(self, ctx: StrategyContext) -> Signal:
        """Protocol-compatible method: returns HOLD (context lacks OHLCV)."""
        return _HOLD

    def decide_df(self, df: pd.DataFrame) -> OhlcvSignal:
        """Return a long/short OhlcvSignal from the latest OHLCV data."""
        if len(df) < self._min_bars:
            return _INSUF
        try:
            atr_df = ta.atr(df, length=14)
        except ValueError:
            return _INSUF

        atr_val = Decimal(str(round(float(atr_df.iloc[-1, 0]), 2)))
        if atr_val <= 0:
            return _HOLD

        # Prior N-bar channel EXCLUDES the current bar (no same-bar lookahead).
        prior_high = float(df["high"].iloc[-(self._n + 1) : -1].max())
        prior_low = float(df["low"].iloc[-(self._n + 1) : -1].min())
        close = float(df["close"].iloc[-1])
        entry = Decimal(str(round(close, 2)))

        if close > prior_high:
            stop = entry - Decimal("2") * atr_val
            take = entry + Decimal("3") * atr_val
            if stop >= entry:
                return _HOLD
            return OhlcvSignal(
                action=SignalAction.BUY,
                confidence=Decimal("1"),
                reason="breakout_high",
                stop_price=stop,
                take_profit_price=take,
            )
        if close < prior_low:
            stop = entry + Decimal("2") * atr_val
            take = entry - Decimal("3") * atr_val
            if take <= 0 or stop <= entry:
                return _HOLD
            return OhlcvSignal(
                action=SignalAction.SELL,
                confidence=Decimal("1"),
                reason="breakdown_low",
                stop_price=stop,
                take_profit_price=take,
            )
        return _HOLD
