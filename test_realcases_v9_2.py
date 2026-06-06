# -*- coding: utf-8 -*-
"""test_realcases_v9_2.py — ตรึงเคสจริงที่ลูกค้ารายงาน (KRR/STC/TKH 69.05)

กันบั๊กกลับสำหรับ false-positive ที่เคยทำให้รายงาน "บิลถูกดูเหมือนผิดหมด":
  R1  double-count: บิล AKT (TKH CB69050671) ผลรวมรายการ = subtotal (242,955) — ไม่เด้ง VAT001
  R2  ยอดตัวอักษรไทย (เช่น "สองแสนห้าหมื่น...") ไม่ถูกนับเป็นรายการสินค้า
  R3  ITM008 (ราคา/หน่วยผิดปกติ + "0.0×") ต้อง "ไม่เด้ง" — ของถูก (ราคา 3 บาท × 500)
  R4  HAI UNION → ต้องจับเป็น "น่าจะเป็น THAI UNION" (STC)
  R5  รายงานลูกค้า: ตัด noise (เดาหน่วย/เว้นวรรค) ออก แต่คงคำผิดจริง (HAI UNION)

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_realcases_v9_2.py
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

import parser as P
import rules_engine as RE
from master import load_master
from agents.vendor_report import build_vendor_reports
from parser_p0 import _is_thai_amount_words

CASE_DIR = os.path.join(HERE, "tests", "real_cases")
FILES = ["KRR_69_05.xls", "STC_69_05.xls", "TKH_69_05.xls"]

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


print("=" * 64)
print("REAL CASES v9.2 — ตรึง false-positive ที่ลูกค้ารายงาน")
print("=" * 64)

master = load_master() or {}
by_file = {}
all_bills = []
with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    for fn in FILES:
        bills = P.parse_file(os.path.join(CASE_DIR, fn))
        for b in bills:
            b.setdefault("issues", [])
            RE.run_rules(b, master, {"month": None, "month_end": None})
        by_file[fn] = bills
        all_bills += bills


def _items_sum(b):
    return sum(float(it.get("amount") or 0) for it in (b.get("items") or []))


def _find_bill(iv):
    return next((b for b in all_bills if (b.get("iv_number") or "") == iv), None)


# ── R1: double-count หาย — บิล AKT CB69050671 ผลรวมรายการ = subtotal ──
akt = _find_bill("CB69050671")
check(akt is not None, "พบบิล AKT CB69050671 (TKH)")
if akt:
    isum, sub = _items_sum(akt), float(akt.get("subtotal") or 0)
    check(abs(isum - sub) < 1.0, f"ผลรวมรายการ ({isum:,.2f}) = subtotal ({sub:,.2f}) — ไม่ double-count")
    check(abs(sub - 242955.0) < 1.0, f"subtotal = 242,955 ตามบิลจริง (ได้ {sub:,.2f})")
    vat_gap = [i for i in akt.get("issues", []) if i.get("code", "").startswith("VAT001")]
    check(not vat_gap, "บิล AKT ไม่เด้ง VAT001 (ผลรวมรายการ≠subtotal)")

# ── R2: ยอดตัวอักษรไทย ไม่ถูกนับเป็นรายการ ──
word_items = []
for b in all_bills:
    for it in b.get("items") or []:
        nm = str(it.get("name") or "")
        if _is_thai_amount_words(nm):
            word_items.append((b.get("file"), b.get("iv_number"), nm[:30]))
check(not word_items, f"ไม่มี 'ยอดตัวอักษรไทย' ถูกนับเป็นรายการ (พบ {len(word_items)})")

# ── R3: ITM008 ต้องไม่เด้ง (ปิดแล้ว) — รวมถึงไฟล์ที่มีราคา 3 บาท ──
itm008 = [
    (b.get("file"), i.get("detail"))
    for b in all_bills
    for i in b.get("issues", [])
    if i.get("code", "").startswith("ITM008")
]
check(RE.RULES.get("ITM008", {}).get("enabled") is False, "RULES['ITM008'].enabled = False")
check(not itm008, f"ITM008 (ราคา/หน่วยผิดปกติ + 0.0×) ไม่เด้งเลย (พบ {len(itm008)})")

# ── R4: HAI UNION → THAI UNION ถูกจับ ──
hai = [
    (b.get("file"), b.get("iv_number"), i.get("detail"))
    for b in all_bills
    for i in b.get("issues", [])
    if "THAI UNION" in (i.get("detail") or "")
]
check(len(hai) >= 1, f"จับ HAI UNION → 'น่าจะเป็น THAI UNION' ได้ (พบ {len(hai)} จุด)")

# ── R5: รายงานลูกค้า — ตัด noise คงคำผิดจริง ──
reps = build_vendor_reports(all_bills, None, master)
joined = "\n".join(t for _, t in reps)
check("คำว่า HAI UNION" in joined, "รายงานชี้คำผิดจริงแบบภาษาคน ('คำว่า HAI UNION')")
check("รายการสินค้า ลำดับที่" in joined, "รายงานใช้สำนวน 'รายการสินค้า ลำดับที่ N'")
check('สะกดตก T' not in joined, "รายงานไม่มีสำนวนเชิงเครื่อง '(สะกดตก T)'")
check("_69_05.xls" not in joined, "รายงานใช้ prefix สั้น (ไม่มีชื่อไฟล์เต็ม .xls)")
check("อาจไม่เหมาะ" not in joined, "รายงานตัด noise เดาหน่วย ('อาจไม่เหมาะ') ออก")
check("ติดกัน" not in joined, "รายงานตัด noise เว้นวรรค ('ติดกัน') ออก")
check("[soft]" not in joined, "รายงานไม่มี marker '[soft]'")
# ยอดในรายงาน = ก่อน VAT (subtotal) — ตรวจว่าบรรทัดยอดมีและเป็น 'ตรง' (ไม่มี gap จริง)
amount_lines = [l for t in (t for _, t in reps) for l in t.splitlines() if l.startswith("ยอด : ")]
check(all("บาท" in l for l in amount_lines) and len(amount_lines) == len(reps), "ทุกรายงานมีบรรทัด 'ยอด : ... บาท'")


print("\n" + "=" * 64)
print(f"REAL CASES: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ เคสจริงที่ลูกค้ารายงานถูกตรึงครบ (ไม่มี false-positive)")
sys.exit(0)
