# Layer 1 — Domain (analytics/emotion)
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class MarketEmotion(StrEnum):
    FEAR = "FEAR"
    GREED = "GREED"
    NEUTRAL = "NEUTRAL"
    PANIC = "PANIC"
    EUPHORIA = "EUPHORIA"


def classify_emotion(
    volatility: Decimal,
    momentum: Decimal,
) -> MarketEmotion:
    if volatility > Decimal("0.05") and momentum < Decimal("-0.03"):
        return MarketEmotion.PANIC
    if volatility > Decimal("0.05") and momentum > Decimal("0.03"):
        return MarketEmotion.EUPHORIA
    if momentum < Decimal("-0.01"):
        return MarketEmotion.FEAR
    if momentum > Decimal("0.01"):
        return MarketEmotion.GREED
    return MarketEmotion.NEUTRAL
