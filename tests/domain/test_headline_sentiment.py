# Tests — pure headline sentiment scorer
from __future__ import annotations

from decimal import Decimal

from domain.analytics.sentiment import (
    classify_sentiment,
    score_headlines,
    sentiment_size_factor,
)


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


# ── U6: sentiment as a soft sizing filter ────────────────────────────
def test_size_factor_neutral_is_one():
    assert sentiment_size_factor(Decimal("0")) == Decimal("1")


def test_size_factor_negative_shrinks_to_floor():
    assert sentiment_size_factor(Decimal("-1")) == Decimal("0.5")
    assert sentiment_size_factor(Decimal("-0.5")) == Decimal("0.75")
    assert sentiment_size_factor(Decimal("-0.3")) < Decimal("1")


def test_size_factor_positive_confirms_up_to_cap():
    assert sentiment_size_factor(Decimal("1")) == Decimal("1.25")
    assert Decimal("1") < sentiment_size_factor(Decimal("0.4")) < Decimal("1.25")


def test_size_factor_clamps_out_of_range_scores():
    assert sentiment_size_factor(Decimal("5")) == Decimal("1.25")    # clamp +1
    assert sentiment_size_factor(Decimal("-5")) == Decimal("0.5")    # clamp -1


def test_size_factor_is_bounded_filter_not_trigger():
    for raw in ("-1", "-0.6", "0", "0.6", "1"):
        f = sentiment_size_factor(Decimal(raw))
        assert Decimal("0.5") <= f <= Decimal("1.25")  # only ever a nudge
