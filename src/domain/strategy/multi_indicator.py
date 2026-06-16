# Layer 1 — Domain (strategy/multi_indicator)
"""Multi-indicator confluence entry signal.

Combines several INDEPENDENT indicator "lines" computed over the recent price
history into one honest agreement score, so an entry leans on more than a single
crossover:

  1. EMA momentum   — fast EMA vs slow EMA
  2. Trend          — price vs the slow trend EMA
  3. MACD histogram — sign of (macd − signal)
  4. RSI momentum   — mid-zone bias (overbought/oversold are ambiguous → no vote)

The more lines that agree on a direction, the higher the confidence
(``agreeing_votes / total_lines``). This is a MEASURED confluence of the
indicators over real history — never a promise that the trade will win.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from domain.analytics.indicators import ema, macd, rsi_wilder
from domain.strategy.base import SignalAction

_RSI_OVERBOUGHT = Decimal("70")
_RSI_OVERSOLD = Decimal("30")
_RSI_MID = Decimal("50")


@dataclass(frozen=True)
class ConfluenceResult:
    """One multi-indicator verdict. ``confidence`` = agreeing votes / total lines."""

    action: SignalAction
    confidence: Decimal
    buy_votes: int
    sell_votes: int
    total: int
    detail: str


def multi_indicator_signal(
    prices: list[Decimal] | tuple[Decimal, ...],
    fast: int = 12,
    slow: int = 26,
    trend: int = 50,
    rsi_period: int = 14,
    min_votes: int = 2,
) -> ConfluenceResult:
    """Score the confluence of 4 indicator lines over ``prices``.

    Returns BUY/SELL only when at least ``min_votes`` lines agree AND outvote the
    other side; otherwise HOLD. Pure and deterministic — no I/O, no look-ahead
    (every indicator reads only the supplied history)."""
    total = 4
    need = max(slow, trend, rsi_period) + 2
    n = len(prices)
    if n < need:
        return ConfluenceResult(
            action=SignalAction.HOLD, confidence=Decimal(0),
            buy_votes=0, sell_votes=0, total=total, detail=f"อุ่นเครื่อง {n}/{need}",
        )

    ef = ema(prices, fast)
    es = ema(prices, slow)
    et = ema(prices, trend)
    _, _, hist = macd(prices, fast=fast, slow=slow)
    rsis = rsi_wilder(prices, rsi_period)
    last = prices[-1]

    buy = 0
    sell = 0
    lines: list[str] = []

    # 1. EMA momentum (fast vs slow)
    if ef[-1] > es[-1]:
        buy += 1
        lines.append("EMA↑")
    elif ef[-1] < es[-1]:
        sell += 1
        lines.append("EMA↓")

    # 2. Trend (price vs slow trend EMA)
    if last > et[-1]:
        buy += 1
        lines.append("เทรนด์↑")
    elif last < et[-1]:
        sell += 1
        lines.append("เทรนด์↓")

    # 3. MACD histogram sign
    h = hist[-1]
    if h.is_finite() and h > 0:
        buy += 1
        lines.append("MACD+")
    elif h.is_finite() and h < 0:
        sell += 1
        lines.append("MACD−")

    # 4. RSI momentum — mid-zone bias only (extremes are ambiguous: an overbought
    # market can keep ripping or snap back, so it casts no vote).
    r = rsis[-1]
    if r.is_finite():
        if _RSI_MID < r < _RSI_OVERBOUGHT:
            buy += 1
            lines.append("RSI↑")
        elif _RSI_OVERSOLD < r < _RSI_MID:
            sell += 1
            lines.append("RSI↓")

    detail = f"{buy}↑/{sell}↓ · " + " ".join(lines)
    if buy >= min_votes and buy > sell:
        return ConfluenceResult(
            action=SignalAction.BUY, confidence=Decimal(buy) / Decimal(total),
            buy_votes=buy, sell_votes=sell, total=total, detail=detail,
        )
    if sell >= min_votes and sell > buy:
        return ConfluenceResult(
            action=SignalAction.SELL, confidence=Decimal(sell) / Decimal(total),
            buy_votes=buy, sell_votes=sell, total=total, detail=detail,
        )
    return ConfluenceResult(
        action=SignalAction.HOLD, confidence=Decimal(0),
        buy_votes=buy, sell_votes=sell, total=total, detail=detail,
    )
