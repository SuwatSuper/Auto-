# -*- coding: utf-8 -*-
"""test_unit_detection_ext.py — เทสการ "ตรวจจับหน่วยสินค้าเพิ่มเติม" (ADD-ON)

ครอบ 4 อาการที่ลูกค้าแจ้ง + กัน false-positive + การผูกกฎ ITM019 + ส่วน Notepad:
  (1) ตรม. (ตารางเมตร) ถูกรู้จัก (hint/สรุป) และไม่ถูกฟ้องผิด
  (2) fuzzy หน่วยที่ผิดครอบครบขึ้น (map + rapidfuzz)
  (3) ปี๊ป/แกลอน/แกนลอน ถูกจับ พร้อมคำแนะนำรูปมาตรฐาน
  (4) ไฟล์เดียวปนหน่วยไทย+อังกฤษ → ตรวจเจอ (สำหรับ Notepad)
  + หน่วยมาตรฐานต้องไม่ถูกฟ้อง (กัน FP)
  + ITM019 ผูกใน RULES และ run_rules เรียกได้จริง
  + _render_unit_consistency ผลิตข้อความที่มีคำเตือนครบ

ทั้งหมดเป็น add-on อ่านอย่างเดียว — ไม่แตะ logic เดิม/golden hash.
    PYTHONHASHSEED=0 PUOPUY_ALLOW_VERSION_MISMATCH=1 python3 test_unit_detection_ext.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import copy
import contextlib
import warnings

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import unit_detection_ext as ux

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


# ════════════════════════ (1) ตรม. — หน่วยพื้นที่ ════════════════════════
print("\n[1] ตรม. (ตารางเมตร) ถูกรู้จัก + ไม่ถูกฟ้องผิด")
check(ux.canonical_family_key('ตรม.') == 'ตรม.', "ตรม. → family 'ตรม.'")
check(ux.canonical_family_key('ตร.ม.') == 'ตรม.', "ตร.ม. → family 'ตรม.'")
check(ux.canonical_family_key('ตารางเมตร') == 'ตรม.', "ตารางเมตร → family 'ตรม.'")
check(ux.canonical_family_key('sqm') == 'ตรม.', "sqm → family 'ตรม.' (อังกฤษ)")
check(ux.correct_unit('ตรม.') is None, "ตรม. เป็นหน่วยมาตรฐาน → ไม่ฟ้อง")
check(ux.extract_area_hint('กระเบื้องปูพื้น 1.2 ตรม.') == 'ตรม.', "ดึง hint พื้นที่จากชื่อได้")
check(ux.extract_area_hint('กระจก 2 ตร.ม.') == 'ตรม.', "ดึง hint พื้นที่ 'ตร.ม.' ได้")
check(ux.extract_area_hint('สีน้ำมัน 5 ลิตร') == '', "ไม่มีพื้นที่ในชื่อ → hint ว่าง")


# ════════════════════════ (3) ปี๊ป / แกลอน / แกนลอน ════════════════════════
print("\n[3] ปี๊ป / แกลอน / แกนลอน ถูกจับ + แนะนำรูปมาตรฐาน")
cases = {'ปี๊ป': 'ปี๊บ', 'แกลอน': 'แกลลอน', 'แกนลอน': 'แกลลอน'}
for wrong, right in cases.items():
    r = ux.correct_unit(wrong)
    check(r is not None and r['suggestion'] == right,
          f"{wrong} → แนะนำ {right} (ได้ {r['suggestion'] if r else None})")


# ════════════════════════ (2) fuzzy ครอบหน่วยผิดเพิ่ม ════════════════════════
print("\n[2] fuzzy/map ครอบหน่วยผิดให้ครบขึ้น")
for wrong in ['กระปอง', 'ตาราเมตร', 'มั้วน']:
    check(ux.correct_unit(wrong) is not None, f"{wrong} ถูกจับ (map)")
# fuzzy fallback: รูปเพี้ยนที่ไม่อยู่ใน _TYPO_MAP ตรง ๆ แต่ใกล้ target (พิสูจน์ fuzzy ทำงาน)
assert 'แกล่อน' not in ux._TYPO_MAP, "ต้องไม่อยู่ใน map เพื่อพิสูจน์เส้นทาง fuzzy"
fz = ux.correct_unit('แกล่อน')
check(fz is not None and fz['suggestion'] == 'แกลลอน' and fz['method'] == 'fuzzy',
      f"แกล่อน → fuzzy แนะนำ แกลลอน (ได้ {fz if fz else None})")


# ════════════════════════ กัน false-positive (สำคัญสุด) ════════════════════════
print("\n[FP] หน่วยมาตรฐานต้องไม่ถูกฟ้อง (ไม่กระทบระบบเดิม)")
valid_units = ['เส้น', 'ท่อน', 'อัน', 'ตัว', 'ลูก', 'ก้อน', 'ถุง', 'กระสอบ',
               'คิว', 'เมตร', 'ม.', 'กก.', 'kg', 'ชุด', 'set', 'ตรม.', 'ปี๊บ',
               'แกลลอน', 'กระป๋อง', 'ถัง', 'งาน', 'ตัน', 'ต้น', 'ใบ', 'แผ่น',
               'ม้วน', 'กล่อง', 'ลัง', 'pcs', 'ลิตร', 'โหล', 'คู่', 'pair']
fp = [u for u in valid_units if ux.correct_unit(u) is not None]
check(not fp, f"หน่วยมาตรฐาน {len(valid_units)} ตัว ไม่ถูกฟ้องเลย (FP: {fp})")


# ════════════════════════ (4) ไฟล์เดียวปนไทย+อังกฤษ ════════════════════════
print("\n[4] ไฟล์เดียวปนหน่วยไทย+อังกฤษ (ความหมายเดียวกัน)")
bills_mix = [
    {'file': 'A.xlsx', 'sheet': '1',
     'items': [{'seq': 1, 'name': 'ปูน', 'unit': 'กก.'},
               {'seq': 2, 'name': 'cement', 'unit': 'kg'}]},
    {'file': 'A.xlsx', 'sheet': '2',
     'items': [{'seq': 1, 'name': 'กระเบื้อง', 'unit': 'ตรม.'},
               {'seq': 2, 'name': 'tile', 'unit': 'sqm'}]},
    {'file': 'B.xlsx', 'sheet': '1',
     'items': [{'seq': 1, 'name': 'เหล็ก', 'unit': 'เส้น'}]},
]
mixes = ux.detect_file_unit_language_mix(bills_mix)
mix_files = {d['file'] for d in mixes}
check('A.xlsx' in mix_files, "A.xlsx (กก./kg + ตรม./sqm) ถูกตรวจว่าปนภาษา")
check('B.xlsx' not in mix_files, "B.xlsx (ไทยล้วน) ไม่ถูกตรวจว่าปนภาษา (ไม่ false-positive)")
fams = {f['family'] for d in mixes if d['file'] == 'A.xlsx' for f in d['mixed_families']}
check({'กก.', 'ตรม.'} <= fams, f"A.xlsx ระบุตระกูลปนภาษาครบ (กก., ตรม.) ได้ {sorted(fams)}")

# สรุปหน่วยต่อไฟล์ — ตรม. ต้องปรากฏ (อาการ 1: 'ไม่ขึ้น')
summ = ux.summarize_units_by_file(bills_mix)
check('ตรม.' in summ.get('A.xlsx', {}), "สรุปหน่วยต่อไฟล์: 'ตรม.' ปรากฏ (แก้อาการ 'ไม่ขึ้น')")


# ════════════════════════ ผูกกฎ ITM019 เข้า engine จริง ════════════════════════
print("\n[ENGINE] ITM019 ผูกใน RULES + run_rules เรียกได้ + ฟ้องถูกจังหวะ")
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
from rules_engine import RULES, run_rules, r_itm019
from analytics import build_unit_index
from golden_snapshot import MASTER

check('ITM019' in RULES, "ITM019 อยู่ใน RULES registry")
check(RULES['ITM019']['check'] is r_itm019, "ITM019.check ชี้ไป r_itm019")

# บิลที่มีหน่วยสะกดผิด → ITM019 ต้องฟ้อง
def issues_of(bill):
    bb = copy.deepcopy(bill)
    file_info = {'month': 5, 'month_end': None, 'year': 2025}
    ui = build_unit_index([bb])
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(bb, MASTER, file_info, unit_index=ui, all_bills_ref=[bb])
    return {iss['code'] for iss in bb.get('issues', [])}

bad_unit_bill = {
    'company': 'บริษัท ทดสอบ จำกัด', 'company_raw': 'บริษัท ทดสอบ จำกัด',
    'tax_id': '', 'tax_id_raw': '', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
    'iv_number': 'IV001', 'iv_number_raw': 'IV001', 'iv_date': None, 'iv_date_str': '',
    'address': '', 'subtotal': 800.0, 'vat': 56.0, 'total': 856.0,
    'sheet': '1', 'file': 'T.xlsx', 'block_idx': 0, 'issues': [],
    'items': [{'seq': 1, 'name': 'สีรองพื้น', 'name_raw': 'สีรองพื้น',
               'qty': 1.0, 'unit': 'แกลอน', 'price': 800.0, 'amount': 800.0}],
}
codes_bad = issues_of(bad_unit_bill)
check('ITM019' in codes_bad, "บิลหน่วย 'แกลอน' → ITM019 ฟ้อง")

# บิลหน่วยถูก → ITM019 เงียบ
ok_unit_bill = copy.deepcopy(bad_unit_bill)
ok_unit_bill['items'][0]['unit'] = 'แกลลอน'
codes_ok = issues_of(ok_unit_bill)
check('ITM019' not in codes_ok, "บิลหน่วย 'แกลลอน' (ถูก) → ITM019 เงียบ (ไม่ FP)")

# run_rules ต้องไม่ throw เมื่อมี ITM019
threw = False
try:
    issues_of(bad_unit_bill)
except Exception:
    threw = True
check(not threw, "run_rules ไม่ throw เมื่อ ITM019 เปิดใช้งาน")


# ════════════════════════ ส่วน Notepad ════════════════════════
print("\n[NOTEPAD] _render_unit_consistency ผลิตคำเตือนครบ")
from agents.notepad_report import _render_unit_consistency
bills_np = bills_mix + [bad_unit_bill]
text = "\n".join(_render_unit_consistency(bills_np))
check('Unit Consistency' in text, "มีหัวข้อ Unit Consistency")
check('ปนภาษาไทย+อังกฤษ' in text and 'A.xlsx' in text, "มีคำเตือนปนภาษา + ระบุไฟล์")
check('แกลลอน' in text, "มีคำแนะนำหน่วยสะกดผิด (แกลลอน) ใน Notepad")
check('ตรม.' in text, "มี 'ตรม.' ปรากฏในรายงาน Notepad (อาการ 1)")


# ════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
if FAIL:
    print(f"UNIT-EXT: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    print("=" * 64)
    sys.exit(1)
print(f"UNIT-EXT: ผ่าน {PASS} / ล้มเหลว 0")
print("=" * 64)
print("RESULT: ✅ ตรวจจับหน่วยเพิ่มครบ 4 อาการ + ไม่ FP + ไม่กระทบ logic เดิม")
sys.exit(0)
