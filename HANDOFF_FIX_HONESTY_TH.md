# HANDOFF — แก้คุณภาพ/ความซื่อสัตย์ของการตรวจ (กอง A golden-safe + กอง B golden-affecting)

> งานตามคำสั่ง `PROMPT_FOR_CLAUDE_CODE_TH.md` — เลิก "ตรวจหลอก", เพิ่มการตรวจที่ทำได้แม้ไม่มี master,
> และรองรับการเพิ่ม master/ผู้ขายใหม่ในอนาคตโดยไม่ต้องแก้โค้ด.

สภาพแวดล้อมที่ใช้พิสูจน์: **Python 3.12 + numpy 2.2.6 + pandas 2.2.2** (ตรง constraints.txt),
`PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02`. `bash run_ci.sh` = **เขียวทั้งหมด**.
golden fixture = `d8bcde85…` (ไม่ขยับตลอดงาน) · golden corpus จริง = `35b2f7c8…` (ยังไม่ rebaseline — เป็นงานเจ้าของ).

---

## กอง A — GOLDEN-SAFE (เสร็จสมบูรณ์ · audit golden ไม่ขยับ · commit แยกราย A)

| ข้อ | สิ่งที่แก้ | ไฟล์หลัก | เทส |
|---|---|---|---|
| **A1** | honesty รายผู้ขาย: ช่องตัวตน (ชื่อ/เลขภาษี/**ที่อยู่**/**สาขา**) พูด "ตรง" ได้เฉพาะเมื่อเทียบ master จริง — แยกสถานะที่ 3 "ตรวจไม่ได้" (3 เหตุผล: ไม่มีใน master / ทะเบียนไม่มีข้อมูลช่องนี้ / อ่านจากบิลไม่ได้). ตัดสินทีละบิลจาก `master_key` (ไม่ใช่ flag global). ครอบทั้ง `super_ultra_viewer` + `vendor_report`. footer/legend อัปเดต. | `code_labels.py`, `super_ultra_viewer.py`, `agents/vendor_report*.py`, `ultra_agent.py`, `pukpui_modular_funcs.py`, entry | `test_honesty_per_bill.py` (ใหม่), `test_super_ultra_viewer.py`, `test_vendor_report.py` |
| **A2** | coverage สถานะกฎ 3 กลุ่ม + เหตุผล: **active / disabled-by-design / unavailable-resource** — ไม่นับ disabled/unavailable เป็น active. โชว์ในชีต Rules. | `code_registry.py`, `reporting_p1.py` | `test_rule_status.py` (ใหม่) |
| **A3** | `lens_provenance` แก้ vocabulary `'parsed'`→`'ocr'` (dead branch → ทำงานจริง ตรง parser) | `agents/verification_lenses.py` | `test_verification_lens_pin.py` |
| **A4** | label TAX002 → "ไม่พบเลขภาษี 13 หลักที่ถูกต้อง" (ตรง r_tax002 จริง) + แก้หลักฐาน ultra_agent | `code_labels.py`, `ultra_agent.py` | (consistency tests) |
| **A5** | สรุป SYS-* ท้ายการรัน — silent skip (กฎ crash ใน run_rules) มองเห็นได้เสมอ | `diagnostics.py`, `pukpui_modular_base.py`, entry | `test_sys_summary.py` (ใหม่) |

**A1 รองรับบริษัทใหม่ (พิสูจน์โดยเทส):** master ว่าง → ทุกช่องตัวตน "ตรวจไม่ได้" ; ใส่ผู้ขาย X เข้า master →
**เฉพาะ X** verified ("ตรง") โดยอัตโนมัติ ผู้ขายอื่นยัง "ตรวจไม่ได้" — **ไม่ต้องแก้โค้ด**.

---

## กอง B — GOLDEN-AFFECTING (โค้ด+เทส+ADR พร้อม · **รอเจ้าของ rebaseline บน corpus จริง**)

| ข้อ | กฎใหม่ | severity | พึ่ง master? | ผลต่อ golden fixtures | เทส | ADR |
|---|---|---|---|---|---|---|
| **B1** | **TAX008** เลขภาษีเดียวกันแต่ชื่อบริษัทต่างกัน (cross-bill) | CRITICAL | ไม่ | ไม่ขยับ (ไม่มี FP บน fixture) | `test_tax008.py` | ADR-027 |
| **B2** | **ADDR006** รหัสไปรษณีย์ ↔ จังหวัด ไม่สอดคล้อง | WARNING | ไม่ | ไม่ขยับ | `test_addr006.py` | ADR-028 |
| **B3** | **BR004** เทียบสาขากับ master (เมื่อมี master+branch) | ERROR | ใช่ (เฉพาะมี master) | ไม่ขยับ | `test_br004.py` | ADR-029 |
| **B4** | DT001 filename-period | — | — | **ไม่แก้** (สอบแล้วไม่มีบั๊ก) | — | ADR-030 |

- ทุกกฎ register ครบ 3 ตารางนำเสนอ (`code_labels.MAP` + `config.FIELD_CODES` + `vendor_report_base.FIELD_LAYOUT`
  ผ่าน prefix) + `RULES` + `ultra_agent` classification → consistency tests เขียว.
- ปรัชญา conservative (false-negative ดีกว่า false-positive): ทุกกฎ "เงียบ" เมื่อข้อมูลไม่พอ/กำกวม.
- **ข้อมูล ADDR006** (`thai_postal.py`): derive จากชุดข้อมูลจริง 7,436 ตำบล (thailand-geography-json) ครบ 77 จังหวัด —
  ไม่ได้เดาจากความจำ. เป็น dict แก้ไข/เพิ่มได้ — เจ้าของควร review.
- **B4 ผลสอบสวน:** `_filename_period_ce('XXX_69_012.xls')` → **(2026, 1) = มกราคม ถูกต้องอยู่แล้ว**
  (ไม่ใช่ "เดือน 12" ตามที่สงสัย). บั๊ก `0NN→NN` ไม่มีจริง → DT001 over-fire = บิลคร่อมเดือนจริง → ไม่แก้ parser.

---

## ✅ สิ่งที่เจ้าของระบบต้องรันเอง (บนเครื่องที่มี corpus 106 ไฟล์ / 834 บิล)

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02

# 1) ยืนยันกอง A ไม่ขยับ audit golden (ต้องได้ 35b2f7c8… เท่าเดิม)
#    เช็คเอาท์ commit กอง A สุดท้าย (ก่อนกอง B) แล้วรัน:
python3 golden_master.py . /tmp/after_A.json
#    → _sha256 ต้อง = 35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba

# 2) เปิดกอง B → ดูจำนวน/ความถูกต้องที่ TAX008/ADDR006/BR004 ยิงบน corpus จริง (ตรวจ false positive)
python3 regression_full.py            # หรือดูผลตรวจ Excel/รายงานต่อบริษัท
#    - ตรวจ TAX008: เคส เจ.อาร์./ฉีหยวน ขึ้นจริงไหม ; มี FP ชื่อย่อ/รูปต่างเล็กน้อยไหม
#    - ตรวจ ADDR006: ไปรษณีย์↔จังหวัดที่ขัด ขึ้นถูกไหม ; review thai_postal.PROVINCE_POSTAL_PREFIXES
#    - ตรวจ BR004: เฉพาะผู้ขายที่ master มี branch

# 3) ถ้าผลกอง B ถูกต้อง → rebaseline golden อย่างเป็นทางการ
python3 golden_master.py . baseline.json
#    แล้วอัปเดต hash ใหม่ใน: GOLDEN.md, README.md, version_gate (neutral), .vscode/*, DECISIONS.md banner §1,
#    _SESSION_HANDOFF.md, QUICKSTART, constraints.txt, run_ci.sh — และเปลี่ยน ADR-027/028/029 จาก
#    PROPOSED → ACTIVE (ใส่ค่า hash ใหม่ + retire 35b2f7c8). test_golden_single_source.py จะคุมให้ครบ.
```

> ⚠️ Claude Code **ไม่ได้** fabricate ค่า golden hash ใหม่ — ค่า hash ของกอง B **ต้องมาจากการรันของเจ้าของ
> บน corpus จริงเท่านั้น**. fixture golden (`d8bcde85…`) ไม่ขยับ เพราะ fixture ไม่มี pattern ที่กฎใหม่จับ
> (ยืนยันว่าไม่มี false positive บนชุดทดสอบ).

## หมายเหตุ follow-up (ไม่บังคับ)
- `vendor_report` ได้ honesty A1 แล้วเช่นกัน (ไม่ใช่แค่ super_ultra_viewer).
- ITM009 ยัง unavailable-resource จนกว่าจะมี `product_master.json` (A2 แสดงสถานะนี้ชัดแล้ว).
