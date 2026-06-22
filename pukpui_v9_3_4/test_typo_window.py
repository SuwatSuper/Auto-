# -*- coding: utf-8 -*-
"""test_typo_window.py — ครอบ sliding-window path ของ check_product_typos (Scalability)

บริบท: check_product_typos มี 2 เส้น — ≤500 ชื่อ ใช้ rapidfuzz.cdist (O(n²) เต็ม) ;
>500 ชื่อ สลับเป็น sliding-window (จำกัดคู่เทียบด้วยช่วงความยาว) เพื่อกัน O(n²) บนข้อมูลใหญ่.
เดิมเส้น window แทบไม่ถูกครอบในเทส (fixture เล็ก) → เทสนี้บังคับ >500 ชื่อ + ฝัง typo คู่หนึ่ง
แล้วยืนยันว่า window path ยัง "จับ typo ที่ควรจับ" ได้จริง (correctness ใต้ scale).

self-contained + deterministic: สร้างชื่อสังเคราะห์เอง (ตัวเติมมีเลขกำกับ → ต่างกลุ่ม spec
จึงไม่รบกวน, คู่ที่ฝังไม่มีเลข → ถูกนำมาเทียบจริง).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validators import check_product_typos
from config import CFG

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


# คู่ typo ที่ฝัง (ไม่มีตัวเลข → ไม่ถูกตัดด้วย spec-diff ; ต่างกัน 1 อักขระ → ratio ~98 ≥ threshold)
PLANT_A = "ท่อพีวีซีขนาดสามนิ้วยาว"
PLANT_B = "ท่อพีวีซีขนาดสามนิวยาว"

# ชื่อเติม 600 ตัว (มีเลขกำกับ → คนละชุด spec → ไม่จับคู่กันเอง = ไม่เกิด noise)
names = [f"วัสดุก่อสร้างรายการที่{i}" for i in range(600)]
names += [PLANT_A, PLANT_B]

bills = [{"items": [{"name": nm, "amount": 100.0, "seq": idx}]}
         for idx, nm in enumerate(names)]

unique_n = len({nm for nm in names})
_check(f"unique names = {unique_n} (>500 → เข้าเส้น sliding-window)", unique_n > 500)
_check(f"threshold = {CFG['FUZZY_PRODUCT_THRESHOLD']} (ใช้ตรวจคู่ที่ฝัง)",
       CFG["FUZZY_PRODUCT_THRESHOLD"] <= 95)

typos = check_product_typos(bills)
pair = tuple(sorted([PLANT_A, PLANT_B]))
found = any(tuple(sorted([t["name1"], t["name2"]])) == pair for t in typos)

_check("window path จับคู่ typo ที่ฝังได้ (correctness ใต้ scale)", found)
# ตัวเติมที่มีเลขต่างกันต้องไม่ถูกฟ้องเป็น typo กันเอง (spec-diff guard ทำงาน)
filler_noise = sum(1 for t in typos
                   if "รายการที่" in t["name1"] and "รายการที่" in t["name2"])
_check(f"ตัวเติมเลขต่างชุดไม่ถูกฟ้องเป็น typo (noise={filler_noise})", filler_noise == 0)

print("=" * 56)
if _fail == 0:
    print("RESULT: ✅ sliding-window typo path ถูกครอบ + ยังถูกต้อง")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน")
    sys.exit(1)
