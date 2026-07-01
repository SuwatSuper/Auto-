# -*- coding: utf-8 -*-
"""test_report_lane_aspect.py — ตรึง ADR-111 (report/diagnostics layer · golden-neutral):
  A) CMP005 (ตรวจโครงสร้างชื่อ ไม่พึ่ง master) ต้อง "ไม่อยู่" ใน MASTER_DEPENDENT
     → ต้องลงเลน must-fix ไม่ใช่ "ขึ้นกับ master".
  B) ITM019/ITM020 (เรื่องหน่วย) ต้องอยู่ในกลุ่ม _ITM_ASPECT['หน่วย']
     → สรุปปัญหาบอกด้าน "หน่วย" ไม่ใช่ "รายการ" ทั่วไป.
ไม่ใช้ข้อมูลจริง รันได้ทุกที่. exit 0 = ผ่าน, 1 = ล้มเหลว.
"""
import sys

from issue_consolidator import MASTER_DEPENDENT, _ITM_ASPECT, consolidate_bill

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("REPORT LANE/ASPECT — ADR-111")

# A) CMP005 ไม่ใช่ master-dependent
_check("CMP005 ไม่อยู่ใน MASTER_DEPENDENT", "CMP005" not in MASTER_DEPENDENT)
# กันถอยหลัง: CMP001/003/004 (master จริง) ยังอยู่
_check("CMP001/003/004 ยังเป็น master-dependent",
       {"CMP001", "CMP003", "CMP004"} <= MASTER_DEPENDENT)

# A2) บิลที่มี CMP005 อย่างเดียว → consolidate ไม่จัดลง 'ขึ้นกับ master'
bill_cmp = {"issues": [{"code": "CMP005", "name": "ขาดจำกัด",
                        "detail": "ชื่อมี 'บริษัท' แต่ไม่มี 'จำกัด'", "severity": "WARNING"}]}
rows = consolidate_bill(bill_cmp)
buckets = {r.get("bucket") for r in rows}
_check(f"CMP005 ไม่ลงเลน 'ขึ้นกับ master' (buckets={buckets})", "ขึ้นกับ master" not in buckets)

# B) ITM019/ITM020 อยู่กลุ่ม 'หน่วย'
unit_group = _ITM_ASPECT.get("หน่วย", set())
_check("ITM019 อยู่กลุ่ม 'หน่วย'", "ITM019" in unit_group)
_check("ITM020 อยู่กลุ่ม 'หน่วย'", "ITM020" in unit_group)

# B2) บิลที่มี ITM019 บนรายการ → summary บอกด้าน 'หน่วย'
bill_itm = {"issues": [{"code": "ITM019", "name": "หน่วยสะกดผิด",
                        "detail": '#2: "ทินเนอร์" หน่วย "แกลอน" ควรเป็น "แกลลอน"', "severity": "WARNING"}]}
rows = consolidate_bill(bill_itm)
itm_row = next((r for r in rows if r.get("summary", "").startswith("รายการสินค้า")), None)
_check("ITM019 summary บอกด้าน 'หน่วย'",
       itm_row is not None and "หน่วย" in itm_row.get("summary", ""))

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ PASS — ADR-111 (CMP005 lane + ITM019/020 aspect) ครบ")
    sys.exit(0)
print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน")
sys.exit(1)
