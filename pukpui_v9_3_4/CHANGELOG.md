# CHANGELOG — ปุ้มปุ้ย (Puopuy)

รูปแบบอิง [Keep a Changelog]; เวอร์ชันปัจจุบันอ่านจาก `config_base.APP_VERSION` (แหล่งความจริงเดียว).
บันทึกรุ่นเก่ากว่า v9.2 ดูที่ `CHANGELOG_v9_1_RELIABILITY.md` (historical).

> **กฎทอง:** golden hash ของผลตรวจ **ห้ามขยับโดยไม่ตั้งใจ**. ทุกบรรทัดด้านล่างที่แตะโค้ด
> พิสูจน์แล้วว่า fixture golden `269ddaed…`, report-determinism `ee4cba65…`, และเทส standalone
> 76/76 **ไม่เปลี่ยน** (รันบน Python 3.12 + เวอร์ชัน lib ที่ล็อกใน `constraints.txt`).

---

## [9.3.4-bugfix] — Full-system bug audit & crash-hardening (2026-06-20)

รอบนี้เป็น **bug-audit ทั้งระบบ** (parser / rules / validators / reporting / core / agents-IO) แล้วแก้
ครบทุกระดับ. พิสูจน์ **golden-neutral**: audit digest บน real_cases (15 บิล) **เท่าเดิมเป๊ะ** ก่อน/หลังแก้
(sentinel ยืนยันสลับโค้ดจริง), เทส standalone **81/81 ผ่าน** (เดิม 79/81 — มี 2 ตัวแดงในแพ็ก GOLDEN).
รายละเอียดเต็มดู `BUGFIX_FULL_AUDIT_20260620_TH.md`.

### Fixed — รายแรง (crash → ข้อมูลหายเงียบ / ไม่ได้รายงาน)
- **[H1] `_money_q` quantize ระเบิด `InvalidOperation` กับยอดมหึมา** (`puopuy_units.py`) — เซลล์เงินมหึมา
  (เกิน Decimal context 28 หลัก) ทำ `parser_p2:113/129`, `parser_p0a:126`, `_reconcile_amounts` ครัช
  → `parse_file` ดักระดับชีต → **บิลทั้งชีตหายเงียบ**. แก้ที่ต้นทาง: คืน `None` แทน raise.
- **[H2] `str.isdigit()` รับ superscript/เลขในวงกลม** (`parser_p0a:322`, `parser_p2:52/196`) — `'²'.isdigit()`
  เป็น `True` แต่ `int('²')` ระเบิด ValueError (พบบ่อยในงานก่อสร้าง m²/m³) → บิลทั้งชีตหาย. แก้เป็น
  `_is_seq_token` (.isdecimal()) — เลขไทย ๕ ยังผ่าน.
- **[H3] อักขระควบคุมในเซลล์ → openpyxl `IllegalCharacterError`** (`reporting_p1.py`) — `build_clean_report`
  คืน False → **ผู้ใช้ไม่ได้รายงานเลย**ทั้งที่ตรวจเสร็จ. แก้: `_xl_safe` sanitize ก่อนเขียนเซลล์.

### Fixed — กลาง
- **[M1]** `parse_date_any` แปลง พ.ศ.→ค.ศ. ของ `datetime` 29 ก.พ. ปีอธิกไม่ guard → ValueError → ไฟล์หาย (`puopuy_dates:29`).
- **[M2]** `_move_processed_files`/`get_files_via_drive`: ข้าม `ตรวจแล้ว_*` + `company_summary*` กันตรวจ output ตัวเองซ้ำ; ย้ายไฟล์ในซับโฟลเดอร์ด้วย (เดิมไม่ย้าย → ตรวจซ้ำทุกครั้ง).
- **[M3]** เทสแดงในแพ็ก GOLDEN: `test_parser_helpers` (อัป assert ตาม FIX-MONTH012 → month 1), `test_file_size_ceiling` (whitelist `parser_p2.py` พร้อมแผนซอย).
- **[M4]** `detail=None` บน issue CRITICAL → `None[:80]` ครัชรายงาน+dashboard (`reporting_p0/p1/p2`) — coerce None.
- **[M5]** `run_rules` guard บิลภายนอกไม่ครบ (เดิม setdefault แค่ 4 คีย์ แล้วอ้าง `bill['company']/['sheet']` ดิบ).
- **[M6]** `summarize_by_company._num(NaN)` คืน NaN → ยอดรวม/อันดับเพี้ยน (`analytics.py`) — coerce NaN→0.

### Fixed — ต่ำ + architectural
- **[L2]** `_D('(1,234.56)')` → -1234.56 (เลขติดลบบัญชี); **[L3]** ย้าย enrichment `CONSTRUCTION_DICT` ไป
  `config_base` ให้ครบ 263 คำทุกเส้น import; **[L4]** `r_itm001` ห่อ quantize เหมือน `r_itm018`;
  **[L5]** `r_itm014` กรอง seq int เหมือน `r_itm013`; **[L6]** `detect_iv_period_mismatch` ไม่ตีเลขรัน 4 หลักล้วนเป็นงวด;
  **[L7]** `r_itm016` ข้าม dedup เมื่อ price=None; **[L8]** รับ seq text `'1.00'`; **[L9]** วันที่ปี 2 หลัก+เวลา;
  **[L-T]** done_dir +PID กันชนวินาทีเดียว; **[ARCH]** `_audit_core_crosschecks` ห่อแต่ละ crosscheck แยกกัน.
- **หมายเหตุ:** `thai_postal` (L1 ที่ agent เสนอ) **ไม่แก้** — เป็น mapping ที่ derive จากข้อมูลจริง + มี pinned test
  (`เชียงใหม่ 58130 → เงียบ`) การ "แก้" จะทำเทสแดง + เสี่ยง false-positive กับที่อยู่อำเภอชายแดนจริง.

---

## [9.3.4] — Quality / Consistency Hardening

รอบนี้เป็น **งานคุณภาพล้วน** (เสถียร/สอดคล้อง/บำรุงรักษา) — ไม่มีฟีเจอร์ใหม่ ไม่เปลี่ยนผลตรวจ.

### Fixed — ความสอดคล้อง (consistency / drift)
- **เวอร์ชันเป็นค่าเดียวทั้งระบบ = 9.3.4.** เดิมป้ายเวอร์ชันปนกัน (`APP_VERSION=9.2`, README v9.2,
  README_PACKAGE v9.1, CERTIFICATION v9.3, prefix แพ็ก `v9_2_hardened`). ตอนนี้ทุกพื้นผิวอ่าน/ตรงกับ
  `config_base.APP_VERSION`. APP_VERSION พิสูจน์แล้วว่า *ไม่อยู่ในสิ่งที่ถูกแฮช*.
- **ล้าง golden hash เก่าที่ค้างในพื้นผิว operational.** fixture ถูก rebaseline `d8bcde85 → 269ddaed`
  (ADR-041) และ corpus `ec61907f/f1ac8421 → d6b23d12` แต่ `Makefile`, `.github/workflows/ci.yml`,
  `MAINTENANCE.md` ยังอ้างค่าเก่า (รวมถึง "81 ไฟล์" ที่ควรเป็น "106 ไฟล์"). แก้ครบแล้ว.

### Added — guard กันปัญหาเดิมกลับมา (root-cause)
- **`test_golden_single_source.py` คุม fixture hash + Makefile/CI/MAINTENANCE.** เดิมเทสนี้คุมแค่
  corpus hash บน allowlist เดิม → ช่องที่ทำให้ `d8bcde85` ค้างได้. เพิ่ม: (1) อ่าน
  `baseline_fixture.json._sha256` เป็น single source ของ fixture, แบน prefix ปลดระวาง `d8bcde85`,
  บังคับให้พื้นผิวที่พูดถึง fixture อ้าง `269ddaed`; (2) เอา Makefile/ci.yml/MAINTENANCE เข้า
  OPERATIONAL_SURFACES; (3) เช็คเวอร์ชัน — title ของเอกสารผู้ใช้ต้องสะกด `v<APP_VERSION>`.
  *พิสูจน์ว่าจับจริง:* ใส่ `d8bcde85` กลับเข้า Makefile → เทสแดงทันที.
- **`DOCS_INDEX.md` + `CHANGELOG.md`.** จัดเอกสาร ~48 ไฟล์เป็น 3 ชั้น (active / ADR / historical)
  ลดภาระการค้นหา โดยไม่เขียนทับหลักฐานประวัติ.

### Changed — คุณภาพโค้ด (code quality, golden-neutral)
- **รวมอัตรา VAT 7% เป็นค่าคงที่เดียว `puopuy_units.VAT_RATE`.** เดิม `Decimal('0.07')` ฮาร์ดโค้ดซ้ำใน
  `rules_engine_rules_b/c`, `parser_p0a/p2`. ใช้ค่ากลางทุกจุดคำนวณ VAT (ค่าเท่าเดิมเป๊ะ).
- **บังคับ branch coverage ใน GitHub CI (≥85%).** เดิม `run_ci.sh` บังคับ branch ≥85 แต่ GitHub CI
  รายงานเฉย ๆ. ตั้ง `PUOPUY_COV_BRANCH_MIN=85` ใน `ci.yml` + เพิ่ม `make coverage` → local==CI เข้มเท่ากัน.

### Removed
- โค้ดตาย: `return vat_rows` ซ้ำซ้อน (บรรทัดที่เข้าไม่ถึง) ใน `parser_p1._detect_vat_rows`.

---

ประวัติก่อนหน้า: ดู `CHANGELOG_v9_1_RELIABILITY.md`, `DELIVERY_v9_2_READY_TH.md`,
`BUGHUNT_REPORT_v9_3_1_TH.md`, และทะเบียน ADR ใน `INVARIANTS/DECISIONS.md`.

[Keep a Changelog]: https://keepachangelog.com/
