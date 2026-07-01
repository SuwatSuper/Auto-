# -*- coding: utf-8 -*-
"""test_bs3_tax009_samename.py — [BS-3/ADR-116] TAX009 ชื่อเดียวกัน เลขภาษีต่างกัน (cross-bill)

ช่องโหว่: มี TAX008 จับ "เลขเดียว ชื่อต่าง" (สวมเลข) แต่ไม่มีกฎจับทิศกลับ
"ชื่อเดียว เลขต่าง" → ผู้ขายรายเดียวพิมพ์เลขภาษีผิดบางใบ จับไม่ได้.

ตรึง (conservative — false-negative ดีกว่า false-positive):
  • ชื่อ normalize เดียวกัน + เลขภาษี 13 หลัก ≥2 เลข → ฟ้องทุกบิลในกลุ่ม
  • ชื่อต่างเลขต่าง (คนละบริษัท) → เงียบ
  • ชื่อเดียวเลขเดียว → เงียบ ; เลขไม่ครบ 13 หลัก → เงียบ ; ไม่มี all_bills → เงียบ
self-contained: ไม่พึ่ง corpus. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import r_tax009

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _b(company, tax):
    return {"company": company, "tax_id": tax, "tax_id_raw": tax}


def _fires(bill, all_bills):
    return bool(r_tax009(bill, None, {"all_bills_for_iv_check": all_bills}))


TA = "0105540001234"
TB = "0105540009999"

# 1) ฟ้องเคสผิด: ชื่อเดียวกันจริง เลข 13 หลักต่างกัน → ยิงทั้งสองบิล
a1 = _b("บริษัท เอ จำกัด", TA)
a2 = _b("บริษัท เอ จำกัด", TB)
both = [a1, a2]
_check("ชื่อเดียวเลขต่าง → TAX009 ยิง (บิล TA)", _fires(a1, both))
_check("ชื่อเดียวเลขต่าง → TAX009 ยิง (บิล TB)", _fires(a2, both))
_detail = r_tax009(a1, None, {"all_bills_for_iv_check": both})[0]
_check("detail ระบุเลขภาษีทั้งสอง", TA in _detail and TB in _detail)

# 2) เงียบเคสถูก: ชื่อต่างเลขต่าง (คนละบริษัท) → ไม่ฟ้อง
d1 = _b("บริษัท เอ จำกัด", TA)
d2 = _b("บริษัท บี จำกัด", TB)
_check("ชื่อต่างเลขต่าง (คนละบริษัท) → เงียบ", not _fires(d1, [d1, d2]) and not _fires(d2, [d1, d2]))

# 3) ชื่อเดียวเลขเดียว (ผู้ขายปกติหลายใบ) → เงียบ
s1 = _b("บริษัท เอ จำกัด", TA)
s2 = _b("บริษัท เอ จำกัด", TA)
_check("ชื่อเดียวเลขเดียว → เงียบ", not _fires(s1, [s1, s2]))

# 4) ต่างแค่เว้นวรรค (ผู้ขายเดียวกัน) เลขต่าง → ยังฟ้อง (normalize ยุบเว้นวรรค)
w1 = _b("บริษัท เอ จำกัด", TA)
w2 = _b("บริษัท  เอ  จำกัด", TB)
_check("ต่างแค่เว้นวรรค + เลขต่าง → ฟ้อง (ชื่อ normalize ตรง)", _fires(w1, [w1, w2]))

# 5) เลขไม่ครบ 13 หลัก → เงียบ (ปล่อย TAX001 จัดการ)
sh1 = _b("บริษัท เอ จำกัด", "01055")
sh2 = _b("บริษัท เอ จำกัด", "09999")
_check("เลขไม่ครบ 13 หลัก → เงียบ", not _fires(sh1, [sh1, sh2]))

# 6) ไม่มี all_bills_ref → เงียบ ; บิลเดียว → เงียบ
_check("ไม่มี all_bills_ref → เงียบ", not r_tax009(a1, None, {}))
_check("บิลเดียว (ชื่อไม่ซ้ำใคร) → เงียบ", not _fires(a1, [a1]))

# 6b) [ADR-118] กัน over-collapse 'สาขา<คำ>' กลางชื่อ: คนละนิติบุคคลที่ชื่อมีคำขึ้นต้น 'สาขา'
#     + เลขต่าง → ต้อง "เงียบ" (เดิม regex 'สาขา\S*' ยุบ 'สาขาวิชาการ'/'สาขาเกษตร' เป็นชื่อเดียว → false-positive)
fp1 = _b("บริษัท สาขาวิชาการ จำกัด", TA)
fp2 = _b("บริษัท สาขาเกษตร จำกัด", TB)
_check("คนละบริษัทชื่อมีคำ 'สาขา...' + เลขต่าง → เงียบ (ไม่ false-positive)",
       not _fires(fp1, [fp1, fp2]) and not _fires(fp2, [fp1, fp2]))
from rules_engine import r_tax008
def _t8(bill, ab):
    return bool(r_tax008(bill, None, {"all_bills_for_iv_check": ab}))
# 6c) reverse: เลขเดียวสวมคนละบริษัทที่ชื่อมี 'สาขา...' → TAX008 ต้องฟ้อง (เดิม over-collapse → miss)
fn1 = _b("บริษัท สาขาวิชาการ จำกัด", TA)
fn2 = _b("บริษัท สาขาเกษตร จำกัด", TA)
_check("เลขเดียวสวมคนละบริษัท 'สาขา...' → TAX008 ฟ้อง (ไม่ false-negative)", _t8(fn1, [fn1, fn2]))
# 6d) [ADR-118] สนญ. vs 'สาขา 00001' (ผู้ขายเดียวกัน) เลขต่าง → TAX009 ฟ้อง (เดิม residue เลขสาขารั่ว → miss)
br1 = _b("บริษัท เอ จำกัด (สำนักงานใหญ่)", TA)
br2 = _b("บริษัท เอ จำกัด สาขา 00001", TB)
_check("HQ vs 'สาขา 00001' (ผู้ขายเดียว) + เลขต่าง → ฟ้อง (residue เลขสาขาหาย)", _fires(br1, [br1, br2]))

# 7) 3 บิล ชื่อเดียว 3 เลขต่าง → ฟ้อง + นับ 3 เลข
t1 = _b("บริษัท ซี จำกัด", "0105540000011")
t2 = _b("บริษัท ซี จำกัด", "0105540000022")
t3 = _b("บริษัท ซี จำกัด", "0105540000033")
trio = [t1, t2, t3]
_check("3 บิลชื่อเดียว 3 เลข → ฟ้อง", _fires(t1, trio))
_check("detail นับ '3 เลข'", "3 เลข" in r_tax009(t1, None, {"all_bills_for_iv_check": trio})[0])

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] TAX009 ยิงเมื่อชื่อเดียวเลขต่าง + เงียบทุกเคส benign")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
