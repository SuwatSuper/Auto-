# Layer 1 — Domain (tests/domain/test_analytics_domain)
"""Tests for emotion, market_mode, sentiment, and achievements analytics."""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.achievements import Achievement, check_achievements
from domain.analytics.emotion import MarketEmotion, classify_emotion
from domain.analytics.market_mode import MarketMode, detect_market_mode
from domain.analytics.sentiment import SentimentLabel, classify_sentiment

# --- Emotion ---

def test_emotion_panic() -> None:
    e = classify_emotion(volatility=Decimal("0.06"), momentum=Decimal("-0.04"))
    assert e == MarketEmotion.PANIC


def test_emotion_euphoria() -> None:
    e = classify_emotion(volatility=Decimal("0.06"), momentum=Decimal("0.04"))
    assert e == MarketEmotion.EUPHORIA


def test_emotion_fear() -> None:
    e = classify_emotion(volatility=Decimal("0.01"), momentum=Decimal("-0.02"))
    assert e == MarketEmotion.FEAR


def test_emotion_greed() -> None:
    e = classify_emotion(volatility=Decimal("0.01"), momentum=Decimal("0.02"))
    assert e == MarketEmotion.GREED


def test_emotion_neutral() -> None:
    e = classify_emotion(volatility=Decimal("0.01"), momentum=Decimal("0.00"))
    assert e == MarketEmotion.NEUTRAL


# --- MarketMode ---

def test_market_mode_unknown_zero_atr() -> None:
    m = detect_market_mode(Decimal("100"), Decimal("90"), Decimal("0"), Decimal("100"))
    assert m == MarketMode.UNKNOWN


def test_market_mode_unknown_zero_price() -> None:
    m = detect_market_mode(Decimal("100"), Decimal("90"), Decimal("1"), Decimal("0"))
    assert m == MarketMode.UNKNOWN


def test_market_mode_ranging() -> None:
    m = detect_market_mode(Decimal("100"), Decimal("100"), Decimal("1"), Decimal("100000"))
    assert m == MarketMode.RANGING


def test_market_mode_trending_up() -> None:
    m = detect_market_mode(Decimal("110"), Decimal("90"), Decimal("1"), Decimal("100"))
    assert m == MarketMode.TRENDING_UP


def test_market_mode_trending_down() -> None:
    m = detect_market_mode(Decimal("90"), Decimal("110"), Decimal("1"), Decimal("100"))
    assert m == MarketMode.TRENDING_DOWN


# --- Sentiment ---

def test_sentiment_very_bullish() -> None:
    assert classify_sentiment(Decimal("0.7")) == SentimentLabel.VERY_BULLISH


def test_sentiment_bullish() -> None:
    assert classify_sentiment(Decimal("0.3")) == SentimentLabel.BULLISH


def test_sentiment_neutral() -> None:
    assert classify_sentiment(Decimal("0.0")) == SentimentLabel.NEUTRAL


def test_sentiment_bearish() -> None:
    assert classify_sentiment(Decimal("-0.4")) == SentimentLabel.BEARISH


def test_sentiment_very_bearish() -> None:
    assert classify_sentiment(Decimal("-0.8")) == SentimentLabel.VERY_BEARISH


# --- Achievements ---

def test_achievements_none() -> None:
    earned = check_achievements(0, 0, Decimal("-100"), False)
    assert earned == []


def test_achievements_first_win() -> None:
    earned = check_achievements(1, 0, Decimal("0"), False)
    assert Achievement.FIRST_WIN in earned
    assert Achievement.PROFITABLE_MONTH not in earned


def test_achievements_ten_wins() -> None:
    earned = check_achievements(10, 0, Decimal("0"), False)
    assert Achievement.FIRST_WIN in earned
    assert Achievement.TEN_WINS in earned


def test_achievements_hundred_wins() -> None:
    earned = check_achievements(100, 0, Decimal("0"), False)
    assert Achievement.HUNDRED_WINS in earned


def test_achievements_streak_5() -> None:
    earned = check_achievements(0, 5, Decimal("0"), False)
    assert Achievement.STREAK_5 in earned
    assert Achievement.STREAK_10 not in earned


def test_achievements_streak_10() -> None:
    earned = check_achievements(0, 10, Decimal("0"), False)
    assert Achievement.STREAK_5 in earned
    assert Achievement.STREAK_10 in earned


def test_achievements_drawdown_survived() -> None:
    earned = check_achievements(0, 0, Decimal("0"), True)
    assert Achievement.DRAWDOWN_SURVIVED in earned


def test_achievements_profitable_month() -> None:
    earned = check_achievements(0, 0, Decimal("100"), False)
    assert Achievement.PROFITABLE_MONTH in earned
