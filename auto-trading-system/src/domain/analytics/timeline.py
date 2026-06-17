# Layer 1 — Domain (analytics/timeline)
"""Pure historical-setup analysis: grade EMA-cross setups over a full price
series and summarise win rates. No I/O, Decimal in / float-free where it counts.

This is the engine behind the Timeline Analyst: it replays the whole price
history, finds every entry setup, grades each against the REAL price that
followed, and reports the measured win rate. The number it produces is an
honest historical frequency — the basis for the win-probability entry gate.
"""
from __future__ import annotations

from decimal import Decimal

from domain.analytics.indicators import ema
from domain.strategy.base import SignalAction


class GradedSetup:
    """One historical setup graded against the price that followed."""

    __slots__ = ("index", "action", "won", "move_pct")

    def __init__(self, index: int, action: SignalAction, won: bool, move_pct: Decimal) -> None:
        self.index = index
        self.action = action
        self.won = won
        self.move_pct = move_pct


def ema_cross_setups(
    prices: list[Decimal],
    fast: int = 12,
    slow: int = 26,
    horizon: int = 10,
    edge: Decimal = Decimal("0.001"),
) -> list[GradedSetup]:
    """Find every EMA(fast/slow) cross and grade it by the move ``horizon`` bars
    later. A BUY wins if price rose ≥ edge; a SELL wins if price fell ≥ edge.
    Linear-time: EMAs computed once, then a single pass."""
    n = len(prices)
    if n < slow + horizon + 2:
        return []
    ef = ema(prices, fast)
    es = ema(prices, slow)
    out: list[GradedSetup] = []
    for i in range(slow, n - horizon):
        entry = prices[i]
        if entry <= 0:
            continue
        crossed_up = ef[i - 1] <= es[i - 1] and ef[i] > es[i]
        crossed_dn = ef[i - 1] >= es[i - 1] and ef[i] < es[i]
        if not (crossed_up or crossed_dn):
            continue
        future = prices[i + horizon]
        move = (future - entry) / entry
        if crossed_up:
            out.append(GradedSetup(i, SignalAction.BUY, move >= edge, move))
        else:
            out.append(GradedSetup(i, SignalAction.SELL, -move >= edge, move))
    return out


def _win_rate(setups: list[GradedSetup]) -> Decimal | None:
    if not setups:
        return None
    wins = sum(1 for s in setups if s.won)
    return (Decimal(wins) / Decimal(len(setups))).quantize(Decimal("0.0001"))


def summarize(
    setups: list[GradedSetup], past_n: int = 50, recent_n: int = 50
) -> dict[str, object]:
    """Split the most recent ``past_n + recent_n`` setups into an older 'past'
    block and a newer 'recent' block, returning win rates and a blended p_win.

    p_win is the win rate over the combined sample — the figure the entry gate
    compares against its floor."""
    window = setups[-(past_n + recent_n):]
    past = window[:past_n] if len(window) > recent_n else window[: max(0, len(window) - recent_n)]
    recent = window[-recent_n:]
    combined = window
    return {
        "total_setups": len(setups),
        "sample": len(combined),
        "past_n": len(past),
        "recent_n": len(recent),
        "past_win_rate": str(_win_rate(past)) if _win_rate(past) is not None else None,
        "recent_win_rate": str(_win_rate(recent)) if _win_rate(recent) is not None else None,
        "p_win": str(_win_rate(combined)) if _win_rate(combined) is not None else None,
        "wins": sum(1 for s in combined if s.won),
        "losses": sum(1 for s in combined if not s.won),
    }
