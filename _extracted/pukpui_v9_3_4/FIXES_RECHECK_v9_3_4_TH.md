# สรุปการแก้บั๊กรอบรีเช็คทั้งระบบ — pukpui v9.3.4

แก้ตามรายงาน `BUGHUNT_RECHECK` (รีเช็คทุกหมวด). **ทุกการแก้พิสูจน์แล้วว่า golden-neutral**:
fixture hash = `269ddaed…` และ real-case digest = `95852c68…` **ไม่ขยับ** (แก้เฉพาะเคสบั๊ก ไม่แตะพฤติกรรมที่ถูกอยู่แล้ว),
เทสต์ผ่าน 76/77 (ตัวเดียวที่ตก = `test_package_integrity` ต้องรันใน git repo — artifact ของการรันจาก zip),
parallel==serial ยังตรงเป๊ะ, ไฟล์ทุกไฟล์ ≤600 LOC.

> หมายเหตุ golden: เครื่องที่รัน baseline ทางการ (Python 3.12 / numpy 2.2 / corpus 106 ไฟล์) ควร
> รัน `regression_full.py` ใหม่เพื่อยืนยัน — การแก้เหล่านี้ออกแบบให้ผลตรวจ "ของเดิมที่ถูกอยู่แล้ว" ไม่เปลี่ยน
> (เปลี่ยนเฉพาะเมื่อเจอเคสบั๊กจริง เช่น IV ซ้ำข้ามหลัก / VAT label / 29 ก.พ. พ.ศ.).

## รายการแก้ (ยืนยันด้วย repro เดิมทุกตัว)

| # | ระดับ | ไฟล์:บรรทัด | อาการเดิม | การแก้ |
|---|---|---|---|---|
| 1 | HIGH | `validators.py` (`_iv_check_sequence`, `_iv_check_ascending`, `check_iv_date_sequence`) | ตรวจ IV ซ้ำ/ถอยหลังหลุดเมื่อเลขข้ามหลัก 100/1000 (`IV0100,IV0100,IV0099`→0 issue) | เทียบ "ความยาวสตริงเลขท้ายดิบ" (`_seq_len`/`rawlen`/จำนวนหลัก) แทน `len(str(int))` ที่ศูนย์นำหาย |
| 2 | MED | `rules_engine_rules_b.py:r_vat004` | กฎปัดเศษเปิดอยู่แต่ไม่เคย flag (round 2 ก่อนวัด >2) | ปัดที่ 6 ตำแหน่ง (ตัด float residue) ก่อนวัดทศนิยมจริง + กัน nan/inf |
| 3 | MED | `parser_p1.py` ANTI_PREFIX | `"VAT 1416233"` ถูกอ่านเป็นเลขที่ใบกำกับ | เพิ่ม `VAT/NET/SUM/AMT/TOTAL/BAHT/GROSS/SUBTOTAL` |
| 4 | MED | `puopuy_units.py:_D` | `_D("nan"/"inf")` คืน Decimal ไม่จำกัด → VAT ผ่านหลอก/ครัช | คืน None เมื่อ `not is_finite()` ทุก path (bool ก่อน Decimal) |
| 5 | MED | `puopuy_dates.py:parse_date_any` | `29/2/2567` (พ.ศ. อธิกสุรทิน) → None | fallback: แปลงปี −543 "ก่อน" สร้าง datetime |
| 6 | LOW-MED | `rules_engine_rules_c.py:r_addr005` | คว้าเลข 5 หลักตัวแรกเป็นไปรษณีย์ → false positive | ใช้ `zips[-1]` (ตัวท้าย) ตามแบบ `_addr_parse_smart` |
| 7 | LOW-MED | `parser_p0a.py:_dic_find_seq` | `best=0` → บิลรายการเดียวคอลัมน์ seq index ≥10 สกัด item ไม่ได้ | ใช้ sentinel `None` (รับ seq-run แรกเสมอ; เคส score>0 ผู้ชนะเดิมไม่เปลี่ยน) |
| 8 | LOW-MED | `validators.py:check_iv_date_sequence` | IV 4-7 หลัก (ทั้งก้อน) ปนกับ ≥8 หลัก (last-4) → ฟ้องถอยหลังหลอก | guard: กลุ่มจำนวนหลักไม่เท่ากัน → ไม่เทียบ |
| 9 | LOW | `rules_engine_rules_a.py:r_dt003` | ตรวจ digit-swap ปีอยู่ใน band พ.ศ. ที่ตายหลัง parser แปลงเป็น ค.ศ. | เช็ก `(yr+543)` ใน band ค.ศ. → ขึ้นข้อความ digit-swap ได้จริง |
| + | LOW | `r_vat006/007` | bool money (bool⊂int) → `_D(bool)=None` ครัช → skip เงียบ | กัน `isinstance(x,bool)` ที่ type-gate |
| + | LOW | `r_itm013` | seq เป็น string → `'1'!=1` → false positive "ไม่เริ่มที่ 1" | รับเฉพาะ seq เป็น int แท้ |
| + | LOW | `validators.py` (`iv_number`/`iv_date`/`dates`) | index ตรง → KeyError บนบิลพิการ | ใช้ `.get()` |

## ที่ "ตั้งใจไม่แก้" (ซื่อตรง)
- กฎรายการ `it['qty']/['unit']` index ตรง: เป็น defensive ล้วน (parser จริงใส่ key ครบเสมอ + มี per-bill
  try/except กันครัชทั้ง batch แล้ว). การใส่ default ผิดเสี่ยง "สร้าง false positive ใหม่" — แย่กว่าเดิม. คงไว้.
- `thai_postal` prefix เสริมบางจังหวัด / `normalize_ocr` สระสั้น→ยาว / `_pick_best_iv_safe` (no call site) /
  `_filename_period_ce` (time-bomb หลัง พ.ศ.2582): ผลกระทบต่ำ/นอกเส้นทางจริง — บันทึกไว้ ยังไม่แตะเพื่อคุม golden.

ดูรายละเอียดเชิงลึก + repro ใน `BUGHUNT_RECHECK_pukpui_v9_3_4_TH.md` (รากโปรเจกต์).

---

## รอบที่ 2 — ตามคำขอเจ้าของ (ปิด VAT004 + ปรับถ้อยคำรายงานให้สั้น/เป็นภาษาคน)

ทุกอย่าง golden-neutral (fixture `269ddaed…` + real-case `95852c68…` ไม่ขยับ), เทสต์ **78/0**, parallel==serial, ทุกไฟล์ ≤600 LOC.

1. **ปิดรหัส VAT004** (`rules_engine.py` `enabled=False` + เหตุผลใน `code_registry.DISABLED_BY_DESIGN`).
   เจ้าของยืนยัน: ยอดที่ปัดทศนิยมเป็น 2 ตำแหน่งเพื่อแสดงผล (เช่น `12128.830000000002 → 12128.83`)
   **ถูกต้องอยู่แล้ว** — float residue ไม่ใช่ error. คืน `r_vat004` กลับเป็นพฤติกรรมเดิม (ปัด 2 ตำแหน่ง = ไม่ flag)
   และปิดที่ registry. *(ยกเลิกการ "ทำให้ยิง" ที่เคยทำในรอบแรก — ตามที่เจ้าของท้วงว่าไม่จริง)*

2. **หมายเหตุหน่วยไทย/อังกฤษ — สั้น เป็นภาษาคน** (`unit_detection_ext.py`).
   เดิม: `ไฟล์ SHS หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษ (ไทย: กก/นิ้ว/มม · อังกฤษ: kg)` ×หลายบรรทัด
   ใหม่: รวมไฟล์เป็นบรรทัดเดียว ตัด list หน่วย ลงท้าย "ครับ" →
   `หมายเหตุ : ไฟล์ SHS และ TSH หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษครับ`

3. **หน่วยสินค้าทำเหมือนรายการสินค้า** (`super_ultra_viewer.py` — ทั้ง .txt และ .xlsx).
   เดิม: `หน่วย "ปี๊ป" ควรเป็น "ปี๊บ"` → ใหม่: `หน่วย ปี๊ป` (โชว์หน่วยในบิลให้รีเช็ค ไม่ prescribe คำที่ "ควรเป็น"
   ซึ่งระบบอาจเดาผิด — แบบเดียวกับชื่อสินค้า "คำว่าเจียร์"). รูป `ควรเป็น` ยังเก็บใน detail ภายในเพื่อให้
   Precision Council จำแนก typo↔หน่วยขาด ได้ถูก แล้วตัดออกที่ชั้นแสดงผลเท่านั้น.

ด่านกันถอยหลังเพิ่มใน `test_bughunt_recheck.py` (VAT004 ปิด + รูปแบบ "หน่วย X" + หมายเหตุสั้น).
