# -*- coding: utf-8 -*-
"""test_iv_parser_guard.py — [D2-GUARD] post-extraction: ปฏิเสธ iv_number ขยะ/มาจากยอดเงิน → ว่าง

ไม่พึ่ง corpus จริง. แนวทาง (ตามคำสั่ง): **post-extraction validation** — ไม่แก้ flow การ extract
แต่ "หลังได้ iv + ยอดครบ" ค่อยตรวจ iv_number เทียบยอด ; ถ้าขยะ → ตั้ง iv_number='' ให้ IV005/IV007 จับ
("ซื่อสัตย์กว่าโชว์เลขผิด"). guard = `core_utils.validate_iv_post` เรียกใน `parse_file` (parser_p2).

ตรึง:
  • เศษ float ของยอด VAT ('1416233.0000000002' → iv '0000000002') → ปฏิเสธ (iv ว่าง)
  • all-zeros / placeholder / เลขเดียวซ้ำ → ปฏิเสธ
  • iv = เศษทศนิยมของยอด (เพียว ไม่ใช่ placeholder) → ปฏิเสธ
  • เลข iv จริง (IV6905000279, 01954) → ไม่แตะ
  • parser เรียก guard นี้จริง (parse_file มี validate_iv_post)

exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core_utils import validate_iv_post

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _iv_after(iv, **amts):
    b = {"iv_number": iv, "iv_number_raw": iv, "subtotal": None, "vat": None, "total": None}
    b.update(amts)
    rejected = validate_iv_post(b)
    return b["iv_number"], rejected


# 1) root cause: เศษ float ของยอด VAT → ปฏิเสธ (iv ว่าง + raw ว่าง)
iv, rej = _iv_after("0000000002", vat=1416233.0000000002)
_check("เศษ float (iv '0000000002' + vat 1416233.0000000002) → ปฏิเสธ → iv ว่าง", iv == "" and rej)
b = {"iv_number": "0000000002", "iv_number_raw": "0000000002", "vat": 1416233.0000000002}
validate_iv_post(b)
_check("ปฏิเสธแล้ว iv_number_raw ก็ว่างด้วย", b["iv_number_raw"] == "")

# 2) เลขขยะรูปแบบต่าง ๆ → ปฏิเสธ
_check("all-zeros '0000000000' → ปฏิเสธ", _iv_after("0000000000")[0] == "")
_check("placeholder '00000000001' → ปฏิเสธ", _iv_after("00000000001")[0] == "")
_check("เลขเดียวซ้ำ '1111111111' → ปฏิเสธ", _iv_after("1111111111")[0] == "")

# 3) iv = เศษทศนิยมของยอด (เพียว ไม่ใช่ placeholder) → ปฏิเสธ
_check("amount-fragment เพียว: iv '3456789' = เศษของ total 12.3456789 → ปฏิเสธ",
       _iv_after("3456789", total=12.3456789)[0] == "")

# 4) เลข iv จริง → ไม่แตะ
_check("IV6905000279 → ไม่แตะ", _iv_after("IV6905000279", vat=7.0, total=107.0, subtotal=100.0)[0] == "IV6905000279")
_check("01954 → ไม่แตะ", _iv_after("01954", vat=7.0)[0] == "01954")
_check("เลขจริง '6905000279' (ไม่ตรงยอด) → ไม่แตะ", _iv_after("6905000279", total=500.0)[0] == "6905000279")
_check("iv ว่างอยู่แล้ว → no-op (ไม่ครัช)", _iv_after("")[0] == "")

# 5) parser เรียก guard นี้จริง (post-extraction hook ใน parse_file)
import parser_p2
_check("parser_p2 เข้าถึง validate_iv_post (re-export chain) ได้", hasattr(parser_p2, "validate_iv_post"))
import inspect
_src = inspect.getsource(parser_p2.parse_file)
_check("parse_file เรียก validate_iv_post (post-extraction hook)", "validate_iv_post" in _src)

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] post-extraction guard ปฏิเสธ iv ขยะ/เศษยอด → ว่าง (iv จริงไม่แตะ)")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
