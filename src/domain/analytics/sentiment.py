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


def sentiment_size_factor(
    score: Decimal,
    *,
    min_factor: Decimal = Decimal("0.5"),
    max_factor: Decimal = Decimal("1.25"),
) -> Decimal:
    """Soft position-size multiplier from news sentiment — a FILTER, not a trigger.

    Strong-negative news shrinks the next entry toward ``min_factor`` (de-risk
    into a hostile tape); strong-positive news modestly confirms it up to
    ``max_factor``; neutral leaves size unchanged (1.0). Bounded by construction
    so sentiment can only nudge sizing, never dominate it, and the result still
    flows through the immutable risk caps downstream.

    ``score`` is clamped to [-1, +1]:
        score = -1 → min_factor      score = 0 → 1.0      score = +1 → max_factor
    """
    s = max(Decimal("-1"), min(Decimal("1"), score))
    one = Decimal("1")
    if s >= 0:
        return one + (max_factor - one) * s
    return one + (one - min_factor) * s


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


# Keyword lexicon for headline scoring (lowercase). Deliberately small and
# crypto-flavoured; this is a transparent heuristic, not an ML model.
_BULLISH_WORDS: frozenset[str] = frozenset({
    "surge", "surges", "soar", "soars", "rally", "rallies", "gain", "gains",
    "jump", "jumps", "rise", "rises", "rising", "soaring", "bull", "bullish",
    "record", "high", "highs", "ath", "breakout", "adopt", "adoption", "approve",
    "approved", "approval", "etf", "inflow", "inflows", "boost", "boosts",
    "optimistic", "support", "buy", "buying", "accumulate", "upgrade", "partnership",
    "milestone", "moon", "green", "recover", "recovery", "rebound", "outperform",
})
_BEARISH_WORDS: frozenset[str] = frozenset({
    "crash", "crashes", "plunge", "plunges", "plummet", "drop", "drops", "fall",
    "falls", "falling", "slump", "slumps", "tumble", "tumbles", "bear", "bearish",
    "low", "lows", "selloff", "sell-off", "dump", "dumps", "fear", "fears",
    "decline", "declines", "ban", "banned", "hack", "hacked", "exploit", "lawsuit",
    "sue", "sued", "reject", "rejected", "warn", "warning", "loss", "losses",
    "liquidation", "liquidated", "outflow", "outflows", "downgrade", "fraud",
    "scam", "collapse", "red", "weak", "selloffs",
})


def score_headlines(headlines: list[str]) -> Decimal:
    """Score a batch of news headlines to a sentiment value in [-1, 1].

    Pure function: counts bullish vs bearish keyword hits across all headlines
    and returns (bull - bear) / (bull + bear). Returns 0 (neutral) when no
    sentiment-bearing words are present or the input is empty.
    """
    bull = 0
    bear = 0
    for headline in headlines:
        for token in str(headline).lower().replace("-", " ").split():
            word = token.strip(".,!?:;\"'()[]")
            if word in _BULLISH_WORDS:
                bull += 1
            elif word in _BEARISH_WORDS:
                bear += 1
    total = bull + bear
    if total == 0:
        return Decimal("0")
    return (Decimal(bull - bear) / Decimal(total)).quantize(Decimal("0.0001"))
