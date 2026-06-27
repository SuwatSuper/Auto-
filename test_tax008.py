# -*- coding: utf-8 -*-
"""test_tax008.py — [B1] negative fixture: TAX008 เลขภาษีเดียวกันแต่ชื่อบริษัทต่างกัน

ไม่พึ่ง corpus จริง — ปั้นบิลทดสอบ. ตรึง:
  • เลขภาษี 13 หลักตัวเดียว ใต้ 2 ชื่อ "ต่างกันจริง" → TAX008 ยิง (ทั้งสองบิล)
  • ต่างแค่ เว้นวรรค / (สำนักงานใหญ่) / สาขา / ลำดับคำ / ย่อ-เต็ม → เงียบ (ชื่อเดียวกัน)
  • tax ไม่ครบ 13 หลัก → เงียบ ; ไม่มี all_bills_ref → เงียบ ; คนละ tax → เงียบ

conservative: false-negative ดีกว่า false-positive. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import r_tax008

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _b(company, tax):
    return {"company": company, "tax_id": tax, "tax_id_raw": tax}


def _fires(bill, all_bills):
    return bool(r_tax008(bill, None, {"all_bills_for_iv_check": all_bills}))


TAX = "0105556000010"      # 13 หลัก checksum-agnostic (กฎไม่เช็ค checksum — แค่ความยาว)

# 1) เลขเดียว 2 ชื่อต่างกันจริง (เจ.อาร์. vs ฉีหยวน) → ยิงทั้งคู่
jr = _b("บริษัท เจ.อาร์. คอนสตรัคชั่น จำกัด", TAX)
qy = _b("บริษัท ฉีหยวน กรุ๊ป จำกัด", TAX)
both = [jr, qy]
_check("เลขเดียว 2 ชื่อต่างกันจริง → TAX008 ยิง (บิล เจ.อาร์.)", _fires(jr, both))
_check("เลขเดียว 2 ชื่อต่างกันจริง → TAX008 ยิง (บิล ฉีหยวน)", _fires(qy, both))
_detail = r_tax008(jr, None, {"all_bills_for_iv_check": both})[0]
_check("detail ระบุเลขภาษี + ชื่อที่ขัดกัน", TAX in _detail and "ฉีหยวน" in _detail)

# 2) ต่างแค่ (สำนักงานใหญ่) / สาขา → เงียบ (บริษัทเดียวกัน)
hq = _b("บริษัท เอ บี ซี จำกัด (สำนักงานใหญ่)", TAX)
br = _b("บริษัท เอ บี ซี จำกัด สาขา 00001", TAX)
_check("ต่างแค่ (สำนักงานใหญ่)/สาขา → เงียบ", not _fires(hq, [hq, br]) and not _fires(br, [hq, br]))

# 3) ต่างแค่เว้นวรรค / ลำดับคำ → เงียบ
sp1 = _b("บริษัท เอ บี ซี จำกัด", TAX)
sp2 = _b("บริษัท  เอ บี ซี  จำกัด", TAX)        # เว้นวรรคเกิน
_check("ต่างแค่เว้นวรรค → เงียบ", not _fires(sp1, [sp1, sp2]))

# 4) ย่อ-เต็ม (substring) → เงียบ
full = _b("บริษัท เจ.อาร์. คอนสตรัคชั่น จำกัด", TAX)
abbr = _b("เจ.อาร์. คอนสตรัคชั่น", TAX)
_check("ย่อ-เต็ม (substring) → เงียบ", not _fires(full, [full, abbr]))

# 5) tax ไม่ครบ 13 หลัก → เงียบ (ปล่อย TAX001 จัดการ)
short1 = _b("บริษัท เอ จำกัด", "01055")
short2 = _b("บริษัท บี จำกัด", "01055")
_check("tax ไม่ครบ 13 หลัก → เงียบ", not _fires(short1, [short1, short2]))

# 6) ไม่มี all_bills_ref → เงียบ
_check("ไม่มี all_bills_ref → เงียบ", not r_tax008(jr, None, {}))

# 7) คนละ tax → เงียบ (ไม่ปนข้ามเลขภาษี)
o1 = _b("บริษัท เอ จำกัด", TAX)
o2 = _b("บริษัท บี จำกัด", "0105556000027")
_check("คนละ tax → เงียบ", not _fires(o1, [o1, o2]))

# 8) บิลเดียว (ไม่มีคู่เทียบ) → เงียบ
_check("บิลเดียว (เลขไม่ซ้ำใคร) → เงียบ", not _fires(jr, [jr]))

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] TAX008 ยิงเมื่อชื่อต่างจริง + เงียบทุกเคส benign")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
