# HANDOFF — งานต่อรอบหน้า (อัปเดต 11.06.69 หลังปิด F1/F2/F3)

## สถานะปัจจุบัน
- **Golden:** `d6b23d12 7999e62c a898554c 012e60c1 d8731dff ec212770 569fa6ec 8818173` (ไม่ขยับ — fix ทั้งหมด dormant บน corpus)
- ปิดแล้ว: F1 (input ซ้ำเงียบ → การ์ด SYS004), F2 (เลขเอกสารโดด 4-5 หลัก → _pb_iv_lastresort),
  F3 (คอลัมน์หน่วยชนะคอลัมน์ชื่อ → กติกา distinct ใน _dic_find_name)
- เทสใหม่เข้า CI แล้ว: [3b1] test_input_dedupe / [3b2] test_dic_find_name_unitlike / [3b3] test_pb_iv_lastresort
- รายละเอียดเต็ม: `FIX_11_06_69_TH.md`

## งานรอบหน้า (เรียงตามที่ตกลง)

### Slice 4 — กติการีพอร์ต (advisory ล้วน — golden ไม่เกี่ยว แต่เทสล็อกฟอร์แมตต้องอัปเดต)
1. **ยุบช่อง "เลขที่" รวมเข้า "เลขที่ iv"** — `agents/vendor_report_base.py:23`
   FIELDS: ย้าย ("DOC002","DOC003") เข้า tuple ของ "เลขที่ iv" แล้วลบแถว "เลขที่" + อัปเดต FIELD_DESC
   เหตุผล (เจ้าของระบบ): เลขที่เอกสาร = เลขที่ IV ตัวเดียวกัน ช่องซ้ำทำให้สับสน
2. **หมายเหตุหน่วยว่างแบบ pinpoint** — `unit_detection_ext.company_unit_notes`
   เดิม: "หน่วยสินค้าบางรายการไม่มีหน่วย/ดึงมาไม่ครบ (N รายการ)"
   ใหม่: pinpoint {รหัสไฟล์} วันที่ dd.mm.yyyy ลำดับที่ n (group + cap เช่น 3 กลุ่มแรก "และอีก N จุด")
   ⚠️ corpus มี TOR_67_08 หน่วยว่างจริง 107 รายการ (layout ไม่มีคอลัมน์หน่วย) → ต้อง cap
3. dup ข้ามไฟล์ไม่ขึ้น .txt — DOC003 same-file-only อยู่แล้ว ✓ แค่ document/ตรึงเทส
4. เทสที่ต้องอัปเดต: test_super_ultra_viewer.py / test_vendor_report.py / test_report_c1_c2.py / test_unit_detection_ext.py

### Slice 5 — กันถอยหลังบริษัทใหม่
- เพิ่มชุดเทส 4 ไฟล์ (KRR/SHS/SSN/TNT 11.06.69) เป็น tests/fixtures/new_company_2026/
- test_new_company_layouts.py: SSN ชื่อ/หน่วยครบ · TNT iv=01954/01955 · ธ.การช่าง 12 บิล/100,010 · ปี๊ป 1 ครั้ง/ชีต

### ค้างเดิม (ไม่เร่ง)
- Bisectable per-commit checkout (local git) ปิด certification
- Profiling / calamine swap (decision gate แยก) · context-object state.py (เสี่ยง ต้อง session เฉพาะ)
- ยืนยัน ec61907f บน HEAD สำหรับ 81-file corpus (pre-Decimal)

## คำสั่ง verify มาตรฐาน
```
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . /mnt/project
bash run_ci.sh /mnt/project
```
