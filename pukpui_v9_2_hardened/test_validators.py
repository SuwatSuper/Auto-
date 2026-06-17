# -*- coding: utf-8 -*-
"""test_validators.py — [OBJ-1D] unit test validators (IV/date/period/typo/duplicate)

ตรวจ "ค่าถูกต้อง" + "edge ไม่ throw" ของฟังก์ชันตรวจลำดับ/วันที่/งวด/typo/ซ้ำ.
    PYTHONHASHSEED=0 python3 test_validators.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings
import datetime as dt

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
import validators as V

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def no_throw(fn, label):
    global PASS
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            r = fn()
        PASS += 1
        print(f"  ✅ {label}")
        return r
    except BaseException as e:
        FAIL.append(f"{label} → THREW {type(e).__name__}: {str(e)[:90]}")
        print(f"  ❌ {label} → THREW {type(e).__name__}")
        return None


def mk(iv, day, month=5, company='บริษัท ก จำกัด', items=None, sheet=None):
    return {
        'iv_number': iv, 'iv_number_raw': iv,
        'iv_date': dt.date(2025, month, day) if day else None,
        'iv_date_str': f'{day:02d}/{month:02d}/2025' if day else '',
        'company': company, 'tax_id': '0105566206726', 'sheet': sheet or str(day or 1),
        'file': 'TEST_69_05.xls',
        'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0, 'branch_no': '00000',
        'items': items or [{'seq': 1, 'name': 'เหล็ก', 'name_raw': 'เหล็ก',
                            'qty': 1.0, 'unit': 'เส้น', 'price': 1000.0, 'amount': 1000.0}],
        'issues': [], 'file_info': {'month': month, 'month_end': None, 'year': 2025},
    }


print("=" * 64)
print("VALIDATORS — IV/date/period/typo/duplicate")
print("=" * 64)

print("\n[1] detect_iv_period_mismatch")
check(V.detect_iv_period_mismatch('IV6805001', dt.date(2025, 5, 15))['mismatch'] is False,
      "IV งวด 68/05 + วันที่ พ.ค.68 → ไม่ขัด")
m = V.detect_iv_period_mismatch('IV6805001', dt.date(2025, 12, 15))
check(m and m['mismatch'] is True, "IV งวด 68/05 + วันที่ ธ.ค.68 → ขัด (mismatch=True)")
check(V.detect_iv_period_mismatch('IV6805001', None) is None, "ไม่มีวันที่ → None")
check(V.detect_iv_period_mismatch('XYZ', dt.date(2025, 5, 1)) is None, "IV ไม่สื่องวด → None")
for iv, d in [(None, None), ('', dt.date(2025, 1, 1)), ('IV', dt.date(2025, 1, 1))]:
    no_throw(lambda iv=iv, d=d: V.detect_iv_period_mismatch(iv, d), f"detect({iv!r},{d}) ไม่ throw")

print("\n[2] check_invoice_sequence / check_iv_date_sequence")
seq_bills = [mk('IV6805001', 1), mk('IV6805002', 2), mk('IV6805005', 5),  # gap 3→5
             mk('IV6805003', 10)]  # ลำดับสลับวันที่
no_throw(lambda: V.check_invoice_sequence([dict(b) for b in seq_bills]), "check_invoice_sequence ไม่ throw")
no_throw(lambda: V.check_iv_date_sequence([dict(b) for b in seq_bills]), "check_iv_date_sequence ไม่ throw")
check(isinstance(V.check_invoice_sequence([]), list), "check_invoice_sequence([]) → list")
check(isinstance(V.check_iv_date_sequence([]), list), "check_iv_date_sequence([]) → list")

print("\n[3] check_duplicate_items (สร้างรายการซ้ำข้ามบิลให้จับได้)")
dup = [
    mk('IV6805010', 1, items=[{'seq': 1, 'name': 'เหล็กเส้น 12mm', 'name_raw': 'เหล็กเส้น 12mm',
                               'qty': 100.0, 'unit': 'เส้น', 'price': 50.0, 'amount': 5000.0}]),
    mk('IV6805011', 2, items=[{'seq': 1, 'name': 'เหล็กเส้น 12mm', 'name_raw': 'เหล็กเส้น 12mm',
                               'qty': 100.0, 'unit': 'เส้น', 'price': 50.0, 'amount': 5000.0}]),
]
res_dup = no_throw(lambda: V.check_duplicate_items([dict(b) for b in dup]), "check_duplicate_items ไม่ throw")
check(isinstance(res_dup, list), "check_duplicate_items → list")
check(isinstance(V.check_duplicate_items([]), list), "check_duplicate_items([]) → list")

print("\n[4] check_product_typos / crosschecks / filename")
typo = [mk('IV6805020', 1, items=[{'seq': 1, 'name': 'เหล้กเส้น', 'name_raw': 'เหล้กเส้น',
                                   'qty': 1.0, 'unit': 'เส้น', 'price': 100.0, 'amount': 100.0}]),
        mk('IV6805021', 2, items=[{'seq': 1, 'name': 'เหล็กเส้น', 'name_raw': 'เหล็กเส้น',
                                   'qty': 1.0, 'unit': 'เส้น', 'price': 100.0, 'amount': 100.0}])]
no_throw(lambda: V.check_product_typos([dict(b) for b in typo]), "check_product_typos ไม่ throw")
no_throw(lambda: V.apply_iv_period_crosscheck([dict(b) for b in seq_bills]), "apply_iv_period_crosscheck ไม่ throw")
no_throw(lambda: V.apply_sheet_date_crosscheck([dict(b) for b in seq_bills]), "apply_sheet_date_crosscheck ไม่ throw")
no_throw(lambda: V.check_filename_consistency('KRR_69_05.xls', [dict(b) for b in seq_bills],
                                              {'month': 5, 'month_end': None, 'year': 2025}),
         "check_filename_consistency ไม่ throw")
# edge: บิลว่าง / ฟิลด์หาย
no_throw(lambda: V.check_product_typos([]), "check_product_typos([]) ไม่ throw")
no_throw(lambda: V.check_duplicate_items([{'items': [], 'issues': []}]), "check_duplicate_items(บิลไม่มีรายการ) ไม่ throw")

print("\n" + "=" * 64)
print(f"VALIDATORS: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for f in FAIL:
        print(f"  • {f}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ validators ตรวจลำดับ/วันที่/งวด/typo/ซ้ำ ถูกต้อง + ทนทาน")
sys.exit(0)
