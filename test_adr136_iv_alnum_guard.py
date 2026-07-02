# -*- coding: utf-8 -*-
"""test_adr136_iv_alnum_guard.py — [ADR-136] reject_iv_equal_amount ล้างเฉพาะ iv ตัวเลขล้วน.

บั๊ก (false-positive): `reject_iv_equal_amount` ทำ `re.sub(r'\\D','',iv)` ก่อนเทียบยอด → iv ที่มี
ตัวอักษร เช่น 'IV-1250' (เลขเอกสารจริง) เหลือ digits '1250' → ถ้ายอดบิล=1250 จะถูก "ล้างทิ้ง"
(เข้าใจผิดว่าเป็นยอดเงินที่อ่านเป็นเลขเอกสาร) = ลบเลขเอกสารจริง. money-misread จริง (subtotal
อ่านเป็น iv) เป็นตัวเลขล้วนอยู่แล้ว → ยังจับได้.

แก้: gate `raw_iv.isdigit()` ก่อนล้าง. ตรึง: (A) iv alphanumeric digit-collide → คงเดิม ;
(B) iv ตัวเลขล้วน==ยอด → ยังถูกล้าง (money-misread guard เดิม). golden-neutral (golden=23b315e8).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from parser_guards import reject_iv_equal_amount

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    df = pd.DataFrame([['x'] * 4 for _ in range(6)])   # df ขั้นต่ำ (last-resort ใช้ to_numpy)

    print('=== [A] iv alphanumeric (digits ตรงยอด) — ห้ามล้าง ===')
    res = {'iv_number': 'IV-1250', 'iv_number_raw': 'IV-1250',
           'subtotal': 1250, 'vat': 87.5, 'total': 1337.5, 'items': []}
    reject_iv_equal_amount(df, res, 0, 5, 4)
    _check(res['iv_number'] == 'IV-1250', "iv 'IV-1250' ไม่ถูกล้าง (digits 1250 บังเอิญตรง subtotal)")

    res2 = {'iv_number': 'CB-6905-0392', 'iv_number_raw': 'CB-6905-0392',
            'subtotal': 69050392, 'vat': 0, 'total': 69050392, 'items': []}
    reject_iv_equal_amount(df, res2, 0, 5, 4)
    _check(res2['iv_number'] == 'CB-6905-0392', "iv 'CB-6905-0392' ไม่ถูกล้าง (alphanumeric)")

    print('=== [B] iv ตัวเลขล้วน == ยอด — ยังถูกล้าง (money-misread guard เดิม) ===')
    res3 = {'iv_number': '200500', 'iv_number_raw': '200500',
            'subtotal': 200500, 'vat': 14035, 'total': 214535, 'items': []}
    reject_iv_equal_amount(df, res3, 0, 5, 4)
    _check(res3['iv_number'] != '200500',
           "iv '200500' (ตัวเลขล้วน==subtotal) ถูกล้าง/แทน (money-misread จับได้เดิม)")

    print('=== [C] iv ตัวเลขล้วนปกติ (ไม่ตรงยอด) — คงเดิม ===')
    res4 = {'iv_number': '01954', 'iv_number_raw': '01954',
            'subtotal': 5000, 'vat': 350, 'total': 5350, 'items': []}
    reject_iv_equal_amount(df, res4, 0, 5, 4)
    _check(res4['iv_number'] == '01954', "iv '01954' (ไม่ตรงยอด) คงเดิม")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — ล้างเฉพาะ iv ตัวเลขล้วน==ยอด ; iv มีตัวอักษรไม่ถูกล้าง (FP ปิด)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
