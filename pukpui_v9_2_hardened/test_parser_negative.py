# -*- coding: utf-8 -*-
"""test_parser_negative.py — [OBJ-1D] FUZZ / NEGATIVE-PATH ของ parser + leaf utils

เป้าหมาย (กฎเหล็กข้อ 4 + OBJ-1D): พิสูจน์ว่า "ไฟล์พัง/ขยะ/ว่าง → ห้าม crash + ต้องยิง SYS00x"
และ leaf helper (_D, _vat_tolerance) รับ input สุดขั้ว (NaN/inf/ยักษ์/ขยะ/unicode) โดยไม่ throw.

ครอบ:
  T1  ไฟล์ไม่มีอยู่จริง                → ไม่ throw, ยิง SYS001, ข้ามไฟล์
  T2  ไฟล์พัง (ว่าง/ขยะ/ข้อความ/zip เสีย) → ไม่ throw, ยิง SYS001
  T3  xlsx ถูกฟอร์แมตแต่เนื้อหาเพี้ยน    → ไม่ throw (แถวน้อย/เซลล์ว่าง/ขยะปนชนิด)
  T4  RESILIENCE: ไฟล์ดี + ไฟล์พัง ปนกัน → บิลจากไฟล์ดี "ยังครบ" (ไฟล์พังไม่ล้มทั้ง batch)
  T5  ส่ง path ที่เป็นโฟลเดอร์          → ไม่ throw
  T6  parse_sheet ป้อน DataFrame สุ่ม   → ไม่ throw
  T7  _D fuzz (NaN/inf/ยักษ์/bytes/ขยะ)  → ไม่ throw, คืน Decimal หรือ None เสมอ
  T8  _vat_tolerance fuzz               → ไม่ throw, คืน Decimal เสมอ

ไม่ต้องใช้ข้อมูลจริง (ใช้ไฟล์ที่สร้างเอง + fixture ในแพ็กเกจ) → เร็ว ใส่ CI ได้:
    PYTHONHASHSEED=0 python3 test_parser_negative.py
exit 0 = ผ่าน, 1 = พบปัญหา
"""
import os
import sys
import io
import tempfile
import contextlib
import warnings
import importlib
from decimal import Decimal

warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import state
import pandas as pd
import numpy as np
from openpyxl import Workbook

# import โมดูลหลัก (เงียบ — ดูด stdout ตอน import/parse กันรก)
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
import parser as P
from puopuy_units import _D, _vat_tolerance

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
    """รัน fn() (ดูด stdout) — ผ่านถ้าไม่ throw, คืนผลลัพธ์ (หรือ None ถ้า throw)."""
    global PASS
    try:
        b = io.StringIO()
        with contextlib.redirect_stdout(b):
            res = fn()
        PASS += 1
        print(f"  ✅ {label}")
        return res
    except BaseException as e:  # รวม SystemExit/KeyboardInterrupt — parser ห้ามล้มทุกชนิด
        FAIL.append(f"{label}  → THREW {type(e).__name__}: {str(e)[:120]}")
        print(f"  ❌ {label}  → THREW {type(e).__name__}: {str(e)[:120]}")
        return None


def sys_codes():
    """คืน set ของ code ใน audit trail ปัจจุบัน."""
    return {i.get('code') for i in state._SYSTEM_ISSUES}


# ════════════════════════════════════════════════════════════════════════════
print("=" * 64)
print("PARSER NEGATIVE-PATH / FUZZ — ไฟล์พังห้าม crash + ต้องยิง SYS00x")
print("=" * 64)

TMP = tempfile.mkdtemp(prefix="pukpui_neg_")

# ── สร้างไฟล์พังแบบต่าง ๆ ─────────────────────────────────────────────────────
f_empty = os.path.join(TMP, "empty.xls")
open(f_empty, "wb").close()                                  # 0 ไบต์

f_garbage = os.path.join(TMP, "garbage.xls")
open(f_garbage, "wb").write(os.urandom(2048))                # ไบต์สุ่ม

f_text = os.path.join(TMP, "textfile.xls")
open(f_text, "w", encoding="utf-8").write("นี่ไม่ใช่ไฟล์ Excel\nบรรทัดสอง\n")

f_badxlsx = os.path.join(TMP, "garbage.xlsx")
open(f_badxlsx, "wb").write(os.urandom(3000))                # zip เสีย

f_nonexist = os.path.join(TMP, "does_not_exist.xls")

# xlsx ถูกฟอร์แมต แต่เนื้อหาเพี้ยน
def _mk_xlsx(path, rows):
    wb = Workbook(); ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)

f_tiny = os.path.join(TMP, "tiny.xlsx")
_mk_xlsx(f_tiny, [["a", "b"], [1, 2]])                       # < 5 แถว → ควรถูกข้าม

f_emptycells = os.path.join(TMP, "emptycells.xlsx")
_mk_xlsx(f_emptycells, [[None] * 4 for _ in range(8)])       # 8 แถวว่าง

f_garbagecells = os.path.join(TMP, "garbagecells.xlsx")
_mk_xlsx(f_garbagecells, [["@@@", "###", None, "ฟฟฟ", 3.14],
                          ["xyz", "", "!!!", None, "abc"]] * 4)  # ขยะ 8 แถว

# fixture ที่ดี (มากับแพ็กเกจ → CI มีแน่)
f_good = os.path.join(HERE, "tests", "fixtures", "fixture_invoices.xlsx")

# ── T1: ไฟล์ไม่มีอยู่จริง ─────────────────────────────────────────────────────
print("\n[T1] ไฟล์ไม่มีอยู่จริง")
app.reset_run_state()
r = no_throw(lambda: app.parse_all_files([f_nonexist]), "parse_all_files([ไฟล์ที่ไม่มี]) ไม่ throw")
check(isinstance(r, tuple) and len(r) == 2 and r[0] == [], "คืน (bills=[], filename_issues=...) ถูกชนิด")
check('SYS001' in sys_codes(), "ยิง SYS001 (audit trail บันทึกไฟล์ที่ล้ม)")

# ── T2: ไฟล์พังหลายแบบ ────────────────────────────────────────────────────────
print("\n[T2] ไฟล์พัง (ว่าง/ขยะ/ข้อความ/xlsx zip เสีย)")
app.reset_run_state()
r = no_throw(lambda: app.parse_all_files([f_empty, f_garbage, f_text, f_badxlsx]),
             "parse_all_files([ไฟล์พัง 4 แบบ]) ไม่ throw")
check(isinstance(r, tuple) and r[0] == [], "ไม่มีบิลหลุดออกมาจากไฟล์พัง")
check('SYS001' in sys_codes(), "ยิง SYS001 สำหรับไฟล์ที่เปิด/อ่านไม่ได้")

# ── T3: xlsx ถูกฟอร์แมต เนื้อหาเพี้ยน ─────────────────────────────────────────
print("\n[T3] xlsx ฟอร์แมตถูก เนื้อหาเพี้ยน (แถวน้อย/ว่าง/ขยะ)")
app.reset_run_state()
no_throw(lambda: app.parse_all_files([f_tiny]), "tiny (<5 แถว) ไม่ throw")
no_throw(lambda: app.parse_all_files([f_emptycells]), "เซลล์ว่างล้วน ไม่ throw")
no_throw(lambda: app.parse_all_files([f_garbagecells]), "เซลล์ขยะปนชนิด ไม่ throw")

# ── T4: RESILIENCE — ไฟล์ดีปนไฟล์พัง ──────────────────────────────────────────
print("\n[T4] RESILIENCE: ไฟล์ดี + ไฟล์พัง ปนกัน (batch ต้องไม่ล้มทั้งหมด)")
app.reset_run_state()
good_only = no_throw(lambda: app.parse_all_files([f_good]), "parse fixture ดี (อ้างอิง)")
n_good = len(good_only[0]) if good_only else -1
app.reset_run_state()
mixed = no_throw(lambda: app.parse_all_files([f_garbage, f_good, f_empty, f_badxlsx]),
                 "parse [พัง, ดี, พัง, พัง] ไม่ throw")
n_mixed = len(mixed[0]) if mixed else -1
check(n_good > 0, f"fixture ดีให้บิล > 0 (ได้ {n_good})")
check(n_mixed == n_good, f"ไฟล์พังไม่ทำให้บิลจากไฟล์ดีหาย ({n_mixed} == {n_good})")
check('SYS001' in sys_codes(), "ยังยิง SYS001 ให้ไฟล์พังในชุดผสม")

# ── T5: path เป็นโฟลเดอร์ ─────────────────────────────────────────────────────
print("\n[T5] ส่ง path ที่เป็นโฟลเดอร์ (ไม่ใช่ไฟล์)")
app.reset_run_state()
no_throw(lambda: app.parse_all_files([TMP]), "parse_all_files([โฟลเดอร์]) ไม่ throw")
no_throw(lambda: P.parse_file(TMP), "parse_file(โฟลเดอร์) ไม่ throw")

# ── T6: parse_sheet ป้อน DataFrame สุ่ม ───────────────────────────────────────
print("\n[T6] parse_sheet ป้อน DataFrame หลากรูปแบบ")
rng = np.random.default_rng(0)
dfs = {
    "ว่างเปล่า": pd.DataFrame(),
    "1x1": pd.DataFrame([[1]]),
    "NaN ล้วน 10x6": pd.DataFrame(np.full((10, 6), np.nan)),
    "ตัวเลขสุ่ม 20x8": pd.DataFrame(rng.integers(-10**9, 10**9, size=(20, 8))),
    "ข้อความสุ่ม 15x5": pd.DataFrame(rng.choice(list("กขคงabc@# "), size=(15, 5))),
}
for nm, df in dfs.items():
    no_throw(lambda df=df: P.parse_sheet(df, "fuzz", "fuzz.xlsx"), f"parse_sheet({nm}) ไม่ throw")

# ── T7: _D fuzz ───────────────────────────────────────────────────────────────
print("\n[T7] _D fuzz — รับขยะแล้วต้องคืน Decimal|None เสมอ (ไม่ throw)")
fuzz_vals = [
    None, "", "   ", "abc", "1,234.56", "฿1,000", "\xa0\u200b", float('nan'),
    float('inf'), float('-inf'), 10**30, -(10**30), 0, 0.0, True, False,
    "1e500", "NaN", "Infinity", "--5", "5.5.5", b"123", [], {}, object(),
    "๑๒๓", "1\u00a0234", Decimal('123.45'), 3.14159,
]
all_ok = True
for v in fuzz_vals:
    try:
        out = _D(v)
        if not (out is None or isinstance(out, Decimal)):
            all_ok = False
            FAIL.append(f"_D({v!r}) คืนชนิดผิด: {type(out).__name__}")
    except BaseException as e:
        all_ok = False
        FAIL.append(f"_D({v!r}) THREW {type(e).__name__}")
check(all_ok, f"_D รับ fuzz {len(fuzz_vals)} ค่า โดยไม่ throw + คืน Decimal|None")

# ── T8: _vat_tolerance fuzz ────────────────────────────────────────────────────
print("\n[T8] _vat_tolerance fuzz — ต้องคืน Decimal เสมอ (ไม่ throw)")
all_ok = True
for v in fuzz_vals:
    try:
        out = _vat_tolerance(v)
        if not isinstance(out, Decimal):
            all_ok = False
            FAIL.append(f"_vat_tolerance({v!r}) คืนชนิดผิด: {type(out).__name__}")
    except BaseException as e:
        all_ok = False
        FAIL.append(f"_vat_tolerance({v!r}) THREW {type(e).__name__}")
check(all_ok, f"_vat_tolerance รับ fuzz {len(fuzz_vals)} ค่า โดยไม่ throw + คืน Decimal")

# ── cleanup ────────────────────────────────────────────────────────────────────
import shutil
shutil.rmtree(TMP, ignore_errors=True)

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"NEGATIVE/FUZZ: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    print("รายการที่ล้ม:")
    for f in FAIL:
        print(f"  • {f}")
    print("RESULT: ❌ พบ negative-path/fuzz ที่ยังไม่ปลอดภัย")
    sys.exit(1)
print("RESULT: ✅ ไฟล์พัง/ขยะ/สุดขั้ว ไม่ทำให้ระบบ crash และยิง SYS00x ครบ")
sys.exit(0)
