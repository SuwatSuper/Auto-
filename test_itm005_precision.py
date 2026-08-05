# -*- coding: utf-8 -*-
"""test_itm005_precision.py — RULE-LEVEL characterization ของ ITM005 หลัง F1 (ADR-087).

เจตนา (สัญญา §4 "ทุก rule ที่แตะ → characterization ครอบ positive+negative"):
  ล็อก "ความแม่นระดับสไนเปอร์" ของ r_itm005 ที่ขอบกฎจริง (ไม่ใช่แค่ helper _kw_in_name):
    • NEGATIVE (ตัด false-positive): สินค้า "ไม่ใช่สี" + คำบอกสี (สวิตช์/สายไฟ/กระเบื้อง/
      ซิลิโคน/ข้อต่อ … สีดำ/สีขาว/สีน้ำตาล/สีเรียบ) → ต้อง "ไม่ฟ้อง" ITM005.
    • POSITIVE (recall คงเดิม): สีจริง (สีน้ำมัน/สีรองพื้น/สีน้ำ/สีอะคริลิค/สีสเปรย์) ที่หน่วยผิด
      จริง → ต้อง "ยังฟ้อง". และสีจริงที่หน่วยถูก → ไม่ฟ้อง (control).
  ทั้งหมดเป็น pure check (สร้าง bill สังเคราะห์ → เรียก r_itm005 ตรง) — ไม่แตะ golden hash.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_itm005_precision.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import rules_engine as R

PASS, FAIL = 0, []


def _check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


M = {'name': 'บริษัท ทดสอบ จำกัด', 'name_alt': '', 'tax_id': '0105566206726',
     'branch': 'สำนักงานใหญ่', 'address': '', 'iv_prefix': 'IV'}


def ctx(**over):
    c = {'sheet_name': '1', 'target_month': None, 'target_month_end': None,
         'all_masters': {'ทดสอบ': M}, 'unit_index': None, 'all_bills_for_iv_check': []}
    c.update(over)
    return c


def item(seq, name, unit):
    return {'seq': seq, 'name': name, 'name_raw': name, 'qty': 1,
            'unit': unit, 'price': 100, 'amount': 100}


def itm005(name, unit):
    return R.r_itm005({'items': [item(1, name, unit)]}, M, ctx())


def no_flag(name, unit, label):
    out = itm005(name, unit)
    _check(out == [], label + ('' if out == [] else f"  (ควรเงียบ แต่ได้ {out})"))


def flags(name, unit, label):
    out = itm005(name, unit)
    _check(bool(out), label + ('' if out else "  (ควรฟ้อง แต่เงียบ)"))


print("ITM005 PRECISION — characterization (ADR-087 F1 sniper)")
print()
print("=== NEGATIVE: สินค้าไม่ใช่สี + คำบอกสี → ต้องไม่ฟ้อง (ตัด false-positive) ===")
no_flag('BLสวิตซ์ทางเดียว 3 ปุ่ม LM003OB สีดำ', 'ชิ้น', 'สวิตช์ + สีดำ → ไม่ฟ้อง')
no_flag('YAZAKI THW 1 x 2.5 สีน้ำตาล', 'ขด', 'สายไฟ THW + สีน้ำตาล → ไม่ฟ้อง')
no_flag('YAZAKI THW 1 x 2.5 สีเขียวคาดเหลือง', 'ขด', 'สายไฟ + สีเขียว → ไม่ฟ้อง')
no_flag('กระเบื้องเคลือบบุผนัง สีเรียบ 8x8', 'ตรม.', 'กระเบื้อง + สีเรียบ → ไม่ฟ้อง')
no_flag('กาวซิลิโคน TOA ซีลแลนท์ สีขาวขุ่น 280 ML', 'หลอด', 'ซิลิโคน + สีขาว → ไม่ฟ้อง')
no_flag('ข้อต่อ MC4 SUNTREE สีดำ', 'ชิ้น', 'ข้อต่อ MC4 + สีดำ → ไม่ฟ้อง')
no_flag('เกรียงโบกปูน ผิวหนา พลาสติก สีดำ', 'ชิ้น', 'เกรียง + สีดำ → ไม่ฟ้อง')
no_flag('สีน้ำเงิน', 'อัน', "'สีน้ำเงิน' (สีล้วน) → ไม่ฟ้อง")

print()
print("=== POSITIVE: สีจริง + หน่วยผิดจริง → ต้องยังฟ้อง (recall ไม่ตก) ===")
flags('สีน้ำมัน TOA G252', 'เส้น', 'สีน้ำมัน + เส้น (ผิด) → ฟ้อง')
flags('สีรองพื้น เบเยอร์', 'ม้วน', 'สีรองพื้น + ม้วน (ผิด) → ฟ้อง')
flags('สีน้ำ TOA', 'กก.', 'สีน้ำ + กก. (ผิด) → ฟ้อง [จงใจไม่กัน สีน้ำ]')
flags('สีอะคริลิค 75ML', 'เส้น', 'สีอะคริลิค + เส้น (ผิด) → ฟ้อง')
flags('สีสเปรย์ TOA 29', 'ชิ้น', 'สีสเปรย์ (สีจริง) + ชิ้น → ฟ้อง [ไม่ over-suppress]')

print()
print("=== CONTROL: สีจริง + หน่วยถูก/พ้อง → ไม่ฟ้อง ===")
no_flag('สีน้ำมัน TOA G252', 'แกลลอน', 'สีน้ำมัน + แกลลอน (ถูก) → ไม่ฟ้อง')
no_flag('สีรองพื้น เบเยอร์', 'ถัง', 'สีรองพื้น + ถัง (พ้องแกลลอน) → ไม่ฟ้อง')

print()
print("=" * 64)
if FAIL:
    print(f"RESULT: ❌ FAIL ({len(FAIL)} จุด) — ความแม่น ITM005 (ADR-087) เปลี่ยนจากที่ล็อก")
    for f in FAIL:
        print("   -", f)
    sys.exit(1)
print(f"RESULT: ✅ PASS ({PASS} เคส) — ITM005 sniper: ตัด FP ครบ + recall คงเดิม (ADR-087)")
sys.exit(0)
