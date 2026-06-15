# Layer 1 — Domain (strategy/rsi_reversion)
"""RSI mean-reversion strategy: BUY when oversold (<30), SELL when overbought (>70)."""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.indicators import rsi_wilder
from domain.strategy.base import Signal, SignalAction, StrategyContext


class RsiReversionStrategy:
    """Mean-reversion based on Wilder RSI levels."""

    def __init__(self, oversold: Decimal = Decimal(30), overbought: Decimal = Decimal(70), period: int = 14) -> None:
        self.oversold = oversold
        self.overbought = overbought
        self.period = period

    def decide(self, ctx: StrategyContext) -> Signal:
        """Return BUY if RSI < oversold, SELL if RSI > overbought, else HOLD."""
        prices = ctx.prices
        if len(prices) < self.period + 2:
            return Signal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")

        rsi = rsi_wilder(prices, self.period)
        latest = rsi[-1]

        if str(latest) == "NaN":
            return Signal(action=SignalAction.HOLD, confidence=Decimal(0), reason="rsi_nan")

        if latest < self.oversold:
            confidence = (self.oversold - latest) / self.oversold
            return Signal(action=SignalAction.BUY, confidence=min(Decimal(1), confidence), reason="rsi_oversold")
        if latest > self.overbought:
            confidence = (latest - self.overbought) / (Decimal(100) - self.overbought)
            return Signal(action=SignalAction.SELL, confidence=min(Decimal(1), confidence), reason="rsi_overbought")
        return Signal(action=SignalAction.HOLD, confidence=Decimal(0), reason="rsi_neutral")
