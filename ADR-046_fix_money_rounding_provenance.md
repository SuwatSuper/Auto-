# ADR-046 — แก้ F-1/F-2/F-4 + Rebaseline golden: `bb042554` → `662c9132`

สถานะ : ACCEPTED — 18.06.2026
บริบท : Deep bug-hunt (BUGHUNT_DEEP_20260618_TH.md) บนคอร์ปัสจริง 106 ไฟล์ / 834 บิล พบความไม่สอดคล้อง
เชิงปัดเศษเงิน + provenance หาย + assert ใน production. ด้านบนอนุมัติให้แก้ทั้งหมด.

env ตรวจ: `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02`

---

## สิ่งที่แก้ (สืบจาก source/เซลล์จริง ไม่เดา)

### F-1 [MEDIUM] ปัดเศษเงินไม่สม่ำเสมอ — `round()` (banker's) → `Decimal+ROUND_HALF_UP`
- **ราก:** กฎของระบบคือ "เงินทุกค่าใช้ Decimal+ROUND_HALF_UP" แต่จุดเติม/derive ยอดบางจุดยังใช้
  `round(x, 2)` ของ Python = banker's rounding (half-to-even). ที่ขอบครึ่งสตางค์ (.xx5) ให้ผลต่าง 0.01
  จากมาตรฐานที่ระบบประกาศไว้เอง (ขัดกับ path VAT-จาก-subtotal ที่ทำถูกด้วย HALF_UP อยู่แล้ว).
- **หลักฐานเซลล์จริง:** `SHS_68_117.xls` ช.7 — ในไฟล์ subtotal=124887.5, total=133629.625 ; ระบบ derive
  VAT = `round(total−sub,2)` = `round(8742.125,2)` = **8742.12** (banker's ปัด .125→คู่ลง) ทั้งที่ HALF_UP
  ต้องได้ **8742.13**.
- **แก้:** เพิ่ม helper เดียว `_money_q(x)` ใน `puopuy_units.py` (Decimal(str(x)).quantize(0.01, ROUND_HALF_UP)
  → float ; None-safe) เป็นแหล่งความจริงเดียวของการปัดเงิน. แทน `round(...,2)` ทุกจุดเติม/รวม/derive ยอด:
  - `parser_p1.py:409–411` (_reconcile_amounts — เติมฟิลด์ที่ขาดจากอัตลักษณ์ sub+vat=tot)
  - `parser_p2.py:126, 139` (derive total) + `parser_p2.py:128` (item_sum subtotal เดิมไม่ปัด → 3 ตำแหน่ง)
  - `parser_p0a.py:126, 132` (item_sum subtotal + derive total)
- **import:** `_money_q` import ตรงจาก leaf `puopuy_units` ในแต่ละไฟล์ (parser_p0a/p1/p2) — เลี่ยง re-export
  chain fragility, ไม่มี circular (puopuy_units เป็น leaf).

### F-2 [LOW] 50 บิล (TOR_67_08.xlsx) ไม่มี `amount_source`
- **ราก:** TOR-format ใช้เส้น `_parse_tor_sheet` ที่ข้าม `_pb_finalize_amounts` (จุดที่ติด provenance).
- **แก้:** เรียก `_pb_finalize_amounts(result)` ท้าย `_parse_tor_sheet`. ยอด TOR ครบทั้ง 3 อยู่แล้ว →
  `_reconcile_amounts` คืนค่าเดิม (ไม่ derive/ไม่เปลี่ยนยอด) เพิ่มเฉพาะ `amount_source` + `amount_confidence`.

### F-4 [INFO] `assert` ใน production 2 จุด (หายภายใต้ `python -O`)
- **แก้:** `report_precision.py:167` (COUNCIL) + `viewers.py:81` (VIEWERS) เปลี่ยน `assert len(...)==10` →
  `if len(...)!=10: raise RuntimeError(...)`. **golden-neutral** (โมดูลรายงาน ไม่แตะข้อมูลบิล).

### ไม่แก้ (จงใจ — บันทึกเหตุผล)
- **F-3 [LOW] VAT เยื้องคอลัมน์ → derive แทน read:** วัด blast radius จริง = **410/412 บิลที่ derive VAT
  มีเซลล์ VAT ตรงกันอยู่แล้ว** (เพราะใบกำกับ internally consistent: total=sub+vat=sub×1.07) → ค่าที่ derive
  **เท่ากับ** เซลล์อยู่แล้ว 411/412 บิล. การแก้ column-detection จะ churn provenance 410 บิล (golden ขยับมหาศาล)
  เพื่อ "ค่าที่ถูกอยู่แล้ว" = เพิ่ม regression risk โดยไม่มีประโยชน์ → ละเมิดหลัก minimize-regression-risk.
  เคสเดียวที่ค่าต่าง (SHS) ถูกจัดการด้วย F-1 (HALF_UP) แล้ว.
- **F-5 [policy] VAT ไม่ปัดสตางค์ในไฟล์ต้นทาง (103 บิล):** ระบบอ่านตรงไฟล์ (ไม่ใช่บั๊ก). การเพิ่มกฎ advisory
  = **feature ใหม่** → ไม่ทำจนกว่าจะได้รับอนุมัติเฉพาะ (ตามกติกา feature-prohibition).

---

## Rebaseline + Blast radius (validate ทุกบิลที่เปลี่ยน)

`bb042554` → **`662c9132`** (เต็ม: `662c91320056d98bf7faf85378ff08a18aaaa3449a8774a6e2438613c8c05f6a`)

diff old↔new (834 บิล): **เปลี่ยน 61 บิล** = 11 ค่าเงิน + 50 provenance เท่านั้น
- **11 ค่าเงิน — ตรวจทีละใบ ถูกทั้งหมด:**
  - 9 ใบ: ล้าง float-noise ของ item_sum (เช่น 268360.19999999995→268360.2, 496364.00000000006→496364.0)
  - SHS_68_117 ช.7: VAT 8742.12→**8742.13** (เป้าหมาย F-1)
  - SEE_69_053 ช.16: subtotal 228386.4999…→228386.5 → VAT 15987.05→**15987.06**, total →244373.56
    (cascade ถูก: subtotal สะอาดแล้ว VAT คิด HALF_UP ได้ค่าถูก)
- **50 provenance — TOR_67_08:** เพิ่ม `amount_source=('ocr','ocr','ocr')` ทุกใบ · ยอดเงิน **ไม่เปลี่ยน** (0 ใบ)
- **0 บิลที่ issues เปลี่ยน** · **issue-code totals เหมือนเดิมเป๊ะ** · โครงสร้างคงที่
  (iv_seq=29, iv_date=2, typos=42, dup=1, companies=2)

determinism: รัน golden_master ซ้ำได้ hash เดิม (662c9132) ภายใต้ env ที่ pin.
backup: `baseline.bb042554.pre-F1F2.json`.

---

## ผลกระทบ
- production logic เปลี่ยน 4 ไฟล์ (puopuy_units +helper, parser_p0a/p1/p2 แทน round()) + report 2 ไฟล์ (assert→raise)
- golden ขยับ `bb042554`→`662c9132` (มีหลักฐาน + validate) · doc surfaces sync ครบ · bb042554 ขึ้นทะเบียน retired
- ผลตรวจ (issues) **ไม่เปลี่ยน** — การแก้เป็นเรื่องความถูกต้องของ "ค่าเงินที่เก็บ/แสดง" ไม่ใช่ข้อสรุปการตรวจ
