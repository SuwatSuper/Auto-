# -*- coding: utf-8 -*-
"""test_rules_c_decimal_gates.py — ปักหมุดเส้นตัดสินเงินใน rules_engine_rules_c หลังย้ายเป็น Decimal
(v9.3 STEP 3 / ADR-020-F2). standalone: python3 test_rules_c_decimal_gates.py

ครอบค่าขอบสองฝั่งของ tolerance + input แปลก — พฤติกรรมต้องตรงตามที่ตรึงไว้ ห้าม flip.
"""
import sys

PASS = True


def _check(label, cond):
    global PASS
    print(f"  {'✅' if cond else '❌'} {label}")
    if not cond:
        PASS = False


def main():
    import rules_engine as RE

    def vat008(vat, total, subtotal, items=({'seq': 1},)):
        b = {'vat': vat, 'total': total, 'subtotal': subtotal, 'items': list(items)}
        return RE.r_vat008(b, None, {})

    def vat009(subtotal, total=None, items=({'seq': 1},)):
        b = {'subtotal': subtotal, 'total': total, 'items': list(items)}
        return RE.r_vat009(b, None, {})

    print("— r_vat008: sub≈total exemption boundary (tolerance 1) —")
    # vat=0, total>10000 ; |sub-total| สองฝั่งของ 1
    _check("diff=0.999 → ยกเว้น (เงียบ)", vat008(0, 20000, 19999.001) == [])
    _check("diff=1.000 → ฟ้อง (ขอบไม่รวม)", vat008(0, 20000, 19999.0) != [])
    _check("diff=1.001 → ฟ้อง", vat008(0, 20000, 19998.999) != [])

    print("— r_vat008: เพดาน total 10000 —")
    _check("total=10000.00 → เงียบ (<=)", vat008(0, 10000, 5000) == [])
    _check("total=10000.01 → ฟ้อง", vat008(0, 10000.01, 5000) != [])
    _check("vat≠0 → เงียบเสมอ", vat008(7.0, 99999, 5000) == [])

    print("— r_vat009: subtotal zero —")
    _check("subtotal=0 → ฟ้อง", vat009(0) != [])
    _check("subtotal=0.0 → ฟ้อง", vat009(0.0) != [])
    _check("subtotal=0.01 → เงียบ", vat009(0.01) == [])
    _check("subtotal=None + มี total → ฟ้องแบบข้อความเฉพาะ", vat009(None, total=100) != [])

    print("— input แปลก (พฤติกรรมต้องเหมือนก่อนแก้: เงียบ ไม่มี exception หลุด) —")
    for bad in ('', 'abc', None):
        _check(f"vat008 vat={bad!r} → เงียบ", vat008(bad, 20000, 100) == [])
    _check("vat008 total='abc' → เงียบ", vat008(0, 'abc', 100) == [])
    _check("vat009 subtotal='abc' → เงียบ", vat009('abc') == [])
    _check("vat008 รับ '1e3' (float-style) ไม่ระเบิด", isinstance(vat008(0, '1e3', '1e3'), list))

    print()
    if PASS:
        print("RESULT: ✅ Decimal gates — ค่าขอบทุกฝั่งตรงหมุด, input แปลกไม่ระเบิด")
        return 0
    print("RESULT: ❌ มีค่าขอบ flip — ห้าม merge")
    return 1


if __name__ == "__main__":
    sys.exit(main())
