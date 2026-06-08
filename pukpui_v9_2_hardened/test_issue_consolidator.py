# -*- coding: utf-8 -*-
"""test_issue_consolidator.py — ยืนยันชั้นสรุป (Agent ยุบรหัส) ทำงานถูก

ตรึงพฤติกรรม:
  • หลายรหัส ITM บน 'รายการเดียวกัน' (เลขเดียวกัน) → ยุบเหลือ 1 ข้อสรุป + รวมรหัสครบ
  • bucket จัดถูก: master-dependent → 'ขึ้นกับ master' ; review-only → 'ข้อสังเกต' ; อื่น → 'ต้องแก้'
  • รหัสคนละหมวด/คนละรายการ → แยกข้อสรุป (ไม่ยุบมั่ว)
self-contained: สร้าง bill สังเคราะห์ ไม่พึ่ง /mnt/project.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import issue_consolidator as IC

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


def _iss(code, name, detail, sev="WARNING"):
    return {"code": code, "name": name, "detail": detail, "severity": sev,
            "category": "x"}


# บิล: รายการ #2 โดน 5 รหัส (review+fix ผสม), รายการ #5 โดน 1, + ปัญหาบริษัท (master) ระดับบิล
bill = {
    "file": "TEST.xls", "sheet": "1", "iv_number": "IV001",
    "issues": [
        _iss("ITM004", "คำสะกด pattern", "#2: อักขระแปลก", "INFO"),
        _iss("ITM005", "หน่วย keyword", "#2 \"สายไฟ\" หน่วยไม่เหมาะ", "INFO"),
        _iss("ITM010", "Thai typo", "#2: \"มั้วน\" → \"ม้วน\"", "WARNING"),
        _iss("ITM011", "Fuzzy dict", "#2: ใกล้เคียง", "WARNING"),
        _iss("ITM015", "หน่วยต่าง", "#2 ใช้หน่วยต่างชุด", "WARNING"),
        _iss("ITM018", "จำนวนผิด", "#5: qty=0 แต่ amount=100", "WARNING"),
        _iss("CMP001", "ชื่อ exact", "ในไฟล์: A | master: B", "CRITICAL"),
        _iss("TAX003", "TaxID↔Company", "เลขภาษีไม่ตรง", "CRITICAL"),
    ],
}

f = IC.consolidate_bill(bill)
by_spot = {(r["category"], r["spot"]): r for r in f}

# รายการ #2: 5 รหัส → 1 ข้อสรุป
itm2 = by_spot.get(("รายการสินค้า", "รายการ #2"))
_check("รายการ #2 ยุบเป็น 1 ข้อสรุป", itm2 is not None)
if itm2:
    codes2 = set(itm2["codes"].split(","))
    _check("รวมรหัสครบ 5 (ITM004/005/010/011/015)",
           codes2 == {"ITM004", "ITM005", "ITM010", "ITM011", "ITM015"})
    _check("severity สูงสุด = WARNING (ไม่ใช่ INFO)", itm2["max_severity"] == "WARNING")
    _check("bucket = 'ต้องแก้' (มี fix code ปนแม้มี review)", itm2["bucket"] == "ต้องแก้")
    _check("สรุปบอกด้าน 'ชื่อ/สะกด' + 'หน่วย'",
           "ชื่อ/สะกด" in itm2["summary"] and "หน่วย" in itm2["summary"])

# รายการ #5 แยกต่างหาก
itm5 = by_spot.get(("รายการสินค้า", "รายการ #5"))
_check("รายการ #5 แยกข้อสรุปของตัวเอง (ไม่ยุบรวม #2)", itm5 is not None)

# บริษัท/เลขภาษี ระดับบิล → bucket 'ขึ้นกับ master'
cmp_f = by_spot.get(("บริษัท/นิติบุคคล", "ทั้งบิล"))
tax_f = by_spot.get(("เลขผู้เสียภาษี", "ทั้งบิล"))
_check("CMP ยุบระดับบิล + bucket 'ขึ้นกับ master'",
       cmp_f is not None and cmp_f["bucket"] == "ขึ้นกับ master")
_check("TAX ยุบระดับบิล + bucket 'ขึ้นกับ master'",
       tax_f is not None and tax_f["bucket"] == "ขึ้นกับ master")

# review-only ล้วน → bucket 'ข้อสังเกต'
rbill = {"file": "R.xls", "sheet": "1", "iv_number": "IV9",
         "issues": [_iss("ITM004", "สะกด", "#1: x", "INFO"),
                    _iss("ITM005", "หน่วย", "#1 y", "INFO")]}
rf = IC.consolidate_bill(rbill)
_check("รายการ review-only ล้วน → bucket 'ข้อสังเกต (review)'",
       len(rf) == 1 and rf[0]["bucket"] == "ข้อสังเกต (review)")

print("=" * 56)
if _fail == 0:
    print("RESULT: ✅ consolidator ยุบรหัส + จัด bucket/หมวด ถูกต้อง")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน")
    sys.exit(1)
