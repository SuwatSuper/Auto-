# Layer 1 — Domain (backtest/profit_engine)
"""Directional (long + short) bracket portfolio backtester — proves profitability.

Where ``bracket_engine`` answers "does each trade beat its breakeven?", this
engine answers the owner's real question: **does the equity curve go up after
costs?** It simulates a single-position book that can go LONG (BUY) or SHORT
(SELL): each signal opens a position with an attached take-profit + stop-loss
bracket; the position is walked forward and closed on the first of take-profit,
stop-loss, an opposite signal (flip), the holding horizon, or end of data. Fees
+ slippage are charged on BOTH legs of every trade.

Profit comes from both directions — a long that rises and a short that falls
(buy low / sell high, either order). The verdict is honest: ``profitable`` is
true only when final equity exceeds the start after all costs.

Pure Layer-1 domain: Decimal-only (no float), no I/O, no lookahead. The entry at
bar ``i`` fills at ``close[i]``; its bracket is monitored from bar ``i+1`` on.
Conservative tie-break: the stop is tested before the take-profit within a bar.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel

from domain.backtest.bracket_engine import Direction, Entry, bracket_prices

_BPS = Decimal("10000")
_HUNDRED = Decimal("100")


class ExitKind(StrEnum):
    """Why a position was closed."""

    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    OPPOSITE = "OPPOSITE"
    TIME = "TIME"
    END = "END"


class ProfitTrade(BaseModel, frozen=True):
    """One completed round-trip in the portfolio simulation."""

    entry_index: int
    exit_index: int
    direction: Direction
    entry_price: Decimal
    exit_price: Decimal
    exit_kind: ExitKind
    notional: Decimal
    pnl: Decimal  # net of round-trip cost
    return_bps: Decimal
    bars_held: int


class ProfitReport(BaseModel, frozen=True):
    """Portfolio-level profitability verdict for one strategy/market."""

    name: str
    initial_equity: Decimal
    final_equity: Decimal
    net_return_pct: Decimal
    n_trades: int
    n_long: int
    n_short: int
    n_wins: int
    n_losses: int
    win_rate: Decimal
    profit_factor: Decimal | None  # None when there are no losing trades
    expectancy_bps: Decimal
    max_drawdown_pct: Decimal
    avg_bars_held: Decimal
    cost_bps: Decimal
    profitable: bool
    trades: tuple[ProfitTrade, ...]


@dataclass
class _OpenPosition:
    direction: Direction
    entry_index: int
    entry_price: Decimal
    tp_price: Decimal
    sl_price: Decimal
    notional: Decimal


def _gross_frac(direction: Direction, entry: Decimal, exit_price: Decimal) -> Decimal:
    if entry <= 0:
        return Decimal(0)
    move = (exit_price - entry) / entry
    return -move if direction == Direction.SHORT else move


def _resolve_exit(
    pos: _OpenPosition,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    bar: int,
    max_hold: int,
    opposite: Entry | None,
) -> tuple[Decimal, ExitKind] | None:
    """Decide whether ``pos`` exits on this bar. Stop is tested before TP."""
    if pos.direction == Direction.LONG:
        if low <= pos.sl_price:
            return pos.sl_price, ExitKind.STOP_LOSS
        if high >= pos.tp_price:
            return pos.tp_price, ExitKind.TAKE_PROFIT
    else:
        if high >= pos.sl_price:
            return pos.sl_price, ExitKind.STOP_LOSS
        if low <= pos.tp_price:
            return pos.tp_price, ExitKind.TAKE_PROFIT
    if opposite is not None and opposite.direction != pos.direction:
        return close, ExitKind.OPPOSITE
    if bar - pos.entry_index >= max_hold:
        return close, ExitKind.TIME
    return None


def _max_drawdown_pct(equity_curve: Sequence[Decimal]) -> Decimal:
    peak = equity_curve[0]
    worst = Decimal(0)
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak
            if dd > worst:
                worst = dd
    return worst * _HUNDRED


def run_profit_backtest(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    signals: Sequence[Entry],
    *,
    cost_bps: Decimal,
    max_hold: int,
    initial_equity: Decimal = Decimal("10000"),
    position_fraction: Decimal = Decimal("1"),
    allow_flip: bool = True,
    name: str = "strategy",
) -> ProfitReport:
    """Run a single-position long/short bracket backtest and return the verdict.

    ``signals`` carry the entry bar, direction (LONG=BUY / SHORT=SELL) and the
    bracket distances in bps. Each trade deploys ``position_fraction`` of the
    current equity as notional (default full equity, no leverage), so the equity
    compounds. ``cost_bps`` is the round-trip cost charged on every trade.

    ``allow_flip`` (default True): an opposite signal closes the position and
    immediately re-opens the reverse. When False, an opposite signal only closes
    to flat (no same-bar reversal) — useful to avoid counter-trend whipsaw.
    """
    n = len(closes)
    by_index: dict[int, Entry] = {s.index: s for s in signals if 0 <= s.index < n}
    cost_frac = cost_bps / _BPS

    equity = initial_equity
    equity_curve: list[Decimal] = [equity]
    trades: list[ProfitTrade] = []
    pos: _OpenPosition | None = None

    def _close(exit_price: Decimal, kind: ExitKind, bar: int) -> None:
        nonlocal equity, pos
        assert pos is not None
        net_frac = _gross_frac(pos.direction, pos.entry_price, exit_price) - cost_frac
        pnl = pos.notional * net_frac
        equity += pnl
        equity_curve.append(equity)
        trades.append(
            ProfitTrade(
                entry_index=pos.entry_index,
                exit_index=bar,
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                exit_kind=kind,
                notional=pos.notional,
                pnl=pnl,
                return_bps=net_frac * _BPS,
                bars_held=bar - pos.entry_index,
            )
        )
        pos = None

    for i in range(n):
        signal = by_index.get(i)
        blocked_reopen = False
        if pos is not None and i > pos.entry_index:
            outcome = _resolve_exit(pos, highs[i], lows[i], closes[i], i, max_hold, signal)
            if outcome is not None:
                _close(outcome[0], outcome[1], i)
                blocked_reopen = outcome[1] == ExitKind.OPPOSITE and not allow_flip
        if pos is None and signal is not None and not blocked_reopen:
            entry_price = closes[i]
            tp_price, sl_price = bracket_prices(
                entry_price, signal.direction, signal.tp_bps, signal.sl_bps
            )
            pos = _OpenPosition(
                direction=signal.direction,
                entry_index=i,
                entry_price=entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                notional=equity * position_fraction,
            )

    if pos is not None and n > 0:
        _close(closes[n - 1], ExitKind.END, n - 1)

    n_trades = len(trades)
    n_wins = sum(1 for t in trades if t.pnl > 0)
    n_losses = sum(1 for t in trades if t.pnl < 0)
    gross_profit = sum((t.pnl for t in trades if t.pnl > 0), Decimal(0))
    gross_loss = -sum((t.pnl for t in trades if t.pnl < 0), Decimal(0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

    win_rate = Decimal(n_wins) / Decimal(n_trades) if n_trades else Decimal(0)
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
    net_return_pct = (
        (equity - initial_equity) / initial_equity * _HUNDRED
        if initial_equity > 0
        else Decimal(0)
    )

    return ProfitReport(
        name=name,
        initial_equity=initial_equity,
        final_equity=equity,
        net_return_pct=net_return_pct,
        n_trades=n_trades,
        n_long=sum(1 for t in trades if t.direction == Direction.LONG),
        n_short=sum(1 for t in trades if t.direction == Direction.SHORT),
        n_wins=n_wins,
        n_losses=n_losses,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expectancy_bps=expectancy_bps,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        avg_bars_held=avg_bars_held,
        cost_bps=cost_bps,
        profitable=equity > initial_equity,
        trades=tuple(trades),
    )
