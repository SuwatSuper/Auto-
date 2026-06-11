# -*- coding: utf-8 -*-
"""test_report_precision.py — Precision Council (รีพอร์ตพร้อมส่งลูกค้า) 10 ผู้ตรวจ + 2-tier

ตรึง: แต่ละผู้ตรวจให้ verdict ถูก (CONFIRM/RECHECK/ABSTAIN) + council รวมเป็น tier
  'clear' (เข้ารีพอร์ตหลัก) / 'soft' (ยกไป "ตรวจตาเพิ่ม") ตาม precision-first.
  โดยเฉพาะ fuzzy: ITM010 = ชัด (clear) ; ITM011 'ใกล้เคียง (ตรวจสอบ)' = ก้ำกึ่ง (soft).

advisory ล้วน — ไม่แตะ golden. self-contained (import แค่ report_precision).
    PYTHONHASHSEED=0 python3 test_report_precision.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import report_precision as RP

PASS, FAIL = 0, []


def chk(cond, label):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def _e(code, **kw):
    """fixlist entry สังเคราะห์."""
    d = {"code": code, "field": kw.get("field", "รายการสินค้า"), "detail": kw.get("detail", ""),
         "type": kw.get("type", ""), "seq": kw.get("seq", "1"), "file": kw.get("file", "F.xls"),
         "sheet": kw.get("sheet", "1"), "date": kw.get("date", "06/05/2026")}
    return d


def tier(code, bill=None, fixlist=None, master=True, **kw):
    e = _e(code, **kw)
    return RP.council_review(e, bill=bill, fixlist=fixlist or [e], master_present=master)["tier"]


print("PRECISION COUNCIL — 10 ผู้ตรวจ + 2-tier (advisory, golden-neutral)")

# มี 10 ผู้ตรวจจริง
chk(len(RP.COUNCIL) == 10, "มีผู้ตรวจครบ 10 ตัว")

# 1) typo: ITM010 ชัด → clear ; ITM011 'ใกล้เคียง (ตรวจสอบ)' → soft ; ITM011 มั่นใจสูง → clear
chk(tier("ITM010", detail='#2: "มั้วน" → "ม้วน"') == "clear", "ITM010 (typo ชัด) → clear")
chk(tier("ITM011", detail='#3: "เจียร" ใกล้เคียง (ตรวจสอบ) "เจียร์"') == "soft",
    "ITM011 'ใกล้เคียง (ตรวจสอบ)' → soft")
chk(tier("ITM011", detail='#3: "เจียร" → "เจียร์"') == "clear", "ITM011 มั่นใจสูง → clear")

# 2) unit: ITM015 (เหล็กเพลท/เส้น) → CONFIRM
v, _ = RP.a_unit_sanity(_e("ITM015"), {}, {})
chk(v == RP.CONFIRM, "a_unit_sanity ITM015 → CONFIRM")

# 3) taxid: บิล taxid พัง (checksum) → clear ; ไม่มีบิล → soft (ต้องเทียบ master)
chk(tier("TAX006", field="เลขที่ผู้เสียภาษี", bill={"tax_id": "1111111111111"}) == "clear",
    "เลขภาษี checksum พัง → clear")
chk(tier("TAX006", field="เลขที่ผู้เสียภาษี", bill={"tax_id": ""}) == "soft",
    "ไม่มีเลขภาษีให้ตรวจซ้ำ → soft")

# 4) name: CMP005 (ขาด 'จำกัด') → clear ; CMP001 (เทียบ master) + ไม่มี master → soft
chk(tier("CMP005", field="ชื่อบจ.") == "clear", "CMP005 (ขาดจำกัด) → clear")
chk(tier("CMP001", field="ชื่อบจ.", master=False) == "soft", "CMP001 + ไม่มี master → soft")
# CMP001 = ชื่อต่าง master แบบ fuzzy → precision-first คงเป็น soft แม้มี master (ขอตาคนยืนยัน ไม่ฟันธงส่งลูกค้า)
chk(tier("CMP001", field="ชื่อบจ.", master=True) == "soft", "CMP001 + มี master → soft (fuzzy ชื่อ ก้ำกึ่ง)")

# 5) seq: ITM002 → clear
chk(tier("ITM002") == "clear", "ITM002 (ลำดับหาย) → clear")

# 6) amount presence: detail บอกยอดหาย → CONFIRM
v, _ = RP.a_amount_presence(_e("ITMx", detail="ยอดเงินรายการหาย"), {}, {})
chk(v == RP.CONFIRM, "a_amount_presence 'ยอด...หาย' → CONFIRM")

# 7) reconcile: Σรายการ ≠ subtotal → CONFIRM
bill_recon = {"items": [{"qty": 2, "price": 100}, {"qty": 1, "price": 50}], "subtotal": 999.0}
v, _ = RP.a_subtotal_reconcile(_e("ITMx", field="ยอดก่อน vat"), bill_recon, {})
chk(v == RP.CONFIRM, "a_subtotal_reconcile Σ≠subtotal → CONFIRM")
bill_ok = {"items": [{"qty": 2, "price": 100}], "subtotal": 200.0}
v, _ = RP.a_subtotal_reconcile(_e("ITMx", field="ยอดก่อน vat"), bill_ok, {})
chk(v == RP.ABSTAIN, "a_subtotal_reconcile Σ=subtotal → ABSTAIN")

# 8) empty items: ไม่มี items แต่มียอด → CONFIRM
v, _ = RP.a_empty_items(_e("ITMx", field="รายการสินค้า"), {"items": [], "total": 500}, {})
chk(v == RP.CONFIRM, "a_empty_items (0 รายการ + มียอด) → CONFIRM")

# 9) consensus: ≥2 รหัสจุดเดียวกัน → upgrade RECHECK→clear
soft_pt = _e("ITM011", detail="ใกล้เคียง (ตรวจสอบ)", seq="3")
sibling = _e("ITM010", detail='"x"→"y"', seq="3")     # จุดเดียวกัน (file/date/seq เดียว)
chk(RP.council_review(soft_pt, fixlist=[soft_pt, sibling])["tier"] == "clear",
    "consensus: 2 รหัสจุดเดียว → upgrade เป็น clear")

# 10) structural default vs unknown
chk(tier("IV002", field="เลขที่ iv") == "clear", "IV002 (structural) ไม่มีผู้ตรวจเฉพาะ → clear")
chk(tier("ZZZ999", field="อื่น") == "soft", "รหัสไม่รู้จัก + ไม่มีผู้ตรวจ → soft (กันพลาดส่งลูกค้า)")

# annotate_tiers ติด tier ให้ทุก entry
fl = [_e("ITM010", detail='"a"→"b"'), _e("ITM011", detail="ใกล้เคียง (ตรวจสอบ)", seq="2")]
RP.annotate_tiers(fl, bill_lookup={}, master_present=True)
chk(all("tier" in e and "council" in e for e in fl), "annotate_tiers ติด tier+council ครบทุก entry")
chk(fl[0]["tier"] == "clear" and fl[1]["tier"] == "soft", "annotate_tiers: ITM010=clear, ITM011ก้ำกึ่ง=soft")

print("=" * 60)
if not FAIL:
    print(f"RESULT: ✅ Precision Council ทำงานถูก — ผ่าน {PASS} เคส (10 ผู้ตรวจ + 2-tier)")
    sys.exit(0)
print(f"RESULT: ❌ ไม่ผ่าน {len(FAIL)}/{PASS + len(FAIL)} เคส")
sys.exit(1)
