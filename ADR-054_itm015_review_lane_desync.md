# ADR-054 — แก้ desync ITM015 ใน lane "ข้อสังเกต" (consolidated report จัด 34 ใบผิดเป็น "ต้องแก้")

สถานะ : ACCEPTED — 20.06.2026 · **golden ไม่เปลี่ยน (`ba9deda0`)** · advisory layer · สั่งโดย : ผู้ใช้ ("ตรวจรีพอร์ตทั้งสอง + เช็คว่าตรงมั้ย + error ผิดจริงมั้ย")

> ระดับ: 🟢 report-consistency fix (advisory · ไม่แตะ engine/golden). พบระหว่าง forensic audit รีพอร์ตตามคำสั่งผู้ใช้.

## บริบท
ผู้ใช้สั่งประกบรีพอร์ตสองตัว (Error Report Excel จาก `build_consolidated_report` + company_summary จาก `super_ultra_viewer`) ว่า "ตรงมั้ย" และ error "ผิดจริงมั้ย". ตรวจพบ:

**desync ที่ memory เตือนไว้:** `ITM015` อยู่ใน `config.REVIEW_CODES` (ADR-051 ใส่) แต่ **ตกหล่นจาก `issue_consolidator.REVIEW_ONLY`**. `build_consolidated_report` จัดเลนด้วย `REVIEW_ONLY` (บรรทัด 114 `elif codes <= REVIEW_ONLY`) → finding ที่มี ITM015 อย่างเดียว **ไม่เข้าเงื่อนไข subset → ตกเลน "ต้องแก้"** ทั้งที่ ADR-051 ตั้งใจให้เป็น advisory.

## หลักฐาน forensic (ITM015 ผิดจริงมั้ย → ไม่ผิด)
ตรวจ ITM015-only ทั้ง 34 ใบ — รูปแบบเดียวกันหมด:
- `"ทรายละเอียด"` ใช้หน่วย `['คิว','ตัน']` ในชุดเดียวกัน
- `"ปูนซีเมนต์ไฮดรอลิก ปูนถุง บรรจุ 50"` ใช้หน่วย `['ถุง','ลบ.ม.']`
→ วัสดุก่อสร้างขายได้ทั้งปริมาตร(คิว/ลบ.ม.)และน้ำหนัก/จำนวน(ตัน/ถุง) = **ปกติของผู้ขาย ไม่ใช่ error คำนวณ** → ยืนยัน ADR-051 ถูก, ITM015 ควรเป็น "ข้อสังเกต".

## การตัดสินใจ
เพิ่ม `"ITM015"` ใน `issue_consolidator.REVIEW_ONLY` ให้ sync กับ `config.REVIEW_CODES` (ตาม invariant ที่ documented: "ITM007 + ITM015 ต้องอยู่ทั้งสองชุด"). **advisory เท่านั้น — ไม่แตะ engine/ผลตรวจ/golden hash** (พิสูจน์: hash = `ba9deda0` หลังแก้).

## ผล
- ITM015 อยู่ครบทั้ง `config.REVIEW_CODES` + `REVIEW_ONLY` ✅
- consolidated report: **ต้องแก้ 204 → 161** (ย้าย 43 ใบ = 34 ITM015-only + 9 ITM015+review-tier-อื่น → "ข้อสังเกต") · review 628 → 671
- golden `ba9deda0` ไม่ขยับ · report tests (issue_consolidator/super_ultra_viewer/vendor_report/report_precision) ผ่านครบ

## หมายเหตุ (ค้าง — ไม่แก้รอบนี้)
1. **code_labels.MAP ยังบอก ITM015 action='fix'** (ขณะ lane=review). ใช้คนละ path (action=ป้ายรหัส, REVIEW_ONLY=เลน) → ไม่ขัดผลเลน แต่เป็น 3-way inconsistency เชิงป้าย. ปรับให้ตรงต้องเลือกว่า ITM015 ควร 'review'/'check' — design call ของผู้ใช้.
2. **reverse desync:** `REVIEW_ONLY` มี ITM003/VAT006/VAT010 ที่ `config.REVIEW_CODES` ไม่มี (code_labels=review ทั้งคู่). ไม่ปรากฏใน corpus → ไม่กระทบ output. ปล่อยไว้กัน regression รหัสอื่น.
3. **lane logic ใช้ REVIEW_ONLY hardcoded แทน code_labels.MAP action tier (source of truth):** ทำให้รหัส tier อ่อน (DT001='note', CMP006/IV004/ITM019='check') ตกเลน "ต้องแก้". เป็น report-design judgment (จะเปลี่ยน output มาก) — เสนอผู้ใช้ตัดสิน ไม่ refactor เอง.
