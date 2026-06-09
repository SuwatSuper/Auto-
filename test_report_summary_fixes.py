# -*- coding: utf-8 -*-
"""test_report_summary_fixes.py — สรุปบริษัท (Notepad): ชื่อเข้มขึ้น (CMP006) + ที่อยู่สั้น

อาการที่ลูกค้าแจ้ง:
  (ก) ชื่อบริษัทต่างจาก ภ.พ.20 เล็กน้อย (ฉี/ชี, กรุ๊ป/กรุงเทพ) ระบบยอมผ่านเป็น 'ตรง' (fuzzy≥85)
      → เพิ่มกฎ CMP006 (เลน CHECK) ฟ้องโซน fuzzy ที่ CMP001 ปล่อยผ่าน (ต่างตัวอักษร = ฟ้อง)
  (ข) ที่อยู่ในรีพอร์ตยาวมาก (ดัมพ์ทุกบิล) → สรุปสั้น "บอกเฉพาะ field ที่ผิด + จำนวนบิล"

advisory-only: code_labels/viewers/CMP006(เลน CHECK) ไม่แตะ path Excel byte-identical.
    PYTHONHASHSEED=0 PUOPUY_ALLOW_VERSION_MISMATCH=1 python3 test_report_summary_fixes.py
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

from golden_snapshot import MASTER
from rules_engine import run_rules, RULES
from code_labels import addr_summary, lane_of, CHECK
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


key = list(MASTER.keys())[0]
mname = MASTER[key]['name']
tid = MASTER[key]['tax_id']


def mk(name, raw=None):
    return {'company': name, 'company_raw': raw or name, 'tax_id': tid, 'tax_id_raw': tid,
            'branch': 'สำนักงานใหญ่', 'branch_no': '00000', 'iv_number': 'IV1', 'iv_number_raw': 'IV1',
            'iv_date': datetime.date(2025, 6, 2), 'iv_date_str': '02/06/2025',
            'address': MASTER[key].get('address', ''), 'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
            'sheet': '1', 'file': 'SHS_69.06.xls', 'block_idx': 0, 'issues': [],
            'items': [{'seq': 1, 'name': 'เหล็ก', 'name_raw': 'เหล็ก', 'qty': 1.0, 'unit': 'เส้น',
                       'price': 1.0, 'amount': 1.0}]}


def codes(b):
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(b, MASTER, {'month': 6, 'month_end': None, 'year': 2025}, unit_index={}, all_bills_ref=[b])
    return [i['code'] for i in b['issues']]


print("\n[CMP006] ชื่อเข้มขึ้น — โซน fuzzy ที่ CMP001 ปล่อยผ่าน")
check('CMP006' in RULES, "CMP006 อยู่ใน RULES")
check(lane_of('CMP006') == CHECK, "CMP006 เลน CHECK (โชว์ในสรุปบริษัท)")
check('CMP006' not in codes(mk(mname)), "ชื่อตรงเป๊ะ → CMP006 เงียบ")
check('CMP006' in codes(mk(mname.replace('ฉี', 'ชี'))), "ฉี→ชี (ต่าง 1 ตัว) → CMP006 ฟ้อง")
check('CMP006' in codes(mk(mname.replace('กรุ๊ป', 'กรุงเทพ'))), "กรุ๊ป→กรุงเทพ → CMP006 ฟ้อง")
sp = codes(mk(mname, mname.replace(' ', '  ', 1)))
check('CMP004' in sp and 'CMP006' not in sp, "เว้นวรรคเกิน → CMP004 เท่านั้น (ไม่ซ้ำ CMP006)")
check('CMP006' not in codes(mk(mname + ' (สำนักงานใหญ่)')), "ต่อท้าย (สำนักงานใหญ่) → CMP006 เงียบ (substring ไม่ FP)")

# viewer: ชื่อบจ. โชว์ CMP006 แบบย่อ
b = mk(mname.replace('ฉี', 'ชี')); codes(b)
with contextlib.redirect_stdout(io.StringIO()):
    rows = V.build([b], master_present=True)
nl = ""
for i, r in enumerate(rows, 1):
    for ln in V.render_block(i, r).splitlines():
        if ln.strip().startswith('ชื่อบจ'):
            nl = ln
check('ไม่ตรง ภ.พ.20' in nl and 'ตรง' != nl.split(':', 1)[-1].strip(),
      "viewer: ชื่อบจ. โชว์ 'ไม่ตรง ภ.พ.20' (ไม่ใช่ 'ตรง')")


print("\n[ADDR] ที่อยู่สั้น — บอกเฉพาะ field ที่ผิด + จำนวนบิล")
det = ("ที่อยู่ไม่ตรงทะเบียน: รหัสไปรษณีย์ไม่ตรง (บิล: 10540 / ทะเบียน: 10280); "
       "เขต/อำเภอไม่ตรง (บิล: บางพลี / ทะเบียน: เมือง); แขวง/ตำบลไม่ตรง (บิล: ราชาเทวะ / ทะเบียน: แพรกษา); "
       "เลขที่ไม่ตรง (บิล: 299/76 / ทะเบียน: 1122/68)")
entries9 = [{'file': 'TKH', 'sheet': str(i), 'date': f'2{i}.05.2026', 'detail': det} for i in range(9)]
s9 = addr_summary(entries9)
print("    ->", s9)
check('รหัสไปรษณีย์' in s9 and 'เขต-อำเภอ' in s9 and 'เลขที่' in s9, "ระบุ field ที่ผิดครบ")
check('(9 บิล)' in s9, "นับจำนวนบิลถูก (9 บิล)")
check('ทะเบียน' not in s9 and '␣' not in s9, "ย่อ/ไม่ดัมพ์ค่าที่อยู่เต็ม (เป็นภาษาคน)")
# ผิดแค่ field เดียว
s1 = addr_summary([{'file': 'TSH', 'sheet': '1', 'date': 'x',
                    'detail': 'ที่อยู่ไม่ตรงทะเบียน: รหัสไปรษณีย์ไม่ตรง (บิล: 10540 / ทะเบียน: 10280)'}])
check(s1.startswith('รหัสไปรษณีย์ ไม่ตรง (1 บิล)'), f"ผิด field เดียว → สั้นตรง ({s1})")


print("\n" + "=" * 64)
if FAIL:
    print(f"REPORT-SUMMARY: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    sys.exit(1)
print(f"REPORT-SUMMARY: ผ่าน {PASS} / ล้มเหลว 0")
print("=" * 64)
print("RESULT: ✅ ชื่อเข้มขึ้น (CMP006) + ที่อยู่สั้น (เฉพาะ field ผิด + จำนวนบิล)")
sys.exit(0)
