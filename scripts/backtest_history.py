#!/usr/bin/env python3
# Tooling — full historical BTC backtest by regime + per-agent capture
"""Simulate every strategy over the REAL, long BTC history and report, per market
regime (UPTREND / DOWNTREND / RANGE), whether it makes money — and exactly what
each agent/strategy captures in each regime.

Data: Coin Metrics daily BTC/USD reference price (real, public, back to 2010).
Honest framing: there is NO guaranteed profit. We report per-regime edge,
risk-adjusted stats, and an out-of-sample + Monte-Carlo confidence verdict.
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
from infrastructure.gateway.bitkub_klines import OhlcBar, load_csv
from infrastructure.gateway.coinmetrics import fetch_btc_history

_BPS = Decimal("10000")
_WINDOW = 80
_SCAN_START = 55
_REGIMES = ("UPTREND", "DOWNTREND", "RANGE")
_ALL = "breakout_ls,momentum_ls,reversion_ls,trend_following,breakout,range_reversion"


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


def _regime_labels(df: pd.DataFrame, ema_len: int = 100, look: int = 20, thr: float = 0.05) -> list[str]:
    """Tag each bar UPTREND/DOWNTREND/RANGE by the slope of a long EMA."""
    ema = df["close"].ewm(span=ema_len, adjust=False).mean()
    labels: list[str] = []
    for i in range(len(df)):
        if i < ema_len:
            labels.append("RANGE")
            continue
        past = ema.iloc[max(0, i - look)]
        slope = (ema.iloc[i] - past) / past if past else 0.0
        labels.append("UPTREND" if slope > thr else "DOWNTREND" if slope < -thr else "RANGE")
    return labels


def _signals_for(strat: object, df: pd.DataFrame, bars: list[OhlcBar], direction: str) -> list[Entry]:
    decide_df = getattr(strat, "decide_df", None)
    if decide_df is None:
        return []
    allow_long, allow_short = direction in ("long", "both"), direction in ("short", "both")
    out: list[Entry] = []
    for i in range(_SCAN_START, len(df) + 1):
        sig = decide_df(df.iloc[max(0, i - _WINDOW) : i])
        if (sig.action == SignalAction.BUY and not allow_long) or (
            sig.action == SignalAction.SELL and not allow_short
        ) or sig.action not in (SignalAction.BUY, SignalAction.SELL):
            continue
        idx = i - 1
        entry = bars[idx].close
        stop, take = getattr(sig, "stop_price", None), getattr(sig, "take_profit_price", None)
        if stop is None or take is None or entry <= 0:
            continue
        sd, tk = Decimal(str(stop)), Decimal(str(take))
        if sig.action == SignalAction.BUY:
            d, sl, tp = Direction.LONG, (entry - sd) / entry * _BPS, (tk - entry) / entry * _BPS
        else:
            d, sl, tp = Direction.SHORT, (sd - entry) / entry * _BPS, (entry - tk) / entry * _BPS
        if sl <= 0 or tp <= 0:
            continue
        out.append(Entry(index=idx, direction=d, tp_bps=tp, sl_bps=sl))
    return out


def _monte_carlo(returns: list[float], runs: int, rng: random.Random) -> tuple[float, float, float]:
    if not returns or runs <= 0:
        return 0.0, 0.0, 0.0
    finals = []
    for _ in range(runs):
        eq = 1.0
        for _ in range(len(returns)):
            eq *= 1.0 + rng.choice(returns)
        finals.append(eq - 1.0)
    finals.sort()
    return sum(1 for f in finals if f > 0) / runs, finals[runs // 2], finals[int(runs * 0.05)]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Historical BTC backtest by regime + per-agent capture.")
    p.add_argument("--csv", help="cached daily OHLC CSV (else fetch Coin Metrics live)")
    p.add_argument("--strategies", default=_ALL)
    p.add_argument("--direction", choices=("long", "short", "both"), default="both")
    p.add_argument("--flip", action="store_true")
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("15"))
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("3"))
    p.add_argument("--max-hold", type=int, default=30)
    p.add_argument("--position-frac", type=Decimal, default=Decimal("0.25"))
    p.add_argument("--mc-runs", type=int, default=1500)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args(argv)

    try:
        bars = load_csv(args.csv) if args.csv else fetch_btc_history()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to load BTC history: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if len(bars) < 200:
        print(f"too few bars ({len(bars)})", file=sys.stderr)
        return 2

    df = _build_df(bars)
    labels = _regime_labels(df)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    cost_bps = (args.fee_bps + args.slip_bps) * Decimal(2)
    rng = random.Random(args.seed)

    from datetime import UTC, datetime  # noqa: PLC0415
    d0 = datetime.fromtimestamp(bars[0].ts_ms / 1000, UTC).date()
    d1 = datetime.fromtimestamp(bars[-1].ts_ms / 1000, UTC).date()
    years = (bars[-1].ts_ms - bars[0].ts_ms) / 1000 / 86400 / 365.25
    bh = (closes[-1] / closes[0] - 1) * 100
    mix = {r: labels.count(r) / len(labels) * 100 for r in _REGIMES}
    print(f"=== REAL BTC/USD daily (Coin Metrics) | {d0} → {d1} | {len(bars)} days (~{years:.1f}y) ===")
    print(f"Price ${float(closes[0]):.2f} → ${float(closes[-1]):,.0f} | Buy&Hold {bh:,.0f}%")
    print(f"Regime mix: UPTREND {mix['UPTREND']:.0f}% | DOWNTREND {mix['DOWNTREND']:.0f}% | RANGE {mix['RANGE']:.0f}%")
    print(f"Cost {cost_bps} bps round-trip | maxHold {args.max_hold}d | pos {args.position_frac} | dir {args.direction}\n")

    names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    hdr = f"  {'agent/strategy':<16}{'trades':>7}{'win%':>6}{'net%':>9}{'PF':>6}{'maxDD%':>7}{'exp(bps)':>9}  verdict"
    print("PER-AGENT (whole history):")
    print(hdr + "\n  " + "-" * (len(hdr) - 2))
    bucketed: dict[str, dict[str, list]] = {}
    for name in names:
        try:
            strat = get(name)()
        except KeyError:
            continue
        sigs = _signals_for(strat, df, bars, args.direction)
        rep = run_profit_backtest(
            highs, lows, closes, sigs, cost_bps=cost_bps, max_hold=args.max_hold,
            position_fraction=args.position_frac, allow_flip=args.flip, name=name,
        )
        pf = "inf" if rep.profit_factor is None else f"{rep.profit_factor:.2f}"
        verdict = "profit ✅" if rep.profitable and (rep.profit_factor or Decimal(2)) > 1 else "loss ❌"
        print(f"  {name:<16}{rep.n_trades:>7}{rep.win_rate * 100:>5.1f}%{rep.net_return_pct:>8.1f}%"
              f"{pf:>6}{rep.max_drawdown_pct:>6.1f}%{rep.expectancy_bps:>9.1f}  {verdict}")
        # bucket trades by entry regime
        b: dict[str, list] = {r: [] for r in _REGIMES}
        for t in rep.trades:
            b[labels[t.entry_index]].append(t)
        bucketed[name] = b

    print("\nWHAT EACH AGENT CAPTURES — avg net return per trade (bps) by regime  [trades, win%]:")
    print(f"  {'agent/strategy':<16}{'UPTREND':>22}{'DOWNTREND':>22}{'RANGE':>22}")
    for name, b in bucketed.items():
        cells = []
        for r in _REGIMES:
            ts = b[r]
            if ts:
                avg = sum((t.return_bps for t in ts), Decimal(0)) / Decimal(len(ts))
                wr = sum(1 for t in ts if t.pnl > 0) / len(ts) * 100
                cells.append(f"{avg:>+7.0f} [{len(ts):>3},{wr:>3.0f}%]")
            else:
                cells.append(f"{'—':>16}")
        print(f"  {name:<16}{cells[0]:>22}{cells[1]:>22}{cells[2]:>22}")

    print("\nCONFIDENCE (out-of-sample 70/30 + significance + Monte Carlo):")
    for name in names:
        if name not in bucketed:
            continue
        strat = get(name)()
        sigs = _signals_for(strat, df, bars, args.direction)
        k = int(len(bars) * 0.7)
        oos_sigs = [Entry(index=e.index - k, direction=e.direction, tp_bps=e.tp_bps, sl_bps=e.sl_bps)
                    for e in sigs if e.index >= k]
        oos = run_profit_backtest(highs[k:], lows[k:], closes[k:], oos_sigs, cost_bps=cost_bps,
                                  max_hold=args.max_hold, position_fraction=args.position_frac, allow_flip=args.flip)
        sg = significance([t.return_bps for t in oos.trades])
        # Monte Carlo on the OUT-OF-SAMPLE trades (recent, more stationary) — bootstrapping
        # the full history would be dominated by unrepeatable 2011-era 100x moves.
        pprof, med, p5 = _monte_carlo([float(t.return_bps) / 10000.0 for t in oos.trades], args.mc_runs, rng)
        tag = ("HIGH" if oos.net_return_pct > 0 and sg.significant_95 and pprof >= 0.95
               else "MODERATE" if oos.net_return_pct > 0 and (sg.significant_95 or pprof >= 0.8)
               else "WEAK/luck" if oos.net_return_pct > 0 else "NO edge")
        print(f"  {name:<16} OOS net {oos.net_return_pct:>7.1f}%  t={sg.t_statistic:>5.2f}  "
              f"MC P(profit)={pprof * 100:>4.0f}%  p5={p5 * 100:>+6.1f}%  ➜ {tag}")

    print("\nNote: Buy&Hold dwarfs every strategy over BTC's mega-trend — strategies aim for")
    print("downside protection + shorting bears, not beating a 15-year hold. No result is a guarantee.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
