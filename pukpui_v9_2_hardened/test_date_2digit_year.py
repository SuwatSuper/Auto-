# -*- coding: utf-8 -*-
"""test_date_2digit_year.py — TRIPWIRE: ปี 2 หลักใน parse_date_any ต้องตีความเหมือน _ivp_year2_to_ce

บริบท (P1-FIX วันที่ 2 หลัก):
  เดิม parse_date_any ตีปี 2 หลักเป็น "พ.ศ.ย่อ" เสมอ (yy+2500-543) → "1/1/15" กลายเป็น ค.ศ.1972
  ขณะที่ _ivp_year2_to_ce (เส้น IV-period) ตี "15" เป็น ค.ศ.2015 → ตีความขัดกัน 2 ที่ → ฟ้องวันที่ผิด.
  แก้: parse_date_any ใช้กติกาเดียวกับ _ivp_year2_to_ce (58-82=พ.ศ.→ค.ศ., 15-39=ค.ศ.).

ตรึงสองสัญญา:
  • ปีกลุ่ม corpus ปัจจุบัน (66-69 = พ.ศ.) → ค.ศ. 2023-2026 เท่าเดิม (golden ไม่ขยับ)
  • ปีกลุ่ม ค.ศ.ย่อ (15-39) → 2015-2039 (เลิกเพี้ยนเป็น 19xx)

self-contained: เรียก parse_date_any ตรง ๆ (deterministic, ไม่พึ่ง /mnt/project).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from puopuy_dates import parse_date_any

_fail = 0


def _check(label, got, want):
    global _fail
    ok = got == want
    print(("  ✅ " if ok else "  ❌ ") + f"{label}: ได้ {got} (คาด {want})")
    if not ok:
        _fail += 1


print("DATE 2-DIGIT YEAR — พ.ศ./ค.ศ. ต้องไม่ขัดกัน (P1-FIX)")

# (1) corpus ปัจจุบัน: ปี 66-69 = พ.ศ.ย่อ → ค.ศ. 2023-2026 (เท่าเดิม → golden ไม่ขยับ)
_check("5/5/69 (พ.ศ.69)", parse_date_any("5/5/69").year, 2026)
_check("25/12/68 (พ.ศ.68)", parse_date_any("25/12/68").year, 2025)
_check("1/1/66 (พ.ศ.66)", parse_date_any("1/1/66").year, 2023)

# (2) เคสบั๊กเดิม: ปี 15-39 = ค.ศ.ย่อ → 2015-2039 (เดิมเพี้ยนเป็น 1972/1996)
_check("1/1/15 (ค.ศ.15)", parse_date_any("1/1/15").year, 2015)
_check("10/3/39 (ค.ศ.39)", parse_date_any("10/3/39").year, 2039)

# (3) ปี 4 หลักไม่ถูกแตะ (ไปทาง strptime/พ.ศ.→ค.ศ. เดิม)
_check("15/05/2025 (4 หลัก ค.ศ.)", parse_date_any("15/05/2025").year, 2025)
_check("01/01/2569 (4 หลัก พ.ศ.)", parse_date_any("01/01/2569").year, 2026)

# (4) เดือนไทย ปี 2 หลัก ก็ต้องใช้กติกาเดียวกัน
_check("5 ม.ค. 69 (เดือนไทย พ.ศ.69)", parse_date_any("5 มกราคม 69").year, 2026)

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ ปี 2 หลักตีความตรงกับ _ivp_year2_to_ce — ไม่มี divergence")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — ตรวจ parse_date_any / _ivp_year2_to_ce")
    sys.exit(1)
