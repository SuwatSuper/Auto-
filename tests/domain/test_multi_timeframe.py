# Tests — multi-timeframe trend features (U4)
from __future__ import annotations

from decimal import Decimal

from domain.analytics.multi_timeframe import (
    DEFAULT_FACTORS,
    TimeframeRead,
    _stdev_over_mean,
    all_timeframes_agree,
    confluence_score,
    mtf_feature_vector,
    multi_timeframe_reads,
    resample_closes,
    timeframe_read,
)

D = Decimal


def _ramp(n: int, start: float = 100.0, step: float = 1.0) -> list[Decimal]:
    return [Decimal(str(start + i * step)) for i in range(n)]


# ── resampling ───────────────────────────────────────────────────────
def test_resample_factor_one_is_identity() -> None:
    closes = _ramp(10)
    assert resample_closes(closes, 1) == closes
    assert resample_closes(closes, 0) == closes  # clamp


def test_resample_takes_last_of_each_full_bucket() -> None:
    closes = [D(str(i)) for i in range(10)]  # 0..9
    # factor 3 → buckets [0,1,2],[3,4,5],[6,7,8]; last of each = 2,5,8 (9 dropped)
    assert resample_closes(closes, 3) == [D("2"), D("5"), D("8")]


def test_resample_drops_trailing_partial_bucket() -> None:
    assert resample_closes(_ramp(7), 3) == [_ramp(7)[2], _ramp(7)[5]]


# ── single timeframe read ────────────────────────────────────────────
def test_warmup_returns_neutral_read() -> None:
    r = timeframe_read(_ramp(5), 1)
    assert r.direction == 0 and r.strength == D("0") and r.warming_up


def test_uptrend_read_is_bullish() -> None:
    r = timeframe_read(_ramp(80), 1)
    assert r.direction == 1
    assert r.strength > 0
    assert r.ema_gap > 0
    assert r.bars == 80


def test_downtrend_read_is_bearish() -> None:
    r = timeframe_read(_ramp(80, start=200.0, step=-1.0), 1)
    assert r.direction == -1 and r.ema_gap < 0


def test_resampled_timeframe_needs_enough_buckets() -> None:
    # 80 bars / factor 5 = 16 resampled bars < slow+1 (27) → warming up
    r = timeframe_read(_ramp(80), 5)
    assert r.warming_up and r.bars == 16


# ── multi-timeframe aggregation ──────────────────────────────────────
def test_multi_reads_one_per_factor() -> None:
    reads = multi_timeframe_reads(_ramp(2000), DEFAULT_FACTORS)
    assert [r.factor for r in reads] == list(DEFAULT_FACTORS)


def test_confluence_positive_in_clean_uptrend() -> None:
    reads = multi_timeframe_reads(_ramp(3000), DEFAULT_FACTORS)
    score = confluence_score(reads)
    assert score > 0
    assert all_timeframes_agree(reads)


def test_confluence_negative_in_downtrend() -> None:
    reads = multi_timeframe_reads(_ramp(3000, start=4000.0, step=-1.0), DEFAULT_FACTORS)
    assert confluence_score(reads) < 0


def test_confluence_zero_when_all_warming_up() -> None:
    reads = multi_timeframe_reads(_ramp(10), DEFAULT_FACTORS)
    assert confluence_score(reads) == D("0")
    assert not all_timeframes_agree(reads)


def test_confluence_empty_reads_is_zero() -> None:
    assert confluence_score([]) == D("0")


def test_stdev_over_mean_degenerate_inputs() -> None:
    # reusable helper guards: too-short and non-positive-mean windows → 0
    assert _stdev_over_mean([D("100")]) == D("0")
    assert _stdev_over_mean([D("-5"), D("5")]) == D("0")  # mean 0 → guarded
    assert _stdev_over_mean([D("100"), D("102")]) > D("0")


def test_confluence_higher_timeframe_dominates() -> None:
    # 1m says bull (small weight), 60m says bear (large weight) → net bearish.
    reads = [
        TimeframeRead(1, 1, D("1"), D("0.1"), D("0"), 100),
        TimeframeRead(60, -1, D("1"), D("-0.1"), D("0"), 100),
    ]
    assert confluence_score(reads) < 0


def test_all_agree_requires_nonzero_direction() -> None:
    reads = [TimeframeRead(1, 0, D("0"), D("0"), D("0"), 5)]
    assert not all_timeframes_agree(reads)
    reads2 = [TimeframeRead(1, 1, D("0.5"), D("0.01"), D("0"), 80),
              TimeframeRead(5, 1, D("0.5"), D("0.01"), D("0"), 80)]
    assert all_timeframes_agree(reads2)


# ── ML feature vector ────────────────────────────────────────────────
def test_feature_vector_shape_and_values() -> None:
    feats = mtf_feature_vector(_ramp(3000), DEFAULT_FACTORS)
    # 2 features per factor + 1 aggregate score
    assert len(feats) == 2 * len(DEFAULT_FACTORS) + 1
    assert feats[-1] > 0  # aggregate confluence bullish in an uptrend
