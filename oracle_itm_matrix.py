# -*- coding: utf-8 -*-
"""oracle_itm_matrix.py — ORACLE: บรรทัดรายการที่ 'ผิดจริง' ตัวไหนถูกฟ้อง / ตัวไหนหลุด

oracle อิสระ: บรรทัดถูกต้องก็ต่อเมื่อ
    qty × price == amount            (ไม่มีส่วนลด)
    qty × price × (1-discount) == amount   (มีส่วนลดพิสูจน์ได้จากเซลล์)
อย่างอื่น = ผิด → "ต้องมีกฎใดกฎหนึ่งฟ้อง" มิฉะนั้น = false-clean

รัน:  python3 oracle_itm_matrix.py
"""
from decimal import Decimal

import rules_engine as RE

CTX = {'sheet_name': '1', 'target_month': None, 'target_month_end': None,
       'all_masters': {}, 'unit_index': None, 'all_bills_for_iv_check': [],
       'xbill_tax_index': {}, 'xbill_file_index': {}, 'xbill_iv_index': {}}

ITEM_RULES = [c for c in RE.RULES if c.startswith(('ITM', 'VAT'))]


def mk(items):
    return {'file': 'x.xls', 'sheet': '1', 'company': 'บริษัท ก จำกัด',
            'company_raw': 'บริษัท ก จำกัด', 'tax_id': '0105556123456',
            'tax_id_raw': '0105556123456', 'branch': 'สำนักงานใหญ่',
            'branch_no': '00000', 'address': 'a', 'address_raw': 'a',
            'iv_number': 'IV1', 'iv_number_raw': 'IV1', 'iv_date': None,
            'iv_date_str': '05/05/2026', 'subtotal': None, 'vat': None,
            'total': None, 'items': items, 'issues': []}


def it(q, p, a, d=None):
    return {'seq': 1, 'name': 'ท่อพีวีซี', 'name_raw': 'ท่อพีวีซี', 'qty': q,
            'unit': 'เส้น', 'price': p, 'amount': a, 'discount': d}


def fired(items):
    """รหัสกฎที่ฟ้องบิลนี้"""
    b = mk(items)
    out = []
    for code in ITEM_RULES:
        r = RE.RULES[code]
        if not r.get('enabled'):
            continue
        try:
            if r['check'](b, None, CTX):
                out.append(code)
        except Exception:
            out.append(f"SYS-{code}")
    return out


def oracle_ok(q, p, a, d):
    """oracle อิสระ: บรรทัดนี้ถูกต้องหรือไม่"""
    if any(x is None for x in (q, p, a)):
        return None                       # ตรวจไม่ได้ (ข้อมูลหาย) — ไม่ใช่ 'ถูก'
    exp = Decimal(str(q)) * Decimal(str(p))
    if d is not None:
        exp = exp * (Decimal('1') - Decimal(str(d)))
    return abs(exp - Decimal(str(a))) <= Decimal('0.01')


CASES = [
    # (qty, price, amount, discount, คำอธิบาย)
    (5, 100, 500.0, None, 'ถูกต้อง'),
    (5, 100, 499.0, None, 'ผิด 1 บาท'),
    (5, 100, 450.0, None, 'ผิด 10% (ช่วงที่ ITM018 เดาว่าเป็นส่วนลด)'),
    (5, 100, 300.0, None, 'ผิด 40% (ช่วงที่ ITM018 เดาว่าเป็นส่วนลด)'),
    (5, 100, 200.0, None, 'ผิด 60%'),
    (5, 100, 0.0, None, 'amount=0 ทั้งที่ qty×price=500'),
    (0, 100, 500.0, None, 'qty=0 ทั้งที่ amount=500'),
    (5, 0, 500.0, None, 'price=0 ทั้งที่ amount=500'),
    (0, 0, 0.0, None, 'ศูนย์ทั้งบรรทัด (ถูกต้องตามตรรกะ)'),
    (5, 100, 450.0, 0.10, 'ส่วนลด 10% พิสูจน์ได้ → ถูกต้อง'),
    (5, 100, 400.0, 0.10, 'ส่วนลด 10% แต่ยอดไม่ลงตัว (ควรได้ 450)'),
    (5, 100, 1000.0, None, 'amount สูงกว่า 2 เท่า'),
]

print("=" * 96)
print(f"{'เคส':<48} {'oracle':<8} {'กฎที่ฟ้อง'}")
print("=" * 96)
holes = []
for q, p, a, d, desc in CASES:
    ok = oracle_ok(q, p, a, d)
    f = fired([it(q, p, a, d)])
    verdict = {True: 'ถูก', False: 'ผิด', None: '?'}[ok]
    mark = ''
    if ok is False and not f:
        mark = '  ❌ FALSE-CLEAN'
        holes.append((desc, q, p, a, d))
    elif ok is True and f:
        mark = '  ⚠ FP?'
    print(f"{desc:<48} {verdict:<8} {','.join(f) or '(เงียบ)'}{mark}")

print("=" * 96)
if holes:
    print(f"\n❌ พบช่องโหว่ false-clean {len(holes)} เคส:")
    for desc, q, p, a, d in holes:
        print(f"   • {desc}: qty={q} price={p} amount={a} discount={d}")
else:
    print("\n✅ ไม่พบ false-clean")
