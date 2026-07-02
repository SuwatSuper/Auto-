# -*- coding: utf-8 -*-
"""test_adr155_issues_coerce.py — [ADR-155] run_rules coerce bill['issues'] → list.

บั๊กเดิม (silent false-negative): bill.setdefault('issues', []) เป็น no-op ถ้า 'issues' มีอยู่แต่เป็น
non-list (None/''/dict/int) → add_issue เรียก b['issues'].append(...) ครัชในทุกกฎที่ "พบปัญหา" →
run_rules ดักเป็น SYS-<code> แล้ว "ข้ามกฎเงียบ" → บิลที่มี ERROR/CRITICAL จริงโผล่เป็น 'ตรง' หลอก.

เทสนี้ป้อนบิลที่ issues=non-list แล้วยืนยันว่ากฎยัง "ฟ้องได้" (issues ถูก coerce เป็น list + มี finding)
และ golden-neutral (บิล issues=list ปกติ ผลเท่าเดิม).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules_engine as RE

fails = 0
def check(cond, msg):
    global fails
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        fails += 1

print("ADR-155 — run_rules coerce issues→list (กัน silent FN)")

def _bill_with_bad_taxid(issues_val):
    # เลขภาษีสั้น → TAX001 (CRITICAL) ต้องฟ้อง ; item ปกติ 1 รายการ
    return {
        'tax_id': '123', 'company': 'บริษัท ทดสอบ จำกัด', 'address': '',
        'iv_number': 'IV001', 'sheet': '1', 'file': 'x.xls',
        'items': [{'seq': 1, 'name': 'ของ', 'qty': 1, 'unit': 'ชิ้น', 'price': 1.0, 'amount': 1.0}],
        'issues': issues_val,
        'subtotal': 1.0, 'vat': 0.07, 'total': 1.07,
    }

# baseline: issues=[] ปกติ → TAX001 ฟ้อง
b_ok = _bill_with_bad_taxid([])
RE.run_rules(b_ok, {}, {}, all_bills_ref=[b_ok])
codes_ok = {i.get('code') for i in b_ok['issues']}
check('TAX001' in codes_ok, f"baseline issues=[] → TAX001 ฟ้อง (codes={sorted(codes_ok)})")

# บั๊กเคส: issues=non-list ต่าง ๆ → ต้อง coerce + ยังฟ้อง TAX001 (ไม่ครัชเงียบ)
for bad in (None, '', {'x': 1}, 0, 'already-a-string'):
    b = _bill_with_bad_taxid(bad)
    try:
        RE.run_rules(b, {}, {}, all_bills_ref=[b])
        thrown = False
    except Exception:
        thrown = True
    is_list = isinstance(b.get('issues'), list)
    codes = {i.get('code') for i in b['issues']} if is_list else set()
    check(not thrown and is_list and 'TAX001' in codes,
          f"issues={bad!r:22} → coerce เป็น list + TAX001 ฟ้อง (ไม่ silent-skip)")

# golden-neutral spot: บิล issues=list ที่มีของเดิมอยู่แล้ว → ไม่ถูกล้าง (append ต่อ)
pre = [{'code': 'SEED', 'severity': 'INFO', 'category': 'x', 'name': 'seed', 'detail': 'd'}]
b2 = _bill_with_bad_taxid(list(pre))
RE.run_rules(b2, {}, {}, all_bills_ref=[b2])
check(any(i.get('code') == 'SEED' for i in b2['issues']) and any(i.get('code') == 'TAX001' for i in b2['issues']),
      "issues=list เดิม (มีของ) → ไม่ถูกล้าง + ฟ้องเพิ่มได้ (append ต่อ) = golden-neutral")

print(("RESULT: ✅ ADR-155 ผ่าน" if fails == 0 else f"RESULT: ❌ {fails} ข้อไม่ผ่าน"))
sys.exit(1 if fails else 0)
