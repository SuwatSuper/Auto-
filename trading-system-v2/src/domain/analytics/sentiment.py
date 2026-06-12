# Layer 1 — Domain (analytics/sentiment)
from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class SentimentLabel(StrEnum):
    VERY_BULLISH = "VERY_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    VERY_BEARISH = "VERY_BEARISH"


def classify_sentiment(score: Decimal) -> SentimentLabel:
    if score >= Decimal("0.6"):
        return SentimentLabel.VERY_BULLISH
    if score >= Decimal("0.2"):
        return SentimentLabel.BULLISH
    if score >= Decimal("-0.2"):
        return SentimentLabel.NEUTRAL
    if score >= Decimal("-0.6"):
        return SentimentLabel.BEARISH
    return SentimentLabel.VERY_BEARISH
