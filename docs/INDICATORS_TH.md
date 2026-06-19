# 📚 คลังความรู้เส้นอินดิเคเตอร์ของเอเจนท์ (45 เส้น)

เอกสารนี้คือ "ความรู้" ที่ปลูกฝังให้เอเจนท์นักวิเคราะห์ (Market Analyst) ของ Kingdom Prime
รวมเส้นอินดิเคเตอร์ทางเทคนิคมาตรฐาน **45 เส้น แบ่งเป็น 9 กลุ่ม**

ความรู้นี้อยู่ใน 2 ระดับ:

| ระดับ | ไฟล์ | หน้าที่ |
|---|---|---|
| **การคำนวณ** (จะคำนวณได้) | [`src/domain/analytics/indicator_lines.py`](../src/domain/analytics/indicator_lines.py) | ฟังก์ชัน Decimal บริสุทธิ์ของทุกเส้น |
| **ความรู้เชิงบรรยาย** (รู้ว่าคืออะไร) | [`src/domain/analytics/indicator_catalog.py`](../src/domain/analytics/indicator_catalog.py) | แค็ตตาล็อก 45 รายการ พร้อมชื่อ/กลุ่ม/คำอธิบายไทย ให้เอเจนท์ "อธิบาย" ตัวเองได้ |

> ทุกฟังก์ชันเป็น **Layer 1 (Domain)** บริสุทธิ์ — ใช้ `Decimal` ทั้งหมด ไม่มี I/O ไม่มี
> `time`/`random` จึงคำนวณซ้ำได้ผลเดิมเสมอ (deterministic) และผ่าน `mypy --strict`
> ค่าที่ยังอุ่นเครื่องไม่พอจะเป็น `Decimal('NaN')` (ตรวจด้วย `value.is_finite()`)

วิธีเรียกใช้แค็ตตาล็อกความรู้:

```python
from domain.analytics import indicator_catalog as cat

cat.all_lines()          # ทั้ง 45 เส้น
cat.by_group(1)          # เส้นในกลุ่มที่ 1 (Moving Averages)
cat.by_category("momentum")
cat.by_key("supertrend") # ค้นรายเส้นด้วยคีย์
```

---

## กลุ่มที่ 1 — เส้นค่าเฉลี่ยเคลื่อนที่ (Moving Average Lines)

เส้นที่คำนวณจากราคาในอดีตเพื่อหาแนวโน้มหลัก เป็นเส้นเดี่ยวที่วิ่งไปพร้อมราคา

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 1 | **SMA** | ค่าเฉลี่ยเลขคณิตพื้นฐาน ให้น้ำหนักทุกแท่งเท่ากัน | `sma(close, period)` |
| 2 | **EMA** | ถ่วงน้ำหนักราคาล่าสุดมากกว่า ตอบสนองไวกว่า SMA | `ema(close, period)` |
| 3 | **WMA** | ถ่วงน้ำหนักลดหลั่นเชิงเส้นตามลำดับเวลา | `wma(close, period)` |
| 4 | **HMA** | Hull MA ลดความล่าช้า (lag) ได้มากที่สุด | `hma(close, period)` |
| 5 | **SMMA** | Smoothed MA (Wilder) เรียบ เหมาะมองระยะยาว | `smma(close, period)` |
| 6 | **CMA** | ค่าเฉลี่ยสะสมตั้งแต่อดีตถึงปัจจุบัน | `cma(close)` |
| 7 | **VWAP** | ราคาเฉลี่ยถ่วงน้ำหนักด้วยปริมาณซื้อขาย (intraday) | `vwap(high, low, close, volume)` |

---

## กลุ่มที่ 2 — เส้นในกลุ่ม MACD

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 8 | **MACD Line** | ผลต่าง EMA(12) − EMA(26) | `macd(close)[0]` |
| 9 | **Signal Line** | EMA(9) ของเส้น MACD ใช้ดูจุดตัดซื้อ/ขาย | `macd(close)[1]` |
| 10 | **Zero Line** | เส้นระดับ 0 แกนกลาง วัดขาขึ้น (>0) / ขาลง (<0) | `MACD_ZERO_LINE` |

> โบนัส: `macd()` คืน histogram (`[2]`) = MACD − Signal ด้วย

---

## กลุ่มที่ 3 — เส้นในกลุ่ม Bollinger Bands (BB)

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 11 | **Upper Band** | แนวต้าน = เส้นกลาง + (k × ส่วนเบี่ยงเบนมาตรฐาน) | `bollinger_bands(close).upper` |
| 12 | **Middle Band** | แกนกลาง = SMA 20 วัน | `bollinger_bands(close).middle` |
| 13 | **Lower Band** | แนวรับ = เส้นกลาง − (k × ส่วนเบี่ยงเบนมาตรฐาน) | `bollinger_bands(close).lower` |

---

## กลุ่มที่ 4 — เส้นในกลุ่ม Oscillator

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 14 | **RSI Line** | Relative Strength Index วิ่ง 0–100 | `rsi_wilder(close)` |
| 15 | **Overbought Line** | เส้นซื้อมากเกินไป (มัก 70/80) | `RSI_OVERBOUGHT` |
| 16 | **Oversold Line** | เส้นขายมากเกินไป (มัก 30/20) | `RSI_OVERSOLD` |
| 17 | **RSI-based MA** | ค่าเฉลี่ยเคลื่อนที่ของเส้น RSI | `rsi_based_ma(close)` |
| 18 | **%K Line** | เส้นหลัก Stochastic ตอบสนองไว | `stochastic(high, low, close).k` |
| 19 | **%D Line** | เส้นสัญญาณ = SMA ของ %K | `stochastic(high, low, close).d` |
| 20 | **CCI Line** | Commodity Channel Index วัดการเบี่ยงเบนจากค่าเฉลี่ย | `cci(high, low, close)` |
| 21 | **Williams %R** | ราคาปิดเทียบช่วงสูง-ต่ำ วิ่ง 0 ถึง −100 | `williams_r(high, low, close)` |

---

## กลุ่มที่ 5 — เส้นระบบเมฆอิชิโมกุ (Ichimoku Cloud)

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 22 | **Tenkan-sen** | สัญญาณระยะสั้น = กึ่งกลางสูง-ต่ำ 9 วัน | `ichimoku(...).tenkan` |
| 23 | **Kijun-sen** | แนวโน้มระยะกลาง = กึ่งกลางสูง-ต่ำ 26 วัน | `ichimoku(...).kijun` |
| 24 | **Chikou Span** | ราคาปิดวาดถอยหลัง 26 วัน | `ichimoku(...).chikou` |
| 25 | **Senkou Span A** | (Tenkan+Kijun)/2 พล็อตล่วงหน้า 26 วัน | `ichimoku(...).senkou_a` |
| 26 | **Senkou Span B** | กึ่งกลางสูง-ต่ำ 52 วัน พล็อตล่วงหน้า 26 วัน | `ichimoku(...).senkou_b` |

> หมายเหตุ: `senkou_a/b` คืนค่า ณ แท่งที่คำนวณ — บนกราฟให้เลื่อนไปข้างหน้า `displacement` แท่ง

---

## กลุ่มที่ 6 — เส้นวัดความแข็งแกร่งของเทรนด์ (DMI & ADX)

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 27 | **+DI** | แรงซื้อ (ทิศขาขึ้น) | `dmi_adx(high, low, close).plus_di` |
| 28 | **−DI** | แรงขาย (ทิศขาลง) | `dmi_adx(high, low, close).minus_di` |
| 29 | **ADX** | ความแรงของเทรนด์ (ยิ่งสูงยิ่งแรง) | `dmi_adx(high, low, close).adx` |
| 30 | **ADX Threshold** | เส้นเกณฑ์ยืนยันเทรนด์ (มัก 20/25) | `ADX_TREND_THRESHOLD` |

---

## กลุ่มที่ 7 — เส้นขอบเขตราคาและแนวรับแนวต้าน (Channels & Envelopes)

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 31 | **Keltner Upper** | EMA + (k × ATR) | `keltner_channels(high, low, close).upper` |
| 32 | **Keltner Lower** | EMA − (k × ATR) | `keltner_channels(high, low, close).lower` |
| 33 | **Donchian Upper** | ราคาสูงสุดรอบ N วัน | `donchian_channels(high, low).upper` |
| 34 | **Donchian Lower** | ราคาต่ำสุดรอบ N วัน | `donchian_channels(high, low).lower` |
| 35 | **Donchian Middle** | (ขอบบน + ขอบล่าง) / 2 | `donchian_channels(high, low).middle` |
| 36 | **Envelope Upper** | ค่าเฉลี่ย × (1 + เปอร์เซ็นต์) | `envelopes(close).upper` |
| 37 | **Envelope Lower** | ค่าเฉลี่ย × (1 − เปอร์เซ็นต์) | `envelopes(close).lower` |

---

## กลุ่มที่ 8 — เส้นระดับราคาทางคณิตศาสตร์และสถิติ (Fibonacci & Pivot)

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 38 | **Pivot Point (P)** | แกนกลางราคาสมดุล = (H+L+C)/3 | `pivot_points(h, l, c).p` |
| 39 | **Resistance R1–R5** | แนวต้าน 5 ระดับ | `pivot_points(h, l, c).r1 … .r5` |
| 40 | **Support S1–S5** | แนวรับ 5 ระดับ | `pivot_points(h, l, c).s1 … .s5` |
| 41 | **Fib Retracement** | 0/23.6/38.2/50/61.8/78.6/100% หาจุดย่อตัว | `fibonacci_retracement(high, low)` |
| 42 | **Fib Extension** | 161.8/261.8/423.6% หาเป้าทำกำไร | `fibonacci_extension(low, high)` |

> R2–R5 / S2–S5 ใช้สูตรขยาย `P ± n·(H−L)` ส่วน R1/S1 เป็นสูตร floor pivot มาตรฐาน

---

## กลุ่มที่ 9 — เส้นราคาหยุดและกลับตัว (Trailing Stop Lines)

| # | เส้น | ความหมาย | ฟังก์ชัน |
|---|---|---|---|
| 43 | **Parabolic SAR** | จุดไข่ปลาวิ่งตามราคา ตัดทะลุ = ย้ายฝั่ง | `parabolic_sar(high, low)` |
| 44 | **Chandelier Exit** | Trailing stop = HH − (k × ATR) / LL + (k × ATR) | `chandelier_exit(high, low, close)` |
| 45 | **Supertrend** | แบ่งแนวโน้ม + จุดตัดขาดทุน (เขียว=ขึ้น แดง=ลง) | `supertrend(high, low, close)` |

---

## 🤝 เอเจนท์ใช้ความรู้นี้อย่างไร — Confluence แบบขยาย

นอกจากคำนวณได้ เอเจนท์ยังนำเส้นเหล่านี้มา "โหวตร่วมกัน" เพื่อตัดสินใจเข้าออเดอร์ ผ่าน
[`expanded_confluence_signal`](../src/domain/strategy/multi_indicator.py) ที่ขยายจาก
Confluence เดิม **4 เส้น → 9 เส้น** (เพิ่ม SMA cross, ความชัน WMA/HMA, ตำแหน่งราคาเทียบ
Bollinger และ RSI เทียบเส้นค่าเฉลี่ยของมันเอง)

ยิ่งหลายเส้นเห็นพ้องทิศเดียวกัน → ความมั่นใจยิ่งสูง (`เสียงที่เห็นพ้อง / 9`) ซึ่งเป็นค่า
**ที่วัดได้จริง** จากประวัติราคา ไม่ใช่คำสัญญาว่าจะกำไร

เปิดใช้งานในไฟล์ตั้งค่า:

```ini
MULTI_INDICATOR_ENTRY=true       # เปิด confluence (ค่าเริ่มต้น)
EXPANDED_CONFLUENCE_ENTRY=true   # ขยายเป็น 9 เส้น (ค่าเริ่มต้น = false)
```

เมื่อเปิด `EXPANDED_CONFLUENCE_ENTRY` เอเจนท์ Market Analyst จะรายงานรายละเอียดขึ้นต้นด้วย
`Confluence+` พร้อมรายการเส้นที่โหวต เช่น `7↑/0↓ · EMA↑ เทรนด์↑ MACD+ SMA↑ WMA↑ HMA↑ BB↑`

---

## ✅ การทดสอบ

- [`tests/domain/test_indicator_lines.py`](../tests/domain/test_indicator_lines.py) — ทุกเส้น
  ครบ 9 กลุ่ม รวมการตรวจ "ตรงกับ" ตัวคำนวณ `.ta` ที่ฝังมา (ATR/SuperTrend ตรงกันถึง ~1e-6)
- [`tests/domain/test_indicator_catalog.py`](../tests/domain/test_indicator_catalog.py) — แค็ตตาล็อกครบ 45 รายการ คีย์/หมายเลขไม่ซ้ำ และทุกเส้นชี้ไปฟังก์ชันจริง
- [`tests/domain/test_expanded_confluence.py`](../tests/domain/test_expanded_confluence.py) — การโหวต 9 เส้น
