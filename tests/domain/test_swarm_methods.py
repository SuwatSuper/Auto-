# Layer 1 — Domain (tests/domain/test_swarm_methods)
"""Tests for the pure chart-analysis method library used by the agent swarm."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.analytics.swarm_methods import (
    BEAR,
    BULL,
    METHOD_NAMES,
    METHODS,
    NEUTRAL,
    AnalysisRead,
    Candle,
    double_top_bottom,
    engulfing,
    run_method,
)


def _candles(closes: list[float]) -> list[Candle]:
    """Build OHLC candles from closes with small symmetric wicks."""
    out: list[Candle] = []
    for i, c in enumerate(closes):
        cd = Decimal(str(c))
        out.append(Candle(i * 1000, cd, cd * Decimal("1.002"), cd * Decimal("0.998"), cd))
    return out


def _ohlc(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    return [
        Candle(i * 1000, Decimal(str(o)), Decimal(str(h)), Decimal(str(low)), Decimal(str(c)))
        for i, (o, h, low, c) in enumerate(rows)
    ]


RISING = _candles([100 + i for i in range(80)])
FALLING = _candles([200 - i for i in range(80)])


def test_analysis_read_neutral_factory() -> None:
    r = AnalysisRead.neutral("hi")
    assert r.direction == NEUTRAL
    assert r.strength == Decimal("0")
    assert r.label == "hi"


def test_candle_as_dict_roundtrips_strings() -> None:
    c = Candle(1000, Decimal("10"), Decimal("12"), Decimal("9"), Decimal("11"))
    d = c.as_dict()
    assert d == {"ts_ms": 1000, "open": "10", "high": "12", "low": "9", "close": "11"}


def test_registry_has_thirteen_methods() -> None:
    assert len(METHODS) == 13
    assert len(METHOD_NAMES) == 13
    assert set(METHOD_NAMES) == set(METHODS)


@pytest.mark.parametrize("name", METHOD_NAMES)
def test_warming_up_returns_neutral(name: str) -> None:
    """With almost no data every method must report NEUTRAL — never a guess."""
    r = run_method(name, _candles([100.0, 100.5]))
    assert r.direction == NEUTRAL


@pytest.mark.parametrize("name", METHOD_NAMES)
def test_strength_always_in_unit_interval(name: str) -> None:
    for series in (RISING, FALLING):
        r = run_method(name, series)
        assert Decimal("0") <= r.strength <= Decimal("1")
        assert r.direction in (BULL, BEAR, NEUTRAL)
        assert isinstance(r.label, str) and r.label


def test_trend_methods_are_bullish_on_a_rising_market() -> None:
    for name in ("ema_cross", "momentum", "sma_slope", "donchian", "hh_ll_trend"):
        assert run_method(name, RISING).direction == BULL, name


def test_trend_methods_are_bearish_on_a_falling_market() -> None:
    for name in ("ema_cross", "momentum", "sma_slope", "donchian", "hh_ll_trend"):
        assert run_method(name, FALLING).direction == BEAR, name


def test_oscillators_flag_overbought_on_a_rising_market() -> None:
    # RSI / stochastic measure exhaustion: a relentless rise reads overbought.
    assert run_method("rsi", RISING).direction == BEAR
    assert run_method("stochastic", RISING).direction == BEAR


def test_run_method_unknown_name_is_neutral() -> None:
    r = run_method("does_not_exist", RISING)
    assert r.direction == NEUTRAL
    assert "unknown" in r.label


def test_engulfing_detects_bullish_pattern() -> None:
    # prev red (100→95), cur green engulfs it (94→101)
    r = engulfing(_ohlc([(100, 100, 95, 95), (94, 101, 94, 101)]))
    assert r.direction == BULL
    assert "engulfing" in r.label


def test_engulfing_detects_bearish_pattern() -> None:
    # prev green (95→100), cur red engulfs it (101→94)
    r = engulfing(_ohlc([(95, 100, 95, 100), (101, 101, 94, 94)]))
    assert r.direction == BEAR


def test_engulfing_neutral_when_no_pattern() -> None:
    assert engulfing(_ohlc([(100, 101, 99, 100), (100, 101, 99, 100)])).direction == NEUTRAL


def test_double_bottom_detected() -> None:
    left = [96, 94, 92, 90, 92, 94, 96, 95, 93, 91]
    mid = [98, 99, 100, 100, 99, 98, 97, 98, 99, 100]
    right = [95, 93, 91, 90, 92, 94, 96, 94, 92, 90]
    r = double_top_bottom(_candles([float(x) for x in left + mid + right]))
    assert r.direction == BULL
    assert "bottom" in r.label


def test_double_top_detected() -> None:
    left = [104, 106, 108, 110, 108, 106, 104, 105, 107, 109]
    mid = [102, 101, 100, 100, 101, 102, 103, 102, 101, 100]
    right = [105, 107, 109, 110, 108, 106, 104, 106, 108, 110]
    r = double_top_bottom(_candles([float(x) for x in left + mid + right]))
    assert r.direction == BEAR
    assert "top" in r.label


def test_bollinger_reverts_below_lower_band() -> None:
    from domain.analytics.swarm_methods import bollinger

    closes = [100.0] * 20 + [80.0]  # sharp drop below the band
    r = bollinger(_candles(closes))
    assert r.direction == BULL


def test_macd_bullish_on_rising_series() -> None:
    assert run_method("macd", RISING).direction == BULL
