# Tests — pure headline sentiment scorer
from __future__ import annotations

from decimal import Decimal

from domain.analytics.sentiment import classify_sentiment, score_headlines


def test_bullish_headlines_positive():
    s = score_headlines(["Bitcoin surges to record high as ETF inflows soar"])
    assert s > Decimal("0")
    assert classify_sentiment(s) in ("BULLISH", "VERY_BULLISH")


def test_bearish_headlines_negative():
    s = score_headlines(["Crypto market crashes; exchange hacked, lawsuit filed"])
    assert s < Decimal("0")
    assert classify_sentiment(s) in ("BEARISH", "VERY_BEARISH")


def test_neutral_when_no_keywords():
    assert score_headlines(["The conference will be held next week"]) == Decimal("0")
    assert score_headlines([]) == Decimal("0")


def test_score_bounded():
    s = score_headlines(["surge rally gain", "crash plunge dump"])  # balanced
    assert Decimal("-1") <= s <= Decimal("1")
    assert s == Decimal("0")  # 3 bull vs 3 bear
