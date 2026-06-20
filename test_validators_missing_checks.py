# -*- coding: utf-8 -*-
"""test_validators_missing_checks.py — เก็บกิ่งของ 4 กฎ "เอกสารไม่สมบูรณ์" (active rules)

บริบท (จากการตรวจ coverage gate [10]): apply_missing_date_check (DT005) /
apply_missing_iv_check (IV005) / apply_bad_date_check (DT006) /
apply_abbrev_invoice_check (IV006) ถูกเรียกจริงใน pipeline (pukpui_modular_funcs.py
:322-325) แต่ fixture 3 บิล "สะอาด" ไม่ trigger → กิ่ง emit + กิ่ง skip ไม่ถูกตรวจ.

เทสนี้เรียกแต่ละฟังก์ชันตรงๆ ด้วยบิลสังเคราะห์ที่ "จุดชนวน" ทั้ง 2 ฝั่ง:
  • positive (emit): บิลตรงเงื่อนไข → ต้องมี issue code ถูกต้อง
  • guard/skip: บิลที่ควรข้าม (มีค่าแล้ว / บิลเงา/ว่าง / เฉพาะเจาะจงกว่า) → ต้องไม่ฟ้อง
  • idempotent: เรียกซ้ำ 2 ครั้ง → issue ไม่ซ้ำ (docstring การันตี)

เป็น pin/coverage test ล้วน — ไม่แตะ business logic ; golden ไม่ขยับ (ชั้น metadata/ตรวจ).

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_validators_missing_checks.py
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


def _bill(**kw):
    b = {
        "file": "F.xlsx",
        "sheet": "1",
        "block_idx": 0,
        "iv_number": None,
        "iv_date": None,
        "tax_id": "0105500000001",
        "company": "บริษัท ทดสอบ จำกัด",
        "items": [],
        "issues": [],
    }
    b.update(kw)
    return b


def _codes(b):
    return {i.get("code") for i in b.get("issues", [])}


print("=" * 64)
print("VALIDATORS — 4 กฎ 'เอกสารไม่สมบูรณ์' (DT005/IV005/DT006/IV006)")
print("=" * 64)

# ── [A] DT005 — apply_missing_date_check ───────────────────────────────
print("\n[A] DT005 บิลไม่มีวันที่")
b_emit = _bill(iv_number="00123", iv_date=None)            # ไม่มีวันที่ + เป็นบิลจริง → emit
b_has_date = _bill(iv_number="00124", iv_date="x")          # มี iv_date → skip
b_baddate = _bill(iv_number="00125", _bad_date="31/04/2026")  # _bad_date → ให้ DT006 จัดการ → skip
b_shadow = _bill(iv_number=None, items=[], total=None)      # บิลเงา (ไม่มี iv/items/total) → skip
V.apply_missing_date_check([b_emit, b_has_date, b_baddate, b_shadow])
check("DT005" in _codes(b_emit), "บิลไม่มีวันที่ → ฟ้อง DT005")
check("DT005" not in _codes(b_has_date), "มี iv_date → ไม่ฟ้อง")
check("DT005" not in _codes(b_baddate), "_bad_date → ปล่อยให้ DT006 (ไม่ฟ้อง DT005 ซ้ำซ้อน)")
check("DT005" not in _codes(b_shadow), "บิลเงา/ว่าง → ไม่ฟ้อง")
# idempotent
V.apply_missing_date_check([b_emit])
check(sum(1 for i in b_emit["issues"] if i.get("code") == "DT005") == 1, "DT005 idempotent (เรียกซ้ำไม่ซ้ำ)")

# ── [B] IV005 — apply_missing_iv_check ─────────────────────────────────
print("\n[B] IV005 บิลไม่มีเลขที่ใบกำกับ")
b_noiv = _bill(iv_number=None, total=1000.0)               # ไม่มีเลข + มียอด → emit
b_noiv_items = _bill(iv_number="", items=[{"seq": 1}])     # iv ว่าง + มีรายการ → emit
b_hasiv = _bill(iv_number="00200", total=1000.0)           # มีเลข → skip
b_blank = _bill(iv_number=" ", items=[], total=None, subtotal=None)  # iv เว้นวรรค + บิลว่าง → skip
V.apply_missing_iv_check([b_noiv, b_noiv_items, b_hasiv, b_blank])
check("IV005" in _codes(b_noiv), "ไม่มีเลข+มียอด → ฟ้อง IV005")
check("IV005" in _codes(b_noiv_items), "เลขว่าง+มีรายการ → ฟ้อง IV005")
check("IV005" not in _codes(b_hasiv), "มีเลขใบกำกับ → ไม่ฟ้อง")
check("IV005" not in _codes(b_blank), "บิลว่าง (ไม่มีรายการ/ยอด) → ไม่ฟ้อง")

# ── [C] DT006 — apply_bad_date_check ───────────────────────────────────
print("\n[C] DT006 วันที่ไม่มีจริงในปฏิทิน")
b_bad = _bill(iv_number="00300", _bad_date="31/04/2026", iv_date=None)   # มี _bad_date + ไม่มี iv_date → emit
b_nobad = _bill(iv_number="00301", iv_date="ok")                          # ไม่มี _bad_date → skip
b_bad_resolved = _bill(iv_number="00302", _bad_date="30/02/2026", iv_date="ok")  # _bad_date แต่ parse iv_date ได้ → skip
V.apply_bad_date_check([b_bad, b_nobad, b_bad_resolved])
check("DT006" in _codes(b_bad), "_bad_date + ไม่มี iv_date → ฟ้อง DT006")
check("DT006" not in _codes(b_nobad), "ไม่มี _bad_date → ไม่ฟ้อง")
check("DT006" not in _codes(b_bad_resolved), "มี iv_date แล้ว → ไม่ฟ้อง")

# ── [D] IV006 — apply_abbrev_invoice_check ─────────────────────────────
print("\n[D] IV006 ใบกำกับภาษีอย่างย่อ")
b_abbrev = _bill(iv_number="00400", _abbrev=True)          # อย่างย่อ → emit
b_full = _bill(iv_number="00401", _abbrev=False)           # เต็มรูป → skip
V.apply_abbrev_invoice_check([b_abbrev, b_full])
check("IV006" in _codes(b_abbrev), "ใบกำกับอย่างย่อ → ฟ้อง IV006")
check("IV006" not in _codes(b_full), "ใบกำกับเต็มรูป → ไม่ฟ้อง")

# ── สรุป ───────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL:
        print("   ❌", l)
    sys.exit(1)
print("✅ ครบ — 4 กฎเอกสารไม่สมบูรณ์ทำงานถูก (emit/skip/idempotent)")
