# -*- coding: utf-8 -*-
"""test_adr133_consolidator_robust.py — [ADR-133] consolidate_bill ทนบิลเพี้ยน (ชั้นรายงาน).

บั๊ก: `consolidate_bill` ครัช 3 ทาง — (1) `bill['issues']=None` → `for iss in None` TypeError ;
(2) issue ที่ไม่ใช่ dict (str) → `.get` AttributeError ; (3) `code` เป็น non-str (int) →
`_family`/`sorted(codes)`/`",".join` ครัช. ชั้นรายงาน (advisory) → ครัชทำ Error Report ล่ม.
แก้: `(issues or [])` + ข้าม non-dict + `str(code)`. golden-neutral (report layer, ไม่แตะ audit).
รันได้ทุกที่.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import issue_consolidator as IC

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== ทนบิลเพี้ยน (ไม่ครัช) ===')
    cases = [
        ('issues=None', {'file': 'F', 'issues': None}),
        ('issues ขาด', {'file': 'F'}),
        ('non-dict issue', {'file': 'F', 'issues': ['ขยะ', None, 123]}),
        ('non-str code', {'file': 'F', 'issues': [{'code': 123, 'name': 'x', 'severity': 'ERROR', 'detail': ''}]}),
        ('code=None', {'file': 'F', 'issues': [{'code': None, 'name': 'x', 'severity': 'ERROR', 'detail': 'd'}]}),
    ]
    for desc, bill in cases:
        try:
            out = IC.consolidate_bill(bill)
            _check(isinstance(out, list), f'{desc}: คืน list ไม่ครัช')
        except Exception as e:  # noqa: BLE001
            _check(False, f'{desc}: ครัช {type(e).__name__}: {e}')

    print()
    print('=== บิลปกติยังได้ผลเดิม (byte-identical behavior) ===')
    bill = {'file': 'F.xls', 'sheet': 's', 'iv_number': 'IV1',
            'issues': [{'code': 'TAX001', 'name': 'เลขภาษีผิด', 'severity': 'CRITICAL', 'detail': 'x'}]}
    out = IC.consolidate_bill(bill)
    _check(len(out) == 1 and out[0]['codes'] == 'TAX001', 'บิลปกติ: 1 finding, code=TAX001')
    _check(out[0]['file'] == 'F.xls', 'บิลปกติ: file ถูกต้อง')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — consolidate_bill ทนบิลเพี้ยน + บิลปกติเดิม')
    return 0


if __name__ == '__main__':
    sys.exit(main())
