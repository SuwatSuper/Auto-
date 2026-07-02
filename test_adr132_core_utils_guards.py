# -*- coding: utf-8 -*-
"""test_adr132_core_utils_guards.py — [ADR-132] core_utils crash-guards (golden-neutral).

(A) iv_amount_fragment: `repr(float(v))` ระเบิด OverflowError เมื่อ v = int มหึมา (เกินช่วง float)
    → r_iv007 (rules_engine_rules_c) ครัช → SYS → ข้ามกฎ = false-negative. แก้: try/except → ข้ามค่า
    ที่ float ไม่ได้ (ไม่ใช่ "เศษ float ของยอด"). corpus SYS=0 → guard no-op → golden-neutral.
(B) sort_bills_by_date: `b['file']` ดิบ (ไม่ str-wrap) → TypeError ตอน tie บน iv_date เดียวกัน + file=None.
    แก้: str-wrap file/sheet (เหมือน sheet เดิม). corpus file=basename(str) → byte-identical ; ชั้นรายงาน
    (downstream audit) → golden ไม่กระทบ.

ตรึง: ไม่ครัชบน adversarial + พฤติกรรมปกติเดิม (float-tail detection, sort order). รันได้ทุกที่.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core_utils as C

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== [A] iv_amount_fragment กัน OverflowError (int มหึมา) ===')
    for huge in (10 ** 400, 10 ** 309, -(10 ** 400)):
        try:
            r = C.iv_amount_fragment('123456', total=huge)
            _check(r is False, f'iv_amount_fragment(total={"int " + str(len(str(abs(huge)))) + " digits"}) = False (ไม่ครัช)')
        except Exception as e:  # noqa: BLE001
            _check(False, f'iv_amount_fragment ครัช: {type(e).__name__}')

    print()
    print('=== [A2] iv_amount_fragment พฤติกรรมปกติเดิม (float-tail detection byte-identical) ===')
    # เคส docstring: iv '0000000002' = เศษ float ของ VAT 1416233.0000000002
    _check(C.iv_amount_fragment('0000000002', vat=1416233.0000000002) is True,
           "float-tail: iv '0000000002' == frac ของ VAT → True (เดิม)")
    _check(C.iv_amount_fragment('123', total=999999.0) is False,
           "iv สั้น (<6) → False (เดิม)")
    _check(C.iv_amount_fragment('200500', total=200500) is False,
           "integer-mismatch ยังเป็น False (ไม่แตะ detection semantics PG-05/golden-risk)")

    print()
    print('=== [B] sort_bills_by_date กัน TypeError (file/sheet None) ===')
    bills = [{'iv_date': datetime(2026, 1, 1), 'file': None, 'sheet': 's'},
             {'iv_date': datetime(2026, 1, 1), 'file': 'a', 'sheet': 1},
             {'iv_date': None, 'file': 'b', 'sheet': None}]
    try:
        out = C.sort_bills_by_date(bills)
        _check(len(out) == 3, 'sort_bills_by_date ไม่ครัชบน file/sheet None')
    except Exception as e:  # noqa: BLE001
        _check(False, f'sort_bills_by_date ครัช: {type(e).__name__}: {e}')

    print('=== [B2] sort order ปกติ (file=str เสมอ) byte-identical ===')
    a = {'iv_date': datetime(2026, 1, 2), 'file': 'z.xls', 'sheet': 'a'}
    b = {'iv_date': datetime(2026, 1, 1), 'file': 'a.xls', 'sheet': 'b'}
    _check(C.sort_bills_by_date([a, b]) == [b, a], 'เรียงตาม iv_date ก่อน (เดิม)')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — core_utils ไม่ครัชบน adversarial + พฤติกรรมปกติเดิม')
    return 0


if __name__ == '__main__':
    sys.exit(main())
