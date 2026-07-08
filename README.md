# SET Weekly Stat-Edge Finder

ระบบเทรดอัตโนมัติเชิงสถิติสำหรับหุ้นไทย (SET) — เน้น **หาจุดเข้า (Entry Point) ที่แม่นยำ**
ด้วยโมเดลคณิตศาสตร์/สถิติล้วน แล้ว **พิสูจน์ขอบ (edge) ด้วย out-of-sample validation** ก่อนใช้จริง
ทำงานแบบรายสัปดาห์ (รันศุกร์หลังตลาดปิด → ตั้งคำสั่งซื้อเช้าวันจันทร์)

> ปรัชญาหลัก: **ตัวเลขเป็นผู้ตัดสิน ไม่ใช่ความรู้สึก** และ **ห้ามโกหก** — ถ้าไม่มี edge ระบบจะบอกตรง ๆ ว่า "ไม่เข้า"

---

## 1. ทำอะไร (Pipeline)

```
ดึงราคาสด 5 ปี (yfinance)
        │
        ▼
 precompute()  ── คำนวณอินดิเคเตอร์ + forward bars + market breadth (ครั้งเดียว/หุ้น)
        │
        ├── แบ่งข้อมูล 80/20 ตามเวลา (in-sample / out-of-sample)
        ▼
 run_search()  ── สุ่ม/ไล่ combo พารามิเตอร์นับล้านแบบบน in-sample
        │           คัดเฉพาะที่ WR≥70% & Net≥3% & median>0 & n≥30
        ▼
 validate_oos()── เอาผู้รอดไปทดสอบซ้ำบน "ข้อมูลที่ไม่เคยเห็น" (out-of-sample)
        │           ผ่านซ้ำ = confirmed  (overfit ถูกคัดออกอัตโนมัติ)
        ▼
 VerdictAgent  ── ฟันธงด้วย "ฉันทามติ" ของ Top-K สมการที่ยืนยันแล้ว
        │
        ├── trade_journal.csv  ── บันทึกออร์เดอร์จริง + ตัดสินผลรอบถัดไป (track record)
        └── dashboard.html     ── สรุปผลจริง vs ที่คาด (ธีมสบายตา)
```

โครงสร้างชั้น (layered): **Layer 1 (pure business logic)** คำนวณได้/ทดสอบได้ ไม่มี side-effect
· **Layer 3 (infra)** คือ `fetch_prices()` ที่แตะ network เท่านั้น — แยกออกเพื่อทดสอบส่วนคำนวณได้ 100%

---

## 2. คณิตศาสตร์เบื้องหลัง

### 2.1 อินดิเคเตอร์ (Layer 1 — pure)

| อินดิเคเตอร์ | สมการ | ใช้ทำอะไร |
|---|---|---|
| **Wilder RSI** | RS = EMA_α(gain) / EMA_α(loss), α = 1/period; RSI = 100 − 100/(1+RS) | วัดแรงซื้อ/ขาย (โมเมนตัม) |
| **EMA** | EMAₜ = α·Cₜ + (1−α)·EMAₜ₋₁, α = 2/(span+1) | เส้นแนวโน้ม |
| **ATR (Wilder)** | TR = max(H−L, \|H−Cₜ₋₁\|, \|L−Cₜ₋₁\|); ATR = EMA_{1/period}(TR) | ความผันผวนจริง (ใช้ตั้ง TP/SL) |
| **ADX** | จาก +DI/−DI ของ directional movement, DX = 100·\|+DI−−DI\|/(+DI+−DI); ADX = EMA(DX) | ความ "แรง" ของเทรนด์ (filter) |
| **MACD cross** | MACD = EMA_fast − EMA_slow; สัญญาณ = MACD ตัดขึ้นเหนือ EMA₉(MACD) | จุดกลับตัวเชิงโมเมนตัม |
| **Stochastic %K** | %K = 100·(C − LLₙ)/(HHₙ − LLₙ) | oversold/overbought (คนละแกนกับ RSI) |
| **Donchian high** | max ของ Close ย้อนหลัง N แท่ง **แล้ว shift(1)** | ฐาน breakout (ไม่รวมแท่งปัจจุบัน) |

หมายเหตุ edge case ที่ฝังในสมการ: RSI แยกกรณี warm-up / ไม่มี loss (→100) / ไม่มีทั้ง gain-loss (→50);
Stochastic และ ADX ป้องกันหารศูนย์ด้วย `replace(0, NaN)` เมื่อช่วงราคาแบน

### 2.2 ตระกูลจุดเข้า (Entry Families) — 7 ตรรกะ

จุดเข้าคือ **เงื่อนไขบูลีนล้วน** บนข้อมูลถึงแท่งปัจจุบันเท่านั้น (ไม่มองอนาคต):

| # | ชื่อ | เงื่อนไขเข้า (ยิงเมื่อ) |
|---|---|---|
| 0 | `MEAN_REVERSION` | RSI < threshold **และ** Close < Bollinger lower (mid − k·σ) |
| 1 | `BREAKOUT` | Close > Donchian_high(N) |
| 2 | `TREND_PULLBACK` | EMA_fast > EMA_slow **และ** RSI ย่อ < threshold |
| 3 | `MACD_CROSS` | MACD ตัดขึ้นเหนือ signal line |
| 4 | `STOCH_OVERSOLD` | %K < stoch_th |
| 5 | `GAP_DOWN_REVERSAL` | เปิด gap ลง ≥ gap_pct% **และ** Close > Open (แท่งฟื้น) |
| 6 | `VOLSPIKE_BREAKOUT` | Volume ≥ vol_mult × VolSMA20 **และ** Close > Donchian_high(N) |

**ทำไมหลายตระกูล?** เพราะ edge ไม่ได้อยู่ที่ตรรกะเดียว การค้นเชิงสถิติทั่วทั้ง 7 ตระกูล ×
ทุกพารามิเตอร์ ให้ข้อมูลเป็นผู้เลือกว่าตรรกะไหน (ถ้ามี) ที่ทำ WR>70% ได้จริงและยืนยัน OOS ได้

### 2.3 โมเดลออก (Exit) — Bracket + สองโหมด

ทุกไม้ตั้ง **TP (take-profit)** และ **SL (stop-loss)** ล่วงหน้า แล้วเดินไปข้างหน้าทีละแท่งจนชนอย่างใดอย่างหนึ่ง
หรือครบ `hold_days` (ออกที่ราคาปิด):

- **โหมด % ตายตัว:** TP = entry·(1 + tp/100), SL = entry·(1 − sl/100)
- **โหมด ATR-multiple:** TP = entry + tp·ATR, SL = entry − sl·ATR  ← ปรับตามความผันผวนจริงของหุ้นแต่ละตัว

**กำไรสุทธิต่อไม้:** `net = (exit/entry − 1)·100 − FRICTION_PCT` โดย FRICTION_PCT = 0.514%
(ค่าคอมมิชชัน+สเปรดไป-กลับ) — **หักต้นทุนก่อนเสมอ** ไม่มีกำไรลม

### 2.4 ตัวกรองบริบท (Filters)

- **ADX ≥ adx_min** — เข้าเฉพาะเมื่อเทรนด์แรงพอ (0 = ปิด filter)
- **Volume > VolSMA20** — เข้าเฉพาะเมื่อมีสภาพคล่องหนุน
- **Regime (market breadth)** — เข้าเฉพาะเมื่อ >50% ของ universe ยืนเหนือ SMA50 (ตลาดโดยรวมเป็นขาขึ้น)

### 2.5 การตัดสินทางสถิติ (ทำไมเชื่อได้ว่า >70%)

1. **In-sample search:** คัด combo ที่ `WR ≥ 70% & avg_net ≥ 3% & median_net > 0 & n_resolved ≥ 30`
   (median > 0 กัน outlier ตัวเดียวหลอก; n ≥ 30 กัน fluke)
2. **Wilson score lower bound (95%):** ขอบล่างของ WR จริงทางสถิติ —
   ป้องกัน "ชนะ 8/10 = 80%" ที่จริงไม่มีนัยสำคัญ ระบบจัดอันดับด้วยขอบล่างนี้ ไม่ใช่ WR ดิบ
3. **Out-of-sample confirmation:** เอาผู้รอดไปรันบนช่วงเวลาที่ **ไม่เคยใช้ค้นหา** —
   ถ้ายังผ่านเกณฑ์เดิม = edge จริง ไม่ใช่ overfit  (นี่คือด่านที่ตัด overfit ออกอัตโนมัติ)
4. **Positive expectancy:** avg_net (หลังหักต้นทุน) ต้องเป็นบวก — WR สูงอย่างเดียวไม่พอ ต้องคุ้มเมื่อรวมไม้แพ้

---

## 3. การรับประกัน "ไม่รีเพนต์" (Strictly Non-Repainting)

**นิยาม:** สัญญาณที่แท่ง *t* ต้อง **ไม่เปลี่ยนค่า** เมื่อมีข้อมูลอนาคตมาต่อท้าย

**บังคับด้วยโครงสร้าง:**
- ทุกอินดิเคเตอร์ใช้เฉพาะการคำนวณย้อนหลัง (`ewm`, `rolling`, และ `shift(+1)` สำหรับ Donchian)
- entry จริงคือ **ราคาเปิดแท่งถัดไป** (`Open.shift(-1)`) — ราคาที่ยังไม่เกิด ณ เวลาตัดสิน จึงเข้าไม่ได้ล่วงหน้า
- คอลัมน์ forward (H/L/C ล่วงหน้า) ใช้ **เฉพาะจำลองผลออกในแบ็กเทสต์** ไม่แตะการสร้างสัญญาณ
- เส้นทางตัดสินสด (`_latest_bar_signal`) อ่านเฉพาะแท่งล่าสุดที่ปิดแล้ว → ตั้งออร์เดอร์รอบถัดไป

**พิสูจน์ด้วยเทสต์:** `test_strictly_non_repainting_all_families` เทียบสัญญาณที่คำนวณจาก prefix `[0..t]`
กับที่คำนวณจากทั้งชุด แล้วยืนยัน **0 ความต่าง ทั้ง 7 ตระกูล**

---

## 4. การเคลียร์บั๊ก & Edge Cases

ระบบผ่านเทสต์ 64 เคส และจัดการเคสสุดขอบต่อไปนี้แบบชัดเจน:

| เคส | การจัดการ |
|---|---|
| **ข้อมูลตลาดขาดหาย** (NaN กลางชุด, หุ้นดึงไม่ได้, แท่งไม่พอ) | ทุกสัญญาณมี NaN-guard; ticker สั้นเกินไป → ไม่ยิง; `fetch_prices` ข้ามตัวที่ล้มเหลว |
| **ราคาเสีย = 0 / ติดลบ** (tick ผิด) | `MIN_VALID_PRICE` guard — ตัด entry ≤ 0 ทิ้ง กันหารศูนย์ → inf/NaN ปนเปื้อนสถิติ |
| **สัญญาณชนกันในแท่งเดียว** (High≥TP **และ** Low≤SL) | `TIE_BREAK_SL_WINS=True` — ให้ SL ชนะ (นับเป็นแพ้, worst-case) เพราะไม่รู้ลำดับ intraday → ไม่ปั่น WR ให้สูงเกินจริง |
| **Price gap** (เปิดกระโดด) | fam5 ใช้ gap เป็นสัญญาณโดยตรง; GapPct กัน prev-close=0 → inf |
| **ความผันผวน = 0** (ราคานิ่งสนิท) | ATR guard (>0) กัน TP=entry → "ชนะทันที" จอมปลอม; Stoch/ADX กันหารศูนย์ |
| **limit ไม่ติด / ติดวันแรก** | ติดเฉพาะแท่งแรก (Low≤limit); วันติดเช็คได้เฉพาะ SL (conservative); ไม่ติด = ยกเลิกฟรี |
| **ศุกร์เป็นวันหยุด** | นับ "แท่งท้ายสัปดาห์จริง" (เช่น พฤหัส) เป็นจุดสัญญาณแทน |
| **รันซ้ำวันเดียวกัน** | journal idempotent — dedup ด้วย (signal_date, ticker) |
| **pandas 3.x / numpy 2.x** | ทดสอบแล้วไม่มี FutureWarning/crash |

---

## 5. การตั้งค่า (Configuration)

แก้ได้ที่บล็อก `CONFIG` ด้านบนไฟล์ `set_edge_finder.py`:

| ค่า | ความหมาย | ค่าเริ่มต้น |
|---|---|---|
| `UNIVERSE` | `"QUALITY19"` (หุ้นคุณภาพ 19 ตัว) หรือ `"SET100"` | `QUALITY19` |
| `FRIDAY_ONLY` | นับสัญญาณเฉพาะแท่งท้ายสัปดาห์ (fidelity ตรงกับ workflow รายสัปดาห์) | `True` |
| `BUDGET_PER_TRADE_THB` | งบต่อไม้ (ใช้คำนวณจำนวน lot, board lot = 100 หุ้น) | `10,000` |
| `WIN_RATE_MIN` | เกณฑ์ WR ขั้นต่ำ (%) | `70.0` |
| `NET_RETURN_MIN` | เกณฑ์กำไรสุทธิเฉลี่ยขั้นต่ำ (%/ไม้) | `3.0` |
| `MIN_RESOLVED` | จำนวนไม้ขั้นต่ำต่อ combo (กัน fluke) | `30` |
| `OOS_SPLIT_FRACTION` | สัดส่วน in-sample (ที่เหลือเป็น out-of-sample) | `0.8` |
| `N_TARGET` / `N_ESCALATE` | จำนวน combo ที่สุ่มค้น / เพิ่มถ้ารอบแรกไม่เจอ | `3M` / `6M` |
| `FRICTION_PCT` | ต้นทุนไป-กลับต่อไม้ (%) | `0.514` |
| `TIE_BREAK_SL_WINS` | สัญญาณชนกันในแท่งเดียว: `True`=SL ชนะ (ซื่อสัตย์), `False`=TP ชนะ (optimistic) | `True` |
| `MIN_VALID_PRICE` | ราคาต่ำสุดที่ยอมรับ (กันข้อมูลเสีย) | `1e-9` |
| `JOURNAL_PATH` | ที่เก็บสมุดบันทึกผลจริง (Colab: ชี้ไป Google Drive เพื่อไม่ให้หาย) | `trade_journal.csv` |
| `SPACE` | search space ของทุกพารามิเตอร์ (RSI period, TP/SL, hold_days, ...) | ดูในไฟล์ |

---

## 6. วิธีรัน

### บน Google Colab (ตามที่ออกแบบไว้)
```python
!pip install yfinance pandas numpy --quiet
# วางไฟล์ set_edge_finder.py แล้ว:
%run set_edge_finder.py
```
> เก็บ track record ถาวร: `from google.colab import drive; drive.mount('/content/drive')`
> แล้วตั้ง `JOURNAL_PATH = "/content/drive/MyDrive/trade_journal.csv"`

### บนเครื่อง/เซิร์ฟเวอร์
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python set_edge_finder.py          # ต้องต่อ internet (ดึงราคาสด)
```

### รันเทสต์ (ไม่ต้องต่อ internet)
```bash
pip install -r requirements.txt
pytest -q                          # 64 passed
```

### จังหวะใช้จริง
รัน **ศุกร์หลังตลาดปิด (≥18:00) หรือเสาร์/อาทิตย์** → อ่านคำฟันธง/แดชบอร์ด → ตั้งคำสั่งซื้อ **เช้าวันจันทร์**
→ ศุกร์ถัดไประบบตัดสินผลไม้เก่าอัตโนมัติแล้วอัปเดต track record

---

## 7. ความสัตย์จริง (อ่านก่อนใช้เงินจริง)

- ระบบนี้ **ค้นหาและยืนยัน** edge เชิงสถิติ — **ไม่การันตีผลอนาคต** ตลาดเปลี่ยน edge ได้
- ถ้ารอบไหน **ไม่มีสมการผ่าน OOS** ระบบจะฟันธง "ไม่เข้า" ตรง ๆ — นั่นคือคำตอบที่ซื่อสัตย์ ไม่ใช่บั๊ก
- WR ที่รายงานเป็นแบบ **conservative** (สัญญาณชนกันนับเป็นแพ้, หักต้นทุนแล้ว, ใช้ Wilson lower bound)
- Track record บันทึก **ผลจริง vs ที่คาด** ทุกไม้ — ความแม่นวัดจากของจริง ไม่ใช่คำโฆษณา
- ไม่ใช่คำแนะนำการลงทุน · ผู้ใช้รับความเสี่ยงเอง

---

## 8. ไฟล์ในโปรเจกต์

| ไฟล์ | หน้าที่ |
|---|---|
| `set_edge_finder.py` | ระบบทั้งหมด (single-file, copy-paste รันได้) |
| `test_set_edge_finder.py` | ชุดทดสอบ 64 เคส (unit + edge + non-repaint proof) |
| `requirements.txt` | dependencies |
| `.gitignore` | กันไฟล์ผลลัพธ์/venv หลุดเข้า git |
