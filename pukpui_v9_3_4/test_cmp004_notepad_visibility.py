# -*- coding: utf-8 -*-
"""test_cmp004_notepad_visibility.py — TRIPWIRE: ชื่อบริษัทเว้นวรรคผิด (CMP004) ต้องขึ้นในสรุปบริษัท

อาการที่ลูกค้าแจ้ง: "ชื่อบริษัทวรรคผิด รีพอร์ต Excel ขึ้น แต่รีพอร์ต Notepad (สรุปบริษัท) ไม่ขึ้น"
ต้นเหตุ: code_labels เดิมจัด CMP004 = เลน REVIEW → viewers.py เลื่อนเฉพาะ fix/check/master
         → REVIEW ตกหล่นเป็น "ตรง" เงียบ ๆ (ขึ้น Excel แต่ไม่ขึ้นสรุปบริษัท).
แก้: CMP004 -> เลน CHECK (เป็นความต่างที่ตรวจกับ master ได้จริง = ควรรีเช็ค) + ย่อข้อความให้สั้น.

advisory ล้วน — code_labels/viewers ไม่แตะ engine/golden (path Excel ไม่ได้ import code_labels).
    PYTHONHASHSEED=0 PUOPUY_ALLOW_VERSION_MISMATCH=1 python3 test_cmp004_notepad_visibility.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import datetime
import warnings

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

with contextlib.redirect_stdout(io.StringIO()):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

from code_labels import lane_of, CHECK
from golden_snapshot import MASTER
from rules_engine import run_rules
import super_ultra_viewer as V

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


print("\n[1] code_labels: CMP004 อยู่เลน CHECK (ไม่ใช่ REVIEW ที่ตกหล่นเงียบ)")
check(lane_of("CMP004") == CHECK, f"lane_of('CMP004') == CHECK (ได้ {lane_of('CMP004')!r})")


print("\n[2] บิลที่ชื่อ 'เว้นวรรคเกิน' จาก master → CMP004 ฟ้อง + ขึ้นในบล็อกสรุปบริษัท")
key = list(MASTER.keys())[0]
mname = MASTER[key]['name']
spaced = mname.replace(' ', '  ', 1)   # เพิ่มช่องว่างคู่ 1 จุด (ชื่อเดียวกัน ต่างแค่เว้นวรรค)
bill = {
    'company': mname, 'company_raw': spaced,
    'tax_id': MASTER[key]['tax_id'], 'tax_id_raw': MASTER[key]['tax_id'],
    'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
    'iv_number': 'IV6806001', 'iv_number_raw': 'IV6806001',
    'iv_date': datetime.date(2025, 6, 15), 'iv_date_str': '15/06/2025',
    'address': MASTER[key].get('address', ''),
    'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
    'sheet': '1', 'file': 'SHS_69.06.xls', 'block_idx': 0, 'issues': [],
    'items': [{'seq': 1, 'name': 'เหล็กเส้น', 'name_raw': 'เหล็กเส้น',
               'qty': 10.0, 'unit': 'เส้น', 'price': 100.0, 'amount': 1000.0}],
}
with contextlib.redirect_stdout(io.StringIO()):
    run_rules(bill, MASTER, {'month': 6, 'month_end': None, 'year': 2025},
              unit_index={}, all_bills_ref=[bill])
codes = [i['code'] for i in bill['issues']]
check('CMP004' in codes, f"CMP004 ฟ้อง (issues={codes})")

with contextlib.redirect_stdout(io.StringIO()):
    rows = V.build([bill], master_present=True)
name_line = ""
for i, r in enumerate(rows, 1):
    for ln in V.render_block(i, r).splitlines():
        if ln.strip().startswith('ชื่อบจ'):
            name_line = ln
print(f"     -> {name_line.strip()}")
check('ตรง' not in name_line.split(':', 1)[-1].split('รีเช็ค')[0] or 'เว้นวรรค' in name_line,
      "ช่อง 'ชื่อบจ.' ไม่ขึ้น 'ตรง' เฉย ๆ (ต้องโชว์ปัญหาเว้นวรรค)")
check('เว้นวรรค' in name_line, "ช่อง 'ชื่อบจ.' โชว์ 'เว้นวรรค...' (อาการที่ลูกค้าแจ้งถูกแก้)")
check('ช่อง' in name_line and '␣' not in name_line,
      "ข้อความย่อ/เป็นภาษาคน (โชว์จำนวน 'ช่อง' ไม่โชว์สตริง ␣ ยาว)")


print("\n[3] บิลชื่อตรง master เป๊ะ → ชื่อบจ. = 'ตรง' (ไม่ false-positive)")
ok = dict(bill); ok = {**bill, 'company_raw': mname, 'issues': []}
with contextlib.redirect_stdout(io.StringIO()):
    run_rules(ok, MASTER, {'month': 6, 'month_end': None, 'year': 2025}, unit_index={}, all_bills_ref=[ok])
check('CMP004' not in [i['code'] for i in ok['issues']], "ชื่อตรงเป๊ะ → CMP004 เงียบ (ไม่ FP)")


print("\n" + "=" * 64)
if FAIL:
    print(f"CMP004-VISIBILITY: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    sys.exit(1)
print(f"CMP004-VISIBILITY: ผ่าน {PASS} / ล้มเหลว 0")
print("=" * 64)
print("RESULT: ✅ ชื่อบริษัทเว้นวรรคผิด ขึ้นในสรุปบริษัท (Notepad) แล้ว + ข้อความย่อ")
sys.exit(0)
