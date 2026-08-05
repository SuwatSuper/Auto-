# -*- coding: utf-8 -*-
"""test_adr131_item_member.py — [ADR-131] run_rules coerce "สมาชิก non-dict" ใน items
(พี่น้องของ GAP-B/ADR-124 ที่ coerce container→list ; จุดนี้คือ "สมาชิก" ที่ตกหล่น).

บั๊ก (กลาง, false-negative): bill['items'] มีสมาชิกที่ไม่ใช่ dict (None/str/int — บิลภายนอก/
parser อนาคต) → loop coercion ใน run_rules coerce เฉพาะ dict → สมาชิก non-dict ค้าง → กฎ
ITM/VAT ~14 ตัวที่อ้าง it['name']/it.get('amount') ดิบ ครัช → run_rules ดักเป็น SYS-* →
"ข้ามกฎเงียบ" = บิลโผล่ 'ตรง' หลอก (false-negative อันตรายกว่า false-positive).

แก้: drop สมาชิก non-dict ก่อนรันกฎ (เหมือน analytics._safe_items). corpus 0/3307 non-dict
→ no-op → golden-NEUTRAL (golden=23b315e8). เทสนี้ล็อก: ไม่ครัช + กฎ item/VAT ยังตรวจ item จริง.
รันได้ทุกที่.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules_engine as RE
import diagnostics

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def _bill(items):
    return {'company': 'บริษัท ทดสอบ จำกัด', 'company_raw': 'บริษัท ทดสอบ จำกัด',
            'tax_id': '0105551234567', 'tax_id_raw': '0105551234567',
            'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
            'iv_number': 'IV1', 'iv_number_raw': 'IV1', 'iv_date': None, 'iv_date_str': '',
            'address': '', 'subtotal': 100, 'vat': 7, 'total': 107,
            'sheet': 's', 'file': 't.xls', 'block_idx': 0, 'items': items, 'issues': []}


def _run_capture(items):
    """รัน run_rules ; คืน (raised, sys_codes, issue_codes)."""
    sys_codes = []
    orig = diagnostics.log_system_issue

    def spy(*a, **k):
        sys_codes.append(k.get('code') or (a[0] if a else '?'))
        return orig(*a, **k)
    diagnostics.log_system_issue = spy
    RE.log_system_issue = spy
    raised = None
    bill = _bill(items)
    try:
        RE.run_rules(bill, {}, None)
    except Exception as e:  # noqa: BLE001
        raised = f'{type(e).__name__}: {e}'
    finally:
        diagnostics.log_system_issue = orig
        RE.log_system_issue = orig
    return raised, sys_codes, [i.get('code') for i in bill['issues']], bill


def main():
    valid = {'seq': 1, 'name': 'ของจริง', 'name_raw': 'ของจริง', 'qty': 1,
             'unit': 'ชิ้น', 'price': 100, 'amount': 100}

    print('=== [A] baseline: items ปกติ (dict ล้วน) — ไม่มี SYS จากการ coerce ===')
    raised, syscodes, codes, _ = _run_capture([dict(valid)])
    _check(raised is None, 'run_rules ไม่ครัช (items ปกติ)')
    item_sys = [c for c in syscodes if 'ITM' in str(c) or 'VAT' in str(c)]
    _check(not item_sys, f'ไม่มี SYS-ITM/VAT (items ปกติ) — เจอ: {item_sys}')

    print()
    print('=== [B] non-dict member (None/str/int) — drop ออก ไม่ครัช ไม่ SYS ===')
    for desc, items in [('items=[None, valid]', [None, dict(valid)]),
                        ('items=["str", valid]', ['ขยะ', dict(valid)]),
                        ('items=[123, None, valid]', [123, None, dict(valid)]),
                        ('items=[None]', [None])]:
        raised, syscodes, codes, bill = _run_capture(items)
        item_sys = [c for c in syscodes if 'ITM' in str(c) or 'VAT' in str(c)]
        _check(raised is None, f'{desc}: run_rules ไม่ครัช')
        _check(not item_sys, f'{desc}: ไม่มี SYS-ITM/VAT (กฎ item/VAT ไม่ถูกข้ามเงียบ) — เจอ: {item_sys}')
        _check(all(isinstance(it, dict) for it in bill['items']),
               f'{desc}: bill[items] เหลือเฉพาะ dict (สมาชิก non-dict ถูก drop)')

    print()
    print('=== [C] valid item ยังถูกตรวจจริง (ไม่ใช่ข้ามทั้งบิล) ===')
    # item ที่ qty*price != amount → ITM001/006 ควรมีโอกาสยิง (พิสูจน์ "ตรวจจริง")
    bad_item = {'seq': 1, 'name': 'ของ', 'name_raw': 'ของ', 'qty': 2, 'unit': 'ชิ้น', 'price': 100, 'amount': 999}
    raised, syscodes, codes, _ = _run_capture([None, bad_item])
    item_sys = [c for c in syscodes if 'ITM' in str(c) or 'VAT' in str(c)]
    _check(raised is None and not item_sys,
           'items=[None, bad_item]: ไม่ครัช + กฎ item รันจริงบน item ที่เหลือ')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — non-dict item member ไม่ทำกฆ item/VAT ครัช→ข้ามเงียบ (false-negative ปิด)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
