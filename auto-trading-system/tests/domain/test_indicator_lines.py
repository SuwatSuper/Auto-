# Layer 1 — Domain (tests/domain/test_indicator_lines)
"""Tests for the pure indicator-line library (all nine families)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.analytics import indicator_lines as il
from tests._fixtures.ohlcv import build_ohlcv


def _d(x: object) -> Decimal:
    return Decimal(str(x))


def _ramp(start: int, step: int, n: int) -> list[Decimal]:
    return [Decimal(start) + Decimal(step) * Decimal(i) for i in range(n)]


def _const(v: int, n: int) -> list[Decimal]:
    return [Decimal(v)] * n


def _finite(values: list[Decimal]) -> list[Decimal]:
    return [v for v in values if v.is_finite()]


# Realistic deterministic OHLC (Decimal) shared by several tests.
_DF = build_ohlcv(n=120, seed=42)
_H = [_d(x) for x in _DF["high"]]
_L = [_d(x) for x in _DF["low"]]
_C = [_d(x) for x in _DF["close"]]
_V = [_d(x) for x in _DF["volume"]]


# ---------------------------------------------------------------------------
# Group 1 — Moving averages
# ---------------------------------------------------------------------------

def test_sma_known_values() -> None:
    result = il.sma([_d(1), _d(2), _d(3), _d(4)], period=2)
    assert not result[0].is_finite()
    assert result[1:] == [_d("1.5"), _d("2.5"), _d("3.5")]


def test_sma_constant() -> None:
    result = il.sma(_const(5, 6), period=3)
    assert all(v == _d(5) for v in _finite(result))


def test_sma_invalid_or_short_is_all_nan() -> None:
    assert all(not v.is_finite() for v in il.sma(_ramp(1, 1, 5), period=0))
    assert all(not v.is_finite() for v in il.sma(_ramp(1, 1, 2), period=5))


def test_sma_is_nan_safe() -> None:
    values = [il.NAN, _d(1), _d(2), _d(3)]
    result = il.sma(values, period=2)
    assert not result[1].is_finite()  # window touches the NaN
    assert result[3] == _d("2.5")


def test_wma_weights_recent_heaviest() -> None:
    # (1*1 + 2*2 + 3*3) / (1+2+3) = 14/6
    result = il.wma([_d(1), _d(2), _d(3)], period=3)
    assert result[-1] == _d(14) / _d(6)


def test_wma_constant_and_invalid() -> None:
    assert all(v == _d(7) for v in _finite(il.wma(_const(7, 5), period=3)))
    assert all(not v.is_finite() for v in il.wma(_ramp(1, 1, 2), period=5))


def test_hma_tracks_linear_ramp() -> None:
    prices = _ramp(100, 1, 40)
    result = il.hma(prices, period=9)
    # On a perfectly linear ramp the low-lag HMA sits very close to the last price.
    assert abs(result[-1] - prices[-1]) < _d("0.5")


def test_hma_constant_and_invalid() -> None:
    assert all(abs(v - _d(50)) < _d("0.0001") for v in _finite(il.hma(_const(50, 40), period=9)))
    assert all(not v.is_finite() for v in il.hma(_ramp(1, 1, 40), period=1))


def test_smma_matches_wilder_recurrence() -> None:
    prices = _ramp(10, 2, 20)
    period = 5
    result = il.smma(prices, period)
    seed = sum(prices[:period], Decimal(0)) / Decimal(period)
    assert result[period - 1] == seed
    expected = (seed * Decimal(period - 1) + prices[period]) / Decimal(period)
    assert result[period] == expected


def test_smma_invalid() -> None:
    assert all(not v.is_finite() for v in il.smma(_ramp(1, 1, 2), period=5))


def test_cma_running_mean() -> None:
    assert il.cma([_d(1), _d(2), _d(3), _d(4)]) == [_d(1), _d("1.5"), _d(2), _d("2.5")]
    assert il.cma([]) == []


def test_vwap_constant_price_equals_price() -> None:
    n = 5
    high = _const(100, n)
    low = _const(100, n)
    close = _const(100, n)
    vol = _ramp(1, 1, n)
    assert all(v == _d(100) for v in il.vwap(high, low, close, vol))


def test_vwap_length_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        il.vwap(_const(1, 3), _const(1, 2), _const(1, 3), _const(1, 3))


# ---------------------------------------------------------------------------
# Group 3 — Bollinger Bands
# ---------------------------------------------------------------------------

def test_bollinger_constant_collapses_bands() -> None:
    bb = il.bollinger_bands(_const(100, 30), period=20)
    assert bb.upper[-1] == bb.middle[-1] == bb.lower[-1] == _d(100)


def test_bollinger_middle_is_sma_and_width_positive() -> None:
    bb = il.bollinger_bands(_C, period=20)
    assert bb.middle == il.sma(_C, 20)
    assert bb.upper[-1] > bb.middle[-1] > bb.lower[-1]


def test_bollinger_short_history_all_nan() -> None:
    bb = il.bollinger_bands(_ramp(1, 1, 5), period=20)
    assert all(not v.is_finite() for v in bb.upper)


# ---------------------------------------------------------------------------
# Group 4 — Oscillators
# ---------------------------------------------------------------------------

def test_rsi_based_ma_length_and_finite_tail() -> None:
    result = il.rsi_based_ma(_C, rsi_period=14, ma_period=14)
    assert len(result) == len(_C)
    assert result[-1].is_finite()


def test_stochastic_top_bottom_and_flat() -> None:
    rising = _ramp(100, 1, 30)
    st = il.stochastic([c for c in rising], [c - _d(10) for c in rising], rising, 14, 3)
    assert st.k[-1] == _d(100)  # close at the very top of the range
    falling = _ramp(200, -1, 30)
    st2 = il.stochastic([c + _d(10) for c in falling], list(falling), falling, 14, 3)
    assert st2.k[-1] == _d(0)
    flat = il.stochastic(_const(5, 20), _const(5, 20), _const(5, 20), 14, 3)
    assert flat.k[-1] == _d(50)


def test_cci_finite_after_warmup() -> None:
    result = il.cci(_H, _L, _C, period=20)
    assert result[-1].is_finite()
    assert all(not v.is_finite() for v in il.cci(_H[:5], _L[:5], _C[:5], period=20))


def test_williams_r_top_is_zero_bottom_is_minus_100() -> None:
    rising = _ramp(100, 1, 30)
    top = il.williams_r(list(rising), [c - _d(10) for c in rising], rising, 14)
    assert top[-1] == _d(0)
    falling = _ramp(200, -1, 30)
    bottom = il.williams_r([c + _d(10) for c in falling], list(falling), falling, 14)
    assert bottom[-1] == _d(-100)


# ---------------------------------------------------------------------------
# Group 5 — Ichimoku
# ---------------------------------------------------------------------------

def test_ichimoku_midpoints_and_senkou_a() -> None:
    ich = il.ichimoku(_H, _L, _C)
    i = len(_C) - 1
    exp_tenkan = (max(_H[i - 8 : i + 1]) + min(_L[i - 8 : i + 1])) / _d(2)
    exp_kijun = (max(_H[i - 25 : i + 1]) + min(_L[i - 25 : i + 1])) / _d(2)
    assert ich.tenkan[-1] == exp_tenkan
    assert ich.kijun[-1] == exp_kijun
    assert ich.senkou_a[-1] == (ich.tenkan[-1] + ich.kijun[-1]) / _d(2)


def test_ichimoku_chikou_is_shifted_close() -> None:
    ich = il.ichimoku(_H, _L, _C, displacement=26)
    assert ich.chikou[0] == _C[26]
    assert not ich.chikou[-1].is_finite()  # no future close to borrow


# ---------------------------------------------------------------------------
# Group 6 — DMI / ADX & ATR
# ---------------------------------------------------------------------------

def test_true_range_first_bar_is_high_minus_low() -> None:
    tr = il.true_range(_H, _L, _C)
    assert tr[0] == _H[0] - _L[0]


def test_atr_positive_after_warmup_and_invalid() -> None:
    a = il.atr(_H, _L, _C, period=14)
    assert a[13].is_finite() and a[-1] > 0
    assert all(not v.is_finite() for v in il.atr(_H[:5], _L[:5], _C[:5], period=14))


def test_dmi_uptrend_and_downtrend_direction() -> None:
    up = _ramp(100, 2, 60)
    dmi_up = il.dmi_adx([c + _d(1) for c in up], [c - _d(1) for c in up], up, 14)
    assert dmi_up.plus_di[-1] > dmi_up.minus_di[-1]
    assert dmi_up.adx[-1].is_finite()
    down = _ramp(220, -2, 60)
    dmi_down = il.dmi_adx([c + _d(1) for c in down], [c - _d(1) for c in down], down, 14)
    assert dmi_down.minus_di[-1] > dmi_down.plus_di[-1]


def test_dmi_short_history_all_nan() -> None:
    dmi = il.dmi_adx(_H[:10], _L[:10], _C[:10], period=14)
    assert all(not v.is_finite() for v in dmi.plus_di)
    assert all(not v.is_finite() for v in dmi.adx)


# ---------------------------------------------------------------------------
# Group 7 — Channels / Envelopes
# ---------------------------------------------------------------------------

def test_keltner_band_ordering() -> None:
    kc = il.keltner_channels(_H, _L, _C, ema_period=20, atr_period=10)
    assert kc.upper[-1] > kc.middle[-1] > kc.lower[-1]


def test_keltner_non_positive_ema_period_is_all_nan() -> None:
    # A non-positive EMA period makes the middle line empty in ``ema``; the channel
    # must stay length-n (all NaN) rather than raising IndexError.
    kc = il.keltner_channels(_H, _L, _C, ema_period=0, atr_period=10)
    assert len(kc.upper) == len(kc.middle) == len(kc.lower) == len(_C)
    assert all(not v.is_finite() for v in kc.middle)


def test_donchian_extremes() -> None:
    dc = il.donchian_channels(_H, _L, period=20)
    i = len(_H) - 1
    assert dc.upper[-1] == max(_H[i - 19 : i + 1])
    assert dc.lower[-1] == min(_L[i - 19 : i + 1])
    assert dc.middle[-1] == (dc.upper[-1] + dc.lower[-1]) / _d(2)


def test_envelopes_percentage_offset() -> None:
    env = il.envelopes(_C, period=20, percent=Decimal("2.5"))
    mid = env.middle[-1]
    assert env.upper[-1] == mid * (Decimal(1) + Decimal("0.025"))
    assert env.lower[-1] == mid * (Decimal(1) - Decimal("0.025"))


# ---------------------------------------------------------------------------
# Group 8 — Fibonacci / Pivot
# ---------------------------------------------------------------------------

def test_pivot_points_known() -> None:
    pp = il.pivot_points(_d(110), _d(90), _d(100))
    assert pp.p == _d(100)
    assert (pp.r1, pp.s1) == (_d(110), _d(90))
    assert (pp.r2, pp.s2) == (_d(120), _d(80))
    assert (pp.r5, pp.s5) == (_d(180), _d(20))


def test_fibonacci_retracement_levels() -> None:
    levels = il.fibonacci_retracement(_d(100), _d(0))
    assert levels[Decimal("0")] == _d(100)
    assert levels[Decimal("0.5")] == _d(50)
    assert levels[Decimal("1")] == _d(0)
    assert levels[Decimal("0.618")] == _d("38.200")


def test_fibonacci_extension_levels() -> None:
    levels = il.fibonacci_extension(_d(0), _d(100))
    assert levels[Decimal("1.618")] == _d("161.800")
    assert levels[Decimal("2.618")] == _d("261.800")
    assert levels[Decimal("4.236")] == _d("423.600")


# ---------------------------------------------------------------------------
# Group 9 — Trailing stops
# ---------------------------------------------------------------------------

def test_parabolic_sar_trends_up_and_reverses() -> None:
    up = _ramp(100, 1, 30)
    psar_up = il.parabolic_sar([c + _d(1) for c in up], [c - _d(1) for c in up])
    assert psar_up.trend[-1] == _d(1)
    assert psar_up.sar[-1] < up[-1]  # SAR trails below price in an up-trend
    # Up then sharply down → the dot must flip to the short side at some point.
    highs = [c + _d(1) for c in up] + [c + _d(1) for c in _ramp(130, -3, 30)]
    lows = [c - _d(1) for c in up] + [c - _d(1) for c in _ramp(130, -3, 30)]
    psar = il.parabolic_sar(highs, lows)
    assert any(t == _d(-1) for t in _finite(psar.trend))


def test_parabolic_sar_too_short() -> None:
    psar = il.parabolic_sar([_d(1)], [_d(1)])
    assert all(not v.is_finite() for v in psar.sar)


def test_chandelier_exit_ordering() -> None:
    ce = il.chandelier_exit(_H, _L, _C, period=22, multiplier=Decimal(3))
    assert ce.long_stop[-1].is_finite()
    assert ce.long_stop[-1] < max(_H[-22:])
    assert ce.short_stop[-1] > min(_L[-22:])


def test_supertrend_direction_is_signed() -> None:
    sup = il.supertrend(_H, _L, _C)
    assert sup.trend[-1] in (_d(1), _d(-1))
    assert sup.line[-1] > 0


# ---------------------------------------------------------------------------
# Fidelity — the pure-Decimal math agrees with the vendored .ta stub
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Edge cases / defensive branches
# ---------------------------------------------------------------------------

def test_true_range_empty_input() -> None:
    assert il.true_range([], [], []) == []


def test_williams_r_short_history_all_nan() -> None:
    assert all(not v.is_finite() for v in il.williams_r(_H[:5], _L[:5], _C[:5], 14))


def test_ichimoku_short_history_leaves_long_lines_undefined() -> None:
    ich = il.ichimoku(_H[:20], _L[:20], _C[:20])
    assert all(not v.is_finite() for v in ich.senkou_b)  # 52-bar line never warms up


def test_bollinger_skips_windows_touching_a_nan() -> None:
    values = [_d(1), il.NAN, _d(2), _d(3), _d(4), _d(5)]
    bb = il.bollinger_bands(values, period=3)
    assert not bb.upper[2].is_finite()  # window [1, NaN, 2] is undefined
    assert bb.upper[-1].is_finite()


def test_parabolic_sar_flips_from_short_to_long() -> None:
    down = _ramp(200, -2, 30)
    up = _ramp(140, 2, 30)
    highs = [c + _d(1) for c in down] + [c + _d(1) for c in up]
    lows = [c - _d(1) for c in down] + [c - _d(1) for c in up]
    psar = il.parabolic_sar(highs, lows)
    assert psar.trend[-1] == _d(1)  # ended in an up-trend after the flip


def test_atr_matches_vendored_stub() -> None:
    import vendor_ta  # noqa: F401 — registers the .ta accessor

    mine = float(il.atr(_H, _L, _C, 14)[-1])
    theirs = float(_DF.ta.atr(length=14).iloc[-1])
    assert abs(mine - theirs) < 1e-6


def test_supertrend_matches_vendored_stub() -> None:
    import vendor_ta  # noqa: F401

    mine = il.supertrend(_H, _L, _C, period=10, multiplier=Decimal(3))
    theirs = _DF.ta.supertrend(length=10, multiplier=3.0)
    assert float(mine.trend[-1]) == float(theirs.iloc[-1, 1])
    assert abs(float(mine.line[-1]) - float(theirs.iloc[-1, 0])) < 1e-3
