# -*- coding: utf-8 -*-
"""test_iv007.py — [D1] negative fixture: IV007 เลขใบกำกับ "ไม่สมเหตุสมผล" (absolute validity)

ไม่พึ่ง corpus จริง. จับเลขขยะที่ IV002 (consistency-only) ปล่อยหลุด — โดยไม่เทียบบิลอื่น/ไม่พึ่ง master.
ตรึง:
  ยิง  — ศูนย์ล้วน ('0000000000') / เลขเดียวซ้ำ ('1111111111') / placeholder ('0000000002','00000000001')
         / ตรงเศษทศนิยมของยอดเงิน (parser คว้าเศษ float มาเป็นเลขเอกสาร)
  เงียบ — เลขจริงรูปแบบสมเหตุผล ('IV6905000279','01954','INV-2026-001','6905000279') / เลขสั้น / ว่าง

conservative: false-negative ดีกว่า false-positive. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import r_iv007

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _fires(iv, **amts):
    b = {"iv_number": iv, "items": [{"seq": 1}], "subtotal": None, "vat": None, "total": None}
    b.update(amts)
    return bool(r_iv007(b, None, {}))


# ── ยิง: เลขขยะ ────────────────────────────────────────────────────────────────
_check("ศูนย์ล้วน '0000000000' → ยิง", _fires("0000000000"))
_check("เลขเดียวซ้ำ '1111111111' → ยิง", _fires("1111111111"))
_check("placeholder '0000000002' (เคสจริง TNT) → ยิง", _fires("0000000002"))
_check("placeholder '00000000001' → ยิง", _fires("00000000001"))
_d = r_iv007({"iv_number": "0000000002", "items": [{"seq": 1}]}, None, {})[0]
_check("detail ระบุเลขที่ผิด '0000000002'", "0000000002" in _d)

# ตรงเศษทศนิยมของยอดเงิน (root cause: parser คว้าเศษ float ของ VAT)
_check("เคสจริง: iv '0000000002' + vat 1416233.0000000002 → ยิง",
       _fires("0000000002", vat=1416233.0000000002))
_check("amount-fragment เพียว: iv '3456789' = เศษของ total 12.3456789 → ยิง (ไม่ใช่ placeholder/ซ้ำ)",
       _fires("3456789", total=12.3456789))

# ── เงียบ: เลขจริงสมเหตุผล ─────────────────────────────────────────────────────
for iv in ("IV6905000279", "01954", "IV6905000850", "INV-2026-001", "6905000279", "2026/0042"):
    _check(f"เลขจริง '{iv}' → เงียบ", not _fires(iv))

# เลขสั้นปกติ (ไม่ใช่ placeholder 8+ หลัก) → เงียบ
_check("'2' (สั้น ไม่ใช่ placeholder) → เงียบ", not _fires("2"))
_check("'123' → เงียบ", not _fires("123"))
# เลขจริงที่บังเอิญมีศูนย์นำแต่เนื้อยาว → เงียบ
_check("'0105556' (ศูนย์นำ 1 ตัว เนื้อยาว) → เงียบ", not _fires("0105556"))
# ว่าง → ปล่อย IV005 ดูแล (ไม่ทับ)
_check("iv ว่าง → เงียบ (IV005 ดูแล)", not _fires(""))
# รหัสตัวอักษรล้วน (ไม่มีตัวเลข) → ไม่ตัดสินที่นี่
_check("'ABCDEF' (ไม่มีตัวเลข) → เงียบ", not _fires("ABCDEF"))

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] IV007 ยิงเลขขยะ (ศูนย์ล้วน/ซ้ำ/placeholder/เศษยอด) + เงียบเลขจริง")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
