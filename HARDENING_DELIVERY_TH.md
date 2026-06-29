# 🛡️ HARDENING DELIVERY — ปุ้มปุ้ย v9.2 (เสริมความแข็งแรง) — ส่งมอบ

> ภารกิจ: **STABILIZE & HARDEN** (ไม่เพิ่มฟีเจอร์) — ทำให้ระบบ "หยุดงอกบั๊กรายวัน".
> หลักเหล็กตลอดงาน: **golden audit hash ห้ามขยับ** · ทุกการแก้มี diagnose ก่อน · ทุก defer มีเหตุผล.
> สรุปการตัดสินใจเชิงลึกทั้งหมดอยู่ใน `P3_FOLLOWUP_TH.md` §5 (Decision Log).
> ค่า hash ทุกตัวอธิบายไว้ที่ `GOLDEN.md` (แหล่งอ้างอิงเดียว).

---

## ✅ สิ่งที่แก้ไปทั้งหมด (19 จุด · golden ไม่ขยับสักรอบ)

### P0 — บั๊กที่ทำร้ายแบบเงียบ (ปิดแล้ว)
- **P0-1 ข้อมูล master หาย** — เครื่องมือ golden/verify 7 ตัวเคยเขียนทับ `master_companies.json`
  ของผู้ใช้ด้วย stub. แก้ที่ `golden_snapshot.write_master_file`: สำรอง + คืนค่าอัตโนมัติ (atexit).
- **P0-2 แดชบอร์ดโชว์ "ตรง" หลอก** — `config.FIELD_CODES` ขาด 12 รหัส (CMP005/DOC003/VAT009…)
  → เติมครบ + `test_field_codes_coverage.py` กัน drift.

### P1 / P2 — เสถียรภาพ + ความถูกต้อง
- **P1-3 version_gate ดับเงียบ** — เขียนเหตุผลไป stderr เสมอ + exit code เฉพาะ (86 ≠ hash-mismatch 1).
- **P1-4 วันที่ 2 หลัก พ.ศ./ค.ศ. ขัดกัน** — `'1/1/15'→1972` ผิด; แก้ให้ใช้กติกาเดียวกับ `_ivp_year2_to_ce`
  (ปี 66-69 ของ corpus ปัจจุบันผลเท่าเดิม → golden ไม่ขยับ) + `test_date_2digit_year.py`.
- **P2 hashseed นอก VS Code** — `hashseed_guard.py` บังคับ `PYTHONHASHSEED=0` บนเส้น CLI (re-exec ครั้งเดียว).
- **P2 SuperAgent QA** — `_EXPECTED` เติม `verification` (9→10) ให้ QA นับถูก.

### P3 — Maintainability (single source)
- **code_registry.py** — แหล่งความจริงเดียวของ "จักรวาลรหัส" (parser/rules/crosscheck 3 ชั้น)
  + `test_code_tables_consistency.py` (MAP+FIELD_LAYOUT ตามทันทุกรหัส) → เพิ่มกฎใหม่ลืม table ไหน = CI แดง.

### A — Hardening ชั้น advisory/รายงาน (ทนข้อมูลเพี้ยน ไม่ครัช)
- A1 `build_consolidated_report` ชื่อไฟล์เปล่า · A2 `ultra_agent` (prevat ไม่ใช่ตัวเลข/iv_date string/บล็อกพัง)
  · A3 `super_ultra_viewer` BE-year guard · A4 lens VAT003 (vat=None → abstain) · A5 รายงาน issue ขาดคีย์
  → workbook ไม่ล่มทั้งก้อน · A6 คอมเมนต์ VAT002 ตรง ADR-005 · `test_a_hardening.py` (11 เช็ค).

### B — ตาข่ายนิรภัย / CI
- B1 `ci.yml` version_gate บล็อกจริง (เลิก `|| true`) · B2 numpy เข้า version gate ·
  B3 verify_golden baseline หาย → fail-closed · B4 coverage_gate + parse_canary เข้า GitHub CI ·
  B6 dedup Tier-1 set → `agents/_shared.TIER1`.

### C — คุณภาพ
- C1 `AgentError` พก result (traceback เต็ม) ตอน critical crash.
- เอกสาร golden hash: `GOLDEN.md` (แหล่งอ้างอิงเดียว) + banner เอกสารประวัติ + แก้ constraints.txt.

### #1 / #2 / #3 — รอบ STABILIZE & HARDEN (forensic)
- **#1 merged cells → NO-FIX (มีหลักฐาน)** — `diagnose_merged_cells.py` พิสูจน์บนไฟล์จริง: parser
  ทน merge ได้ (ทุกบิล reconcile, taxid ครบ); ติดตั้งเป็น guard. *ค้างให้คุณรันบน 106 ไฟล์.*
- **#2 pytest collect crash → FIXED** — `conftest.py` รันเทสเป็น subprocess (ไม่ import) → pytest ใช้ได้
  โดยไม่แตะไฟล์เทสเลย.
- **#3 lens consensus → DEFERRED** — เงื่อนไขปลดล็อก 2 ข้อยังไม่ครบ (บันทึกเหตุผล).

---

## 🧪 ผลทดสอบยอมรับ (acceptance — รันก่อนส่งมอบ)

> รันบน sandbox Python 3.11 + `PUOPUY_ALLOW_VERSION_MISMATCH=1` (เครื่องนี้ไม่ใช่ 3.12).
> hash-gate ที่รันได้จริงที่นี่ = **fixture `d8bcde85`** (golden 81/106 ไฟล์จริงต้องรันบนเครื่องคุณ).

| ด่าน | ผล |
|---|---|
| golden fixture invariant (engine==agent==baseline) | ✅ ผ่าน |
| golden fixture hash | ✅ `d8bcde85…` (ไม่ขยับ) |
| doc single-source + merged-cell guard | ✅ ผ่าน |
| run_ci.sh (เทส standalone ทั้งหมด) | ✅ **53 ด่านผ่าน** |
| pytest (ทุกสคริปต์ผ่าน subprocess collector) | ✅ **48 passed** |
| coverage gate (line ≥90% แกน) | ✅ ผ่าน |
| reachability / report-det / reset-completeness guard (Round-2) | ✅ ผ่าน |

**เทสกันถอยหลังใหม่ในรอบนี้ (7 ไฟล์):** `test_field_codes_coverage` · `test_date_2digit_year` ·
`test_code_tables_consistency` · `test_a_hardening` · `diagnose_merged_cells` (guard) · `conftest.py` (pytest) ·
+ ขยาย `test_golden_single_source`.

---

## 🔑 สิ่งที่ "ต้องทำเอง" บนเครื่องที่มีข้อมูลจริง (Python 3.12) — ปิด hash-gate ระดับ production

```bash
# 1) ยืนยัน golden 106 ไฟล์ ไม่ขยับ (ต้องได้ 35b2f7c8 ทั้ง 3 บรรทัด)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . <โฟลเดอร์ 106 ไฟล์>

# 2) วินิจฉัย merged cells บนข้อมูลจริงทั้งหมด (ถ้าขึ้น 🚩 ค่อยทำ handler — ดู P3_FOLLOWUP §5 #1)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 diagnose_merged_cells.py <โฟลเดอร์ 106 ไฟล์>

# 3) report determinism บนข้อมูลจริง (absolute report hash — บน 106 ไฟล์ควรได้ fff69fc6)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_report_det.py <โฟลเดอร์ 106 ไฟล์>

# 4) (ถ้ามี) verify parallel == serial บนข้อมูลจริง
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_parallel.py <โฟลเดอร์> 8

# 5) CI เต็มในเครื่อง
bash run_ci.sh            # standalone · หรือ ·  python3 -m pytest   (ต้องเขียวทั้งคู่)
```

> **Round-2 (PART A/B/C)** เพิ่ม guard เชิงโครงสร้าง: `test_reachability` (ไม่มี floating module/CI
> เขียวบนโค้ดตาย) · `test_report_det` (รายงานนิ่ง) · `test_reset_completeness` (parse 2 รอบเท่ากัน) ·
> retire `puopuy_ingest` (floating). B2/C1/C2 = defer/no-fix พร้อมหลักฐาน (ดู `P3_FOLLOWUP_TH.md §6`).

> ❗ ถ้าข้อ 1 ได้ hash ต่างจาก `35b2f7c8` = มีพฤติกรรมเปลี่ยน → **หยุด ย้อนหาเหตุ ห้าม commit/rebaseline**
> โดยไม่มีหลักฐาน before/after (กฎ R3). ปกติทุก fix ในรอบนี้ออกแบบให้ "ไม่ขยับ golden" แล้ว.

---

## 📜 ประวัติการเปลี่ยนแปลง (branch `claude/focused-lovelace-otUNP`)
ดู `git log` — commit หลัก: P0 → P1+P2 → P3 → A → B+C → doc-golden → #1 → #2,#3.
ทุก commit ยืนยัน fixture `d8bcde85` คงเดิม + CI เขียว.
