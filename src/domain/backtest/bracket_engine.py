# Layer 1 — Domain (backtest/bracket_engine)
"""Bracket backtester — measures whether bracketed entries have real edge.

A *bracket* is an entry plus an attached take-profit (TP) and stop-loss (SL).
Given OHLC bars and a set of entry signals, this engine walks each trade forward
bar-by-bar and resolves it WIN (TP hit first), LOSS (SL hit first), or OPEN
(neither level touched within the holding horizon — marked-to-close on the last
bar of the window).

The honest yardstick is ``win_rate`` versus ``breakeven_rate``:

    breakeven_rate = (sl_bps + cost_bps) / (tp_bps + sl_bps)

where ``cost_bps`` is the ROUND-TRIP cost (fees + slippage on both legs). A
bracket has positive expectancy iff ``win_rate > breakeven_rate``. For a fixed
symmetric bracket the two statements are exactly equivalent; the engine also
reports the realised per-trade expectancy in bps so the verdict is auditable.

Pure Layer-1 domain: Decimal-only (no float), no I/O, no infra imports. The
caller supplies the entries (e.g. from a strategy) and the cost model in bps.
Conservative tie-break: within a bar the STOP is tested before the TP, so a bar
that straddles both levels resolves as a LOSS (matches domain.trading.paper).
"""
from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

_BPS = Decimal("10000")


class Direction(StrEnum):
    """Trade direction for a bracket."""

    LONG = "LONG"
    SHORT = "SHORT"


class TradeOutcome(StrEnum):
    """How a bracketed trade ended."""

    WIN = "WIN"
    LOSS = "LOSS"
    OPEN = "OPEN"


class Entry(BaseModel, frozen=True):
    """A bracketed entry: open at bar ``index`` with TP/SL distances in bps."""

    index: int
    direction: Direction
    tp_bps: Decimal
    sl_bps: Decimal


class BracketTrade(BaseModel, frozen=True):
    """The resolved result of a single bracketed trade."""

    entry_index: int
    exit_index: int
    direction: Direction
    entry_price: Decimal
    tp_price: Decimal
    sl_price: Decimal
    exit_price: Decimal
    outcome: TradeOutcome
    bars_held: int
    return_bps: Decimal  # net of cost_bps (round-trip fees + slippage)


class BracketResult(BaseModel, frozen=True):
    """Aggregate edge measurement for one set of bracketed entries."""

    name: str
    n_trades: int
    n_wins: int
    n_losses: int
    n_open: int
    win_rate: Decimal  # wins / (wins + losses) — comparable to breakeven_rate
    breakeven_rate: Decimal
    edge: bool  # win_rate > breakeven_rate
    expectancy_bps: Decimal  # mean net return over ALL trades (open marked-to-close)
    cost_bps: Decimal
    avg_bars_held: Decimal
    trades: tuple[BracketTrade, ...]


def breakeven_rate(tp_bps: Decimal, sl_bps: Decimal, cost_bps: Decimal) -> Decimal:
    """Win-rate needed to break even on a (tp, sl) bracket after round-trip cost.

    Solving ``p·(tp − cost) = (1 − p)·(sl + cost)`` gives
    ``p = (sl + cost) / (tp + sl)``. All inputs are in basis points.
    """
    denom = tp_bps + sl_bps
    if denom <= 0:
        raise ValueError("tp_bps + sl_bps must be > 0")
    return (sl_bps + cost_bps) / denom


def bracket_prices(
    entry_price: Decimal, direction: Direction, tp_bps: Decimal, sl_bps: Decimal
) -> tuple[Decimal, Decimal]:
    """Return the (take_profit_price, stop_loss_price) for an entry."""
    tp_frac = tp_bps / _BPS
    sl_frac = sl_bps / _BPS
    if direction == Direction.LONG:
        return (
            entry_price * (Decimal(1) + tp_frac),
            entry_price * (Decimal(1) - sl_frac),
        )
    return (
        entry_price * (Decimal(1) - tp_frac),
        entry_price * (Decimal(1) + sl_frac),
    )


def resolve_trade(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    *,
    direction: Direction,
    entry_price: Decimal,
    tp_price: Decimal,
    sl_price: Decimal,
) -> tuple[TradeOutcome, int, Decimal]:
    """Walk the bars AFTER the entry bar and return (outcome, bars_held, exit_price).

    ``highs``/``lows``/``closes`` are the post-entry bars only (no same-bar
    lookahead). The STOP is tested before the TP within a bar, so a bar that
    touches both resolves as a LOSS (conservative). If neither level is touched
    the trade is OPEN and exits at the last available close.
    """
    n = len(highs)
    for i in range(n):
        hi = highs[i]
        lo = lows[i]
        if direction == Direction.LONG:
            if lo <= sl_price:
                return TradeOutcome.LOSS, i + 1, sl_price
            if hi >= tp_price:
                return TradeOutcome.WIN, i + 1, tp_price
        else:
            if hi >= sl_price:
                return TradeOutcome.LOSS, i + 1, sl_price
            if lo <= tp_price:
                return TradeOutcome.WIN, i + 1, tp_price
    if n == 0:
        return TradeOutcome.OPEN, 0, entry_price
    return TradeOutcome.OPEN, n, closes[n - 1]


def _gross_return_bps(
    entry_price: Decimal, exit_price: Decimal, direction: Direction
) -> Decimal:
    """Signed price move in bps for the trade's direction (cost not yet applied)."""
    if entry_price <= 0:
        return Decimal(0)
    move = (exit_price - entry_price) / entry_price
    if direction == Direction.SHORT:
        move = -move
    return move * _BPS


def backtest_bracket(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    entries: Sequence[Entry],
    *,
    cost_bps: Decimal,
    max_hold: int,
    name: str = "bracket",
) -> BracketResult:
    """Resolve every bracketed entry and aggregate the edge measurement.

    The entry fills at ``closes[entry.index]``; the bracket is then monitored
    over the next ``max_hold`` bars. ``cost_bps`` is the round-trip cost and is
    subtracted from every trade's gross return. Entries on or after the last bar
    (no forward bars to monitor) are skipped.
    """
    n_bars = len(closes)
    trades: list[BracketTrade] = []
    breakeven_sum = Decimal(0)

    for entry in entries:
        if entry.index < 0 or entry.index >= n_bars - 1:
            continue
        entry_price = closes[entry.index]
        tp_price, sl_price = bracket_prices(
            entry_price, entry.direction, entry.tp_bps, entry.sl_bps
        )
        start = entry.index + 1
        stop = min(start + max_hold, n_bars)
        outcome, bars_held, exit_price = resolve_trade(
            highs[start:stop],
            lows[start:stop],
            closes[start:stop],
            direction=entry.direction,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
        )
        return_bps = _gross_return_bps(entry_price, exit_price, entry.direction) - cost_bps
        trades.append(
            BracketTrade(
                entry_index=entry.index,
                exit_index=entry.index + bars_held,
                direction=entry.direction,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                exit_price=exit_price,
                outcome=outcome,
                bars_held=bars_held,
                return_bps=return_bps,
            )
        )
        breakeven_sum += breakeven_rate(entry.tp_bps, entry.sl_bps, cost_bps)

    n_trades = len(trades)
    n_wins = sum(1 for t in trades if t.outcome == TradeOutcome.WIN)
    n_losses = sum(1 for t in trades if t.outcome == TradeOutcome.LOSS)
    n_open = sum(1 for t in trades if t.outcome == TradeOutcome.OPEN)

    resolved = n_wins + n_losses
    win_rate = Decimal(n_wins) / Decimal(resolved) if resolved else Decimal(0)
    be_rate = breakeven_sum / Decimal(n_trades) if n_trades else Decimal(0)
    expectancy_bps = (
        sum((t.return_bps for t in trades), Decimal(0)) / Decimal(n_trades)
        if n_trades
        else Decimal(0)
    )
    avg_bars_held = (
        sum((Decimal(t.bars_held) for t in trades), Decimal(0)) / Decimal(n_trades)
        if n_trades
        else Decimal(0)
    )

    return BracketResult(
        name=name,
        n_trades=n_trades,
        n_wins=n_wins,
        n_losses=n_losses,
        n_open=n_open,
        win_rate=win_rate,
        breakeven_rate=be_rate,
        edge=win_rate > be_rate,
        expectancy_bps=expectancy_bps,
        cost_bps=cost_bps,
        avg_bars_held=avg_bars_held,
        trades=tuple(trades),
    )
