# Layer 1 — Domain (strategy/ema_cross)
"""EMA crossover strategy: BUY on fast > slow cross, SELL on fast < slow cross."""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.indicators import ema
from domain.strategy.base import Signal, SignalAction, StrategyContext


class EmaCrossStrategy:
    """EMA crossover: BUY when fast EMA crosses above slow EMA, SELL on cross below."""

    def __init__(self, fast: int = 12, slow: int = 26) -> None:
        self.fast = fast
        self.slow = slow

    def decide(self, ctx: StrategyContext) -> Signal:
        """Return BUY/SELL/HOLD signal based on EMA crossover."""
        prices = ctx.prices
        if len(prices) < self.slow + 1:
            return Signal(action=SignalAction.HOLD, confidence=Decimal(0), reason="insufficient_data")

        fast_ema = ema(prices, self.fast)
        slow_ema = ema(prices, self.slow)

        prev_fast = fast_ema[-2]
        prev_slow = slow_ema[-2]
        curr_fast = fast_ema[-1]
        curr_slow = slow_ema[-1]

        spread = abs(curr_fast - curr_slow)
        if curr_slow > 0:
            confidence = min(Decimal(1), spread / curr_slow * Decimal(100))
        else:
            confidence = Decimal(0)

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return Signal(action=SignalAction.BUY, confidence=confidence, reason="ema_cross_up")
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return Signal(action=SignalAction.SELL, confidence=confidence, reason="ema_cross_down")
        return Signal(action=SignalAction.HOLD, confidence=Decimal(0), reason="no_cross")
