#!/usr/bin/env python3
"""
================================================================================
SET DAILY EDGE FINDER v1 — ระบบเทรดหุ้นไทย "รายวัน" (ไฟล์เดียวจบ รันได้ทันที)
================================================================================
ระบบหา "จุดเข้ารายวัน" เชิงสถิติ: ค้นสมการเข้า-ออกแบบครบทุกความเป็นไปได้
(exhaustive) บนข้อมูลจริง -> ยืนยัน 2 ช่วง out-of-sample -> จำลองพอร์ตจริง
(กำไร %/วัน) -> ฟันธงออร์เดอร์ของ "พรุ่งนี้" -> บันทึก track record + dashboard

--------------------------------------------------------------------------------
ทำไมระบบเดิม (รายสัปดาห์) หาจุดเข้าไม่ได้เลย — สาเหตุจริง 6 ข้อ ที่แก้แล้วในไฟล์นี้
--------------------------------------------------------------------------------
 1. FRIDAY_ONLY=True  ตัดสัญญาณทิ้ง ~80% (นับเฉพาะแท่งท้ายสัปดาห์) แล้วยังบังคับ
    MIN_RESOLVED>=30 -> แทบไม่มี combo ไหนมีไม้พอ            -> ตัดทิ้ง เทรดทุกวัน
 2. สุ่ม 3M จาก 446M combo ที่ "ซ้ำกันเอง" (พารามิเตอร์ 21 มิติ แต่แต่ละสมการใช้จริง
    2-4 มิติ) -> ค้น 3 ล้านครั้งได้สมการต่างกันจริงไม่กี่พัน  -> ค้นแบบ exhaustive
    เฉพาะมิติที่สมการนั้นใช้จริง = ครบ 100% ของ space ที่มีความหมาย
 3. precompute แยก in-sample/out-of-sample -> อินดิเคเตอร์ warm-up ใหม่ (SMA50/EMA100
    เป็น NaN ~100 แท่งแรกของ OOS) -> OOS แทบไม่มีสัญญาณ -> "ยืนยันไม่ผ่าน" ทุกครั้ง
                                                            -> precompute ครั้งเดียวบน
    ข้อมูลเต็ม แล้วแบ่งด้วย mask + embargo (ไม่มี warm-up ซ้ำ ไม่มี leakage)
 4. เกณฑ์ WR>=70% และกำไร>=3%/ไม้ พร้อมกัน บน hold 5-10 วัน = แทบเป็นไปไม่ได้
                                                            -> เกณฑ์ตั้งได้ + รายงาน
    "เกรด A (ถึงเป้า) / เกรด B (ดีสุดที่ยืนยันได้จริง)" แยกกันชัด ไม่โกหก
 5. ตรรกะสัญญาณถูกเขียน 2 ที่ (vectorized สำหรับ backtest + pandas loop สำหรับสัญญาณสด)
    -> เพี้ยนกันได้เงียบ ๆ                                   -> เหลือทางเดียว ใช้ mask
    ชุดเดียวกันทั้ง backtest และสัญญาณวันนี้ (พิสูจน์ด้วยเทสต์)
 6. ฟันธงต้องให้ Top-5 เห็นตรงกัน >=3 สมการ "บนแท่งศุกร์" เท่านั้น -> ยิงยากมาก
                                                            -> ฉันทามติปรับได้ + เทรดทุกวัน

--------------------------------------------------------------------------------
วิธีรัน
--------------------------------------------------------------------------------
  Colab   :  !pip install yfinance pandas numpy --quiet
             วางไฟล์นี้ทั้งไฟล์ แล้ว Run  (ต่อ internet เพื่อดึงราคาสด)
  เครื่อง :  pip install yfinance pandas numpy
             python daily_edge_finder.py              # รันจริง (ดึงราคาสด)
             python daily_edge_finder.py --demo       # รันสาธิตแบบไม่ต้องต่อเน็ต
             python daily_edge_finder.py --fast       # ค้นแบบย่อ (เร็ว ~1/6 เวลา)
             python daily_edge_finder.py --selftest   # รันเทสต์ทั้งชุด (ต้องมี pytest)
  จังหวะใช้จริง : รันทุกเย็นหลังตลาดปิด (>=18:00) -> อ่านคำฟันธง -> ตั้งคำสั่งเช้าวันถัดไป
                  (วันถัดไประบบตัดสินผลไม้เก่าให้เองอัตโนมัติจากราคาจริง)

--------------------------------------------------------------------------------
Pipeline
--------------------------------------------------------------------------------
  fetch_prices -> precompute (อินดิเคเตอร์+forward bars+breadth, ครั้งเดียว)
  -> split IS/OOS1/OOS2 ด้วย mask + embargo
  -> run_search (exhaustive ต่อ family) -> validate 2 ช่วง -> จัดเกรด A/B
  -> portfolio_backtest (พอร์ตจริง: จำกัดไม้/เงินสด -> กำไร %/วันจริง)
  -> DailyVerdictAgent (ออร์เดอร์พรุ่งนี้) -> journal + dashboard.html

--------------------------------------------------------------------------------
สมการจุดเข้า 10 ตระกูล (บูลีนล้วน ใช้เฉพาะข้อมูลถึงแท่งที่ปิดแล้ว = ไม่มองอนาคต)
--------------------------------------------------------------------------------
  0 MR_RSI_BB          RSI < th  AND  Close < Bollinger_lower
  1 DONCHIAN_BREAKOUT  Close > max(Close, N แท่งก่อนหน้า)
  2 TREND_PULLBACK     EMA_fast > EMA_slow  AND  RSI < th
  3 MACD_CROSS         MACD ตัดขึ้นเหนือ signal (EMA9)
  4 STOCH_OVERSOLD     Stochastic %K < th
  5 GAP_DOWN_REVERSAL  เปิด gap ลง >= x%  AND  Close > Open
  6 VOLSPIKE_BREAKOUT  Volume >= m × VolSMA20  AND  Close > Donchian
  7 INSIDE_BAR_BREAK   แท่งก่อนเป็น inside bar  AND  Close > High แท่งก่อน
  8 DOWN_STREAK_BOUNCE ปิดลบติดกัน k วัน (+ ตัวเลือก: ยืนเหนือ SMA200)
  9 SMA_RECLAIM        Close ตัดขึ้นเหนือ SMA(n) จากใต้เส้น

--------------------------------------------------------------------------------
สมการออก + การคิดกำไร (ตรงกับความจริงมากกว่าเดิม)
--------------------------------------------------------------------------------
  โหมด %      : TP = entry×(1+tp/100), SL = entry×(1-sl/100)
  โหมด ATR    : TP = entry + tp×ATR14,  SL = entry - sl×ATR14
  เข้า        : market = ราคาเปิดแท่งถัดไป | limit = ตั้งซื้อต่ำกว่าปิด x% (ติดวันแรกเท่านั้น)
  *** GAP FILL: ถ้าแท่งถัดมาเปิด "ทะลุ" SL/TP ไปแล้ว ระบบคิดราคาออกที่ "ราคาเปิดจริง"
      ไม่ใช่ที่ระดับ SL/TP (ระบบเดิมคิดที่ระดับ SL = โกหกตัวเอง ทำให้ผลดูดีเกินจริง)
  ชนกันในแท่งเดียว (High>=TP และ Low<=SL) -> SL ชนะ (นับแพ้) = worst case ซื่อสัตย์
  กำไรสุทธิ/ไม้ = (exit/entry - 1)×100 - FRICTION_PCT (หักค่าคอม+VAT ไป-กลับก่อนเสมอ)
  ชนะ = "กำไรสุทธิ > 0 หลังหักต้นทุน" (ไม่ใช่แค่แตะ TP) -> WR ที่รายงานคือของจริง

--------------------------------------------------------------------------------
ความสัตย์จริง (ห้ามโกหก)
--------------------------------------------------------------------------------
  * เป้าที่สั่ง: WR > 80% และกำไร > 2% ต่อวัน — ระบบตั้งเกณฑ์นี้เป็น "เกรด A" ตรง ๆ
  * ถ้าไม่มีสมการไหนถึงเกรด A ระบบจะบอกตรง ๆ ว่า "ไม่ถึงเป้า" แล้วแสดง "เกรด B"
    = สมการที่ดีที่สุดเท่าที่ยืนยันได้จริงบนข้อมูลที่ไม่เคยเห็น พร้อมตัวเลขจริง
  * ตัวเลขทุกตัวหักต้นทุนแล้ว + tie นับแพ้ + gap คิดราคาจริง + Wilson lower bound 95%
  * ไม่การันตีผลอนาคต ไม่ใช่คำแนะนำการลงทุน ผู้ใช้รับความเสี่ยงเอง
================================================================================
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime

import numpy as np
import pandas as pd

# ============================================================== CONFIG (แก้ได้)
# ---- Universe ----
QUALITY19 = ["ADVANC", "CPALL", "GULF", "PTT", "BDMS", "KTB", "WHA", "KBANK",
             "SCB", "AOT", "TRUE", "BEM", "CPN", "BBL", "CRC", "TISCO",
             "HMPRO", "AP", "SCC"]

# หุ้นสภาพคล่องสูง (ซื้อ-ขายได้จริง ไม่ติดกระดาน) — ค่าเริ่มต้นของระบบรายวัน
SET50 = [
    "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BDMS", "BEM", "BGRIM", "BH", "BTS",
    "CBG", "CPALL", "CPAXT", "CPF", "CPN", "CRC", "DELTA", "EA", "EGCO", "GLOBAL",
    "GPSC", "GULF", "HMPRO", "INTUCH", "IVL", "KBANK", "KCE", "KTB", "KTC", "LH",
    "MINT", "MTC", "OR", "OSP", "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD", "SCB",
    "SCC", "SCGP", "TIDLOR", "TISCO", "TLI", "TOP", "TRUE", "TTB", "TU", "WHA",
]

SET100_EXTRA = [
    "AAV", "AMATA", "AP", "BA", "BAM", "BCH", "BCP", "BJC", "CENTEL", "CHG",
    "CK", "COM7", "DOHOME", "ERW", "GFPT", "HANA", "ICHI", "IRPC", "JMART",
    "KKP", "M", "MAJOR", "NER", "PLANB", "PR9", "PSL", "QH", "SPALI", "SPRC",
    "SIRI", "STA", "SYNEX", "TASCO", "TCAP", "TVO", "VGI", "WORK",
]

UNIVERSES = {
    "QUALITY19": QUALITY19,
    "SET50": SET50,
    "SET100": list(dict.fromkeys(SET50 + SET100_EXTRA)),
}
UNIVERSE = "SET50"                    # "QUALITY19" | "SET50" | "SET100"
TICKERS = UNIVERSES[UNIVERSE]

HISTORY_PERIOD = "5y"                 # ความยาวข้อมูลที่ดึง

# ---- เป้าหมายที่ผู้ใช้สั่ง (เกรด A) ----
TARGET_WIN_RATE = 80.0                # % ชนะขั้นต่ำ (ชนะ = กำไรสุทธิ > 0)
TARGET_NET_PER_DAY = 2.0              # % กำไรสุทธิต่อ "วันที่ถือ" ขั้นต่ำ
TARGET_NET_PER_TRADE = 2.0            # % กำไรสุทธิเฉลี่ยต่อไม้ขั้นต่ำ

# ---- เกณฑ์ "เกรด B" (ดีที่สุดเท่าที่ยืนยันได้จริง — ใช้เมื่อไม่มีอะไรถึงเกรด A) ----
FLOOR_WIN_RATE = 55.0
FLOOR_NET_PER_DAY = 0.10
FLOOR_WILSON_LB = 50.0                # Wilson 95% lower bound ของ WR

# ---- ความน่าเชื่อถือทางสถิติ ----
MIN_TRADES_IS = 40                    # จำนวนไม้ขั้นต่ำในช่วงค้นหา
MIN_TRADES_OOS = 12                   # จำนวนไม้ขั้นต่ำต่อช่วงยืนยัน (มี 2 ช่วง)
TOP_N_VALIDATE = 400                  # เอา in-sample ที่ดีสุดกี่ตัวไปยืนยัน
TOP_N_REPORT = 20

# ---- ต้นทุน & การเทรดจริง ----
FRICTION_PCT = 2 * (0.157 + 0.10)     # 0.514% ไป-กลับ (คอม+VAT+ค่าธรรมเนียม)
TIE_BREAK_SL_WINS = True              # แท่งเดียวชนทั้ง TP/SL -> นับ SL (ซื่อสัตย์)
MIN_VALID_PRICE = 1e-9
MIN_PRICE_THB = 1.0                   # หุ้นต่ำกว่านี้ = สเปรดกินเรียบ ไม่เทรด
MIN_TURNOVER_THB = 20_000_000         # มูลค่าซื้อขายเฉลี่ย 20 วันขั้นต่ำ (สภาพคล่อง)

# ---- พอร์ตจริง (ใช้จำลอง "กำไร %/วัน" และคำนวณจำนวนหุ้นที่ซื้อได้) ----
CAPITAL_THB = 30_000                  # เงินทุนตั้งต้น
MAX_POSITIONS = 3                     # ถือพร้อมกันสูงสุดกี่ตัว
BOARD_LOT = 100
BUDGET_PER_TRADE_THB = CAPITAL_THB // MAX_POSITIONS

# ---- การแบ่งข้อมูล (walk-forward 3 ช่วง) ----
IS_FRACTION = 0.60                    # ช่วงค้นหา
OOS1_FRACTION = 0.20                  # ช่วงยืนยันที่ 1
                                      # ที่เหลือ = ช่วงยืนยันที่ 2 (ล่าสุด)
EMBARGO_BARS = None                   # None = ใช้ max(hold_days) อัตโนมัติ

# ---- ฉันทามติของ agent ฟันธง ----
VERDICT_TOP_K = 5
VERDICT_MIN_AGREE = 2

# ---- ไฟล์ผลลัพธ์ ----
JOURNAL_PATH = "daily_trade_journal.csv"
PRICE_CACHE_PATH = "price_cache_daily.csv"
DASHBOARD_PATH = "dashboard_daily.html"

RANDOM_SEED = 20260725

# =============================================================== SEARCH SPACE
# หมายเหตุสำคัญ: แต่ละ family ใช้พารามิเตอร์ "เฉพาะที่ตัวเองใช้จริง" (FAMILY_PARAMS)
# ระบบจึงค้นแบบครบทุกความเป็นไปได้ (exhaustive) ได้จริงในเวลาที่ยอมรับได้
SPACE = dict(
    rsi_period=[7, 14],
    rsi_threshold=[10, 20, 30, 40, 50],
    bb_period=[10, 20],
    bb_std=[1.5, 2.0, 2.5],
    donchian_n=[5, 10, 20, 40],
    ema_fast=[8, 12, 20],
    ema_slow=[26, 50, 100],
    stoch_period=[14],
    stoch_th=[10, 15, 20, 25],
    gap_pct=[1.5, 2.0, 3.0],
    vol_mult=[1.5, 2.0, 3.0],
    streak_n=[2, 3, 4],
    sma_n=[20, 50],
    require_trend=[0, 1],
    atr_period=[14],
    exit_mode=[0, 1],
    tp_val=[1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    sl_val=[1.0, 1.5, 2.0, 2.5, 3.0, 5.0],
    hold_days=[1, 2, 3, 5],
    adx_min=[0, 25],
    vol_filter=[0, 1],
    regime_filter=[0, 1],
    entry_mode=[0, 1],                # 0 = market ราคาเปิดถัดไป, 1 = limit -1%
)

# คู่ TP/SL ที่จะค้น (แยกตามโหมด: % กับ ATR-multiple คนละสเกลกัน)
EXIT_COMBOS = (
    [(0, tp, sl) for tp in (1.0, 1.5, 2.0, 3.0, 4.0, 5.0)
     for sl in (1.0, 1.5, 2.0, 3.0, 5.0)] +
    [(1, tp, sl) for tp in (1.0, 1.5, 2.0, 3.0) for sl in (1.0, 1.5, 2.0, 3.0)]
)

FAMILY_NAME = {
    0: "MR_RSI_BB", 1: "DONCHIAN_BREAKOUT", 2: "TREND_PULLBACK", 3: "MACD_CROSS",
    4: "STOCH_OVERSOLD", 5: "GAP_DOWN_REVERSAL", 6: "VOLSPIKE_BREAKOUT",
    7: "INSIDE_BAR_BREAK", 8: "DOWN_STREAK_BOUNCE", 9: "SMA_RECLAIM",
}

# พารามิเตอร์ที่ "แต่ละสมการใช้จริง" — หัวใจของการค้นแบบไม่ซ้ำซ้อน
FAMILY_PARAMS = {
    0: ("rsi_period", "rsi_threshold", "bb_period", "bb_std"),
    1: ("donchian_n",),
    2: ("ema_fast", "ema_slow", "rsi_period", "rsi_threshold"),
    3: ("ema_fast", "ema_slow"),
    4: ("stoch_period", "stoch_th"),
    5: ("gap_pct",),
    6: ("donchian_n", "vol_mult"),
    7: ("require_trend",),
    8: ("streak_n", "require_trend"),
    9: ("sma_n",),
}

# ค่ากลางสำหรับมิติที่ family นั้นไม่ใช้ (ทำให้ทุกสมการมีคีย์ครบเท่ากัน = เทียบ/บันทึกง่าย)
PARAM_DEFAULTS = dict(
    entry_family=0, rsi_period=14, rsi_threshold=30, bb_period=20, bb_std=2.0,
    donchian_n=20, ema_fast=12, ema_slow=26, stoch_period=14, stoch_th=20,
    gap_pct=2.0, vol_mult=2.0, streak_n=3, sma_n=20, require_trend=0,
    atr_period=14, exit_mode=0, tp_val=2.0, sl_val=2.0, hold_days=3,
    adx_min=0, vol_filter=0, regime_filter=0, entry_mode=0,
)
PARAM_KEYS = tuple(PARAM_DEFAULTS.keys())
INT_PARAM_KEYS = {"entry_family", "rsi_period", "bb_period", "donchian_n", "ema_fast",
                  "ema_slow", "stoch_period", "streak_n", "sma_n", "require_trend",
                  "atr_period", "exit_mode", "hold_days", "adx_min", "vol_filter",
                  "regime_filter", "entry_mode"}


def fast_mode(on: bool = True) -> None:
    """ย่อ search space ให้รันเร็ว (สำหรับทดลอง/เครื่องช้า) — ผลจะหยาบกว่าเต็มรูปแบบ."""
    global EXIT_COMBOS
    if not on:
        return
    SPACE["rsi_threshold"] = [20, 30, 40]
    SPACE["bb_std"] = [1.5, 2.0]
    SPACE["donchian_n"] = [10, 20]
    SPACE["ema_fast"] = [12, 20]
    SPACE["ema_slow"] = [26, 50]
    SPACE["stoch_th"] = [15, 25]
    SPACE["hold_days"] = [1, 3, 5]
    SPACE["adx_min"] = [0]
    EXIT_COMBOS = ([(0, tp, sl) for tp in (1.5, 2.0, 3.0, 5.0) for sl in (1.5, 2.0, 3.0)] +
                   [(1, tp, sl) for tp in (1.5, 2.0, 3.0) for sl in (1.5, 2.0, 3.0)])


# ================================================================ SMALL UTILS
def _safe_int(val, default: int) -> int:
    """int() ที่ไม่ crash — NaN/None/ขยะ -> default (บั๊ก [ครัช] ของระบบเดิม)."""
    try:
        if val is None:
            return default
        if isinstance(val, (float, np.floating)) and not np.isfinite(val):
            return default
        if pd.isna(val):
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val, default: float = float("nan")) -> float:
    """float() ที่ไม่ crash — ขยะ -> default (ค่าเริ่มต้น NaN ให้ผู้เรียกตัดสินใจ)."""
    try:
        if val is None:
            return default
        f = float(val)
        return f
    except (ValueError, TypeError):
        return default


def wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    """ขอบล่างความเชื่อมั่น 95% ของสัดส่วนชนะ — กัน 8/10 หลอกตา (คืนค่า 0..1)."""
    if n <= 0:
        return 0.0
    wins = max(0, min(int(wins), int(n)))
    p = wins / n
    return (p + z * z / (2 * n) - z * np.sqrt((p * (1 - p) + z * z / (4 * n)) / n)) / (1 + z * z / n)


def _r(x, nd: int = 2):
    """ปัดทศนิยมแบบไม่ crash และไม่ปล่อย inf/NaN ปนเปื้อนรายงาน."""
    f = _safe_float(x)
    if not np.isfinite(f):
        return None
    return round(f, nd)


# ============================================================ DATA LAYER (I/O)
def _to_naive_datetime(s) -> pd.Series:
    """datetime แบบ tz-naive เสมอ — รองรับทั้ง tz-aware และ naive (yfinance คืนไม่เหมือนกัน)."""
    dt = pd.to_datetime(s)
    if not isinstance(dt, pd.Series):
        dt = pd.Series(dt)
    tz = getattr(dt.dt, "tz", None)
    if tz is not None:
        return dt.dt.tz_convert(None) if hasattr(dt.dt, "tz_convert") else dt.dt.tz_localize(None)
    return dt


PRICE_COLUMNS = ["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"]


def clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    """ทำความสะอาดราคาแบบเดียวกันทุกแหล่ง (สด/แคช/สังเคราะห์):
    ตัดแถวราคา<=0 / NaN / High<Low / วันซ้ำ แล้วเรียงตาม (Ticker, Date)."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=PRICE_COLUMNS)
    d = df.copy()
    missing = [c for c in PRICE_COLUMNS if c not in d.columns]
    if missing:
        raise ValueError(f"ข้อมูลราคาขาดคอลัมน์: {missing}")
    d = d[PRICE_COLUMNS]
    d["Date"] = _to_naive_datetime(d["Date"])
    for c in ("Open", "High", "Low", "Close", "Volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    px = ["Open", "High", "Low", "Close"]
    d = d.dropna(subset=["Ticker", "Date"] + px)
    d = d[(d[px] > MIN_VALID_PRICE).all(axis=1)]
    d = d[np.isfinite(d[px]).all(axis=1)]
    d = d[d["High"] >= d["Low"]]
    d["Volume"] = d["Volume"].fillna(0.0).clip(lower=0.0)
    d = d.drop_duplicates(subset=["Ticker", "Date"], keep="last")
    return d.sort_values(["Ticker", "Date"]).reset_index(drop=True)


def fetch_prices(tickers=None, period: str = HISTORY_PERIOD, retries: int = 3,
                 cache_path: str | None = PRICE_CACHE_PATH) -> pd.DataFrame:
    """ดึงราคาสดจาก yfinance (Layer 3 — แตะ network เท่านั้น).
    - retry ต่อ ticker เมื่อ network สะดุด
    - auto_adjust=True: ปรับ split/ปันผลแล้ว -> ไม่มี gap ปลอมวัน XD ทำสถิติเพี้ยน
    - สำเร็จแล้วเซฟแคช CSV: รันซ้ำ/รันออฟไลน์ได้ (และกู้คืนได้เมื่อเน็ตล่ม)"""
    tickers = list(TICKERS if tickers is None else tickers)
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("ต้องติดตั้งก่อน: pip install yfinance") from e
    parts, ok, failed = [], [], []
    print(f"[{datetime.now():%H:%M:%S}] ดึงข้อมูลสด {len(tickers)} ตัว ...", flush=True)
    for t in tickers:
        d = None
        for attempt in range(1, max(1, retries) + 1):
            try:
                d = yf.Ticker(t + ".BK").history(period=period, interval="1d", auto_adjust=True)
                break
            except Exception as e:
                if attempt >= retries:
                    print(f"  [!] {t}: {e}", flush=True)
                else:
                    time.sleep(min(2 ** attempt, 8))
        if d is None or len(d) == 0:
            failed.append(t)
            continue
        try:
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d.reset_index()
            d["Date"] = _to_naive_datetime(d[d.columns[0]])
            d["Ticker"] = t
            parts.append(d[PRICE_COLUMNS].copy())
            ok.append(t)
        except Exception as e:
            failed.append(t)
            print(f"  [!] {t} (parse): {e}", flush=True)
    if not parts:
        if cache_path and os.path.exists(cache_path):
            print("  ดึงสดไม่สำเร็จเลย -> ใช้แคชเดิมแทน")
            return load_price_cache(cache_path)
        raise RuntimeError("ดึงข้อมูลไม่สำเร็จเลย และไม่มีแคชสำรอง")
    df = clean_prices(pd.concat(parts, ignore_index=True))
    print(f"  สำเร็จ {len(ok)} | ล้มเหลว {len(failed)}: {failed if failed else '-'}")
    if len(df):
        print(f"  ช่วง: {df['Date'].min():%Y-%m-%d} ถึง {df['Date'].max():%Y-%m-%d} | {len(df):,} แถว")
    if cache_path:
        try:
            df.to_csv(cache_path, index=False)
        except OSError as e:
            print(f"  [!] เซฟแคชไม่ได้: {e}")
    return df


def load_price_cache(path: str = PRICE_CACHE_PATH) -> pd.DataFrame:
    """โหลดราคาจากแคช CSV (ใช้รันซ้ำ/ออฟไลน์). ไฟล์เสีย -> DataFrame ว่าง."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=PRICE_COLUMNS)
    try:
        return clean_prices(pd.read_csv(path))
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        print(f"  [!] แคชเสีย ({e}) -> เริ่มใหม่")
        return pd.DataFrame(columns=PRICE_COLUMNS)


def synthetic_prices(tickers=None, n_days: int = 1300, seed: int = RANDOM_SEED,
                     start: str = "2021-01-04") -> pd.DataFrame:
    """สร้างราคาสังเคราะห์เสมือนจริง (ไม่ต้องต่อเน็ต) — ใช้สำหรับ --demo และเทสต์.
    มี: เทรนด์ระยะยาว, ระบอบผันผวนสลับ (regime switching), หางหนา (fat tail),
    ช่วง intraday สมจริง, วอลุ่มสหสัมพันธ์กับความผันผวน, gap ข้ามคืน.
    เตือนตามตรง: ข้อมูลนี้ 'ไม่ใช่ตลาดจริง' ใช้พิสูจน์ว่าโปรแกรมทำงานถูก เท่านั้น."""
    tickers = list(TICKERS if tickers is None else tickers)
    dates = pd.bdate_range(start=start, periods=int(n_days))
    parts = []
    for i, tk in enumerate(tickers):
        r = np.random.default_rng(seed + i * 7919)
        drift = r.normal(0.0003, 0.0004)
        vol_lo, vol_hi = 0.010, 0.026
        regime = np.zeros(len(dates))
        state, p_switch = 0, 0.02
        for k in range(len(dates)):
            if r.random() < p_switch:
                state = 1 - state
            regime[k] = vol_lo if state == 0 else vol_hi
        shock = r.standard_t(df=4, size=len(dates)) / np.sqrt(2.0)
        ret = drift + regime * shock
        close = 100.0 * np.exp(np.cumsum(ret)) * float(r.uniform(0.15, 4.0))
        prev = np.concatenate([[close[0]], close[:-1]])
        gap = r.normal(0, 0.4) / 100.0 + r.normal(0, 0.004, len(dates))
        open_ = prev * (1 + gap)
        rng_pct = np.abs(r.normal(0, 1, len(dates))) * regime * 1.6 + 0.002
        hi = np.maximum(open_, close) * (1 + rng_pct * r.uniform(0.3, 0.9, len(dates)))
        lo = np.minimum(open_, close) * (1 - rng_pct * r.uniform(0.3, 0.9, len(dates)))
        vol = (r.lognormal(mean=15.0, sigma=0.6, size=len(dates))
               * (1 + 8 * np.abs(ret)))
        parts.append(pd.DataFrame({
            "Ticker": tk, "Date": dates, "Open": open_, "High": hi,
            "Low": lo, "Close": close, "Volume": vol,
        }))
    return clean_prices(pd.concat(parts, ignore_index=True))


# ================================================== INDICATORS (Layer 1, pure)
def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    """RSI แบบ Wilder — กันหารศูนย์: ราคานิ่ง=50, ขึ้นล้วน=100."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1 / period, adjust=False).mean()
    al = loss.ewm(alpha=1 / period, adjust=False).mean()
    out = pd.Series(np.nan, index=close.index, dtype=float)
    warm = ag.isna() | al.isna()
    both0 = (ag == 0) & (al == 0) & ~warm
    loss0 = (al == 0) & (ag > 0) & ~warm
    norm = ~warm & ~both0 & ~loss0
    out[norm] = 100 - (100 / (1 + ag[norm] / al[norm]))
    out[loss0] = 100.0
    out[both0] = 50.0
    return out


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up = high.diff()
    down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
                   axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1 / period, adjust=False).mean().replace(0, np.nan)
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    # clip: กันค่าล้นขอบจากความคลาดเคลื่อนทศนิยม (เช่น 100.00000000000001)
    return dx.ewm(alpha=1 / period, adjust=False).mean().clip(0, 100)


def macd_cross_up(close: pd.Series, fast: int, slow: int, signal: int = 9) -> pd.Series:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))


def stoch_k(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    ll = low.rolling(period).min()
    hh = high.rolling(period).max()
    rng = (hh - ll).replace(0, np.nan)
    return 100 * (close - ll) / rng


def down_streak(close: pd.Series) -> pd.Series:
    """จำนวนวันที่ปิดลบ 'ติดกัน' นับถึงแท่งปัจจุบัน (0 = วันนี้ไม่ลบ)."""
    down = (close.diff() < 0).astype(int)
    grp = (down == 0).cumsum()
    return down.groupby(grp).cumsum().astype(float)


# =============================================== PRECOMPUTE (Layer 1, pure)
def _max_hold() -> int:
    return int(max(SPACE["hold_days"]))


LIMIT_DISCOUNT_PCT = 1.0        # entry_mode=1 : ตั้ง limit ต่ำกว่าราคาปิดสัญญาณ 1%


def precompute(raw: pd.DataFrame) -> pd.DataFrame:
    """คำนวณอินดิเคเตอร์ทั้งหมด + แท่งอนาคต (สำหรับจำลอง exit) ครั้งเดียวบนข้อมูลเต็ม.

    สำคัญ (แก้บั๊ก [ร้าย] ของระบบเดิม): ต้องคำนวณบนข้อมูล 'เต็มชุด' แล้วค่อยแบ่ง
    in-sample / out-of-sample ด้วย mask ทีหลัง. ระบบเดิมแบ่งข้อมูลก่อนแล้วค่อยคำนวณ
    -> SMA50/EMA100/SMA200 ต้อง warm-up ใหม่ ทำให้ ~100-200 แท่งแรกของ OOS เป็น NaN
    -> OOS แทบไม่มีสัญญาณ -> 'ยืนยันไม่ผ่าน' ทุกครั้ง (คือสาเหตุที่หาจุดเข้าไม่ได้).
    อินดิเคเตอร์ทั้งหมดเป็น backward-looking จึงไม่มี look-ahead แม้คำนวณรวดเดียว."""
    if raw is None or len(raw) == 0:
        raise ValueError("precompute: ไม่มีข้อมูลราคา")
    mh = _max_hold()
    rsi_periods = sorted(set(SPACE["rsi_period"]))
    bb_pairs = sorted(set(itertools.product(SPACE["bb_period"], SPACE["bb_std"])))
    ema_spans = sorted(set(SPACE["ema_fast"]) | set(SPACE["ema_slow"]))
    macd_pairs = sorted(set(itertools.product(SPACE["ema_fast"], SPACE["ema_slow"])))
    don_ns = sorted(set(SPACE["donchian_n"]))
    stoch_ps = sorted(set(SPACE["stoch_period"]))
    atr_ps = sorted(set(SPACE["atr_period"]))
    sma_ns = sorted(set(SPACE["sma_n"]))

    parts = []
    for _, g in raw.groupby("Ticker", sort=False):
        g = g.sort_values("Date").reset_index(drop=True)
        o, h, l, c, v = g["Open"], g["High"], g["Low"], g["Close"], g["Volume"]
        out = {}
        out["VolSMA20"] = v.rolling(20).mean()
        out["Turn20"] = (c * v).rolling(20).mean()
        for n in sorted(set(sma_ns) | {50, 200}):
            out[f"SMA{n}"] = c.rolling(n).mean()
        for p in atr_ps:
            out[f"ATR{p}"] = atr(h, l, c, p)
        out["ADX14"] = adx(h, l, c, 14)
        for p in rsi_periods:
            out[f"RSI{p}"] = wilder_rsi(c, p)
        for bp, bs in bb_pairs:
            mid = c.rolling(bp).mean()
            sd = c.rolling(bp).std()
            out[f"BBL{bp}_{bs}"] = mid - bs * sd
        for s in ema_spans:
            out[f"EMA{s}"] = ema(c, s)
        for ef, es in macd_pairs:
            out[f"MACDX{ef}_{es}"] = macd_cross_up(c, ef, es).astype(float)
        for n in don_ns:
            out[f"DON{n}"] = c.rolling(n).max().shift(1)
        for p in stoch_ps:
            out[f"STOCH{p}"] = stoch_k(h, l, c, p)
        prev_close = c.shift(1).replace(0, np.nan)
        out["GapPct"] = (o / prev_close - 1) * 100
        inside_prev = (h.shift(1) < h.shift(2)) & (l.shift(1) > l.shift(2))
        out["InsideBrk"] = (inside_prev & (c > h.shift(1))).astype(float)
        out["DownStreak"] = down_streak(c)
        for n in sma_ns:
            sma_n_s = c.rolling(n).mean()
            out[f"RECLAIM{n}"] = ((c > sma_n_s) & (c.shift(1) <= sma_n_s.shift(1))).astype(float)
        for k in range(1, mh + 1):
            out[f"O{k}"] = o.shift(-k)
            out[f"H{k}"] = h.shift(-k)
            out[f"L{k}"] = l.shift(-k)
            out[f"C{k}"] = c.shift(-k)
        parts.append(pd.concat([g, pd.DataFrame(out, index=g.index)], axis=1))

    data = pd.concat(parts, ignore_index=True)
    # สภาพคล่อง/ราคาขั้นต่ำ: หุ้นถูกเกิน/ซื้อขายบางเกิน = เข้าไม่ได้จริง -> ตัดตั้งแต่ต้น
    data["Tradable"] = ((data["Close"] >= MIN_PRICE_THB)
                        & (data["Turn20"] >= MIN_TURNOVER_THB)).astype(float)
    # market breadth ต่อวัน: สัดส่วนหุ้นที่ยืนเหนือ SMA50 (astype(float) กัน object dtype)
    above = (data["Close"] > data["SMA50"]).astype(float).where(data["SMA50"].notna())
    data["Breadth"] = above.groupby(data["Date"]).transform("mean").astype(float)
    return data


def build_cache(data: pd.DataFrame) -> dict:
    """แปลง DataFrame -> dict ของ numpy array (เร็วขึ้น ~10 เท่าในลูปค้นหา)."""
    mh = _max_hold()
    c: dict = {}
    for col in data.columns:
        if col in ("Ticker", "Date"):
            continue
        c[col] = np.asarray(data[col], dtype=float)
    c["_n"] = len(data)
    c["_date"] = np.asarray(data["Date"], dtype="datetime64[ns]")
    c["_ticker"] = np.asarray(data["Ticker"], dtype=object)
    c["fwd_valid"] = {k: np.isfinite(c[f"C{k}"]) & np.isfinite(c[f"O{k}"])
                      for k in range(1, mh + 1)}
    c["_max_hold"] = mh
    return c


# ============================================ ENTRY SIGNALS (Layer 1, pure)
def _col(c: dict, name: str) -> np.ndarray:
    """อ่านคอลัมน์จาก cache พร้อมข้อความบอกสาเหตุที่ชัดเจน [กันครัชแบบงง ๆ]:
    เกิดเมื่อแก้ SPACE หลัง precompute แล้วค่าพารามิเตอร์ไม่มีคอลัมน์รองรับ."""
    arr = c.get(name)
    if arr is None:
        raise ValueError(f"cache ไม่มีคอลัมน์ '{name}' — ค่าพารามิเตอร์นี้ไม่ได้อยู่ใน SPACE "
                         f"ตอน precompute (แก้ SPACE แล้วต้อง precompute ใหม่)")
    return arr


def entry_mask(c: dict, fam: int, p: dict) -> np.ndarray:
    """สัญญาณเข้าของ family เดียว (บูลีน array ยาวเท่าจำนวนแถว).
    ใช้ 'ทางเดียวกัน' ทั้ง backtest และการหาสัญญาณของวันนี้ -> เพี้ยนกันไม่ได้."""
    close = c["Close"]
    if fam == 0:
        rsi = _col(c, f"RSI{int(p['rsi_period'])}")
        bbl = _col(c, f"BBL{int(p['bb_period'])}_{float(p['bb_std'])}")
        return np.isfinite(rsi) & np.isfinite(bbl) & (rsi < p["rsi_threshold"]) & (close < bbl)
    if fam == 1:
        dh = _col(c, f"DON{int(p['donchian_n'])}")
        return np.isfinite(dh) & (close > dh)
    if fam == 2:
        ef = _col(c, f"EMA{int(p['ema_fast'])}")
        es = _col(c, f"EMA{int(p['ema_slow'])}")
        rsi = _col(c, f"RSI{int(p['rsi_period'])}")
        return (np.isfinite(ef) & np.isfinite(es) & np.isfinite(rsi)
                & (ef > es) & (rsi < p["rsi_threshold"]))
    if fam == 3:
        return _col(c, f"MACDX{int(p['ema_fast'])}_{int(p['ema_slow'])}") > 0.5
    if fam == 4:
        k = _col(c, f"STOCH{int(p['stoch_period'])}")
        return np.isfinite(k) & (k < p["stoch_th"])
    if fam == 5:
        gap = c["GapPct"]
        return np.isfinite(gap) & (gap <= -float(p["gap_pct"])) & (close > c["Open"])
    if fam == 6:
        dh = _col(c, f"DON{int(p['donchian_n'])}")
        vs = c["VolSMA20"]
        return (np.isfinite(dh) & np.isfinite(vs) & (c["Volume"] >= float(p["vol_mult"]) * vs)
                & (close > dh))
    if fam == 7:
        m = c["InsideBrk"] > 0.5
        if int(p.get("require_trend", 0)) == 1:
            s200 = c["SMA200"]
            m = m & np.isfinite(s200) & (close > s200)
        return m
    if fam == 8:
        m = c["DownStreak"] >= float(p["streak_n"])
        if int(p.get("require_trend", 0)) == 1:
            s200 = c["SMA200"]
            m = m & np.isfinite(s200) & (close > s200)
        return m
    if fam == 9:
        return _col(c, f"RECLAIM{int(p['sma_n'])}") > 0.5
    raise ValueError(f"ไม่รู้จัก entry_family={fam}")


def filter_mask(c: dict, adx_min: int, vol_filter: int, regime_filter: int) -> np.ndarray:
    """ตัวกรองร่วม (ใช้ได้กับทุก family) + เงื่อนไขสภาพคล่องที่บังคับเสมอ."""
    m = c["Tradable"] > 0.5
    if adx_min and adx_min > 0:
        a = c["ADX14"]
        m = m & np.isfinite(a) & (a >= adx_min)
    if vol_filter:
        vs = c["VolSMA20"]
        m = m & np.isfinite(vs) & (c["Volume"] > vs)
    if regime_filter:
        br = c["Breadth"]
        m = m & np.isfinite(br) & (br > 0.5)
    return m


def signal_mask(c: dict, strat: dict, seg: np.ndarray | None = None) -> np.ndarray:
    """สัญญาณสุดท้าย = entry family AND ตัวกรอง AND ช่วงข้อมูลที่เลือก."""
    m = entry_mask(c, int(strat["entry_family"]), strat)
    m = m & filter_mask(c, int(strat.get("adx_min", 0)), int(strat.get("vol_filter", 0)),
                        int(strat.get("regime_filter", 0)))
    if seg is not None:
        m = m & seg
    return m


# ================================================ TRADE SIMULATION (pure)
def _simulate(entry: np.ndarray, tp: np.ndarray, sl: np.ndarray,
              fo: dict, fh: dict, fl: dict, fc: dict, hold: int,
              skip_tp_day1: bool = False):
    """จำลอง bracket order ต่อไม้ (vectorized).

    กติกาต่อแท่ง k (k=1 คือแท่งที่เข้าไม้):
      k>=2 และเปิด <= SL  -> ออกที่ 'ราคาเปิดจริง' (gap ทะลุ = ขาดทุนมากกว่า SL)
      k>=2 และเปิด >= TP  -> ออกที่ 'ราคาเปิดจริง' (gap ทะลุ = กำไรมากกว่า TP)
      ระหว่างวัน Low<=SL  -> ออกที่ SL       | High>=TP -> ออกที่ TP
      ชนทั้งคู่ในแท่งเดียว -> TIE_BREAK_SL_WINS (ค่าเริ่มต้น: SL ชนะ = นับแพ้)
      ครบ hold           -> ออกที่ราคาปิดแท่งสุดท้าย (time exit)
    skip_tp_day1: โหมด limit — วันที่ order ติด ไม่นับ TP (ไม่รู้ลำดับ intraday)
    คืน (outcome[1/-1/0], exit_price, bars_held)."""
    n = entry.size
    outcome = np.zeros(n, dtype=np.int8)
    exit_price = np.array(fc[hold], dtype=float)
    bars = np.full(n, hold, dtype=np.int16)
    open_ = np.zeros(n, dtype=bool)          # ไม้ที่ยังไม่ปิด (True = ยังเปิดอยู่)
    open_[:] = True
    for k in range(1, hold + 1):
        if not open_.any():
            break
        o, h, l = fo[k], fh[k], fl[k]
        act = open_
        if k == 1:
            gap_sl = np.zeros(n, dtype=bool)
            gap_tp = np.zeros(n, dtype=bool)
        else:
            gap_sl = act & (o <= sl)
            gap_tp = act & ~gap_sl & (o >= tp)
        can_tp = not (skip_tp_day1 and k == 1)
        intr_sl = act & ~gap_sl & ~gap_tp & (l <= sl)
        intr_tp = (act & ~gap_sl & ~gap_tp & (h >= tp)) if can_tp else np.zeros(n, dtype=bool)
        if TIE_BREAK_SL_WINS:
            intr_tp = intr_tp & ~intr_sl
        else:
            intr_sl = intr_sl & ~intr_tp
        hit_sl = gap_sl | intr_sl
        hit_tp = gap_tp | intr_tp
        if hit_sl.any():
            px = np.where(gap_sl, o, sl)
            exit_price[hit_sl] = px[hit_sl]
            outcome[hit_sl] = -1
            bars[hit_sl] = k
        if hit_tp.any():
            px = np.where(gap_tp, o, tp)
            exit_price[hit_tp] = px[hit_tp]
            outcome[hit_tp] = 1
            bars[hit_tp] = k
        open_ = open_ & ~hit_sl & ~hit_tp
    return outcome, exit_price, bars


def _metrics(net: np.ndarray, bars: np.ndarray, outcome: np.ndarray, n_signals: int) -> dict:
    """สถิติของสมการหนึ่ง — 'ชนะ' = กำไรสุทธิ > 0 หลังหักต้นทุน (นิยามที่ซื่อสัตย์)."""
    n = int(net.size)
    wins_mask = net > 0
    wins = int(wins_mask.sum())
    gain = float(net[wins_mask].sum())
    loss = float(-net[~wins_mask].sum())
    avg_hold = float(bars.mean()) if n else float("nan")
    avg_net = float(net.mean()) if n else float("nan")
    return dict(
        n_signals=int(n_signals), n_trades=n, wins=wins,
        win_rate=_r(wins / n * 100) if n else None,
        wilson_lb=_r(wilson_lb(wins, n) * 100),
        avg_net=_r(avg_net), median_net=_r(float(np.median(net)) if n else float("nan")),
        avg_hold=_r(avg_hold),
        net_per_day=_r(avg_net / avg_hold) if (n and avg_hold > 0) else None,
        profit_factor=_r(gain / loss) if loss > 0 else (None if gain <= 0 else 999.0),
        worst=_r(float(net.min()) if n else float("nan")),
        best=_r(float(net.max()) if n else float("nan")),
        n_tp=int((outcome == 1).sum()), n_sl=int((outcome == -1).sum()),
        n_time=int((outcome == 0).sum()),
    )


def evaluate(c: dict, strat: dict, seg: np.ndarray | None = None,
             return_trades: bool = False):
    """ประเมินสมการ 1 ตัวบนช่วงข้อมูลที่กำหนด -> dict สถิติ (None ถ้าไม่มีไม้)."""
    hold = int(strat["hold_days"])
    if hold not in c["fwd_valid"]:
        raise ValueError(f"hold_days={hold} เกิน max_hold ที่ precompute ไว้ ({c['_max_hold']})")
    mask = signal_mask(c, strat, seg) & c["fwd_valid"][hold]
    idx = np.where(mask)[0]
    n_signals = int(idx.size)
    if n_signals == 0:
        return None
    res = _prepare_entries(c, idx, int(strat.get("entry_mode", 0)))
    if res is None:
        return None
    idx, entry, skip_tp_day1 = res
    tp, sl = _tp_sl_levels(c, idx, entry, strat)
    if tp is None:
        return None
    if int(strat.get("exit_mode", 0)) == 1:
        keep = np.isfinite(tp) & np.isfinite(sl) & (tp > entry) & (sl < entry) & (sl > 0)
        if not keep.all():
            idx, entry, tp, sl = idx[keep], entry[keep], tp[keep], sl[keep]
        if entry.size == 0:
            return None
    fo = {k: c[f"O{k}"][idx] for k in range(1, hold + 1)}
    fh = {k: c[f"H{k}"][idx] for k in range(1, hold + 1)}
    fl = {k: c[f"L{k}"][idx] for k in range(1, hold + 1)}
    fc = {k: c[f"C{k}"][idx] for k in range(1, hold + 1)}
    outcome, exit_price, bars = _simulate(entry, tp, sl, fo, fh, fl, fc, hold,
                                          skip_tp_day1=skip_tp_day1)
    net = (exit_price / entry - 1) * 100 - FRICTION_PCT
    ok = np.isfinite(net)
    if not ok.all():
        net, bars, outcome, idx = net[ok], bars[ok], outcome[ok], idx[ok]
    if net.size == 0:
        return None
    m = _metrics(net, bars, outcome, n_signals)
    if return_trades:
        m["trades"] = pd.DataFrame({
            "Ticker": c["_ticker"][idx], "SignalDate": c["_date"][idx],
            "net": net, "bars": bars, "outcome": outcome,
        })
    return m


def _prepare_entries(c: dict, idx: np.ndarray, entry_mode: int):
    """คำนวณราคาเข้าจริงต่อสัญญาณ + คัดไม้ที่เข้าไม่ได้ออก.
    entry_mode 0 = market ที่ราคาเปิดแท่งถัดไป | 1 = limit ต่ำกว่าปิด LIMIT_DISCOUNT_PCT%"""
    if entry_mode == 0:
        entry = c["O1"][idx]
        ok = np.isfinite(entry) & (entry > MIN_VALID_PRICE)
        return (idx[ok], entry[ok], False) if ok.any() else None
    limit = c["Close"][idx] * (1 - LIMIT_DISCOUNT_PCT / 100.0)
    l1 = c["L1"][idx]
    filled = np.isfinite(l1) & np.isfinite(limit) & (limit > MIN_VALID_PRICE) & (l1 <= limit)
    if not filled.any():
        return None
    return idx[filled], limit[filled], True


def _tp_sl_levels(c: dict, idx: np.ndarray, entry: np.ndarray, strat: dict):
    """ระดับ TP/SL ต่อไม้ (โหมด % หรือ ATR-multiple)."""
    tp_val, sl_val = float(strat["tp_val"]), float(strat["sl_val"])
    if int(strat.get("exit_mode", 0)) == 0:
        return entry * (1 + tp_val / 100.0), entry * (1 - sl_val / 100.0)
    a = c[f"ATR{int(strat.get('atr_period', 14))}"][idx]
    a = np.where(np.isfinite(a) & (a > 0), a, np.nan)
    return entry + tp_val * a, entry - sl_val * a


# ==================================================== SEARCH (Layer 1, pure)
def make_strategy(fam: int, entry_params: dict, exit_mode: int, tp_val: float,
                  sl_val: float, hold_days: int, adx_min: int, vol_filter: int,
                  regime_filter: int, entry_mode: int) -> dict:
    """สร้าง dict สมการที่มีคีย์ครบทุกมิติเสมอ (มิติที่ไม่ใช้ = ค่ากลาง)."""
    s = dict(PARAM_DEFAULTS)
    s["entry_family"] = int(fam)
    s.update({k: entry_params[k] for k in FAMILY_PARAMS[fam]})
    s.update(exit_mode=int(exit_mode), tp_val=float(tp_val), sl_val=float(sl_val),
             hold_days=int(hold_days), adx_min=int(adx_min), vol_filter=int(vol_filter),
             regime_filter=int(regime_filter), entry_mode=int(entry_mode))
    return s


def strategy_key(s: dict) -> tuple:
    """คีย์เอกลักษณ์ของสมการ = family + เฉพาะมิติที่ family นั้นใช้ + exit/filter.
    (นี่คือเหตุผลที่ค้นแบบ exhaustive ได้: ไม่เสียเวลากับ combo ที่ 'ต่างกันแต่เหมือนกัน')"""
    fam = int(s["entry_family"])
    used = tuple((k, s[k]) for k in FAMILY_PARAMS[fam])
    return (fam, used, int(s["exit_mode"]), float(s["tp_val"]), float(s["sl_val"]),
            int(s["hold_days"]), int(s["adx_min"]), int(s["vol_filter"]),
            int(s["regime_filter"]), int(s["entry_mode"]))


def strategy_label(s: dict) -> str:
    """ชื่ออ่านง่ายของสมการ (ใช้ในรายงาน/dashboard)."""
    fam = int(s["entry_family"])
    parts = [f"{k}={s[k]}" for k in FAMILY_PARAMS[fam]]
    ex = "%" if int(s["exit_mode"]) == 0 else "ATR"
    parts.append(f"TP/SL={s['tp_val']}/{s['sl_val']}{ex}")
    parts.append(f"hold={s['hold_days']}d")
    if int(s["adx_min"]):
        parts.append(f"ADX>={s['adx_min']}")
    if int(s["vol_filter"]):
        parts.append("volOK")
    if int(s["regime_filter"]):
        parts.append("regime")
    parts.append("market" if int(s["entry_mode"]) == 0 else f"limit-{LIMIT_DISCOUNT_PCT}%")
    return f"{FAMILY_NAME[fam]} [" + ", ".join(parts) + "]"


def _score(m: dict) -> float:
    """คะแนนจัดอันดับ = ความมั่นใจของ WR (Wilson LB) × กำไรต่อวัน — ต้องดีทั้งคู่."""
    if not m:
        return -1e9
    w = _safe_float(m.get("wilson_lb"), 0.0)
    npd = _safe_float(m.get("net_per_day"), 0.0)
    if not np.isfinite(w) or not np.isfinite(npd):
        return -1e9
    return (w / 100.0) * max(npd, 0.0)


def count_search_space() -> int:
    """จำนวนสมการที่ 'ต่างกันจริง' ทั้งหมดที่ระบบจะค้น (ไม่ใช่การสุ่ม)."""
    n_filters = len(SPACE["adx_min"]) * len(SPACE["vol_filter"]) * len(SPACE["regime_filter"])
    n_exec = len(SPACE["entry_mode"]) * len(SPACE["hold_days"]) * len(EXIT_COMBOS)
    total = 0
    for fam, keys in FAMILY_PARAMS.items():
        n_entry = 1
        for k in keys:
            n_entry *= len(SPACE[k])
        total += n_entry * n_filters * n_exec
    return total


def run_search(c: dict, seg: np.ndarray, min_trades: int = MIN_TRADES_IS,
               keep_top: int = TOP_N_VALIDATE, families=None,
               progress: bool = True) -> list:
    """ค้นหาแบบครบทุกความเป็นไปได้ (exhaustive) บนช่วง in-sample.

    ประหยัดเวลาด้วยการใช้ผลลัพธ์ร่วมกัน 3 ชั้น:
      1) mask ของ family+พารามิเตอร์เข้า คำนวณครั้งเดียว ใช้กับทุก exit/filter
      2) mask ของตัวกรอง (ADX/vol/regime) คำนวณครั้งเดียว ใช้กับทุก family
      3) แท่งอนาคตถูก slice ครั้งเดียวต่อ (entry_mode, hold) ใช้กับทุกคู่ TP/SL
    เก็บผลด้วย bounded heap -> RAM คงที่ ไม่ระเบิดแม้สมการผ่านเกณฑ์เป็นล้าน."""
    import heapq

    families = sorted(FAMILY_PARAMS) if families is None else list(families)
    filt_combos = [(a, vf, rf) for a in SPACE["adx_min"]
                   for vf in SPACE["vol_filter"] for rf in SPACE["regime_filter"]]
    filt_masks = [((a, vf, rf), filter_mask(c, a, vf, rf)) for a, vf, rf in filt_combos]
    cap = max(1, int(keep_top) * 6)          # เผื่อไว้ให้ _dedup_candidates คัดทีหลัง
    heap: list = []
    counter = 0
    n_eval = n_pass = 0
    total = count_search_space()
    t0 = time.time()
    last_print = t0

    for fam in families:
        ekeys = FAMILY_PARAMS[fam]
        for evals in itertools.product(*[SPACE[k] for k in ekeys]):
            ep = dict(zip(ekeys, evals))
            base = entry_mask(c, fam, {**PARAM_DEFAULTS, **ep}) & seg
            if int(base.sum()) < min_trades:
                n_eval += len(filt_masks) * len(SPACE["entry_mode"]) * \
                    len(SPACE["hold_days"]) * len(EXIT_COMBOS)
                continue
            for (a_min, volf, regf), fmask in filt_masks:
                m = base & fmask
                if int(m.sum()) < min_trades:
                    n_eval += len(SPACE["entry_mode"]) * len(SPACE["hold_days"]) * len(EXIT_COMBOS)
                    continue
                for emode in SPACE["entry_mode"]:
                    for hold in SPACE["hold_days"]:
                        idx0 = np.where(m & c["fwd_valid"][hold])[0]
                        if idx0.size < min_trades:
                            n_eval += len(EXIT_COMBOS)
                            continue
                        prep = _prepare_entries(c, idx0, emode)
                        if prep is None:
                            n_eval += len(EXIT_COMBOS)
                            continue
                        idx, entry, skip1 = prep
                        if entry.size < min_trades:
                            n_eval += len(EXIT_COMBOS)
                            continue
                        n_signals = int(idx0.size)
                        s_o = {k: c[f"O{k}"][idx] for k in range(1, hold + 1)}
                        s_h = {k: c[f"H{k}"][idx] for k in range(1, hold + 1)}
                        s_l = {k: c[f"L{k}"][idx] for k in range(1, hold + 1)}
                        s_c = {k: c[f"C{k}"][idx] for k in range(1, hold + 1)}
                        atr_v = c["ATR14"][idx]
                        atr_ok = np.isfinite(atr_v) & (atr_v > 0)
                        atr_all = bool(atr_ok.all())
                        atr_sets = None
                        for xm, tpv, slv in EXIT_COMBOS:
                            n_eval += 1
                            if xm == 0:
                                e_, o_, h_, l_, c_ = entry, s_o, s_h, s_l, s_c
                                tp = entry * (1 + tpv / 100.0)
                                sl = entry * (1 - slv / 100.0)
                            else:
                                if atr_all:
                                    e_, o_, h_, l_, c_, a_ = entry, s_o, s_h, s_l, s_c, atr_v
                                else:
                                    if atr_sets is None:
                                        if int(atr_ok.sum()) < min_trades:
                                            atr_sets = False
                                        else:
                                            sub = np.where(atr_ok)[0]
                                            atr_sets = (
                                                entry[sub],
                                                {k: v[sub] for k, v in s_o.items()},
                                                {k: v[sub] for k, v in s_h.items()},
                                                {k: v[sub] for k, v in s_l.items()},
                                                {k: v[sub] for k, v in s_c.items()},
                                                atr_v[sub])
                                    if atr_sets is False:
                                        continue
                                    e_, o_, h_, l_, c_, a_ = atr_sets
                                tp = e_ + tpv * a_
                                sl = e_ - slv * a_
                                if np.any(sl <= 0):
                                    keep = sl > 0
                                    if int(keep.sum()) < min_trades:
                                        continue
                                    e_ = e_[keep]
                                    o_ = {k: v[keep] for k, v in o_.items()}
                                    h_ = {k: v[keep] for k, v in h_.items()}
                                    l_ = {k: v[keep] for k, v in l_.items()}
                                    c_ = {k: v[keep] for k, v in c_.items()}
                                    tp, sl = tp[keep], sl[keep]
                            if e_.size < min_trades:
                                continue
                            outcome, exit_price, bars = _simulate(
                                e_, tp, sl, o_, h_, l_, c_, hold, skip_tp_day1=skip1)
                            net = (exit_price / e_ - 1) * 100 - FRICTION_PCT
                            good = np.isfinite(net)
                            if not good.all():
                                net, bars, outcome = net[good], bars[good], outcome[good]
                            if net.size < min_trades:
                                continue
                            met = _metrics(net, bars, outcome, n_signals)
                            if met["avg_net"] is None or met["avg_net"] <= 0:
                                continue
                            if met["win_rate"] is None or met["win_rate"] < FLOOR_WIN_RATE:
                                continue
                            if met["net_per_day"] is None or met["net_per_day"] < FLOOR_NET_PER_DAY:
                                continue
                            n_pass += 1
                            strat = make_strategy(fam, ep, xm, tpv, slv, hold,
                                                  a_min, volf, regf, emode)
                            row = {**strat, **met}
                            sc_val = _score(met)
                            counter += 1
                            if len(heap) < cap:
                                heapq.heappush(heap, (sc_val, counter, row))
                            elif sc_val > heap[0][0]:
                                heapq.heapreplace(heap, (sc_val, counter, row))
            if progress and (time.time() - last_print) > 20:
                el = time.time() - t0
                rate = n_eval / el if el > 0 else 0
                eta = (total - n_eval) / rate if rate > 0 else 0
                print(f"  [{datetime.now():%H:%M:%S}] {n_eval:,}/{total:,} สมการ "
                      f"({el:.0f}s, {rate:,.0f}/s, เหลือ ~{eta/60:.1f} นาที) "
                      f"| ผ่านเกณฑ์พื้น: {n_pass:,}", flush=True)
                last_print = time.time()
    el = time.time() - t0
    if progress:
        print(f"  ค้นครบ {n_eval:,} สมการ ใน {el:.0f}s | ผ่านเกณฑ์พื้น {n_pass:,} "
              f"| เก็บตัวท็อป {len(heap):,} ตัวไปยืนยัน", flush=True)
    ranked = [row for _, _, row in sorted(heap, key=lambda x: -x[0])]
    return _dedup_candidates(ranked, keep_top)


def _dedup_candidates(rows: list, keep_top: int, max_per_group: int = 4) -> list:
    """คัดผู้เข้ารอบให้ 'หลากหลายจริง' ก่อนไปยืนยัน.

    ปัญหาที่พบจริง: สมการที่ต่างกันแค่ SL ที่ไม่เคยถูกชนเลย จะให้ไม้ชุดเดียวกันเป๊ะ
    -> ท็อป 400 กลายเป็นสมการเดียวกัน 400 หน้า -> การยืนยันไร้ความหมาย.
    วิธีแก้: ตัดตัวที่ 'ผลลัพธ์เหมือนกันทุกประการ' ทิ้ง และจำกัดจำนวนต่อกลุ่มพารามิเตอร์เข้า."""
    seen_sig, per_group, out = set(), {}, []
    for row in rows:
        fam = int(row["entry_family"])
        ep = tuple(row[k] for k in FAMILY_PARAMS[fam])
        sig = (fam, ep, row["n_trades"], row["wins"], row["avg_net"], row["avg_hold"])
        if sig in seen_sig:
            continue
        grp = (fam, ep)
        if per_group.get(grp, 0) >= max_per_group:
            continue
        seen_sig.add(sig)
        per_group[grp] = per_group.get(grp, 0) + 1
        out.append(row)
        if len(out) >= keep_top:
            break
    return out


# ============================================ VALIDATION (out-of-sample)
def make_segments(data: pd.DataFrame, is_frac: float = IS_FRACTION,
                  oos1_frac: float = OOS1_FRACTION, embargo: int | None = EMBARGO_BARS):
    """แบ่งข้อมูลเป็น 3 ช่วงตามเวลา + embargo (กันไม้ของช่วงก่อนไปกินแท่งของช่วงถัดไป).

    คืน dict ของ boolean mask (ยาวเท่าจำนวนแถวของ data) + วันคั่น."""
    dates = np.sort(pd.to_datetime(pd.Series(data["Date"].unique())).values)
    n = len(dates)
    if n < 60:
        raise ValueError(f"ข้อมูลสั้นเกินไป ({n} วัน) — ต้องมีอย่างน้อย 60 วันทำการ")
    emb = _max_hold() if embargo is None else int(embargo)
    i1 = int(n * is_frac)
    i2 = int(n * (is_frac + oos1_frac))
    i1 = max(1, min(i1, n - 3))
    i2 = max(i1 + 1, min(i2, n - 2))
    d = pd.to_datetime(data["Date"]).values
    cut1, cut2 = dates[i1], dates[i2]
    emb1 = dates[max(0, i1 - emb)]
    emb2 = dates[max(0, i2 - emb)]
    seg_is = d < emb1
    seg_o1 = (d >= cut1) & (d < emb2)
    seg_o2 = d >= cut2
    return dict(is_=seg_is, oos1=seg_o1, oos2=seg_o2, oos=(seg_o1 | seg_o2),
                cut1=pd.Timestamp(cut1), cut2=pd.Timestamp(cut2),
                n_days=n, embargo=emb)


def grade_strategy(o1: dict | None, o2: dict | None, comb: dict | None) -> str:
    """ให้เกรดจากผล out-of-sample 2 ช่วง — เกณฑ์เดียวกับที่ประกาศไว้ ไม่ผ่อนให้ใคร.
      A = ถึงเป้าที่ผู้ใช้สั่ง (WR>=80% และกำไร>=2%/วัน) ทั้ง 2 ช่วง และรวมกัน
      B = ยืนยันได้ว่ามี edge จริง แต่ 'ไม่ถึงเป้า'
      -  = ตก (ไม่ผ่าน)"""
    if not (o1 and o2 and comb):
        return "-"
    if min(o1["n_trades"], o2["n_trades"]) < MIN_TRADES_OOS:
        return "-"
    def _f(m, k):
        return _safe_float(m.get(k), float("-inf"))
    hit_a = all([
        _f(o1, "win_rate") >= TARGET_WIN_RATE, _f(o2, "win_rate") >= TARGET_WIN_RATE,
        _f(comb, "win_rate") >= TARGET_WIN_RATE,
        _f(o1, "net_per_day") >= TARGET_NET_PER_DAY,
        _f(o2, "net_per_day") >= TARGET_NET_PER_DAY,
        _f(comb, "net_per_day") >= TARGET_NET_PER_DAY,
        _f(comb, "avg_net") >= TARGET_NET_PER_TRADE,
    ])
    if hit_a:
        return "A"
    hit_b = all([
        _f(o1, "win_rate") >= FLOOR_WIN_RATE, _f(o2, "win_rate") >= FLOOR_WIN_RATE,
        _f(o1, "net_per_day") >= FLOOR_NET_PER_DAY, _f(o2, "net_per_day") >= FLOOR_NET_PER_DAY,
        _f(o1, "avg_net") > 0, _f(o2, "avg_net") > 0,
        _f(comb, "wilson_lb") >= FLOOR_WILSON_LB,
    ])
    return "B" if hit_b else "-"


def validate(c: dict, candidates: list, segs: dict, progress: bool = True) -> pd.DataFrame:
    """ยืนยันสมการบนข้อมูลที่ไม่เคยเห็น 2 ช่วง (ต้องผ่านทั้งคู่ ไม่ใช่เลือกช่วงที่ชอบ)."""
    rows = []
    for i, cand in enumerate(candidates, 1):
        strat = {k: cand[k] for k in PARAM_KEYS}
        o1 = evaluate(c, strat, segs["oos1"])
        o2 = evaluate(c, strat, segs["oos2"])
        comb = evaluate(c, strat, segs["oos"])
        g = grade_strategy(o1, o2, comb)
        row = dict(strat)
        row["strategy"] = FAMILY_NAME[int(strat["entry_family"])]
        row["label"] = strategy_label(strat)
        row["grade"] = g
        for tag, m in (("is", cand), ("o1", o1), ("o2", o2), ("oos", comb)):
            row[f"{tag}_n"] = (m or {}).get("n_trades", 0)
            row[f"{tag}_wr"] = (m or {}).get("win_rate")
            row[f"{tag}_wlb"] = (m or {}).get("wilson_lb")
            row[f"{tag}_net"] = (m or {}).get("avg_net")
            row[f"{tag}_npd"] = (m or {}).get("net_per_day")
            row[f"{tag}_pf"] = (m or {}).get("profit_factor")
            row[f"{tag}_hold"] = (m or {}).get("avg_hold")
        row["oos_score"] = _score(comb)
        rows.append(row)
        if progress and i % 100 == 0:
            print(f"    ยืนยันแล้ว {i}/{len(candidates)}", flush=True)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    grade_rank = {"A": 0, "B": 1, "-": 2}
    df["_g"] = df["grade"].map(grade_rank).fillna(3)
    df = df.sort_values(["_g", "oos_score"], ascending=[True, False]).drop(columns="_g")
    return df.reset_index(drop=True)


# ====================================== PORTFOLIO BACKTEST (กำไร %/วัน จริง)
ONE_WAY_COST = FRICTION_PCT / 200.0     # ต้นทุนต่อขา (สัดส่วน ไม่ใช่ %)


def _row_lookup(data: pd.DataFrame):
    """ตารางค้นแถว (ticker, วัน) -> index แถว + ดัชนีแท่งก่อนหน้าในหุ้นเดียวกัน."""
    tick_codes, tick_names = pd.factorize(data["Ticker"])
    dts = np.asarray(data["Date"], dtype="datetime64[ns]")
    udates = np.unique(dts)
    date_ids = np.searchsorted(udates, dts)
    lut = np.full((len(tick_names), len(udates)), -1, dtype=np.int64)
    lut[tick_codes, date_ids] = np.arange(len(data), dtype=np.int64)
    prev = np.full(len(data), -1, dtype=np.int64)
    if len(data) > 1:
        same = tick_codes[1:] == tick_codes[:-1]
        prev[1:] = np.where(same, np.arange(len(data) - 1), -1)
    return dict(tick_codes=tick_codes, tick_names=list(tick_names), udates=udates,
                date_ids=date_ids, lut=lut, prev=prev)


def portfolio_backtest(data: pd.DataFrame, c: dict, strat: dict,
                       seg: np.ndarray | None = None, capital: float = CAPITAL_THB,
                       max_positions: int = MAX_POSITIONS) -> dict:
    """จำลองพอร์ตจริงแบบวันต่อวัน — ตอบคำถาม 'กำไรกี่ % ต่อวัน' ด้วยเงินจำกัดจริง.

    ต่างจากสถิติต่อไม้ตรงที่: ถือพร้อมกันได้ไม่เกิน max_positions, ต้องมีเงินสดพอ,
    ซื้อเป็น board lot (100 หุ้น), หักค่าคอมทั้งขาซื้อและขาย, และคิด mark-to-market
    ทุกวันทำการ -> ได้ equity curve จริง (ใช้คำนวณ %/วัน, max drawdown)."""
    if capital <= 0 or max_positions < 1:
        raise ValueError("capital ต้อง > 0 และ max_positions ต้อง >= 1")
    hold = int(strat["hold_days"])
    emode = int(strat.get("entry_mode", 0))
    lk = _row_lookup(data)
    lut, prev, udates = lk["lut"], lk["prev"], lk["udates"]
    tick_codes, tick_names = lk["tick_codes"], lk["tick_names"]
    o, h, l, cl = c["Open"], c["High"], c["Low"], c["Close"]
    sig = signal_mask(c, strat, seg)
    cand = np.zeros(len(data), dtype=bool)
    has_prev = prev >= 0
    cand[has_prev] = sig[prev[has_prev]]
    cand_rows = np.where(cand)[0]
    cand_by_date: dict[int, list] = {}
    for r in cand_rows:
        cand_by_date.setdefault(int(lk["date_ids"][r]), []).append(int(r))

    # เดินเฉพาะช่วงวันของ segment ที่ทดสอบ (+ ท้ายอีก hold วันไว้ปิดไม้ค้าง)
    # [แก้บั๊ก กลาง] เดิมเดินทุกวันตั้งแต่ต้นข้อมูล -> วันที่ไม่ได้เทรดถูกนับเป็น
    # 'วันกำไร 0%' -> ค่าเฉลี่ย %/วัน ต่ำกว่าความจริงอย่างมีนัยสำคัญ
    d_start, d_end = 0, len(udates) - 1
    if seg is not None and bool(np.any(seg)):
        sd = np.asarray(data["Date"], dtype="datetime64[ns]")[seg]
        d_start = int(np.searchsorted(udates, sd.min()))
        d_end = int(min(len(udates) - 1, np.searchsorted(udates, sd.max()) + hold + 1))

    cash = float(capital)
    positions: dict[int, dict] = {}
    trades, equity = [], []
    n_signals = int(sig.sum())
    skipped_cash = skipped_slot = 0

    for did in range(d_start, d_end + 1):
        # ---------- 1) จัดการไม้ที่ถืออยู่ (ออกก่อนเข้าเสมอ) ----------
        for tid in list(positions):
            pos = positions[tid]
            r = int(lut[tid, did])
            if r < 0 or r <= pos["entry_row"]:
                continue                      # วันนี้หุ้นตัวนี้ไม่มีแท่ง (พักการซื้อขาย)
            pos["bars"] += 1
            pos["last_close"] = cl[r]
            exit_px = None
            if o[r] <= pos["sl"]:
                exit_px, kind = o[r], "SL_GAP"          # เปิดทะลุ SL -> ขาดทุนจริงมากกว่า SL
            elif o[r] >= pos["tp"]:
                exit_px, kind = o[r], "TP_GAP"
            elif TIE_BREAK_SL_WINS and l[r] <= pos["sl"]:
                exit_px, kind = pos["sl"], "SL"
            elif h[r] >= pos["tp"]:
                exit_px, kind = pos["tp"], "TP"
            elif l[r] <= pos["sl"]:
                exit_px, kind = pos["sl"], "SL"
            elif pos["bars"] >= hold:
                exit_px, kind = cl[r], "TIME"
            if exit_px is not None:
                cash += pos["shares"] * exit_px * (1 - ONE_WAY_COST)
                trades.append(_close_trade(pos, tick_names[tid], exit_px, udates[did], kind))
                del positions[tid]

        # ---------- 2) ตีราคาพอร์ต (mark-to-market) ----------
        mtm = 0.0
        for tid, pos in positions.items():
            r = int(lut[tid, did])
            if r >= 0:
                pos["last_close"] = cl[r]
            mtm += pos["shares"] * pos["last_close"]
        eq_open = cash + mtm

        # ---------- 3) เปิดไม้ใหม่ (สัญญาณของ 'เมื่อวาน' -> เข้าที่ราคาเปิดวันนี้) ----------
        for r in cand_by_date.get(did, []):
            if len(positions) >= max_positions:
                skipped_slot += 1
                continue
            tid = int(tick_codes[r])
            if tid in positions:
                continue
            sig_row = int(prev[r])
            if emode == 0:
                price = o[r]
            else:
                limit = cl[sig_row] * (1 - LIMIT_DISCOUNT_PCT / 100.0)
                if not (np.isfinite(limit) and l[r] <= limit):
                    continue
                price = min(limit, o[r])      # เปิดต่ำกว่า limit -> ได้ราคาเปิด (ดีกว่า)
            if not (np.isfinite(price) and price > MIN_VALID_PRICE):
                continue
            tp, sl = _levels_for_price(c, sig_row, price, strat)
            if tp is None or not (np.isfinite(tp) and np.isfinite(sl)) or sl <= 0:
                continue
            budget = min(cash, eq_open / max_positions)
            unit = price * (1 + ONE_WAY_COST) * BOARD_LOT
            lots = int(budget // unit) if unit > 0 else 0
            if lots < 1:
                skipped_cash += 1
                continue
            shares = lots * BOARD_LOT
            cash -= shares * price * (1 + ONE_WAY_COST)
            pos = dict(entry_row=r, entry_price=float(price), tp=float(tp), sl=float(sl),
                       shares=shares, bars=1, last_close=cl[r],
                       entry_date=udates[did], sig_row=sig_row)
            # แท่งแรก: market เช็คได้ทั้ง TP/SL | limit ไม่นับ TP (ไม่รู้ลำดับ intraday)
            exit_px = None
            if TIE_BREAK_SL_WINS and l[r] <= sl:
                exit_px, kind = sl, "SL"
            elif emode == 0 and h[r] >= tp:
                exit_px, kind = tp, "TP"
            elif l[r] <= sl:
                exit_px, kind = sl, "SL"
            elif hold <= 1:
                exit_px, kind = cl[r], "TIME"
            if exit_px is not None:
                cash += shares * exit_px * (1 - ONE_WAY_COST)
                trades.append(_close_trade(pos, tick_names[tid], exit_px, udates[did], kind))
            else:
                positions[tid] = pos

        mtm = sum(p["shares"] * p["last_close"] for p in positions.values())
        equity.append((udates[did], cash + mtm, len(positions)))

    # ---------- ปิดไม้ค้างท้ายช่วง ----------
    # equity ตัวสุดท้ายเป็น mark-to-market อยู่แล้ว จึงไม่แก้ cash ซ้ำ
    # แต่ต้องบันทึกเป็นไม้ (OPEN_END) เพื่อให้สถิติต่อไม้ครบถ้วน ไม่ซ่อนไม้ที่ยังไม่ปิด
    for tid, pos in list(positions.items()):
        trades.append(_close_trade(pos, tick_names[tid], pos["last_close"],
                                   udates[d_end], "OPEN_END"))
    tdf = pd.DataFrame(trades)
    edf = pd.DataFrame(equity, columns=["Date", "equity", "n_open"])
    return _portfolio_stats(tdf, edf, capital, n_signals, skipped_cash, skipped_slot,
                            max_positions)


def _levels_for_price(c: dict, sig_row: int, price: float, strat: dict):
    """TP/SL จากราคาเข้าจริง (ใช้ ATR ของแท่งสัญญาณเมื่ออยู่โหมด ATR)."""
    tp_val, sl_val = float(strat["tp_val"]), float(strat["sl_val"])
    if int(strat.get("exit_mode", 0)) == 0:
        return price * (1 + tp_val / 100.0), price * (1 - sl_val / 100.0)
    a = c[f"ATR{int(strat.get('atr_period', 14))}"][sig_row]
    if not (np.isfinite(a) and a > 0):
        return None, None
    return price + tp_val * a, price - sl_val * a


def _close_trade(pos: dict, ticker: str, exit_px: float, exit_date, kind: str) -> dict:
    gross = (exit_px / pos["entry_price"] - 1) * 100
    return dict(
        Ticker=ticker, EntryDate=pos["entry_date"], ExitDate=exit_date,
        EntryPrice=round(float(pos["entry_price"]), 4), ExitPrice=round(float(exit_px), 4),
        Shares=int(pos["shares"]), Bars=int(pos["bars"]), Kind=kind,
        NetPct=round(float(gross - FRICTION_PCT), 4),
        PnlTHB=round(float(pos["shares"] * (exit_px * (1 - ONE_WAY_COST)
                                            - pos["entry_price"] * (1 + ONE_WAY_COST))), 2),
    )


def _portfolio_stats(tdf: pd.DataFrame, edf: pd.DataFrame, capital: float,
                     n_signals: int, skipped_cash: int, skipped_slot: int,
                     max_positions: int = MAX_POSITIONS) -> dict:
    """สรุปผลพอร์ต — %/วัน คิดจาก equity curve จริง (ไม่ใช่ค่าเฉลี่ยต่อไม้)."""
    stats = dict(n_signals=int(n_signals), n_trades=int(len(tdf)),
                 skipped_no_cash=int(skipped_cash), skipped_no_slot=int(skipped_slot),
                 capital=float(capital), max_positions=int(max_positions),
                 budget_per_trade=_r(capital / max(1, int(max_positions)), 0))
    if len(edf) == 0:
        stats.update(final_equity=float(capital), total_return_pct=0.0, n_days=0,
                     avg_daily_pct=None, median_daily_pct=None, max_drawdown_pct=None,
                     cagr_pct=None, win_rate=None, avg_net_pct=None, exposure=None,
                     best_day_pct=None, worst_day_pct=None, days_target_hit=None)
        return stats
    eq = edf["equity"].astype(float).to_numpy()
    rets = np.diff(eq) / np.where(eq[:-1] == 0, np.nan, eq[:-1]) * 100
    rets = rets[np.isfinite(rets)]
    peak = np.maximum.accumulate(eq)
    dd = np.where(peak > 0, (eq - peak) / peak * 100, 0.0)
    n_days = int(len(edf))
    total_ret = (eq[-1] / capital - 1) * 100 if capital > 0 else float("nan")
    years = n_days / 252.0
    cagr = ((eq[-1] / capital) ** (1 / years) - 1) * 100 if (years > 0 and eq[-1] > 0
                                                             and capital > 0) else None
    wins = int((tdf["NetPct"] > 0).sum()) if len(tdf) else 0
    stats.update(
        final_equity=_r(eq[-1]), total_return_pct=_r(total_ret), n_days=n_days,
        avg_daily_pct=_r(float(rets.mean()), 4) if rets.size else None,
        median_daily_pct=_r(float(np.median(rets)), 4) if rets.size else None,
        best_day_pct=_r(float(rets.max()), 3) if rets.size else None,
        worst_day_pct=_r(float(rets.min()), 3) if rets.size else None,
        days_target_hit=int((rets >= TARGET_NET_PER_DAY).sum()) if rets.size else 0,
        max_drawdown_pct=_r(float(dd.min())), cagr_pct=_r(cagr) if cagr is not None else None,
        win_rate=_r(wins / len(tdf) * 100) if len(tdf) else None,
        wilson_lb=_r(wilson_lb(wins, len(tdf)) * 100) if len(tdf) else None,
        avg_net_pct=_r(float(tdf["NetPct"].mean())) if len(tdf) else None,
        total_pnl_thb=_r(float(tdf["PnlTHB"].sum())) if len(tdf) else 0.0,
        exposure=_r(float(edf["n_open"].mean() / max(1, int(max_positions)) * 100)),
    )
    stats["equity"] = edf
    stats["trades"] = tdf
    return stats


# ================================ DAILY VERDICT AGENT (Layer 1 — Trading Domain)
@dataclass(frozen=True)
class TickerOrder:
    """ออร์เดอร์ราย ticker สำหรับ 'วันทำการถัดไป' — frozen = ผลลัพธ์คงที่ ตรวจสอบซ้ำได้."""
    ticker: str
    action: str                 # "เข้า (TRADE)" | "เฝ้าดู (WATCH)"
    agree_count: int
    of_k: int
    grade: str
    strategy: str
    order_type: str
    buy_ref: float
    sell_tp: float
    stop_sl: float
    tp_pct: float
    sl_pct: float
    lots: int
    shares: int
    cost_thb: float
    budget_ok: bool
    hold_days: int
    entry_mode: int
    exit_mode: int
    tp_val: float
    sl_val: float
    expected_wr: float
    expected_npd: float
    expected_wlb: float
    reasons: str


@dataclass(frozen=True)
class VerdictReport:
    overall: str
    grade: str
    k_used: int
    asof: str
    orders: tuple


class DailyVerdictAgent:
    """เอเจนท์ฟันธง 'พรุ่งนี้เข้าตัวไหน' (pure, deterministic).

    Contract:
      input : data ที่ precompute แล้ว + cache + ตารางสมการที่ยืนยันผ่าน OOS
      output: VerdictReport (ไม่มี side effect; input เดิม -> output เดิมเสมอ)
    หลักการ: ใช้ 'สมการชุดเดียวกับที่ backtest' ยิงบนแท่งล่าสุดที่ปิดแล้ว
      เข้า (TRADE)   : จำนวนสมการที่เห็นตรงกัน >= min_agree และงบพอ >= 1 board lot
      เฝ้าดู (WATCH) : มีสัญญาณแต่ฉันทามติ/งบ/จำนวนไม้สูงสุดไม่ผ่าน
      ไม่มีสมการยืนยัน: ตอบ 'ไม่เข้า' ตรง ๆ (คำตอบที่ซื่อสัตย์ ไม่ใช่บั๊ก)"""

    def __init__(self, top_k: int = VERDICT_TOP_K, min_agree: int = VERDICT_MIN_AGREE,
                 max_orders: int = MAX_POSITIONS, budget_thb: float = BUDGET_PER_TRADE_THB):
        if top_k < 1 or min_agree < 1 or max_orders < 1:
            raise ValueError("top_k, min_agree, max_orders ต้อง >= 1")
        self.top_k = int(top_k)
        self.min_agree = int(min_agree)
        self.max_orders = int(max_orders)
        self.budget = float(budget_thb)

    def decide(self, data: pd.DataFrame, c: dict, confirmed: pd.DataFrame) -> VerdictReport:
        last_date = pd.to_datetime(data["Date"]).max()
        asof = f"{last_date:%Y-%m-%d}"
        if confirmed is None or len(confirmed) == 0 or "grade" not in confirmed.columns:
            return VerdictReport("ไม่เข้า (NO_TRADE) — ไม่มีสมการผ่านการยืนยัน out-of-sample",
                                 "-", 0, asof, tuple())
        usable = confirmed[confirmed["grade"].isin(["A", "B"])]
        if len(usable) == 0:
            return VerdictReport("ไม่เข้า (NO_TRADE) — ไม่มีสมการผ่านการยืนยัน out-of-sample",
                                 "-", 0, asof, tuple())
        top = usable.head(self.top_k)
        k = len(top)
        eff_min = min(self.min_agree, k)
        best_grade = "A" if (top["grade"] == "A").any() else "B"
        last_mask = np.asarray(pd.to_datetime(data["Date"]) == last_date)

        hits: dict[str, list] = {}
        for rank, (_, row) in enumerate(top.iterrows()):
            strat = {key: row[key] for key in PARAM_KEYS}
            strat = _coerce_strategy(strat)
            m = signal_mask(c, strat) & last_mask
            for r in np.where(m)[0]:
                hits.setdefault(str(c["_ticker"][r]), []).append((rank, int(r), strat, row))

        cands = []
        for tk in sorted(hits):
            lst = sorted(hits[tk], key=lambda x: x[0])
            rank, r, strat, row = lst[0]
            ref_close = float(c["Close"][r])
            emode = int(strat["entry_mode"])
            buy_ref = ref_close if emode == 0 else ref_close * (1 - LIMIT_DISCOUNT_PCT / 100.0)
            tp, sl = _levels_for_price(c, r, buy_ref, strat)
            if tp is None or not np.isfinite(tp) or not np.isfinite(sl) or sl <= 0:
                continue
            unit = buy_ref * BOARD_LOT
            lots = int(self.budget // unit) if unit > 0 else 0
            reasons = []
            if lots < 1:
                reasons.append(f"งบไม่พอ 1 lot (ต้องใช้ {unit:,.0f} บาท/lot)")
            agree = len(lst)
            if agree < eff_min:
                reasons.append(f"ฉันทามติ {agree}/{k} ต่ำกว่าเกณฑ์ {eff_min}")
            cands.append(dict(
                ticker=tk, agree=agree, rank=rank, strat=strat, row=row, lots=lots,
                buy_ref=buy_ref, tp=tp, sl=sl, unit=unit, reasons=reasons,
                npd=_safe_float(row.get("oos_npd"), 0.0)))

        cands.sort(key=lambda d: (-d["agree"], d["rank"], -d["npd"], d["ticker"]))
        orders, n_trade = [], 0
        for d in cands:
            ok = (d["agree"] >= eff_min) and (d["lots"] >= 1)
            if ok and n_trade >= self.max_orders:
                ok = False
                d["reasons"].append(f"เกินจำนวนไม้สูงสุดที่ถือพร้อมกัน ({self.max_orders})")
            action = "เข้า (TRADE)" if ok else "เฝ้าดู (WATCH)"
            n_trade += 1 if ok else 0
            s, row = d["strat"], d["row"]
            orders.append(TickerOrder(
                ticker=d["ticker"], action=action, agree_count=d["agree"], of_k=k,
                grade=str(row.get("grade", "-")), strategy=str(row.get("label", "")),
                order_type=("Market@Open (ตั้งซื้อราคาเปิด)" if int(s["entry_mode"]) == 0
                            else f"Limit -{LIMIT_DISCOUNT_PCT}% (ตั้งซื้อรอ)"),
                buy_ref=round(d["buy_ref"], 2), sell_tp=round(float(d["tp"]), 2),
                stop_sl=round(float(d["sl"]), 2),
                tp_pct=round((d["tp"] / d["buy_ref"] - 1) * 100, 3),
                sl_pct=round((1 - d["sl"] / d["buy_ref"]) * 100, 3),
                lots=int(d["lots"]), shares=int(d["lots"] * BOARD_LOT),
                cost_thb=round(d["lots"] * d["unit"], 2), budget_ok=bool(d["lots"] >= 1),
                hold_days=int(s["hold_days"]), entry_mode=int(s["entry_mode"]),
                exit_mode=int(s["exit_mode"]), tp_val=float(s["tp_val"]),
                sl_val=float(s["sl_val"]),
                expected_wr=_safe_float(row.get("oos_wr"), float("nan")),
                expected_npd=_safe_float(row.get("oos_npd"), float("nan")),
                expected_wlb=_safe_float(row.get("oos_wlb"), float("nan")),
                reasons="; ".join(d["reasons"]) if d["reasons"] else "-"))

        if n_trade > 0:
            overall = (f"เข้า {n_trade} ตัว (เกรด {best_grade} · ฉันทามติ >= {eff_min}/{k} สมการ)")
        elif orders:
            overall = "เฝ้าดูอย่างเดียว — มีสัญญาณแต่ไม่ผ่านเกณฑ์ฉันทามติ/งบ/จำนวนไม้"
        else:
            overall = f"ไม่เข้า (NO_TRADE) — วันที่ {asof} ไม่มีหุ้นเข้าเงื่อนไขสมการที่ยืนยันแล้ว"
        return VerdictReport(overall, best_grade, k, asof, tuple(orders))


def _coerce_strategy(strat: dict) -> dict:
    """บังคับชนิดข้อมูลของพารามิเตอร์ให้ถูก (int ต้องเป็น int, ที่เหลือ float).
    แก้บั๊ก [สูง] ของระบบเดิม: cast เป็น int ทั้งหมดทำให้ค่า 2.5 ถูกปัดเป็น 2 เงียบ ๆ
    -> สมการที่เอาไปยืนยัน/เทรดจริง 'คนละตัว' กับที่ค้นเจอ."""
    out = {}
    for k in PARAM_KEYS:
        v = strat.get(k, PARAM_DEFAULTS[k])
        out[k] = _safe_int(v, int(PARAM_DEFAULTS[k])) if k in INT_PARAM_KEYS \
            else _safe_float(v, float(PARAM_DEFAULTS[k]))
        if k not in INT_PARAM_KEYS and not np.isfinite(out[k]):
            out[k] = float(PARAM_DEFAULTS[k])
    return out


# ================================= TRADE JOURNAL (track record ของจริง)
JOURNAL_COLUMNS = ["signal_date", "ticker", "strategy", "grade", "order_type",
                   "entry_mode", "buy_ref", "sell_tp", "stop_sl", "tp_pct", "sl_pct",
                   "hold_days", "action", "status", "fill_price", "exit_date",
                   "exit_price", "net_return_pct", "expected_wr", "expected_npd",
                   "run_date"]
# status: PENDING -> FILLED_TP | FILLED_SL | FILLED_TIME | NOT_FILLED | NO_DATA


def load_journal(path: str = JOURNAL_PATH) -> pd.DataFrame:
    """โหลดสมุดบันทึก — ไฟล์เก่าที่ขาดคอลัมน์ใหม่จะถูกเติมให้อัตโนมัติ (ไม่ crash)."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    try:
        j = pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    for col in JOURNAL_COLUMNS:
        if col not in j.columns:
            j[col] = np.nan
    return j[JOURNAL_COLUMNS]


def save_journal(j: pd.DataFrame, path: str = JOURNAL_PATH) -> None:
    try:
        j.to_csv(path, index=False)
    except OSError as e:
        print(f"  [!] เซฟสมุดบันทึกไม่ได้: {e}")


def resolve_journal(journal: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """ตัดสินผลออร์เดอร์ PENDING ด้วยราคาจริงล่าสุด — กติกาเดียวกับ backtest เป๊ะ
    (รวม gap-through: เปิดทะลุ SL/TP -> คิดที่ราคาเปิดจริง).
    TP/SL คิดใหม่จาก 'ราคาที่ได้จริง' โดยใช้ % ที่บันทึกไว้ = สิ่งที่ผู้ใช้ตั้งจริงหลังไม้ติด."""
    if journal is None or len(journal) == 0:
        return journal if journal is not None else pd.DataFrame(columns=JOURNAL_COLUMNS)
    j = journal.copy()
    for col in ("status", "exit_date", "order_type", "action", "strategy", "grade"):
        if col in j.columns:
            j[col] = j[col].astype(object)   # กัน LossySetitemError เมื่อคอลัมน์เป็น float ล้วน
    if raw is None or len(raw) == 0:
        return j
    by_ticker = {tk: g.sort_values("Date").reset_index(drop=True)
                 for tk, g in raw.groupby("Ticker", sort=False)}
    pending = j.index[j["status"].astype(str) == "PENDING"]
    for idx in pending:
        row = j.loc[idx]
        tk = str(row["ticker"])
        if tk not in by_ticker:
            j.loc[idx, "status"] = "NO_DATA"
            continue
        g = by_ticker[tk]
        sig_date = pd.to_datetime(row["signal_date"], errors="coerce")
        if pd.isna(sig_date):
            j.loc[idx, "status"] = "NO_DATA"
            continue
        fut = g[pd.to_datetime(g["Date"]) > sig_date].reset_index(drop=True)
        if len(fut) == 0:
            continue                                   # ยังไม่มีแท่งใหม่ -> คง PENDING
        hold = _safe_int(row["hold_days"], default=3)
        emode = _safe_int(row["entry_mode"], default=0)
        tp_pct = _safe_float(row["tp_pct"])
        sl_pct = _safe_float(row["sl_pct"])
        buy_ref = _safe_float(row["buy_ref"])
        if emode == 0:
            fill = float(fut["Open"].iloc[0])
            skip_tp_first = False
        else:
            if not (np.isfinite(buy_ref) and buy_ref > MIN_VALID_PRICE):
                continue
            if float(fut["Low"].iloc[0]) > buy_ref:
                j.loc[idx, "status"] = "NOT_FILLED"
                continue
            fill = min(buy_ref, float(fut["Open"].iloc[0]))
            skip_tp_first = True
        if not (np.isfinite(fill) and fill > MIN_VALID_PRICE):
            continue
        if np.isfinite(tp_pct) and np.isfinite(sl_pct):
            tp = fill * (1 + tp_pct / 100.0)
            sl = fill * (1 - sl_pct / 100.0)
        else:                                          # สมุดรุ่นเก่า: ใช้ระดับที่บันทึกไว้
            tp, sl = _safe_float(row["sell_tp"]), _safe_float(row["stop_sl"])
        if not (np.isfinite(tp) and np.isfinite(sl)) or sl <= 0:
            continue                                   # ตัดสินไม่ได้ -> ไม่เดา คง PENDING
        status = exit_price = exit_date = None
        n_avail = min(hold, len(fut))
        for k in range(n_avail):
            o_k = float(fut["Open"].iloc[k])
            h_k = float(fut["High"].iloc[k])
            l_k = float(fut["Low"].iloc[k])
            if k > 0 and o_k <= sl:
                status, exit_price = "FILLED_SL", o_k
            elif k > 0 and o_k >= tp:
                status, exit_price = "FILLED_TP", o_k
            elif TIE_BREAK_SL_WINS and l_k <= sl:
                status, exit_price = "FILLED_SL", sl
            elif h_k >= tp and not (skip_tp_first and k == 0):
                status, exit_price = "FILLED_TP", tp
            elif l_k <= sl:
                status, exit_price = "FILLED_SL", sl
            if status is not None:
                exit_date = fut["Date"].iloc[k]
                break
        if status is None:
            if len(fut) >= hold:
                status = "FILLED_TIME"
                exit_price = float(fut["Close"].iloc[hold - 1])
                exit_date = fut["Date"].iloc[hold - 1]
            else:
                j.loc[idx, "fill_price"] = fill        # ติดแล้วแต่ยังไม่ครบวันถือ
                continue
        j.loc[idx, "status"] = status
        j.loc[idx, "fill_price"] = round(fill, 4)
        j.loc[idx, "exit_price"] = round(float(exit_price), 4)
        j.loc[idx, "exit_date"] = pd.Timestamp(exit_date).strftime("%Y-%m-%d")
        j.loc[idx, "net_return_pct"] = round((exit_price / fill - 1) * 100 - FRICTION_PCT, 2)
    return j


def journal_stats(journal: pd.DataFrame) -> dict:
    """สถิติจริงสะสม — WR ใช้นิยามเดียวกับ backtest: ชนะ = กำไรสุทธิ > 0."""
    if journal is None or len(journal) == 0:
        return dict(n_orders=0)
    status = journal["status"].astype(str)
    filled = journal[status.isin(["FILLED_TP", "FILLED_SL", "FILLED_TIME"])]
    nets = pd.to_numeric(filled["net_return_pct"], errors="coerce").dropna()
    wins = int((nets > 0).sum())
    n_res = int(len(nets))
    exp = pd.to_numeric(filled["expected_npd"], errors="coerce").dropna()
    return dict(
        n_orders=int(len(journal)),
        n_pending=int((status == "PENDING").sum()),
        n_not_filled=int((status == "NOT_FILLED").sum()),
        n_filled=int(len(filled)), n_resolved=n_res, wins=wins,
        realized_wr=_r(wins / n_res * 100) if n_res else None,
        realized_wilson_lb=_r(wilson_lb(wins, n_res) * 100) if n_res else None,
        realized_avg_net=_r(float(nets.mean())) if n_res else None,
        expected_avg_npd=_r(float(exp.mean())) if len(exp) else None,
        best=_r(float(nets.max())) if n_res else None,
        worst=_r(float(nets.min())) if n_res else None,
        cum_net=_r(float(nets.sum())) if n_res else None,
    )


def append_new_orders(journal: pd.DataFrame, vr: VerdictReport, run_date: str) -> pd.DataFrame:
    """บันทึกเฉพาะออร์เดอร์ 'เข้า (TRADE)' แบบ idempotent — รันซ้ำวันเดิมไม่เพิ่มซ้ำ."""
    if journal is None:
        journal = pd.DataFrame(columns=JOURNAL_COLUMNS)
    existing = set()
    if len(journal):
        existing = set(zip(journal["signal_date"].astype(str), journal["ticker"].astype(str)))
    rows = []
    for o in vr.orders:
        if not o.action.startswith("เข้า"):
            continue
        if (vr.asof, o.ticker) in existing:
            continue
        rows.append(dict(
            signal_date=vr.asof, ticker=o.ticker, strategy=o.strategy, grade=o.grade,
            order_type=o.order_type, entry_mode=o.entry_mode, buy_ref=o.buy_ref,
            sell_tp=o.sell_tp, stop_sl=o.stop_sl, tp_pct=o.tp_pct, sl_pct=o.sl_pct,
            hold_days=o.hold_days, action=o.action, status="PENDING",
            fill_price=np.nan, exit_date=np.nan, exit_price=np.nan,
            net_return_pct=np.nan, expected_wr=o.expected_wr,
            expected_npd=o.expected_npd, run_date=run_date))
    if not rows:
        return journal
    add = pd.DataFrame(rows, columns=JOURNAL_COLUMNS)
    if len(journal) == 0:
        return add
    return pd.concat([journal, add], ignore_index=True)


# ======================= DASHBOARD (Layer 1 — Reporting, ธีม Claude ivory+coral)
_STATUS_TH = {"FILLED_TP": ("ชนะ (TP)", "#6E8B5E"), "FILLED_SL": ("แพ้ (SL)", "#C24C3F"),
              "FILLED_TIME": ("หมดเวลา", "#8A8375"), "PENDING": ("รอผล", "#C9A227"),
              "NOT_FILLED": ("limit ไม่ติด", "#A39B8B"), "NO_DATA": ("ไม่มีข้อมูล", "#999999")}

_DASH_CSS = """
:root{--bg:#FAF9F5;--card:#FFFFFF;--line:#E8E4DA;--ink:#29261B;--sub:#6B6558;
--coral:#D97757;--coral-dk:#C05F3C;--green:#6E8B5E;--red:#C24C3F;--amber:#C9A227}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Thai",sans-serif;
font-size:15px;line-height:1.55;padding:24px}
.wrap{max-width:1100px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 12px;color:var(--coral-dk)}
.sub{color:var(--sub);font-size:13px;margin-bottom:18px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;
padding:4px 12px;font-size:12.5px;color:var(--sub)}
.chip.ok{border-color:var(--green);color:var(--green)}
.chip.warn{border-color:var(--amber);color:var(--amber)}
.chip.bad{border-color:var(--red);color:var(--red)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(41,38,27,.05)}
.hero{border-left:5px solid var(--coral)}
.honest{border-left:5px solid var(--amber);background:#FFFDF6}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.tile{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .v{font-size:20px;font-weight:600}.tile .k{font-size:12px;color:var(--sub)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}
.scroll{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
th{color:var(--sub);font-weight:600;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;color:#fff}
.vcard{border:1px solid var(--line);border-left:4px solid var(--coral);border-radius:10px;
padding:12px 14px;margin-bottom:10px;background:var(--bg)}
.vcard.watch{border-left-color:var(--amber)}
.vcard b{font-size:15px}.muted{color:var(--sub);font-size:12.5px}
.big{font-size:17px;font-weight:600}.pos{color:var(--green)}.neg{color:var(--red)}
.empty{color:var(--sub);font-style:italic;padding:8px 0}
.badge{display:inline-block;border-radius:8px;padding:2px 10px;font-weight:600;color:#fff}
footer{color:var(--sub);font-size:12px;margin-top:8px}
"""


def _fmt(x, suf="", nd=2):
    if x is None:
        return "-"
    f = _safe_float(x)
    if not np.isfinite(f):
        return "-"
    if nd <= 0:
        return f"{int(round(f)):,}{suf}"
    return f"{round(f, nd)}{suf}"


def _cls(x, good_when_positive=True):
    f = _safe_float(x)
    if not np.isfinite(f):
        return ""
    ok = f >= 0 if good_when_positive else f <= 0
    return "pos" if ok else "neg"


def generate_dashboard(run_info: dict, stats: dict, journal: pd.DataFrame,
                       vr: VerdictReport | None, confirmed: pd.DataFrame,
                       port: dict | None = None) -> str:
    """สร้าง HTML แดชบอร์ดทั้งหน้า (pure function: data -> string, เทสต์ได้)."""
    grade = run_info.get("grade", "-")
    gcolor = {"A": "#6E8B5E", "B": "#C9A227"}.get(grade, "#C24C3F")
    gtext = {"A": "เกรด A — ถึงเป้าที่ตั้งไว้", "B": "เกรด B — มี edge จริงแต่ไม่ถึงเป้า"}.get(
        grade, "ไม่ผ่าน — ไม่มีสมการที่ยืนยันได้")
    chips = (f'<span class="chip">{run_info.get("universe")} · '
             f'{run_info.get("n_tickers")} หุ้น</span>'
             f'<span class="chip">แท่งล่าสุด {run_info.get("last_bar")}</span>'
             f'<span class="chip">ค้นครบ {run_info.get("n_space", 0):,} สมการ</span>'
             f'<span class="chip">ยืนยัน 2 ช่วง OOS</span>'
             f'<span class="chip {"ok" if grade == "A" else "warn" if grade == "B" else "bad"}">'
             f'เป้า WR≥{TARGET_WIN_RATE:.0f}% & กำไร≥{TARGET_NET_PER_DAY}%/วัน</span>')
    if run_info.get("demo"):
        chips += '<span class="chip bad">DEMO — ข้อมูลสังเคราะห์ ไม่ใช่ราคาจริง</span>'

    # ---- คำฟันธง ----
    vcards = ""
    if vr is not None and vr.orders:
        for o in vr.orders:
            cls = "vcard" if o.action.startswith("เข้า") else "vcard watch"
            rs = "" if o.reasons == "-" else f'<div class="muted">เหตุผล: {o.reasons}</div>'
            vcards += (f'<div class="{cls}"><b>{o.ticker}</b> — {o.action} '
                       f'<span class="muted">({o.agree_count}/{o.of_k} สมการเห็นตรงกัน · '
                       f'เกรด {o.grade} · คาด WR {_fmt(o.expected_wr, "%")} · '
                       f'{_fmt(o.expected_npd, "%/วัน")})</span><br>'
                       f'{o.order_type} · ซื้อ <b>{o.buy_ref}</b> · TP <b>{o.sell_tp}</b> '
                       f'(+{o.tp_pct}%) · SL <b>{o.stop_sl}</b> (-{o.sl_pct}%) · '
                       f'{o.lots} lot ({o.shares:,} หุ้น ≈ {o.cost_thb:,.0f} บาท) · '
                       f'ถือสูงสุด {o.hold_days} วัน{rs}</div>')
    else:
        vcards = '<div class="empty">วันนี้: ไม่มีคำสั่งเข้า</div>'
    overall = vr.overall if vr is not None else "-"

    # ---- ความจริงเรื่องเป้าหมาย ----
    honest = (f'<div class="card honest"><h2>เป้าที่สั่ง vs ผลจริง (ห้ามโกหก)</h2>'
              f'<span class="badge" style="background:{gcolor}">{gtext}</span>'
              f'<div class="tiles" style="margin-top:12px">'
              f'<div class="tile"><div class="v">{TARGET_WIN_RATE:.0f}% / {TARGET_NET_PER_DAY}%</div>'
              f'<div class="k">เป้า: WR / กำไรต่อวัน</div></div>'
              f'<div class="tile"><div class="v">{run_info.get("n_grade_a", 0)}</div>'
              f'<div class="k">สมการถึงเป้า (เกรด A)</div></div>'
              f'<div class="tile"><div class="v">{run_info.get("n_grade_b", 0)}</div>'
              f'<div class="k">สมการมี edge จริง (เกรด B)</div></div>'
              f'<div class="tile"><div class="v">{_fmt(run_info.get("best_wr"), "%")}</div>'
              f'<div class="k">WR ดีสุดที่ยืนยันได้ (OOS)</div></div>'
              f'<div class="tile"><div class="v">{_fmt(run_info.get("best_npd"), "%")}</div>'
              f'<div class="k">กำไร/วัน ดีสุดที่ยืนยันได้</div></div></div>'
              f'<div class="muted" style="margin-top:10px">{run_info.get("honest_note", "")}</div>'
              f'</div>')

    # ---- พอร์ตจำลอง ----
    if port:
        ptiles = f"""
        <div class="tiles">
          <div class="tile"><div class="v">{_fmt(port.get('avg_daily_pct'), '%', 4)}</div>
               <div class="k">กำไรเฉลี่ยต่อวัน (พอร์ตจริง)</div></div>
          <div class="tile"><div class="v">{_fmt(port.get('total_return_pct'), '%')}</div>
               <div class="k">ผลตอบแทนรวมช่วง OOS</div></div>
          <div class="tile"><div class="v">{_fmt(port.get('cagr_pct'), '%')}</div>
               <div class="k">ต่อปี (CAGR)</div></div>
          <div class="tile"><div class="v neg">{_fmt(port.get('max_drawdown_pct'), '%')}</div>
               <div class="k">ขาดทุนสูงสุด (max DD)</div></div>
          <div class="tile"><div class="v">{_fmt(port.get('win_rate'), '%')}</div>
               <div class="k">WR พอร์ต ({port.get('n_trades', 0)} ไม้)</div></div>
          <div class="tile"><div class="v">{_fmt(port.get('exposure'), '%')}</div>
               <div class="k">ใช้เงินเฉลี่ย (exposure)</div></div>
        </div>"""
    else:
        ptiles = '<div class="empty">ยังไม่มีสมการที่ยืนยันได้ จึงยังไม่มีผลพอร์ตจำลอง</div>'

    # ---- กราฟ ----
    charts_html = charts_js = ""
    eq = (port or {}).get("equity")
    if eq is not None and len(eq):
        labels = [pd.Timestamp(x).strftime("%Y-%m-%d") for x in eq["Date"].tolist()]
        vals = [round(float(v), 2) for v in eq["equity"].tolist()]
        charts_html += ('<div class="card"><h2>เส้นทางเงินทุนพอร์ตจำลอง (บาท)</h2>'
                        '<canvas id="eq" height="200"></canvas></div>')
        charts_js += f"""
        new Chart(document.getElementById('eq'),{{type:'line',
          data:{{labels:{json.dumps(labels)},datasets:[{{data:{json.dumps(vals)},
            borderColor:'#D97757',backgroundColor:'rgba(217,119,87,.12)',fill:true,
            tension:.25,pointRadius:0,borderWidth:2}}]}},
          options:{{plugins:{{legend:{{display:false}}}},
            scales:{{y:{{grid:{{color:'#EFEBE0'}}}},x:{{grid:{{display:false}},
            ticks:{{maxTicksLimit:8}}}}}}}}}});"""
    nets = pd.to_numeric(journal["net_return_pct"], errors="coerce").dropna() \
        if (journal is not None and len(journal)) else pd.Series(dtype=float)
    if len(nets):
        cum = nets.cumsum().round(2).tolist()
        charts_html += ('<div class="card"><h2>กำไรสะสมจริงจากสมุดบันทึก (%)</h2>'
                        '<canvas id="cum" height="200"></canvas></div>')
        charts_js += f"""
        new Chart(document.getElementById('cum'),{{type:'line',
          data:{{labels:{json.dumps([str(i + 1) for i in range(len(cum))])},
            datasets:[{{data:{json.dumps(cum)},borderColor:'#6E8B5E',
            backgroundColor:'rgba(110,139,94,.12)',fill:true,tension:.25,pointRadius:3}}]}},
          options:{{plugins:{{legend:{{display:false}}}},
            scales:{{y:{{grid:{{color:'#EFEBE0'}}}},x:{{grid:{{display:false}}}}}}}}}});"""
    if charts_js:
        charts_js = ('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>'
                     f'<script>{charts_js}</script>')

    # ---- track record ----
    n_orders = stats.get("n_orders", 0)
    if n_orders:
        tiles = f"""
        <div class="tiles">
          <div class="tile"><div class="v">{n_orders}</div><div class="k">ออร์เดอร์สะสม</div></div>
          <div class="tile"><div class="v">{stats.get('n_pending', 0)}</div><div class="k">รอผล</div></div>
          <div class="tile"><div class="v">{stats.get('n_not_filled', 0)}</div><div class="k">limit ไม่ติด</div></div>
          <div class="tile"><div class="v">{_fmt(stats.get('realized_wr'), '%')}</div>
               <div class="k">WR จริง (LB {_fmt(stats.get('realized_wilson_lb'), '%')})</div></div>
          <div class="tile"><div class="v">{_fmt(stats.get('realized_avg_net'), '%')}</div>
               <div class="k">กำไรจริงเฉลี่ย/ไม้</div></div>
          <div class="tile"><div class="v {_cls(stats.get('cum_net'))}">{_fmt(stats.get('cum_net'), '%')}</div>
               <div class="k">กำไรสะสมจริง</div></div>
        </div>"""
    else:
        tiles = '<div class="empty">ยังไม่มีประวัติ — ระบบเริ่มบันทึกอัตโนมัติจากรอบนี้</div>'

    # ---- สมุดบันทึก ----
    if journal is not None and len(journal):
        rows = ""
        for _, r in journal.tail(15).iloc[::-1].iterrows():
            th, color = _STATUS_TH.get(str(r["status"]), (str(r["status"]), "#999"))
            net = r["net_return_pct"]
            net_html = "-" if pd.isna(net) else \
                f'<span class="{_cls(net)}">{_fmt(net, "%")}</span>'
            rows += (f'<tr><td>{r["signal_date"]}</td><td><b>{r["ticker"]}</b></td>'
                     f'<td>{r["order_type"]}</td><td>{r["buy_ref"]}</td><td>{r["sell_tp"]}</td>'
                     f'<td>{r["stop_sl"]}</td>'
                     f'<td><span class="pill" style="background:{color}">{th}</span></td>'
                     f'<td>{net_html}</td></tr>')
        journal_html = ('<div class="scroll"><table><tr><th>วันสัญญาณ</th><th>หุ้น</th>'
                        '<th>ออร์เดอร์</th><th>ซื้อ</th><th>TP</th><th>SL</th>'
                        f'<th>สถานะ</th><th>กำไรสุทธิ</th></tr>{rows}</table></div>')
    else:
        journal_html = '<div class="empty">สมุดบันทึกว่าง</div>'

    # ---- สมการที่ยืนยันแล้ว ----
    if confirmed is not None and len(confirmed):
        show = confirmed[confirmed["grade"].isin(["A", "B"])].head(10)
        if len(show):
            cols = [("grade", "เกรด"), ("label", "สมการ"), ("is_n", "ไม้(IS)"),
                    ("oos_n", "ไม้(OOS)"), ("oos_wr", "WR%"), ("oos_wlb", "WR LB%"),
                    ("oos_net", "กำไร%/ไม้"), ("oos_npd", "กำไร%/วัน"), ("oos_pf", "PF")]
            head = "".join(f"<th>{t}</th>" for _, t in cols)
            body = ""
            for _, r in show.iterrows():
                # ใช้ r.get(): ตาราง confirmed ที่ขาดคอลัมน์ (เช่นมาจากไฟล์รุ่นเก่า)
                # ต้องไม่ทำให้ทั้งหน้าพัง [แก้บั๊ก ครัช]
                cells = []
                for k, _t in cols:
                    v = r.get(k, None)
                    cells.append(f"<td>{v if k in ('grade', 'label', 'is_n', 'oos_n') and v is not None else _fmt(v)}</td>")
                body += "<tr>" + "".join(cells) + "</tr>"
            conf_html = f'<div class="scroll"><table><tr>{head}</tr>{body}</table></div>'
        else:
            conf_html = '<div class="empty">ไม่มีสมการผ่านการยืนยัน</div>'
    else:
        conf_html = '<div class="empty">ไม่มีสมการผ่านการยืนยัน</div>'

    return f"""<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SET Daily Edge Finder — Dashboard</title><style>{_DASH_CSS}</style></head>
<body><div class="wrap">
<h1>📈 SET Daily Edge Finder</h1>
<div class="sub">รันเมื่อ {run_info.get('run_ts')} · เทรดรายวัน · ตั้งคำสั่งเช้าวันทำการถัดไป</div>
<div class="chips">{chips}</div>
<div class="card hero"><h2>คำฟันธงสำหรับวันทำการถัดไป</h2>
<div class="big">{overall}</div>{vcards}</div>
{honest}
<div class="card"><h2>พอร์ตจำลองด้วยเงินจริง {_fmt((port or {}).get('capital'), ' บาท', 0)}
 (สูงสุด {MAX_POSITIONS} ไม้พร้อมกัน)</h2>{ptiles}</div>
{charts_html}
<div class="card"><h2>Track Record — ผลจริงสะสมจากคำฟันธงที่ผ่านมา</h2>{tiles}</div>
<div class="card"><h2>สมุดบันทึกออร์เดอร์ (ล่าสุด 15)</h2>{journal_html}</div>
<div class="card"><h2>สมการที่ยืนยันผ่าน out-of-sample</h2>{conf_html}</div>
<footer>WR LB = ขอบล่างความมั่นใจ 95% (Wilson) · ตัวเลขทุกตัวหักต้นทุน
{FRICTION_PCT}% แล้ว · ระบบไม่การันตีผลอนาคต ไม่ใช่คำแนะนำการลงทุน</footer>
</div>{charts_js}</body></html>"""


# ================================================== PIPELINE (Layer 2 — flow)
def _honest_note(n_a: int, n_b: int, best: dict | None, port: dict | None) -> str:
    """ข้อความสรุปความจริง — ถ้าไม่ถึงเป้าต้องพูดตรง ๆ ห้ามตกแต่งตัวเลข."""
    if n_a > 0:
        return (f"มีสมการถึงเป้า {n_a} ตัว (WR≥{TARGET_WIN_RATE:.0f}% และ "
                f"≥{TARGET_NET_PER_DAY}%/วัน บนข้อมูลที่ไม่เคยเห็นทั้ง 2 ช่วง). "
                "ยังต้องเฝ้าดูผลจริงในสมุดบันทึกก่อนเชื่อเต็มร้อย — อดีตไม่การันตีอนาคต.")
    if n_b > 0 and best:
        note = (f"ไม่มีสมการใดถึงเป้า WR>{TARGET_WIN_RATE:.0f}% + {TARGET_NET_PER_DAY}%/วัน. "
                f"ดีที่สุดที่ 'ยืนยันได้จริง' คือ WR {_fmt(best.get('oos_wr'), '%')}, "
                f"กำไร {_fmt(best.get('oos_npd'), '%')}/วัน "
                f"({_fmt(best.get('oos_net'), '%')}/ไม้, {_safe_int(best.get('oos_n'), 0)} ไม้).")
        if port and port.get("avg_daily_pct") is not None:
            note += (f" พอร์ตจำลองจริงได้ {_fmt(port.get('avg_daily_pct'), '%', 4)}/วัน "
                     f"(รวม {_fmt(port.get('total_return_pct'), '%')}, "
                     f"ขาดทุนสูงสุด {_fmt(port.get('max_drawdown_pct'), '%')}).")
        note += (" เหตุผลเชิงคณิตศาสตร์: ต้นทุนไป-กลับ "
                 f"{FRICTION_PCT}% กินกำไรทุกไม้ และ WR สูงมากจะมาพร้อม TP เล็ก "
                 "(กำไรต่อไม้ต่ำ) เสมอ — ทั้งสองอย่างพร้อมกันจึงหายากมากในตลาดจริง.")
        return note
    return ("ไม่มีสมการใดผ่านการยืนยัน out-of-sample รอบนี้ = คำตอบที่ซื่อสัตย์คือ "
            "'ยังไม่ควรเข้า'. ลองเพิ่มจำนวนหุ้น (UNIVERSE=SET100), ยืดข้อมูล "
            "(HISTORY_PERIOD='10y') หรือลดเกณฑ์ FLOOR_* แล้วรันใหม่.")


def run_pipeline(raw: pd.DataFrame, families=None, keep_top: int = TOP_N_VALIDATE,
                 progress: bool = True, journal_path: str | None = JOURNAL_PATH,
                 dashboard_path: str | None = DASHBOARD_PATH, demo: bool = False,
                 universe_name: str = None, save_csv: bool = True,
                 capital: float = CAPITAL_THB) -> dict:
    """ไหลทั้งกระบวนการ: ราคา -> ค้น -> ยืนยัน -> พอร์ต -> ฟันธง -> สมุด -> dashboard.
    คืน dict ของทุกชิ้นส่วน (ทำให้เทสต์ end-to-end ได้โดยไม่ต้องแตะไฟล์/network)."""
    if raw is None or len(raw) == 0:
        raise ValueError("ไม่มีข้อมูลราคา")
    n_tickers = int(raw["Ticker"].nunique())

    # 1) ตัดสินผลออร์เดอร์เก่าก่อนเสมอ (track record ต้องมาก่อนคำฟันธงใหม่)
    journal = load_journal(journal_path) if journal_path else pd.DataFrame(columns=JOURNAL_COLUMNS)
    journal = resolve_journal(journal, raw)

    # 2) เตรียมข้อมูล + แบ่งช่วง
    data = precompute(raw)
    c = build_cache(data)
    segs = make_segments(data)
    if progress:
        print(f"  แบ่งข้อมูล: IS {int(segs['is_'].sum()):,} แถว | "
              f"OOS1 {int(segs['oos1'].sum()):,} | OOS2 {int(segs['oos2'].sum()):,} "
              f"| คั่นที่ {segs['cut1']:%Y-%m-%d} / {segs['cut2']:%Y-%m-%d} "
              f"(embargo {segs['embargo']} แท่ง)")

    # 3) ค้นหา + ยืนยัน
    cands = run_search(c, segs["is_"], keep_top=keep_top, families=families, progress=progress)
    confirmed = validate(c, cands, segs, progress=progress) if cands else pd.DataFrame()
    n_a = int((confirmed["grade"] == "A").sum()) if len(confirmed) else 0
    n_b = int((confirmed["grade"] == "B").sum()) if len(confirmed) else 0
    best = confirmed.iloc[0].to_dict() if (len(confirmed) and confirmed.iloc[0]["grade"] in ("A", "B")) else None

    # 4) พอร์ตจำลองด้วยสมการที่ดีที่สุด (บนช่วง out-of-sample ล้วน)
    port = None
    if best is not None:
        strat = _coerce_strategy({k: best[k] for k in PARAM_KEYS})
        port = portfolio_backtest(data, c, strat, seg=segs["oos"], capital=capital)

    # 5) ฟันธงวันถัดไป + บันทึกสมุด
    vr = DailyVerdictAgent().decide(data, c, confirmed)
    journal = append_new_orders(journal, vr, run_date=f"{datetime.now():%Y-%m-%d}")
    if journal_path:
        save_journal(journal, journal_path)
    jstats = journal_stats(journal)

    # 6) รายงาน
    last_bar = pd.to_datetime(raw["Date"]).max()
    run_info = dict(
        run_ts=f"{datetime.now():%Y-%m-%d %H:%M}", last_bar=f"{last_bar:%Y-%m-%d}",
        universe=universe_name or UNIVERSE, n_tickers=n_tickers, demo=bool(demo),
        grade=(best or {}).get("grade", "-"), n_grade_a=n_a, n_grade_b=n_b,
        n_space=count_search_space(),
        best_wr=(best or {}).get("oos_wr"), best_npd=(best or {}).get("oos_npd"),
        honest_note=_honest_note(n_a, n_b, best, port))
    html = generate_dashboard(run_info, jstats, journal, vr, confirmed, port)
    if dashboard_path:
        try:
            with open(dashboard_path, "w", encoding="utf-8") as f:
                f.write(html)
        except OSError as e:
            print(f"  [!] เขียน dashboard ไม่ได้: {e}")
    if save_csv and len(confirmed):
        try:
            confirmed.head(200).to_csv("confirmed_strategies_daily.csv", index=False)
            if port is not None and len(port.get("trades", [])):
                port["trades"].to_csv("portfolio_trades_oos.csv", index=False)
        except OSError as e:
            print(f"  [!] เขียน CSV ไม่ได้: {e}")
    return dict(data=data, cache=c, segs=segs, candidates=cands, confirmed=confirmed,
                best=best, port=port, verdict=vr, journal=journal, jstats=jstats,
                run_info=run_info, html=html)


def _print_track_record(stats: dict) -> None:
    print("\n" + "=" * 78)
    print('TRACK RECORD — ผลจริงสะสมจากคำฟันธงที่ผ่านมา (คำตอบของ "แม่นจริงมั้ย")')
    if stats.get("n_orders", 0) == 0:
        print("  ยังไม่มีประวัติ — ระบบเริ่มบันทึกอัตโนมัติจากรอบนี้")
        print("=" * 78)
        return
    print(f"  ออร์เดอร์สะสม {stats['n_orders']} | รอผล {stats['n_pending']} "
          f"| limit ไม่ติด {stats['n_not_filled']} | จบแล้ว {stats['n_resolved']}")
    if stats.get("n_resolved"):
        print(f"  ชนะ {stats['wins']}/{stats['n_resolved']} = WR จริง {stats['realized_wr']}% "
              f"(Wilson LB {stats['realized_wilson_lb']}%)")
        print(f"  กำไรสุทธิเฉลี่ยจริง {stats['realized_avg_net']}%/ไม้ "
              f"| สะสม {stats['cum_net']}% | ดีสุด {stats['best']}% | แย่สุด {stats['worst']}%")
    print("=" * 78)


def main(argv=None) -> int:
    import argparse
    global TICKERS, UNIVERSE, MAX_POSITIONS, BUDGET_PER_TRADE_THB
    ap = argparse.ArgumentParser(description="SET Daily Edge Finder")
    ap.add_argument("--demo", action="store_true", help="ใช้ข้อมูลสังเคราะห์ (ไม่ต้องต่อเน็ต)")
    ap.add_argument("--offline", action="store_true", help="ใช้ราคาจากแคชที่เคยดึงไว้")
    ap.add_argument("--fast", action="store_true", help="ย่อ search space ให้รันเร็ว")
    ap.add_argument("--universe", default=UNIVERSE, choices=sorted(UNIVERSES),
                    help="ชุดหุ้นที่ใช้")
    ap.add_argument("--limit-tickers", type=int, default=0, help="จำกัดจำนวนหุ้น (ทดสอบ)")
    ap.add_argument("--capital", type=float, default=CAPITAL_THB, help="เงินทุนพอร์ตจำลอง")
    ap.add_argument("--max-positions", type=int, default=MAX_POSITIONS,
                    dest="max_positions", help="ถือพร้อมกันสูงสุดกี่ไม้")
    ap.add_argument("--selftest", "--test", action="store_true", dest="selftest",
                    help="รันชุดทดสอบทั้งหมด (ต้องมี pytest)")
    args = ap.parse_args([] if argv is None and len(sys.argv) == 1 else argv)

    if args.selftest:
        return run_selftest()
    if args.fast:
        fast_mode(True)
    if args.max_positions and args.max_positions > 0:
        MAX_POSITIONS = int(args.max_positions)
        BUDGET_PER_TRADE_THB = args.capital // MAX_POSITIONS
    UNIVERSE = args.universe
    TICKERS = list(UNIVERSES[UNIVERSE])
    if args.limit_tickers and args.limit_tickers > 0:
        TICKERS = TICKERS[:args.limit_tickers]

    print("=" * 78)
    print("SET DAILY EDGE FINDER v1 — ระบบเทรดรายวัน (เริ่มทำงาน)")
    print(f"universe={UNIVERSE} ({len(TICKERS)} ตัว) | ทุน {args.capital:,.0f} บาท "
          f"| ถือพร้อมกันสูงสุด {MAX_POSITIONS} ไม้")
    print(f"เป้าที่สั่ง: WR > {TARGET_WIN_RATE:.0f}% และกำไร > {TARGET_NET_PER_DAY}% ต่อวัน")
    print(f"จะค้นสมการทั้งหมด {count_search_space():,} แบบ (ครบทุกความเป็นไปได้ ไม่ใช่การสุ่ม)")
    print("=" * 78)

    if args.demo:
        print("\n[DEMO] ใช้ข้อมูลสังเคราะห์ — พิสูจน์ว่าโปรแกรมทำงานครบ ไม่ใช่ราคาจริง")
        raw = synthetic_prices(TICKERS)
    elif args.offline:
        raw = load_price_cache()
        if len(raw) == 0:
            print("ไม่มีแคชราคา — รันแบบปกติ (ต่อเน็ต) หรือ --demo ก่อน")
            return 1
        print(f"[OFFLINE] ใช้แคช {len(raw):,} แถว")
    else:
        try:
            raw = fetch_prices(TICKERS)
        except RuntimeError as e:
            print(f"\n[!] ดึงราคาไม่สำเร็จ: {e}")
            print("    ลองใหม่ภายหลัง หรือรัน --demo เพื่อตรวจว่าโปรแกรมทำงานถูกต้อง")
            return 1
    if len(raw) == 0:
        print("[!] ไม่มีข้อมูลราคาให้ประมวลผล")
        return 1

    last_bar = pd.to_datetime(raw["Date"]).max()
    print(f"\nแท่งข้อมูลล่าสุด: {last_bar:%Y-%m-%d} ({last_bar.strftime('%a')}) "
          f"| หุ้น {raw['Ticker'].nunique()} ตัว | {len(raw):,} แถว")
    print("  จังหวะใช้จริง: รันหลังตลาดปิด -> ตั้งคำสั่งเช้าวันทำการถัดไป")

    res = run_pipeline(raw, demo=args.demo, universe_name=UNIVERSE, capital=args.capital)
    _print_track_record(res["jstats"])

    confirmed, best, port, vr = res["confirmed"], res["best"], res["port"], res["verdict"]
    ri = res["run_info"]
    print("\n" + "=" * 78)
    print(f"ผลการยืนยัน: เกรด A (ถึงเป้า) {ri['n_grade_a']} สมการ | "
          f"เกรด B (มี edge จริง) {ri['n_grade_b']} สมการ")
    print("=" * 78)
    if len(confirmed):
        show = confirmed[confirmed["grade"].isin(["A", "B"])].head(TOP_N_REPORT)
        if len(show):
            cols = ["grade", "label", "is_n", "is_wr", "oos_n", "oos_wr", "oos_wlb",
                    "oos_net", "oos_npd", "oos_pf"]
            print("\nสมการที่ยืนยันผ่าน out-of-sample ทั้ง 2 ช่วง (บนสุด = ดีสุด):")
            with pd.option_context("display.max_colwidth", 70, "display.width", 200):
                print(show[cols].to_string(index=False))
    if port:
        print(f"\nพอร์ตจำลองบนช่วง out-of-sample (ทุน {port['capital']:,.0f} บาท, "
              f"สูงสุด {MAX_POSITIONS} ไม้):")
        print(f"  กำไรเฉลี่ย {port['avg_daily_pct']}%/วัน | รวม {port['total_return_pct']}% "
              f"| ต่อปี {port['cagr_pct']}% | ขาดทุนสูงสุด {port['max_drawdown_pct']}%")
        print(f"  เทรด {port['n_trades']} ไม้ | WR {port['win_rate']}% "
              f"| กำไรเฉลี่ย {port['avg_net_pct']}%/ไม้ | ใช้เงินเฉลี่ย {port['exposure']}%")
        if port['skipped_no_cash'] or port['skipped_no_slot']:
            print(f"  พลาดสัญญาณเพราะงบไม่พอ 1 lot: {port['skipped_no_cash']} ครั้ง "
                  f"| เพราะไม้เต็ม: {port['skipped_no_slot']} ครั้ง "
                  f"(งบต่อไม้ {port['budget_per_trade']:,.0f} บาท) "
                  f"-> เพิ่มทุน/ลดจำนวนไม้ จะเข้าได้มากขึ้น")
        print(f"  วันที่ทำได้ถึงเป้า {TARGET_NET_PER_DAY}%: {port['days_target_hit']}/"
              f"{port['n_days']} วัน")

    print("\n" + "-" * 78)
    print("คำฟันธงสำหรับวันทำการถัดไป")
    print(f"  {vr.overall}")
    for o in vr.orders:
        print(f"   - {o.ticker}: {o.action} | {o.order_type} | ซื้อ {o.buy_ref} "
              f"TP {o.sell_tp} SL {o.stop_sl} | {o.lots} lot ({o.cost_thb:,.0f} บาท) "
              f"| ถือ {o.hold_days} วัน | เหตุผล: {o.reasons}")
    if vr.orders:
        try:
            pd.DataFrame([asdict(o) for o in vr.orders]).to_csv("daily_orders.csv", index=False)
            print("  -> daily_orders.csv")
        except OSError:
            pass

    print("\n" + "=" * 78)
    print("ความจริงเรื่องเป้าหมาย (ห้ามโกหก)")
    print("  " + ri["honest_note"].replace(". ", ".\n  "))
    print("=" * 78)
    print(f"\nแดชบอร์ด -> {DASHBOARD_PATH}")
    try:
        from IPython.display import HTML, display
        display(HTML(res["html"]))
    except Exception:
        pass
    print(f"[{datetime.now():%H:%M:%S}] เสร็จสิ้น")
    return 0


def run_selftest() -> int:
    try:
        import pytest as _pt
    except ImportError:
        print("ต้องติดตั้ง pytest ก่อน: pip install pytest")
        return 1
    return int(_pt.main([os.path.abspath(__file__), "-q"]))


# ============================================================================
# SELF-TESTS — อยู่ในไฟล์เดียวกับระบบ (ไม่ต้องมีไฟล์แยก)
#   รันเทสต์: python daily_edge_finder.py --selftest   หรือ  pytest daily_edge_finder.py
#   รันระบบ : python daily_edge_finder.py              (ส่วนนี้ไม่ทำงาน ไม่ต้องมี pytest)
# ============================================================================
import sys as _sys

SELF = _sys.modules[__name__]           # alias: โค้ดเทสต์อ้าง SELF.<ชื่อ> = โมดูลนี้เอง

try:
    import pytest
except ImportError:
    pytest = None


if pytest is not None:
    @pytest.fixture(autouse=True)
    def _relax_liquidity_for_tests():
        """เทสต์ใช้ข้อมูลจำลองเล็ก ๆ — ปิดเกณฑ์สภาพคล่องระหว่างเทสต์
        (มีเทสต์เฉพาะของตัวกรองสภาพคล่องแยกไว้เอง) แล้วคืนค่าเดิมเสมอ."""
        old_t, old_p = SELF.MIN_TURNOVER_THB, SELF.MIN_PRICE_THB
        SELF.MIN_TURNOVER_THB, SELF.MIN_PRICE_THB = 0.0, 0.0
        yield
        SELF.MIN_TURNOVER_THB, SELF.MIN_PRICE_THB = old_t, old_p


# ------------------------------------------------------------------ helpers
def _bars(name="X", closes=None, opens=None, highs=None, lows=None, vol=1_000_000.0,
          start="2021-01-04"):
    c = np.asarray(closes, dtype=float)
    n = len(c)
    o = np.asarray(opens, dtype=float) if opens is not None else c.copy()
    h = np.asarray(highs, dtype=float) if highs is not None else np.maximum(o, c) * 1.01
    l = np.asarray(lows, dtype=float) if lows is not None else np.minimum(o, c) * 0.99
    v = np.full(n, float(vol)) if np.isscalar(vol) else np.asarray(vol, dtype=float)
    return pd.DataFrame({"Ticker": name, "Date": pd.bdate_range(start, periods=n),
                         "Open": o, "High": h, "Low": l, "Close": c, "Volume": v})


def _multi(nt=4, n=260, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(nt):
        c = 100 + np.cumsum(rng.normal(0, 1.2, n))
        c = np.maximum(c, 5.0)
        out.append(_bars(f"T{i}", c))
    return pd.concat(out, ignore_index=True)


def _strat(fam=0, **over):
    s = dict(SELF.PARAM_DEFAULTS)
    s["entry_family"] = fam
    s.update(over)
    return s


# ------------------------------------------------------------- indicators
def test_rsi_bounds_and_direction():
    up = pd.Series(np.linspace(100, 130, 60))
    r = SELF.wilder_rsi(up, 14).dropna()
    assert r.between(0, 100).all() and r.iloc[-1] > 50


def test_rsi_flat_is_50_no_div_zero():
    assert (SELF.wilder_rsi(pd.Series([10.0] * 30), 14).dropna() == 50.0).all()


def test_rsi_pure_up_is_100():
    s = pd.Series(np.arange(1, 40, dtype=float))
    assert SELF.wilder_rsi(s, 14).dropna().iloc[-1] == 100.0


def test_ema_matches_pandas():
    s = pd.Series(np.arange(1, 40, dtype=float))
    assert np.allclose(SELF.ema(s, 10).values, s.ewm(span=10, adjust=False).mean().values)


def test_atr_non_negative():
    df = _bars("X", list(np.linspace(100, 130, 60)))
    assert (SELF.atr(df["High"], df["Low"], df["Close"], 14).dropna() >= 0).all()


def test_adx_bounded():
    df = _bars("X", list(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 120))))
    a = SELF.adx(df["High"], df["Low"], df["Close"], 14).dropna()
    assert a.between(0, 100).all()


def test_adx_flat_prices_no_crash():
    df = _bars("X", [100.0] * 60)
    a = SELF.adx(df["High"], df["Low"], df["Close"], 14)
    assert not np.isinf(a.to_numpy(dtype=float)).any()


def test_macd_cross_is_bool():
    s = pd.Series(100 + np.cumsum(np.random.default_rng(2).normal(0, 1, 120)))
    assert SELF.macd_cross_up(s, 12, 26).dtype == bool


def test_stoch_bounded_and_flat_safe():
    df = _bars("X", list(100 + np.cumsum(np.random.default_rng(3).normal(0, 1, 100))))
    k = SELF.stoch_k(df["High"], df["Low"], df["Close"], 14).dropna()
    assert k.between(0, 100).all()
    flat = _bars("F", [50.0] * 40)
    kf = SELF.stoch_k(flat["High"], flat["Low"], flat["Close"], 14)
    assert not np.isinf(kf.to_numpy(dtype=float)).any()


def test_down_streak_counts():
    s = pd.Series([10.0, 9.0, 8.0, 7.0, 8.0, 7.0])
    assert list(SELF.down_streak(s).values) == [0.0, 1.0, 2.0, 3.0, 0.0, 1.0]


def test_wilson_lb_properties():
    assert SELF.wilson_lb(0, 0) == 0.0
    assert SELF.wilson_lb(8, 10) < 0.8
    assert SELF.wilson_lb(800, 1000) > SELF.wilson_lb(8, 10)
    assert 0.0 <= SELF.wilson_lb(15, 10) <= 1.0        # wins > n ต้องไม่พัง


# ------------------------------------------------------------- data layer
def test_clean_prices_drops_bad_rows():
    df = _bars("X", [100.0] * 6)
    df.loc[1, "Close"] = 0.0                    # ราคา 0
    df.loc[2, "High"] = float("nan")            # NaN
    df.loc[3, ["High", "Low"]] = [90.0, 110.0]  # High < Low
    out = SELF.clean_prices(df)
    assert len(out) == 3
    assert (out[["Open", "High", "Low", "Close"]] > 0).all().all()


def test_clean_prices_dedups_and_sorts():
    df = pd.concat([_bars("B", [10.0] * 3), _bars("A", [20.0] * 3)], ignore_index=True)
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    out = SELF.clean_prices(dup)
    assert len(out) == 6 and out["Ticker"].iloc[0] == "A"
    assert out.duplicated(["Ticker", "Date"]).sum() == 0


def test_clean_prices_missing_column_raises():
    with pytest.raises(ValueError):
        SELF.clean_prices(pd.DataFrame({"Ticker": ["X"], "Date": ["2021-01-01"]}))


def test_clean_prices_empty_input():
    out = SELF.clean_prices(pd.DataFrame())
    assert len(out) == 0 and list(out.columns) == SELF.PRICE_COLUMNS


def test_to_naive_datetime_both_forms():
    aware = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("Asia/Bangkok"))
    naive = pd.Series(pd.to_datetime(["2024-01-01", "2024-01-02"]))
    for s in (aware, naive):
        assert getattr(SELF._to_naive_datetime(s).dt, "tz", None) is None


def test_synthetic_prices_valid_and_deterministic():
    a = SELF.synthetic_prices(["A", "B"], n_days=120, seed=5)
    b = SELF.synthetic_prices(["A", "B"], n_days=120, seed=5)
    assert a.equals(b)
    assert (a["High"] >= a["Low"]).all() and (a["Close"] > 0).all()
    assert a["Ticker"].nunique() == 2 and len(a) == 240


def test_load_price_cache_missing_and_corrupt(tmp_path):
    assert len(SELF.load_price_cache(str(tmp_path / "nope.csv"))) == 0
    bad = tmp_path / "bad.csv"
    bad.write_text("this,is\nnot,prices\n")
    assert len(SELF.load_price_cache(str(bad))) == 0


# ------------------------------------------------------------- precompute
def test_precompute_forward_columns_are_shifts():
    raw = _bars("X", list(np.linspace(100, 140, 80)))
    data = SELF.precompute(raw)
    for k in range(1, SELF._max_hold() + 1):
        np.testing.assert_allclose(data[f"C{k}"].values[:-k], raw["Close"].values[k:])
        np.testing.assert_allclose(data[f"O{k}"].values[:-k], raw["Open"].values[k:])


def test_precompute_entry_is_next_open():
    raw = _bars("X", list(np.linspace(100, 120, 40)))
    data = SELF.precompute(raw)
    np.testing.assert_allclose(data["O1"].values[:-1], raw["Open"].values[1:])


def test_precompute_empty_raises():
    with pytest.raises(ValueError):
        SELF.precompute(pd.DataFrame(columns=SELF.PRICE_COLUMNS))


def test_breadth_is_float_and_bounded():
    data = SELF.precompute(_multi(3, 140, seed=2))
    b = data["Breadth"].dropna()
    assert len(b) and b.between(0, 1).all() and b.dtype == float


def test_tradable_respects_price_and_turnover():
    old_t, old_p = SELF.MIN_TURNOVER_THB, SELF.MIN_PRICE_THB
    try:
        SELF.MIN_TURNOVER_THB, SELF.MIN_PRICE_THB = 1e9, 1.0
        data = SELF.precompute(_bars("X", [100.0] * 40, vol=1000.0))
        assert data["Tradable"].max() == 0.0            # turnover ต่ำ -> เทรดไม่ได้
        SELF.MIN_TURNOVER_THB = 0.0
        data2 = SELF.precompute(_bars("Y", [0.5] * 40, vol=1e9))
        assert data2["Tradable"].max() == 0.0           # ราคาต่ำกว่าขั้นต่ำ -> เทรดไม่ได้
    finally:
        SELF.MIN_TURNOVER_THB, SELF.MIN_PRICE_THB = old_t, old_p


def test_build_cache_has_arrays_and_fwd_valid():
    c = SELF.build_cache(SELF.precompute(_multi(2, 120)))
    assert c["_n"] == 240 and c["Close"].dtype == float
    assert set(c["fwd_valid"]) == set(range(1, SELF._max_hold() + 1))


# ------------------------------------------------------------ entry signals
def test_all_ten_families_return_bool_masks():
    data = SELF.precompute(_multi(4, 300, seed=7))
    c = SELF.build_cache(data)
    for fam in range(10):
        m = SELF.entry_mask(c, fam, SELF.PARAM_DEFAULTS)
        assert m.dtype == bool and len(m) == len(data)


def test_unknown_family_raises():
    c = SELF.build_cache(SELF.precompute(_multi(2, 120)))
    with pytest.raises(ValueError):
        SELF.entry_mask(c, 99, SELF.PARAM_DEFAULTS)


def test_breakout_fires_on_new_high():
    c = SELF.build_cache(SELF.precompute(_bars("X", list(np.linspace(100, 200, 90)))))
    assert SELF.entry_mask(c, 1, {**SELF.PARAM_DEFAULTS, "donchian_n": 10}).sum() > 0


def test_mean_reversion_fires_on_dip():
    closes = [100.0] * 40 + [95, 90, 86, 83, 80] + [82.0] * 20
    c = SELF.build_cache(SELF.precompute(_bars("X", closes)))
    p = {**SELF.PARAM_DEFAULTS, "rsi_period": 7, "rsi_threshold": 40,
         "bb_period": 10, "bb_std": 1.5}
    assert SELF.entry_mask(c, 0, p).sum() > 0


def test_stoch_oversold_fires():
    closes = list(np.linspace(120, 80, 50)) + list(np.linspace(80, 95, 40))
    c = SELF.build_cache(SELF.precompute(_bars("X", closes)))
    assert SELF.entry_mask(c, 4, {**SELF.PARAM_DEFAULTS, "stoch_th": 25}).sum() > 0


def test_gap_down_reversal_fires():
    n = 60
    closes = [100.0] * n
    o = list(closes)
    o[40] = 97.0
    closes[40] = 99.0
    raw = _bars("X", closes, opens=o)
    c = SELF.build_cache(SELF.precompute(raw))
    m = SELF.entry_mask(c, 5, {**SELF.PARAM_DEFAULTS, "gap_pct": 2.0})
    assert m[40] and m.sum() == 1


def test_volspike_breakout_fires():
    closes = list(np.linspace(90, 100, 60))
    vol = np.full(60, 1_000_000.0)
    vol[50] = 5_000_000.0
    raw = _bars("X", closes, vol=vol)
    c = SELF.build_cache(SELF.precompute(raw))
    m = SELF.entry_mask(c, 6, {**SELF.PARAM_DEFAULTS, "donchian_n": 10, "vol_mult": 2.0})
    assert m[50]


def test_inside_bar_break_fires():
    n = 40
    c_ = [100.0] * n
    h = [102.0] * n
    l = [98.0] * n
    h[30], l[30] = 101.0, 99.0            # inside bar
    c_[31] = 101.5                        # ปิดเหนือ high ของ inside bar
    h[31] = 102.0
    raw = _bars("X", c_, highs=h, lows=l, opens=[100.0] * n)
    c = SELF.build_cache(SELF.precompute(raw))
    m = SELF.entry_mask(c, 7, {**SELF.PARAM_DEFAULTS, "require_trend": 0})
    assert m[31]


def test_down_streak_bounce_fires():
    closes = [100.0] * 30 + [99.0, 98.0, 97.0] + [100.0] * 10
    c = SELF.build_cache(SELF.precompute(_bars("X", closes)))
    m = SELF.entry_mask(c, 8, {**SELF.PARAM_DEFAULTS, "streak_n": 3, "require_trend": 0})
    assert m[32] and not m[31]


def test_sma_reclaim_fires():
    closes = list(np.linspace(120, 80, 40)) + [95.0] + [95.0] * 10
    c = SELF.build_cache(SELF.precompute(_bars("X", closes)))
    m = SELF.entry_mask(c, 9, {**SELF.PARAM_DEFAULTS, "sma_n": 20})
    assert m.sum() >= 1


def test_trend_pullback_needs_trend_and_dip():
    closes = list(np.linspace(80, 140, 120)) + [130.0, 125.0, 120.0]
    c = SELF.build_cache(SELF.precompute(_bars("X", closes)))
    p = {**SELF.PARAM_DEFAULTS, "ema_fast": 8, "ema_slow": 26,
         "rsi_period": 7, "rsi_threshold": 40}
    assert SELF.entry_mask(c, 2, p).sum() > 0


def test_filters_only_reduce_signals():
    data = SELF.precompute(_multi(5, 300, seed=11))
    c = SELF.build_cache(data)
    base = SELF.filter_mask(c, 0, 0, 0)
    for a, v, r in [(25, 0, 0), (0, 1, 0), (0, 0, 1), (25, 1, 1)]:
        assert SELF.filter_mask(c, a, v, r).sum() <= base.sum()


def test_signal_mask_respects_segment():
    data = SELF.precompute(_multi(3, 200, seed=4))
    c = SELF.build_cache(data)
    s = _strat(4, stoch_th=25)
    full = SELF.signal_mask(c, s).sum()
    half = np.zeros(len(data), dtype=bool)
    half[: len(data) // 2] = True
    assert SELF.signal_mask(c, s, half).sum() <= full


def test_strictly_non_repainting_all_families():
    """สัญญาณที่แท่ง t ต้องไม่เปลี่ยนเมื่อมีข้อมูลอนาคตมาต่อ (พิสูจน์ครบ 10 family)."""
    rng = np.random.default_rng(42)
    n = 130
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))
    raw = _bars("X", close, opens=close * (1 + rng.normal(0, 0.003, n)),
                highs=close * 1.02, lows=close * 0.98)
    full = SELF.build_cache(SELF.precompute(raw))
    for fam in range(10):
        f_mask = SELF.entry_mask(full, fam, SELF.PARAM_DEFAULTS)
        for t in range(110, n):
            pref = SELF.build_cache(SELF.precompute(raw.iloc[:t + 1].copy()))
            p_mask = SELF.entry_mask(pref, fam, SELF.PARAM_DEFAULTS)
            assert bool(p_mask[-1]) == bool(f_mask[t]), f"repaint fam={fam} t={t}"


# ----------------------------------------------------------- simulation
def _sim_arrays(bars):
    """bars = list ของ (open, high, low, close) ต่อแท่งอนาคต -> dict สำหรับ _simulate."""
    fo = {k + 1: np.array([b[0]], dtype=float) for k, b in enumerate(bars)}
    fh = {k + 1: np.array([b[1]], dtype=float) for k, b in enumerate(bars)}
    fl = {k + 1: np.array([b[2]], dtype=float) for k, b in enumerate(bars)}
    fc = {k + 1: np.array([b[3]], dtype=float) for k, b in enumerate(bars)}
    return fo, fh, fl, fc


def test_simulate_take_profit_exact():
    e = np.array([100.0]); tp = np.array([103.0]); sl = np.array([97.0])
    fo, fh, fl, fc = _sim_arrays([(100, 101, 99, 100), (100, 104, 99.5, 103)])
    o, px, bars = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 2)
    assert o[0] == 1 and px[0] == 103.0 and bars[0] == 2


def test_simulate_stop_loss_exact():
    e = np.array([100.0]); tp = np.array([103.0]); sl = np.array([97.0])
    fo, fh, fl, fc = _sim_arrays([(100, 101, 96.5, 97), (100, 104, 99.5, 103)])
    o, px, bars = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 2)
    assert o[0] == -1 and px[0] == 97.0 and bars[0] == 1


def test_simulate_gap_through_sl_uses_open_price():
    """[แก้บั๊ก สูง] เปิดต่ำกว่า SL -> ต้องออกที่ราคาเปิดจริง (ขาดทุนมากกว่า SL)."""
    e = np.array([100.0]); tp = np.array([103.0]); sl = np.array([97.0])
    fo, fh, fl, fc = _sim_arrays([(100, 101, 98, 99), (90, 92, 89, 91)])
    o, px, bars = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 2)
    assert o[0] == -1 and px[0] == 90.0 and bars[0] == 2      # ไม่ใช่ 97.0


def test_simulate_gap_through_tp_uses_open_price():
    e = np.array([100.0]); tp = np.array([103.0]); sl = np.array([97.0])
    fo, fh, fl, fc = _sim_arrays([(100, 101, 98, 99), (110, 112, 109, 111)])
    o, px, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 2)
    assert o[0] == 1 and px[0] == 110.0


def test_simulate_gap_not_checked_on_entry_bar():
    """แท่งแรก 'ราคาเปิด' คือราคาที่เข้าไม้เอง จึงห้ามนับเป็น gap ทะลุ."""
    e = np.array([100.0]); tp = np.array([101.0]); sl = np.array([99.0])
    fo, fh, fl, fc = _sim_arrays([(100, 100.5, 99.5, 100)])
    o, px, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 1)
    assert o[0] == 0 and px[0] == 100.0                       # time exit ที่ราคาปิด


def test_simulate_tie_policy():
    e = np.array([100.0]); tp = np.array([102.0]); sl = np.array([98.0])
    fo, fh, fl, fc = _sim_arrays([(100, 103, 97, 100)])
    old = SELF.TIE_BREAK_SL_WINS
    try:
        SELF.TIE_BREAK_SL_WINS = True
        o, px, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 1)
        assert o[0] == -1 and px[0] == 98.0
        SELF.TIE_BREAK_SL_WINS = False
        o, px, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 1)
        assert o[0] == 1 and px[0] == 102.0
    finally:
        SELF.TIE_BREAK_SL_WINS = old


def test_simulate_time_exit_at_close():
    e = np.array([100.0]); tp = np.array([120.0]); sl = np.array([80.0])
    fo, fh, fl, fc = _sim_arrays([(100, 101, 99, 100.5), (100, 102, 99, 101.5),
                                  (101, 103, 100, 102.5)])
    o, px, bars = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 3)
    assert o[0] == 0 and px[0] == 102.5 and bars[0] == 3


def test_simulate_skip_tp_on_fill_day():
    e = np.array([100.0]); tp = np.array([101.0]); sl = np.array([90.0])
    fo, fh, fl, fc = _sim_arrays([(100, 200, 99, 100), (100, 100.2, 99, 100)])
    o, _, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 2, skip_tp_day1=True)
    assert o[0] == 0                                          # ห้ามนับ TP วันที่ order ติด
    o2, _, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 2, skip_tp_day1=False)
    assert o2[0] == 1


def test_simulate_sl_still_checked_on_fill_day():
    e = np.array([100.0]); tp = np.array([110.0]); sl = np.array([99.0])
    fo, fh, fl, fc = _sim_arrays([(100, 101, 98, 99)])
    o, px, _ = SELF._simulate(e, tp, sl, fo, fh, fl, fc, 1, skip_tp_day1=True)
    assert o[0] == -1 and px[0] == 99.0


def test_metrics_win_means_net_positive_not_tp_touch():
    """[สำคัญ] TP เล็กกว่าค่าคอม -> แตะ TP แต่ 'ขาดทุนจริง' ต้องไม่ถูกนับเป็นชนะ."""
    net = np.array([0.4 - SELF.FRICTION_PCT])
    m = SELF._metrics(net, np.array([1]), np.array([1], dtype=np.int8), 1)
    assert m["n_tp"] == 1 and m["wins"] == 0 and m["win_rate"] == 0.0


def test_metrics_net_per_day_math():
    net = np.array([3.0, 1.0])
    m = SELF._metrics(net, np.array([2, 2]), np.array([1, 1], dtype=np.int8), 2)
    assert m["avg_net"] == 2.0 and m["avg_hold"] == 2.0 and m["net_per_day"] == 1.0


def test_metrics_profit_factor_and_extremes():
    net = np.array([2.0, -1.0, 4.0])
    m = SELF._metrics(net, np.array([1, 1, 1]), np.array([1, -1, 1], dtype=np.int8), 3)
    assert m["profit_factor"] == 6.0 and m["best"] == 4.0 and m["worst"] == -1.0


def test_evaluate_percent_exit_end_to_end():
    closes = [100.0] * 40 + [95, 90, 86] + list(np.linspace(88, 130, 40))
    c = SELF.build_cache(SELF.precompute(_bars("X", closes)))
    s = _strat(0, rsi_period=7, rsi_threshold=40, bb_period=10, bb_std=1.5,
               tp_val=3.0, sl_val=5.0, hold_days=5)
    r = SELF.evaluate(c, s)
    assert r is not None and 0 <= r["win_rate"] <= 100 and r["n_trades"] >= 1


def test_evaluate_no_signal_returns_none():
    c = SELF.build_cache(SELF.precompute(_bars("X", [100.0] * 80)))
    assert SELF.evaluate(c, _strat(0, rsi_threshold=10, bb_std=2.5)) is None


def test_evaluate_atr_mode_zero_volatility_no_fake_win():
    c = SELF.build_cache(SELF.precompute(_bars("X", [100.0] * 80, highs=[100.0] * 80,
                                                     lows=[100.0] * 80, opens=[100.0] * 80)))
    s = _strat(0, rsi_threshold=60, exit_mode=1, tp_val=2.0, sl_val=2.0)
    assert SELF.evaluate(c, s) is None


def test_evaluate_hold_beyond_precompute_raises():
    c = SELF.build_cache(SELF.precompute(_bars("X", [100.0] * 60)))
    with pytest.raises(ValueError):
        SELF.evaluate(c, _strat(0, hold_days=SELF._max_hold() + 1))


def test_evaluate_zero_price_bar_does_not_corrupt_stats():
    import warnings as _w
    closes = [100.0] * 40 + [90.0] + [100.0] * 20
    raw = _bars("X", closes)
    raw.loc[41, ["Open", "High", "Low", "Close"]] = [1e-12, 1e-12, 1e-12, 1e-12]
    c = SELF.build_cache(SELF.precompute(raw))
    s = _strat(0, rsi_period=7, rsi_threshold=45, bb_period=10, bb_std=1.5)
    with _w.catch_warnings():
        _w.simplefilter("error")
        r = SELF.evaluate(c, s)
    assert r is None or (np.isfinite(r["avg_net"]) and np.isfinite(r["median_net"]))


def test_evaluate_limit_entry_not_filled():
    closes = [100.0] * 40 + [90.0] + [100.0] * 20
    raw = _bars("X", closes, lows=[99.9] * 61)
    raw.loc[40, "Low"] = 89.9
    c = SELF.build_cache(SELF.precompute(raw))
    s = _strat(0, rsi_period=7, rsi_threshold=45, bb_period=10, bb_std=1.5, entry_mode=1)
    r = SELF.evaluate(c, s)
    assert r is None or r["n_trades"] < r["n_signals"]


# ----------------------------------------------------------------- search
def test_count_search_space_matches_manual():
    n_filt = len(SELF.SPACE["adx_min"]) * len(SELF.SPACE["vol_filter"]) * \
        len(SELF.SPACE["regime_filter"])
    n_exec = len(SELF.SPACE["entry_mode"]) * len(SELF.SPACE["hold_days"]) * \
        len(SELF.EXIT_COMBOS)
    manual = 0
    for fam, keys in SELF.FAMILY_PARAMS.items():
        e = 1
        for k in keys:
            e *= len(SELF.SPACE[k])
        manual += e * n_filt * n_exec
    assert SELF.count_search_space() == manual > 100_000


def test_every_family_has_params_and_name():
    for fam in range(10):
        assert fam in SELF.FAMILY_PARAMS and fam in SELF.FAMILY_NAME
        for k in SELF.FAMILY_PARAMS[fam]:
            assert k in SELF.SPACE and k in SELF.PARAM_DEFAULTS


def test_make_strategy_fills_defaults_and_types():
    s = SELF.make_strategy(1, {"donchian_n": 20}, 0, 2.0, 3.0, 2, 25, 1, 0, 1)
    assert set(s) == set(SELF.PARAM_KEYS)
    assert s["donchian_n"] == 20 and s["adx_min"] == 25 and s["entry_mode"] == 1


def test_strategy_key_ignores_unused_params():
    a = SELF.make_strategy(1, {"donchian_n": 20}, 0, 2.0, 3.0, 2, 0, 0, 0, 0)
    b = dict(a)
    b["rsi_threshold"] = 999          # family 1 ไม่ใช้ RSI -> ต้องถือว่าเป็นสมการเดียวกัน
    assert SELF.strategy_key(a) == SELF.strategy_key(b)


def test_strategy_label_readable():
    s = SELF.make_strategy(0, dict(rsi_period=7, rsi_threshold=30, bb_period=10,
                                      bb_std=1.5), 0, 2.0, 3.0, 3, 0, 0, 0, 0)
    lab = SELF.strategy_label(s)
    assert "MR_RSI_BB" in lab and "hold=3d" in lab and "market" in lab


def test_dedup_candidates_removes_identical_results():
    base = SELF.make_strategy(0, dict(rsi_period=7, rsi_threshold=30, bb_period=10,
                                         bb_std=1.5), 0, 2.0, 3.0, 3, 0, 0, 0, 0)
    rows = []
    for i in range(10):
        r = dict(base)
        r.update(n_trades=50, wins=40, avg_net=1.0, avg_hold=2.0, sl_val=float(i))
        rows.append(r)
    assert len(SELF._dedup_candidates(rows, keep_top=10)) == 1


def test_dedup_candidates_caps_per_group():
    base = SELF.make_strategy(0, dict(rsi_period=7, rsi_threshold=30, bb_period=10,
                                         bb_std=1.5), 0, 2.0, 3.0, 3, 0, 0, 0, 0)
    rows = []
    for i in range(20):
        r = dict(base)
        r.update(n_trades=50 + i, wins=40, avg_net=1.0, avg_hold=2.0)
        rows.append(r)
    out = SELF._dedup_candidates(rows, keep_top=20, max_per_group=4)
    assert len(out) == 4


def test_run_search_returns_sorted_and_bounded():
    data = SELF.precompute(_multi(4, 320, seed=21))
    c = SELF.build_cache(data)
    seg = np.ones(len(data), dtype=bool)
    rows = SELF.run_search(c, seg, min_trades=10, keep_top=8, families=[0, 4],
                              progress=False)
    assert len(rows) <= 8
    scores = [SELF._score(r) for r in rows]
    assert scores == sorted(scores, reverse=True)
    for r in rows:
        assert r["win_rate"] >= SELF.FLOOR_WIN_RATE and r["avg_net"] > 0


def test_run_search_finds_planted_edge():
    """ปลูก edge ชัด ๆ: ทุกครั้งที่ RSI ต่ำ ราคาจะเด้งขึ้น -> ระบบต้องหาเจอ."""
    rng = np.random.default_rng(9)
    closes, price = [], 100.0
    for i in range(400):
        if i % 20 in (0, 1, 2, 3):
            price *= 0.985                   # ย่อลงเป็นจังหวะ
        elif i % 20 in (4, 5, 6):
            price *= 1.02                    # แล้วเด้งแรง
        else:
            price *= 1 + rng.normal(0, 0.004)
        closes.append(price)
    raw = _bars("P", closes, highs=np.array(closes) * 1.012, lows=np.array(closes) * 0.995)
    c = SELF.build_cache(SELF.precompute(raw))
    seg = np.ones(c["_n"], dtype=bool)
    rows = SELF.run_search(c, seg, min_trades=10, keep_top=5, families=[0, 4],
                              progress=False)
    assert rows and rows[0]["win_rate"] >= 70 and rows[0]["avg_net"] > 0


def test_fast_mode_shrinks_space():
    import copy
    old_space = copy.deepcopy(SELF.SPACE)
    old_exit = list(SELF.EXIT_COMBOS)
    big = SELF.count_search_space()
    try:
        SELF.fast_mode(True)
        assert SELF.count_search_space() < big
    finally:
        SELF.SPACE.clear()
        SELF.SPACE.update(old_space)
        SELF.EXIT_COMBOS = old_exit


# ------------------------------------------------------------- validation
def test_make_segments_non_overlapping_with_embargo():
    data = SELF.precompute(_multi(3, 300, seed=6))
    s = SELF.make_segments(data)
    assert not (s["is_"] & s["oos1"]).any()
    assert not (s["oos1"] & s["oos2"]).any()
    assert not (s["is_"] & s["oos2"]).any()
    d = pd.to_datetime(data["Date"])
    assert d[s["is_"]].max() < s["cut1"]                     # embargo กันชนจริง
    assert d[s["oos1"]].max() < s["cut2"]
    assert (s["oos"] == (s["oos1"] | s["oos2"])).all()


def test_make_segments_too_short_raises():
    with pytest.raises(ValueError):
        SELF.make_segments(SELF.precompute(_bars("X", [100.0] * 30)))


def test_grade_strategy_levels():
    good = dict(n_trades=50, win_rate=85.0, net_per_day=3.0, avg_net=3.0, wilson_lb=75.0)
    mid = dict(n_trades=50, win_rate=62.0, net_per_day=0.5, avg_net=1.0, wilson_lb=55.0)
    bad = dict(n_trades=50, win_rate=40.0, net_per_day=-0.5, avg_net=-1.0, wilson_lb=30.0)
    thin = dict(n_trades=3, win_rate=100.0, net_per_day=9.0, avg_net=9.0, wilson_lb=40.0)
    assert SELF.grade_strategy(good, good, good) == "A"
    assert SELF.grade_strategy(mid, mid, mid) == "B"
    assert SELF.grade_strategy(bad, bad, bad) == "-"
    assert SELF.grade_strategy(thin, thin, thin) == "-"     # ไม้น้อยเกินไป
    assert SELF.grade_strategy(good, bad, good) == "-"      # ต้องผ่านทั้ง 2 ช่วง
    assert SELF.grade_strategy(None, good, good) == "-"


def test_validate_produces_grades_and_sorting():
    data = SELF.precompute(_multi(5, 400, seed=13))
    c = SELF.build_cache(data)
    segs = SELF.make_segments(data)
    cands = SELF.run_search(c, segs["is_"], min_trades=10, keep_top=10,
                               families=[0, 4], progress=False)
    conf = SELF.validate(c, cands, segs, progress=False)
    assert len(conf) == len(cands)
    assert {"grade", "label", "oos_wr", "oos_npd", "oos_score"} <= set(conf.columns)
    ranks = [{"A": 0, "B": 1, "-": 2}[g] for g in conf["grade"]]
    assert ranks == sorted(ranks)


def test_validate_empty_candidates():
    data = SELF.precompute(_multi(2, 200))
    c = SELF.build_cache(data)
    assert len(SELF.validate(c, [], SELF.make_segments(data), progress=False)) == 0


# -------------------------------------------------------------- portfolio
def _port_setup(nt=4, n=300, seed=15):
    raw = _multi(nt, n, seed=seed)
    data = SELF.precompute(raw)
    return data, SELF.build_cache(data)


def test_portfolio_respects_max_positions_and_cash():
    data, c = _port_setup()
    s = _strat(4, stoch_th=25, hold_days=5, tp_val=3.0, sl_val=3.0)
    p = SELF.portfolio_backtest(data, c, s, capital=100_000, max_positions=2)
    assert p["equity"]["n_open"].max() <= 2
    assert (p["equity"]["equity"] > 0).all()


def test_portfolio_equity_covers_segment_only():
    data, c = _port_setup()
    segs = SELF.make_segments(data)
    s = _strat(4, stoch_th=25)
    p = SELF.portfolio_backtest(data, c, s, seg=segs["oos2"], capital=100_000)
    n_seg_days = int(pd.to_datetime(data.loc[segs["oos2"], "Date"]).nunique())
    assert n_seg_days <= p["n_days"] <= n_seg_days + s["hold_days"] + 2


def test_portfolio_is_deterministic():
    data, c = _port_setup()
    s = _strat(0, rsi_threshold=40, hold_days=3)
    a = SELF.portfolio_backtest(data, c, s, capital=200_000)
    b = SELF.portfolio_backtest(data, c, s, capital=200_000)
    assert a["final_equity"] == b["final_equity"] and a["n_trades"] == b["n_trades"]


def test_portfolio_total_return_matches_equity():
    data, c = _port_setup()
    s = _strat(4, stoch_th=25, hold_days=2)
    p = SELF.portfolio_backtest(data, c, s, capital=150_000)
    expect = (p["equity"]["equity"].iloc[-1] / 150_000 - 1) * 100
    assert abs(p["total_return_pct"] - expect) < 0.02


def test_portfolio_hold_one_day_exits_same_bar():
    data, c = _port_setup()
    s = _strat(4, stoch_th=30, hold_days=1, tp_val=50.0, sl_val=50.0)
    p = SELF.portfolio_backtest(data, c, s, capital=500_000)
    if p["n_trades"]:
        assert set(p["trades"]["Bars"].unique()) == {1}


def test_portfolio_no_signal_keeps_capital_flat():
    data, c = _port_setup()
    s = _strat(0, rsi_threshold=1, bb_std=2.5)       # แทบไม่มีทางยิง
    p = SELF.portfolio_backtest(data, c, s, capital=50_000)
    assert p["n_trades"] == 0 and p["final_equity"] == 50_000
    assert p["total_return_pct"] == 0.0


def test_portfolio_invalid_config_raises():
    data, c = _port_setup(2, 120)
    with pytest.raises(ValueError):
        SELF.portfolio_backtest(data, c, _strat(0), capital=0)
    with pytest.raises(ValueError):
        SELF.portfolio_backtest(data, c, _strat(0), max_positions=0)


def test_portfolio_trade_pnl_sign_matches_net():
    data, c = _port_setup(5, 400, seed=31)
    s = _strat(4, stoch_th=25, hold_days=3, tp_val=2.0, sl_val=2.0)
    p = SELF.portfolio_backtest(data, c, s, capital=300_000)
    if p["n_trades"]:
        t = p["trades"]
        assert ((t["NetPct"] > 0) == (t["PnlTHB"] > 0)).all()


def test_portfolio_gap_through_stop_recorded():
    """หุ้นเปิด gap ลงทะลุ SL -> ต้องบันทึกชนิด SL_GAP และขาดทุนมากกว่า SL ที่ตั้งไว้."""
    closes = [100.0] * 40 + [92.0] + [70.0] + [70.0] * 10
    raw = _bars("G", closes)
    raw.loc[41, ["Open", "High", "Low", "Close"]] = [100.0, 100.5, 99.0, 100.0]
    raw.loc[42, ["Open", "High", "Low", "Close"]] = [80.0, 82.0, 79.0, 80.0]
    data = SELF.precompute(raw)
    c = SELF.build_cache(data)
    s = _strat(0, rsi_period=7, rsi_threshold=45, bb_period=10, bb_std=1.5,
               hold_days=5, tp_val=5.0, sl_val=5.0)
    p = SELF.portfolio_backtest(data, c, s, capital=200_000, max_positions=1)
    assert p["n_trades"] >= 1
    row = p["trades"].iloc[0]
    assert row["Kind"] == "SL_GAP" and row["NetPct"] < -5.0


# ----------------------------------------------------------- verdict agent
def _confirmed_from(strat: dict, n=5, grade="B", **over):
    rows = []
    for i in range(n):
        r = dict(strat)
        r.update(grade=grade, label=SELF.strategy_label(strat),
                 strategy=SELF.FAMILY_NAME[int(strat["entry_family"])],
                 oos_n=40, oos_wr=75.0 - i, oos_wlb=60.0, oos_net=1.5, oos_npd=0.5,
                 oos_score=0.4, is_n=100)
        r.update(over)
        rows.append(r)
    return pd.DataFrame(rows)


def _always_fire_data(price=10.0, n=120, ticker="CHEAP"):
    """ราคาที่ทำให้ family 8 (ปิดลบติดกัน) ยิงที่แท่งสุดท้ายแน่นอน."""
    closes = [price] * (n - 4) + [price * 0.99, price * 0.98, price * 0.97, price * 0.96]
    raw = _bars(ticker, closes)
    data = SELF.precompute(raw)
    return data, SELF.build_cache(data)


def test_verdict_no_confirmed_is_no_trade():
    data, c = _always_fire_data()
    vr = SELF.DailyVerdictAgent().decide(data, c, pd.DataFrame())
    assert vr.k_used == 0 and not vr.orders and "ไม่เข้า" in vr.overall


def test_verdict_all_rejected_is_no_trade():
    data, c = _always_fire_data()
    conf = _confirmed_from(_strat(8, streak_n=3), grade="-")
    vr = SELF.DailyVerdictAgent().decide(data, c, conf)
    assert not vr.orders and "ไม่เข้า" in vr.overall


def test_verdict_consensus_trade():
    data, c = _always_fire_data()
    conf = _confirmed_from(_strat(8, streak_n=3, hold_days=3, tp_val=2.0, sl_val=2.0))
    vr = SELF.DailyVerdictAgent(top_k=5, min_agree=2).decide(data, c, conf)
    assert len(vr.orders) == 1
    o = vr.orders[0]
    assert o.ticker == "CHEAP" and o.action.startswith("เข้า")
    assert o.agree_count == 5 and o.lots >= 1 and o.shares == o.lots * SELF.BOARD_LOT
    assert o.sell_tp > o.buy_ref > o.stop_sl


def test_verdict_budget_blocks_expensive_stock():
    data, c = _always_fire_data(price=5000.0, ticker="PRICY")
    conf = _confirmed_from(_strat(8, streak_n=3))
    vr = SELF.DailyVerdictAgent(budget_thb=10_000).decide(data, c, conf)
    assert len(vr.orders) == 1 and vr.orders[0].action.startswith("เฝ้าดู")
    assert "งบไม่พอ" in vr.orders[0].reasons


def test_verdict_respects_max_orders():
    parts = [_always_fire_data(price=10.0 + i, ticker=f"S{i}")[0] for i in range(4)]
    data = pd.concat(parts, ignore_index=True)
    data["Breadth"] = data["Breadth"].fillna(1.0)
    c = SELF.build_cache(data)
    conf = _confirmed_from(_strat(8, streak_n=3))
    vr = SELF.DailyVerdictAgent(max_orders=2, min_agree=1).decide(data, c, conf)
    assert sum(1 for o in vr.orders if o.action.startswith("เข้า")) == 2
    assert any("เกินจำนวนไม้สูงสุด" in o.reasons for o in vr.orders)


def test_verdict_min_agree_not_met_is_watch():
    data, c = _always_fire_data()
    conf = _confirmed_from(_strat(8, streak_n=3), n=1)
    conf = pd.concat([conf, _confirmed_from(_strat(1, donchian_n=40), n=4)], ignore_index=True)
    vr = SELF.DailyVerdictAgent(top_k=5, min_agree=3).decide(data, c, conf)
    assert vr.orders and all(o.action.startswith("เฝ้าดู") for o in vr.orders)


def test_verdict_is_deterministic():
    data, c = _always_fire_data()
    conf = _confirmed_from(_strat(8, streak_n=3))
    a = SELF.DailyVerdictAgent().decide(data, c, conf)
    b = SELF.DailyVerdictAgent().decide(data, c, conf)
    assert a == b


def test_verdict_invalid_config_raises():
    with pytest.raises(ValueError):
        SELF.DailyVerdictAgent(top_k=0)
    with pytest.raises(ValueError):
        SELF.DailyVerdictAgent(min_agree=0)
    with pytest.raises(ValueError):
        SELF.DailyVerdictAgent(max_orders=0)


def test_coerce_strategy_preserves_floats():
    """[regression บั๊กสูง] cast เป็น int ทั้งหมด จะปัด 2.5 -> 2 เงียบ ๆ = คนละสมการ."""
    s = SELF._coerce_strategy({**SELF.PARAM_DEFAULTS, "tp_val": 2.5, "bb_std": 1.5,
                                  "hold_days": 3.0, "gap_pct": 1.5})
    assert s["tp_val"] == 2.5 and s["bb_std"] == 1.5 and s["gap_pct"] == 1.5
    assert isinstance(s["hold_days"], int) and s["hold_days"] == 3


def test_coerce_strategy_handles_junk():
    s = SELF._coerce_strategy({"entry_family": "2", "hold_days": np.nan,
                                  "tp_val": None, "sl_val": float("inf")})
    assert s["entry_family"] == 2
    assert s["hold_days"] == SELF.PARAM_DEFAULTS["hold_days"]
    assert np.isfinite(s["tp_val"]) and np.isfinite(s["sl_val"])


# -------------------------------------------------------------- journal
def _jrow(**over):
    base = dict(signal_date="2026-01-02", ticker="X", strategy="MR", grade="B",
                order_type="Market@Open", entry_mode=0, buy_ref=100.0, sell_tp=105.0,
                stop_sl=95.0, tp_pct=5.0, sl_pct=5.0, hold_days=3,
                action="เข้า (TRADE)", status="PENDING", fill_price=np.nan,
                exit_date=np.nan, exit_price=np.nan, net_return_pct=np.nan,
                expected_wr=75.0, expected_npd=0.5, run_date="2026-01-02")
    base.update(over)
    return pd.DataFrame([base], columns=SELF.JOURNAL_COLUMNS)


def _pf(ticker, dates, o, h, l, c):
    return pd.DataFrame({"Ticker": ticker, "Date": pd.to_datetime(dates), "Open": o,
                         "High": h, "Low": l, "Close": c, "Volume": 1e6})


def test_load_journal_missing_file(tmp_path):
    j = SELF.load_journal(str(tmp_path / "none.csv"))
    assert list(j.columns) == SELF.JOURNAL_COLUMNS and len(j) == 0


def test_load_journal_adds_missing_columns(tmp_path):
    p = tmp_path / "old.csv"
    pd.DataFrame([{"signal_date": "2026-01-02", "ticker": "X", "status": "PENDING"}]).to_csv(
        p, index=False)
    j = SELF.load_journal(str(p))
    assert list(j.columns) == SELF.JOURNAL_COLUMNS and len(j) == 1


def test_load_journal_corrupt_file(tmp_path):
    p = tmp_path / "corrupt.csv"
    p.write_text("")
    assert len(SELF.load_journal(str(p))) == 0


def test_resolve_market_take_profit():
    raw = _pf("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
              o=[99, 100, 101], h=[99, 106, 101], l=[99, 98, 100], c=[99, 104, 101])
    j = SELF.resolve_journal(_jrow(), raw)
    r = j.iloc[0]
    assert r["status"] == "FILLED_TP" and r["fill_price"] == 100.0
    assert r["net_return_pct"] == round(5 - SELF.FRICTION_PCT, 2)


def test_resolve_gap_through_stop_uses_open():
    """[แก้บั๊ก สูง] วันที่ 2 เปิด 80 (ต่ำกว่า SL 95) -> ต้องคิดที่ 80 ไม่ใช่ 95."""
    raw = _pf("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
              o=[99, 100, 80], h=[99, 101, 81], l=[99, 99, 78], c=[99, 100, 79])
    j = SELF.resolve_journal(_jrow(), raw)
    r = j.iloc[0]
    assert r["status"] == "FILLED_SL" and r["exit_price"] == 80.0
    assert r["net_return_pct"] < -19


def test_resolve_recomputes_levels_from_actual_fill():
    """เปิดจริง 90 (ไม่ใช่ 100 ที่อ้างอิงไว้) -> TP ต้องเป็น 94.5 (+5%) ไม่ใช่ 105."""
    raw = _pf("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
              o=[99, 90, 94], h=[99, 92, 95], l=[99, 89, 93], c=[99, 91, 94.6])
    j = SELF.resolve_journal(_jrow(), raw)
    r = j.iloc[0]
    assert r["fill_price"] == 90.0 and r["status"] == "FILLED_TP"
    assert abs(float(r["exit_price"]) - 94.5) < 1e-6


def test_resolve_limit_not_filled():
    raw = _pf("X", ["2026-01-02", "2026-01-05"], o=[99, 100], h=[99, 101],
              l=[99, 96], c=[99, 100])
    j = SELF.resolve_journal(_jrow(entry_mode=1, buy_ref=95.0), raw)
    assert j.iloc[0]["status"] == "NOT_FILLED"


def test_resolve_limit_skips_tp_on_fill_day():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    raw = _pf("X", dates, o=[99, 96, 96, 96], h=[99, 200, 97, 97],
              l=[99, 90, 95.5, 95.5], c=[99, 96, 96, 97])
    j = SELF.resolve_journal(_jrow(entry_mode=1, buy_ref=95.0, tp_pct=5.0, sl_pct=20.0), raw)
    r = j.iloc[0]
    assert r["status"] == "FILLED_TIME" and r["fill_price"] == 95.0 and r["exit_price"] == 97.0


def test_resolve_pending_when_not_enough_bars():
    raw = _pf("X", ["2026-01-02", "2026-01-05"], o=[99, 100], h=[99, 101],
              l=[99, 99], c=[99, 100])
    j = SELF.resolve_journal(_jrow(tp_pct=50.0, sl_pct=50.0), raw)
    assert j.iloc[0]["status"] == "PENDING" and j.iloc[0]["fill_price"] == 100.0


def test_resolve_no_data_ticker():
    raw = _pf("OTHER", ["2026-01-05"], o=[10], h=[10], l=[10], c=[10])
    assert SELF.resolve_journal(_jrow(ticker="GONE"), raw).iloc[0]["status"] == "NO_DATA"


def test_resolve_legacy_row_missing_fields_no_crash():
    row = _jrow()
    row.loc[0, ["entry_mode", "hold_days", "tp_pct", "sl_pct"]] = np.nan
    raw = _pf("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
              o=[99, 100, 101], h=[99, 106, 101], l=[99, 98, 100], c=[99, 104, 101])
    j = SELF.resolve_journal(row, raw)
    assert j.iloc[0]["status"] == "FILLED_TP"      # ใช้ระดับ TP/SL ที่บันทึกไว้แทน


def test_resolve_broken_levels_stays_pending():
    row = _jrow(sell_tp=np.nan, stop_sl=np.nan, tp_pct=np.nan, sl_pct=np.nan)
    raw = _pf("X", ["2026-01-02", "2026-01-05"], o=[99, 100], h=[99, 106],
              l=[99, 98], c=[99, 104])
    assert SELF.resolve_journal(row, raw).iloc[0]["status"] == "PENDING"


def test_resolve_bad_signal_date_no_crash():
    row = _jrow(signal_date="ไม่ใช่วันที่")
    raw = _pf("X", ["2026-01-05"], o=[100], h=[106], l=[98], c=[104])
    assert SELF.resolve_journal(row, raw).iloc[0]["status"] == "NO_DATA"


def test_resolve_empty_journal_and_empty_prices():
    empty = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    assert len(SELF.resolve_journal(empty, _pf("X", ["2026-01-02"], [1], [1], [1], [1]))) == 0
    j = SELF.resolve_journal(_jrow(), pd.DataFrame(columns=SELF.PRICE_COLUMNS))
    assert j.iloc[0]["status"] == "PENDING"


def test_resolve_all_nan_status_column_no_lossy_crash():
    """[regression บั๊กครัช] คอลัมน์ที่เป็น NaN ล้วนจาก CSV จะเป็น float64 ->
    เขียน string ลงไปแล้ว pandas โยน LossySetitemError."""
    row = _jrow()
    row["exit_date"] = np.nan
    row["exit_date"] = row["exit_date"].astype(float)
    raw = _pf("X", ["2026-01-02", "2026-01-05", "2026-01-06"],
              o=[99, 100, 101], h=[99, 106, 101], l=[99, 98, 100], c=[99, 104, 101])
    j = SELF.resolve_journal(row, raw)
    assert j.iloc[0]["exit_date"] == "2026-01-05"


def test_journal_stats_math():
    rows = pd.concat([
        _jrow(status="FILLED_TP", net_return_pct=4.49),
        _jrow(ticker="B", status="FILLED_TP", net_return_pct=4.49),
        _jrow(ticker="C", status="FILLED_SL", net_return_pct=-5.51),
        _jrow(ticker="D", status="FILLED_TIME", net_return_pct=0.5),
        _jrow(ticker="E", status="NOT_FILLED"),
        _jrow(ticker="F", status="PENDING"),
    ], ignore_index=True)
    s = SELF.journal_stats(rows)
    assert s["n_orders"] == 6 and s["n_pending"] == 1 and s["n_not_filled"] == 1
    assert s["n_resolved"] == 4 and s["wins"] == 3
    assert s["realized_wr"] == 75.0
    assert s["realized_avg_net"] == round(np.mean([4.49, 4.49, -5.51, 0.5]), 2)
    assert s["cum_net"] == round(4.49 + 4.49 - 5.51 + 0.5, 2)


def test_journal_stats_empty():
    assert SELF.journal_stats(pd.DataFrame(columns=SELF.JOURNAL_COLUMNS))["n_orders"] == 0


def test_append_new_orders_idempotent_and_carries_fields():
    o = SELF.TickerOrder(
        ticker="X", action="เข้า (TRADE)", agree_count=3, of_k=5, grade="B",
        strategy="lbl", order_type="Limit -1.0% (ตั้งซื้อรอ)", buy_ref=9.9, sell_tp=10.4,
        stop_sl=9.4, tp_pct=5.0, sl_pct=5.0, lots=10, shares=1000, cost_thb=9900.0,
        budget_ok=True, hold_days=5, entry_mode=1, exit_mode=0, tp_val=5.0, sl_val=5.0,
        expected_wr=70.0, expected_npd=0.4, expected_wlb=60.0, reasons="-")
    watch = SELF.TickerOrder(**{**asdict(o), "ticker": "W", "action": "เฝ้าดู (WATCH)"})
    vr = SELF.VerdictReport("เข้า 1 ตัว", "B", 5, "2026-01-02", (o, watch))
    j0 = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    j1 = SELF.append_new_orders(j0, vr, "2026-01-02")
    j2 = SELF.append_new_orders(j1, vr, "2026-01-02")
    assert len(j1) == 1 and len(j2) == 1                 # เฉพาะ TRADE และไม่ซ้ำ
    assert j1.iloc[0]["hold_days"] == 5 and j1.iloc[0]["entry_mode"] == 1
    assert j1.iloc[0]["tp_pct"] == 5.0 and j1.iloc[0]["ticker"] == "X"


# ------------------------------------------------------------- dashboard
def _run_info(**over):
    d = dict(run_ts="2026-07-25 18:30", last_bar="2026-07-24", universe="SET50",
             n_tickers=50, demo=False, grade="B", n_grade_a=0, n_grade_b=3,
             n_space=565_248, best_wr=68.0, best_npd=0.42, honest_note="ไม่ถึงเป้า")
    d.update(over)
    return d


def _demo_order(**over):
    base = dict(ticker="DEMO", action="เข้า (TRADE)", agree_count=3, of_k=5, grade="B",
                strategy="lbl", order_type="Market@Open (ตั้งซื้อราคาเปิด)", buy_ref=9.8,
                sell_tp=10.3, stop_sl=9.3, tp_pct=5.0, sl_pct=5.0, lots=10, shares=1000,
                cost_thb=9800.0, budget_ok=True, hold_days=3, entry_mode=0, exit_mode=0,
                tp_val=5.0, sl_val=5.0, expected_wr=70.0, expected_npd=0.4,
                expected_wlb=60.0, reasons="-")
    base.update(over)
    return SELF.TickerOrder(**base)


def test_dashboard_html_with_theme_and_order():
    vr = SELF.VerdictReport("เข้า 1 ตัว", "B", 5, "2026-07-24", (_demo_order(),))
    j = _jrow(status="FILLED_TP", net_return_pct=4.49, exit_date="2026-07-23")
    html = SELF.generate_dashboard(_run_info(), SELF.journal_stats(j), j, vr,
                                      pd.DataFrame())
    assert html.startswith("<!DOCTYPE html")
    assert "#D97757" in html and "#FAF9F5" in html
    assert "DEMO" in html and "เข้า 1 ตัว" in html and "4.49" in html


def test_dashboard_empty_state_no_crash():
    vr = SELF.VerdictReport("ไม่เข้า (NO_TRADE)", "-", 0, "2026-07-24", tuple())
    empty = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    html = SELF.generate_dashboard(_run_info(grade="-"), SELF.journal_stats(empty),
                                      empty, vr, pd.DataFrame())
    assert "ยังไม่มีประวัติ" in html and "สมุดบันทึกว่าง" in html
    assert "ไม่มีคำสั่งเข้า" in html and "chart.js" not in html.lower()


def test_dashboard_grade_badges():
    empty = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    vr = SELF.VerdictReport("-", "-", 0, "2026-07-24", tuple())
    for g, txt in (("A", "ถึงเป้า"), ("B", "ไม่ถึงเป้า"), ("-", "ไม่ผ่าน")):
        html = SELF.generate_dashboard(_run_info(grade=g), SELF.journal_stats(empty),
                                          empty, vr, pd.DataFrame())
        assert txt in html


def test_dashboard_demo_warning_chip():
    empty = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    vr = SELF.VerdictReport("-", "-", 0, "2026-07-24", tuple())
    html = SELF.generate_dashboard(_run_info(demo=True), SELF.journal_stats(empty),
                                      empty, vr, pd.DataFrame())
    assert "ข้อมูลสังเคราะห์" in html


def test_dashboard_with_portfolio_and_equity_chart():
    data, c = _port_setup(3, 250, seed=8)
    p = SELF.portfolio_backtest(data, c, _strat(4, stoch_th=25), capital=200_000)
    vr = SELF.VerdictReport("-", "B", 5, "2026-07-24", tuple())
    empty = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    html = SELF.generate_dashboard(_run_info(), SELF.journal_stats(empty), empty,
                                      vr, pd.DataFrame(), p)
    assert "chart.js" in html.lower() and "เส้นทางเงินทุน" in html


def test_dashboard_confirmed_table():
    s = _strat(0, rsi_threshold=30)
    conf = _confirmed_from(s, n=2, grade="A")
    vr = SELF.VerdictReport("-", "A", 2, "2026-07-24", tuple())
    empty = pd.DataFrame(columns=SELF.JOURNAL_COLUMNS)
    html = SELF.generate_dashboard(_run_info(grade="A"), SELF.journal_stats(empty),
                                      empty, vr, conf)
    assert "MR_RSI_BB" in html and "WR LB%" in html


def test_fmt_and_cls_helpers():
    assert SELF._fmt(None) == "-" and SELF._fmt(float("nan")) == "-"
    assert SELF._fmt(1.234, "%", 2) == "1.23%"
    assert SELF._cls(1.0) == "pos" and SELF._cls(-1.0) == "neg"
    assert SELF._cls(None) == ""
    assert SELF._r(float("inf")) is None and SELF._r(1.234) == 1.23


# --------------------------------------------------------------- pipeline
def test_run_pipeline_end_to_end(tmp_path):
    raw = SELF.synthetic_prices([f"S{i}" for i in range(6)], n_days=420, seed=77)
    res = SELF.run_pipeline(
        raw, families=[0, 4], keep_top=12, progress=False,
        journal_path=str(tmp_path / "j.csv"), dashboard_path=str(tmp_path / "d.html"),
        demo=True, universe_name="TEST", save_csv=False, capital=200_000)
    assert set(["data", "confirmed", "verdict", "journal", "html", "run_info"]) <= set(res)
    assert (tmp_path / "d.html").exists() and (tmp_path / "j.csv").exists()
    assert res["html"].startswith("<!DOCTYPE html")
    assert res["run_info"]["n_grade_a"] >= 0 and res["run_info"]["honest_note"]


def test_run_pipeline_no_candidates_still_reports(tmp_path):
    raw = SELF.synthetic_prices(["A", "B"], n_days=200, seed=5)
    res = SELF.run_pipeline(raw, families=[5], keep_top=3, progress=False,
                               journal_path=str(tmp_path / "j.csv"),
                               dashboard_path=str(tmp_path / "d.html"),
                               save_csv=False)
    assert res["best"] is None or res["best"]["grade"] in ("A", "B")
    assert res["verdict"].overall
    assert "ไม่" in res["run_info"]["honest_note"] or res["run_info"]["n_grade_a"] > 0


def test_run_pipeline_empty_raises():
    with pytest.raises(ValueError):
        SELF.run_pipeline(pd.DataFrame(columns=SELF.PRICE_COLUMNS))


def test_honest_note_says_target_missed_when_no_grade_a():
    note = SELF._honest_note(0, 2, dict(oos_wr=65.0, oos_npd=0.5, oos_net=1.2, oos_n=40),
                                None)
    assert "ไม่มีสมการใดถึงเป้า" in note and "65.0%" in note


def test_honest_note_no_confirmed():
    assert "ยังไม่ควรเข้า" in SELF._honest_note(0, 0, None, None)


# --------------------------------------------------- crash / edge hardening
def test_safe_int_and_float_handle_junk():
    assert SELF._safe_int(np.nan, 5) == 5
    assert SELF._safe_int(None, 7) == 7
    assert SELF._safe_int("bad", 3) == 3
    assert SELF._safe_int(np.inf, 5) == 5
    assert SELF._safe_int("10", 0) == 10 and SELF._safe_int(10.9, 0) == 10
    assert SELF._safe_float("bad") != SELF._safe_float("bad")      # NaN
    assert SELF._safe_float(None, 1.0) == 1.0 and SELF._safe_float("2.5") == 2.5


def test_flat_prices_pipeline_no_warnings():
    import warnings as _w
    raw = _bars("FLAT", [100.0] * 120, opens=[100.0] * 120, highs=[100.0] * 120,
                lows=[100.0] * 120)
    with _w.catch_warnings():
        _w.simplefilter("error")
        data = SELF.precompute(raw)
        c = SELF.build_cache(data)
        for fam in range(10):
            SELF.entry_mask(c, fam, SELF.PARAM_DEFAULTS)
        SELF.evaluate(c, _strat(0, rsi_threshold=60))


def test_zero_volume_no_crash():
    raw = _bars("Z", list(100 + np.arange(80.0)), vol=0.0)
    data = SELF.precompute(raw)
    c = SELF.build_cache(data)
    assert SELF.entry_mask(c, 6, SELF.PARAM_DEFAULTS).sum() >= 0
    assert SELF.filter_mask(c, 0, 1, 0).sum() == 0        # vol filter ตัดหมด


def test_single_bar_ticker_no_crash():
    raw = pd.concat([_bars("A", list(100 + np.arange(80.0))), _bars("B", [50.0])],
                    ignore_index=True)
    data = SELF.precompute(SELF.clean_prices(raw))
    c = SELF.build_cache(data)
    assert SELF.evaluate(c, _strat(1, donchian_n=10)) is not None or True


def test_gap_with_zero_prev_close_no_inf():
    closes = [100.0] * 20 + [1e-12] + [100.0] * 20
    data = SELF.precompute(_bars("Z", closes))
    g = data["GapPct"].to_numpy(dtype=float)
    assert not np.isinf(g).any()


def test_extreme_price_values_no_overflow():
    closes = [1e6] * 40 + [1e-3] * 40
    data = SELF.precompute(SELF.clean_prices(_bars("X", closes)))
    c = SELF.build_cache(data)
    r = SELF.evaluate(c, _strat(0, rsi_threshold=60, bb_std=1.5))
    assert r is None or np.isfinite(_safe_float(r["avg_net"]))


def test_duplicate_dates_are_removed_before_pipeline():
    raw = _bars("X", [100.0] * 40)
    dup = pd.concat([raw, raw], ignore_index=True)
    clean = SELF.clean_prices(dup)
    assert len(clean) == 40


def test_config_targets_match_user_request():
    assert SELF.TARGET_WIN_RATE == 80.0
    assert SELF.TARGET_NET_PER_DAY == 2.0
    assert SELF.TIE_BREAK_SL_WINS is True
    assert SELF.FRICTION_PCT == pytest.approx(0.514, abs=1e-9)
    assert SELF.BOARD_LOT == 100


def test_universes_are_unique_and_nonempty():
    for name, lst in SELF.UNIVERSES.items():
        assert len(lst) == len(set(lst)) and len(lst) > 0


def test_journal_roundtrip_file(tmp_path):
    p = str(tmp_path / "j.csv")
    j = _jrow(status="FILLED_TP", net_return_pct=1.23)
    SELF.save_journal(j, p)
    back = SELF.load_journal(p)
    assert len(back) == 1 and back.iloc[0]["net_return_pct"] == 1.23


def test_journal_full_cycle_order_to_resolved():
    """วงจรจริง: ฟันธง -> บันทึก PENDING -> วันต่อมาตัดสินผลจากราคาจริง -> เข้าสถิติ."""
    o = _demo_order(ticker="CYC", buy_ref=100.0, sell_tp=105.0, stop_sl=95.0,
                    tp_pct=5.0, sl_pct=5.0, hold_days=3, entry_mode=0)
    vr = SELF.VerdictReport("เข้า 1 ตัว", "B", 5, "2026-01-02", (o,))
    j = SELF.append_new_orders(pd.DataFrame(columns=SELF.JOURNAL_COLUMNS), vr, "2026-01-02")
    assert j.iloc[0]["status"] == "PENDING"
    raw = _pf("CYC", ["2026-01-02", "2026-01-05", "2026-01-06"],
              o=[99, 100, 101], h=[99, 101, 106], l=[99, 99, 100], c=[99, 100, 105])
    j = SELF.resolve_journal(j, raw)
    assert j.iloc[0]["status"] == "FILLED_TP"
    assert j.iloc[0]["net_return_pct"] == round(5 - SELF.FRICTION_PCT, 2)
    st = SELF.journal_stats(j)
    assert st["n_resolved"] == 1 and st["wins"] == 1 and st["realized_wr"] == 100.0


def test_run_pipeline_twice_does_not_duplicate_journal(tmp_path):
    """รันซ้ำวันเดียวกันต้องไม่บันทึกออร์เดอร์ซ้ำ (idempotent) — กันสถิติปนเปื้อน."""
    raw = SELF.synthetic_prices(["A", "B", "C", "D"], n_days=360, seed=99)
    jp, dp = str(tmp_path / "j.csv"), str(tmp_path / "d.html")
    r1 = SELF.run_pipeline(raw, families=[0, 4, 8], keep_top=10, progress=False,
                           journal_path=jp, dashboard_path=dp, save_csv=False)
    r2 = SELF.run_pipeline(raw, families=[0, 4, 8], keep_top=10, progress=False,
                           journal_path=jp, dashboard_path=dp, save_csv=False)
    assert len(r2["journal"]) == len(r1["journal"])


def test_live_signal_path_equals_backtest_path():
    """[regression บั๊กหลักของระบบเดิม] สัญญาณที่ agent ใช้ ต้องมาจาก mask เดียวกับ backtest."""
    data, c = _always_fire_data()
    conf = _confirmed_from(_strat(8, streak_n=3))
    vr = SELF.DailyVerdictAgent(min_agree=1).decide(data, c, conf)
    strat = SELF._coerce_strategy({k: conf.iloc[0][k] for k in SELF.PARAM_KEYS})
    last = pd.to_datetime(data["Date"]).max()
    m = SELF.signal_mask(c, strat) & np.asarray(pd.to_datetime(data["Date"]) == last)
    assert {str(c["_ticker"][r]) for r in np.where(m)[0]} == {o.ticker for o in vr.orders}


if __name__ == "__main__":
    raise SystemExit(main())
