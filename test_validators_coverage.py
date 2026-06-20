# -*- coding: utf-8 -*-
"""test_validators_coverage.py — เก็บกิ่งที่ยังไม่ถูกตรวจใน validators.py (OBJ-TEST → ≥90%)

จุดสำคัญ: เส้นทาง check_product_typos กรณี "ชื่อสินค้า unique > 500" (sliding-window) +
cross-check helper (period/sheet-date) — behavior ไม่เปลี่ยน แค่เพิ่ม coverage.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_validators_coverage.py
"""

import os, sys, io, datetime, contextlib, warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import validators as V

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


print("=" * 60)
print("VALIDATORS COVERAGE — กิ่งที่เหลือ")
print("=" * 60)

# [1] check_product_typos: เส้นทาง > 500 ชื่อ (sliding-window 422-440)
items = []
# filler 590 ชื่อ ยาวเท่ากัน มีตัวเลข (สเปกต่างกัน → _is_spec_diff True path)
for i in range(590):
    items.append(
        {
            "name": f"รายการสินค้ากลุ่มมาตรฐานรหัสที่{i:04d}",
            "qty": 1.0,
            "price": 1.0,
            "amount": 1.0,
        }
    )
# คู่ near-dup ไม่มีตัวเลข ยาวกว่าเล็กน้อย (คลัสเตอร์ท้าย) → spec เท่ากัน → ควร append (438-440)
items.append(
    {
        "name": "รายการสินค้ากลุ่มพิเศษเอเอเอเอเอเอเอ",
        "qty": 1.0,
        "price": 1.0,
        "amount": 1.0,
    }
)
items.append(
    {
        "name": "รายการสินค้ากลุ่มพิเศษเอเอเอเอเอเอบี",
        "qty": 1.0,
        "price": 1.0,
        "amount": 1.0,
    }
)
bills_big = [{"file": "F.xlsx", "sheet": "1", "items": items}]
try:
    with contextlib.redirect_stdout(io.StringIO()):
        typos = V.check_product_typos(bills_big)
    check(
        isinstance(typos, list),
        f"check_product_typos เส้นทาง >500 ชื่อ ทำงาน (พบ typo {len(typos)} คู่)",
    )
except Exception as e:
    check(False, f"check_product_typos >500 ล้มเหลว: {type(e).__name__}: {e}")

# [2] เพดาน MAX_TYPO_NAMES (กรณี > 3000 → ข้าม + SYS002)
from config import CFG

big2 = [
    {
        "file": "F",
        "sheet": "1",
        "items": [
            {"name": f"x{i}", "qty": 1, "price": 1, "amount": 1}
            for i in range(CFG.get("MAX_TYPO_NAMES", 3000) + 5)
        ],
    }
]
try:
    with contextlib.redirect_stdout(io.StringIO()):
        r = V.check_product_typos(big2)
    check(r == [], "เกินเพดาน MAX_TYPO_NAMES → ข้าม (คืน [])")
except Exception as e:
    check(False, f"เพดาน typo ล้มเหลว: {e}")

# [3] cross-check helpers (apply_*): ไม่ crash + คืนค่า/แก้ bills in place
b = [
    {
        "file": "F.xlsx",
        "sheet": "1",
        "iv_number": "IV6801",
        "iv_date": datetime.datetime(2025, 1, 15),
        "iv_date_str": "15/01/2025",
        "file_info": {"year": 2025, "month": 1},
        "items": [],
        "issues": [],
    }
]
for fn in ("apply_iv_period_crosscheck", "apply_sheet_date_crosscheck"):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            getattr(V, fn)(b)
        check(True, f"{fn} ทำงานไม่ crash")
    except Exception as e:
        check(False, f"{fn} ล้มเหลว: {type(e).__name__}: {e}")

# [4] detect_iv_period_mismatch (เส้นทางตรง)
try:
    _ = V.detect_iv_period_mismatch("IV6801-0001", datetime.datetime(2025, 1, 15))
    check(True, "detect_iv_period_mismatch ทำงาน")
except Exception as e:
    check(False, f"detect_iv_period_mismatch ล้มเหลว: {e}")

print("\n" + "=" * 60)
print(f"VALIDATORS COVERAGE: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 60)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    sys.exit(1)
print("RESULT: ✅")
sys.exit(0)
