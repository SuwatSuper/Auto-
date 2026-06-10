# HANDOFF — รายงานลูกค้า + ตรวจเลขเอกสารขยะ (กอง C golden-safe + กอง D golden-affecting)

> งานตามคำสั่งชุดที่ 2 (`PROMPT_FOR_CLAUDE_CODE_PART2_TH.md`) — คนละเรื่องกับชุดที่ 1
> (ชุด 1 = honesty/coverage/lens/TAX008/ADDR006/BR004/SYS ; ชุด 2 = ปรับรายงานโน้ตแพด + จับเลขเอกสารขยะ).

สภาพแวดล้อมพิสูจน์: **Python 3.12 + numpy 2.2.6 + pandas 2.2.2** · `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02`.
`bash run_ci.sh` = **เขียวทั้งหมด** · golden fixture `d8bcde85…` (ไม่ขยับตลอดกอง C+D) · golden corpus จริง `35b2f7c8…` (รอเจ้าของ rebaseline หลังกอง D).

---

## กอง C — GOLDEN-SAFE (composer/agent · audit golden ไม่ขยับ · report-det ไม่ขยับ)

| ข้อ | สิ่งที่แก้ | ไฟล์ | เทส |
|---|---|---|---|
| **C1** | รายงานช่อง "ที่อยู่/เลขภาษี" ต้อง **บอกไฟล์** ("ไฟล์ JRN อำเภอ ไม่ตรง (5 บิล)") ไม่ใช่ "(N บิล)" ลอย ๆ ; หลายไฟล์ → ไล่ทุกไฟล์ | `code_labels.py` (`addr_summary`/`field_summary`) | `test_report_c1_c2.py`, `test_report_summary_fixes.py` |
| **C2** | หน่วยสะกดผิด (ITM019 มี mapping ผิด→ถูกชัด) → ขึ้นช่อง "รายการสินค้า" (เหมือน typo ITM010/011) ; หน่วยขาด/ดึงไม่ได้ → คง "ตรวจตาเพิ่ม" (soft) | `report_precision.py` (a_unit_sanity), `super_ultra_viewer.py` (_pinpoint_field F_ITEM) | `test_report_c1_c2.py` |
| **C3** | **inventory** กฎที่ถูกกรอง/ซ่อน + คำแนะนำ promote (ดูตารางด้านล่าง) — ไม่เปลี่ยนการซ่อนเองโดยไม่ยืนยัน | (เอกสารนี้) | — |

### C3 — Inventory: กฎที่ถูกกรอง/ซ่อนจากรายงานลูกค้า (.txt)

**(ก) ซ่อนตรง ๆ จาก .txt** (`_HIDE_IN_SUMMARY` ใน super_ultra_viewer.py):

| รหัส | ความหมาย | สถานะ/คำแนะนำ |
|---|---|---|
| ITM016 | รายการสินค้าซ้ำในบิล | **ตั้งใจซ่อน** — ลูกค้าสั่งซ่อนเพราะ noise (ขึ้น Excel เท่านั้น). คงไว้. |
| ITM018 | จำนวน=0 แต่มียอดเงิน | **ตั้งใจซ่อน** — มักมาจากคอลัมน์ qty อ่านไม่ติด = artifact. คงไว้. |
| **ITM015** | ชื่อสินค้าเดียวกันใช้หน่วยต่างกันในชุด | ⚠️ **เสนอทบทวน** — ถ้าเป็น error จริง (เช่น หิน 3/4 ใช้ทั้ง คิว+ตัน ปนกัน) อาจควรขึ้นช่อง "รายการสินค้า/ตรวจตา". `report_precision.a_unit_sanity` CONFIRM ITM015 อยู่แล้ว แต่ `_HIDE_IN_SUMMARY` บล็อกก่อนถึง council. **ยังไม่ un-hide เอง — รอเจ้าของยืนยัน** (สอดคล้อง ADR-026 v2). |

**(ข) lane REVIEW (ไม่เข้า worklist เลย)** — `if ln not in ("fix","check"): continue` :

| รหัส | ความหมาย | คำแนะนำ |
|---|---|---|
| ITM003 / ITM004 / ITM007 | ชื่อสินค้าคลุมเครือ / อักขระล่องหน / ชื่อสั้น | คง REVIEW (advisory, soft signal — เสี่ยง noise ถ้าขึ้นรายงานลูกค้า) |
| ITM005 | หน่วยอาจไม่เหมาะกับสินค้า | คง REVIEW — C2 ยก "หน่วยสะกดผิด (ITM019)" ขึ้นแล้ว ; ITM005 = "ความเหมาะสม" ก้ำกึ่งกว่า (เก็บไว้ที่ปัจจุบัน/ตรวจตา) |
| ITM009 / ITM012 | alias สินค้า / ชื่อคล้ายคำอื่น | ITM009 = unavailable (ไม่มี `product_master.json` — ดูชุด 1 A2) ; ITM012 = suggestion. คง REVIEW |
| IV001 | prefix เลขใบกำกับไม่ตรง | คง REVIEW — convention ต่อผู้ขาย (ไม่ใช่ error สากล) |
| VAT006 / VAT008 | ราคารวม VAT แล้ว / VAT เป็นศูนย์ | คง REVIEW — ปกติในบางกรณี (VAT included / ยกเว้น-0%) |
| VAT010 | VAT ไม่ได้ตรวจจริง | **ปิดอยู่ (⛔ ห้ามแตะ)** |

> สรุป C3: รายการ "ผิดจริงที่ควรพิจารณา promote" = **ITM015 เพียงตัวเดียว** — flag ไว้ให้เจ้าของตัดสิน, ไม่เปลี่ยนเอง.
> ที่เหลือเป็น advisory/soft โดยเหมาะสม (กัน noise ในรายงานที่ส่งลูกค้า).

---

## กอง D — GOLDEN-AFFECTING (กฎใหม่ + parser guard · **รอเจ้าของ rebaseline บน corpus จริง**)

| ข้อ | งาน | severity | ผลต่อ golden fixtures | เทส | ADR | สถานะ |
|---|---|---|---|---|---|---|
| **D1** | **IV007** เลขใบกำกับ "ไม่สมเหตุสมผล" (absolute validity) | ERROR | ไม่ขยับ | `test_iv007.py` | ADR-031 | ✅ ทำแล้ว |
| **D2** | parser guard ไม่คว้าเศษ float เป็น iv (root cause) | — | ไม่ขยับ (parse canary นิ่ง) | `test_iv_parser_guard.py` | ADR-032 | ✅ ทำแล้ว |
| **D3** | sanitize เศษ float ในเซลล์ยอดเงินตอน parse | — | — | — | ADR-033 | ⏸️ **DEFERRED** |

- **D1 (IV007):** จับเลขขยะที่ IV002 (consistency-only) ปล่อยหลุด — ศูนย์ล้วน / เลขเดียวซ้ำ / placeholder
  ('0000000002') / ตรงเศษทศนิยมของยอดเงิน. ไม่พึ่ง master/บิลอื่น. conservative. = safety-net ชั้นกฎ.
- **D2-GUARD (post-extraction):** ตัดต้นตอแบบ **ไม่แก้ flow การ extract** — `core_utils.validate_iv_post(bill)`
  เรียกใน `parse_file` **หลัง parse ครบ** (มี iv + ยอด) → ถ้า iv เป็นเลขขยะ/เศษทศนิยม-ตรงยอดเงิน → ตั้ง
  `iv_number=''` ให้ IV005 (ไม่มีเลข)/IV007 จับ ("ซื่อสัตย์กว่าโชว์เลขผิด"). single-source กับ D1 ใน core_utils.
  **bounded:** เปลี่ยน iv เฉพาะบิลที่ iv เป็นเลขขยะ — ไม่ broad.
- **D2-EXTENSION (จับเลขไม่ขึ้นต้น 'IV' เช่น '01954'):** ⏸️ **เลื่อน ไม่ทำรอบนี้** — template ผู้ขายต่างกันมาก
  "เลขสั้นในหัวบิล" อาจเป็นเลขหน้า/วันที่/เบอร์ → golden shift กว้างที่ตรวจสอบไม่ได้ถ้าไม่มี corpus. D1+D2-guard
  แก้ความเจ็บปวดจริงครบแล้ว. ถ้าทำจริง → แยกรอบ + scope ตาม template + เจ้าของวัดผล.
- **D3 (sanitize เศษ float ในยอดเงิน):** ❌ **ไม่ทำ** — โซน ⛔ ห้ามแตะยอด + golden กว้างสุด + ต้นตอ (เศษ float
  รั่วเข้า iv) ถูกอุดด้วย D2-guard แล้ว. อยากให้ยอดใน Excel สวย → ตั้ง **number format** เซลล์ (`'#,##0.00'`)
  ที่ชั้นแสดงผลเท่านั้น (ไม่แตะค่า ไม่กระทบ golden) — เป็นงาน golden-safe แยกได้ถ้าต้องการ. ดู ADR-033.

---

## ✅ สิ่งที่เจ้าของระบบต้องรันเอง (บนเครื่องที่มี corpus 106 ไฟล์ / 834 บิล)

```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02

# 1) ยืนยันกอง C ไม่ขยับ audit golden (เช็คเอาท์ commit กอง C สุดท้าย ก่อนกอง D)
python3 golden_master.py . /tmp/after_C.json
#    → _sha256 ต้อง = 35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba

# 2) เปิดกอง D → ดูผลจริง + จำนวนที่ยิง/เปลี่ยนบน corpus
python3 regression_full.py
#    - D1 (IV007): บิลเลขขยะ (เช่น TNT_69_01) ขึ้นฟ้องจริงไหม ; มี false positive ไหม
#    - D2 (parser guard): **iv_number เปลี่ยนกี่บิล** (สำคัญ — วัดผลกระทบก่อน rebaseline).
#      ถ้าผลกระทบกว้างเกินคาด → พิจารณาทำเฉพาะ D1 ก่อน แล้วเลื่อน D2 (revert commit D2)

# 3) ผลถูกต้อง → rebaseline golden + อัปเดต GOLDEN.md/baseline.json + เปลี่ยน ADR-031/032 PROPOSED→ACTIVE
python3 golden_master.py . baseline.json
#    แล้ว sync hash ใหม่: GOLDEN.md, README.md, version_gate(neutral), .vscode/*, DECISIONS.md banner §1,
#    _SESSION_HANDOFF.md, QUICKSTART, constraints.txt, run_ci.sh (test_golden_single_source.py คุมให้ครบ)
```

> ⚠️ Claude Code **ไม่ได้** fabricate ค่า golden hash ใหม่ — hash ของกอง D **ต้องมาจากการรันของเจ้าของ
> บน corpus จริงเท่านั้น**. fixture golden (`d8bcde85…`) ไม่ขยับ เพราะ fixture ไม่มี pattern ที่กฎใหม่/guard จับ.

## รายการตัดสินใจที่รอเจ้าของ
1. **C3 / ITM015** — un-hide ขึ้นรายงานลูกค้าไหม (ถ้าหน่วยปนกันในชุดเป็น error จริง)?
2. **D2 ส่วนขยาย** — ให้ parser จับเลขเอกสารที่ไม่ขึ้นต้น 'IV' (เช่น '01954') ด้วยไหม (golden กว้างขึ้น)?
3. **D3** — sanitize เศษ float ในยอดเงินตอน parse ไหม (เสี่ยง golden สูง, ใกล้ ⛔)?
