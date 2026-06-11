# -*- coding: utf-8 -*-
"""test_vat002_tolerance.py — pin ขอบเขต tolerance ของ r_vat002 (OBJ-0 / ADR-005)

ล็อกกฎโดเมน VAT 7% เป๊ะ: ยอมต่างเฉพาะเศษปัด < 0.50 บาทเท่านั้น.
ป้องกัน regression เงียบ ๆ (เช่นใครเผลอเปลี่ยน 0.50 กลับเป็น 1.00).
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules_engine as R  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


def fires(sub, vat):
    return bool(R.r_vat002({"subtotal": sub, "vat": vat, "total": sub + vat}, {}, {}))


print("=" * 64)
print("TEST r_vat002 tolerance = 0.50 (ADR-005)")
print("=" * 64)

# subtotal=100 → expected vat=7.00
check("diff 0.40 (<0.50, เศษปัด) → เงียบ", not fires(100.00, 7.40))
check("diff 0.49 (<0.50) → เงียบ", not fires(100.00, 7.49))
check("diff 0.50 (=0.50, ไม่ <0.50) → ฟ้อง", fires(100.00, 7.50))
check("diff 0.70 (>0.50) → ฟ้อง", fires(100.00, 7.70))
check("diff 1.00 (เคยเป็นขอบเดิม) → ฟ้อง", fires(100.00, 8.00))
# discriminator: vat ≤ 1.00 = rate ไม่ใช่ amount → ข้ามเสมอ (line 1003 ต้องไม่ถูกแตะ)
check("vat=0.07 (rate ≤1.00) → ข้าม", not fires(100.00, 0.07))
check("vat=1.00 (=ขอบ rate) → ข้าม", not fires(100.00, 1.00))
# exact 7% → ไม่ฟ้อง
check("vat=7.00 (7% เป๊ะ) → เงียบ", not fires(100.00, 7.00))

print("=" * 64)
print(f"RESULT: {'✅' if FAIL == 0 else '❌'}  ผ่าน {PASS} / ล้มเหลว {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
