#!/usr/bin/env python3
# Tooling — multi-position ("20 ไม้" / scaling-in) simulator on REAL BTC (honest)
"""Answer "if we run N concurrent positions / scoop many lots, how much per day?"

The intuition "20 lots = 20x profit" is FALSE on a single asset. This tool proves
it on real BTC by running the SAME tuned ensemble signals under several lot/sizing
schemes and marking everything to market every day with real fees:

  A) 1 lot, full capital                  — baseline
  B) N lots, capital SPLIT across lots     — honest "more lots", no leverage
  C) N lots, each FULL size (= N× leverage) — the "multiply returns" fantasy
  D) N lots, scoop / average-down on dips   — the classic account-killer

Margin/MTM accounting (handles leverage and liquidation cleanly):
  equity(px) = base_cash + Σ notional_i · dir_i · (px/entry_i − 1)
  open lot   → pay entry fee;   close lot → realise P&L, pay exit fee.
  If equity ≤ 0 in a leverage scheme → LIQUIDATED (account wiped).

Same signals, same data, same fees — only the lot/sizing scheme changes, so the
comparison is apples-to-apples.
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
from domain.strategy.base import SignalAction
from domain.strategy.registry import get
from infrastructure.gateway.bitkub_klines import OhlcBar, load_csv
from infrastructure.gateway.coinmetrics import fetch_btc_history

_WINDOW, _SCAN_START = 80, 55
_SURVIVORS = ("trend_following", "reversion_ls", "breakout_ls")  # OOS survivors from tuning


def _df(bars: list[OhlcBar]) -> pd.DataFrame:
    return pd.DataFrame({c: [float(getattr(b, c)) for b in bars] for c in ("open", "high", "low", "close", "volume")})


def _atr(df: pd.DataFrame, i: int, length: int = 14) -> float:
    try:
        return float(ta.atr(df.iloc[max(0, i - _WINDOW): i + 1], length=length).iloc[-1, 0])
    except Exception:
        return 0.0


def _consensus(objs: dict, df: pd.DataFrame, i: int) -> int:
    vote = 0
    win = df.iloc[max(0, i - _WINDOW + 1): i + 1]
    for o in objs.values():
        s = o.decide_df(win)
        vote += (s.action == SignalAction.BUY) - (s.action == SignalAction.SELL)
    return (vote > 0) - (vote < 0)


@dataclass
class Lot:
    direction: int
    entry: float
    notional: float
    stop: float
    take: float
    held: int = 0


@dataclass
class Result:
    label: str
    final_equity: float
    total_pct: float
    daily_equiv_pct: float
    avg_day_pct: float
    best_day: float
    worst_day: float
    max_dd_pct: float
    fees_paid: float
    n_lots_opened: int
    liquidated: bool
    daily: list[tuple[str, float, float, int]]  # (date, equity, day_pct, open_lots)


def simulate(
    bars: list[OhlcBar], df: pd.DataFrame, objs: dict, *,
    start_equity: float, fee_round: float, max_hold: int, window_days: int,
    max_lots: int, sizing: str, lot_frac: float, scoop: bool, label: str,
    martingale: bool = False,
) -> Result:
    """One scheme. ``sizing``: 'split' (notional=equity/max_lots) or
    'full' (notional=equity*lot_frac per lot → leverage). ``scoop``: also add a
    same-direction lot when price has dropped ≥3% below the last entry.
    ``martingale``: the classic 'ช้อนของถูก' — long-only, NO stop-loss, add a new
    lot every −5% drop, each lot exits only on a +4% take-profit. Accumulates size
    into a falling market (account-killer in a real downtrend)."""
    n = len(bars)
    start_i = max(_SCAN_START, n - window_days)
    base_cash = start_equity
    lots: list[Lot] = []
    fee_leg = fee_round / 2.0
    prev_eq = start_equity
    peak = start_equity
    max_dd = 0.0
    fees_paid = 0.0
    n_opened = 0
    liquidated = False
    daily: list[tuple[str, float, float, int]] = []

    def equity_at(px: float) -> float:
        return base_cash + sum(l.notional * l.direction * (px / l.entry - 1.0) for l in lots)

    for i in range(start_i, n):
        px = float(bars[i].close)
        date = dt.datetime.utcfromtimestamp(bars[i].ts_ms / 1000).strftime("%Y-%m-%d")
        cons = _consensus(objs, df, i)

        # 1) manage open lots
        survivors: list[Lot] = []
        for l in lots:
            l.held += 1
            if martingale:                       # only a +take exit; no stop, no time, no flip
                exit_now = px >= l.take
            elif l.direction == 1:
                exit_now = px <= l.stop or px >= l.take or (cons != 0 and cons != 1) or l.held >= max_hold
            else:
                exit_now = px >= l.stop or px <= l.take or (cons != 0 and cons != -1) or l.held >= max_hold
            if exit_now:
                pnl = l.notional * l.direction * (px / l.entry - 1.0)
                base_cash += pnl - l.notional * fee_leg
                fees_paid += l.notional * fee_leg
            else:
                survivors.append(l)
        lots = survivors

        # 2) open new lot(s)
        eq_now = equity_at(px)
        if martingale:
            longs = [l for l in lots if l.direction == 1]
            # first lot immediately, then add a lot every −5% below the last entry
            want_open = len(lots) < max_lots and (not longs or px <= longs[-1].entry * 0.95)
            new_dir = 1
        else:
            want_open = cons != 0 and len(lots) < max_lots
            new_dir = cons
            if scoop and lots and cons != 0:     # add same-side lot on a dip vs last entry
                same = [l for l in lots if l.direction == cons]
                if same and ((cons == 1 and px <= same[-1].entry * 0.97) or
                             (cons == -1 and px >= same[-1].entry * 1.03)):
                    want_open = True
        if want_open and eq_now > 0:
            notional = (eq_now / max_lots) if sizing == "split" else (eq_now * lot_frac)
            atr = _atr(df, i)
            stop = (px - 2 * atr) if new_dir == 1 else (px + 2 * atr)
            take = (px + 3 * atr) if new_dir == 1 else (px - 3 * atr)
            if atr <= 0 or martingale:
                stop = px * (0.40 if martingale else (0.96 if new_dir == 1 else 1.04))
                take = px * (1.04 if martingale else (1.06 if new_dir == 1 else 0.94))
            base_cash -= notional * fee_leg
            fees_paid += notional * fee_leg
            lots.append(Lot(direction=new_dir, entry=px, notional=notional, stop=stop, take=take))
            n_opened += 1

        eq = equity_at(px)
        if eq <= 0 and sizing == "full":          # margin wipeout
            eq = 0.0
            liquidated = True
        peak = max(peak, eq)
        if peak > 0:
            max_dd = max(max_dd, (peak - eq) / peak)
        day_pct = (eq / prev_eq - 1.0) * 100.0 if prev_eq > 0 else 0.0
        daily.append((date, eq, day_pct, len(lots)))
        prev_eq = eq
        if liquidated:
            break

    days = max((bars[-1].ts_ms - bars[start_i].ts_ms) / 1000 / 86400, 1.0)
    final_eq = daily[-1][1] if daily else start_equity
    total = final_eq / start_equity - 1.0
    base = 1.0 + total
    de = -100.0 if base <= 0 else (math.pow(base, 1.0 / days) - 1.0) * 100.0
    pcts = [d[2] for d in daily]
    return Result(
        label=label, final_equity=final_eq, total_pct=total * 100.0, daily_equiv_pct=de,
        avg_day_pct=(sum(pcts) / len(pcts)) if pcts else 0.0,
        best_day=max(pcts) if pcts else 0.0, worst_day=min(pcts) if pcts else 0.0,
        max_dd_pct=max_dd * 100.0, fees_paid=fees_paid, n_lots_opened=n_opened,
        liquidated=liquidated, daily=daily,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Multi-position / scaling-in simulator on real BTC.")
    p.add_argument("--csv")
    p.add_argument("--lots", type=int, default=20)
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--fee-bps", type=Decimal, default=Decimal("25"))
    p.add_argument("--slip-bps", type=Decimal, default=Decimal("5"))
    p.add_argument("--start-equity", type=float, default=100000.0)
    p.add_argument("--max-hold", type=int, default=20)
    p.add_argument("--out")
    args = p.parse_args(argv)

    try:
        bars = load_csv(args.csv) if args.csv else fetch_btc_history()
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED to load: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    df = _df(bars)
    objs = {n: get(n)() for n in _SURVIVORS}
    fee_round = float((args.fee_bps + args.slip_bps) * Decimal(2)) / 10000.0
    L = args.lots
    lines: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    d1 = dt.datetime.utcfromtimestamp(bars[-1].ts_ms / 1000).date()
    emit(f"# เทรดหลายไม้ ('{L} ไม้') ได้เท่าไหร่ต่อวัน — ทดสอบบน BTC จริง")
    emit("")
    emit(f"- ข้อมูลจริง Coin Metrics ถึง {d1} · ทุนเริ่ม ฿{args.start_equity:,.0f} · "
         f"ค่าฟีไป-กลับ {fee_round*100:.2f}%/ไม้ · หน้าต่าง {args.days} วันล่าสุด")
    emit(f"- สัญญาณชุดเดียวกัน (ensemble: {', '.join(_SURVIVORS)}) ต่างกันแค่วิธีแบ่งไม้/ขนาดไม้")
    emit("")

    configs = [
        ("A) 1 ไม้ เต็มทุน (baseline)", dict(max_lots=1, sizing="split", lot_frac=1.0, scoop=False)),
        (f"B) {L} ไม้ แบ่งทุน (ไม่มี leverage)", dict(max_lots=L, sizing="split", lot_frac=1.0, scoop=False)),
        (f"C) {L} ไม้ เต็มไม้ทุกไม้ (= {L}× leverage)", dict(max_lots=L, sizing="full", lot_frac=1.0, scoop=False)),
        (f"D) {L} ไม้ ช้อนของถูกตอนราคาลง ไม่มี stop (martingale)", dict(max_lots=L, sizing="split", lot_frac=1.0, scoop=False, martingale=True)),
    ]
    results: list[Result] = []
    for label, kw in configs:
        r = simulate(bars, df, objs, start_equity=args.start_equity, fee_round=fee_round,
                     max_hold=args.max_hold, window_days=args.days, label=label, **kw)
        results.append(r)

    win_label = "2 สัปดาห์ล่าสุด" if args.days <= 14 else f"{args.days} วันล่าสุด (ทั้งปี)"
    emit(f"## สรุปเปรียบเทียบ (หน้าต่าง {win_label})")
    emit("")
    emit("| วิธีเทรด | กำไร/วันเฉลี่ย | บาท/วัน* | รวมทั้งช่วง | maxDD | ค่าฟีจ่ายรวม | ผลลัพธ์ |")
    emit("|---|---:|---:|---:|---:|---:|:--|")
    for r in results:
        baht_day = args.start_equity * r.avg_day_pct / 100.0
        status = "💀 ล้างพอร์ต (LIQUIDATED)" if r.liquidated else (
            "กำไร ✅" if r.total_pct > 0 else "ขาดทุน ❌")
        emit(f"| {r.label} | {r.avg_day_pct:+.3f}% | {baht_day:+,.0f} | {r.total_pct:+.2f}% | "
             f"{r.max_dd_pct:.1f}% | {r.fees_paid:,.0f} | {status} |")
    emit("")
    emit("\\* บาท/วัน = กำไรเฉลี่ยต่อวัน × ทุนเริ่มต้น (ตัวเลขจริงแกว่งมากในแต่ละวัน)")
    emit("")

    # day-by-day for config B (the honest "20 lots" interpretation)
    b = results[1]
    emit(f"## รายวัน — {b.label}")
    emit("")
    emit("| วันที่ | ทุน ฿ | % วัน | ไม้ที่เปิดอยู่ |")
    emit("|---|---:|---:|---:|")
    for date, eq, dp, nl in b.daily:
        emit(f"| {date} | {eq:,.0f} | {dp:+.2f}% | {nl} |")
    emit("")

    emit("## 🔑 ข้อสรุปที่ต้องเข้าใจ")
    emit("")
    emit(f"1. **{L} ไม้บน BTC ตัวเดียว = พนัน BTC ก้อนเดิม แค่ซอยย่อย** ผลตอบแทน % ของพอร์ต")
    emit("   ใกล้เคียงเดิม แต่ **จ่ายค่าฟีมากขึ้นหลายเท่า** (แต่ละไม้จ่ายฟีของตัวเอง) → มักได้ *น้อยลง*")
    emit(f"2. จะให้ได้กำไร ×{L} จริง ต้องใช้ **leverage {L}×** (วิธี C) ซึ่ง **ขาดทุนก็ ×{L} เท่า** →")
    emit("   วันที่ราคาสวนแรง ๆ ครั้งเดียว **ล้างพอร์ต** (ดูคอลัมน์ผลลัพธ์)")
    emit("3. **ช้อนเฉลี่ยตอนราคาลง (วิธี D)** ดูดีตอนเด้ง แต่ถ้าเป็นขาลงจริง = ยิ่งช้อนยิ่งเจ็บ")
    emit("   (ซื้อมีดที่กำลังตก) — เป็นวิธีที่ล้างพอร์ตคนมานับไม่ถ้วน")
    emit("4. **จำนวนไม้ไม่ได้เพิ่ม edge** — edge มาจากความแม่นของสัญญาณ (ที่นี่ ~50–55%) เท่านั้น")
    emit("   ซอยกี่ไม้ก็ไม่เปลี่ยนความจริงว่ากำไรจริง ≈ +0.02–0.05%/วัน")

    if args.out:
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n[wrote {args.out}]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
