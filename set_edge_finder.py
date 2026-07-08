"""
================================================================================
SET WEEKLY STAT-EDGE FINDER — ระบบหาจุดเข้าเชิงสถิติ (ไฟล์เดียวจบ รันได้ทันที)
================================================================================
ระบบเทรดอัตโนมัติเชิงสถิติสำหรับหุ้นไทย (SET) — เน้นหา "จุดเข้า (Entry Point)"
ที่แม่นยำด้วยคณิตศาสตร์ล้วน แล้วพิสูจน์ขอบ (edge) ด้วย out-of-sample ก่อนใช้จริง.
ไฟล์นี้รันได้เดี่ยว ๆ ไม่พึ่งไฟล์อื่น: ดึงราคาสด -> ค้นหา -> ยืนยัน -> ฟันธง -> dashboard.

--------------------------------------------------------------------------------
วิธีรัน (เลือกอย่างใดอย่างหนึ่ง)
--------------------------------------------------------------------------------
  Google Colab :  !pip install yfinance pandas numpy --quiet
                  วางไฟล์นี้ทั้งไฟล์ แล้วกด Run  (ต้องต่อ internet เพื่อดึงราคาสด)
  เครื่อง/เซิร์ฟเวอร์ :  pip install yfinance pandas numpy
                  python set_edge_finder.py
  เก็บประวัติถาวรบน Colab :  mount Google Drive แล้วตั้ง
                  JOURNAL_PATH = "/content/drive/MyDrive/trade_journal.csv"
  จังหวะใช้จริง :  รันศุกร์เย็นหลังตลาดปิด -> อ่านคำฟันธง -> ตั้งซื้อเช้าวันจันทร์
                  (ศุกร์ถัดไประบบตัดสินผลไม้เก่าให้อัตโนมัติ)

--------------------------------------------------------------------------------
Pipeline (ไหลจากบนลงล่าง)
--------------------------------------------------------------------------------
  fetch_prices()  ดึง OHLCV 5 ปี (yfinance) -> precompute() คำนวณอินดิเคเตอร์+
  forward bars+breadth -> แบ่ง 80/20 ตามเวลา -> run_search() สุ่มพารามิเตอร์ล้านแบบ
  บน in-sample -> validate_oos() ยืนยันซ้ำบนข้อมูลที่ไม่เคยเห็น (ตัด overfit อัตโนมัติ)
  -> VerdictAgent ฟันธงด้วยฉันทามติ Top-K -> trade_journal.csv (track record) + dashboard.html

--------------------------------------------------------------------------------
สมการจุดเข้า — 7 ตระกูล (เงื่อนไขบูลีนล้วน บนข้อมูลถึงแท่งปัจจุบัน = ไม่มองอนาคต)
--------------------------------------------------------------------------------
  0 MEAN_REVERSION    : RSI < th  AND  Close < Bollinger_lower(mid - k*sigma)
  1 BREAKOUT          : Close > Donchian_high(N)              [shift(1) = ไม่รวมแท่งนี้]
  2 TREND_PULLBACK    : EMA_fast > EMA_slow  AND  RSI ย่อ < th
  3 MACD_CROSS        : MACD ตัดขึ้นเหนือ signal line (EMA9 ของ MACD)
  4 STOCH_OVERSOLD    : Stochastic %K < stoch_th
  5 GAP_DOWN_REVERSAL : เปิด gap ลง >= gap_pct%  AND  Close > Open (แท่งฟื้น)
  6 VOLSPIKE_BREAKOUT : Volume >= vol_mult * VolSMA20  AND  Close > Donchian_high(N)
  อินดิเคเตอร์: Wilder RSI, EMA, Wilder ATR, ADX, MACD, Stochastic %K, Donchian
  (ทั้งหมดคำนวณย้อนหลังล้วน; RSI/Stoch/ADX กันหารศูนย์เมื่อราคาแบน)

--------------------------------------------------------------------------------
สมการออก (Exit) + การคิดกำไร
--------------------------------------------------------------------------------
  โหมด % ตายตัว   : TP = entry*(1+tp/100),  SL = entry*(1-sl/100)
  โหมด ATR-multiple: TP = entry + tp*ATR,     SL = entry - sl*ATR  (ปรับตามผันผวนจริง)
  กำไรสุทธิ/ไม้    : net = (exit/entry - 1)*100 - FRICTION_PCT   (หักต้นทุนก่อนเสมอ)
  entry จริง       : ราคาเปิดแท่งถัดไป (Open ของวันถัดจากสัญญาณ) = เข้าล่วงหน้าไม่ได้

--------------------------------------------------------------------------------
ทำไมเชื่อว่า >70% ได้จริง (การตัดสินทางสถิติ) — และความสัตย์จริง (ห้ามโกหก)
--------------------------------------------------------------------------------
  * คัดเฉพาะ combo ที่ WR>=70% & avg_net>=3% & median_net>0 & n_resolved>=30
  * Wilson score lower bound (95%): จัดอันดับด้วยขอบล่างจริง ไม่ใช่ WR ดิบ (กัน 8/10 หลอก)
  * out-of-sample confirmation: ผ่านซ้ำบนช่วงที่ไม่เคยใช้ค้น = edge จริง ไม่ใช่ overfit
  * WR รายงานแบบ conservative: หักต้นทุนแล้ว + สัญญาณชนกันนับเป็นแพ้ + ใช้ Wilson LB
  * ถ้ารอบไหนไม่มีสมการผ่าน -> ฟันธง "ไม่เข้า" ตรง ๆ = คำตอบที่ซื่อสัตย์ ไม่ใช่บั๊ก
  * ไม่การันตีผลอนาคต ไม่ใช่คำแนะนำการลงทุน ผู้ใช้รับความเสี่ยงเอง

--------------------------------------------------------------------------------
Strictly Non-Repainting (ไม่คำนวณย้อนหลัง เด็ดขาด)
--------------------------------------------------------------------------------
  สัญญาณที่แท่ง t ไม่เปลี่ยนเมื่อมีข้อมูลอนาคตมาต่อ — พิสูจน์ด้วยเทสต์ prefix==full ครบ 7 family.
  อินดิเคเตอร์ย้อนหลังล้วน (ewm/rolling/shift(+1)); คอลัมน์ forward ใช้จำลอง exit ในแบ็กเทสต์
  เท่านั้น ไม่แตะการสร้างสัญญาณ; เส้นทางตัดสินสดอ่านเฉพาะแท่งล่าสุดที่ปิดแล้ว.

--------------------------------------------------------------------------------
การเคลียร์บั๊กทุกระดับ & edge cases (ผ่านเทสต์ 70 เคส + fuzz 3,400 รอบ บน numpy2/pandas3)
--------------------------------------------------------------------------------
  [ร้าย/crash] journal เก่าขาดคอลัมน์ -> int(NaN) เดิม crash -> ใช้ _safe_int/_safe_float
  [สูง]  ราคาเสีย 0/ติดลบ (tick ผิด) -> guard entry>0 กันหารศูนย์ -> inf/NaN ปนเปื้อนสถิติ
  [กลาง] สัญญาณชนกันแท่งเดียว (High>=TP และ Low<=SL) -> SL ชนะ (นับแพ้) via TIE_BREAK_SL_WINS
  [กลาง/perf] iter_combos dedup ด้วย int เดียว (แทน tuple 21 มิติ) -> ลด RAM ~5-10 เท่า
  [ต่ำ]  ATR=0 (ราคานิ่ง) -> guard กัน TP=entry -> ชนะจอมปลอม; prev close=0 -> gap ไม่ inf
  data:  ข้อมูลขาดหาย/หุ้นดึงไม่ได้/แท่งไม่พอ/ศุกร์หยุด/รันซ้ำวันเดิม -> จัดการครบ ไม่ crash

--------------------------------------------------------------------------------
การตั้งค่า (แก้ที่บล็อก CONFIG ด้านล่าง)
--------------------------------------------------------------------------------
  UNIVERSE            "QUALITY19" (หุ้นคุณภาพ 19 ตัว) หรือ "SET100"
  FRIDAY_ONLY         True = นับสัญญาณเฉพาะแท่งท้ายสัปดาห์ (ตรงกับ workflow รายสัปดาห์)
  BUDGET_PER_TRADE_THB งบต่อไม้ (คำนวณจำนวน lot, board lot=100 หุ้น)   [ดีฟอลต์ 10,000]
  WIN_RATE_MIN        เกณฑ์ WR ขั้นต่ำ %                                [70.0]
  NET_RETURN_MIN      เกณฑ์กำไรสุทธิเฉลี่ยขั้นต่ำ %/ไม้                  [3.0]
  MIN_RESOLVED        จำนวนไม้ขั้นต่ำต่อ combo (กัน fluke)              [30]
  OOS_SPLIT_FRACTION  สัดส่วน in-sample                                 [0.8]
  N_TARGET/N_ESCALATE จำนวน combo ที่สุ่มค้น / เพิ่มถ้ารอบแรกไม่เจอ     [3M / 6M]
  FRICTION_PCT        ต้นทุนไป-กลับต่อไม้ %                             [0.514]
  TIE_BREAK_SL_WINS   สัญญาณชนกัน: True=SL ชนะ(ซื่อสัตย์) / False=TP ชนะ [True]
  JOURNAL_PATH        ที่เก็บ track record (Colab: ชี้ไป Google Drive)  ["trade_journal.csv"]
  SPACE               search space ของทุกพารามิเตอร์ (RSI/TP/SL/hold_days/...)
================================================================================
"""

import itertools
import json
import os
import time
import numpy as np
import pandas as pd
from datetime import datetime

# =============================================================== CONFIG (แก้ได้)
# ---- Universe ----
# หลักฐานจากการรันจริง 2 รอบ: edge ที่ยืนยัน out-of-sample ได้ พบเฉพาะบนหุ้น
# คุณภาพ 19 ตัว (limit entry, 9 สมการผ่าน OOS) ส่วน SET100 (101 ตัว, 3M combo,
# in-sample ผ่าน 50) ได้ out-of-sample = 0 ทั้งหมด => ค่าเริ่มต้นคือ QUALITY19
UNIVERSE = "QUALITY19"          # เปลี่ยนเป็น "SET100" ได้ถ้าต้องการทดลองซ้ำ

QUALITY19 = ["ADVANC", "CPALL", "GULF", "PTT", "BDMS", "KTB", "WHA", "KBANK",
             "SCB", "AOT", "TRUE", "BEM", "CPN", "BBL", "CRC", "TISCO",
             "HMPRO", "AP", "SCC"]

# SET100: ตัด 4 ตัวที่รันจริงแล้วดึงไม่ได้ (ควบรวม/เพิกถอน): INTUCH, MAKRO, ORIGIN, STEC
SET100 = [
    "BBL", "KBANK", "SCB", "KTB", "TISCO", "TCAP", "KKP", "TTB", "BAM", "MTC",
    "SAWAD", "KTC", "TIDLOR", "AEONTS",
    "PTT", "PTTEP", "PTTGC", "TOP", "IRPC", "BCP", "OR", "GULF", "GPSC", "EGCO",
    "RATCH", "BGRIM", "BANPU", "EA", "SPRC", "TASCO",
    "ADVANC", "TRUE", "JAS", "JMART", "COM7", "SYNEX", "DELTA", "HANA", "KCE",
    "CPALL", "CPAXT", "BJC", "HMPRO", "GLOBAL", "DOHOME", "CRC",
    "CENTEL", "MINT", "ILM",
    "CPF", "TU", "GFPT", "M", "OSP", "CBG", "ICHI", "TVO", "SAPPE",
    "SCC", "SCGP", "AP", "LH", "SPALI", "QH", "ANAN", "SIRI", "PSH",
    "WHA", "AMATA", "CK", "SEAFCO", "TPIPP", "TPIPL", "DCC", "EPG",
    "BDMS", "BH", "BCH", "CHG", "RJH", "PR9",
    "AOT", "BEM", "BTS", "BA", "AAV", "PSL", "TTA", "III",
    "SCGD", "STGT", "STA", "NER", "STANLY",
    "PLANB", "VGI", "MAJOR", "WORK", "ERW", "BEC", "RS",
]
SET100 = list(dict.fromkeys(SET100))

TICKERS = QUALITY19 if UNIVERSE == "QUALITY19" else SET100

# ---- Workflow จริง: รันสัปดาห์ละครั้งทุกวันศุกร์ ----
# FRIDAY_ONLY=True => backtest นับสัญญาณเฉพาะ "แท่งสุดท้ายของแต่ละสัปดาห์" เท่านั้น
# (สัญญาณกลางสัปดาห์ที่ผู้ใช้ไม่มีทางเห็นจริง จะไม่ถูกนับ — backtest fidelity)
# รองรับสัปดาห์ที่ศุกร์เป็นวันหยุด: แท่งท้ายสัปดาห์จริง (เช่น พฤหัส) จะถูกนับแทน
FRIDAY_ONLY = True

# ---- งบต่อไม้ (ใช้ติดป้ายในรายงานสัญญาณ, board lot = 100 หุ้น) ----
BUDGET_PER_TRADE_THB = 10_000
BOARD_LOT = 100

OOS_SPLIT_FRACTION = 0.8
WIN_RATE_MIN = 70.0
NET_RETURN_MIN = 3.0   # เป้าผู้ใช้: 3%/สัปดาห์ต่อไม้ — ตั้งตามสั่ง
                       # (หลักฐานเดิม: ที่ 2% ไม่มี combo n>=20 ผ่านเลย; OOS ยืนยันได้จริง
                       #  อยู่ช่วง 1.5-2.7% — ให้ผลรันจริงเป็นผู้ตัดสิน)
MIN_RESOLVED = 30      # FRIDAY_ONLY ลดจำนวนสัญญาณ ~5 เท่า — คงเกณฑ์นี้กัน fluke
TOP_N_REPORT = 50
FRICTION_PCT = 2 * (0.157 + 0.10)   # 0.514%

# ---- นโยบายเคลียร์สัญญาณชนกัน (Bar-collision policy) ----
# แท่งเดียวชนทั้ง TP และ SL (High>=TP และ Low<=SL) = ไม่รู้ลำดับ intraday.
# True  = SL ชนะ (นับเป็นแพ้, worst-case) — ซื่อสัตย์ ไม่ปั่น WR ให้สูงเกินจริง [ค่าเริ่มต้น]
# False = TP ชนะ (นับเป็นชนะ, optimistic) — ใช้เมื่อยอมรับ backtest แบบเข้าข้างตัวเอง
# หลักฐาน: การนับ tie เป็นชนะทำให้ WR ที่รายงานสูงกว่าจริง — ขัดข้อกำหนด "ห้ามโกหก"
TIE_BREAK_SL_WINS = True

# ---- ราคาขั้นต่ำที่ยอมรับ (guard ข้อมูลตลาดเสีย/ขาดหาย) ----
# แท่งที่ราคา <= 0 หรือไม่ finite = ข้อมูลเสีย (tick ผิด/หุ้นพัก) — ตัดทิ้ง ไม่เข้าไม้
# ป้องกัน entry=0 -> หารศูนย์ใน (exit/entry-1) -> inf/NaN ปนเปื้อนสถิติ
MIN_VALID_PRICE = 1e-9

N_TARGET = 3_000_000
N_ESCALATE = 6_000_000
RANDOM_SEED = 20260706

# ---- สมุดบันทึกผลจริง (Track Record) ----
# บน Colab: ไฟล์นอก Google Drive จะหายเมื่อจบ session — mount Drive แล้วชี้ path เช่น
#   from google.colab import drive; drive.mount('/content/drive')
#   JOURNAL_PATH = "/content/drive/MyDrive/trade_journal.csv"
JOURNAL_PATH = "trade_journal.csv"

# Multi-strategy search space. entry_family เปลี่ยน "ตรรกะการเข้า" ทั้งหมด.
SPACE = dict(
    entry_family  = [0, 1, 2, 3, 4, 5, 6],     # 0=MR 1=Breakout 2=Pullback 3=MACD
                                               # 4=StochOversold 5=GapDownReversal 6=VolSpikeBreakout
    rsi_period    = [7, 14, 21, 28],
    rsi_threshold = [15, 25, 35, 45],          # MR/pullback ใช้; breakout/macd ไม่สน
    bb_period     = [10, 20],
    bb_std        = [1.5, 2.0, 2.5],
    donchian_n    = [10, 20, 40],              # breakout lookback
    ema_fast      = [10, 20],                  # trend pullback / macd
    ema_slow      = [50, 100],
    exit_mode     = [0, 1],                    # 0=percent 1=ATR-multiple
    tp_val        = [2, 3, 5, 8],              # percent (mode0) หรือ ATR mult (mode1)
    sl_val        = [3, 5, 8, 13],
    atr_period    = [14],
    hold_days     = [5, 10],
    adx_min       = [0, 20, 25],               # 0=ปิด filter; >0=ต้อง ADX เกินนี้
    vol_filter    = [0, 1],
    # ---- พารามิเตอร์ของ family ใหม่ (4/5/6) ----
    stoch_period  = [14],                      # fam4: Stochastic %K period
    stoch_th      = [15, 20, 25],              # fam4: เข้าเมื่อ %K ต่ำกว่าค่านี้
    gap_pct       = [2.0, 3.0],                # fam5: เปิด gap ลง >= ค่านี้ (%)
    vol_mult      = [1.5, 2.0, 3.0],           # fam6: วอลุ่ม >= mult × VolSMA20
    # ---- โครงสร้างใหม่ (ไม่ใช่ indicator เพิ่ม แต่เปลี่ยนวิธีเข้า/บริบทตลาด) ----
    entry_mode    = [0, 1, 2, 3],              # 0=market@next open;
                                               # 1/2/3=ตั้งซื้อ limit ต่ำกว่า close สัญญาณ 1/2/3%
                                               # (ติดเฉพาะวันแรก ไม่ติด=ยกเลิก ไม่เสียอะไร)
    regime_filter = [0, 1],                    # 1=เข้าเฉพาะเมื่อ >50% ของ universe ยืนเหนือ SMA50
)
# search space ขยายด้วย 3 family + พารามิเตอร์ใหม่ -> ~200M combo (สุ่มจากนี้ N_TARGET)
# หมายเหตุ: พารามิเตอร์ที่ family หนึ่งไม่ใช้จะถูกมองข้าม (เช่น fam4 ไม่สน donchian_n)


# ================================================ DATA LAYER (Layer 3 — Infra)
def _to_naive_datetime(s: pd.Series) -> pd.Series:
    """แปลงเป็น datetime แบบ tz-naive อย่างปลอดภัย — รองรับทั้ง tz-aware และ naive.
    yfinance คืน index แบบ tz-aware; แต่บางแหล่ง/บางเวอร์ชันคืน naive -> tz_localize(None)
    เดิมจะ crash. ตรวจ tz ก่อนแล้วเลือก convert/localize ให้ถูก."""
    dt = pd.to_datetime(s)
    tz = getattr(dt.dt, "tz", None)
    if tz is not None:
        return dt.dt.tz_convert(None) if hasattr(dt.dt, "tz_convert") else dt.dt.tz_localize(None)
    return dt


def fetch_prices(tickers=TICKERS, retries: int = 3) -> pd.DataFrame:
    """ดึงราคาสด (Layer 3 — infra, แตะ network เท่านั้น).
    retries: ลองซ้ำต่อ ticker เมื่อ network สะดุด (exponential-ish backoff)."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("ต้องติดตั้งก่อน: !pip install yfinance") from e
    parts, ok, failed = [], [], []
    print(f"[{datetime.now():%H:%M:%S}] ดึงข้อมูลสด {len(tickers)} ตัว ...", flush=True)
    for t in tickers:
        d = None
        for attempt in range(1, max(1, retries) + 1):
            try:
                d = yf.Ticker(t + ".BK").history(period="5y", interval="1d", auto_adjust=False)
                break
            except Exception as e:                       # network/transient -> ลองใหม่
                if attempt >= retries:
                    print(f"  [!] {t}: {e}", flush=True)
                else:
                    time.sleep(min(2 ** attempt, 8))
        if d is None or d.empty:
            failed.append(t); continue
        try:
            if isinstance(d.columns, pd.MultiIndex):
                d.columns = d.columns.get_level_values(0)
            d = d.reset_index()
            d["Date"] = _to_naive_datetime(d[d.columns[0]])
            d["Ticker"] = t
            sub = d[["Ticker", "Date", "Open", "High", "Low", "Close", "Volume"]].copy()
            # ตัดแถวข้อมูลเสีย: ราคา/วันที่ NaN หรือราคา <= 0 (กันหลุดเข้า backtest)
            price_cols = ["Open", "High", "Low", "Close"]
            sub = sub.dropna(subset=["Date"] + price_cols)
            sub = sub[(sub[price_cols] > 0).all(axis=1)]
            if sub.empty:
                failed.append(t); continue
            parts.append(sub); ok.append(t)
        except Exception as e:
            failed.append(t); print(f"  [!] {t} (parse): {e}", flush=True)
    if not parts:
        raise RuntimeError("ดึงข้อมูลไม่สำเร็จเลย")
    df = pd.concat(parts, ignore_index=True).sort_values(["Ticker", "Date"]).reset_index(drop=True)
    # กันแถวซ้ำ (Ticker, Date) ที่บางครั้ง yfinance คืนมา
    df = df.drop_duplicates(subset=["Ticker", "Date"], keep="last").reset_index(drop=True)
    print(f"  สำเร็จ {len(ok)} | ล้มเหลว {len(failed)}: {failed if failed else '-'}")
    print(f"  ช่วง: {df['Date'].min():%Y-%m-%d} ถึง {df['Date'].max():%Y-%m-%d} | {len(df):,} แถว")
    return df


# ============================================ BUSINESS LOGIC (Layer 1 — pure)
def wilder_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0); loss = -delta.clip(upper=0)
    ag = gain.ewm(alpha=1/period, adjust=False).mean()
    al = loss.ewm(alpha=1/period, adjust=False).mean()
    rsi = pd.Series(np.nan, index=close.index, dtype=float)
    warm = ag.isna() | al.isna()
    both0 = (ag == 0) & (al == 0) & ~warm
    loss0 = (al == 0) & (ag > 0) & ~warm
    norm = ~warm & ~both0 & ~loss0
    rsi[norm] = 100 - (100 / (1 + ag[norm] / al[norm]))
    rsi[loss0] = 100.0; rsi[both0] = 50.0
    return rsi


def ema(close: pd.Series, span: int) -> pd.Series:
    return close.ewm(span=span, adjust=False).mean()


def atr(high, low, close, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def adx(high, low, close, period: int = 14) -> pd.Series:
    up = high.diff(); down = -low.diff()
    plus_dm = ((up > down) & (up > 0)) * up
    minus_dm = ((down > up) & (down > 0)) * down
    tr = pd.concat([(high - low), (high - close.shift(1)).abs(), (low - close.shift(1)).abs()], axis=1).max(axis=1)
    atr_ = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False).mean()


def macd_cross_up(close: pd.Series, fast: int, slow: int, signal: int = 9) -> pd.Series:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))


def stoch_k(high, low, close, period: int = 14) -> pd.Series:
    """Stochastic %K — reversal indicator คนละแกนกับ RSI (ใช้ high/low range)."""
    ll = low.rolling(period).min()
    hh = high.rolling(period).max()
    rng = (hh - ll).replace(0, np.nan)
    return 100 * (close - ll) / rng


def wilson_lb(wins: int, n: int, z: float = 1.96) -> float:
    if n == 0:
        return 0.0
    p = wins / n
    return (p + z*z/(2*n) - z*np.sqrt((p*(1-p)+z*z/(4*n))/n)) / (1 + z*z/n)


def precompute(raw: pd.DataFrame) -> pd.DataFrame:
    """คำนวณต่อหุ้นครั้งเดียว: VolSMA20, SMA50, ATR, ADX14, Entry, forward H/L/C,
    IsWeekEnd (แท่งสุดท้ายของแต่ละสัปดาห์ ISO — รองรับศุกร์หยุด→พฤหัสเป็นท้ายสัปดาห์)
    แล้วคำนวณ market breadth ต่อวันจากทั้ง universe."""
    max_hold = max(SPACE["hold_days"])
    parts = []
    for _, g in raw.groupby("Ticker", sort=False):
        g = g.sort_values("Date").reset_index(drop=True)
        g["VolSMA20"] = g["Volume"].rolling(20).mean()
        g["SMA50"] = g["Close"].rolling(50).mean()
        g["Entry"] = g["Open"].shift(-1)
        for ap in set(SPACE["atr_period"]):
            g[f"ATR{ap}"] = atr(g["High"], g["Low"], g["Close"], ap)
        if any(a > 0 for a in SPACE["adx_min"]):
            g["ADX14"] = adx(g["High"], g["Low"], g["Close"], 14)
        for sp in set(SPACE["stoch_period"]):
            g[f"STOCH{sp}"] = stoch_k(g["High"], g["Low"], g["Close"], sp)
        # Gap = (Open - prev Close)/prev Close * 100 ; ลบ = เปิดต่ำกว่าปิดเมื่อวาน
        # replace(0->NaN): กัน prev close=0 (ข้อมูลเสีย) -> หารศูนย์ -> inf gap ปนเปื้อน fam5
        prev_close = g["Close"].shift(1).replace(0, np.nan)
        g["GapPct"] = (g["Open"] / prev_close - 1) * 100
        iso = g["Date"].dt.isocalendar()
        wk = iso["year"].astype(int) * 100 + iso["week"].astype(int)
        g["IsWeekEnd"] = g["Date"].eq(g.groupby(wk)["Date"].transform("max"))
        for k in range(1, max_hold + 1):
            g[f"H{k}"] = g["High"].shift(-k)
            g[f"L{k}"] = g["Low"].shift(-k)
            g[f"C{k}"] = g["Close"].shift(-k)
        parts.append(g)
    data = pd.concat(parts, ignore_index=True)
    # Market breadth ต่อวัน: mean ของ (Close > SMA50) ข้ามทุกหุ้นที่มีข้อมูลวันนั้น
    # .astype(float) จำเป็น: bool.where(NaN) ให้ object dtype ซึ่งทำให้ np.isnan
    # ใน evaluate() พัง (TypeError) — บั๊กจริงที่ test จับได้
    above = (data["Close"] > data["SMA50"]).astype(float).where(data["SMA50"].notna())
    data["Breadth"] = above.groupby(data["Date"]).transform("mean").astype(float)
    return data


def build_cache(data: pd.DataFrame) -> dict:
    """Cache indicator ต่อพารามิเตอร์ (ครั้งเดียวต่อ dataset)."""
    g = data.groupby("Ticker", sort=False)
    cache = dict(
        close=data["Close"].values, high=data["High"].values, low=data["Low"].values,
        open=data["Open"].values,
        vol=data["Volume"].values, volsma20=data["VolSMA20"].values,
        entry=data["Entry"].values, breadth=data["Breadth"].values,
        weekend=data["IsWeekEnd"].values.astype(bool),
        H={}, L={}, C={}, rsi={}, bb={}, ema={}, atr={}, adx={}, donch={}, macd={}, stoch={},
    )
    max_hold = max(SPACE["hold_days"])
    for k in range(1, max_hold + 1):
        cache["H"][k] = data[f"H{k}"].values
        cache["L"][k] = data[f"L{k}"].values
        cache["C"][k] = data[f"C{k}"].values
    for rp in set(SPACE["rsi_period"]):
        cache["rsi"][rp] = g["Close"].transform(lambda s, rp=rp: wilder_rsi(s, rp)).values
    for bp, bs in itertools.product(SPACE["bb_period"], SPACE["bb_std"]):
        mid = g["Close"].transform(lambda s, bp=bp: s.rolling(bp).mean())
        std = g["Close"].transform(lambda s, bp=bp: s.rolling(bp).std())
        cache["bb"][(bp, bs)] = (mid - bs * std).values
    for sp in set(SPACE["ema_fast"]) | set(SPACE["ema_slow"]):
        cache["ema"][sp] = g["Close"].transform(lambda s, sp=sp: ema(s, sp)).values
    for ap in set(SPACE["atr_period"]):
        cache["atr"][ap] = data[f"ATR{ap}"].values
    if any(a > 0 for a in SPACE["adx_min"]):
        cache["adx"]["adx14"] = data["ADX14"].values
    cache["stoch"] = {sp: data[f"STOCH{sp}"].values for sp in set(SPACE["stoch_period"])}
    cache["gap"] = data["GapPct"].values
    for dn in set(SPACE["donchian_n"]):
        # Donchian high based on prior CLOSE highs (breakout = close exceeds
        # the highest close of the last dn bars). Using Close (not High) keeps
        # the comparison consistent with the Close-based entry signal.
        cache["donch"][dn] = g["Close"].transform(lambda s, dn=dn: s.rolling(dn).max().shift(1)).values
    for ef, es in itertools.product(SPACE["ema_fast"], SPACE["ema_slow"]):
        cache["macd"][(ef, es)] = g["Close"].transform(
            lambda s, ef=ef, es=es: macd_cross_up(s, ef, es).astype(float)).values
    cache["fwd_valid"] = {hd: data[f"C{hd}"].notna().values for hd in SPACE["hold_days"]}
    return cache


def _entry_signal(cols, p):
    (fam, rp, rt, bp, bs, dn, ef, es, _em, _tp, _sl, _ap, _hd, _adx, _vf,
     stp, sth, gp, vm, _emode, _regf) = p
    close = cols["close"]
    if fam == 0:
        rsi = cols["rsi"][rp]; bb = cols["bb"][(bp, bs)]
        return ~np.isnan(rsi) & ~np.isnan(bb) & (rsi < rt) & (close < bb)
    if fam == 1:
        dh = cols["donch"][dn]
        return ~np.isnan(dh) & (close > dh)
    if fam == 2:
        ef_v = cols["ema"][ef]; es_v = cols["ema"][es]; rsi = cols["rsi"][rp]
        return (~np.isnan(ef_v) & ~np.isnan(es_v) & ~np.isnan(rsi) & (ef_v > es_v) & (rsi < rt))
    if fam == 3:
        return cols["macd"][(ef, es)] == 1.0
    if fam == 4:  # Stochastic oversold
        k = cols["stoch"][stp]
        return ~np.isnan(k) & (k < sth)
    if fam == 5:  # Gap-down reversal: เปิด gap ลง >= gp% แล้วปิดเหนือ open (ฟื้น)
        gap = cols["gap"]; opn = cols["open"]
        return ~np.isnan(gap) & (gap <= -gp) & (close > opn)
    # fam == 6: Volume-spike breakout: วอลุ่ม >= vm× SMA20 + ปิดเหนือ donchian
    dh = cols["donch"][dn]; vol = cols["vol"]; vsma = cols["volsma20"]
    return (~np.isnan(dh) & ~np.isnan(vsma) & (vol >= vm * vsma) & (close > dh))


def _simulate(entry, atr_e, h_cols, l_cols, c_cols, exit_mode, tp_val, sl_val,
              hold_days, skip_tp_day1=False):
    """Bracket simulation.
    skip_tp_day1: ใช้กับ limit entry — วันที่ order ติด (day1) เช็คได้เฉพาะ SL
    (conservative: ไม่รู้ว่า High เกิดก่อนหรือหลังติด order จึงไม่นับ TP วันนั้น).
    สัญญาณชนกันในแท่งเดียว (High>=TP และ Low<=SL): เคลียร์ด้วย TIE_BREAK_SL_WINS —
    ค่าเริ่มต้น SL ชนะ (นับเป็นแพ้) เพราะไม่รู้ลำดับ intraday — ห้ามเดาเข้าข้างตัวเอง."""
    n = len(entry)
    if exit_mode == 0:
        tp = entry * (1 + tp_val/100); sl = entry * (1 - sl_val/100)
    else:
        tp = entry + tp_val * atr_e; sl = entry - sl_val * atr_e
    outcome = np.zeros(n, dtype=np.int8)
    exit_price = c_cols[hold_days].copy()
    resolved = np.zeros(n, dtype=bool)
    for k in range(1, hold_days + 1):
        h, l = h_cols[k], l_cols[k]
        tp_ok = np.zeros(n, dtype=bool) if (k == 1 and skip_tp_day1) else (h >= tp)
        sl_ok = (l <= sl)
        if TIE_BREAK_SL_WINS:
            # SL มาก่อน: แท่งที่ชนทั้งคู่นับเป็น SL (worst-case, ซื่อสัตย์)
            hit_sl = (~resolved) & sl_ok
            hit_tp = (~resolved) & (~hit_sl) & tp_ok
        else:
            # optimistic: TP มาก่อน (พฤติกรรมเดิม)
            hit_tp = (~resolved) & tp_ok
            hit_sl = (~resolved) & (~hit_tp) & sl_ok
        outcome[hit_tp] = 1; exit_price[hit_tp] = tp[hit_tp]
        outcome[hit_sl] = -1; exit_price[hit_sl] = sl[hit_sl]
        resolved = resolved | hit_tp | hit_sl
    return outcome, exit_price


def evaluate(cols, p) -> dict:
    (fam, rp, rt, bp, bs, dn, ef, es, exit_mode, tp_val, sl_val, ap, hd,
     adx_min, volf, stp, sth, gp, vm, emode, regf) = p
    sig = _entry_signal(cols, p) & cols["fwd_valid"][hd]
    if adx_min > 0:
        adxv = cols["adx"].get("adx14")
        if adxv is not None:
            sig = sig & (adxv >= adx_min)
    if volf:
        sig = sig & (cols["vol"] > cols["volsma20"])
    if regf:
        br = cols["breadth"]
        sig = sig & ~np.isnan(br) & (br > 0.5)
    if FRIDAY_ONLY:
        sig = sig & cols["weekend"]

    idx = np.where(sig)[0]
    if len(idx) == 0:
        return None

    if emode == 0:
        # market order ที่ราคาเปิดแท่งถัดไป (เดิม)
        entry = cols["entry"][idx]
        # guard: entry ต้อง finite และ > 0 (ตัดข้อมูลเสีย/ราคา 0 กันหารศูนย์)
        ok = np.isfinite(entry) & (entry > MIN_VALID_PRICE)
        idx, entry = idx[ok], entry[ok]
        skip_tp_day1 = False
    else:
        # limit order: ตั้งซื้อที่ close สัญญาณ * (1 - emode%) — ติดเฉพาะวันแรก
        close_sig = cols["close"][idx]
        limit = close_sig * (1 - emode / 100.0)
        l1 = cols["L"][1][idx]
        # limit ต้อง > 0 (close เสีย -> limit เพี้ยน) และแท่งแรกต้องแตะถึงจริง
        filled = (np.isfinite(l1) & np.isfinite(limit) & (limit > MIN_VALID_PRICE)
                  & (l1 <= limit))
        idx, entry = idx[filled], limit[filled]
        skip_tp_day1 = True
    if len(entry) == 0:
        return None

    atr_e = cols["atr"][ap][idx] if exit_mode == 1 else np.zeros(len(entry))
    if exit_mode == 1:
        # ATR ต้อง > 0 ด้วย: ATR=0 (ราคานิ่งสนิท) -> tp=entry -> ชนะทันทีจอมปลอม
        keep = np.isfinite(atr_e) & (atr_e > 0)
        idx, entry, atr_e = idx[keep], entry[keep], atr_e[keep]
        if len(entry) == 0:
            return None
    h_cols = {k: cols["H"][k][idx] for k in range(1, hd + 1)}
    l_cols = {k: cols["L"][k][idx] for k in range(1, hd + 1)}
    c_cols = {k: cols["C"][k][idx] for k in range(1, hd + 1)}
    outcome, exit_price = _simulate(entry, atr_e, h_cols, l_cols, c_cols,
                                    exit_mode, tp_val, sl_val, hd,
                                    skip_tp_day1=skip_tp_day1)
    ret_net = (exit_price / entry - 1) * 100 - FRICTION_PCT
    n_res = int((outcome != 0).sum())
    if n_res == 0:
        return None
    wins = int((outcome == 1).sum())
    return dict(n_signals=int(len(entry)), n_resolved=n_res,
                win_rate=round(wins/n_res*100, 2),
                wilson_lb=round(wilson_lb(wins, n_res)*100, 2),
                avg_net=round(float(ret_net.mean()), 2),
                median_net=round(float(np.median(ret_net)), 2),
                entry_family=fam, rsi_period=rp, rsi_threshold=rt, bb_period=bp, bb_std=bs,
                donchian_n=dn, ema_fast=ef, ema_slow=es, exit_mode=exit_mode,
                tp_val=tp_val, sl_val=sl_val, atr_period=ap, hold_days=hd,
                adx_min=adx_min, vol_filter=volf, entry_mode=emode, regime_filter=regf)


def iter_combos(n_target: int, seed: int):
    """สุ่ม combo พารามิเตอร์แบบไม่ซ้ำ (deterministic ต่อ seed).
    เดิม dedup ด้วย set ของ tuple 21 มิติ -> 3M combo กิน RAM ~1GB (เสี่ยง OOM บน Colab).
    แก้ [กลาง/perf]: dedup ด้วย 'ดัชนีจำนวนเต็มเดียว' ต่อ combo (set ของ int) แล้ว
    ถอดรหัสแบบ mixed-radix -> ลด RAM ~5-10 เท่า, การกระจายยังสม่ำเสมอเท่าเดิม."""
    keys = list(SPACE.keys())
    sizes = [len(SPACE[k]) for k in keys]
    total = 1
    for s in sizes:
        total *= s
    if n_target >= total:
        yield from itertools.product(*[SPACE[k] for k in keys])
        return
    rng = np.random.default_rng(seed)
    seen = set()                       # เก็บ int (เบากว่า tuple มาก)
    n_dims = len(sizes)
    while len(seen) < n_target:
        r = int(rng.integers(0, total))
        if r in seen:
            continue
        seen.add(r)
        # ถอด r -> ดัชนีแต่ละมิติ (mixed-radix): บิเจกชัน r <-> combo หนึ่งเดียว
        combo = [None] * n_dims
        x = r
        for i in range(n_dims - 1, -1, -1):
            x, digit = divmod(x, sizes[i])
            combo[i] = SPACE[keys[i]][digit]
        yield tuple(combo)


def run_search(data: pd.DataFrame, n_target: int, seed: int) -> pd.DataFrame:
    cache = build_cache(data)
    survivors = []
    t0 = time.time()
    i = 0
    for i, p in enumerate(iter_combos(n_target, seed), 1):
        r = evaluate(cache, p)
        if r and r["win_rate"] >= WIN_RATE_MIN and r["avg_net"] >= NET_RETURN_MIN \
                and r["median_net"] > 0 and r["n_resolved"] >= MIN_RESOLVED:
            survivors.append(r)
        if i % 200_000 == 0:
            el = time.time() - t0
            print(f"  [{datetime.now():%H:%M:%S}] {i:,}/{n_target:,} ({el:.0f}s, {i/el:.0f}/s) "
                  f"| ผ่านเกณฑ์: {len(survivors)}", flush=True)
    print(f"  เสร็จ {i:,} combo ใน {time.time()-t0:.0f}s | ผ่านเกณฑ์: {len(survivors)}")
    return pd.DataFrame(survivors)


PARAM_KEYS = ["entry_family", "rsi_period", "rsi_threshold", "bb_period", "bb_std",
              "donchian_n", "ema_fast", "ema_slow", "exit_mode", "tp_val", "sl_val",
              "atr_period", "hold_days", "adx_min", "vol_filter", "stoch_period",
              "stoch_th", "gap_pct", "vol_mult", "entry_mode", "regime_filter"]


# มิติที่ต้องเป็น int (ใช้เป็น index/range/dict key) — ที่เหลือรักษา float ไว้
INT_PARAM_KEYS = {"entry_family", "rsi_period", "bb_period", "donchian_n", "ema_fast",
                  "ema_slow", "exit_mode", "atr_period", "hold_days", "adx_min",
                  "vol_filter", "stoch_period", "entry_mode", "regime_filter"}


def _params_from_row(c) -> tuple:
    """แปลงแถว survivor -> param tuple โดยรักษาชนิดตัวเลข.
    แก้บั๊กแฝง [สูง]: โค้ดเดิม int() ทุกค่ายกเว้น bb_std ทำให้ tp/sl/threshold
    ที่เป็นทศนิยม (เช่น 2.5) ถูกปัดทิ้งเงียบ ๆ -> validate คนละสมการกับที่ค้นพบ."""
    return tuple(int(c[k]) if k in INT_PARAM_KEYS else float(c[k]) for k in PARAM_KEYS)


def validate_oos(data_out: pd.DataFrame, survivors: pd.DataFrame) -> pd.DataFrame:
    if survivors.empty:
        return pd.DataFrame()
    cache = build_cache(data_out)
    rows = []
    for _, c in survivors.iterrows():
        p = _params_from_row(c)
        r = evaluate(cache, p)
        rows.append(dict(
            **{k: c[k] for k in PARAM_KEYS},
            in_n=c.n_resolved, in_wr=c.win_rate, in_net=c.avg_net, in_med=c.median_net,
            oos_signals=(r["n_signals"] if r else 0),
            oos_resolved=(r["n_resolved"] if r else 0),
            oos_wr=(r["win_rate"] if r else None),
            oos_wilson_lb=(r["wilson_lb"] if r else None),
            oos_net=(r["avg_net"] if r else None),
            oos_med=(r["median_net"] if r else None)))
    return pd.DataFrame(rows)


FAMILY_NAME = {0: "MEAN_REVERSION", 1: "BREAKOUT", 2: "TREND_PULLBACK", 3: "MACD_CROSS",
               4: "STOCH_OVERSOLD", 5: "GAP_DOWN_REVERSAL", 6: "VOLSPIKE_BREAKOUT"}


def compute_breadth(raw: pd.DataFrame) -> pd.Series:
    """Breadth ต่อวัน (สัดส่วนหุ้นที่ Close > SMA50) จากทั้ง universe — คำนวณครั้งเดียว.
    แก้บั๊ก [กลาง/perf]: เดิม build_trade_report คำนวณซ้อนลูปต่อหุ้น O(n^2)
    (SET100: ~10,201 rolling ops) -> O(n) (101 ops, ลด ~99%)."""
    parts = []
    for _, g in raw.groupby("Ticker", sort=False):
        g = g.sort_values("Date")
        s50 = g["Close"].rolling(50).mean()
        parts.append(pd.DataFrame({
            "Date": g["Date"].values,
            "above": (g["Close"] > s50).astype(float).where(s50.notna()).values,
        }))
    allp = pd.concat(parts, ignore_index=True)
    return allp.groupby("Date")["above"].mean()


def _latest_bar_signal(g: pd.DataFrame, b, breadth_by_date: pd.Series):
    """เช็คแท่งล่าสุดของหุ้น 1 ตัวกับสมการ 1 แถว (row จาก confirmed).
    คืน dict รายละเอียดออร์เดอร์ถ้าเข้าเงื่อนไข, ไม่เข้า -> None.
    Layer 1 — pure. ใช้ร่วมกันโดย build_trade_report และ VerdictAgent."""
    i = len(g) - 1
    if i < max(SPACE["ema_slow"]):
        return None
    close = g["Close"]
    fam = int(b.entry_family)
    if fam == 0:
        rsi = wilder_rsi(close, int(b.rsi_period))
        mid = close.rolling(int(b.bb_period)).mean()
        std = close.rolling(int(b.bb_period)).std()
        bb = mid - float(b.bb_std) * std
        cond = (not np.isnan(rsi.iloc[i])) and (rsi.iloc[i] < b.rsi_threshold) and (close.iloc[i] < bb.iloc[i])
    elif fam == 1:
        dh = close.rolling(int(b.donchian_n)).max().shift(1)
        cond = (not np.isnan(dh.iloc[i])) and (close.iloc[i] > dh.iloc[i])
    elif fam == 2:
        ef_v = ema(close, int(b.ema_fast)); es_v = ema(close, int(b.ema_slow))
        rsi = wilder_rsi(close, int(b.rsi_period))
        cond = (ef_v.iloc[i] > es_v.iloc[i]) and (rsi.iloc[i] < b.rsi_threshold)
    elif fam == 3:
        cond = bool(macd_cross_up(close, int(b.ema_fast), int(b.ema_slow)).iloc[i])
    elif fam == 4:
        k = stoch_k(g["High"], g["Low"], close, int(getattr(b, "stoch_period", 14)))
        cond = (not np.isnan(k.iloc[i])) and (k.iloc[i] < float(getattr(b, "stoch_th", 20)))
    elif fam == 5:
        gap = (g["Open"] / close.shift(1) - 1) * 100
        cond = (not np.isnan(gap.iloc[i])) and (gap.iloc[i] <= -float(getattr(b, "gap_pct", 2.0))) \
            and (close.iloc[i] > g["Open"].iloc[i])
    else:  # fam == 6: Volume-spike breakout
        dh = close.rolling(int(b.donchian_n)).max().shift(1)
        vsma = g["Volume"].rolling(20).mean()
        cond = (not np.isnan(dh.iloc[i])) and (not np.isnan(vsma.iloc[i])) \
            and (g["Volume"].iloc[i] >= float(getattr(b, "vol_mult", 2.0)) * vsma.iloc[i]) \
            and (close.iloc[i] > dh.iloc[i])
    if cond and b.adx_min > 0:
        adxv = adx(g["High"], g["Low"], close, 14)
        cond = (not np.isnan(adxv.iloc[i])) and (adxv.iloc[i] >= b.adx_min)
    if cond and int(b.vol_filter) == 1:
        cond = g["Volume"].iloc[i] > g["Volume"].rolling(20).mean().iloc[i]
    if cond and int(getattr(b, "regime_filter", 0)) == 1:
        br = breadth_by_date.get(g["Date"].iloc[i], np.nan)
        cond = (not np.isnan(br)) and (br > 0.5)
    if not cond:
        return None
    emode = int(getattr(b, "entry_mode", 0))
    close_ref = float(close.iloc[i])
    # market = อ้างอิงราคาปิดล่าสุด (ตั้งซื้อเปิดจันทร์); limit = ตั้งซื้อ close*(1-emode%)
    entry_ref = close_ref if emode == 0 else close_ref * (1 - emode / 100.0)
    if int(b.exit_mode) == 0:
        tp_p = entry_ref * (1 + b.tp_val / 100)
        sl_p = entry_ref * (1 - b.sl_val / 100)
    else:
        a = atr(g["High"], g["Low"], close, int(b.atr_period)).iloc[i]
        if np.isnan(a):
            return None
        tp_p = entry_ref + b.tp_val * a
        sl_p = entry_ref - b.sl_val * a
    cost1 = entry_ref * BOARD_LOT
    lots = int(BUDGET_PER_TRADE_THB // cost1) if cost1 > 0 else 0
    return dict(
        order_type=("Market@Open" if emode == 0 else f"Limit -{emode}% (ตั้งซื้อ)"),
        buy_at=round(entry_ref, 2), sell_tp=round(float(tp_p), 2),
        stop_sl=round(float(sl_p), 2), cost_1lot=round(cost1, 2), lots=lots,
        budget_ok=bool(lots >= 1),
        hold_days=int(b.hold_days), entry_mode=emode,
        signal_date=g["Date"].iloc[i].strftime("%Y-%m-%d"),
        strategy=FAMILY_NAME[fam])


def build_trade_report(raw: pd.DataFrame, confirmed: pd.DataFrame) -> pd.DataFrame:
    """รายงานสัญญาณจากสมการอันดับ 1 (พฤติกรรม/คอลัมน์เดิมคงไว้ทั้งหมด)."""
    if confirmed.empty:
        return pd.DataFrame()
    b = confirmed.sort_values("oos_net", ascending=False).iloc[0]
    breadth_by_date = compute_breadth(raw)
    signals = []
    for tk, g in raw.groupby("Ticker", sort=False):
        g = g.sort_values("Date").reset_index(drop=True)
        s = _latest_bar_signal(g, b, breadth_by_date)
        if s is not None:
            signals.append(dict(Ticker=tk, SignalDate=s["signal_date"], Strategy=s["strategy"],
                                OrderType=s["order_type"], BuyAt=s["buy_at"],
                                SellTP=s["sell_tp"], StopSL=s["stop_sl"],
                                Cost1Lot=s["cost_1lot"], Lots=s["lots"], InBudget=s["budget_ok"]))
    return pd.DataFrame(signals)


# ==================== VERDICT AGENT (Layer 1 — Trading Domain) ====================
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class TickerVerdict:
    """ผลฟันธงราย ticker — frozen เพื่อ determinism/เทียบเท่ากันได้."""
    ticker: str
    action: str               # "เข้า (TRADE)" | "เฝ้าดู (WATCH)"
    agree_count: int          # กี่สมการจาก Top-K ที่ยิงสัญญาณตรงกัน
    of_k: int
    order_type: str
    buy_at: float
    sell_tp: float
    stop_sl: float
    lots: int
    budget_ok: bool
    min_oos_wilson_lb: float  # ขอบล่าง 95% ของ win rate ต่ำสุดในกลุ่มที่เห็นตรงกัน
    expected_oos_net: float   # กำไร OOS ที่สมการดีสุด(ที่ยิง)คาดไว้ — ใช้เทียบผลจริง
    expected_oos_wr: float
    reasons: str
    hold_days: int = 5        # [แก้บั๊กกลาง] พกจากสมการจริง — เดิม journal ตอกตาย 5
    entry_mode: int = 0       # [แก้บั๊กต่ำ] เลิก parse จาก string order_type


@dataclass(frozen=True)
class VerdictReport:
    overall: str
    k_used: int
    verdicts: tuple           # tuple[TickerVerdict, ...]


class VerdictAgent:
    """เอเจนท์ฟันธงการเทรด — Layer 1, Trading Domain (pure, deterministic).

    Agent Contract:
      input : raw OHLCV ทุกหุ้น + confirmed strategies (ผ่าน out-of-sample แล้ว)
      output: VerdictReport — ไม่มี side effect, input เดิมให้ output เดิมเสมอ

    หลักการ: ฟันธงด้วย "ฉันทามติ" ของสมการ Top-K ที่ผ่าน OOS ตามข้อกำหนดเดิม
    ของผู้ใช้ (หลายสมการต้องบอกตรงกัน โดยไม่โกหก):
      เข้า (TRADE)  : >= min_agree สมการยิงหุ้นเดียวกัน และงบพอ >= 1 lot
      เฝ้าดู (WATCH): มีสัญญาณแต่ฉันทามติ/งบไม่ถึงเกณฑ์
      confirmed ว่าง: ฟันธง "ไม่เข้า" — คำตอบซื่อสัตย์ ไม่ใช่ข้อบกพร่อง
    ข้อจำกัดที่แจ้งตรง: ยังไม่เช็ค concentration ราย ticker (ต้องมี OOS trade log เพิ่ม)."""

    def __init__(self, top_k: int = 5, min_agree: int = 3):
        if top_k < 1 or min_agree < 1:
            raise ValueError("top_k และ min_agree ต้อง >= 1")
        self.top_k = top_k
        self.min_agree = min_agree

    def decide(self, raw: pd.DataFrame, confirmed: pd.DataFrame) -> VerdictReport:
        if confirmed is None or confirmed.empty:
            return VerdictReport(
                overall="ไม่เข้า (NO_TRADE) — ไม่มีสมการผ่าน out-of-sample สัปดาห์นี้",
                k_used=0, verdicts=tuple())
        top = confirmed.sort_values("oos_net", ascending=False).head(self.top_k)
        k = len(top)
        eff_min = min(self.min_agree, k)
        breadth_by_date = compute_breadth(raw)

        hits_by_ticker = {}
        for tk, g in raw.groupby("Ticker", sort=False):
            g = g.sort_values("Date").reset_index(drop=True)
            hits = []
            for _, b in top.iterrows():
                s = _latest_bar_signal(g, b, breadth_by_date)
                if s is not None:
                    hits.append((s, float(b.oos_wilson_lb), float(b.oos_net), float(b.oos_wr)))
            if hits:
                hits_by_ticker[tk] = hits

        verdicts = []
        for tk in sorted(hits_by_ticker):
            hits = hits_by_ticker[tk]
            agree = len(hits)
            best = hits[0][0]  # ออร์เดอร์ของสมการอันดับดีสุดที่ยิงสัญญาณตัวนี้
            min_wlb = round(min(h[1] for h in hits), 2)
            reasons = []
            if k < self.min_agree:
                reasons.append(f"สมการยืนยันมีเพียง {k} — ต่ำกว่าเกณฑ์ฉันทามติ {self.min_agree}")
            if not best["budget_ok"]:
                reasons.append(f"งบไม่พอ 1 lot (ต้องใช้ {best['cost_1lot']:,.0f} บาท)")
            if agree >= eff_min and best["budget_ok"]:
                action = "เข้า (TRADE)"
            else:
                action = "เฝ้าดู (WATCH)"
                if agree < eff_min:
                    reasons.append(f"ฉันทามติ {agree}/{k} ต่ำกว่าเกณฑ์ {eff_min}")
            verdicts.append(TickerVerdict(
                ticker=tk, action=action, agree_count=agree, of_k=k,
                order_type=best["order_type"], buy_at=best["buy_at"],
                sell_tp=best["sell_tp"], stop_sl=best["stop_sl"], lots=best["lots"],
                budget_ok=best["budget_ok"], min_oos_wilson_lb=min_wlb,
                expected_oos_net=round(hits[0][2], 2), expected_oos_wr=round(hits[0][3], 2),
                reasons="; ".join(reasons) if reasons else "-",
                hold_days=best["hold_days"], entry_mode=best["entry_mode"]))
        verdicts.sort(key=lambda v: (-v.agree_count, v.ticker))

        n_trade = sum(1 for v in verdicts if v.action.startswith("เข้า"))
        if n_trade > 0:
            overall = f"เข้า {n_trade} ตัว (ฉันทามติ >= {eff_min}/{k} สมการ + งบพอ)"
        elif verdicts:
            overall = "เฝ้าดูอย่างเดียว — มีสัญญาณแต่ยังไม่ถึงเกณฑ์ฉันทามติ/งบ"
        else:
            overall = "ไม่เข้า (NO_TRADE) — สัปดาห์นี้ไม่มีหุ้นเข้าเงื่อนไขสมการที่ยืนยันแล้ว"
        return VerdictReport(overall=overall, k_used=k, verdicts=tuple(verdicts))


# ============== TRADE JOURNAL / TRACK RECORD (Layer 1 — Trading+Reporting) ==============
JOURNAL_COLUMNS = ["signal_date", "ticker", "order_type", "entry_mode", "buy_ref",
                   "sell_tp", "stop_sl", "hold_days", "action", "status",
                   "fill_price", "exit_date", "exit_price", "net_return_pct",
                   "expected_wr", "expected_net", "run_date"]
# status: PENDING -> FILLED_TP | FILLED_SL | FILLED_TIME | NOT_FILLED | NO_DATA


def load_journal(path: str = JOURNAL_PATH) -> pd.DataFrame:
    """โหลดสมุดบันทึก; ไม่มีไฟล์ -> DataFrame ว่างคอลัมน์ครบ.
    Backward compatible: ไฟล์เก่าที่ขาดคอลัมน์ใหม่จะถูกเติมอัตโนมัติ (additive versioning)."""
    if not os.path.exists(path):
        return pd.DataFrame(columns=JOURNAL_COLUMNS)
    j = pd.read_csv(path)
    for c in JOURNAL_COLUMNS:
        if c not in j.columns:
            j[c] = np.nan
    return j[JOURNAL_COLUMNS]


def save_journal(j: pd.DataFrame, path: str = JOURNAL_PATH) -> None:
    j.to_csv(path, index=False)


def _safe_int(val, default: int) -> int:
    """แปลงเป็น int อย่างปลอดภัย — NaN/None/ค่าเสีย -> default (กัน int(NaN) crash)."""
    try:
        if val is None or (isinstance(val, float) and not np.isfinite(val)) or pd.isna(val):
            return default
        return int(float(val))
    except (ValueError, TypeError):
        return default


def _safe_float(val) -> float:
    """แปลงเป็น float อย่างปลอดภัย — ค่าเสีย -> NaN (ให้ผู้เรียกตัดสินใจต่อ)."""
    try:
        f = float(val)
        return f
    except (ValueError, TypeError):
        return float("nan")


def resolve_journal(journal: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """ตัดสินผลออร์เดอร์ PENDING ด้วยราคาสดที่เพิ่งดึง — กติกาเดียวกับ backtest เป๊ะ:
    market: เข้าที่ Open แท่งแรกหลังวันสัญญาณ, TP เช็คก่อน SL ทุกแท่ง
    limit : ติดเฉพาะแท่งแรก (Low<=buy_ref) เข้าที่ buy_ref; แท่งที่ติดเช็คได้เฉพาะ SL
            (conservative — ไม่รู้ลำดับ intraday); ไม่ติด -> NOT_FILLED (ยกเลิกฟรี)
    ครบ hold_days ไม่ชนอะไร -> FILLED_TIME ที่ราคาปิดแท่งสุดท้าย; แท่งยังไม่ครบ -> คง PENDING"""
    if journal.empty:
        return journal
    j = journal.copy()
    # บั๊กจริง [กลาง]: คอลัมน์ NaN ล้วนจาก CSV ถูกอนุมานเป็น float64 ->
    # เขียน string ("FILLED_TP"/วันที่) ลงไปแล้ว crash (LossySetitemError)
    for col in ("status", "exit_date", "order_type", "action"):
        j[col] = j[col].astype(object)
    by_ticker = {tk: g.sort_values("Date").reset_index(drop=True)
                 for tk, g in raw.groupby("Ticker", sort=False)}
    for idx, row in j[j["status"] == "PENDING"].iterrows():
        tk = row["ticker"]
        if tk not in by_ticker:
            j.loc[idx, "status"] = "NO_DATA"
            continue
        g = by_ticker[tk]
        fut = g[pd.to_datetime(g["Date"]) > pd.to_datetime(row["signal_date"])].reset_index(drop=True)
        if fut.empty:
            continue
        # crash guard [ร้าย]: journal เก่าที่ขาดคอลัมน์ -> load_journal เติม NaN ->
        # int(NaN) เดิม crash (ValueError). ใช้ค่า default ที่ปลอดภัยแทน
        hold = _safe_int(row["hold_days"], default=5)
        emode = _safe_int(row["entry_mode"], default=0)
        tp, sl = _safe_float(row["sell_tp"]), _safe_float(row["stop_sl"])
        # ถ้า tp/sl เสีย (NaN) ตัดสินผลไม่ได้ -> คง PENDING ไว้ (ไม่เดา)
        if not (np.isfinite(tp) and np.isfinite(sl)):
            continue
        if emode == 0:
            entry = float(fut["Open"].iloc[0])
            start_k, skip_tp_first = 0, False
        else:
            buy_ref = _safe_float(row["buy_ref"])
            if not (np.isfinite(buy_ref) and buy_ref > MIN_VALID_PRICE):
                continue                    # buy_ref เสีย -> ตัดสินไม่ได้ คง PENDING
            if float(fut["Low"].iloc[0]) > buy_ref:
                j.loc[idx, "status"] = "NOT_FILLED"
                continue
            entry = buy_ref
            start_k, skip_tp_first = 0, True
        if not (np.isfinite(entry) and entry > MIN_VALID_PRICE):
            continue                        # entry เสีย (Open=0/NaN) -> คง PENDING
        outcome, exit_price, exit_date = None, None, None
        n_avail = min(hold, len(fut))
        for k in range(start_k, n_avail):
            hi, lo = float(fut["High"].iloc[k]), float(fut["Low"].iloc[k])
            tp_hit = (not (skip_tp_first and k == 0)) and hi >= tp
            sl_hit = lo <= sl
            # เคลียร์ tie แบบเดียวกับ backtest: TIE_BREAK_SL_WINS -> เช็ค SL ก่อน
            if TIE_BREAK_SL_WINS and sl_hit:
                outcome, exit_price, exit_date = "FILLED_SL", sl, fut["Date"].iloc[k]
                break
            if tp_hit:
                outcome, exit_price, exit_date = "FILLED_TP", tp, fut["Date"].iloc[k]
                break
            if sl_hit:
                outcome, exit_price, exit_date = "FILLED_SL", sl, fut["Date"].iloc[k]
                break
        if outcome is None:
            if len(fut) >= hold:
                outcome = "FILLED_TIME"
                exit_price = float(fut["Close"].iloc[hold - 1])
                exit_date = fut["Date"].iloc[hold - 1]
            else:
                j.loc[idx, "fill_price"] = entry  # ติดแล้วแต่ยังไม่จบสัปดาห์
                continue
        j.loc[idx, "status"] = outcome
        j.loc[idx, "fill_price"] = entry
        j.loc[idx, "exit_price"] = exit_price
        j.loc[idx, "exit_date"] = pd.Timestamp(exit_date).strftime("%Y-%m-%d")
        j.loc[idx, "net_return_pct"] = round((exit_price / entry - 1) * 100 - FRICTION_PCT, 2)
    return j


def journal_stats(journal: pd.DataFrame) -> dict:
    """สถิติจริงสะสม — convention เดียวกับ backtest: WR นับเฉพาะ TP/SL,
    กำไรเฉลี่ยรวม TIME exit ด้วย (เทียบ apples-to-apples กับที่ระบบคาด)."""
    if journal.empty:
        return dict(n_orders=0)
    filled = journal[journal["status"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIME"])]
    resolved = filled[filled["status"].isin(["FILLED_TP", "FILLED_SL"])]
    wins = int((resolved["status"] == "FILLED_TP").sum())
    n_res = len(resolved)
    wr = round(wins / n_res * 100, 2) if n_res else None
    wlb = round(wilson_lb(wins, n_res) * 100, 2) if n_res else None
    avg_real = round(filled["net_return_pct"].astype(float).mean(), 2) if len(filled) else None
    avg_exp = round(filled["expected_net"].astype(float).mean(), 2) if len(filled) else None
    return dict(
        n_orders=len(journal),
        n_pending=int((journal["status"] == "PENDING").sum()),
        n_not_filled=int((journal["status"] == "NOT_FILLED").sum()),
        n_filled=len(filled), n_resolved=n_res, wins=wins,
        realized_wr=wr, realized_wilson_lb=wlb,
        realized_avg_net=avg_real, expected_avg_net=avg_exp,
        gap=(round(avg_real - avg_exp, 2) if avg_real is not None and avg_exp is not None else None))


def append_new_verdicts(journal: pd.DataFrame, vr, run_date: str) -> pd.DataFrame:
    """บันทึกเฉพาะคำฟันธง 'เข้า (TRADE)' (= ออร์เดอร์ที่วางจริง) แบบ idempotent:
    (signal_date, ticker) ซ้ำจะไม่ถูกเพิ่มซ้ำ — รันวันเดียวกันหลายรอบได้ปลอดภัย."""
    existing = set(zip(journal["signal_date"].astype(str), journal["ticker"].astype(str))) if not journal.empty else set()
    rows = []
    for v in vr.verdicts:
        if not v.action.startswith("เข้า"):
            continue
        sig_date = run_date
        if (sig_date, v.ticker) in existing:
            continue
        rows.append(dict(signal_date=sig_date, ticker=v.ticker, order_type=v.order_type,
                         entry_mode=int(v.entry_mode),
                         buy_ref=v.buy_at, sell_tp=v.sell_tp, stop_sl=v.stop_sl,
                         hold_days=int(v.hold_days), action=v.action, status="PENDING",
                         fill_price=np.nan, exit_date=np.nan, exit_price=np.nan,
                         net_return_pct=np.nan, expected_wr=v.expected_oos_wr,
                         expected_net=v.expected_oos_net, run_date=run_date))
    if not rows:
        return journal
    return pd.concat([journal, pd.DataFrame(rows, columns=JOURNAL_COLUMNS)], ignore_index=True)


def print_track_record(stats: dict) -> None:
    print("\n" + "=" * 72)
    print("TRACK RECORD — ผลจริงสะสมจากคำฟันธงในอดีต (คำตอบของ 'แม่นมั้ย')")
    if stats.get("n_orders", 0) == 0:
        print("  ยังไม่มีประวัติ — ระบบเริ่มบันทึกอัตโนมัติจากรอบนี้")
        return
    print(f"  ออร์เดอร์สะสม {stats['n_orders']} | ยังไม่จบ {stats['n_pending']} "
          f"| limit ไม่ติด {stats['n_not_filled']}")
    if stats["n_resolved"]:
        print(f"  จบแล้ว {stats['n_resolved']} ไม้ -> ชนะ {stats['wins']} "
              f"(WR จริง {stats['realized_wr']}% | Wilson LB {stats['realized_wilson_lb']}%)")
    if stats["realized_avg_net"] is not None:
        print(f"  กำไรสุทธิเฉลี่ยจริง {stats['realized_avg_net']}%/ไม้ "
              f"| ระบบคาดไว้ {stats['expected_avg_net']}% | ส่วนต่าง {stats['gap']}")
    print("=" * 72)


# ================= DASHBOARD (Layer 1 — Reporting Domain, ธีม Claude) =================
# Pure function: data -> HTML string (ทดสอบได้, ไม่มี side effect). แสดงผ่าน IPython ใน main.
# ธีม: ivory อุ่น #FAF9F5 + coral #D97757 + น้ำตาลเข้ม #29261B — สบายตา, Chart.js CDN (vanilla JS)

_STATUS_TH = {"FILLED_TP": ("ชนะ (TP)", "#6E8B5E"), "FILLED_SL": ("แพ้ (SL)", "#C24C3F"),
              "FILLED_TIME": ("หมดเวลา", "#8A8375"), "PENDING": ("รอผล", "#C9A227"),
              "NOT_FILLED": ("limit ไม่ติด", "#A39B8B"), "NO_DATA": ("ไม่มีข้อมูล", "#999999")}

_DASH_CSS = """
:root{--bg:#FAF9F5;--card:#FFFFFF;--line:#E8E4DA;--ink:#29261B;--sub:#6B6558;
--coral:#D97757;--coral-dk:#C05F3C;--green:#6E8B5E;--red:#C24C3F;--amber:#C9A227}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans Thai",sans-serif;
font-size:15px;line-height:1.55;padding:24px}
.wrap{max-width:1060px;margin:0 auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:0 0 12px;color:var(--coral-dk)}
.sub{color:var(--sub);font-size:13px;margin-bottom:18px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;
padding:4px 12px;font-size:12.5px;color:var(--sub)}
.chip.ok{border-color:var(--green);color:var(--green)}
.chip.warn{border-color:var(--amber);color:var(--amber)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:18px 20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(41,38,27,.05)}
.hero{border-left:5px solid var(--coral)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.tile{background:var(--bg);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile .v{font-size:20px;font-weight:600}.tile .k{font-size:12px;color:var(--sub)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.grid2{grid-template-columns:1fr}}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{color:var(--sub);font-weight:600;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--line)}
.pill{display:inline-block;border-radius:999px;padding:2px 10px;font-size:12px;color:#fff}
.vcard{border:1px solid var(--line);border-left:4px solid var(--coral);border-radius:10px;
padding:12px 14px;margin-bottom:10px;background:var(--bg)}
.vcard.watch{border-left-color:var(--amber)}
.vcard b{font-size:15px}.muted{color:var(--sub);font-size:12.5px}
.big{font-size:17px;font-weight:600}.pos{color:var(--green)}.neg{color:var(--red)}
.empty{color:var(--sub);font-style:italic;padding:8px 0}
footer{color:var(--sub);font-size:12px;margin-top:8px}
"""


def _fmt(x, suf=""):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x}{suf}"


def generate_dashboard(run_info: dict, stats: dict, journal: pd.DataFrame,
                       vr, confirmed: pd.DataFrame) -> str:
    """สร้าง HTML แดชบอร์ดทั้งหน้า (self-contained ยกเว้น Chart.js CDN)."""
    # ---- chips ----
    fri = ('<span class="chip ok">✓ แท่งศุกร์</span>' if run_info.get("friday_ok")
           else '<span class="chip warn">⚠ แท่งล่าสุดไม่ใช่ศุกร์</span>')
    chips = (f'<span class="chip">{run_info["universe"]} · {run_info["n_tickers"]} หุ้น</span>'
             f'<span class="chip">แท่งล่าสุด {run_info["last_bar"]}</span>{fri}'
             f'<span class="chip">เป้า WR≥{run_info["wr_min"]:.0f}% & Net≥{run_info["net_min"]}%</span>'
             f'<span class="chip">ค้นหา {run_info["n_target"]:,} แบบ</span>')

    # ---- verdict hero ----
    vcards = ""
    if vr is not None and vr.verdicts:
        for v in vr.verdicts:
            cls = "vcard" if v.action.startswith("เข้า") else "vcard watch"
            rs = "" if v.reasons == "-" else f'<div class="muted">เหตุผล: {v.reasons}</div>'
            vcards += (f'<div class="{cls}"><b>{v.ticker}</b> — {v.action} '
                       f'<span class="muted">({v.agree_count}/{v.of_k} สมการเห็นตรงกัน · '
                       f'Wilson LB {v.min_oos_wilson_lb}%)</span><br>'
                       f'{v.order_type} · ตั้งซื้อ <b>{v.buy_at}</b> · ขาย TP <b>{v.sell_tp}</b> · '
                       f'ตัดขาดทุน <b>{v.stop_sl}</b> · {v.lots} lot · ถือสูงสุด {v.hold_days} วัน{rs}</div>')
    else:
        vcards = '<div class="empty">สัปดาห์นี้: ไม่มีคำสั่งเข้า</div>'
    overall = vr.overall if vr is not None else "-"

    # ---- track record tiles ----
    n_orders = stats.get("n_orders", 0)
    if n_orders:
        wr_txt = _fmt(stats.get("realized_wr"), "%")
        wlb_txt = _fmt(stats.get("realized_wilson_lb"), "%")
        real = stats.get("realized_avg_net"); exp = stats.get("expected_avg_net")
        gap = stats.get("gap")
        gap_cls = "pos" if (gap is not None and gap >= 0) else "neg"
        tiles = f"""
        <div class="tiles">
          <div class="tile"><div class="v">{n_orders}</div><div class="k">ออร์เดอร์สะสม</div></div>
          <div class="tile"><div class="v">{stats.get('n_pending',0)}</div><div class="k">รอผล</div></div>
          <div class="tile"><div class="v">{stats.get('n_not_filled',0)}</div><div class="k">limit ไม่ติด</div></div>
          <div class="tile"><div class="v">{wr_txt}</div><div class="k">WR จริง (Wilson LB {wlb_txt})</div></div>
          <div class="tile"><div class="v">{_fmt(real,'%')}</div><div class="k">กำไรจริงเฉลี่ย/ไม้</div></div>
          <div class="tile"><div class="v">{_fmt(exp,'%')} → <span class="{gap_cls}">{_fmt(gap)}</span></div>
               <div class="k">คาดไว้ → ส่วนต่างจริง</div></div>
        </div>"""
    else:
        tiles = '<div class="empty">ยังไม่มีประวัติ — ระบบเริ่มบันทึกอัตโนมัติจากรอบนี้</div>'

    # ---- charts data ----
    filled = journal[journal["status"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIME"])].copy() \
        if not journal.empty else pd.DataFrame()
    charts_html, charts_js = "", ""
    if len(filled):
        filled = filled.sort_values("exit_date")
        labels = [str(x) for x in filled["exit_date"].tolist()]
        cum = filled["net_return_pct"].astype(float).cumsum().round(2).tolist()
        counts = journal["status"].value_counts()
        d_labels = [_STATUS_TH.get(s, (s, "#999"))[0] for s in counts.index]
        d_colors = [_STATUS_TH.get(s, (s, "#999"))[1] for s in counts.index]
        d_values = [int(x) for x in counts.values]
        charts_html = """
        <div class="grid2">
          <div class="card"><h2>กำไรสะสมจริง (%)</h2><canvas id="cum" height="210"></canvas></div>
          <div class="card"><h2>สัดส่วนสถานะออร์เดอร์</h2><canvas id="mix" height="210"></canvas></div>
        </div>"""
        charts_js = f"""
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
        const C='#D97757';
        new Chart(document.getElementById('cum'),{{type:'line',
          data:{{labels:{json.dumps(labels)},datasets:[{{data:{json.dumps(cum)},
            borderColor:C,backgroundColor:'rgba(217,119,87,.12)',fill:true,tension:.3,pointRadius:3}}]}},
          options:{{plugins:{{legend:{{display:false}}}},scales:{{y:{{grid:{{color:'#EFEBE0'}}}},x:{{grid:{{display:false}}}}}}}}}});
        new Chart(document.getElementById('mix'),{{type:'doughnut',
          data:{{labels:{json.dumps(d_labels, ensure_ascii=False)},
                datasets:[{{data:{json.dumps(d_values)},backgroundColor:{json.dumps(d_colors)},borderWidth:0}}]}},
          options:{{plugins:{{legend:{{position:'bottom'}}}},cutout:'62%'}}}});
        </script>"""
    else:
        charts_html = ('<div class="card"><h2>กราฟผลจริง</h2>'
                       '<div class="empty">ยังไม่มีไม้ที่จบ — กราฟจะปรากฏเมื่อมีผลจริงสะสม</div></div>')

    # ---- journal table (ล่าสุด 15) ----
    if not journal.empty:
        rows = ""
        for _, r in journal.tail(15).iloc[::-1].iterrows():
            th, color = _STATUS_TH.get(str(r["status"]), (str(r["status"]), "#999"))
            net = r["net_return_pct"]
            net_html = "-" if pd.isna(net) else f'<span class="{"pos" if float(net) >= 0 else "neg"}">{net}%</span>'
            rows += (f'<tr><td>{r["signal_date"]}</td><td><b>{r["ticker"]}</b></td>'
                     f'<td>{r["order_type"]}</td><td>{r["buy_ref"]}</td><td>{r["sell_tp"]}</td>'
                     f'<td>{r["stop_sl"]}</td><td><span class="pill" style="background:{color}">{th}</span></td>'
                     f'<td>{net_html}</td></tr>')
        journal_html = f"""<table><tr><th>วันสัญญาณ</th><th>หุ้น</th><th>ออร์เดอร์</th>
        <th>ตั้งซื้อ</th><th>TP</th><th>SL</th><th>สถานะ</th><th>กำไรสุทธิ</th></tr>{rows}</table>"""
    else:
        journal_html = '<div class="empty">สมุดบันทึกว่าง</div>'

    # ---- confirmed strategies ----
    if confirmed is not None and not confirmed.empty:
        want = ["strategy_name", "entry_mode", "tp_val", "sl_val", "hold_days",
                "oos_resolved", "oos_wr", "oos_wilson_lb", "oos_net"]
        cols = [c for c in want if c in confirmed.columns]
        head = "".join(f"<th>{c}</th>" for c in cols)
        body = "".join("<tr>" + "".join(f"<td>{r[c]}</td>" for c in cols) + "</tr>"
                        for _, r in confirmed.head(5).iterrows())
        conf_html = f"<table><tr>{head}</tr>{body}</table>"
    else:
        conf_html = '<div class="empty">รอบนี้ไม่มีสมการผ่าน out-of-sample</div>'

    return f"""<!DOCTYPE html><html lang="th"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SET Edge Finder — Dashboard</title><style>{_DASH_CSS}</style></head><body><div class="wrap">
<h1>🎯 SET Weekly Edge Finder</h1>
<div class="sub">รันเมื่อ {run_info['run_ts']} · เทรดรายสัปดาห์ · ตั้งซื้อเช้าวันจันทร์</div>
<div class="chips">{chips}</div>
<div class="card hero"><h2>คำฟันธงสัปดาห์นี้</h2><div class="big">{overall}</div>{vcards}</div>
<div class="card"><h2>Track Record — คำตอบของ "แม่นมั้ย"</h2>{tiles}</div>
{charts_html}
<div class="card"><h2>สมุดบันทึกออร์เดอร์ (ล่าสุด)</h2>{journal_html}</div>
<div class="card"><h2>สมการที่ยืนยันแล้ว (Top 5)</h2>{conf_html}</div>
<footer>Wilson LB = ความมั่นใจขั้นต่ำจริงทางสถิติ · ระบบไม่การันตีผลอนาคต · สร้างโดย set_edge_finder</footer>
</div>{charts_js}</body></html>"""


# ============================================================ MAIN (Colab run)
def main():
    print("="*72)
    print("SET WEEKLY STAT-EDGE FINDER v4 (FRIDAY-ANCHORED) — เริ่มทำงาน")
    print(f"universe={UNIVERSE} ({len(TICKERS)} ตัว) | FRIDAY_ONLY={FRIDAY_ONLY}")
    print(f"เป้า: WR>{WIN_RATE_MIN}% & กำไร(mean)>{NET_RETURN_MIN}% & median>0 | ค้นหา {N_TARGET:,} แบบ")
    print("กลยุทธ์: MR + Breakout + Pullback + MACD | entry: Market/Limit-1,2,3% | regime filter")
    print("="*72)

    raw = fetch_prices()
    last_bar = pd.to_datetime(raw["Date"]).max()
    print(f"\nแท่งข้อมูลล่าสุด: {last_bar:%Y-%m-%d} ({last_bar.strftime('%a')})")
    if last_bar.weekday() != 4:
        print("  ⚠ แท่งล่าสุดไม่ใช่วันศุกร์ — สัญญาณจะอ้างสัปดาห์ที่อาจยังไม่จบ")
    print("  วันรันที่แนะนำ: ศุกร์หลังตลาดปิด (>=18:00) หรือ เสาร์/อาทิตย์ | ตั้งคำสั่งซื้อเช้าวันจันทร์")

    # ---- Track Record: ตัดสินผลออร์เดอร์เก่าด้วยราคาสด แล้วรายงานความแม่นจริง ----
    if "/drive/" not in os.path.abspath(JOURNAL_PATH):
        print("  ⚠ JOURNAL_PATH อยู่นอก Google Drive — Colab จะลบไฟล์เมื่อจบ session")
        print("    แนะนำ: mount Drive แล้วตั้ง JOURNAL_PATH = '/content/drive/MyDrive/trade_journal.csv'")
    journal = load_journal(JOURNAL_PATH)
    journal = resolve_journal(journal, raw)
    print_track_record(journal_stats(journal))
    save_journal(journal, JOURNAL_PATH)
    dates = np.sort(pd.to_datetime(raw["Date"]).unique())
    cutoff = dates[int(len(dates) * OOS_SPLIT_FRACTION)]
    d = pd.to_datetime(raw["Date"])
    in_raw, out_raw = raw[d < cutoff].copy(), raw[d >= cutoff].copy()
    print(f"\nแบ่ง: cutoff={pd.Timestamp(cutoff):%Y-%m-%d} | in {len(in_raw):,} | out {len(out_raw):,}")

    data_in = precompute(in_raw)
    data_out = precompute(out_raw)

    print(f"\n[STEP] ค้นหา in-sample {N_TARGET:,} แบบ ...")
    survivors = run_search(data_in, N_TARGET, RANDOM_SEED)
    if survivors.empty:
        print(f"\n{N_TARGET:,} ไม่เจอ — escalate {N_ESCALATE:,} ...")
        survivors = run_search(data_in, N_ESCALATE, RANDOM_SEED + 1)

    if not survivors.empty:
        survivors = survivors.drop_duplicates(subset=PARAM_KEYS)
        survivors = survivors.sort_values("wilson_lb", ascending=False).head(TOP_N_REPORT)
        survivors.to_csv("in_sample_survivors.csv", index=False)
        print(f"  in-sample survivors: {len(survivors)} -> in_sample_survivors.csv")
    else:
        print("  in-sample survivors: 0")

    print("\n[STEP] ยืนยัน out-of-sample ...")
    oos = validate_oos(data_out, survivors)
    if not oos.empty:
        oos.to_csv("out_of_sample_validation.csv", index=False)
    confirmed = oos[(oos["oos_resolved"] >= 5) & (oos["oos_wr"] >= WIN_RATE_MIN)
                    & (oos["oos_net"] >= NET_RETURN_MIN) & (oos["oos_med"] > 0)].copy() if not oos.empty else pd.DataFrame()

    print("\n" + "="*72)
    print(f"ผลลัพธ์: in-sample survivors {len(survivors)} | out-of-sample ยืนยันผ่าน {len(confirmed)}")
    print("="*72)

    if not confirmed.empty:
        confirmed = confirmed.sort_values("oos_net", ascending=False)
        confirmed["strategy_name"] = confirmed["entry_family"].map(FAMILY_NAME)
        confirmed.to_csv("confirmed_strategies.csv", index=False)
        show = ["strategy_name", "entry_mode", "regime_filter", "rsi_period",
                "rsi_threshold", "bb_period", "bb_std", "donchian_n", "ema_fast",
                "ema_slow", "exit_mode", "tp_val", "sl_val", "hold_days", "adx_min",
                "vol_filter", "in_n", "in_wr", "in_net",
                "oos_resolved", "oos_wr", "oos_wilson_lb", "oos_net", "oos_med"]
        print("\nสมการที่ผ่านทั้ง 2 ชุด (บนสุด=ดีสุด):")
        print(confirmed[show].to_string(index=False))
        report = build_trade_report(raw, confirmed)
        if report.empty:
            print("\n  สัปดาห์นี้ไม่มีหุ้นเข้าเงื่อนไข (ปกติ — สัญญาณไม่เกิดทุกสัปดาห์)")
        else:
            report.to_csv("weekly_signals.csv", index=False)
            print("\n  *** สัญญาณเข้าซื้อสัปดาห์นี้ ***")
            print(report.to_string(index=False))
    else:
        print("\nไม่มีสมการผ่าน out-of-sample. ตัวเลขบอกความจริง: 4 กลยุทธ์ + ATR exit")
        print(f"บน {len(TICKERS)} หุ้น ({UNIVERSE}) ยังไม่มี edge ยืนยันได้ที่เกณฑ์ "
              f"WR{WIN_RATE_MIN:.0f}%+กำไร{NET_RETURN_MIN}%.")
        print("ทางเลือกถัดไป: ผ่อนเป็น WR65%, เพิ่ม N_TARGET, หรือเพิ่ม entry_family ใหม่.")

    # ---- เอเจนท์ฟันธงการเทรด (ฉันทามติ Top-5 สมการที่ผ่าน OOS) ----
    print("\n" + "-" * 72)
    print("เอเจนท์ฟันธงการเทรด (Verdict Agent)")
    vr = VerdictAgent(top_k=5, min_agree=3).decide(raw, confirmed)
    print(f"  ฟันธง: {vr.overall}")
    if vr.verdicts:
        vdf = pd.DataFrame([asdict(v) for v in vr.verdicts])
        vdf.to_csv("weekly_verdict.csv", index=False)
        print(vdf.to_string(index=False))
        print("  หมายเหตุ: min_oos_wilson_lb = ขอบล่างความมั่นใจ 95% ของ win rate "
              "(ความมั่นใจจริงขั้นต่ำ) -> weekly_verdict.csv")

    # ---- บันทึกคำฟันธง 'เข้า' (idempotent, เฉพาะรอบท้ายสัปดาห์ — กันสถิติปนเปื้อน) ----
    week_end_run = (last_bar.weekday() == 4) or (datetime.now().weekday() >= 4)
    if week_end_run:
        n_before = len(journal)
        journal = append_new_verdicts(journal, vr, run_date=f"{last_bar:%Y-%m-%d}")
        save_journal(journal, JOURNAL_PATH)
        n_new = len(journal) - n_before
        print(f"\nบันทึกออร์เดอร์ใหม่ {n_new} รายการ -> {JOURNAL_PATH} "
              f"(รวมสะสม {len(journal)}) — รันศุกร์หน้าระบบจะตัดสินผลให้อัตโนมัติ")
    else:
        print("\n⚠ รันกลางสัปดาห์ — ไม่บันทึกออร์เดอร์ลงสมุด (สัปดาห์ยังไม่จบ สถิติจะเพี้ยน)")

    # ---- Dashboard (ธีม Claude: ivory + coral, สบายตา) ----
    run_info = dict(run_ts=f"{datetime.now():%Y-%m-%d %H:%M}", last_bar=f"{last_bar:%Y-%m-%d}",
                    friday_ok=(last_bar.weekday() == 4), universe=UNIVERSE,
                    n_tickers=len(TICKERS), wr_min=WIN_RATE_MIN, net_min=NET_RETURN_MIN,
                    n_target=N_TARGET)
    html = generate_dashboard(run_info, journal_stats(journal), journal, vr, confirmed)
    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("แดชบอร์ด -> dashboard.html")
    try:  # แสดง inline บน Colab/Jupyter อัตโนมัติ
        from IPython.display import HTML, display
        display(HTML(html))
    except Exception:
        pass

    print(f"\n[{datetime.now():%H:%M:%S}] เสร็จสิ้น")


if __name__ == "__main__":
    main()
