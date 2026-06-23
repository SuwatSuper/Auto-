# -*- coding: utf-8 -*-
"""test_rules_typo_branch.py — เก็บกิ่ง emit ของกฎตรวจการพิมพ์ (r_itm004 / r_itm010)

บริบท (coverage gate [10]): rules_engine_rules_b มีกิ่ง "ตรวจพบแล้วฟ้อง" ของกฎ typo ที่
fixture สะอาดไม่ trigger:
  • r_itm004 — SPELLING_PATTERNS (อังกฤษติดกัน 'WARMWHITE', อังกฤษ+ไทยติดกัน 'ABCนิ้ว')
    หมายเหตุ [ADR-075]: เลข+หน่วยไทยติดกัน ('5นิ้ว'/'60x30มม.') = เขียนไทยปกติ → "ไม่" ฟ้อง (golden 08e6abfd)
  • r_itm010 — THAI_TYPO_PATTERNS (สระ/วรรณยุกต์ซ้อน เช่น 'าา')

เทสนี้ป้อนชื่อสินค้าที่ "จุดชนวน" กิ่ง emit จริง + เคสสะอาด (ต้องไม่ฟ้อง) — ยืนยันพฤติกรรม
ตรวจ typo + เก็บกิ่ง. เป็น pin/coverage test ล้วน ; ไม่แตะ logic ; golden ไม่ขยับ.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_rules_typo_branch.py
"""

import os
import sys
import io
import contextlib
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine_rules_b as B

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def _it(seq, name, raw=None):
    return {"seq": seq, "name": name, "name_raw": raw if raw is not None else name}


def _join(out):
    return " | ".join(out)


print("=" * 64)
print("RULES typo branch — r_itm004 (สะกด/เว้นวรรค) + r_itm010 (สระ/วรรณยุกต์ซ้อน)")
print("=" * 64)

# ── [A] r_itm004 — SPELLING_PATTERNS emit ──────────────────────────────
print("\n[A] r_itm004 ตรวจการเว้นวรรค/ติดกัน")
out = B.r_itm004({"items": [_it(1, "WARMWHITE LED")]}, None, {})
check(any("WARM WHITE" in x for x in out), "WARMWHITE → ฟ้องควรเว้นวรรค")
# [ADR-075/ADR-081] เลข+หน่วยไทยติดกัน ("5นิ้ว") = การเขียนไทยปกติ → ต้อง "ไม่" ฟ้อง
#   (UNIT_OK guard + ตัด 0-9 ออกจาก lookaround). ตรงกับ golden 08e6abfd + test_recheck_rules_20260622.py:84
#   เดิมเทสนี้ assert "len>0 (ฟ้อง)" ค้างจากก่อน ADR-075 → ขัด golden + ขัด recheck test (บั๊กเทสที่ run_ci.sh
#   ไม่ได้รันเป็น step จึงไม่ถูกจับ; coverage_gate รันแต่กลืน exit code).
out2 = B.r_itm004({"items": [_it(1, "ท่อ 5นิ้ว")]}, None, {})
check(out2 == [], "เลข+หน่วยไทยติดกัน (5นิ้ว) → ไม่ฟ้อง (ADR-075 เขียนไทยปกติ)")
# อักษรอังกฤษ+ไทยจริง (ไม่ใช่เลข) ยังต้องฟ้อง — เก็บกิ่ง emit ของ lookaround pattern
out2b = B.r_itm004({"items": [_it(1, "ABCนิ้ว")]}, None, {})
check(len(out2b) > 0, "อังกฤษ+ไทยติดกัน (ABCนิ้ว) → ฟ้อง (เก็บกิ่ง emit)")
out3 = B.r_itm004({"items": [_it(1, "สกรูเหล็ก")]}, None, {})
check(out3 == [], "ชื่อสะอาด → ไม่ฟ้อง")

# ── [B] r_itm010 — THAI_TYPO_PATTERNS emit ─────────────────────────────
print("\n[B] r_itm010 ตรวจสระ/วรรณยุกต์ซ้อน")
o1 = B.r_itm010({"items": [_it(1, "สินค้ากาา")]}, None, {})
check(any("สระซ้อน" in x for x in o1), "สระ า ซ้อน (าา) → ฟ้องสระซ้อน")
o2 = B.r_itm010({"items": [_it(1, "น็อตเหล็ก")]}, None, {})
check(o2 == [], "ชื่อสะอาด → ไม่ฟ้อง")
# หลายรายการ: รายการสะอาด + รายการผิด → ฟ้องเฉพาะที่ผิด
o3 = B.r_itm010({"items": [_it(1, "ปกติ"), _it(2, "ผิดีี")]}, None, {})
check(len(o3) >= 1 and all("#2" in x for x in o3), "ฟ้องเฉพาะรายการที่ผิด (#2)")

# ── สรุป ───────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL:
        print("   ❌", l)
    sys.exit(1)
print("✅ ครบ — กฎ typo (r_itm004/r_itm010) ตรวจพบ+ฟ้องถูกกิ่ง")
