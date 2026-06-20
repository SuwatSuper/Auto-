#!/usr/bin/env python3
# Tooling — profitability proof (long + short, multi-market, offline)
"""Decide whether the strategies actually make money — long AND short, per market.

This is the verdict tool. For each market and strategy it replays the bars
bar-by-bar (no lookahead), opens a LONG on BUY / SHORT on SELL with the
strategy's own ATR bracket, charges fees + slippage on both legs, compounds a
single-position equity curve, and prints the net return, profit factor, max
drawdown and a PROFITABLE / loss verdict.

Offline and paper-only — it never places an order. Profit can come from the
upside (long) and the downside (short): buy low / sell high, either order.

Examples::

    # Multiple markets, live candles (needs egress to api.bitkub.com)
    PYTHONPATH=src python scripts/prove_profit.py --fetch \
        --symbols BTC_THB,ETH_THB --resolution 1h --bars 1500

    # Offline, several CSVs (one per market)
    PYTHONPATH=src python scripts/prove_profit.py \
        --csv data/btc_1h.csv --csv data/eth_1h.csv
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal

import pandas as pd

from domain.backtest.bracket_engine import Direction, Entry
from domain.backtest.profit_engine import run_profit_backtest
from domain.strategy.base import SignalAction
from domain.strategy.registry import get
from infrastructure.gateway.bitkub_klines import OhlcBar, fetch_klines, load_csv

_BPS = Decimal("10000")
_WINDOW = 160  # max trailing bars fed to each strategy per decision (bounds cost)
_SCAN_START = 25  # earliest bar to evaluate; strategies self-guard below their warmup
_DEFAULT_STRATEGIES = "breakout_ls,momentum_ls,reversion_ls"


def _build_df(bars: list[OhlcBar]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [float(b.open) for b in bars],
            "high": [float(b.high) for b in bars],
            "low": [float(b.low) for b in bars],
            "close": [float(b.close) for b in bars],
            "volume": [float(b.volume) for b in bars],
        }
    )


def _signals_for(
    strat: object, df: pd.DataFrame, bars: list[OhlcBar], direction: str
) -> list[Entry]:
    """Replay one strategy and collect bracketed entry signals.

    ``direction`` filters which sides are kept: "long", "short", or "both".
    """
    decide_df = getattr(strat, "decide_df", None)
    if decide_df is None:
        return []
    allow_long = direction in ("long", "both")
    allow_short = direction in ("short", "both")
    out: list[Entry] = []
    n = len(df)
    for i in range(_SCAN_START, n + 1):
        sig = decide_df(df.iloc[max(0, i - _WINDOW) : i])
        if sig.action == SignalAction.BUY and not allow_long:
            continue
        if sig.action == SignalAction.SELL and not allow_short:
            continue
        if sig.action not in (SignalAction.BUY, SignalAction.SELL):
            continue
        idx = i - 1
        entry = bars[idx].close
        stop = getattr(sig, "stop_price", None)
        take = getattr(sig, "take_profit_price", None)
        if stop is None or take is None or entry <= 0:
            continue
        stop_d, take_d = Decimal(str(stop)), Decimal(str(take))
        if sig.action == SignalAction.BUY:
            direction = Direction.LONG
            sl_bps = (entry - stop_d) / entry * _BPS
            tp_bps = (take_d - entry) / entry * _BPS
        else:
            direction = Direction.SHORT
            sl_bps = (stop_d - entry) / entry * _BPS
            tp_bps = (entry - take_d) / entry * _BPS
        if sl_bps <= 0 or tp_bps <= 0:
            continue
        out.append(Entry(index=idx, direction=direction, tp_bps=tp_bps, sl_bps=sl_bps))
    return out


def _load_market(args: argparse.Namespace, source: str) -> list[OhlcBar]:
    if args.fetch:
        return fetch_klines(source, args.resolution, bars=args.bars)
    return load_csv(source)


def _verdict(profitable: bool) -> str:
    return "PROFITABLE ✅" if profitable else "loss ❌"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Profitability proof (long+short, multi-market).")
    p.add_argument("--fetch", action="store_true", help="fetch live candles from Bitkub")
    p.add_argument("--csv", action="append", default=[], help="CSV market file (repeatable)")
    p.add_argument("--symbols", default="BTC_THB", help="comma list of symbols (with --fetch)")
    p.add_argument("--resolution", default="1h")
    p.add_argument("--bars", type=int, default=1500)
    p.add_argument("--strategies", default=_DEFAULT_STRATEGIES, help="comma list of registry names")
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("25"), help="taker fee bps per leg")
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("5"), help="slippage bps per leg")
    p.add_argument("--max-hold", type=int, default=96)
    p.add_argument("--initial-equity", type=Decimal, default=Decimal("10000"))
    p.add_argument("--position-frac", type=Decimal, default=Decimal("1"))
    p.add_argument("--direction", choices=("long", "short", "both"), default="both",
                   help="trade only longs, only shorts, or both (default both)")
    p.add_argument("--flip", action="store_true",
                   help="reverse the position on an opposite signal (default: just exit to flat)")
    args = p.parse_args(argv)

    sources = args.csv if args.csv else args.symbols.split(",")
    if not sources:
        print("error: pass --fetch --symbols ... or --csv PATH (repeatable)", file=sys.stderr)
        return 2
    strat_names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    cost_bps = (args.fee_bps + args.slip_bps) * Decimal(2)  # round trip, both legs

    print(
        f"=== Profit proof | {args.resolution} | dir={args.direction} | "
        f"flip={'on' if args.flip else 'off'} | cost={cost_bps} bps round-trip | "
        f"maxHold={args.max_hold} | start=฿{args.initial_equity} ==="
    )
    header = (
        f"  {'market':<14} {'strategy':<14} {'trades':>6} {'L':>4} {'S':>4} "
        f"{'win%':>7} {'net%':>9} {'PF':>6} {'maxDD%':>7} {'exp(bps)':>9}  verdict"
    )
    any_profitable = False
    for source in sources:
        try:
            bars = _load_market(args, source.strip())
        except Exception as exc:  # noqa: BLE001 — surface the exact error
            print(f"  {source}: FAILED to load — {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if not bars:
            print(f"  {source}: no candles", file=sys.stderr)
            continue
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        closes = [b.close for b in bars]
        df = _build_df(bars)
        label = source.split("/")[-1]
        print(f"\n{header}")
        print("  " + "-" * (len(header) - 2))
        for name in strat_names:
            try:
                strat = get(name)()
            except KeyError:
                print(f"  {label:<14} {name:<14} unknown strategy", file=sys.stderr)
                continue
            signals = _signals_for(strat, df, bars, args.direction)
            rep = run_profit_backtest(
                highs, lows, closes, signals,
                cost_bps=cost_bps, max_hold=args.max_hold,
                initial_equity=args.initial_equity, position_fraction=args.position_frac,
                allow_flip=args.flip, name=name,
            )
            any_profitable = any_profitable or rep.profitable
            pf = "inf" if rep.profit_factor is None else f"{rep.profit_factor:.2f}"
            print(
                f"  {label:<14} {name:<14} {rep.n_trades:>6} {rep.n_long:>4} {rep.n_short:>4} "
                f"{rep.win_rate * 100:>6.1f}% {rep.net_return_pct:>8.2f}% {pf:>6} "
                f"{rep.max_drawdown_pct:>6.1f}% {rep.expectancy_bps:>9.1f}  {_verdict(rep.profitable)}"
            )

    print("\nVERDICT: a strategy proves edge when net% > 0 with profit factor > 1 after costs.")
    print("Profit is counted from BOTH long (price up) and short (price down) trades.")
    return 0 if any_profitable else 1


if __name__ == "__main__":
    raise SystemExit(main())
