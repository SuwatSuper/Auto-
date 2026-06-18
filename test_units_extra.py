# -*- coding: utf-8 -*-
"""test_units_extra.py — [OBJ-1D ต่อยอด] ดัน coverage ของ puopuy_units.py ให้ ≥90% (→ ~98%)

ปิดบรรทัดที่เหลือ 5 บรรทัด (45-46, 122, 129, 144) ด้วยการเรียกฟังก์ชันบริสุทธิ์ตรง ๆ:
  • _D            : กิ่ง int/float ที่ str() ออกมาแปลงเป็น Decimal ไม่ได้ → None  (45-46)
  • _unit_canon   : input ว่าง → ''                                            (122)
  • _unit_canon   : หน่วยมีข้อความห้อย ('กก. (โดยประมาณ)') → จับด้วย substring   (129)
  • extract_unit_hint : ชื่อว่าง → ''                                          (144)

ทุกฟังก์ชันเป็น leaf utility (pure) — ไม่แตะผลหลัก/ไม่กระทบ golden hash.
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_units_extra.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings
from decimal import Decimal

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import puopuy_units as U

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


print("\n[U1] _D — int/float ที่ str() แปลงเป็น Decimal ไม่ได้ → None (บรรทัด 45-46)")


class WeirdFloat(float):
    """float แท้ ๆ (ผ่าน isinstance float) แต่ str() คืนขยะ → Decimal(str(x)) ระเบิด.

    จำลองชนิดตัวเลขเพี้ยน (เช่น proxy/▸numpy ที่ override __str__) เพื่อพิสูจน์ว่า
    _D ไม่โยน exception ออกไปให้ผู้เรียก แต่กลืนเป็น None ตาม contract.
    """
    def __str__(self):
        return 'ขยะที่ไม่ใช่ตัวเลข'


# float subclass → เข้ากิ่ง isinstance(x,(int,float)) → try Decimal(str(x)) → InvalidOperation
wf = WeirdFloat(3.14)
check(isinstance(wf, float), "WeirdFloat ยังเป็น float (เข้ากิ่ง int/float)")
try:
    Decimal(str(wf))
    _raises = False
except Exception:
    _raises = True
check(_raises, "Decimal(str(WeirdFloat)) ต้องโยน exception (เงื่อนไขของกิ่งนี้)")
check(U._D(wf) is None, "_D(WeirdFloat) → None (กลืน exception ไม่โยนต่อ)")

# กัน regression: float ปกติยังแปลงได้ตามเดิม
check(U._D(3.14) == Decimal('3.14'), "_D(3.14) → Decimal('3.14') (ของเดิมไม่พัง)")
check(U._D(0) == Decimal('0'), "_D(0) → Decimal('0')")


print("\n[U2] _unit_canon — input ว่าง → '' (บรรทัด 122)")
check(U._unit_canon('') == '', "_unit_canon('') → ''")
check(U._unit_canon(None) == '', "_unit_canon(None) → ''")


print("\n[U3] _unit_canon — หน่วยมีข้อความห้อย → จับด้วย substring (บรรทัด 129)")
# 'กก. (โดยประมาณ)' ไม่ตรง key ตรง ๆ แต่มี 'กก.' เป็น substring → ต้องยุบเป็นตัวแทนกลุ่มเดียวกับ 'กก.'
canon_plain = U._unit_canon('กก.')
canon_suffix = U._unit_canon('กก. (โดยประมาณ)')
check(canon_suffix == canon_plain,
      f"_unit_canon('กก. (โดยประมาณ)') == _unit_canon('กก.')  (ได้ {canon_suffix!r} vs {canon_plain!r})")
check(canon_suffix != 'กก. (โดยประมาณ)',
      "ต้องยุบเป็นตัวแทนกลุ่ม ไม่ใช่คืน string เดิม (พิสูจน์ว่าเข้ากิ่ง substring)")

# กันfalse-positive: หน่วยที่ไม่อยู่กลุ่มไหนเลย → คืนตัวเอง (กิ่ง return s ปลายฟังก์ชัน)
check(U._unit_canon('หน่วยประหลาดXYZ') == 'หน่วยประหลาดXYZ',
      "_unit_canon(หน่วยนอกกลุ่ม) → คืนค่าเดิม")


print("\n[U4] extract_unit_hint — ชื่อว่าง → '' (บรรทัด 144)")
check(U.extract_unit_hint('') == '', "extract_unit_hint('') → ''")
check(U.extract_unit_hint(None) == '', "extract_unit_hint(None) → ''")

# กัน regression: ชื่อที่มี spec จริงยัง extract ได้
check(U.extract_unit_hint('น้ำมันเครื่อง 5 ลิตร') == 'ลิตร',
      "extract_unit_hint('...5 ลิตร') → 'ลิตร' (ของเดิมไม่พัง)")


print("\n" + "=" * 64)
if FAIL:
    print(f"UNITS EXTRA: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    print("=" * 64)
    sys.exit(1)
else:
    print(f"UNITS EXTRA: ผ่าน {PASS} / ล้มเหลว 0")
    print("=" * 64)
    print("RESULT: ✅ leaf utility ของ puopuy_units.py ครบกิ่ง + ไม่กระทบ golden hash")
    sys.exit(0)
