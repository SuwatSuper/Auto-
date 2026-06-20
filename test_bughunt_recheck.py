# -*- coding: utf-8 -*-
"""test_bughunt_recheck — ด่านกันถอยหลังของบั๊กที่พบในรอบรีเช็คทั้งระบบ (BUGHUNT_RECHECK).

รันเดี่ยว: PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_bughunt_recheck.py
ทุกเคสเป็น "พิสูจน์ว่าแก้แล้ว" + "พิสูจน์ว่าไม่ทำของเดิมพัง" (regression guard).
"""
import os, sys, io, contextlib, datetime as dt

os.environ.setdefault('PYTHONHASHSEED', '0')
os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

with contextlib.redirect_stdout(io.StringIO()):
    import importlib
    app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
    app.reset_run_state()

import validators as V
import rules_engine_rules_b as rb
import rules_engine_rules_c as rc
import parser_p1 as p1
from puopuy_units import _D
from puopuy_dates import parse_date_any

_fails = []


def chk(label, cond):
    print(('  ✅' if cond else '  ❌'), label)
    if not cond:
        _fails.append(label)


def _mk(ivn):
    return {'iv_number': ivn, 'iv_date': dt.datetime(2026, 5, 5),
            'tax_id': '0993000528883', 'company': 'X', 'file': 'F.xls', 'issues': []}


print('== #1 IV ซ้ำ/ถอยหลัง ข้ามหลัก 100/1000 ==')
chk('dup IV0100 ข้าม 99/100 ถูกจับ',
    any(o['type'] == 'IV ซ้ำเลขท้าย' for o in V._iv_check_sequence([_mk('IV0100'), _mk('IV0100'), _mk('IV0099')])))
chk('dup ข้าม 999/1000 ถูกจับ',
    any(o['type'] == 'IV ซ้ำเลขท้าย' for o in V._iv_check_sequence([_mk('IV1000'), _mk('IV1000'), _mk('IV0999')])))
chk('control (ไม่ข้ามหลัก) ยังจับซ้ำได้',
    any(o['type'] == 'IV ซ้ำเลขท้าย' for o in V._iv_check_sequence([_mk('IV0102'), _mk('IV0102'), _mk('IV0101')])))
chk('format ต่างจริง (raw 3 vs 4 หลัก) ยังข้ามถูกต้อง',
    V._iv_check_sequence([_mk('IV100'), _mk('IV0099')]) == [])

print('== #2 VAT004 ปิดใช้งาน (เจ้าของยืนยันถูกต้อง — ปัดทศนิยม 2 ตำแหน่งถูกแล้ว) ==')
from rules_engine import RULES
import code_registry as CR
chk('VAT004 ปิดใน RULES (enabled=False)', RULES['VAT004'].get('enabled') is False)
chk('VAT004 มีเหตุผลใน DISABLED_BY_DESIGN', 'VAT004' in CR.DISABLED_BY_DESIGN)
chk('r_vat004 ไม่ flag float residue 12128.830000000002',
    rb.r_vat004({'subtotal': 12128.830000000002, 'vat': 0.0, 'total': 12128.830000000002, 'items': []}, {}, {}) == [])
chk('r_vat004 ไม่ flag ทศนิยม 3 ตำแหน่ง (ปัดเป็น 2 = ถูกต้อง)',
    rb.r_vat004({'subtotal': 100.123, 'vat': 0.0, 'total': 100.123, 'items': []}, {}, {}) == [])

print('== #3 ANTI_PREFIX (label ยอดเงิน ≠ เลขที่ใบกำกับ) ==')
chk("'VAT 1416233' ไม่ถูกอ่านเป็น IV", p1._pick_best_iv('VAT 1416233') is None)
chk("'NET 999999' ไม่ถูกอ่านเป็น IV", p1._pick_best_iv('NET 999999') is None)
chk("'SUM 250000' ไม่ถูกอ่านเป็น IV", p1._pick_best_iv('SUM 250000') is None)
chk('เลขที่ใบกำกับจริงยังอ่านได้', p1._pick_best_iv('IV-69050092') == 'IV69050092')
chk("'REF 123456' ยังถูกปฏิเสธ (เดิมถูก)", p1._pick_best_iv('REF 123456') is None)

print('== #4 _D() กัน nan/inf ==')
chk("_D('nan') -> None", _D('nan') is None)
chk("_D('inf') -> None", _D('inf') is None)
chk('_D(float inf) -> None', _D(float('inf')) is None)
chk('_D(float nan) -> None', _D(float('nan')) is None)
chk('_D ปกติยังทำงาน (1,234.50)', _D('1,234.50') == _D(1234.50))

print('== #5 วันอธิกสุรทิน พ.ศ. 4 หลัก ==')
chk('29/2/2567 -> 2024-02-29', parse_date_any('29/2/2567') == dt.datetime(2024, 2, 29))
chk('2567-02-29 -> 2024-02-29', parse_date_any('2567-02-29') == dt.datetime(2024, 2, 29))
chk('29-02-2567 -> 2024-02-29', parse_date_any('29-02-2567') == dt.datetime(2024, 2, 29))
chk('วันปกติ 05/05/2569 -> 2026-05-05 (ไม่เปลี่ยน)', parse_date_any('05/05/2569') == dt.datetime(2026, 5, 5))
chk('วันไม่มีจริง 30/02/2567 ยังคืน None', parse_date_any('30/02/2567') is None)

print('== #6 r_addr005 ใช้ไปรษณีย์ตัวท้าย ==')
chk('เลขบ้าน 5 หลักนำหน้าไปรษณีย์ → ไม่ false positive',
    rc.r_addr005({'address': 'เลขที่ 12345 หมู่ 5 กรุงเทพมหานคร 10240'}, {}, {}) == [])
chk('ไปรษณีย์กรุงเทพผิดจริงยังถูกฟ้อง',
    rc.r_addr005({'address': 'กรุงเทพมหานคร 50200'}, {}, {}) != [])

print('== #9/+ defensive ==')
chk('r_vat007 bool money ไม่ครัช',
    rc.r_vat007({'items': [{'amount': 100.0}], 'subtotal': True, 'vat': True}, {}, {}) == [])
chk("r_itm013 seq เป็น string '1','2','3' ไม่ false positive",
    rb.r_itm013({'items': [{'seq': '1'}, {'seq': '2'}, {'seq': '3'}]}, {}, {}) == [])
chk('r_itm013 seq int เริ่มที่ 2 ยังฟ้อง',
    rb.r_itm013({'items': [{'seq': 2}, {'seq': 3}]}, {}, {}) != [])

print('== รายงาน: หน่วยสินค้าทำเหมือนรายการสินค้า (ตัด "ควรเป็น") ==')
import super_ultra_viewer as SUV
_ub = {'file': 'TSH_69_05.xls', 'sheet': '1', 'company': 'บริษัท ทดสอบ จำกัด', 'tax_id': '0',
       'branch': 'สำนักงานใหญ่', 'address': 'x', 'iv_number': 'IV1',
       'iv_date': dt.datetime(2022, 6, 13), 'total': 1070.0, 'vat': 70.0, 'subtotal': 1000.0,
       'items': [{'seq': 6, 'name': 'ทินเนอร์', 'unit': 'ปี๊ป'}],
       'issues': [{'code': 'ITM019', 'detail': '#6: "ทินเนอร์" — หน่วย "ปี๊ป" ควรเป็น "ปี๊บ"', 'severity': 'WARNING'}]}
_blk = SUV.render_block(1, SUV.build([_ub])[0])
chk("หน่วยโชว์ 'หน่วย ปี๊ป' (แบบรายการสินค้า)", 'หน่วย ปี๊ป' in _blk)
chk("ไม่มีรูปเดิม 'ควรเป็น' ในบล็อก", 'ควรเป็น' not in _blk)

print('== รายงาน: หมายเหตุหน่วยไทย/อังกฤษ สั้น (ตัด list หน่วย + ลงท้ายครับ) ==')
import unit_detection_ext as UX
# company_unit_notes อ่าน "ช่องหน่วย" ตรง ๆ (กก ↔ kg)
_cbill = {'file': 'SHS_69_05.xls', 'company': 'บ.เอ', 'tax_id': '0111111111111',
          'items': [{'seq': 1, 'name': 'a', 'unit': 'กก'}, {'seq': 2, 'name': 'b', 'unit': 'kg'}]}
_notes = UX.company_unit_notes([_cbill])
chk('company note ลงท้าย "ครับ"', any(n.endswith('ครับ') for n in _notes))
chk('company note ไม่ list หน่วย (ไม่มี "(ไทย:")', all('(ไทย:' not in n for n in _notes))
# file_spec อ่าน "หน่วยวัดฝังในชื่อ/สเปก" → ต้องมีเลขนำหน้า (เช่น 9มม. / 9mm.)
def _fb(fl, *specs):
    return {'file': fl, 'company': 'บ.เอ', 'tax_id': '0111111111111',
            'items': [{'seq': i + 1, 'name': s, 'unit': ''} for i, s in enumerate(specs)]}
_fnotes = UX.file_spec_unit_lang_notes([_fb('SHS_69_05.xls', 'ท่อ 9มม.', 'pipe 9mm.'),
                                        _fb('TSH_69_05.xls', 'แผ่น 5ซม.', 'sheet 5cm.')])
chk('file note รวมไฟล์เป็นบรรทัดเดียว "SHS และ TSH"', any('SHS และ TSH' in n for n in _fnotes))
chk('file note ลงท้าย "ครับ" + ไม่ list หน่วย',
    all(n.endswith('ครับ') and '(ไทย:' not in n for n in _fnotes))

print()
if _fails:
    print(f'RESULT: ❌ FAIL ({len(_fails)} เคส)')
    for f in _fails:
        print('   -', f)
    sys.exit(1)
print('RESULT: ✅ PASS — ทุกบั๊ก recheck แก้แล้ว และของเดิมไม่พัง')
