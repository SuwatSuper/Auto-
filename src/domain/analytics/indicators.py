# Layer 1 — Domain (analytics/indicators)
"""Pure technical indicator functions over Sequence[Decimal]."""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal


def ema(values: Sequence[Decimal], period: int) -> list[Decimal]:
    """Exponential moving average.

    Returns list same length as values; first period-1 entries are None-padded
    (here we use the first value as seed and grow from index 0).
    """
    if not values or period <= 0:
        return []
    k = Decimal(2) / Decimal(period + 1)
    result: list[Decimal] = []
    current = values[0]
    result.append(current)
    for v in values[1:]:
        current = v * k + current * (Decimal(1) - k)
        result.append(current)
    return result


def rsi_wilder(values: Sequence[Decimal], period: int = 14) -> list[Decimal]:
    """Wilder RSI. Returns list same length as values (NaN → Decimal('NaN') for first period)."""
    if len(values) < period + 1:
        return [Decimal("NaN")] * len(values)

    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(Decimal(0), delta))
        losses.append(max(Decimal(0), -delta))

    # Seed with simple average of first period
    avg_gain = sum(gains[:period]) / Decimal(period)
    avg_loss = sum(losses[:period]) / Decimal(period)

    rsi_values: list[Decimal] = [Decimal("NaN")] * period

    def _rsi(ag: Decimal, al: Decimal) -> Decimal:
        if al == 0:
            return Decimal(100)
        rs = ag / al
        return Decimal(100) - Decimal(100) / (Decimal(1) + rs)

    rsi_values.append(_rsi(avg_gain, avg_loss))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * Decimal(period - 1) + gains[i]) / Decimal(period)
        avg_loss = (avg_loss * Decimal(period - 1) + losses[i]) / Decimal(period)
        rsi_values.append(_rsi(avg_gain, avg_loss))

    return rsi_values


def macd(
    values: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    """MACD = fast_ema - slow_ema; signal = ema(macd, signal); hist = macd - signal.

    Returns (macd_line, signal_line, histogram), all same length as values.
    Signal and histogram will be NaN for first entries.
    """
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)

    macd_line = [f - s for f, s in zip(fast_ema, slow_ema, strict=False)]
    signal_line = ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line, strict=False)]
    return macd_line, signal_line, histogram


def max_drawdown(equity_curve: Sequence[Decimal]) -> Decimal:
    """Compute maximum drawdown as a fraction [0, 1].

    max_drawdown = max((peak - trough) / peak) over all peaks.
    """
    if len(equity_curve) < 2:
        return Decimal(0)
    peak = equity_curve[0]
    max_dd = Decimal(0)
    for v in equity_curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def win_rate(trade_pnls: Sequence[Decimal]) -> Decimal:
    """Fraction of trades with PnL > 0."""
    if not trade_pnls:
        return Decimal(0)
    wins = sum(1 for p in trade_pnls if p > 0)
    return Decimal(wins) / Decimal(len(trade_pnls))


def expectancy(trade_pnls: Sequence[Decimal]) -> Decimal:
    """Average PnL per trade."""
    if not trade_pnls:
        return Decimal(0)
    return sum(trade_pnls, Decimal(0)) / Decimal(len(trade_pnls))
