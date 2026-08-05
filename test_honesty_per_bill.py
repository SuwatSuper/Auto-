# -*- coding: utf-8 -*-
"""test_honesty_per_bill.py — [A1] honesty รายผู้ขาย/รายบิล (ไม่พึ่ง corpus จริง)

พิสูจน์หัวใจของ A1: คำว่า "ตรง" = "เทียบ master จริงแล้วตรง" เท่านั้น — ไม่ใช่ "ไม่ได้เช็ค".
ตัดสินทีละผู้ขาย×เดือน จากสัญญาณรายบิล b['master_key'] (จาก match_company) ไม่ใช่ flag global ตัวเดียว.

ตรึง 4 สัญญา:
  1) master ว่าง → ช่องตัวตนครบ 4 (ชื่อ/เลขภาษี/ที่อยู่/สาขา) = "ตรวจไม่ได้" (ไม่มีใน master) ทุกผู้ขาย
  2) ใส่ผู้ขาย X เข้า master → "เฉพาะ X" verified (ตรง) ; ผู้ขายอื่น (Y) ยัง "ตรวจไม่ได้"
     → รองรับบริษัทใหม่อัตโนมัติ: เพิ่ม master แล้วบิลสลับ "ตรวจไม่ได้"→verified โดย "ไม่ต้องแก้โค้ด"
  3) เจอผู้ขายแต่ทะเบียนไม่มีข้อมูลช่องนั้น (เช่น master ไม่มี address) → "ทะเบียนไม่มีข้อมูลช่องนี้ (ตรวจไม่ได้)"
  4) บิลเองอ่านช่องนั้นไม่ติด (ค่าว่าง) → "อ่านจากบิลไม่ได้ (ตรวจไม่ได้)"

ใช้ match_company จริง (= ตรรกะเดียวกับที่ run_rules ใช้ตั้ง master_key) — advisory ล้วน, golden ไม่ขยับ.
exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import super_ultra_viewer as SUV
from rules_engine import match_company

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _tag(bill, master):
    """จำลอง 2 บรรทัดใน run_rules: ตั้ง master_key/match_score จาก match_company จริง."""
    key, _m, score = match_company(bill.get("company", ""), master)
    bill["master_key"] = key or "(ไม่พบใน master)"
    bill["match_score"] = score
    return bill


def _bill(company, tax_id, address="123 ถนนทดสอบ แขวงทดสอบ เขตทดสอบ กรุงเทพมหานคร 10000",
          branch="สำนักงานใหญ่", file="X.xls"):
    return {"file": file, "sheet": "1", "company": company, "company_raw": company,
            "tax_id": tax_id, "branch": branch, "branch_no": "00000", "address": address,
            "iv_number": "IV1", "iv_date": datetime(2026, 5, 1),
            "total": 1070.0, "vat": 70.0, "subtotal": 1000.0, "items": [], "issues": []}


# master ผู้ขาย X (ครบทุกช่อง — ทะเบียนสมบูรณ์)
MASTER_X_FULL = {
    "เอ็กซ์": {
        "name": "บริษัท เอ็กซ์ จำกัด", "name_alt": "เอ็กซ์",
        "tax_id": "0105556000010", "branch": "สำนักงานใหญ่", "branch_no": "00000",
        "address": "9 ถนนเอ็กซ์ กรุงเทพมหานคร 10110",
        "address_full": "9 ถนนเอ็กซ์ กรุงเทพมหานคร 10110",
        "address_parts": {"zip": "10110", "province": "กรุงเทพมหานคร"},
    }
}

IDENTITY = ["ชื่อบจ.", "เลขที่ผู้เสียภาษี", "ที่อยู่", "สาขา/สนญ."]


def _verdicts_for(rows, company):
    for r in rows:
        if r["company"] == company:
            return r["verdicts"]
    return None


# ── สัญญา 1: master ว่าง → ทุกตัวตน "ตรวจไม่ได้" ──────────────────────────────
print("[1] master ว่าง → ทุกช่องตัวตน 'ตรวจไม่ได้' (ไม่มีใน master)")
bx = _tag(_bill("บริษัท เอ็กซ์ จำกัด", "0105556000010"), {})
by = _tag(_bill("บริษัท วาย ดิฟเฟอเรนต์ โฮลดิ้ง จำกัด", "0105556999999", file="Y.xls"), {})
rows0 = SUV.build([bx, by], master_present=False, masters={})
for comp in ("บริษัท เอ็กซ์ จำกัด", "บริษัท วาย ดิฟเฟอเรนต์ โฮลดิ้ง จำกัด"):
    v = _verdicts_for(rows0, comp)
    for f in IDENTITY:
        _check(f"empty-master: {comp[:14]}… ช่อง {f} = 'ตรวจไม่ได้'",
               v is not None and "ตรวจไม่ได้" in v[f]["status"]
               and "ไม่มีใน master" in v[f]["status"] and v[f]["mark"] == "master")

# ── สัญญา 2: ใส่ผู้ขาย X → X verified, Y ยัง "ตรวจไม่ได้" (รองรับบริษัทใหม่ ไม่ต้องแก้โค้ด) ──
print("[2] ใส่ master X → เฉพาะ X verified ('ตรง') ; Y ยัง 'ตรวจไม่ได้'")
bx2 = _tag(_bill("บริษัท เอ็กซ์ จำกัด", "0105556000010"), MASTER_X_FULL)
by2 = _tag(_bill("บริษัท วาย ดิฟเฟอเรนต์ โฮลดิ้ง จำกัด", "0105556999999", file="Y.xls"), MASTER_X_FULL)
_check("X จับ master ได้ (master_key ≠ '(ไม่พบใน master)')", bx2["master_key"] != "(ไม่พบใน master)")
_check("Y ไม่อยู่ใน master (master_key = '(ไม่พบใน master)')", by2["master_key"] == "(ไม่พบใน master)")
rows1 = SUV.build([bx2, by2], master_present=True, masters=MASTER_X_FULL)
vx = _verdicts_for(rows1, "บริษัท เอ็กซ์ จำกัด")
vy = _verdicts_for(rows1, "บริษัท วาย ดิฟเฟอเรนต์ โฮลดิ้ง จำกัด")
for f in IDENTITY:
    _check(f"X verified: ช่อง {f} = 'ตรง' (เทียบ master จริงแล้วตรง)",
           vx is not None and vx[f]["status"] == "ตรง" and vx[f]["mark"] == "ok")
    _check(f"Y ยัง 'ตรวจไม่ได้': ช่อง {f}",
           vy is not None and "ตรวจไม่ได้" in vy[f]["status"] and vy[f]["mark"] == "master")

# ── สัญญา 3: เจอผู้ขายแต่ทะเบียนไม่มี address → "ทะเบียนไม่มีข้อมูลช่องนี้" ──────────
print("[3] master X ไม่มี address → ช่องที่อยู่ = 'ทะเบียนไม่มีข้อมูลช่องนี้ (ตรวจไม่ได้)'")
master_x_noaddr = {"เอ็กซ์": {"name": "บริษัท เอ็กซ์ จำกัด", "name_alt": "เอ็กซ์",
                              "tax_id": "0105556000010", "branch": "สำนักงานใหญ่", "branch_no": "00000"}}
bx3 = _tag(_bill("บริษัท เอ็กซ์ จำกัด", "0105556000010"), master_x_noaddr)
rows2 = SUV.build([bx3], master_present=True, masters=master_x_noaddr)
v3 = rows2[0]["verdicts"]
_check("addr: 'ทะเบียนไม่มีข้อมูลช่องนี้ (ตรวจไม่ได้)'",
       "ทะเบียนไม่มีข้อมูลช่องนี้" in v3["ที่อยู่"]["status"] and v3["ที่อยู่"]["mark"] == "master")
_check("แต่ชื่อบจ. ยัง verified ('ตรง') เพราะทะเบียนมีชื่อ", v3["ชื่อบจ."]["status"] == "ตรง")

# ── สัญญา 4: บิลอ่านช่องไม่ติด (ที่อยู่ว่าง) → "อ่านจากบิลไม่ได้" ───────────────────
print("[4] บิลที่อยู่ว่าง (matched) → ช่องที่อยู่ = 'อ่านจากบิลไม่ได้ (ตรวจไม่ได้)'")
bx4 = _tag(_bill("บริษัท เอ็กซ์ จำกัด", "0105556000010", address=""), MASTER_X_FULL)
rows3 = SUV.build([bx4], master_present=True, masters=MASTER_X_FULL)
v4 = rows3[0]["verdicts"]
_check("addr ว่าง: 'อ่านจากบิลไม่ได้ (ตรวจไม่ได้)'",
       "อ่านจากบิลไม่ได้" in v4["ที่อยู่"]["status"] and v4["ที่อยู่"]["mark"] == "master")

# ── ตรวจซ้ำ: ช่องที่ "ไม่พึ่ง master" (เลขที่ iv / รายการ / ยอด) ไม่ถูก downgrade ─────────
print("[5] ช่องที่ไม่ใช่ตัวตน (ไม่พึ่ง master) ต้องไม่โดน downgrade")
v_iv = _verdicts_for(rows0, "บริษัท เอ็กซ์ จำกัด")
_check("เลขที่ iv ยัง 'ตรง' แม้ไม่มี master (ไม่ใช่ช่องตัวตน)", v_iv["เลขที่ iv"]["status"] == "ตรง")

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] honesty รายผู้ขาย/รายบิล ครบ — 'ตรง' = เทียบ master จริงเท่านั้น")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
