#!/usr/bin/env python3
# Tooling — grid-search bracket params on REAL BTC to maximise daily profit (honest OOS)
"""Tune every strategy for the highest DAILY profit on real BTC history, then show
the HONEST out-of-sample number. Demonstrates the overfitting trap: in-sample can
be cranked high, out-of-sample is the truth.

Method: take each strategy's entry timing/direction, grid-search the bracket
(tp/sl bps, max-hold) on the in-sample 70%, pick the best, and report its
out-of-sample daily return. Also reports the best OOS achievable by ANY config
(an optimistic upper bound that still cannot reach 2-5%/day).
"""
from __future__ import annotations

import argparse
import math
import sys
from decimal import Decimal

import pandas as pd

from domain.backtest.bracket_engine import Direction, Entry
from domain.backtest.profit_engine import run_profit_backtest
from domain.strategy.base import SignalAction
from domain.strategy.registry import get
from infrastructure.gateway.bitkub_klines import OhlcBar, load_csv
from infrastructure.gateway.coinmetrics import fetch_btc_history

_WINDOW, _SCAN_START = 80, 55
_TP = [Decimal(x) for x in (100, 200, 300, 500, 800, 1200, 2000, 3000)]
_SL = [Decimal(x) for x in (100, 200, 300, 500, 800, 1200)]
_HOLD = [10, 20, 40, 80, 160]
_ALL = "breakout_ls,momentum_ls,reversion_ls,trend_following,range_reversion"


def _build_df(bars: list[OhlcBar]) -> pd.DataFrame:
    return pd.DataFrame({k: [float(getattr(b, k)) for b in bars] for k in ("open", "high", "low", "close", "volume")})


def _timing(strat: object, df: pd.DataFrame) -> list[tuple[int, Direction]]:
    """Entry bar + direction only (bracket is swept separately)."""
    decide = getattr(strat, "decide_df", None)
    if decide is None:
        return []
    out: list[tuple[int, Direction]] = []
    for i in range(_SCAN_START, len(df) + 1):
        s = decide(df.iloc[max(0, i - _WINDOW) : i])
        if s.action == SignalAction.BUY:
            out.append((i - 1, Direction.LONG))
        elif s.action == SignalAction.SELL:
            out.append((i - 1, Direction.SHORT))
    return out


def _daily_pct(net_pct: Decimal, days: int) -> float:
    if days <= 0:
        return 0.0
    base = 1.0 + float(net_pct) / 100.0
    if base <= 0:
        return -100.0
    return (math.pow(base, 1.0 / days) - 1.0) * 100.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Optimise bracket params for daily profit (honest OOS).")
    p.add_argument("--csv")
    p.add_argument("--strategies", default=_ALL)
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("15"))
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("3"))
    p.add_argument("--position-frac", type=Decimal, default=Decimal("0.5"))
    p.add_argument("--split", type=float, default=0.7)
    args = p.parse_args(argv)

    try:
        bars = load_csv(args.csv) if args.csv else fetch_btc_history()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to load: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    df = _build_df(bars)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    n = len(bars)
    k = int(n * args.split)
    is_days, oos_days = k, n - k
    cost = (args.fee_bps + args.slip_bps) * Decimal(2)
    names = [s.strip() for s in args.strategies.split(",") if s.strip()]

    print(f"=== Daily-profit OPTIMIZATION on REAL BTC | {n} days | IS={is_days} OOS={oos_days} | cost={cost}bps ===")
    print("Target asked: 2-5%/day after fees, EVERY day. Honest reality below.\n")
    print(f"  {'strategy':<16}{'best IS cfg (tp/sl/hold)':<26}{'IS/day':>9}{'OOS/day':>9}{'OOS net%':>10}")
    print("  " + "-" * 70)

    global_best_oos_daily = -1e9
    global_best_desc = ""
    for name in names:
        try:
            strat = get(name)()
        except KeyError:
            continue
        timing = _timing(strat, df)
        if not timing:
            print(f"  {name:<16}{'(no signals)':<26}")
            continue

        best_is = None  # (is_net, tp, sl, hold)
        for tp in _TP:
            for sl in _SL:
                for hold in _HOLD:
                    sigs = [Entry(index=i, direction=d, tp_bps=tp, sl_bps=sl) for i, d in timing if i < k]
                    rep = run_profit_backtest(highs[:k], lows[:k], closes[:k], sigs,
                                              cost_bps=cost, max_hold=hold, position_fraction=args.position_frac)
                    if best_is is None or rep.net_return_pct > best_is[0]:
                        best_is = (rep.net_return_pct, tp, sl, hold)
                    # track global OOS upper bound (overfit to OOS — cheating)
                    osigs = [Entry(index=i - k, direction=d, tp_bps=tp, sl_bps=sl) for i, d in timing if i >= k]
                    orep = run_profit_backtest(highs[k:], lows[k:], closes[k:], osigs,
                                               cost_bps=cost, max_hold=hold, position_fraction=args.position_frac)
                    od = _daily_pct(orep.net_return_pct, oos_days)
                    if od > global_best_oos_daily:
                        global_best_oos_daily = od
                        global_best_desc = f"{name} tp={tp} sl={sl} hold={hold}"

        assert best_is is not None
        _, tp, sl, hold = best_is
        osigs = [Entry(index=i - k, direction=d, tp_bps=tp, sl_bps=sl) for i, d in timing if i >= k]
        oos = run_profit_backtest(highs[k:], lows[k:], closes[k:], osigs,
                                  cost_bps=cost, max_hold=hold, position_fraction=args.position_frac)
        cfg = f"tp={tp} sl={sl} hold={hold}"
        print(f"  {name:<16}{cfg:<26}{_daily_pct(best_is[0], is_days):>8.3f}%"
              f"{_daily_pct(oos.net_return_pct, oos_days):>8.3f}%{oos.net_return_pct:>9.1f}%")

    bh_daily = _daily_pct(Decimal(str((float(closes[-1]) / float(closes[0]) - 1) * 100)), n)
    print("\n  " + "-" * 70)
    print(f"  Buy & Hold (no trading):                          {bh_daily:>8.3f}%/day")
    print(f"  BEST OOS/day by ANY config (OVERFIT upper bound): {global_best_oos_daily:>8.3f}%/day")
    print(f"    └ {global_best_desc}")
    print("\nEven the cheating overfit-to-OOS upper bound is the ceiling of what is")
    print("POSSIBLE here — a realistic, picked-in-advance config gets the OOS/day column.")
    print("2-5%/day EVERY day = +137,000% to +39,000,000% per year — no system on Earth does this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
