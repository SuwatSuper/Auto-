# -*- coding: utf-8 -*-
"""test_recheck_20260621.py — ตรึงการแก้จากรอบรีเช็คทั้งระบบ 2026-06-21.

รันแบบ standalone:  python3 test_recheck_20260621.py   (exit 0 = ผ่าน)

ครอบ 2 การแก้ที่ยืนยันแล้วว่า golden-neutral (real_cases digest 95852c68… + fixture
b5c415bb… ไม่ขยับ, parallel==serial ตรงเป๊ะ):
  • P-MED2 (parser_p2._pb_extract_items): แถวสรุป/ยอดรวม/ภาษี (label อยู่คอลัมน์ชื่อ + blank seq)
      ต้องไม่ถูกนับเป็น "รายการสินค้า" และไม่ฟ้อง ITM016 หลอก — แต่รายการจริงที่ลืมใส่เลขลำดับ
      ต้องยังถูกจับเหมือนเดิม (ไม่สร้าง false-negative).
  • V-F3 (validators.apply_sheet_date_crosscheck): ชื่อชีตที่ไม่ใช่ "วัน.เดือน" จริง (วัน>31 / เดือน>12
      / เป็น 0 เช่น "5.2025"=วัน.ปี, "5.13", "0.5") ต้องไม่ฟ้อง DOC001 หลอก — แต่ "วัน.เดือน" จริงที่
      ไม่ตรงบิล (เช่น "5.6" กับบิล 05/05) ต้องยังฟ้อง DOC001 เหมือนเดิม.
"""
import os
import sys

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
os.environ.setdefault("PUOPUY_ALLOW_VERSION_MISMATCH", "1")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from datetime import datetime

_passed = 0
_failed = 0


def check(cond, label):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {label}")
    else:
        _failed += 1
        print(f"  ❌ {label}")


# ── P-MED2 ───────────────────────────────────────────────────────────────────
print("\n[P-MED2] แถวสรุป/ยอดรวม/ภาษี (blank seq) ไม่กลายเป็นรายการสินค้า + ไม่ฟ้อง ITM016")
import parser_p2

# บล็อกที่มี 2 รายการจริง + 2 แถวสรุป (ลำดับว่าง, label อยู่คอลัมน์ชื่อ, ยอดใน amt_col)
_block = pd.DataFrame({
    0: [1, 2, "", ""],
    1: ["เหล็กเส้น", "ปูนซีเมนต์", "รวมเป็นเงิน", "จำนวนเงินรวมทั้งสิ้น"],
    2: [2, 5, "", ""],
    3: ["เส้น", "ถุง", "", ""],
    4: [250.0, 100.0, "", ""],
    5: [500.0, 500.0, 1000.0, 1070.0],
})
_res = {"items": [], "issues": []}
parser_p2._pb_extract_items(_res, _block, (0, 1, 2, 3, 4, 5))
_names = [i.get("name") for i in _res["items"]]
_itm016 = sum(1 for x in _res["issues"] if x.get("code") == "ITM016")
check("รวมเป็นเงิน" not in _names and "จำนวนเงินรวมทั้งสิ้น" not in _names,
      "แถว 'รวมเป็นเงิน'/'จำนวนเงินรวมทั้งสิ้น' ไม่ถูกนับเป็นรายการ")
check(_itm016 == 0, "ไม่มี ITM016 หลอกจากแถวสรุป")
check(_names == ["เหล็กเส้น", "ปูนซีเมนต์"], "รายการจริง 2 ตัวยังครบ")

# control: รายการจริงที่ลืมใส่เลขลำดับ (blank seq) ต้องยังถูกจับ + ยังฟ้อง ITM016
_block2 = pd.DataFrame({
    0: [1, "", ""],
    1: ["เหล็กเส้น", "ลวดผูกเหล็ก", "รวมเป็นเงิน"],
    2: [2, 3, ""],
    3: ["เส้น", "กก", ""],
    4: [250.0, 40.0, ""],
    5: [500.0, 120.0, 620.0],
})
_res2 = {"items": [], "issues": []}
parser_p2._pb_extract_items(_res2, _block2, (0, 1, 2, 3, 4, 5))
_names2 = [i.get("name") for i in _res2["items"]]
check("ลวดผูกเหล็ก" in _names2, "รายการจริงที่ลืมเลขลำดับ ('ลวดผูกเหล็ก') ยังถูกจับ (ไม่ false-negative)")
check(any(x.get("code") == "ITM016" for x in _res2["issues"]),
      "ITM016 ยังฟ้องแถวที่ลืมเลขลำดับจริง")


# ── V-F3 ─────────────────────────────────────────────────────────────────────
print("\n[V-F3] ชื่อชีตที่ไม่ใช่ 'วัน.เดือน' จริง ไม่ฟ้อง DOC001 หลอก; ของจริงยังฟ้อง")
import validators


def _doc001(sheet):
    b = {"sheet": sheet, "iv_date": datetime(2025, 5, 5), "filepath": "f", "issues": []}
    validators.apply_sheet_date_crosscheck([b])
    return any(i["code"] == "DOC001" for i in b["issues"])


check(_doc001("5.2025") is False, "ชีต '5.2025' (วัน.ปี → เดือน=20) ไม่ฟ้อง DOC001")
check(_doc001("5.13") is False, "ชีต '5.13' (เดือน 13 เป็นไปไม่ได้) ไม่ฟ้อง DOC001")
check(_doc001("0.5") is False, "ชีต '0.5' (วัน 0 เป็นไปไม่ได้) ไม่ฟ้อง DOC001")
check(_doc001("5.6") is True, "ชีต '5.6' (วัน.เดือนจริง) ≠ บิล 05/05 → ยังฟ้อง DOC001")
check(_doc001("5.5") is False, "ชีต '5.5' = บิล 05/05 → ไม่ฟ้อง (ถูกต้อง)")


print("\n" + "=" * 64)
print(f"RECHECK 2026-06-21: ผ่าน {_passed} / ล้มเหลว {_failed}")
print("=" * 64)
if _failed:
    print("RESULT: ❌ พบ regression")
    sys.exit(1)
print("RESULT: ✅ ทุกการแก้ถูกตรึงครบ")
sys.exit(0)
