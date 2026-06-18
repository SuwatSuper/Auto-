# CHANGELOG — ปุ้มปุ้ย (Puopuy)

รูปแบบอิง [Keep a Changelog]; เวอร์ชันปัจจุบันอ่านจาก `config_base.APP_VERSION` (แหล่งความจริงเดียว).
บันทึกรุ่นเก่ากว่า v9.2 ดูที่ `CHANGELOG_v9_1_RELIABILITY.md` (historical).

> **กฎทอง:** golden hash ของผลตรวจ **ห้ามขยับโดยไม่ตั้งใจ**. ทุกบรรทัดด้านล่างที่แตะโค้ด
> พิสูจน์แล้วว่า fixture golden `269ddaed…`, report-determinism `ee4cba65…`, และเทส standalone
> 76/76 **ไม่เปลี่ยน** (รันบน Python 3.12 + เวอร์ชัน lib ที่ล็อกใน `constraints.txt`).

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
