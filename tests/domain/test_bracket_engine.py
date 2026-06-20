# Layer 1 — Domain (tests/domain/test_bracket_engine)
"""Unit tests for the bracket backtester (edge measurement, Decimal-only)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from domain.backtest.bracket_engine import (
    Direction,
    Entry,
    TradeOutcome,
    backtest_bracket,
    breakeven_rate,
    resolve_trade,
)


def _d(values: list[float | int | str]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


# ── breakeven_rate: the honest yardstick ─────────────────────────────

def test_breakeven_symmetric_no_cost() -> None:
    """A 1:1 bracket with no costs breaks even at exactly 50%."""
    assert breakeven_rate(Decimal("100"), Decimal("100"), Decimal("0")) == Decimal("0.5")


def test_breakeven_with_round_trip_cost() -> None:
    """A 1:1 bracket costing 60 bps round-trip needs an 80% win rate to break even."""
    assert breakeven_rate(Decimal("100"), Decimal("100"), Decimal("60")) == Decimal("0.8")


def test_breakeven_asymmetric_reward() -> None:
    """A 2:1 reward:risk bracket (no cost) breaks even at 1/3."""
    assert breakeven_rate(Decimal("200"), Decimal("100"), Decimal("0")) == (
        Decimal("1") / Decimal("3")
    )


def test_breakeven_zero_denominator_raises() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        breakeven_rate(Decimal("0"), Decimal("0"), Decimal("0"))


# ── resolve_trade: tie-break and open-trade behaviour ────────────────

def test_resolve_stop_wins_ties_and_empty_window() -> None:
    """A bar that straddles both levels is a LOSS; an empty window is OPEN."""
    loss, held, exit_price = resolve_trade(
        _d([200]), _d([0]), _d([150]),
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        tp_price=Decimal("101"),
        sl_price=Decimal("99"),
    )
    assert (loss, held, exit_price) == (TradeOutcome.LOSS, 1, Decimal("99"))

    nothing = resolve_trade(
        [], [], [],
        direction=Direction.LONG,
        entry_price=Decimal("100"),
        tp_price=Decimal("101"),
        sl_price=Decimal("99"),
    )
    assert nothing == (TradeOutcome.OPEN, 0, Decimal("100"))


# ── backtest_bracket: end-to-end edge verdicts ───────────────────────

def test_long_bracket_wins_on_uptrend() -> None:
    """TP hit first → win_rate 1.0 > breakeven 0.8 → edge YES; net exp = tp - cost."""
    highs = _d([100, 102, 103])
    lows = _d([100, 100, 101])
    closes = _d([100, 101, 102])
    entries = [
        Entry(index=0, direction=Direction.LONG, tp_bps=Decimal("100"), sl_bps=Decimal("100")),
        # An entry on the last bar has no forward bars and must be skipped.
        Entry(index=2, direction=Direction.LONG, tp_bps=Decimal("100"), sl_bps=Decimal("100")),
    ]
    r = backtest_bracket(highs, lows, closes, entries, cost_bps=Decimal("60"), max_hold=10)
    assert r.n_trades == 1
    assert r.n_wins == 1 and r.n_losses == 0 and r.n_open == 0
    assert r.win_rate == Decimal("1")
    assert r.breakeven_rate == Decimal("0.8")
    assert r.edge is True
    assert r.expectancy_bps == Decimal("40")  # +100 bps TP − 60 bps cost
    assert r.trades[0].outcome == TradeOutcome.WIN

    # An empty entry list yields a well-formed, zeroed, no-edge result.
    empty = backtest_bracket(highs, lows, closes, [], cost_bps=Decimal("60"), max_hold=10)
    assert empty.n_trades == 0 and empty.edge is False
    assert empty.win_rate == Decimal("0") and empty.expectancy_bps == Decimal("0")


def test_long_bracket_loses_on_downtrend() -> None:
    """SL hit first → win_rate 0 < breakeven → edge NO; net exp = -(sl + cost)."""
    highs = _d([100, 100, 99])
    lows = _d([100, 98, 97])
    closes = _d([100, 98, 97])
    entries = [Entry(index=0, direction=Direction.LONG, tp_bps=Decimal("100"), sl_bps=Decimal("100"))]
    r = backtest_bracket(highs, lows, closes, entries, cost_bps=Decimal("60"), max_hold=10)
    assert r.n_losses == 1 and r.n_wins == 0
    assert r.win_rate == Decimal("0")
    assert r.edge is False
    assert r.expectancy_bps == Decimal("-160")  # −100 bps SL − 60 bps cost


def test_short_bracket_wins_and_open_trade_marks_to_close() -> None:
    """A SHORT wins as price falls; a flat series leaves the trade OPEN."""
    short = backtest_bracket(
        _d([100, 100, 99]), _d([100, 98, 97]), _d([100, 99, 98]),
        [Entry(index=0, direction=Direction.SHORT, tp_bps=Decimal("100"), sl_bps=Decimal("100"))],
        cost_bps=Decimal("60"), max_hold=10,
    )
    assert short.n_wins == 1 and short.edge is True
    assert short.expectancy_bps == Decimal("40")

    flat = backtest_bracket(
        _d([100, 100, 100, 100]), _d([100, 100, 100, 100]), _d([100, 100, 100, 100]),
        [Entry(index=0, direction=Direction.LONG, tp_bps=Decimal("100"), sl_bps=Decimal("100"))],
        cost_bps=Decimal("60"), max_hold=2,
    )
    assert flat.n_open == 1 and flat.n_wins == 0 and flat.n_losses == 0
    assert flat.trades[0].outcome == TradeOutcome.OPEN
    assert flat.expectancy_bps == Decimal("-60")  # 0 move − 60 bps cost
