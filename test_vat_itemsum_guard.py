# -*- coding: utf-8 -*-
"""test_vat_itemsum_guard.py — ตรึง ADR-109: r_vat006/r_vat007 ต้องไม่ครัชเงียบเมื่อ item amount
เป็น bool / non-finite (inf/NaN) — ซึ่งเดิมทำให้กฎ CRITICAL VAT007 ถูกข้าม (false-negative).

หลักการ (regression guard):
  • bool ⊂ int → ลอด isinstance((int,float)) → _D(bool)=None → Decimal+None = TypeError (ไม่ใช่
    ArithmeticError) → หลุด except → run_rules กลืนเป็น SYS-VAT00x → กฎถูกข้ามเงียบ.
  • inf/NaN ก็ให้ _D()=None เช่นกัน.
ADR-109 แก้ด้วย _safe_items_sum (กัน bool+None ก่อนบวก). เทสนี้พิสูจน์:
  A) bill ที่ item amount เป็น bool/inf/nan → กฎคืน list (ไม่ throw).
  B) VAT007 true-positive จริง (VAT คำนวณก่อนหักส่วนลด) ยังฟ้องเหมือนเดิม (ไม่กลบ true-positive).
  C) _safe_items_sum ข้าม bool/None แต่บวก number finite ปกติครบ.
ไม่ใช้ข้อมูลจริง รันได้ทุกที่. exit 0 = ผ่าน, 1 = ล้มเหลว.
"""
import sys
from decimal import Decimal

from rules_engine_rules_c import r_vat006, r_vat007, _safe_items_sum

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("VAT ITEMSUM GUARD — ADR-109 (กัน bool/non-finite item amount → ครัช → กฎข้ามเงียบ)")

# A) ต้องไม่ throw เมื่อมี item amount เป็น bool / inf / nan
bad_bills = {
    "bool-item": {'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
                  'items': [{'amount': 900.0}, {'amount': True}, {'amount': 100.0}]},
    "inf-item":  {'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
                  'items': [{'amount': 900.0}, {'amount': float('inf')}]},
    "nan-item":  {'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
                  'items': [{'amount': float('nan')}, {'amount': 100.0}]},
}
for name, bill in bad_bills.items():
    for rname, fn in [("r_vat006", r_vat006), ("r_vat007", r_vat007)]:
        try:
            out = fn(bill, None, {})
            _check(f"{name} / {rname} ไม่ครัช (คืน list)", isinstance(out, list))
        except Exception as e:
            _check(f"{name} / {rname} ไม่ครัช (เจอ {type(e).__name__})", False)

# B) true-positive จริงต้องยังฟ้อง — VAT คิดจาก items_sum (ก่อนหักส่วนลด) ไม่ใช่ subtotal
#    items_sum=1150, subtotal=1000, vat=80.5 (=1150*0.07 ปัด) → ควรเป็น 70 (=1000*0.07) → ฟ้อง
vat007_hit = {'subtotal': 1000.0, 'vat': 80.5, 'total': 1070.0,
              'items': [{'amount': 800.0}, {'amount': 350.0}]}
res = r_vat007(vat007_hit, None, {})
_check("VAT007 true-positive (VAT ก่อนหักส่วนลด) ยังฟ้อง", bool(res))

# C) _safe_items_sum: ข้าม bool/None แต่บวก finite ครบ
s = _safe_items_sum({'items': [{'amount': 100.0}, {'amount': True}, {'amount': 50},
                               {'amount': float('inf')}, {'amount': None}, {'amount': 'x'}]})
_check(f"_safe_items_sum ข้าม bool/inf/None/str บวกแต่ finite (ได้ {s})", s == Decimal('150'))

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ PASS — ADR-109 guard ครบ (ไม่ครัช + ไม่กลบ true-positive)")
    sys.exit(0)
print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน")
sys.exit(1)
