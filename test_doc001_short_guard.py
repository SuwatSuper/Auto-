# -*- coding: utf-8 -*-
"""test_doc001_short_guard.py — TRIPWIRE: ADR-058 DOC001 SHORT-format false-positive guard

แทน coverage ของ fixture เดิม (269ddaed → b5c415bb) ที่หลัง rebaseline ไม่มี DOC001 SHORT แล้ว.
ตรึงพฤติกรรม 2-signal guard ของ r_doc001 (rules_engine_rules_a) ผ่าน run_rules (integration —
ทดสอบทั้งสาย all_bills_for_iv_check plumbing เหมือนที่ engine จริงเรียก):

  (P)  positive : ไฟล์ตั้งชื่อชีต=วันจริง (≥2 ชีตเลขล้วนตรงวัน) + ชีตที่ผิดวัน ไม่มี copy-sibling
                  → DOC001 ฟ้อง (anomaly จริง เช่น SHS_68_02 "6")
  (N1) negative : ชีตเลขล้วนมี Excel copy-sibling "N (k)" (เทมเพลตก๊อป เช่น TNT_69_03 "2")
                  → ไม่ฟ้อง แม้ไฟล์จะมี corroboration
  (N2) negative : ชีตเลขล้วนเดี่ยว ไม่มีชีตอื่นยืนยันวัน (lone-index เช่น TSH_69_039 "1")
                  → ไม่ฟ้อง

guard "ระงับ" อย่างเดียว — ไม่เพิ่ม flag ใหม่. advisory correctness ของ DOC001 SHORT producer.
    PYTHONHASHSEED=0 PUOPUY_ALLOW_VERSION_MISMATCH=1 python3 test_doc001_short_guard.py
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

from rules_engine import run_rules

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def _bill(file, sheet, day, iv):
    """บิลสังเคราะห์ขั้นต่ำ — สนใจแค่ DOC001 (sheet vs iv_date.day)."""
    return {
        'company': 'บริษัท ทดสอบ จำกัด', 'company_raw': 'บริษัท ทดสอบ จำกัด',
        'tax_id': '0105500000000', 'tax_id_raw': '0105500000000',
        'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        'iv_number': iv, 'iv_number_raw': iv,
        'iv_date': datetime.date(2026, 3, day),
        'iv_date_str': f'{day:02d}/03/2026',
        'address': '', 'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
        'sheet': sheet, 'file': file, 'block_idx': 0, 'issues': [],
        'items': [{'seq': 1, 'name': 'เหล็กเส้น', 'name_raw': 'เหล็กเส้น',
                   'qty': 10.0, 'unit': 'เส้น', 'price': 100.0, 'amount': 1000.0}],
    }


# ── (P) ไฟล์ day-naming จริง: ชีต "5"(วัน5) "8"(วัน8) ยืนยัน → ชีต "6"(วัน7) = anomaly ฟ้อง ──
F_POS = 'TEST_POS.xls'
pos_bills = [
    _bill(F_POS, '5', 5, 'IVP0001'),     # ตรงวัน (corroborate)
    _bill(F_POS, '8', 8, 'IVP0002'),     # ตรงวัน (corroborate)
    _bill(F_POS, '6', 7, 'IVP0003'),     # ผิดวัน + ไม่มี copy-sibling → ควรฟ้อง
]

# ── (N1) เทมเพลตก๊อป: ชีต "3"(วัน3) "9"(วัน9) ยืนยัน → ชีต "2"(วัน11) มี "2 (2)"/"2 (3)" → ไม่ฟ้อง ──
F_TPL = 'TEST_TPL.xls'
tpl_bills = [
    _bill(F_TPL, '3', 3, 'IVT0001'),     # ตรงวัน (corroborate)
    _bill(F_TPL, '9', 9, 'IVT0002'),     # ตรงวัน (corroborate)
    _bill(F_TPL, '2', 11, 'IVT0003'),    # ผิดวัน แต่มี copy-sibling → ไม่ควรฟ้อง
    _bill(F_TPL, '2 (2)', 11, 'IVT0004'),
    _bill(F_TPL, '2 (3)', 11, 'IVT0005'),
]

# ── (N2) บิลเดี่ยว: ชีต "1"(วัน4) ไฟล์เดียวไม่มีชีตอื่นยืนยัน → ไม่ฟ้อง ──
F_LONE = 'TEST_LONE.xls'
lone_bills = [
    _bill(F_LONE, '1', 4, 'IVL0001'),    # ผิดวัน แต่ไม่มี corroboration → ไม่ควรฟ้อง
]

ALL = pos_bills + tpl_bills + lone_bills   # รวมทุกไฟล์ (guard กรอง same-file เอง = ทดสอบ file-filter ด้วย)


def doc001_codes(bill):
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(bill, {}, {'month': 3, 'month_end': None, 'year': 2026},
                  unit_index={}, all_bills_ref=ALL)
    return [i['code'] for i in bill['issues'] if i['code'] == 'DOC001']


print("\n[P] day-naming จริง + ชีตผิดวันไม่มี copy-sibling → DOC001 ฟ้อง (true positive)")
got = doc001_codes(pos_bills[2])
check('DOC001' in got, f"ชีต '6' วัน 7 (ไฟล์มี '5','8' ยืนยัน) → DOC001 ฟ้อง (got {got})")

print("\n[P-control] ชีตที่ตรงวันในไฟล์เดียวกัน → ไม่ฟ้อง")
got = doc001_codes(pos_bills[0])
check('DOC001' not in got, f"ชีต '5' วัน 5 → ไม่ฟ้อง (got {got})")

print("\n[N1] เทมเพลตก๊อป (ชีต '2' มี '2 (2)'/'2 (3)') → ไม่ฟ้อง แม้มี corroboration")
got = doc001_codes(tpl_bills[2])
check('DOC001' not in got, f"ชีต '2' วัน 11 + copy-sibling → ไม่ฟ้อง (got {got})")

print("\n[N2] บิลเดี่ยว ไม่มีชีตอื่นยืนยันวัน (lone-index) → ไม่ฟ้อง")
got = doc001_codes(lone_bills[0])
check('DOC001' not in got, f"ชีต '1' วัน 4 (ไฟล์ชีตเดียว) → ไม่ฟ้อง (got {got})")

print("\n" + "=" * 60)
if FAIL:
    print(f"RESULT: ❌ FAIL {len(FAIL)} เคส:")
    for f in FAIL:
        print(f"   - {f}")
    sys.exit(1)
print(f"RESULT: ✅ PASS {PASS}/{PASS} — ADR-058 SHORT guard ตรึงครบ (P + control + N1 + N2)")
sys.exit(0)
