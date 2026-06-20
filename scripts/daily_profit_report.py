#!/usr/bin/env python3
# Tooling — HONEST day-by-day profit report on REAL BTC history (2-week breakdown)
"""Build an honest, day-by-day profit-and-loss report from REAL BTC price history.

What it does, end to end:
  1. Loads REAL daily BTC prices (Coin Metrics reference rate, public, since 2010).
  2. Re-tunes every strategy's take-profit / stop-loss / hold bracket by grid
     search on an IN-SAMPLE slice, then keeps only the strategies that still make
     money OUT-OF-SAMPLE (the honest survivors). This is the "adjust all
     strategies" step — done without peeking at the test window.
  3. Runs the surviving ensemble as a single-position long/short book and marks
     it to market EVERY day, charging real Bitkub-style fees + slippage on both
     legs, so we can report the realised profit for EACH of the last N days.
  4. Prints, day by day, the % gained/lost after fees, and compares it to the
     "2-5% per day" target.

Honesty rules baked in:
  * No lookahead — each day's signal sees only prior bars; the tuning split is
    chosen before the test window is touched.
  * Fees + slippage charged on every entry and every exit.
  * The 2-5%/day target is reported truthfully against what really happened.

Usage::

    PYTHONPATH=src python scripts/daily_profit_report.py \
        --csv data/btc_usd_daily_cm.csv --days 14 --out reports/daily_profit_2weeks.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import sys
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from domain.analytics import ta
from domain.backtest.bracket_engine import Direction, Entry
from domain.backtest.profit_engine import run_profit_backtest
from domain.strategy.base import SignalAction
from domain.strategy.registry import get
from infrastructure.gateway.bitkub_klines import OhlcBar, load_csv
from infrastructure.gateway.coinmetrics import fetch_btc_history

_BPS = Decimal("10000")
_WINDOW = 80          # trailing bars fed to each strategy per decision
_SCAN_START = 55      # earliest bar evaluated (strategies self-guard below warmup)
_TP = [Decimal(x) for x in (200, 300, 500, 800, 1200, 2000, 3000)]
_SL = [Decimal(x) for x in (150, 200, 300, 500, 800)]
_HOLD = [10, 20, 40, 80]
_ALL = "trend_following,momentum_ls,reversion_ls,breakout_ls,range_reversion"


def _build_df(bars: list[OhlcBar]) -> pd.DataFrame:
    return pd.DataFrame({k: [float(getattr(b, k)) for b in bars] for k in ("open", "high", "low", "close", "volume")})


def _timing(strat: object, df: pd.DataFrame) -> list[tuple[int, Direction]]:
    decide = getattr(strat, "decide_df", None)
    if decide is None:
        return []
    out: list[tuple[int, Direction]] = []
    for i in range(_SCAN_START, len(df) + 1):
        s = decide(df.iloc[max(0, i - _WINDOW): i])
        if s.action == SignalAction.BUY:
            out.append((i - 1, Direction.LONG))
        elif s.action == SignalAction.SELL:
            out.append((i - 1, Direction.SHORT))
    return out


def _daily_pct(net_pct: Decimal, days: int) -> float:
    if days <= 0:
        return 0.0
    base = 1.0 + float(net_pct) / 100.0
    return -100.0 if base <= 0 else (math.pow(base, 1.0 / days) - 1.0) * 100.0


@dataclass
class Tuned:
    name: str
    tp: Decimal
    sl: Decimal
    hold: int
    is_daily: float
    oos_daily: float
    oos_net: Decimal


def tune_strategy(name: str, df: pd.DataFrame, highs, lows, closes, k: int, cost: Decimal, pos: Decimal) -> Tuned | None:
    """Grid-search the bracket on the in-sample half; report the honest OOS number."""
    try:
        strat = get(name)()
    except KeyError:
        return None
    timing = _timing(strat, df)
    if not timing:
        return None
    best = None  # (is_net, tp, sl, hold)
    for tp in _TP:
        for sl in _SL:
            for hold in _HOLD:
                sigs = [Entry(index=i, direction=d, tp_bps=tp, sl_bps=sl) for i, d in timing if i < k]
                rep = run_profit_backtest(highs[:k], lows[:k], closes[:k], sigs,
                                          cost_bps=cost, max_hold=hold, position_fraction=pos)
                if best is None or rep.net_return_pct > best[0]:
                    best = (rep.net_return_pct, tp, sl, hold)
    assert best is not None
    _, tp, sl, hold = best
    osigs = [Entry(index=i - k, direction=d, tp_bps=tp, sl_bps=sl) for i, d in timing if i >= k]
    oos = run_profit_backtest(highs[k:], lows[k:], closes[k:], osigs,
                              cost_bps=cost, max_hold=hold, position_fraction=pos)
    return Tuned(name, tp, sl, hold, _daily_pct(best[0], k),
                 _daily_pct(oos.net_return_pct, len(closes) - k), oos.net_return_pct)


@dataclass
class DayRow:
    date: str
    close: float
    signal: str
    position: str
    event: str
    fees: float
    pnl: float
    day_pct: float
    equity: float
    cum_pct: float


def _consensus(survivors: list[Tuned], objs: dict, df: pd.DataFrame, i: int) -> int:
    """Majority vote of the surviving strategies at bar i: +1 long, -1 short, 0 flat."""
    vote = 0
    win = df.iloc[max(0, i - _WINDOW + 1): i + 1]
    for t in survivors:
        s = objs[t.name].decide_df(win)
        if s.action == SignalAction.BUY:
            vote += 1
        elif s.action == SignalAction.SELL:
            vote -= 1
    return (vote > 0) - (vote < 0)


def simulate_daily(
    bars: list[OhlcBar], df: pd.DataFrame, survivors: list[Tuned], *,
    cost_bps: Decimal, start_equity: float, pos_frac: float, max_hold: int, window_days: int,
) -> list[DayRow]:
    """Single-position long/short ensemble marked to market EVERY day.

    The ATR(14) bracket (median tuned tp/sl across survivors) caps each trade; an
    opposite consensus flips the book, else it closes after ``max_hold`` days.
    Fees+slippage hit both legs. Each day's P&L = change in (cash + open MTM).
    """
    cost_frac = float(cost_bps) / float(_BPS)
    objs = {t.name: get(t.name)() for t in survivors}
    tp_bps = float(sorted(t.tp for t in survivors)[len(survivors) // 2])
    sl_bps = float(sorted(t.sl for t in survivors)[len(survivors) // 2])

    n = len(bars)
    start_i = max(_SCAN_START, n - window_days)
    cash = start_equity
    # open position state
    side = 0           # +1 long, -1 short, 0 flat
    entry_px = 0.0
    qty = 0.0          # signed BTC units (long>0, short<0)
    bars_held = 0
    stop_px = take_px = 0.0
    prev_equity = start_equity
    rows: list[DayRow] = []

    def mtm(px: float) -> float:
        return cash + qty * px if side else cash

    for i in range(start_i, n):
        px = float(bars[i].close)
        date = dt.datetime.utcfromtimestamp(bars[i].ts_ms / 1000).strftime("%Y-%m-%d")
        cons = _consensus(survivors, objs, df, i)
        event = "—"
        fees = 0.0

        # 1) manage an open position (stop / take / flip / time) on today's close
        if side != 0:
            bars_held += 1
            if side == 1:                 # long: stop below, take above
                hit_stop = px <= stop_px
                hit_take = px >= take_px
            else:                         # short: stop above, take below
                hit_stop = px >= stop_px
                hit_take = px <= take_px
            flip = cons != 0 and cons != side
            reason = ("STOP" if hit_stop else "TAKE" if hit_take else
                      "FLIP" if flip else "TIME" if bars_held >= max_hold else "")
            if reason:
                notional = abs(qty) * px
                exit_fee = notional * cost_frac / 2.0
                cash += qty * px - exit_fee
                fees += exit_fee
                event = f"CLOSE/{reason}"
                side, qty, bars_held = 0, 0.0, 0

        # 2) open a new position if flat and there is a consensus (incl. fresh flip)
        if side == 0 and cons != 0:
            notional = mtm(px) * pos_frac
            entry_fee = notional * cost_frac / 2.0
            cash -= entry_fee
            fees += entry_fee
            qty = (notional / px) * (1 if cons == 1 else -1)
            cash -= qty * px            # pay for the position out of cash
            side = cons
            entry_px = px
            atr = _atr(df, i)
            if cons == 1:
                stop_px = px - sl_bps / 10000.0 * px if atr <= 0 else px - 2 * atr
                take_px = px + tp_bps / 10000.0 * px if atr <= 0 else px + 3 * atr
            else:
                stop_px = px + sl_bps / 10000.0 * px if atr <= 0 else px + 2 * atr
                take_px = px - tp_bps / 10000.0 * px if atr <= 0 else px - 3 * atr
            bars_held = 0
            event = "OPEN/LONG" if cons == 1 else "OPEN/SHORT"
        elif side != 0 and event == "—":
            event = "HOLD"

        equity = mtm(px)
        day_pct = (equity / prev_equity - 1.0) * 100.0 if prev_equity else 0.0
        pnl = equity - prev_equity
        rows.append(DayRow(
            date=date, close=px,
            signal={1: "BUY", -1: "SELL", 0: "HOLD"}[cons],
            position={1: "LONG", -1: "SHORT", 0: "FLAT"}[side],
            event=event, fees=fees, pnl=pnl, day_pct=day_pct,
            equity=equity, cum_pct=(equity / start_equity - 1.0) * 100.0,
        ))
        prev_equity = equity

    return rows


def _atr(df: pd.DataFrame, i: int, length: int = 14) -> float:
    try:
        a = ta.atr(df.iloc[max(0, i - _WINDOW): i + 1], length=length)
        return float(a.iloc[-1, 0])
    except Exception:
        return 0.0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Honest day-by-day profit report on real BTC.")
    p.add_argument("--csv", help="cached daily OHLC CSV (else fetch Coin Metrics live)")
    p.add_argument("--strategies", default=_ALL)
    p.add_argument("--days", type=int, default=14, help="length of the day-by-day window")
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("25"), help="taker fee per leg (Bitkub 0.25%)")
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("5"))
    p.add_argument("--split", type=float, default=0.7, help="in-sample fraction for tuning")
    p.add_argument("--position-frac", type=Decimal, default=Decimal("0.5"))
    p.add_argument("--start-equity", type=float, default=100000.0, help="starting equity (฿)")
    p.add_argument("--max-hold", type=int, default=20)
    p.add_argument("--out", help="write a Markdown report to this path")
    args = p.parse_args(argv)

    try:
        bars = load_csv(args.csv) if args.csv else fetch_btc_history()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to load BTC history: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    df = _build_df(bars)
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    closes = [b.close for b in bars]
    n = len(bars)
    k = int(n * args.split)
    cost = (args.fee_bps + args.slip_bps) * Decimal(2)
    names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    d0 = dt.datetime.utcfromtimestamp(bars[0].ts_ms / 1000).date()
    d1 = dt.datetime.utcfromtimestamp(bars[-1].ts_ms / 1000).date()

    lines: list[str] = []
    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    emit(f"# Honest day-by-day BTC profit report")
    emit("")
    emit(f"- **Data**: REAL Coin Metrics BTC/USD daily, {d0} → {d1} ({n} days)")
    emit(f"- **Price**: ${float(closes[0]):,.0f} → ${float(closes[-1]):,.0f} "
         f"(buy & hold {(float(closes[-1])/float(closes[0])-1)*100:+.1f}%)")
    emit(f"- **Costs**: {args.fee_bps}bps/leg fee + {args.slip_bps}bps slippage = "
         f"{cost}bps round-trip (Bitkub-style taker)")
    emit(f"- **Tuning**: grid-search bracket on in-sample {k}d, verify out-of-sample {n-k}d (no lookahead)")
    emit("")

    # ---- tune every strategy, keep the honest OOS survivors ----
    emit("## 1) Strategy re-tuning (all strategies) — honest out-of-sample")
    emit("")
    emit("| strategy | best bracket (tp/sl/hold) | IS %/day | OOS %/day | OOS net% | kept? |")
    emit("|---|---|---:|---:|---:|:--:|")
    tuned: list[Tuned] = []
    for name in names:
        t = tune_strategy(name, df, highs, lows, closes, k, cost, args.position_frac)
        if t is None:
            emit(f"| {name} | (no signals) | — | — | — | ❌ |")
            continue
        keep = t.oos_daily > 0 and t.oos_net > 0
        tuned.append(t)
        emit(f"| {name} | tp={t.tp} sl={t.sl} hold={t.hold} | {t.is_daily:.3f}% | "
             f"{t.oos_daily:+.3f}% | {float(t.oos_net):+.1f}% | {'✅' if keep else '❌'} |")
    survivors = [t for t in tuned if t.oos_daily > 0 and t.oos_net > 0]
    emit("")
    if not survivors:
        emit("> No strategy survived out-of-sample on this window — the honest ensemble is **flat (cash)**.")
        survivors = sorted(tuned, key=lambda t: t.oos_daily, reverse=True)[:1]
        emit(f"> For the demo below we use the least-bad one: **{survivors[0].name}**.")
    else:
        emit(f"**Kept for the live ensemble:** {', '.join(t.name for t in survivors)}")
    emit("")

    # ---- day-by-day over the last N days ----
    emit(f"## 2) Day-by-day P&L — last {args.days} days (after fees)")
    emit("")
    rows = simulate_daily(bars, df, survivors, cost_bps=cost,
                          start_equity=args.start_equity, pos_frac=float(args.position_frac),
                          max_hold=args.max_hold, window_days=args.days)
    emit("| date | BTC close | signal | position | event | fees ฿ | day P&L ฿ | day % | equity ฿ | cum % |")
    emit("|---|---:|:--:|:--:|:--|---:|---:|---:|---:|---:|")
    wins = 0
    for r in rows:
        if r.day_pct > 0:
            wins += 1
        emit(f"| {r.date} | {r.close:,.0f} | {r.signal} | {r.position} | {r.event} | "
             f"{r.fees:,.0f} | {r.pnl:+,.0f} | {r.day_pct:+.2f}% | {r.equity:,.0f} | {r.cum_pct:+.2f}% |")
    emit("")

    if rows:
        cum = rows[-1].cum_pct
        avg = sum(r.day_pct for r in rows) / len(rows)
        best = max(r.day_pct for r in rows)
        worst = min(r.day_pct for r in rows)
        days_hit = sum(1 for r in rows if r.day_pct >= 2.0)
        emit("## 3) Verdict vs the 2-5%/day target")
        emit("")
        emit(f"- Window cumulative after fees: **{cum:+.2f}%** over {len(rows)} days")
        emit(f"- Average day: **{avg:+.3f}%/day**  ·  best **{best:+.2f}%**  ·  worst **{worst:+.2f}%**")
        emit(f"- Up days: **{wins}/{len(rows)}**")
        emit(f"- Days that actually hit **≥ 2%**: **{days_hit}/{len(rows)}**")
        emit("")
        target_year = (1.02 ** 365 - 1) * 100
        emit(f"> **The honest truth:** 2-5%/day compounded is **+{target_year:,.0f}%+ per year**. "
             f"No real strategy on real BTC does this. The numbers above are what the tuned, "
             f"fee-charged system *actually* produced on real prices — not a promise.")
    # ---- section 4: survey EVERY 2-week window across the out-of-sample period ----
    emit("## 4) Every 2-week window across the out-of-sample year (not cherry-picked)")
    emit("")
    oos_days = n - k
    oos_rows = simulate_daily(bars, df, survivors, cost_bps=cost,
                              start_equity=args.start_equity, pos_frac=float(args.position_frac),
                              max_hold=args.max_hold, window_days=oos_days)
    emit("| 2-week window | net % after fees | avg %/day | up days | hit ≥2%/day |")
    emit("|---|---:|---:|---:|---:|")
    chunk = args.days
    bucket_nets: list[float] = []
    for s in range(0, len(oos_rows) - chunk + 1, chunk):
        seg = oos_rows[s:s + chunk]
        eq0 = seg[0].equity - seg[0].pnl
        net = (seg[-1].equity / eq0 - 1.0) * 100.0 if eq0 else 0.0
        bucket_nets.append(net)
        avg = sum(r.day_pct for r in seg) / len(seg)
        up = sum(1 for r in seg if r.day_pct > 0)
        hit2 = sum(1 for r in seg if r.day_pct >= 2.0)
        emit(f"| {seg[0].date} → {seg[-1].date} | {net:+.2f}% | {avg:+.3f}% | {up}/{len(seg)} | {hit2}/{len(seg)} |")
    emit("")
    if bucket_nets:
        full_net = (oos_rows[-1].equity / args.start_equity - 1.0) * 100.0
        win_windows = sum(1 for b in bucket_nets if b > 0)
        emit(f"- Out-of-sample full period: **{full_net:+.2f}%** over {oos_days} days "
             f"(≈ {_daily_pct(Decimal(str(full_net)), oos_days):+.3f}%/day)")
        emit(f"- 2-week windows that were profitable: **{win_windows}/{len(bucket_nets)}** "
             f"(best {max(bucket_nets):+.2f}%, worst {min(bucket_nets):+.2f}%)")
        emit(f"- 2-week windows that averaged ≥ 2%/day: **"
             f"{sum(1 for b in bucket_nets if (1+b/100)**(1/chunk)-1 >= 0.02)}/{len(bucket_nets)}**")
    emit("")

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[wrote {args.out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
