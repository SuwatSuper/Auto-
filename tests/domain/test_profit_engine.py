# Layer 1 — Domain (tests/domain/test_profit_engine)
"""Unit tests for the long/short profit backtester (Decimal-only verdict engine)."""
from __future__ import annotations

from decimal import Decimal

from domain.backtest.bracket_engine import Direction, Entry
from domain.backtest.profit_engine import ExitKind, run_profit_backtest


def _d(values: list[float | int | str]) -> list[Decimal]:
    return [Decimal(str(v)) for v in values]


def _long(i: int, tp: str = "100", sl: str = "100") -> Entry:
    return Entry(index=i, direction=Direction.LONG, tp_bps=Decimal(tp), sl_bps=Decimal(sl))


def _short(i: int, tp: str = "100", sl: str = "100") -> Entry:
    return Entry(index=i, direction=Direction.SHORT, tp_bps=Decimal(tp), sl_bps=Decimal(sl))


def test_long_profits_on_uptrend() -> None:
    r = run_profit_backtest(
        _d([100, 102, 103, 104]), _d([100, 100, 101, 102]), _d([100, 101, 102, 103]),
        [_long(0)], cost_bps=Decimal("60"), max_hold=10,
    )
    assert r.profitable is True
    assert r.final_equity == Decimal("10040")  # +100 bps TP − 60 bps cost on ฿10000
    assert r.n_long == 1 and r.n_short == 0 and r.n_wins == 1
    assert r.profit_factor is None  # no losses
    assert r.expectancy_bps == Decimal("40")
    assert r.trades[0].exit_kind == ExitKind.TAKE_PROFIT


def test_short_profits_on_downtrend() -> None:
    r = run_profit_backtest(
        _d([100, 100, 99, 98]), _d([100, 98, 97, 96]), _d([100, 99, 98, 97]),
        [_short(0)], cost_bps=Decimal("60"), max_hold=10,
    )
    assert r.profitable is True
    assert r.n_short == 1 and r.n_wins == 1
    assert r.final_equity == Decimal("10040")
    assert r.trades[0].exit_kind == ExitKind.TAKE_PROFIT


def test_stop_loss_caps_loss_long() -> None:
    r = run_profit_backtest(
        _d([100, 100, 99]), _d([100, 98, 97]), _d([100, 98, 97]),
        [_long(0)], cost_bps=Decimal("60"), max_hold=10,
    )
    assert r.profitable is False
    assert r.n_losses == 1
    assert r.trades[0].exit_kind == ExitKind.STOP_LOSS
    assert r.final_equity == Decimal("9840")  # −100 bps SL − 60 bps cost


def test_time_exit_on_flat_market_loses_cost() -> None:
    r = run_profit_backtest(
        _d([100, 100, 100, 100]), _d([100, 100, 100, 100]), _d([100, 100, 100, 100]),
        [_long(0)], cost_bps=Decimal("60"), max_hold=2,
    )
    assert r.profitable is False
    assert r.trades[0].exit_kind == ExitKind.TIME
    assert r.final_equity == Decimal("9940")  # 0 move − 60 bps cost


def test_flip_closes_long_and_opens_short() -> None:
    r = run_profit_backtest(
        _d([100, 100, 100]), _d([100, 100, 100]), _d([100, 100, 100]),
        [_long(0, tp="1000", sl="1000"), _short(1, tp="1000", sl="1000")],
        cost_bps=Decimal("0"), max_hold=10, allow_flip=True,
    )
    assert r.n_trades == 2
    assert r.n_long == 1 and r.n_short == 1
    assert r.trades[0].exit_kind == ExitKind.OPPOSITE
    assert r.trades[1].exit_kind == ExitKind.END


def test_no_flip_exits_to_flat_on_opposite() -> None:
    r = run_profit_backtest(
        _d([100, 100, 100]), _d([100, 100, 100]), _d([100, 100, 100]),
        [_long(0, tp="1000", sl="1000"), _short(1, tp="1000", sl="1000")],
        cost_bps=Decimal("0"), max_hold=10, allow_flip=False,
    )
    assert r.n_trades == 1  # opposite signal closes the long, no reverse
    assert r.n_short == 0
    assert r.trades[0].exit_kind == ExitKind.OPPOSITE


def test_no_signals_means_flat_and_no_profit() -> None:
    r = run_profit_backtest(
        _d([100, 101, 102]), _d([100, 101, 102]), _d([100, 101, 102]),
        [], cost_bps=Decimal("60"), max_hold=10,
    )
    assert r.n_trades == 0
    assert r.profitable is False
    assert r.net_return_pct == Decimal("0")
    assert r.profit_factor is None
    assert r.win_rate == Decimal("0")


def test_profit_factor_and_drawdown_with_win_then_loss() -> None:
    r = run_profit_backtest(
        _d([100, 103, 102, 100, 99, 98]),
        _d([100, 103, 102, 100, 97, 96]),
        _d([100, 102, 102, 100, 98, 98]),
        [_long(0), _long(3)], cost_bps=Decimal("0"), max_hold=10,
    )
    assert r.n_trades == 2 and r.n_wins == 1 and r.n_losses == 1
    assert r.win_rate == Decimal("0.5")
    assert r.profit_factor is not None and r.profit_factor < Decimal("1")  # loss > win here
    assert r.max_drawdown_pct > Decimal("0")
    assert r.profitable is False


def test_position_fraction_scales_pnl() -> None:
    full = run_profit_backtest(
        _d([100, 102]), _d([100, 102]), _d([100, 101]),
        [_long(0)], cost_bps=Decimal("0"), max_hold=10, position_fraction=Decimal("1"),
    )
    half = run_profit_backtest(
        _d([100, 102]), _d([100, 102]), _d([100, 101]),
        [_long(0)], cost_bps=Decimal("0"), max_hold=10, position_fraction=Decimal("0.5"),
    )
    gain_full = full.final_equity - full.initial_equity
    gain_half = half.final_equity - half.initial_equity
    assert gain_full == gain_half * Decimal("2")
