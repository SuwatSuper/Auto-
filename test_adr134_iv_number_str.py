# -*- coding: utf-8 -*-
"""test_adr134_iv_number_str.py — [ADR-134] check_iv_date_sequence str-wrap iv_number (กัน non-str ครัช).

บั๊ก: validators.check_iv_date_sequence:287 ทำ `re.sub(r'[^\\d]','',b['iv_number'])` ดิบ — guard
บรรทัดบนกรองแค่ falsy → iv_number ที่ truthy แต่ non-str (int 123 จากบิลภายนอก) ทำ re.sub ระเบิด
TypeError → crosscheck IV004 ครัชทั้งชุดบิล. sibling (186/224/324) str-wrap หมดแล้ว — จุดนี้ตกหล่น.
แก้: str() wrap. corpus iv_number=str เสมอ → no-op → golden-neutral (golden=23b315e8). รันได้ทุกที่.
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validators as V

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== check_iv_date_sequence ทน iv_number non-str (ไม่ครัช) ===')
    # บิลที่ iv_number เป็น int (truthy non-str) → เดิม re.sub ระเบิด
    bills = [
        {'iv_number': 1001, 'iv_date': date(2026, 1, 5), 'file': 'f.xls'},
        {'iv_number': 1002, 'iv_date': date(2026, 1, 6), 'file': 'f.xls'},
        {'iv_number': 'CB-6905-0001', 'iv_date': date(2026, 1, 7), 'file': 'f.xls'},
    ]
    try:
        out = V.check_iv_date_sequence(bills)
        _check(isinstance(out, list), 'check_iv_date_sequence(int iv_number) ไม่ครัช → คืน list')
    except Exception as e:  # noqa: BLE001
        _check(False, f'ครัช: {type(e).__name__}: {e}')

    print('=== iv_number=str ปกติยังทำงานเดิม ===')
    bills2 = [
        {'iv_number': 'IV-001', 'iv_date': date(2026, 1, 5), 'file': 'f.xls'},
        {'iv_number': 'IV-002', 'iv_date': date(2026, 1, 6), 'file': 'f.xls'},
    ]
    try:
        out2 = V.check_iv_date_sequence(bills2)
        _check(isinstance(out2, list), 'iv_number=str: คืน list (เดิม)')
    except Exception as e:  # noqa: BLE001
        _check(False, f'ครัช (str): {type(e).__name__}: {e}')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — check_iv_date_sequence str-wrap iv_number, ไม่ครัช non-str')
    return 0


if __name__ == '__main__':
    sys.exit(main())
