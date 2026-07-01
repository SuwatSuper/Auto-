# -*- coding: utf-8 -*-
"""test_bs2_vat011_zero.py — [BS-2/ADR-115] VAT011 ใบมียอดแต่ VAT=0 (ยกเว้นจริง/ลืมคิด?)

ช่องโหว่: ใบ pre-VAT=N, VAT=0, total=N (ไม่ได้บวก VAT) เงียบทุกกฎ —
  VAT008 เงียบเมื่อ sub≈total (เดาว่า "ยกเว้น VAT จริง") → ใบ "ลืมคิด VAT" หลุด.
VAT011 เติมรูนั้นเป็น REVIEW "ยกเว้นภาษีจริงหรือลืมคิด?" (ไม่ใช่ ERROR — บางใบ zero-rated จริง).

เกณฑ์ (เจ้าของเคาะ BS-2): subtotal ≥ 1,000 บาท — กัน noise ใบจิ๋ว/ของแถม.
ตรึง: ฟ้องเคสผิด (≥เกณฑ์ + vat≈0 + total≈sub) ; เงียบใบถูก (vat 7%) / ใต้เกณฑ์ / total≠sub ;
      เป็นเลน REVIEW (ข้อสังเกต ไม่ใช่ must-fix) ; ไม่ทับ VAT008.
self-contained: ไม่พึ่ง corpus. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import r_vat011, r_vat008
from config import REVIEW_CODES

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _b(sub, vat, tot, items=True):
    it = [{"seq": 1, "name": "สินค้า", "qty": 1, "unit": "ชิ้น", "price": sub, "amount": sub}] if items else []
    return {"subtotal": sub, "vat": vat, "total": tot, "items": it}


def _fires(b):
    return bool(r_vat011(b, None, {}))


# 1) ฟ้องเคสผิด: ยอด ≥ เกณฑ์ + VAT=0 + total≈subtotal
_check("sub=2000 vat=0 total=2000 → ฟ้อง", _fires(_b(2000, 0, 2000)))
_check("sub=1000 (ที่เกณฑ์พอดี) vat=0 total=1000 → ฟ้อง", _fires(_b(1000, 0, 1000)))
_check("detail บอกยอด + ถาม 'ยกเว้น/ลืมคิด'",
       "ลืมคิด" in r_vat011(_b(2000, 0, 2000), None, {})[0])

# 2) เงียบใบถูก: VAT 7% ถูกต้อง (total = sub×1.07) → ไม่ฟ้อง
_check("sub=2000 vat=140 total=2140 (vat 7% ถูก) → เงียบ", not _fires(_b(2000, 140, 2140)))
# vat ปัดเศษ ≤0.50 บนใบที่บวก VAT จริง (total≠sub) → เงียบ
_check("vat=0.30 แต่ total≠sub (total=2140) → เงียบ", not _fires(_b(2000, 0.30, 2140)))

# 3) เงียบใต้เกณฑ์: ยอดต่ำ (กัน noise ใบจิ๋ว/ของแถม)
_check("sub=100 vat=0 total=100 (ใต้เกณฑ์) → เงียบ", not _fires(_b(100, 0, 100)))
_check("sub=999 vat=0 total=999 (ใต้เกณฑ์) → เงียบ", not _fires(_b(999, 0, 999)))

# 4) เงียบเมื่อข้อมูลไม่พอ/ไม่ใช่เคสนี้
_check("ไม่มีรายการ → เงียบ", not _fires(_b(2000, 0, 2000, items=False)))
_check("subtotal=None → เงียบ", not _fires(_b(None, 0, 2000)))
_check("total=None → เงียบ", not _fires(_b(2000, 0, None)))
_check("total≠subtotal (มี VAT ในยอด) → เงียบ", not _fires(_b(2000, 0, 2140)))

# 5) เลน REVIEW (ข้อสังเกต ไม่ใช่ must-fix)
_check("VAT011 อยู่ใน REVIEW_CODES (เลนข้อสังเกต)", "VAT011" in REVIEW_CODES)

# 6) ไม่ทับ VAT008: ที่ที่ VAT011 ฟ้อง (sub≈total) VAT008 ต้องเงียบ (exempt guard) → ไม่ double-fire
hi = _b(20000, 0, 20000)
_check("sub≈total ยอดสูง: VAT008 เงียบ (exempt guard)", not r_vat008(hi, None, {}))
_check("sub≈total ยอดสูง: VAT011 ฟ้อง (เติมรู VAT008)", _fires(hi))

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] VAT011 ฟ้องใบมียอดแต่ VAT=0 (≥เกณฑ์) + เงียบใบถูก/ใต้เกณฑ์")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
