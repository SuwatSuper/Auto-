# -*- coding: utf-8 -*-
"""test_a_hardening.py — TRIPWIRE: ชั้น advisory/รายงานต้องทนข้อมูลเพี้ยน ไม่ครัช (หมวด A)

ตรึงผลของการแก้บั๊กหมวด A (ความทนทาน — ระบบต้องไม่ล้มเพราะข้อมูล 1 จุดเพี้ยน):
  A2a render_ultra_block : prevat ไม่ใช่ตัวเลข ('-') → ไม่ครัช (เดิม ValueError)
  A2b _ctx               : iv_date เป็น string → ไม่ครัช (เดิม AttributeError)
  A2c emit_ultra_summary : บล็อกหนึ่งพังต้องไม่ทำสรุปทั้งไฟล์หาย
  A3  _month_label       : ปี พ.ศ. (>2500) ไม่ถูก +543 ซ้ำ; ปี ค.ศ. ผลเท่าเดิม
  A4  lens VAT003        : vat อ่านไม่ออก (None) → abstain (เดิมตีเป็น 0 แล้วโหวตผิด)
  A5  build_clean_report : issue ขาดคีย์มาตรฐาน → ไม่ทำทั้ง workbook ล่ม
  A1  build_consolidated : OUT ชื่อไฟล์เปล่า → ไม่ครัช (เดิม FileNotFoundError) [subprocess]

self-contained: ใช้ fixtures 3 บิล (deterministic) สร้าง vc/summary จริง.
"""
import os
import sys
import subprocess
import tempfile
import glob as _glob

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("A-HARDENING — ชั้น advisory/รายงานต้องทนข้อมูลเพี้ยน")

# ── เตรียมบิลจริงจาก fixtures (ใช้ร่วม A2/A5) ─────────────────────────────────
import importlib
app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
app.reset_run_state()
_fl = sorted(_glob.glob(os.path.join(HERE, "tests", "fixtures", "*.xls"))
             + _glob.glob(os.path.join(HERE, "tests", "fixtures", "*.xlsx")))
_bills, _fi = app.parse_all_files(_fl)
for _b in _bills:
    app.compute_bill_confidence(_b)
_core = app.run_audit_core(_bills, {}, isolate=True)

import ultra_agent as UA
from super_ultra_viewer import _month_label

# ── A2a: prevat ไม่ใช่ตัวเลข (ใช้ vc จริง แล้ว override prevat) ────────────────
_vcs = UA.build_ultra(_bills, master_present=False)
if _vcs:
    _vc = dict(_vcs[0]); _vc["row"] = dict(_vc["row"]); _vc["row"]["prevat"] = "-"
    try:
        s = UA.render_ultra_block(1, _vc)
        _check("A2a render_ultra_block: prevat '-' → ไม่ครัช", isinstance(s, str))
    except Exception as e:
        _check(f"A2a render_ultra_block: prevat '-' → ไม่ครัช (ได้ {type(e).__name__})", False)
else:
    _check("A2a render_ultra_block: (ไม่มี vc ทดสอบ — fixtures ว่าง?)", False)

# ── A2b: iv_date เป็น string ──────────────────────────────────────────────────
try:
    c = UA._ctx({"file": "JRN_69.xls", "iv_number": "IV1", "iv_date": "2025-05-01"})
    _check("A2b _ctx: iv_date string → ไม่ครัช + ไม่ใส่วันที่มั่ว", isinstance(c, str) and "วันที่" not in c)
except Exception as e:
    _check(f"A2b _ctx: iv_date string → ไม่ครัช (ได้ {type(e).__name__})", False)

# ── A2c: emit_ultra_summary ต้องเขียนไฟล์ได้ (ไม่ล้มทั้งไฟล์) ────────────────
with tempfile.TemporaryDirectory() as _td:
    try:
        p = UA.emit_ultra_summary(_bills, _td, master_present=False)
        _check("A2c emit_ultra_summary: เขียนสรุปได้", bool(p) and os.path.isfile(p))
    except Exception as e:
        _check(f"A2c emit_ultra_summary: ไม่ครัช (ได้ {type(e).__name__})", False)

# ── A3: ปี พ.ศ. vs ค.ศ. ต้องได้ '05/69' เท่ากัน (ไม่ +543 ซ้ำ) ────────────────
class _D2:
    def __init__(self, y, m): self.year, self.month, self.day = y, m, 1
ce = _month_label(_D2(2026, 5))[1]
be = _month_label(_D2(2569, 5))[1]
_check(f"A3 _month_label: ค.ศ.2026 → {ce} (คาด 05/69)", ce == "05/69")
_check(f"A3 _month_label: พ.ศ.2569 → {be} (ไม่ +543 ซ้ำ; คาด 05/69)", be == "05/69")

# ── A4: lens VAT003 vat=None → abstain; vat=0 จริง → ยังโหวต ──────────────────
from agents.verification_lenses import lens_recompute
from agents.verification_lenses_base import LensInput

def _li(bill):
    return LensInput(bill=bill, issue={}, code="VAT003", sev="CRITICAL", peers=[])

v_none = lens_recompute(_li({"subtotal": 100, "vat": None, "total": 200}))
_check(f"A4 lens VAT003: vat=None → abstain (ได้ {v_none})", v_none[0] == 0)
v_zero = lens_recompute(_li({"subtotal": 100, "vat": 0, "total": 200}))
_check(f"A4 lens VAT003: vat=0 จริง + sub+vat≠total → ยังโหวต +1 (ได้ {v_zero})", v_zero[0] == 1)

# ── A5: build_clean_report ทน issue ขาดคีย์ ──────────────────────────────────
if _bills:
    _bills[0].setdefault("issues", []).append({"code": "ZZZ999"})   # ไม่มี severity/category/name/detail
with tempfile.TemporaryDirectory() as _td:
    _out = os.path.join(_td, "clean.xlsx")
    try:
        ok = app.build_clean_report(_bills, _core["summary"], _core["iv_issues"], _core["typos"], _fi, _out)
        _check("A5 build_clean_report: issue ขาดคีย์ → ยังออกรายงานได้ (ไม่ล่มทั้ง workbook)",
               bool(ok) and os.path.isfile(_out))
    except Exception as e:
        _check(f"A5 build_clean_report: issue ขาดคีย์ → ไม่ครัช (ได้ {type(e).__name__})", False)

# ── A1: build_consolidated OUT ชื่อไฟล์เปล่า [subprocess] ─────────────────────
#   หมายเหตุ: สคริปต์ os.chdir ไปโฟลเดอร์โปรเจกต์ → ไฟล์ผลลัพธ์ไปอยู่ที่นั่น (ไม่ใช่ cwd ที่เรียก)
_bare = os.path.join(HERE, "bare_consolidated_test.xlsx")
if os.path.exists(_bare):
    os.remove(_bare)
_env = {**os.environ, "PYTHONHASHSEED": "0", "PUOPUY_AUDIT_DATE": "2026-06-02",
        "PUOPUY_ALLOW_VERSION_MISMATCH": "1"}
r = subprocess.run([sys.executable, os.path.join(HERE, "build_consolidated_report.py"),
                    os.path.join(HERE, "tests", "fixtures"), "bare_consolidated_test.xlsx"],
                   capture_output=True, text=True, env=_env, cwd=tempfile.gettempdir())
_made = os.path.isfile(_bare)
_check(f"A1 build_consolidated: OUT ชื่อไฟล์เปล่า → ไม่ครัช + สร้างไฟล์ได้ (rc={r.returncode})",
       r.returncode == 0 and _made)
if os.path.exists(_bare):
    os.remove(_bare)

print("=" * 64)
if _fail == 0:
    print("RESULT: ✅ ชั้น advisory/รายงานทนข้อมูลเพี้ยนครบทุกเคส (หมวด A)")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — ตรวจการแก้หมวด A")
    sys.exit(1)
