# 🔧 บันทึกการแก้ P1/P2 (รอบ 2) — ปุ้มปุ้ย v9

**วันที่:** 1 มิถุนายน 2026
**หลักการ:** แก้เฉพาะความเสถียร/บำรุงรักษา — ไม่แตะ business logic
**พิสูจน์:** oracle PASS (hash `1dcc6fb3…`) + determinism ทุก seed + E2E สร้าง Excel ครบ

> ต่อจากรอบแรกที่แก้ P0 ไปแล้ว 3 เรื่อง (nondeterminism, file-handle, import-guard)
> รอบนี้แก้เพิ่ม **6 เรื่องปานกลาง (P1/P2) + 2 เรื่องเล็กน้อย** = รวมจัดการ 8/9 เรื่อง

---

## ✅ ที่แก้สำเร็จในรอบนี้ (8 เรื่อง)

### #4 — Validator Isolation (ปานกลาง) — main
ห่อ `check_invoice_sequence` / `check_product_typos` / `summarize_by_company`
แต่ละตัวใน try/except แยกกัน. ตัวใดพัง → log SYS003 + คืน list/dict ว่าง แล้วไปต่อ
**เดิม:** ตัวใดพัง = ล้มทั้งรอบ (parse+56 rules เสร็จแล้วเสียเปล่า)
**พิสูจน์:** จำลอง typo พัง → pipeline ไปต่อได้ + สร้าง Excel ได้ + SYS003 ถูกบันทึก ✅

### #5 — Lazy-Builder Guards (ปานกลาง) — state.py
เพิ่มคำเตือนชัดเจนว่า "ทุกจุดที่อ่าน cache ต้องมี lazy-init guard ก่อน"
ตรวจแล้วทุก call site ปัจจุบันมี guard ครบ (`if state.X is None: _build_X()`)

### #6 — CFG Immutable (ปานกลาง) — config.py
freeze `CFG` เป็น `MappingProxyType` (read-only) หลังนิยามจบ
ตรวจแล้วไม่มีโค้ดไหน mutate `CFG[..]=..` (มีแต่ `VERIFY_CFG` ที่ต้อง toggle จึงคงเป็น dict)
**ประโยชน์:** กันเผลอแก้ค่า config กลาง runtime → ค่าคงเส้นคงวา ตามรอยได้
**พิสูจน์:** อ่าน `CFG['x']`/`CFG.get()` ปกติ, mutate ไม่ได้แล้ว (TypeError), oracle PASS ✅

### #7 — State Cache Cleanup (ปานกลาง) — main `reset_run_state()`
เพิ่มการเคลียร์ state caches (`_CONSTRUCTION_DICT_BY_LEN` ฯลฯ) เป็น None ต้นรอบ
**เดิม:** เคลียร์แค่ `_FUZZY_DICT_CACHE`/`_PYTHAINLP_CACHE` → state caches ค้างข้ามรอบ
**พิสูจน์:** รัน 2 รอบในเซสชันเดียวได้ผลเหมือนกัน (ไม่มี state bleed) ✅

### #8 — Error Context (ปานกลาง) — validators.py
เพิ่ม `[file]` ต้น detail ของ issue "IV ซ้ำเลขท้าย" / "IV ถอยหลัง"
**ประโยชน์:** คนตรวจเห็นไฟล์ที่มีปัญหาทันที (เดิมมีแต่ vendor/วันที่ ต้องไล่หาเอง)
oracle เก็บแค่ type/iv/severity (ไม่เก็บ detail) → การเติม file ไม่กระทบ oracle ✅

### #9 — Analytics API Clarity (ปานกลาง) — config.py + main
เพิ่ม documentation ว่า `CONF_TIERS` ถูกใช้ 2 บริบท (แสดงผล tier + ตัดสิน logic pythainlp)
เตือนว่าแก้ค่าเดียวกระทบทั้งหน้าตาและพฤติกรรม — ถ้าจะแยกให้สร้าง dict ใหม่ อย่าแก้ค่าเดิม

### #11 — O(N²) Observability (เล็กน้อย) — validators.py
เพิ่มข้อความ actionable เมื่อชนเพดาน `MAX_TYPO_NAMES` (แบ่ง batch / ปรับ CFG)
+ note ว่าอัลกอริทึม >500 ชื่อใช้ sliding-window ลด O(n²) อยู่แล้ว
**ไม่แตะ algorithm** (เปลี่ยน = เสี่ยงผลตรวจ) — ปรับแค่ observability

### #12 — Excel Scaling Note (เล็กน้อย) — reporting.py
เพิ่ม note ใน `build_clean_report` ว่าเมื่อถึง scale แสน-บิลควรทำอะไร
(แบ่งไฟล์ / xlsxwriter / batch styling) เรียงตามความเสี่ยงน้อย→มาก
**ไม่แตะ Excel layer** (ปัจจุบัน efficient พอสำหรับหลักพัน-หมื่นบิล)

---

## ⏭️ ที่ตัดสินใจ "ไม่แก้" (1 เรื่อง) — พร้อมเหตุผล

### #10 — Parser/Rules Extraction (เล็กน้อย/debt)
**ไม่แยกตอนนี้** — ตรงตามที่ HANDOVER.md เดิมแนะนำ เพราะ:
- ใช้เวลา ~18 ชม. + แตะ cross-import หลายสิบจุด (แต่ละจุด silent-break risk)
- ปัจจุบัน layering สะอาด ไม่มี circular → แยกทีหลังได้ปลอดภัย
- ประโยชน์ต่ำ (โค้ดทำงานดีอยู่แล้ว) เทียบความเสี่ยงสูง = ไม่คุ้มตอนนี้
- `state.py` foundation พร้อมแล้ว → เมื่อมีเวลา/ความจำเป็นค่อยทำผ่าน oracle ทีละ step

---

## ผลการทดสอบรวม

| การทดสอบ | ผล |
|----------|-----|
| syntax ทุกไฟล์ (6 ไฟล์) | ✅ OK |
| oracle check (พฤติกรรมเดิม 100%) | ✅ PASS (`1dcc6fb3…`) |
| #4 isolation (typo พัง→ไปต่อได้) | ✅ ผ่าน |
| #6 CFG read-only + อ่านได้ปกติ | ✅ ผ่าน |
| #7 multi-run ไม่มี state bleed | ✅ ผ่าน |
| E2E สร้าง Excel 9 ชีต | ✅ สมบูรณ์ (248 KB) |
| Excel determinism ทุก seed | ✅ เหมือนกัน |

---

## สรุปทั้ง 2 รอบ (P0 + P1/P2)

**แก้สำเร็จ 11 เรื่อง** จากทั้งหมด 12 เรื่องใน architectural audit:
- รอบ 1 (P0): nondeterminism, file-handle (มีอยู่แล้ว), import-guards
- รอบ 2 (P1/P2): isolation, lazy-guard, CFG-immutable, cache-cleanup, error-context, API-clarity, O(N²)-observability, Excel-scaling-note

**ไม่แก้ 1 เรื่อง:** #10 parser/rules extraction (เสี่ยงสูง/ประโยชน์ต่ำ — รอเวลาที่เหมาะสม)

**ทุกการแก้ไม่กระทบผลตรวจบิลแม้แต่น้อย** (ยอดเงิน/กฎ/sequence/typo เหมือน baseline 100%)
