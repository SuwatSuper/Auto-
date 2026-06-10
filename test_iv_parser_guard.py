# -*- coding: utf-8 -*-
"""test_iv_parser_guard.py — [D2] parser ไม่คว้าเลขเอกสารจากเศษ float ของยอดเงิน (root cause)

ไม่พึ่ง corpus จริง — เทส _pb_try_iv (จุดเลือก iv_number ใน non-TOR block parser) โดยตรง.
forensic (TNT_69_01.xls): เซลล์ VAT '1416233.0000000002' → parser คว้า '0000000002' เป็น iv_number.
guard ใหม่: ปฏิเสธ candidate ที่ iv_digits_garbage (เศษ float/ศูนย์ล้วน/placeholder) — single-source กับ IV007.

ตรึง:
  • เซลล์ค่าเงินที่มีเศษ float ('1416233.0000000002') → ไม่ถูกคว้าเป็น iv (iv ว่าง)
  • เลข iv จริง (IV6905000279, AB1234567) → ยังถูกเลือกตามเดิม
  • เลขขยะ (ศูนย์ล้วน) → ไม่ถูกเลือก
  • เลขขยะ "ไม่ทับ" iv ที่ valid อยู่แล้ว (ไม่ลด _iv_score)

advisory ของ parser (guard เฉพาะ candidate ขยะ) — golden ของ fixtures ไม่ขยับ (fixture ไม่มี iv ขยะ).
exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser_p1 import _pb_try_iv

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _iv_after(v, s, pre=None):
    r = dict(pre or {})
    _pb_try_iv(r, v, s)
    return r.get("iv_number", "")


# 1) root cause: เศษ float ของยอด VAT → ไม่ถูกคว้าเป็น iv
_check("เศษ float '1416233.0000000002' → ไม่คว้าเป็น iv (ว่าง)",
       _iv_after(1416233.0000000002, "1416233.0000000002") == "")
_check("เศษ float (string เดียวกัน) → ไม่คว้าเป็น iv",
       _iv_after("1416233.0000000002", "1416233.0000000002") == "")

# 2) เลข iv จริง → ยังถูกเลือก (ไม่ regress)
_check("IV6905000279 → ยังเลือกได้", _iv_after("IV6905000279", "IV6905000279") == "IV6905000279")
_check("fallback 'AB1234567' (อักษรนำ+เลข) → ยังเลือกได้",
       _iv_after("AB1234567", "AB1234567") == "AB1234567")

# 3) เลขขยะอื่น → ไม่ถูกเลือก
_check("'0000000000' (ศูนย์ล้วน) → ไม่เลือก", _iv_after("0000000000", "0000000000") == "")

# 4) เลขขยะ "ไม่ทับ" iv ที่ valid อยู่แล้ว
_check("เศษ float ไม่ override iv ที่ valid อยู่แล้ว",
       _iv_after("1416233.0000000002", "1416233.0000000002",
                 {"iv_number": "IV6905000279", "_iv_score": 80}) == "IV6905000279")

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] parser guard กันคว้าเลขขยะ/เศษ float เป็น iv (iv จริงยังเลือกได้)")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
