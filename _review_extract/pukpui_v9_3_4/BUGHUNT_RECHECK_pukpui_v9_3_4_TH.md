# รายงานรีเช็คบั๊กทั้งระบบ — pukpui v9.3.4 (ทุกหมวดหมู่)

วันที่: 2026-06-18 · ขอบเขต: ทั้งระบบ (parser / rules / validators / reporting / agents+concurrency / core utils)
วิธีตรวจ: รันระบบจริง + เทสต์ทั้งชุด + รีวิวโค้ดเชิงลึกทุก subsystem แบบขนาน — **ทุกบั๊กยืนยันด้วยการรันจริง (reproduce)**

> หมายเหตุสภาพแวดล้อมที่รีเช็ค: Python 3.11 / numpy 2.4 (ระบบล็อก 3.12 / numpy 2.2) → version gate เตือนถูกต้อง
> ไม่ใช่บั๊ก แต่ทำให้ golden hash จริงเทียบไม่ได้ (คาดไว้แล้ว). เทสต์ logic ผ่าน 76/77
> (ตัวที่ตก = `test_package_integrity` ล้มเพราะรันจาก zip ไม่ใช่ git repo — ไม่ใช่บั๊กโค้ด).

---

## สรุปสุขภาพระบบ (สิ่งที่พิสูจน์แล้วว่า "สะอาด")

- **Determinism แข็งแรงมาก**: digest นิ่งทุกรอบ/ทุก `PYTHONHASHSEED`, parallel==serial ตรงเป๊ะ, golden fixture hash ตรง
- **เลขผู้เสียภาษี 13 หลัก checksum**: ถูกต้อง 100% (เทียบ 100,000 เคสสุ่ม) เคสขอบ `11-rem=10→0` จัดการถูก
- **คณิต VAT 7% / tolerance 0.50**: Decimal + ROUND_HALF_UP ไม่ปน float, ขอบ 0.50 ถูกต้อง
- **Concurrency**: parallel==serial เป๊ะ (golden+issues+recoveries+ลำดับ), idempotent, reset state ครบ, ไม่มี mutable default
- **Offline guarantee**: `llm_provider` ผ่าน `offline_guard`, default ไม่แตะ network
- ไม่มี mutable default arg, ไม่มี bare `except:`, ไม่มี float-equality บนเส้นทางผลตรวจ

ระบบ harden ดี (try/except รายไฟล์/รายบิล, atomic write) — บั๊กที่เจ้อยู่ใน **ช่อง logic ที่เทสต์ปัจจุบันไม่ครอบ**

---

## 🔴 บั๊กสำคัญ (ยืนยันแล้ว — กระทบผลตรวจ)

### #1 [HIGH] ตรวจ "เลข IV ซ้ำ / ถอยหลัง" หลุดเงียบ เมื่อเลขข้ามหลัก 100/1000
- **ตำแหน่ง**: `validators.py:143` (และ `:228` ตัว ascending)
- **เหตุ**: `_seq` ถูกเก็บเป็น `int("0100")=100` → ศูนย์นำหาย → `IV0100`(len 3) กับ `IV0099`(len 2) ถูกมองว่า "ฟอร์แมตต่างกัน" แล้ว `continue` ข้ามทั้งกลุ่ม ทั้งที่ raw 4 หลักเท่ากัน
- **รันจริง**:
  | input (vendor/วันเดียวกัน) | ผล |
  |---|---|
  | `IV0100, IV0100, IV0099` | **0 issue** ❌ ไม่เจอเลขซ้ำ IV0100 |
  | `IV0102, IV0102, IV0101` (control) | 2 issue ✅ เจอซ้ำ+ถอยหลัง |
  | `IV1000, IV1000, IV0999` | **0 issue** ❌ ไม่เจอซ้ำ |
- **ผลกระทบ**: false-negative ใน "หัวใจระบบ" (จับใบกำกับเลขซ้ำ/ผิดลำดับ); เลขรัน zero-pad ข้าม 100/1000 ในเดือนเดียวพบบ่อย
- **แก้**: เทียบความยาว string ดิบ `len(m_seq.group(1))` แทน `len(str(int))` (เก็บ `_seq_len` ตอนสร้าง entry บรรทัด 137)

### #2 [MEDIUM] กฎ VAT004 (ปัดเศษ) เป็นกฎตาย — เปิดใช้อยู่แต่ไม่เคยทำงาน
- **ตำแหน่ง**: `rules_engine_rules_b.py:379-381` (registry `enabled: True`)
- **เหตุ**: `round(fv, 2)` ก่อน แล้วเช็ก `len(dec_str) > 2` → หลังปัดเป็น 2 ตำแหน่ง เป็นไปไม่ได้ที่จะ > 2
- **รันจริง**: `subtotal=100.123 → []`, `12345.6789 → []` (ทุกค่า) → แดชบอร์ด "เห็นว่ามีกฎปัดเศษ" แต่ไม่ตรวจอะไรเลย
- **แก้**: ปัดที่ความละเอียดสูงกว่า (เช่น 6) เพื่อกัน float residue แล้วค่อยเช็กว่าเกิน 2 ตำแหน่งจริงไหม

### #3 [MEDIUM] ยอดเงินที่มี label ติดกันถูกอ่านเป็น "เลขที่ใบกำกับ"
- **ตำแหน่ง**: `parser_p1.py:95` — `ANTI_PREFIX` ขาด `VAT/NET/SUM/AMT/TOTAL`
- **รันจริง** (ผ่าน `_pick_best_iv`): `"VAT 1416233" → VAT1416233` ❌, `"NET 999999" → NET999999` ❌, `"SUM 250000" → SUM250000` ❌ ; ขณะที่ `"REF 123456"/"TAX 123456" → None` ✅ (มีใน list แล้ว)
- **ผลกระทบ**: `VAT` เป็น label บนใบกำกับที่พบบ่อยสุดแต่ไม่อยู่ใน ANTI_PREFIX → เสี่ยงอ่านยอด VAT เป็นเลขเอกสาร
- **แก้**: เพิ่ม `'VAT','NET','SUM','AMT','TOTAL','BAHT'` เข้า ANTI_PREFIX

### #4 [MEDIUM] `_D()` รับ "nan"/"inf" → Decimal ไม่จำกัด → VAT ผ่านหลอก
- **ตำแหน่ง**: `puopuy_units.py:57-60`
- **รันจริง**: `_D('nan')→NaN`, `_D('inf')→Infinity`, `_D('1e999')→1E+999`; `r_vat001(subtotal=inf) → []` (บิลยอด infinity ผ่านการตรวจ VAT เงียบ)
- **หมายเหตุ reachability**: parser มี `math.isfinite` กันไว้ จึงไม่เกิดจากไฟล์จริงตรง ๆ แต่ leaf contract ("parse ไม่ได้ → None") ถูกละเมิด เสี่ยงกับ caller อื่น/ข้อความ OCR (`#NUM!`)
- **แก้**: หลังสร้าง Decimal เช็ก `if not d.is_finite(): return None`

### #5 [MEDIUM] วัน 29 ก.พ. ปีอธิกสุรทิน (พ.ศ. 4 หลัก) ถูกปฏิเสธ
- **ตำแหน่ง**: `puopuy_dates.py:70-75` (path strptime)
- **รันจริง**: `parse_date_any("29/2/2567") → None` (ควรเป็น 2024-02-29; พ.ศ.2567=ค.ศ.2024 อธิกสุรทินจริง) เพราะสร้าง `datetime(2567,2,29)` ก่อนลบ 543 → error
- **หมายเหตุ**: path 2 หลัก `"29/2/67"` ถูกต้อง — บั๊กเฉพาะ พ.ศ. 4 หลักผ่าน strptime; อาจลามไป DT004/DT005 ผิด

---

## 🟡 บั๊กรอง (ยืนยันแล้ว — false positive / กรณีขอบ)

### #6 [LOW-MED] `r_addr005` คว้าเลข 5 หลัก**ตัวแรก**เป็นไปรษณีย์ (ควรเป็นตัวท้าย)
- `rules_engine_rules_c.py:132` ใช้ `re.search` (ตัวแรก) ขณะที่ฝาแฝด `_addr_parse_smart` (`rules_engine_rules_a.py:172`) ใช้ `zips[-1]` (ท้าย) ถูกต้อง
- รันจริง: `"เลขที่ 12345 หมู่ 5 กรุงเทพ 10240"` → ❌ ฟ้อง "ไปรษณีย์ 12345 ไม่ตรงกรุงเทพฯ" (ที่จริง 10240 ถูก)

### #7 [LOW-MED] `_dic_find_seq` init `best=0` → บิลรายการเดียวอาจสกัด item ไม่ได้เลย
- `parser_p0a.py:297` — `score = len(ints)*10 - c` ติดลบได้เมื่อ seq col index ≥10 → คืน `(None,)*6` → ไม่ได้ line item สำหรับบิล item เดียว
- แก้: init `best = -10**9`

### #8 [LOW-MED] `check_iv_date_sequence` สกัดเลขไม่สม่ำเสมอ → false positive
- `validators.py:290` — IV ≥8 หลักใช้ last-4, 4-7 หลักใช้ทั้งก้อน → ปนกันในเดือนเดียวเทียบกันไม่ได้ → ฟ้อง "IV↔วันที่ถอยหลัง" ผิด

### #9 [LOW] `r_dt003` ตรวจ digit-swap ปี เป็น branch ตาย
- `rules_engine_rules_a.py:507` — โค้ดอยู่ band พ.ศ. (2500-2600) แต่ parser แปลงเป็น ค.ศ.ไปแล้ว (พิมพ์ผิด 2658→ปี 2115) → ตกไป branch "คลุมเครือ" แทน ข้อความ digit-swap ไม่เคยขึ้น (ค่ายังถูกฟ้องว่าน่าสงสัย ผลกระทบจำกัด)

---

## ⚪ ข้อสังเกต LOW / defensive (ยืนยันแล้ว — ไม่ถึงบั๊กในเส้นทางจริง)

- กฎหลายตัว index ตรง ๆ `it['qty']/['unit']` / `bill['company']/['sheet']` → KeyError ถ้าบิลไม่ครบ key แต่ orchestrator ห่อ try/except รายบิล (parser จริงใส่ key ครบเสมอ) → defensive เท่านั้น
- `r_vat006/007` crash ถ้า money เป็น `bool`; `r_itm013` false positive ถ้า seq เป็น string — parser จริงไม่ผลิตเคสนี้
- `parser_p0._pick_best_iv_safe` หลุด sync กับ `_pick_best_iv` (ขัด ADR-041 "twin") — ไม่มี call site ใน production
- `parser_p2.py:170` ช่วงปี `_filename_period_ce` แคบกว่า date parser → time-bomb หลัง พ.ศ.2582
- `config.py:111` `normalize_ocr` แทนสระสั้น→ยาวไม่มีเงื่อนไข (`บริษัท→บรีษัท`) — ปลอดเพราะ default ปิด OCR
- `thai_postal.py` prefix เสริมบางจังหวัดผิด (พังงา 83=ภูเก็ต ฯลฯ) → check อ่อนลง (false-negative) ไม่ก่อ false positive
- วันที่เลขไทย `๒๕๖๙-๐๑-๑๕ → None` (แต่ `๕/๕/๖๙` ใช้ได้) — จัดการเลขไทยไม่สม่ำเสมอ
- `issue_consolidator.py:44,49` hardcode lane set ขนานกับ `code_labels` (maintainability)
- รายงาน advisory ของ agent ประทับ `datetime.now()` — ไม่ไหลเข้า golden hash (benign)

---

## ลำดับแนะนำการแก้ (ตามผลกระทบจริง)

1. **#1** IV ซ้ำ/ถอยหลังหลุด — one-line fix, ผลกระทบสูงสุด, ไม่ควรกระทบ false-positive
2. **#3** VAT label เป็น IV — เพิ่มคำใน ANTI_PREFIX
3. **#4** nan/inf ใน `_D` — เพิ่ม `is_finite()` guard
4. **#2** VAT004 กฎตาย — แก้ลำดับ round/check
5. **#5** 29 ก.พ. พ.ศ. 4 หลัก — แปลงปีก่อนสร้าง datetime

> ⚠️ ทุกการแก้ logic จะเปลี่ยน golden hash → ต้อง regenerate baseline + รัน CI ใหม่ตามวินัย golden ของระบบ

**สถิติ**: 22 จุด (5 สำคัญ + 4 รอง + 13 LOW/defensive). หมวด concurrency/agent + checksum + VAT math + determinism = สะอาด.
