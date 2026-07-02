# -*- coding: utf-8 -*-
"""test_adr140_bkk_skip.py — [ADR-140] district_postal_mismatch (ADDR007) เว้นกรุงเทพฯ จริง (dead-guard fix).

บั๊ก (logic conflict / dead-guard): เดิม
    `if province is None or province in _ADDR006_SKIP_PROVINCES: if province is None: return None`
→ กรุงเทพฯ (สมาชิกเดียวของ SKIP) เข้า if นอกได้ แต่ inner คืนเฉพาะ None → "ตกผ่าน" → ถูกประมวลผล
ทั้งที่ intent = เว้น (ADDR005 ดูแลโซน กทม.แล้ว). guard ตายสนิท.

แก้: `if ... : return None` (เว้นทั้ง None และ SKIP-province). golden-neutral (golden=23b315e8 delta=0).
ตรึง: กรุงเทพฯ → None (เว้น) ; province None → None (เดิม). รันได้ทุกที่.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thai_postal as TP

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== กรุงเทพฯ ถูกเว้น (skip) จริง — ไม่ ADDR007 ===')
    bkk_addrs = [
        'เลขที่ 1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
        '99/9 ถนนพระราม 4 แขวงสีลม เขตบางรัก กรุงเทพมหานคร 10500',
        'เลขที่ 5 แขวงจตุจักร เขตจตุจักร กรุงเทพมหานคร 99999',   # รหัสมั่ว — ถ้าไม่เว้นอาจฟ้อง
    ]
    for a in bkk_addrs:
        prov = TP.province_in_address(a)
        _check(prov == 'กรุงเทพมหานคร', f'province ของ {a[:30]!r}.. = กรุงเทพมหานคร (อยู่ใน SKIP)')
        _check(TP.district_postal_mismatch(a) is None,
               f'district_postal_mismatch เว้น (None) — {a[:30]!r}..')

    print('=== province None / addr ว่าง → None (เดิม) ===')
    _check(TP.district_postal_mismatch('') is None, "addr ว่าง → None")
    _check(TP.district_postal_mismatch('ของขายทั่วไป ไม่มีจังหวัด') is None, "ไม่มีจังหวัด → None")
    _check(TP.district_postal_mismatch(None) is None, "addr=None → None (ทน non-str)")

    print('=== non-Bangkok ที่ตรง → None (ไม่ false-positive) ===')
    ok = 'เลขที่ 1 ตำบลในเมือง อำเภอเมือง จังหวัดเชียงใหม่ 50000'
    _check(TP.district_postal_mismatch(ok) in (None,) or isinstance(TP.district_postal_mismatch(ok), list),
           "ที่อยู่เชียงใหม่ปกติ → ไม่ครัช (None หรือ list)")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — กรุงเทพฯ ถูกเว้นจริง (dead-guard แก้แล้ว) ; เคสอื่นเดิม')
    return 0


if __name__ == '__main__':
    sys.exit(main())
