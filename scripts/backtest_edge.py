#!/usr/bin/env python3
# Tooling — P0 offline edge measurement (CLI runner)
"""Measure whether the bracketed strategies have real edge on REAL Bitkub candles.

This is an OFFLINE, paper-only measurement tool. It never places an order and
never touches the money/treasury/risk/execution layers. It:

  1. loads OHLC candles (live via Bitkub's public UDF endpoint with ``--fetch``,
     or from a CSV with ``--csv PATH``),
  2. replays each registered bracket strategy bar-by-bar (no lookahead) to find
     its entry signals,
  3. wraps every entry in a bracket (take-profit + stop-loss) and resolves it,
  4. prints, per strategy, ``win%`` versus ``breakeven%`` — where breakeven
     already includes round-trip fees + slippage. A strategy has positive
     expectancy only when ``win% > breakeven%`` (edge = YES).

Bracket modes (``--bracket``):
  • ``fixed`` — impose a single symmetric bracket (``--tp-bps`` / ``--sl-bps``)
    on every entry; here ``win% > breakeven%`` is *exactly* positive expectancy.
  • ``atr``   — honour each strategy's own ATR-derived stop / take-profit;
    breakeven% is the per-trade average.
  • ``both``  — print both tables (default).

Examples::

    PYTHONPATH=src python scripts/backtest_edge.py --fetch \
        --symbol BTC_THB --resolution 15m --bars 1500 --bracket both
    PYTHONPATH=src python scripts/backtest_edge.py --csv data/btc_15m.csv --bracket both
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

import pandas as pd

from domain.backtest.bracket_engine import (
    Direction,
    Entry,
    backtest_bracket,
    bracket_prices,
    resolve_trade,
)
from domain.strategy.base import SignalAction
from domain.strategy.registry import _REGISTRY
from infrastructure.gateway.bitkub_klines import (
    OhlcBar,
    fetch_klines,
    load_csv,
)

_BPS = Decimal("10000")
# Trailing window fed to each strategy per bar. Covers the longest strategy
# lookback (regime.classify needs 51 bars) plus SuperTrend/EMA warmup, so the
# windowed replay matches a full-history decision while staying O(n).
_WINDOW = 160


def _build_df(bars: list[OhlcBar]) -> pd.DataFrame:
    """OHLCV DataFrame (float) in the shape the strategies' decide_df expects."""
    return pd.DataFrame(
        {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
        }
    )


def _candidate_entries(
    strat: object, df: pd.DataFrame, bars: list[OhlcBar]
) -> list[tuple[int, Decimal, Decimal]]:
    """Replay one strategy and return (entry_index, atr_tp_bps, atr_sl_bps) tuples.

    Decision at bar i uses bars [i-_WINDOW .. i-1] (no lookahead); a BUY fills at
    that bar's close. atr_*_bps come from the signal's own stop / take-profit.
    """
    decide_df = getattr(strat, "decide_df", None)
    if decide_df is None:
        return []
    out: list[tuple[int, Decimal, Decimal]] = []
    n = len(df)
    for i in range(_WINDOW, n + 1):
        window = df.iloc[i - _WINDOW : i]
        sig = decide_df(window)
        if sig.action != SignalAction.BUY:
            continue
        idx = i - 1
        entry = bars[idx].close
        stop = getattr(sig, "stop_price", None)
        take = getattr(sig, "take_profit_price", None)
        if stop is None or take is None or entry <= 0:
            continue
        sl_bps = (entry - Decimal(str(stop))) / entry * _BPS
        tp_bps = (Decimal(str(take)) - entry) / entry * _BPS
        if sl_bps <= 0 or tp_bps <= 0:
            continue
        out.append((idx, tp_bps, sl_bps))
    return out


def _select_non_overlapping(
    entries: list[Entry],
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    max_hold: int,
) -> list[Entry]:
    """Greedily keep a single position at a time (no overlapping trades)."""
    chosen: list[Entry] = []
    next_free = 0
    n = len(closes)
    for e in entries:
        if e.index < next_free or e.index >= n - 1:
            continue
        tp_price, sl_price = bracket_prices(closes[e.index], e.direction, e.tp_bps, e.sl_bps)
        start = e.index + 1
        stop = min(start + max_hold, n)
        _outcome, bars_held, _exit = resolve_trade(
            highs[start:stop],
            lows[start:stop],
            closes[start:stop],
            direction=e.direction,
            entry_price=closes[e.index],
            tp_price=tp_price,
            sl_price=sl_price,
        )
        chosen.append(e)
        next_free = e.index + max(bars_held, 1) + 1
    return chosen


def _fmt_pct(x: Decimal) -> str:
    return f"{x * 100:6.2f}%"


def _print_table(title: str, results: list, cost_bps: Decimal) -> None:
    print(f"\n{title}  (round-trip cost = {cost_bps} bps)")
    header = (
        f"  {'strategy':<20} {'trades':>6} {'win':>4} {'loss':>4} {'open':>4} "
        f"{'win%':>8} {'breakeven%':>11} {'edge':>5} {'exp(bps)':>9} {'avgBars':>8}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        edge = "YES" if r.edge else "no"
        print(
            f"  {r.name:<20} {r.n_trades:>6} {r.n_wins:>4} {r.n_losses:>4} {r.n_open:>4} "
            f"{_fmt_pct(r.win_rate):>8} {_fmt_pct(r.breakeven_rate):>11} {edge:>5} "
            f"{r.expectancy_bps:>9.1f} {r.avg_bars_held:>8.1f}"
        )


def _run_mode(
    *,
    mode: str,
    candidates: dict[str, list[tuple[int, Decimal, Decimal]]],
    highs: list[Decimal],
    lows: list[Decimal],
    closes: list[Decimal],
    tp_bps: Decimal,
    sl_bps: Decimal,
    cost_bps: Decimal,
    max_hold: int,
) -> list:
    """Build entries for one bracket mode and return a BracketResult per strategy."""
    results = []
    for name, cands in candidates.items():
        if mode == "fixed":
            entries = [Entry(index=i, direction=Direction.LONG, tp_bps=tp_bps, sl_bps=sl_bps) for i, _t, _s in cands]
        else:  # atr — honour the strategy's own bracket
            entries = [Entry(index=i, direction=Direction.LONG, tp_bps=t, sl_bps=s) for i, t, s in cands]
        entries = _select_non_overlapping(entries, highs, lows, closes, max_hold)
        results.append(
            backtest_bracket(
                highs, lows, closes, entries, cost_bps=cost_bps, max_hold=max_hold, name=name
            )
        )

    if mode == "fixed":
        # Baseline sanity check: blind long entries spaced by the holding horizon.
        n = len(closes)
        baseline = [
            Entry(index=i, direction=Direction.LONG, tp_bps=tp_bps, sl_bps=sl_bps)
            for i in range(_WINDOW, n - 1, max_hold)
        ]
        results.append(
            backtest_bracket(
                highs, lows, closes, baseline, cost_bps=cost_bps, max_hold=max_hold, name="baseline_long"
            )
        )
    return results


def _load_bars(args: argparse.Namespace) -> list[OhlcBar]:
    if args.fetch:
        return fetch_klines(args.symbol, args.resolution, bars=args.bars)
    if args.csv:
        return load_csv(args.csv)
    raise SystemExit("error: pass --fetch (live Bitkub) or --csv PATH (offline)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="P0 bracket edge measurement (offline, paper-only).")
    src = p.add_argument_group("data source")
    src.add_argument("--fetch", action="store_true", help="fetch live candles from Bitkub")
    src.add_argument("--csv", help="load candles from a CSV file (offline)")
    p.add_argument("--symbol", default="BTC_THB", help="Bitkub UDF symbol (default BTC_THB)")
    p.add_argument("--resolution", default="15m", help="bar resolution: 5m, 15m, 1h, ...")
    p.add_argument("--bars", type=int, default=1500, help="number of bars (default 1500)")
    p.add_argument("--bracket", choices=("fixed", "atr", "both"), default="both")
    p.add_argument("--tp-bps", type=Decimal, default=Decimal("100"), help="fixed take-profit bps")
    p.add_argument("--sl-bps", type=Decimal, default=Decimal("100"), help="fixed stop-loss bps")
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("25"), help="taker fee bps per leg")
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("5"), help="slippage bps per leg")
    p.add_argument("--max-hold", type=int, default=96, help="max bars to hold a trade")
    p.add_argument("--cache-csv", help="write fetched candles to this CSV path")
    args = p.parse_args(argv)

    try:
        bars = _load_bars(args)
    except Exception as exc:  # noqa: BLE001 — surface the exact error per the handoff
        print(f"FAILED to load candles: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("If --fetch failed, Bitkub may have changed the endpoint/symbol; "
              "you can still run offline with --csv PATH.", file=sys.stderr)
        return 2

    if not bars:
        print("No candles returned.", file=sys.stderr)
        return 2
    if args.cache_csv and args.fetch:
        from infrastructure.gateway.bitkub_klines import write_csv
        write_csv(bars, args.cache_csv)

    cost_bps = (args.fee_bps + args.slip_bps) * Decimal(2)  # round trip: both legs, both costs
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    df = _build_df(bars)

    candidates = {name: _candidate_entries(cls(), df, bars) for name, cls in _REGISTRY.items()}

    span_ms = bars[-1].ts_ms - bars[0].ts_ms
    days = Decimal(span_ms) / Decimal(86_400_000)
    print(
        f"=== Bracket edge: {args.symbol} {args.resolution} | {len(bars)} bars "
        f"(~{days:.1f} days) | window={_WINDOW} maxHold={args.max_hold} ==="
    )

    modes = ("fixed", "atr") if args.bracket == "both" else (args.bracket,)
    for mode in modes:
        title = (
            f"[fixed bracket {args.tp_bps}/{args.sl_bps} bps]"
            if mode == "fixed"
            else "[atr bracket — strategy's own stop/take]"
        )
        results = _run_mode(
            mode=mode,
            candidates=candidates,
            highs=highs,
            lows=lows,
            closes=closes,
            tp_bps=args.tp_bps,
            sl_bps=args.sl_bps,
            cost_bps=cost_bps,
            max_hold=args.max_hold,
        )
        _print_table(title, results, cost_bps)

    print("\nedge = YES  ⟺  win% > breakeven%  (breakeven already includes fees+slippage)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
