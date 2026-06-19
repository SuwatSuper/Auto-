# Layer 1 — Domain (analytics/indicator_lines)
"""Pure technical-indicator *lines* — the analyst agent's computational knowledge.

Every public function here is a deterministic, side-effect-free computation over
``Sequence[Decimal]`` price/volume history (no I/O, no ``time``/``random``/``os``),
so it is safe to call from Layer-1 domain code and trivially testable. Decimals are
used throughout — never ``float`` — to keep indicator math exact and reproducible.

The module covers the nine families of indicator lines an analyst reasons about
(see :mod:`domain.analytics.indicator_catalog` for the human-readable, Thai
knowledge base that describes each one):

  1. Moving averages ....... SMA, EMA, WMA, HMA, SMMA, CMA, VWAP
  2. MACD .................. MACD line, signal line, histogram, zero line
  3. Bollinger Bands ....... upper / middle / lower
  4. Oscillators ........... RSI, Stochastic %K/%D, CCI, Williams %R, RSI-based MA
  5. Ichimoku .............. Tenkan, Kijun, Chikou, Senkou A, Senkou B
  6. DMI / ADX ............. +DI, -DI, ADX
  7. Channels / Envelopes .. Keltner, Donchian, Envelopes
  8. Fibonacci / Pivots .... Pivot points (P, R1-R5, S1-S5), retracement, extension
  9. Trailing stops ........ Parabolic SAR, Chandelier Exit, SuperTrend

Returned lists are always the same length as the input; warm-up positions where a
value is not yet defined hold ``Decimal('NaN')`` (test with ``value.is_finite()``).
This mirrors :mod:`domain.analytics.indicators` so the two compose cleanly. The
single-value helpers (pivots, Fibonacci) return dataclasses / dicts instead.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from domain.analytics.indicators import ema, macd, rsi_wilder

# Re-export the close-only primitives that already live in ``indicators`` so a
# caller can reach the whole indicator vocabulary from one module.
__all__ = [
    "NAN",
    "MACD_ZERO_LINE",
    "RSI_OVERBOUGHT",
    "RSI_OVERSOLD",
    "ADX_TREND_THRESHOLD",
    "ema",
    "macd",
    "rsi_wilder",
    "sma",
    "wma",
    "hma",
    "smma",
    "cma",
    "vwap",
    "bollinger_bands",
    "rsi_based_ma",
    "stochastic",
    "cci",
    "williams_r",
    "ichimoku",
    "dmi_adx",
    "true_range",
    "atr",
    "keltner_channels",
    "donchian_channels",
    "envelopes",
    "pivot_points",
    "fibonacci_retracement",
    "fibonacci_extension",
    "parabolic_sar",
    "chandelier_exit",
    "supertrend",
    "BollingerBands",
    "Stochastic",
    "Ichimoku",
    "DMI",
    "Channel",
    "PivotPoints",
    "ParabolicSAR",
    "ChandelierExit",
    "SuperTrend",
]

#: Not-a-number sentinel for warm-up positions (matches ``indicators.rsi_wilder``).
NAN = Decimal("NaN")

#: The MACD zero / centre line — a fixed level, not a series.
MACD_ZERO_LINE = Decimal(0)

#: Conventional oscillator threshold lines.
RSI_OVERBOUGHT = Decimal(70)
RSI_OVERSOLD = Decimal(30)
#: ADX above this level is the usual "a real trend is present" confirmation.
ADX_TREND_THRESHOLD = Decimal(25)


def _aligned(*series: Sequence[Decimal]) -> int:
    """Validate that every series has the same length; return that length."""
    lengths = {len(s) for s in series}
    if len(lengths) > 1:
        raise ValueError(f"series length mismatch: {sorted(lengths)}")
    return lengths.pop() if lengths else 0


# ---------------------------------------------------------------------------
# Group 1 — Moving-average lines
# ---------------------------------------------------------------------------

def sma(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """Simple Moving Average — arithmetic mean of the last ``period`` values.

    NaN-safe: a window containing a non-finite value yields ``NaN``.
    """
    n = len(values)
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        if any(not x.is_finite() for x in window):
            continue
        out[i] = sum(window, Decimal(0)) / Decimal(period)
    return out


def wma(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """Weighted Moving Average — linearly weights recent values heaviest."""
    n = len(values)
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    denom = Decimal(period * (period + 1) // 2)
    for i in range(period - 1, n):
        window = values[i - period + 1 : i + 1]
        if any(not x.is_finite() for x in window):
            continue
        weighted = sum((window[j] * Decimal(j + 1) for j in range(period)), Decimal(0))
        out[i] = weighted / denom
    return out


def hma(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """Hull Moving Average — ``WMA(2·WMA(n/2) − WMA(n), sqrt(n))``; very low lag."""
    n = len(values)
    out = [NAN] * n
    if period <= 1 or n < period:
        return out
    half = max(1, period // 2)
    sqrt_p = max(1, int(Decimal(period).sqrt().to_integral_value(rounding=ROUND_HALF_UP)))
    wma_half = wma(values, half)
    wma_full = wma(values, period)
    raw: list[Decimal] = []
    for i in range(n):
        a, b = wma_half[i], wma_full[i]
        raw.append(Decimal(2) * a - b if a.is_finite() and b.is_finite() else NAN)
    return wma(raw, sqrt_p)


def smma(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """Smoothed Moving Average (Wilder's RMA) — heavily damped, long-memory."""
    n = len(values)
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    prev = sum(values[:period], Decimal(0)) / Decimal(period)
    out[period - 1] = prev
    for i in range(period, n):
        prev = (prev * Decimal(period - 1) + values[i]) / Decimal(period)
        out[i] = prev
    return out


def cma(values: Sequence[Decimal]) -> list[Decimal]:
    """Cumulative Moving Average — running mean of all data seen so far."""
    n = len(values)
    out = [NAN] * n
    total = Decimal(0)
    for i, v in enumerate(values):
        total += v
        out[i] = total / Decimal(i + 1)
    return out


def vwap(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    volume: Sequence[Decimal],
) -> list[Decimal]:
    """Volume-Weighted Average Price — cumulative, session-based.

    Uses the typical price ``(H+L+C)/3`` weighted by traded volume.
    """
    n = _aligned(high, low, close, volume)
    out = [NAN] * n
    cum_pv = Decimal(0)
    cum_v = Decimal(0)
    for i in range(n):
        typical = (high[i] + low[i] + close[i]) / Decimal(3)
        cum_pv += typical * volume[i]
        cum_v += volume[i]
        if cum_v > 0:
            out[i] = cum_pv / cum_v
    return out


# ---------------------------------------------------------------------------
# Group 3 — Bollinger Bands
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BollingerBands:
    """Three parallel volatility bands around an SMA middle line."""

    upper: list[Decimal]
    middle: list[Decimal]
    lower: list[Decimal]


def bollinger_bands(
    values: Sequence[Decimal],
    period: int = 20,
    num_std: Decimal = Decimal(2),
) -> BollingerBands:
    """Bollinger Bands: SMA middle ± ``num_std`` population standard deviations."""
    n = len(values)
    middle = sma(values, period)
    upper = [NAN] * n
    lower = [NAN] * n
    if period > 0 and n >= period:
        for i in range(period - 1, n):
            m = middle[i]
            if not m.is_finite():
                continue
            window = values[i - period + 1 : i + 1]
            variance = sum(((x - m) ** 2 for x in window), Decimal(0)) / Decimal(period)
            sd = variance.sqrt()
            upper[i] = m + num_std * sd
            lower[i] = m - num_std * sd
    return BollingerBands(upper=upper, middle=middle, lower=lower)


# ---------------------------------------------------------------------------
# Group 4 — Oscillators
# ---------------------------------------------------------------------------

def rsi_based_ma(
    values: Sequence[Decimal],
    rsi_period: int = 14,
    ma_period: int = 14,
) -> list[Decimal]:
    """Moving average of the RSI line — a smoothed RSI signal line."""
    return sma(rsi_wilder(values, rsi_period), ma_period)


@dataclass(frozen=True)
class Stochastic:
    """Stochastic oscillator fast %K and its %D signal line."""

    k: list[Decimal]
    d: list[Decimal]


def stochastic(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    k_period: int = 14,
    d_period: int = 3,
) -> Stochastic:
    """Stochastic oscillator. %K = position of close within the N-bar range;
    %D = SMA(%K). Both run 0–100. A flat range yields a neutral 50."""
    n = _aligned(high, low, close)
    k = [NAN] * n
    if k_period > 0 and n >= k_period:
        for i in range(k_period - 1, n):
            hh = max(high[i - k_period + 1 : i + 1])
            ll = min(low[i - k_period + 1 : i + 1])
            rng = hh - ll
            k[i] = (close[i] - ll) / rng * Decimal(100) if rng > 0 else Decimal(50)
    return Stochastic(k=k, d=sma(k, d_period))


def cci(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    period: int = 20,
) -> list[Decimal]:
    """Commodity Channel Index — deviation of typical price from its SMA."""
    n = _aligned(high, low, close)
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    typical = [(high[i] + low[i] + close[i]) / Decimal(3) for i in range(n)]
    const = Decimal("0.015")
    for i in range(period - 1, n):
        window = typical[i - period + 1 : i + 1]
        mean = sum(window, Decimal(0)) / Decimal(period)
        mad = sum((abs(x - mean) for x in window), Decimal(0)) / Decimal(period)
        out[i] = (typical[i] - mean) / (const * mad) if mad > 0 else Decimal(0)
    return out


def williams_r(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal]:
    """Williams %R — close relative to the N-bar high/low range, runs 0 to −100."""
    n = _aligned(high, low, close)
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        hh = max(high[i - period + 1 : i + 1])
        ll = min(low[i - period + 1 : i + 1])
        rng = hh - ll
        out[i] = (hh - close[i]) / rng * Decimal(-100) if rng > 0 else Decimal(-50)
    return out


# ---------------------------------------------------------------------------
# Group 5 — Ichimoku Cloud (5 lines)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Ichimoku:
    """The five Ichimoku lines.

    ``senkou_a``/``senkou_b`` are returned at the bar where they are *computed*;
    a chart plots them ``displacement`` bars into the future. ``chikou`` is the
    close shifted ``displacement`` bars into the past (``chikou[i] == close[i+disp]``).
    """

    tenkan: list[Decimal]
    kijun: list[Decimal]
    chikou: list[Decimal]
    senkou_a: list[Decimal]
    senkou_b: list[Decimal]


def _midpoint_hl(
    high: Sequence[Decimal], low: Sequence[Decimal], period: int, n: int
) -> list[Decimal]:
    """(highest high + lowest low) / 2 over a rolling ``period`` window."""
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    for i in range(period - 1, n):
        hh = max(high[i - period + 1 : i + 1])
        ll = min(low[i - period + 1 : i + 1])
        out[i] = (hh + ll) / Decimal(2)
    return out


def ichimoku(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    conversion: int = 9,
    base: int = 26,
    span_b_period: int = 52,
    displacement: int = 26,
) -> Ichimoku:
    """Ichimoku Kinko Hyo — Tenkan, Kijun, Chikou, Senkou A and Senkou B."""
    n = _aligned(high, low, close)
    tenkan = _midpoint_hl(high, low, conversion, n)
    kijun = _midpoint_hl(high, low, base, n)
    senkou_b = _midpoint_hl(high, low, span_b_period, n)
    senkou_a = [NAN] * n
    for i in range(n):
        if tenkan[i].is_finite() and kijun[i].is_finite():
            senkou_a[i] = (tenkan[i] + kijun[i]) / Decimal(2)
    chikou = [NAN] * n
    for i in range(n):
        j = i + displacement
        if j < n:
            chikou[i] = close[j]
    return Ichimoku(
        tenkan=tenkan, kijun=kijun, chikou=chikou, senkou_a=senkou_a, senkou_b=senkou_b
    )


# ---------------------------------------------------------------------------
# Group 6 — DMI / ADX  (and the shared True-Range / ATR helpers)
# ---------------------------------------------------------------------------

def true_range(
    high: Sequence[Decimal], low: Sequence[Decimal], close: Sequence[Decimal]
) -> list[Decimal]:
    """True Range — max of (H−L), |H−Cprev|, |L−Cprev|."""
    n = _aligned(high, low, close)
    tr = [NAN] * n
    if n == 0:
        return tr
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    return tr


def atr(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal]:
    """Average True Range (Wilder smoothing). First value lands at index ``period-1``.

    Seeded with the simple mean of the first ``period`` true ranges, matching the
    vendored ``.ta`` stub so ATR-based lines agree across the codebase.
    """
    n = _aligned(high, low, close)
    out = [NAN] * n
    if period <= 0 or n < period:
        return out
    tr = true_range(high, low, close)
    prev = sum(tr[:period], Decimal(0)) / Decimal(period)
    out[period - 1] = prev
    for i in range(period, n):
        prev = (prev * Decimal(period - 1) + tr[i]) / Decimal(period)
        out[i] = prev
    return out


@dataclass(frozen=True)
class DMI:
    """Directional Movement Index: +DI, −DI and the trend-strength ADX line."""

    plus_di: list[Decimal]
    minus_di: list[Decimal]
    adx: list[Decimal]


def dmi_adx(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    period: int = 14,
) -> DMI:
    """Wilder's +DI / −DI / ADX. ADX measures trend *strength* regardless of side."""
    n = _aligned(high, low, close)
    plus_di = [NAN] * n
    minus_di = [NAN] * n
    adx = [NAN] * n
    if period <= 0 or n <= period:
        return DMI(plus_di=plus_di, minus_di=minus_di, adx=adx)

    tr = true_range(high, low, close)
    plus_dm = [Decimal(0)] * n
    minus_dm = [Decimal(0)] * n
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down

    def _wilder_sum(seq: list[Decimal]) -> list[Decimal]:
        smoothed = [NAN] * n
        prev = sum(seq[1 : period + 1], Decimal(0))
        smoothed[period] = prev
        for i in range(period + 1, n):
            prev = prev - prev / Decimal(period) + seq[i]
            smoothed[i] = prev
        return smoothed

    str_tr = _wilder_sum(tr)
    str_pdm = _wilder_sum(plus_dm)
    str_mdm = _wilder_sum(minus_dm)

    dx = [NAN] * n
    for i in range(period, n):
        if str_tr[i].is_finite() and str_tr[i] > 0:
            pdi = Decimal(100) * str_pdm[i] / str_tr[i]
            mdi = Decimal(100) * str_mdm[i] / str_tr[i]
            plus_di[i] = pdi
            minus_di[i] = mdi
            denom = pdi + mdi
            dx[i] = Decimal(100) * abs(pdi - mdi) / denom if denom > 0 else Decimal(0)

    if n >= 2 * period:
        window = dx[period : 2 * period]
        if all(x.is_finite() for x in window):
            prev = sum(window, Decimal(0)) / Decimal(period)
            adx[2 * period - 1] = prev
            for i in range(2 * period, n):
                if dx[i].is_finite():
                    prev = (prev * Decimal(period - 1) + dx[i]) / Decimal(period)
                    adx[i] = prev
    return DMI(plus_di=plus_di, minus_di=minus_di, adx=adx)


# ---------------------------------------------------------------------------
# Group 7 — Channels / Envelopes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Channel:
    """A generic upper / middle / lower price channel."""

    upper: list[Decimal]
    middle: list[Decimal]
    lower: list[Decimal]


def keltner_channels(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    ema_period: int = 20,
    atr_period: int = 10,
    multiplier: Decimal = Decimal(2),
) -> Channel:
    """Keltner Channels — EMA middle line ± ``multiplier`` × ATR."""
    n = _aligned(high, low, close)
    if ema_period <= 0 or n == 0:
        # ``ema`` returns an empty list for a non-positive period; keep all three
        # lines the same length (all-NaN) so the caller never hits an IndexError.
        return Channel(upper=[NAN] * n, middle=[NAN] * n, lower=[NAN] * n)
    middle = ema(list(close), ema_period)
    band = atr(high, low, close, atr_period)
    upper = [NAN] * n
    lower = [NAN] * n
    for i in range(n):
        if band[i].is_finite():
            upper[i] = middle[i] + multiplier * band[i]
            lower[i] = middle[i] - multiplier * band[i]
    return Channel(upper=upper, middle=middle, lower=lower)


def donchian_channels(
    high: Sequence[Decimal], low: Sequence[Decimal], period: int = 20
) -> Channel:
    """Donchian Channels — highest high / lowest low over N bars, plus their mid."""
    n = _aligned(high, low)
    upper = [NAN] * n
    middle = [NAN] * n
    lower = [NAN] * n
    if period > 0 and n >= period:
        for i in range(period - 1, n):
            u = max(high[i - period + 1 : i + 1])
            low_v = min(low[i - period + 1 : i + 1])
            upper[i] = u
            lower[i] = low_v
            middle[i] = (u + low_v) / Decimal(2)
    return Channel(upper=upper, middle=middle, lower=lower)


def envelopes(
    values: Sequence[Decimal],
    period: int = 20,
    percent: Decimal = Decimal("2.5"),
) -> Channel:
    """Percentage Envelopes — SMA middle line shifted ±``percent``%."""
    n = len(values)
    middle = sma(values, period)
    upper = [NAN] * n
    lower = [NAN] * n
    factor = percent / Decimal(100)
    for i in range(n):
        if middle[i].is_finite():
            upper[i] = middle[i] * (Decimal(1) + factor)
            lower[i] = middle[i] * (Decimal(1) - factor)
    return Channel(upper=upper, middle=middle, lower=lower)


# ---------------------------------------------------------------------------
# Group 8 — Fibonacci / Pivot levels
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PivotPoints:
    """Classic floor pivot with five resistance and five support levels.

    R2..R5 / S2..S5 use the consistent ``P ± n·(H−L)`` extension convention.
    """

    p: Decimal
    r1: Decimal
    r2: Decimal
    r3: Decimal
    r4: Decimal
    r5: Decimal
    s1: Decimal
    s2: Decimal
    s3: Decimal
    s4: Decimal
    s5: Decimal


def pivot_points(high: Decimal, low: Decimal, close: Decimal) -> PivotPoints:
    """Floor pivots from the *prior* period's high/low/close."""
    p = (high + low + close) / Decimal(3)
    rng = high - low
    return PivotPoints(
        p=p,
        r1=Decimal(2) * p - low,
        r2=p + rng,
        r3=p + Decimal(2) * rng,
        r4=p + Decimal(3) * rng,
        r5=p + Decimal(4) * rng,
        s1=Decimal(2) * p - high,
        s2=p - rng,
        s3=p - Decimal(2) * rng,
        s4=p - Decimal(3) * rng,
        s5=p - Decimal(4) * rng,
    )


_RETRACEMENT_RATIOS = (
    Decimal("0"),
    Decimal("0.236"),
    Decimal("0.382"),
    Decimal("0.5"),
    Decimal("0.618"),
    Decimal("0.786"),
    Decimal("1"),
)
_EXTENSION_RATIOS = (Decimal("1.618"), Decimal("2.618"), Decimal("4.236"))


def fibonacci_retracement(
    swing_high: Decimal, swing_low: Decimal
) -> dict[Decimal, Decimal]:
    """Retracement price levels for an up-swing (measured down from the high).

    Keyed by ratio: ``0`` → swing high, ``1`` → swing low.
    """
    rng = swing_high - swing_low
    return {ratio: swing_high - ratio * rng for ratio in _RETRACEMENT_RATIOS}


def fibonacci_extension(
    swing_low: Decimal, swing_high: Decimal
) -> dict[Decimal, Decimal]:
    """Extension / profit-target levels projected above an up-swing high.

    ``161.8% → high + 0.618·range``, ``261.8% → high + 1.618·range``, etc.
    """
    rng = swing_high - swing_low
    return {ratio: swing_high + (ratio - Decimal(1)) * rng for ratio in _EXTENSION_RATIOS}


# ---------------------------------------------------------------------------
# Group 9 — Trailing-stop / reversal lines
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParabolicSAR:
    """Parabolic SAR dots and the active trend (+1 long, −1 short) per bar."""

    sar: list[Decimal]
    trend: list[Decimal]


def parabolic_sar(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    step: Decimal = Decimal("0.02"),
    max_step: Decimal = Decimal("0.2"),
) -> ParabolicSAR:
    """Wilder's Parabolic SAR. The dot flips sides the bar price crosses it."""
    n = _aligned(high, low)
    sar = [NAN] * n
    trend = [NAN] * n
    if n < 2:
        return ParabolicSAR(sar=sar, trend=trend)

    rising = high[1] >= high[0]
    af = step
    ep = high[1] if rising else low[1]
    sar_val = low[0] if rising else high[0]
    sar[1] = sar_val
    trend[1] = Decimal(1) if rising else Decimal(-1)

    for i in range(2, n):
        sar_val = sar_val + af * (ep - sar_val)
        if rising:
            sar_val = min(sar_val, low[i - 1], low[i - 2])
            if low[i] < sar_val:
                rising = False
                sar_val = ep
                ep = low[i]
                af = step
            elif high[i] > ep:
                ep = high[i]
                af = min(af + step, max_step)
        else:
            sar_val = max(sar_val, high[i - 1], high[i - 2])
            if high[i] > sar_val:
                rising = True
                sar_val = ep
                ep = high[i]
                af = step
            elif low[i] < ep:
                ep = low[i]
                af = min(af + step, max_step)
        sar[i] = sar_val
        trend[i] = Decimal(1) if rising else Decimal(-1)
    return ParabolicSAR(sar=sar, trend=trend)


@dataclass(frozen=True)
class ChandelierExit:
    """Chandelier Exit trailing stops for long and short positions."""

    long_stop: list[Decimal]
    short_stop: list[Decimal]


def chandelier_exit(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    period: int = 22,
    multiplier: Decimal = Decimal(3),
) -> ChandelierExit:
    """Chandelier Exit: ``HH(N) − k·ATR`` (long) and ``LL(N) + k·ATR`` (short)."""
    n = _aligned(high, low, close)
    band = atr(high, low, close, period)
    long_stop = [NAN] * n
    short_stop = [NAN] * n
    if period > 0:
        for i in range(period - 1, n):
            if band[i].is_finite():
                hh = max(high[i - period + 1 : i + 1])
                ll = min(low[i - period + 1 : i + 1])
                long_stop[i] = hh - multiplier * band[i]
                short_stop[i] = ll + multiplier * band[i]
    return ChandelierExit(long_stop=long_stop, short_stop=short_stop)


@dataclass(frozen=True)
class SuperTrend:
    """SuperTrend line and its direction (+1 bullish / green, −1 bearish / red)."""

    line: list[Decimal]
    trend: list[Decimal]


def supertrend(
    high: Sequence[Decimal],
    low: Sequence[Decimal],
    close: Sequence[Decimal],
    period: int = 10,
    multiplier: Decimal = Decimal(3),
) -> SuperTrend:
    """ATR-based SuperTrend (pure-Decimal twin of the vendored stub)."""
    n = _aligned(high, low, close)
    line = [NAN] * n
    trend = [NAN] * n
    band = atr(high, low, close, period)
    prev_line: Decimal | None = None
    prev_dir = Decimal(1)
    for i in range(n):
        if not band[i].is_finite():
            continue
        hl2 = (high[i] + low[i]) / Decimal(2)
        upper = hl2 + multiplier * band[i]
        lower = hl2 - multiplier * band[i]
        c = close[i]
        if prev_line is not None:
            if prev_dir == 1:
                lower = max(lower, prev_line)
            else:
                upper = min(upper, prev_line)
        if prev_line is None:
            direction = Decimal(1)
            st = lower
        elif prev_dir == 1:
            direction, st = (Decimal(-1), upper) if c < prev_line else (Decimal(1), lower)
        else:
            direction, st = (Decimal(1), lower) if c > prev_line else (Decimal(-1), upper)
        line[i] = st
        trend[i] = direction
        prev_line = st
        prev_dir = direction
    return SuperTrend(line=line, trend=trend)
