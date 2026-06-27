# -*- coding: utf-8 -*-
"""test_parser_helpers.py — [OBJ-1D] unit test ฟังก์ชันบริสุทธิ์ใน parser (coverage + robustness)

ตรวจ helper ระดับล่างของ parser ที่ข้อมูลจริงไม่ค่อยแตะ (edge layout / รูปแบบเลข/IV/taxid/ที่อยู่):
ทั้ง "ค่าถูกต้องตามที่วัดจากโมดูล" และ "ป้อน edge/fuzz แล้วไม่ throw".

    PYTHONHASHSEED=0 python3 test_parser_helpers.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import pandas as pd
import numpy as np

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
import parser as P

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
        FAIL.append(f"{label} → THREW {type(e).__name__}: {str(e)[:100]}")
        print(f"  ❌ {label} → THREW {type(e).__name__}")
        return None


print("=" * 64)
print("PARSER HELPERS — unit + edge/fuzz")
print("=" * 64)

# ── parse_filename ──
print("\n[1] parse_filename / _declared_period_from_filename")
fi = P.parse_filename("KRR_69_012.xls")
# [FIX-MONTH012] '012' (leading-zero ≥3 หลัก) = เดือน '01' ไม่ใช่ int('012')=12 (กัน DT001 false positive 50 บิล)
check(fi.get("year") == 2569 and fi.get("month") == 1, "KRR_69_012 → year 2569, month 1 (FIX-MONTH012)")
check(P.parse_filename("SHS_68_0514.xls").get("year") == 2568, "SHS_68_0514 → year 2568")
for bad in ["", "x.xls", "เอกสาร.xlsx", "____.xls", "A_B_C_D_E.xls", None]:
    no_throw(lambda bad=bad: P.parse_filename(bad if bad is not None else ""),
             f"parse_filename({bad!r}) ไม่ throw")
no_throw(lambda: P._declared_period_from_filename("KRR_69_0514.xls"), "_declared_period_from_filename ไม่ throw")

# ── _cell_to_num ──
print("\n[2] _cell_to_num")
check(P._cell_to_num("1,234.50") == 1234.5, "'1,234.50' → 1234.5")
check(P._cell_to_num("฿1,000") is None, "'฿1,000' → None (ไม่ strip ฿ ต่างจาก _D)")
check(P._cell_to_num("abc") is None, "'abc' → None")
check(P._cell_to_num(None) is None, "None → None")
check(P._cell_to_num(500) == 500.0, "int 500 → 500.0")
check(P._cell_to_num(-12.5) == -12.5, "ลบ -12.5 → -12.5")
for v in [float('nan'), float('inf'), "", "  ", "1.2.3", np.int64(7), True]:
    no_throw(lambda v=v: P._cell_to_num(v), f"_cell_to_num({v!r}) ไม่ throw")

# ── IV parsing ──
print("\n[3] IV parsing (_pick_best_iv_safe / _pick_best_iv / _has_suspat_in_iv / _raw_iv_form)")
iv, conf = P._pick_best_iv_safe("IV6805001")
check(iv == "IV6805001", "_pick_best_iv_safe('IV6805001') → IV6805001")
check(P._pick_best_iv_safe("")[0] is None, "_pick_best_iv_safe('') → (None, ...)")
for s in [None, "", "เลขที่ IV-680/5001 ลงวันที่", "1234567", "###", "IV 68 05 001"]:
    no_throw(lambda s=s: P._pick_best_iv_safe(s if s is not None else ""), f"_pick_best_iv_safe({s!r}) ไม่ throw")
no_throw(lambda: P._pick_best_iv("IV6805001", known_tax_id="0105566206726", return_score=True),
         "_pick_best_iv(known_tax_id, return_score) ไม่ throw")
no_throw(lambda: P._has_suspat_in_iv("IV000000"), "_has_suspat_in_iv ไม่ throw")
no_throw(lambda: P._raw_iv_form("เลขที่ IV-680/5001", "IV6805001"), "_raw_iv_form ไม่ throw")

# ── tax id ──
print("\n[4] tax id (_extract_taxid_safe / _taxid_from_cell)")
check(P._extract_taxid_safe("เลขประจำตัว 0105566206726 สาขา") == "0105566206726",
      "_extract_taxid_safe ดึง 13 หลักจากข้อความ")
for s in [None, "", "ไม่มีเลข", "123", "0 1 0 5 5 6 6 2 0 6 7 2 6"]:
    no_throw(lambda s=s: P._extract_taxid_safe(s if s is not None else ""), f"_extract_taxid_safe({s!r}) ไม่ throw")
no_throw(lambda: P._taxid_from_cell("0105566206726", 0, 0), "_taxid_from_cell ไม่ throw")

# ── address ──
print("\n[5] _looks_like_address / _addr_parse_confidence")
check(P._looks_like_address("เลขที่ 5/32 ซอย ศรีนครินทร์ เขตประเวศ กรุงเทพ") is True, "ที่อยู่จริง → True")
check(P._looks_like_address("เหล็กเส้น") is False, "ชื่อสินค้า → False")
for s in [None, "", "123", "@@@"]:
    no_throw(lambda s=s: P._looks_like_address(s if s is not None else ""), f"_looks_like_address({s!r}) ไม่ throw")

# ── DataFrame helpers: _detect_vat_rows / _is_tor_format / _rightmost_num ──
print("\n[6] DataFrame helpers")
df_vat = pd.DataFrame([['สินค้า', '', '', ''], ['เหล็ก', '', '', '100'],
                       ['', '', '', ''], ['', '', 'ภาษีมูลค่าเพิ่ม', '7'], ['', '', 'รวม', '107']])
check(3 in P._detect_vat_rows(df_vat), "_detect_vat_rows เจอแถว VAT (index 3)")
check(P._detect_vat_rows(pd.DataFrame([['a', 'b'], ['c', 'd']])) == [], "ไม่มี VAT → []")
check(P._is_tor_format(df_vat) is False, "ตารางปกติ → ไม่ใช่ TOR")
check(P._rightmost_num(df_vat.to_numpy(dtype=object), 4, df_vat.shape[1]) == 107.0, "_rightmost_num แถวรวม → 107")
for df in [pd.DataFrame(), pd.DataFrame([[np.nan] * 4] * 3), pd.DataFrame([['x']])]:
    no_throw(lambda df=df: P._detect_vat_rows(df), "_detect_vat_rows(edge df) ไม่ throw")
    no_throw(lambda df=df: P._is_tor_format(df), "_is_tor_format(edge df) ไม่ throw")

# ── list helpers: merge_continuation_bills / check_iv_format ──
print("\n[7] merge_continuation_bills / check_iv_format")
check(P.merge_continuation_bills([]) == [], "merge_continuation_bills([]) → []")
sample = [{'iv_number': 'IV6805001', 'items': [{'seq': 1, 'name': 'x', 'amount': 100}],
           'subtotal': 100, 'vat': 7, 'total': 107, 'company': 'A', 'sheet': '1',
           'tax_id': '', 'issues': []}]
no_throw(lambda: P.merge_continuation_bills([dict(b) for b in sample]), "merge_continuation_bills(1 บิล) ไม่ throw")
no_throw(lambda: P.check_iv_format([dict(b) for b in sample]), "check_iv_format(1 บิล) ไม่ throw")
no_throw(lambda: P.check_iv_format([]), "check_iv_format([]) ไม่ throw")

print("\n" + "=" * 64)
print(f"PARSER HELPERS: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for f in FAIL:
        print(f"  • {f}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ helper ของ parser ทนทาน + ค่าถูกต้อง")
sys.exit(0)
