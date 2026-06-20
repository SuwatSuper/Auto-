#!/usr/bin/env python3
# Tooling — rigorous profitability validation (out-of-sample + significance + Monte Carlo)
"""Quantify CONFIDENCE that a strategy is profitable — honestly, never 100%.

Three independent checks, the way professionals validate an edge:
  1. Out-of-sample (OOS): observe on the first split, TEST on unseen data. An edge
     that vanishes out-of-sample was overfit.
  2. Statistical significance: is the mean trade return > 0 beyond luck?
     (t-statistic and a 95% confidence interval on expectancy.)
  3. Monte Carlo: resample the realised trades to get the DISTRIBUTION of
     outcomes — the % of runs that end profitable, the median, and the bad-luck
     5th-percentile return.

No line here ever claims certainty. The strongest *honest* verdict is:
profitable out-of-sample + statistically significant (t > 2) + profitable in the
large majority of Monte Carlo runs. That is high confidence — never a guarantee.
"""
from __future__ import annotations

import argparse
import random
import sys
from decimal import Decimal

import pandas as pd

from domain.backtest.bracket_engine import Direction, Entry
from domain.backtest.profit_engine import run_profit_backtest
from domain.backtest.statistics import significance
from domain.strategy.base import SignalAction
from domain.strategy.registry import get
from infrastructure.gateway.bitkub_klines import OhlcBar, fetch_klines, load_csv

_BPS = Decimal("10000")
_WINDOW = 160
_SCAN_START = 25
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


def _signals_for(strat: object, df: pd.DataFrame, bars: list[OhlcBar], direction: str) -> list[Entry]:
    decide_df = getattr(strat, "decide_df", None)
    if decide_df is None:
        return []
    allow_long = direction in ("long", "both")
    allow_short = direction in ("short", "both")
    out: list[Entry] = []
    for i in range(_SCAN_START, len(df) + 1):
        sig = decide_df(df.iloc[max(0, i - _WINDOW) : i])
        if sig.action == SignalAction.BUY and not allow_long:
            continue
        if sig.action == SignalAction.SELL and not allow_short:
            continue
        if sig.action not in (SignalAction.BUY, SignalAction.SELL):
            continue
        idx = i - 1
        entry = bars[idx].close
        stop, take = getattr(sig, "stop_price", None), getattr(sig, "take_profit_price", None)
        if stop is None or take is None or entry <= 0:
            continue
        sd, tk = Decimal(str(stop)), Decimal(str(take))
        if sig.action == SignalAction.BUY:
            d, sl_bps, tp_bps = Direction.LONG, (entry - sd) / entry * _BPS, (tk - entry) / entry * _BPS
        else:
            d, sl_bps, tp_bps = Direction.SHORT, (sd - entry) / entry * _BPS, (entry - tk) / entry * _BPS
        if sl_bps <= 0 or tp_bps <= 0:
            continue
        out.append(Entry(index=idx, direction=d, tp_bps=tp_bps, sl_bps=sl_bps))
    return out


def _monte_carlo(returns_frac: list[float], runs: int, rng: random.Random) -> dict[str, float]:
    """Bootstrap-resample the realised trades; return the outcome distribution."""
    n = len(returns_frac)
    if n == 0 or runs <= 0:
        return {"p_profit": 0.0, "median": 0.0, "p5": 0.0, "p95": 0.0, "worst": 0.0}
    finals: list[float] = []
    for _ in range(runs):
        equity = 1.0
        for _ in range(n):
            equity *= 1.0 + rng.choice(returns_frac)
        finals.append(equity - 1.0)
    finals.sort()
    profitable = sum(1 for f in finals if f > 0)
    return {
        "p_profit": profitable / runs,
        "median": finals[runs // 2],
        "p5": finals[int(runs * 0.05)],
        "p95": finals[min(runs - 1, int(runs * 0.95))],
        "worst": finals[0],
    }


def _run_segment(bars: list[OhlcBar], signals: list[Entry], lo: int, hi: int, args: argparse.Namespace):
    """Run the profit engine on bars[lo:hi] with signals reindexed into that slice."""
    seg = bars[lo:hi]
    highs = [b.high for b in seg]
    lows = [b.low for b in seg]
    closes = [b.close for b in seg]
    seg_signals = [
        Entry(index=e.index - lo, direction=e.direction, tp_bps=e.tp_bps, sl_bps=e.sl_bps)
        for e in signals
        if lo <= e.index < hi
    ]
    cost_bps = (args.fee_bps + args.slip_bps) * Decimal(2)
    return run_profit_backtest(
        highs, lows, closes, seg_signals,
        cost_bps=cost_bps, max_hold=args.max_hold,
        initial_equity=args.initial_equity, position_fraction=args.position_frac,
        allow_flip=args.flip,
    )


def _verdict(oos_net: Decimal, sig_ok: bool, p_profit: float) -> str:
    if oos_net > 0 and sig_ok and p_profit >= 0.95:
        return "HIGH confidence (not a guarantee)"
    if oos_net > 0 and (sig_ok or p_profit >= 0.8):
        return "MODERATE confidence"
    if oos_net > 0:
        return "WEAK / likely luck"
    return "NO edge"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rigorous profitability validation (OOS + significance + Monte Carlo).")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--csv", action="append", default=[])
    p.add_argument("--symbols", default="BTC_THB")
    p.add_argument("--resolution", default="1h")
    p.add_argument("--bars", type=int, default=2000)
    p.add_argument("--strategies", default=_DEFAULT_STRATEGIES)
    p.add_argument("--direction", choices=("long", "short", "both"), default="both")
    p.add_argument("--flip", action="store_true")
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("15"))  # maker-friendly default
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("2"))
    p.add_argument("--max-hold", type=int, default=96)
    p.add_argument("--initial-equity", type=Decimal, default=Decimal("10000"))
    p.add_argument("--position-frac", type=Decimal, default=Decimal("1"))
    p.add_argument("--split", type=float, default=0.7, help="in-sample fraction (rest is OOS)")
    p.add_argument("--mc-runs", type=int, default=2000)
    p.add_argument("--seed", type=int, default=12345)
    args = p.parse_args(argv)

    sources = args.csv if args.csv else args.symbols.split(",")
    strat_names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    cost_bps = (args.fee_bps + args.slip_bps) * Decimal(2)
    rng = random.Random(args.seed)

    print(f"=== Profitability validation | {args.resolution} | dir={args.direction} | "
          f"cost={cost_bps} bps | IS/OOS split={args.split:.0%} | MC runs={args.mc_runs} ===")
    print("NOTE: confidence is probabilistic — no honest tool can promise 100% profit.\n")

    for source in sources:
        try:
            bars = fetch_klines(source.strip(), args.resolution, bars=args.bars) if args.fetch else load_csv(source.strip())
        except Exception as exc:  # noqa: BLE001
            print(f"{source}: FAILED to load — {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if len(bars) < 60:
            print(f"{source}: too few bars ({len(bars)})", file=sys.stderr)
            continue
        df = _build_df(bars)
        k = int(len(bars) * args.split)
        label = source.split("/")[-1]
        print(f"--- {label}  ({len(bars)} bars, IS=0..{k}, OOS={k}..{len(bars)}) ---")
        for name in strat_names:
            try:
                strat = get(name)()
            except KeyError:
                print(f"  {name}: unknown strategy", file=sys.stderr)
                continue
            signals = _signals_for(strat, df, bars, args.direction)
            full = _run_segment(bars, signals, 0, len(bars), args)
            is_rep = _run_segment(bars, signals, 0, k, args)
            oos = _run_segment(bars, signals, k, len(bars), args)
            sig = significance([t.return_bps for t in oos.trades])
            mc = _monte_carlo([float(t.return_bps) / 10000.0 for t in full.trades], args.mc_runs, rng)
            verdict = _verdict(oos.net_return_pct, sig.significant_95, mc["p_profit"])
            print(f"\n  ▶ {name}  (full: {full.n_trades} trades, net {full.net_return_pct:.2f}%)")
            print(f"      IN-SAMPLE : net {is_rep.net_return_pct:7.2f}%  trades {is_rep.n_trades:3}  win {is_rep.win_rate*100:4.1f}%")
            print(f"      OUT-SAMPLE: net {oos.net_return_pct:7.2f}%  trades {oos.n_trades:3}  win {oos.win_rate*100:4.1f}%")
            print(f"      SIGNIFICANCE (OOS): t={sig.t_statistic:.2f}  sig95={sig.significant_95}  "
                  f"exp/trade={sig.mean:.1f}bps  CI95=[{sig.ci95_low:.1f},{sig.ci95_high:.1f}]bps")
            print(f"      MONTE CARLO (full, {args.mc_runs} runs): P(profit)={mc['p_profit']*100:.1f}%  "
                  f"median={mc['median']*100:+.1f}%  p5={mc['p5']*100:+.1f}%  worst={mc['worst']*100:+.1f}%")
            print(f"      ➜ VERDICT: {verdict}")
    print("\nHIGH confidence = profitable out-of-sample AND t>1.96 AND ≥95% of Monte-Carlo runs profitable.")
    print("Even HIGH confidence is NOT a guarantee — size positions for the p5 (bad-luck) case.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
