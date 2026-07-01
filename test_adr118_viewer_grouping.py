# -*- coding: utf-8 -*-
"""test_adr118_viewer_grouping.py — [ADR-118] super_ultra_viewer จัดกลุ่มด้วย clean_tax_id (canonical)

บริบท (re-bughunt BS-1): parser บางเส้นเก็บ tax_id เป็น full-width/เลขไทย "ดิบ" (engine re-clean
อยู่แล้ว แต่ viewer เดิมใช้ดิบเป็น identity จัดกลุ่ม) → ผู้ขายเดียวกัน เดือนเดียวกัน ที่ tax_id
ต่างฟอร์แมต (อารบิก vs full-width) ถูกแยกเป็นคนละบล็อก + โชว์เลขเพี้ยน. แก้: clean ก่อนใช้เป็น identity.

ตรึง: ผู้ขายเดียวกัน tax_id อารบิก vs full-width (ค่าเดียวกันเชิงเลข) → ยุบเป็น 1 บล็อก ;
      ผู้ขายคนละเลขจริง → ยังแยกบล็อก. golden-neutral (viewer = advisory layer).
self-contained: ไม่พึ่ง corpus. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import super_ultra_viewer as suv

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _b(comp, tax):
    return {"company": comp, "company_raw": comp, "tax_id": tax, "tax_id_raw": tax,
            "iv_date": datetime.date(2026, 5, 15), "iv_number": "IV1",
            "subtotal": 100, "vat": 7, "total": 107, "items": [], "issues": [],
            "address": "", "branch": "", "branch_no": "", "sheet": "s", "file": "f.xls"}


AR = "0105540001234"                                  # อารบิก
FW = "".join(chr(ord("０") + int(d)) for d in AR)      # full-width (ค่าเดียวกันเชิงเลข)

# 1) ผู้ขายเดียวกัน เดือนเดียวกัน tax_id อารบิก vs full-width → 1 บล็อก (เดิมแยก 2)
rows = suv.build([_b("บริษัท เอ จำกัด", AR), _b("บริษัท เอ จำกัด", FW)], master_present=False)
_check("ผู้ขายเดียว tax_id อารบิก vs full-width → ยุบ 1 บล็อก", len(rows) == 1)

# 2) ผู้ขายคนละเลขจริง → ยังแยก 2 บล็อก (ไม่ over-merge)
rows2 = suv.build([_b("บริษัท เอ จำกัด", "0105540001234"),
                   _b("บริษัท บี จำกัด", "0105540009999")], master_present=False)
_check("คนละเลขภาษีจริง → แยก 2 บล็อก (ไม่ over-merge)", len(rows2) == 2)

# 3) เลขไทย vs อารบิก (ค่าเดียวกัน) → 1 บล็อก
TH = "".join(chr(ord("๐") + int(d)) for d in AR)
rows3 = suv.build([_b("บริษัท ซี จำกัด", AR), _b("บริษัท ซี จำกัด", TH)], master_present=False)
_check("ผู้ขายเดียว tax_id อารบิก vs เลขไทย → ยุบ 1 บล็อก", len(rows3) == 1)

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] viewer จัดกลุ่มด้วย clean_tax_id — ผู้ขายเดียวไม่แตกบล็อกจากฟอร์แมตเลข")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
