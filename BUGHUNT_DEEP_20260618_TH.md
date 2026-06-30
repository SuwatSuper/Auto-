# BUGHUNT รายงานตรวจบั๊กเชิงลึก — Puopuy v9.3.4 (18.06.2026)

ตรวจ forensic ทั้งระบบบนคอร์ปัสจริง 106 ไฟล์ / 834 บิล (`/mnt/project`)
env: `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02`

> **บทสรุป:** ระบบ **แข็งแรงในระดับราก** — การอ่านข้อมูลทุกฟิลด์ตรงไฟล์จริง 100%, ไม่มี silent data-loss,
> error handling สังเกตได้ (SYS001). bug hunt เชิงลึกเจอ **ความไม่สม่ำเสมอเล็ก ๆ ด้านการปัดเศษ/provenance
> 5 จุด** — ระดับ LOW–MEDIUM ทั้งหมด ไม่มีจุดร้ายแรง. จุดที่กระทบ golden ผม **ไม่แก้เอง** — เสนอให้
> ด้านบนตัดสิน (เป็นเรื่องนโยบายปัดเศษภาษี).

---

## ✅ สิ่งที่ยืนยันว่า "แข็งแรง" (ตรวจแล้วไม่มีบั๊ก)

| เรื่อง | ผล | หลักฐาน |
|---|---|---|
| อ่านข้อมูลครบ | ✅ 834/834 บิล | parse_all_files ครบ ไม่มีบิล None |
| เลขที่เอกสาร (iv_number) ตรงเซลล์จริง | ✅ 834/834 (100%) | `_audit_iv_truth` — TEXT_EXACT ทุกใบ |
| เลขผู้เสียภาษี (tax_id) ตรงเซลล์จริง | ✅ 834/834 | ทุกใบ match เซลล์ในชีต |
| ยอดก่อน VAT (ocr) ตรงเซลล์จริง | ✅ 834/834 | ทุกค่า ocr ตรงเซลล์ |
| ความสอดคล้องภายใน total = sub+vat | ✅ 0 ผิด (>0.02) | recompute ทั้ง 834 |
| วันที่: อ่านตรง + ฟ้องบิลไม่มีวันที่ (DT005) | ✅ ทำงานถูก | 1 บิลไม่มีวันที่จริง → DT005 ติด |
| ตรวจวันที่ไม่มีจริง (DT006 เช่น 35/04) | ✅ detector ทำงาน | unit-probe ผ่าน, 0 หลุด |
| ไฟล์พังถูกข้ามแบบ "สังเกตได้" | ✅ ไม่เงียบ | log SYS001 ต่อไฟล์ + รายงานท้าย |
| โครงสร้างโค้ด | ✅ สะอาด | 0 bare-except, 0 mutable-default, 0 float-eq ใน logic, 0 ไฟล์เกิน 600 LOC |

---

## 🔎 จุดที่เจอ (5 findings)

### F-1 [MEDIUM] ปัดเศษเงินไม่สม่ำเสมอ — `round()` (banker's) ปน Decimal+ROUND_HALF_UP

- **Current risk:** กฎของระบบเอง (และ memory) ระบุ "ใช้ `Decimal`+`ROUND_HALF_UP` กับเลขเงินทุกที่"
  แต่จุดเติมฟิลด์ที่ขาด ใช้ `round(x, 2)` ของ Python ซึ่งเป็น **banker's rounding (half-to-even)**
  ไม่ใช่ HALF_UP → ผลต่าง 0.01 ที่ขอบครึ่งสตางค์ (.xx5).
- **Root cause:**
  - `parser_p1.py:409–411` — `sub/vat/tot = round(tot−vat,2)` ฯลฯ (เติมฟิลด์ที่ขาดจากอีก 2 ฟิลด์)
  - `parser_p2.py:128–129` — item_sum path `subtotal = sum(...)` **ไม่ปัดเลย** ขณะที่ `parser_p0a.py:126`
    ปัด `round(_sub,2)` → 2 path ของ item_sum ทำไม่เหมือนกัน
  - ตรงข้ามกับ path VAT-จาก-subtotal ที่ทำถูก: `(_D(sub)*VAT_RATE).quantize(0.01, ROUND_HALF_UP)`
- **หลักฐาน (real corpus — ขอบเขตชัด 2 บิล):**
  - `SHS_68_117.xls` ชีต '7': ในไฟล์มีเซลล์ VAT `[39,20]=8742.125` แต่ระบบ **derive** VAT =
    `round(total−sub,2)` = `round(8742.125,2)` = **8742.12** (banker's ปัด .125→คู่ลง) ;
    ROUND_HALF_UP จะได้ **8742.13** → ต่าง 0.01
  - `KTV_68_041.xls` ชีต '21': subtotal item_sum = **141312.015** (3 ตำแหน่ง ไม่ถูกปัด — มาจาก path p2)
- **Long-term impact:** ค่าเงินคลาดจากมาตรฐาน HALF_UP ของระบบเอง 0.01 ในเคสขอบ ; ปริมาณเล็ก
  (ปัจจุบัน 2 บิล) แต่เป็น **ความไม่สอดคล้องเชิงหลักการ** ที่อาจโผล่บนข้อมูลชุดใหม่
- **Recommended solution:** รวม logic ปัดเศษเงินไว้ helper เดียว (`_money_q(x) = Decimal(str(x)).quantize(
  Decimal('0.01'), ROUND_HALF_UP)`) แล้วแทน `round(...,2)` ทุกจุดเติม/รวมเงิน → ปัดแบบเดียวทั้งระบบ
- **Migration risk:** **เปลี่ยน golden** (2 บิลขยับค่า) → ต้อง rebaseline + ADR. และเป็น **คำถามนโยบายภาษี**
  (VAT ที่ derive ควรปัด HALF_UP หรือยึดเลขในไฟล์ 8742.125?) → **ขอให้ด้านบนตัดสิน**
- **Priority:** MEDIUM (จริง แต่ปริมาณเล็ก + ต้องการ decision)

### F-2 [LOW] 50 บิล (TOR_67_08.xlsx) ไม่มี `amount_source` (provenance หาย)

- **Current risk:** ทั้ง 50 บิลของไฟล์ TOR_67_08 ผ่าน parse path ที่ไม่เซ็ต `amount_source`
  (ยอดเงินถูกต้องปกติ — sub/vat/total ครบและ balance)
- **Root cause:** path การ parse ของ layout ไฟล์นี้ไม่ผ่าน `_finalize` ที่เซ็ต `result['amount_source']`
- **Long-term impact:** ต่ำมาก — กฎที่ใช้ provenance นี้คือ **VAT010 ซึ่งปิด-by-design อยู่แล้ว**
  จึงแทบไม่กระทบ ; แต่เป็นช่องโหว่ความสม่ำเสมอ (ถ้าเปิด VAT010 วันหน้าจะมองไม่เห็น 50 บิลนี้)
- **Recommended solution:** เซ็ต `amount_source` ให้ครบทุก path (ค่า default `'ocr'`/`'unknown'`)
- **Migration risk:** ต่ำ — `amount_source` เป็น metadata ไม่อยู่ใน golden snapshot (ตรวจแล้ว golden ไม่ขยับ)
- **Priority:** LOW

### F-3 [LOW] เซลล์ VAT มีในไฟล์ แต่ parser อ่านไม่เจอ (คอลัมน์เยื้อง) → ตกไป derive

- **Current risk:** `SHS_68_117.xls` ชีต '7' มี VAT จริงที่ `[39,20]` แต่ตัวตรวจคอลัมน์มองที่คอลัมน์ 19
  (ที่ subtotal/total อยู่) → ไม่เจอ → fallback ไป derive (ซึ่งเจอปัญหา F-1 ต่อ)
- **Root cause:** column-detection ของยอด VAT ไม่ครอบเคสที่ VAT เยื้องคอลัมน์จาก subtotal/total
- **Long-term impact:** ต่ำ — เป็น edge layout (พบ 1 บิล) ; ผลคือ VAT มาจาก derive แทน read
- **Recommended solution:** ขยาย VAT column-detection ให้สแกนคอลัมน์ข้างเคียง (±1–2) ของแถวยอด
- **Migration risk:** กลาง — แตะ parser logic อาจกระทบบิลอื่น → ต้องผ่าน golden-gate
- **Priority:** LOW

### F-4 [INFO] มี `assert` ใน production 2 จุด (หายภายใต้ `python -O`)

- **Current risk:** `report_precision.py:167` (`assert len(COUNCIL)==10`), `viewers.py:81`
  (`assert len(VIEWERS)==10`) — เป็น invariant ตอน import ; ถ้ารันด้วย `python -O` จะถูกตัดทิ้ง
- **Root cause:** ใช้ `assert` แทน explicit check
- **Long-term impact:** ต่ำ — เป็นแค่ sanity ตอน import (ไม่ได้คุมข้อมูล runtime) ; ระบบไม่ได้รันด้วย -O
- **Recommended solution:** เปลี่ยนเป็น `if len(...)!=10: raise RuntimeError(...)`
- **Migration risk:** ต่ำมาก (ไม่กระทบ golden)
- **Priority:** INFO

### F-5 [INFO/นโยบาย] 103 บิลมี VAT 3 ตำแหน่ง (ไม่ปัดสตางค์) ในไฟล์ต้นทาง

- **Current risk:** ใบกำกับของซัพพลายเออร์บางรายมี VAT ไม่ปัดสตางค์ (เช่น 34749.575) — ระบบ **อ่านตรงตามไฟล์**
  (ไม่ใช่บั๊ก) แต่ตามแนวปฏิบัติภาษีไทย VAT ควรปัดเป็นสตางค์ (2 ตำแหน่ง)
- **Root cause:** ฝั่งเอกสารต้นทาง (ไม่ใช่ระบบ)
- **Long-term impact:** เป็นประเด็น compliance ของเอกสาร — ระบบ **ยังไม่ฟ้อง** "VAT ไม่ปัดสตางค์"
- **Recommended solution (ถ้าต้องการ):** เพิ่มกฎ advisory ฟ้องเมื่อ VAT มี >2 ตำแหน่งทศนิยม
  (= feature ใหม่ → ต้องได้รับอนุมัติก่อนตามกติกา)
- **Migration risk:** — (เป็น feature ใหม่ ไม่ทำจนกว่าจะอนุมัติ)
- **Priority:** INFO (นโยบาย ไม่ใช่บั๊ก)

---

## สรุปการตัดสินใจที่รอด้านบน

| Finding | ต้องแก้? | กระทบ golden? | ผมเสนอ |
|---|---|---|---|
| F-1 ปัดเศษไม่สม่ำเสมอ | ตามนโยบาย | **ใช่** (2 บิล) | รวม `_money_q` HALF_UP ทั้งระบบ + rebaseline — **รออนุมัติ** |
| F-2 provenance หาย 50 บิล | ควร | ไม่ | เซ็ต amount_source ให้ครบ — ทำได้เลยถ้าสั่ง |
| F-3 VAT เยื้องคอลัมน์ | ควร | อาจ | ขยาย column-detection — ผ่าน golden-gate |
| F-4 assert ใน prod | ไม่จำเป็น | ไม่ | เปลี่ยนเป็น raise — ทำได้เลย |
| F-5 VAT ไม่ปัดสตางค์ | feature | — | กฎ advisory ใหม่ — รออนุมัติ |

> ทั้ง 5 จุดเป็น LOW–MEDIUM. ระบบหลักถูกต้องและเชื่อถือได้. ผมรอด้านบนเลือกว่าจะให้แก้จุดไหน
> (โดยเฉพาะ F-1 ที่ขยับ golden — เป็นการตัดสินใจเชิงนโยบายปัดเศษภาษี ผมจึงไม่แก้เอง).
