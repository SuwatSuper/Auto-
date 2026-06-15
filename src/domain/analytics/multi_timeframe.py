# Layer 1 — Domain (analytics/multi_timeframe)
"""Multi-timeframe (MTF) trend features from a single close-price stream.

A 1-minute signal that disagrees with the 1-hour trend is a weaker bet. This
module resamples one fine-grained close series into coarser timeframes and
reads the trend on each, then combines them into a single higher-timeframe-
biased confluence score. No new data is needed — it is pure compute over the
price stream the agent already has, so it feeds every strategy AND becomes
extra features for the U2 win-probability model.

Pure & deterministic: Decimal math, no I/O.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from domain.analytics.indicators import ema

_ZERO = Decimal("0")
_ONE = Decimal("1")
DEFAULT_FACTORS: tuple[int, ...] = (1, 5, 15, 60)


def _clamp01(x: Decimal) -> Decimal:
    return _ZERO if x < _ZERO else _ONE if x > _ONE else x


@dataclass(frozen=True)
class TimeframeRead:
    """One timeframe's trend verdict, derived from the resampled closes."""

    factor: int
    direction: int       # +1 bull / -1 bear / 0 neutral (or warming up)
    strength: Decimal    # [0, 1]
    ema_gap: Decimal     # (ema_fast - ema_slow) / ema_slow
    volatility: Decimal  # stdev/mean of the recent resampled window
    bars: int            # resampled bar count available

    @property
    def warming_up(self) -> bool:
        return self.direction == 0 and self.strength == _ZERO and self.ema_gap == _ZERO


def resample_closes(closes: Sequence[Decimal], factor: int) -> list[Decimal]:
    """Down-sample to one close per ``factor`` bars (last close of each FULL
    bucket). ``factor <= 1`` returns the series unchanged. A trailing partial
    bucket is dropped so every emitted bar represents a complete period.
    """
    if factor <= 1:
        return list(closes)
    n = len(closes)
    full = n // factor
    return [closes[(i + 1) * factor - 1] for i in range(full)]


def _stdev_over_mean(window: Sequence[Decimal]) -> Decimal:
    if len(window) < 2:
        return _ZERO
    mean = sum(window, _ZERO) / Decimal(len(window))
    if mean <= 0:
        return _ZERO
    var = sum(((x - mean) ** 2 for x in window), _ZERO) / Decimal(len(window))
    return var.sqrt() / mean


def timeframe_read(
    closes: Sequence[Decimal],
    factor: int,
    *,
    fast: int = 12,
    slow: int = 26,
    vol_n: int = 20,
) -> TimeframeRead:
    """Read the EMA-cross trend on the ``factor``-resampled series.

    Insufficient resampled history yields a neutral, warming-up read — never a
    fabricated direction.
    """
    res = resample_closes(closes, factor)
    bars = len(res)
    if bars < slow + 1:
        return TimeframeRead(factor, 0, _ZERO, _ZERO, _ZERO, bars)
    ef = ema(res, fast)[-1]
    es = ema(res, slow)[-1]
    gap = (ef - es) / es if es != 0 else _ZERO
    direction = 1 if ef > es else -1 if ef < es else 0
    strength = _clamp01(abs(gap) * Decimal(25))
    vol = _stdev_over_mean(res[-vol_n:]) if bars >= 2 else _ZERO
    return TimeframeRead(factor, direction, strength, gap, vol, bars)


def multi_timeframe_reads(
    closes: Sequence[Decimal],
    factors: Sequence[int] = DEFAULT_FACTORS,
    *,
    fast: int = 12,
    slow: int = 26,
    vol_n: int = 20,
) -> list[TimeframeRead]:
    """One :class:`TimeframeRead` per requested timeframe factor."""
    return [timeframe_read(closes, f, fast=fast, slow=slow, vol_n=vol_n) for f in factors]


def confluence_score(reads: Sequence[TimeframeRead]) -> Decimal:
    """Combine timeframe reads into one score in [-1, +1].

    Each read contributes ``direction * strength`` weighted by its timeframe
    factor, so the higher timeframe sets the bias (a classic top-down view).
    Warming-up timeframes contribute nothing. Returns 0 when no timeframe has a
    usable read.
    """
    num = _ZERO
    den = _ZERO
    for r in reads:
        w = Decimal(max(1, r.factor))
        num += Decimal(r.direction) * r.strength * w
        den += w
    if den <= 0:
        return _ZERO
    return (num / den).quantize(Decimal("0.000001"))


def all_timeframes_agree(reads: Sequence[TimeframeRead]) -> bool:
    """True only when every NON-warming-up timeframe points the same way (and at
    least one has a direction). Strong alignment across timeframes."""
    dirs = {r.direction for r in reads if r.direction != 0}
    return len(dirs) == 1


def mtf_feature_vector(
    closes: Sequence[Decimal],
    factors: Sequence[int] = DEFAULT_FACTORS,
) -> list[float]:
    """Flat per-timeframe features for the ML model: [dir*strength, volatility]
    for each factor, followed by the aggregate confluence score."""
    reads = multi_timeframe_reads(closes, factors)
    out: list[float] = []
    for r in reads:
        out.append(float(Decimal(r.direction) * r.strength))
        out.append(float(r.volatility))
    out.append(float(confluence_score(reads)))
    return out
