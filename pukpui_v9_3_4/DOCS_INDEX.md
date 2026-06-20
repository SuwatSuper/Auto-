# 📑 DOCS_INDEX — สารบัญเอกสาร ปุ้มปุ้ย v9.3.4

> เดิมเอกสารกระจัดกระจาย ~48 ไฟล์ปนกันระหว่าง "ของใช้จริงตอนนี้" กับ "หลักฐานประวัติ" ทำให้
> หาเอกสารที่ต้องอ่านยาก. ไฟล์นี้คือ **จุดเริ่มต้นเดียว** — บอกว่าอ่านอะไรก่อน และอะไรคือบันทึกอดีต.
>
> **กฎ:** ไฟล์ในกลุ่ม "หลักฐานประวัติ" ลงวันที่/เวอร์ชันไว้ตามเวลานั้น — เลข hash/เวอร์ชันในนั้น
> ถูกต้องสำหรับยุคของมัน **ห้ามเขียนทับ** (ดู `test_golden_single_source.py` ที่จงใจไม่สแกนไฟล์เหล่านี้).
> ค่าปัจจุบันที่เชื่อถือได้อยู่ใน `GOLDEN.md` (hash) และ `INVARIANTS/DECISIONS.md` (ADR/baseline).

---

## 🟢 1. เริ่มที่นี่ (Active / Operational — อ่านก่อน)

| ไฟล์ | ใช้ทำอะไร |
|---|---|
| `README.md` | ภาพรวมระบบ + วิธีรัน + ปรัชญาการตรวจ |
| `อ่านก่อนใช้.md` | คู่มือผู้ใช้ปลายทาง (ภาษาไทยล้วน) |
| `QUICKSTART_VSCODE_TH.md` | เริ่มงานบน VS Code (ฉบับ offline) |
| `MAINTENANCE.md` | กฎที่คนดูแลต้องจำ (golden discipline, single source, lazy cache) |
| `GOLDEN.md` | 🔒 อภิธานศัพท์ hash ทางการ — **แหล่งอ้างอิง hash เดียวสำหรับมนุษย์** |
| `INVARIANTS/DECISIONS.md` | 📒 สมุด ADR (append-only) + ตัวเลข baseline/สภาพแวดล้อมที่ล็อก |
| `agents/README_AGENTS_TH.md` | สถาปัตยกรรม multi-agent (orchestrator / mesh / lenses) |
| `MESH_MANUAL_TH.md` | คู่มือชั้น mesh (data plane ของ agent) |
| `README_PACKAGE_TH.md` | คู่มือแพ็กเกจที่ส่งมอบ |
| `HANDOVER_TH.md` | เอกสารส่งมอบระบบ |
| `CERTIFICATION_FINAL_TH.md` | ใบรับรองปิดโปรเจค (สถานะคุณภาพล่าสุด) |
| `CHANGELOG.md` | บันทึกการเปลี่ยนแปลงตามเวอร์ชัน (รวมรอบ hardening v9.3.4) |

## 🔵 2. บันทึกการตัดสินใจสถาปัตยกรรม (ADR — อ้างอิงเมื่อจะแก้)

ทะเบียน ADR ทั้งหมดอยู่ใน `INVARIANTS/DECISIONS.md` (§ ADR-LOG). ไฟล์ ADR เดี่ยวที่แยกไว้:

`ADR-023` (ปิด roadmap) · `ADR-024` (กันยอดเงินถูกอ่านเป็นเลขที่บิล) · `ADR-038` (กัน parser ครัช numeric) ·
`ADR-039`/`ADR-040` (master file atomic + backup กัน data loss) · `ADR-041` (หางทศนิยม float — เหตุที่ fixture
rebaseline เป็น `269ddaed`) · `ADR-042` (label เลขภาษีแบบ variant) · `ADR-043` (typo "ฟิมล์" + หน่วยภาษา)

## ⚪ 3. หลักฐานประวัติ (Historical / Archive — ห้ามแก้, เก็บไว้ตามรอย)

> บันทึกงานแต่ละรอบ/รายงานตรวจ/handoff — มีค่าเชิงตรวจสอบย้อนหลัง. **เลข hash/เวอร์ชันในกลุ่มนี้
> เป็นค่า ณ เวลานั้น** (เช่น fixture เคยเป็น `d8bcde85`, corpus เคยเป็น `ec61907f`/`f1ac8421`) — ถูกต้องตามยุค.

- **รายงานตรวจ/แก้บั๊ก:** `AUDIT_FIXES_TH.md` · `AUDIT_v9_1_TH.md` · `AUDIT_v9_2_TH.md` · `BUGFIX_GROUP1_TH.md` · `BUGHUNT_REPORT_v9_3_1_TH.md`
- **แก้เคสเฉพาะ:** `FIX_11_06_69_TH.md` · `FIX_ADDR_FULL_TH.md` · `FIX_FALSEPOS_REPORT_TH.md`
- **handoff/ส่งต่อรอบ:** `HANDOFF_FIX_HONESTY_TH.md` · `HANDOFF_NEXT_CHAT_TH.md` · `HANDOFF_REPORT_AND_IVCHECK_TH.md` · `HANDOFF_SESSION_REPORT_TH.md` · `_SESSION_HANDOFF.md`
- **บันทึกพาส/รอบงาน:** `PASS3_DECOUPLING_TH.md` · `PASS4_MESH_TH.md` · `PASS5_FINAL_TH.md` · `P1_P2_FIXES_SUMMARY_TH.md` · `P3_FOLLOWUP_TH.md` · `PARALLEL_MERGE_FOLLOWUP_TH.md`
- **ส่งมอบ/แข็งแกร่ง/เพอร์ฟ:** `DELIVERY_v9_2_READY_TH.md` · `HARDENING_DELIVERY_TH.md` · `OPTIMIZE_REPORT_TH.md` · `PERFORMANCE_BASELINE_TH.md` · `PERF_BASELINE.md`
- **golden/กู้ระบบ/แผน:** `GOLDEN_EVIDENCE_v9_3_1.md` · `REBUILD_STATUS_TH.md` · `RULES_COVERAGE_ROADMAP_TH.md` · `CHANGELOG_v9_1_RELIABILITY.md`
- **prompt เก่า:** `PROMPT_สรุป+แก้false_positive.md`
