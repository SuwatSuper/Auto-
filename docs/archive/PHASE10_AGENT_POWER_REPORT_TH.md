# PHASE 10 — รายงานปิดท้าย: Agent Intelligence Upgrade (ตามจริง)

> ทำบน branch `claude/sharp-lamport-4vwl01` · effort: max · audit-first
> **กฎที่เคารพทุกข้อ:** ไม่เพิ่ม API key ใหม่ · ไม่แตะรั้วความเสี่ยง · ไม่ลด cov ·
> ไม่มีทางลัด (`type: ignore`/`noqa`/`|| true`/`skip`) · gateway ใหม่ READ-ONLY ·
> ไม่ใช้ sklearn (Layer 1 อนุญาตแค่ numpy/pandas) → ใช้ **numpy ล้วน** แทน

---

## ✅ สรุปผลตรวจรับ (ตัวเลขจริงจากเครื่อง)

```
ruff check src tests            → All checks passed!
mypy --strict src/              → no issues found in 132 source files
pytest tests/architecture/      → 35 passed   (cage + honesty + risk-fence + layer rules เขียวหมด)
pytest (full + coverage gate)   → 822 passed, 1 skipped · coverage 91.14% (เกณฑ์ 90)
```
- ก่อน Phase 10 (baseline ที่นำเข้า): 733 passed · cov 90.56%
- หลัง Phase 10: **822 passed (+89 เทสต์ใหม่) · cov 91.14%** (สูงขึ้น ไม่ลดลง)
- ทุกโมดูลใหม่คุมด้วยเทสต์จริง (ส่วนใหญ่ 100% module coverage)

---

## 🧱 หลักการที่ยึด (honesty)

- พลังที่เพิ่ม = **"เห็นข้อมูลมากขึ้น + รวมสัญญาณฉลาดขึ้น + เรียนจากผลจริง"** ไม่ใช่ "ดูซับซ้อน"
- **ไม่มี upgrade ไหนการันตีกำไร** — ทุกตัวเพิ่มได้แค่ "ความน่าจะที่ดีขึ้น"
- ML ทุกตัวต้องผ่าน **out-of-sample (walk-forward)** ก่อนถูกเชื่อ; แพ้ rule → ใช้ rule
- โมเดลให้แค่ "ความน่าจะ" → ยังต้องผ่าน entry gate + รั้วความเสี่ยงเดิมทุกชั้น

---

## 📦 สิ่งที่ทำจริง (ครบทั้ง 7 upgrades)

### 🥇 U1 — Order Book / Microstructure (ข้อมูลใหม่ที่ agent ไม่เคยเห็น)
- `src/infrastructure/gateway/bitkub_orderbook.py` — gateway **READ-ONLY** ดึง public depth
  (`/api/v3/market/depth`, ไม่ต้องคีย์), GET อย่างเดียว, rate-limited (TokenBucket เดิม),
  cache สั้น (กันยิงซ้ำใน 1 tick), เก็บ book เดิมไว้ถ้า poll ล้ม
- `src/domain/analytics/microstructure.py` — feature บริสุทธิ์ (Decimal): **order-book imbalance**,
  **bid-ask spread (bps)**, **depth ใกล้ราคา**, parser ทนทุก shape ของ Bitkub
- `confluence.py` — เพิ่ม veto `BOOK_IMBALANCE_OPPOSED` (BUY เข้าใส่ฝั่งขายหนา = ปัด) แบบ **opt-in
  ปิดเป็น default** → setup แบบราคาเปล่ายังทำงานเหมือนเดิม
- **cage ยังเขียว**: เทสต์ยืนยันไฟล์ไม่มี marker สั่ง order + เป็น GET เท่านั้น

### 🥈 U2 — ML Win-Probability จาก track record ตัวเอง (self-improvement ตัวจริง)
- `src/domain/analytics/ml_winprob.py` — **logistic regression numpy ล้วน** (ไม่มี sklearn,
  ไม่มี random: gradient descent เริ่มจากศูนย์ → deterministic 100%), Layer 1 บริสุทธิ์
- กัน overfit ครบตามบังคับ:
  - **Cold-start:** `cold_start_ok(n, min=100)` — ข้อมูลไม่พอ → ใช้ rule
  - **Walk-forward validation:** เทรนอดีต ทดสอบอนาคตที่ไม่เคยเห็น → คืน OOS accuracy/expectancy
  - **A/B vs rule:** ตั้ง `use_model=True` **ก็ต่อเมื่อ OOS expectancy ชนะ rule** เท่านั้น
  - **No-lookahead:** `entry_features` อ่านแค่ `closes[:idx+1]` — มีเทสต์ "ป่วนแท่งอนาคต แล้ว
    feature ต้องไม่เปลี่ยน" พิสูจน์ว่าอนาคตรั่วเข้าไม่ได้
- `scripts/validate_winprob.py` — รายงาน OOS จาก `data/trades_*.csv` จริงถ้ามี, ไม่มีก็โชว์
  **synthetic demo ที่ติดป้ายชัดว่าไม่ใช่ผลเทรดจริง**

**ตัวเลข OOS (จากชุด synthetic ที่มีสัญญาณจริง — เพื่อพิสูจน์ "วิธีการ" ไม่ใช่ผลตลาดจริง):**
```
samples 400 · cold-start ok (>=100): True
OOS n=320 · model acc 79.1% · model E[pnl] +0.6161 (take 50%)
                              vs rule E[pnl] +0.0335 (take 100%)  → USE MODEL
```
> ⚠️ ตัวเลขนี้มาจากข้อมูลสังเคราะห์ที่ "จงใจให้มีสัญญาณ" — มันพิสูจน์ว่า **กลไก walk-forward/A/B
> ทำงานและจับ edge ได้จริง** เท่านั้น **ไม่ใช่** คำมั่นเรื่องผลเทรดสด. ผลจริงต้องวัดจาก
> `data/trades_*.csv` ของบัญชีจริงเมื่อมีไม้สะสมพอ (≥100)

### 🥉 U3 — Swarm Meta-Learner (รวมพลังให้ฉลาดขึ้น)
- `src/domain/analytics/swarm_meta.py` — เก็บ hit-rate ของแต่ละ method **แยกตาม regime**
  (Laplace-smoothed → ประวัติบางยังกลาง ไม่มั่นใจเกินจริง) → ถ่วงน้ำหนักโหวต
- น้ำหนัก **มีขอบเขต** (0.25–2.0): method ที่แม่นใน regime นั้นเสียงดังกว่าจริง, แต่ดวงดีแว้บเดียว
  ครองวงไม่ได้
- เทสต์สำคัญ: read ชุดเดิมเป๊ะ ๆ → **ผลโหวตพลิกจาก NEUTRAL เป็น BEAR** เมื่อฝั่ง bear พิสูจน์
  ว่าแม่นกว่าใน regime นั้น (น้ำหนักปรับจากผลจริง ไม่ใช่โหวตเท่ากัน)

### U4 — Multi-Timeframe Features (compute ล้วน ไม่ต้องข้อมูลใหม่)
- `src/domain/analytics/multi_timeframe.py` — resample close stream เดียวเป็นหลาย TF (1/5/15/60),
  อ่านเทรนด์ต่อ TF, รวมเป็น **confluence score ที่ TF ใหญ่มีน้ำหนักกว่า** (top-down bias),
  เช็ก all-timeframes-agree, และสร้าง **feature vector ป้อนโมเดล U2**

### U5 — Adaptive Regime Switching
- `src/domain/analytics/regime_weights.py` — playbook ต่อ regime (trend-following/momentum ขึ้น
  ตอน trend, mean-reversion ขึ้นตอน range, ทุกตัวลดตอน high-vol), map ชื่อ regime สองภาษา
  (MarketRegime/MarketMode) ให้ตรงกัน, และ `adaptive_weights()` **คูณ playbook ด้วยความน่าเชื่อถือ
  จริงจาก U3** (bounded) → ป้อนเข้า swarm
- `regime.py` — เพิ่ม `classify_with_confidence()` (regime + ความเชื่อมั่น 0–1 + ตัวขับ) แบบ
  เพิ่มเข้ามา; `classify()` เดิมไม่ถูกแตะ

### U6 — News RSS Sentiment (ฟรี ไม่ต้องคีย์)
- ของเดิม: sentiment ต่อเข้า gate แล้ว (veto BUY เมื่อข่าวลบแรง ผ่าน `last_news`) — "งดเข้า" มีอยู่
- เพิ่ม: `sentiment.sentiment_size_factor()` — "**ลดขนาด**" เมื่อข่าวลบ (ลงถึง 0.5x), "ยืนยัน"
  เมื่อข่าวบวก (ไม่เกิน 1.25x), กลาง = 1.0x · เป็น **ตัวกรอง bounded ไม่ใช่ตัวสั่งเดี่ยว**
  และผลยังถูก cap ความเสี่ยงครอบอีกชั้น

### U7 — Adaptive Position Sizing (Kelly ใต้รั้ว)
- `src/domain/risk/sizing.py` — `adaptive_kelly_size()` คำนวณขนาดจาก **win-rate + payoff ที่วัดได้**
  (default half-Kelly, multiplier clamp [0,1]) แต่ **hard-cap ที่ `max_notional` เสมอ** —
  Kelly เป็นแค่คำแนะนำ, cap คือกฎ
- Decimal ล้วน (ผ่าน float-ban ของ domain/risk), **ไม่แตะ survival floor / hard cap**
  (risk-fence-immutable เทสต์ยังเขียว)
- เทสต์สำคัญ: **"Kelly แนะนำเกิน cap → ผลลัพธ์ไม่เคยทะลุ cap"**

---

## ⚠️ อันไหนพิสูจน์แล้ว / อันไหนยังต้องพิสูจน์ต่อ (ตามจริง)

| Upgrade | สถานะหลักฐาน |
|---|---|
| U1 microstructure | กลไก + feature ถูกต้องตามเทสต์ · **ผลต่อ PnL จริงยังไม่วัด** (ต้องมี live depth + track record); จึงตั้ง veto เป็น **opt-in ปิด default** จนกว่าจะพิสูจน์ |
| U2 ML win-prob | กลไก walk-forward/A/B/no-lookahead **พิสูจน์แล้วบน OOS (synthetic)** ว่าจับ edge ได้ · **ผลบนข้อมูลเทรดจริงยังไม่มี** (ต้องสะสม ≥100 ไม้) |
| U3 meta-learner | พิสูจน์แล้วว่า "ตัวแม่นกว่าได้น้ำหนักมากกว่า + พลิกโหวตได้" จากผลจริง |
| U4 MTF | คำนวณถูกตามเทสต์เทียบค่ามือ · เป็น input ที่ดีขึ้นให้ U2/strategy |
| U5 regime weights | playbook + การ blend กับ U3 ถูกต้องตามเทสต์ |
| U6 sentiment | ตัวกรอง bounded ทำงานตามเทสต์ · veto เดิม wire อยู่แล้ว |
| U7 Kelly | พิสูจน์แล้วว่า **ไม่มีทางทะลุ cap** แม้ Kelly แนะนำเกิน |

**สิ่งที่เขียนได้อย่างซื่อสัตย์:** upgrade เหล่านี้ทำให้ agent **เห็นข้อมูลมากขึ้น รวมสัญญาณ
ฉลาดขึ้น และมีกลไกเรียนจากผลจริงของตัวเองที่ถูก validate แบบ out-of-sample** — เพิ่ม
"ความน่าจะที่ดีขึ้น" ภายใต้รั้วความเสี่ยงเดิมที่ไม่ถูกแตะ
**สิ่งที่ห้ามเขียนและไม่เขียน:** ไม่มีคำว่า "ทรงพลังที่สุด" หรือ "ชนะตลาดแน่นอน" — ผลเทรดสดจริง
ยังต้องพิสูจน์ด้วย paper track record ต่อเนื่องก่อนเปิดใช้แต่ละตัวเป็น default

---

## 🔌 หมายเหตุการเปิดใช้ (เพื่อความปลอดภัย)
ตัวที่แตะเส้นทางสั่งซื้อสด (U1 veto, U7 sizing multiplier, U6 size factor) ถูกทำเป็น **pure function
+ opt-in/closed-by-default** เพื่อไม่เปลี่ยนพฤติกรรม hot path โดยไม่ผ่าน paper validation ก่อน —
เปิดใช้ทีละตัวหลังเห็นตัวเลข out-of-sample จาก track record จริง
