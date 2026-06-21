# -*- coding: utf-8 -*-
"""test_br004.py — [B3] negative fixture: BR004 เทียบสาขาในบิลกับทะเบียน master

ไม่พึ่ง corpus จริง. ตรึง:
  • master มี branch + บิลใส่สาขาต่าง → BR004 ยิง
  • บิลตรง master (HQ↔HQ / สาขาเลขเดียวกัน) → เงียบ
  • ไม่มี master (m=None) → ไม่ยิง (ตกไป honesty A1 = ช่องสาขา 'ตรวจไม่ได้')
  • master ไม่มี branch / บิลระบุสาขาไม่ชัด → เงียบ (conservative)
  • รองรับรูปสาขาหลากหลาย (branch_no 5 หลัก / label 'สำนักงานใหญ่' / 'สาขา 00007')

exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import r_br004

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _fires(bill, master):
    return bool(r_br004(bill, master, {}))


HQ_MASTER = {"name": "บริษัท เอ จำกัด", "branch": "สำนักงานใหญ่", "branch_no": "00000"}
BR5_MASTER = {"name": "บริษัท บี จำกัด", "branch": "สาขา 00005", "branch_no": "00005"}
NOBR_MASTER = {"name": "บริษัท ซี จำกัด"}   # ทะเบียนไม่มี branch

# 1) master HQ, บิลสาขา 00001 → ยิง
_check("master สนญ. + บิลสาขา 00001 → BR004 ยิง",
       _fires({"branch": "สาขา 00001", "branch_no": "00001"}, HQ_MASTER))
_d = r_br004({"branch": "สาขา 00001", "branch_no": "00001"}, HQ_MASTER, {})[0]
_check("detail ระบุ สาขาบิล vs ทะเบียน", "00001" in _d and "สำนักงานใหญ่" in _d)

# 2) master สาขา 00005, บิล สนญ. → ยิง
_check("master สาขา 00005 + บิล สนญ. → ยิง",
       _fires({"branch": "สำนักงานใหญ่", "branch_no": "00000"}, BR5_MASTER))

# 3) ตรงกัน → เงียบ
_check("HQ ↔ HQ → เงียบ", not _fires({"branch": "สำนักงานใหญ่", "branch_no": "00000"}, HQ_MASTER))
_check("สาขา 00005 ↔ 00005 → เงียบ", not _fires({"branch": "สาขา 00005", "branch_no": "00005"}, BR5_MASTER))

# 4) master ใช้ label อย่างเดียว (ไม่มี branch_no) → derive ได้ → ยังเทียบถูก
HQ_LABEL_ONLY = {"name": "บริษัท ดี จำกัด", "branch": "สำนักงานใหญ่"}
_check("master label 'สำนักงานใหญ่' (ไม่มี branch_no) + บิลสาขา 00009 → ยิง",
       _fires({"branch": "สาขา 00009", "branch_no": "00009"}, HQ_LABEL_ONLY))

# 5) ไม่มี master (m=None) → เงียบ (honesty A1 จัดการช่องสาขา)
_check("m=None → เงียบ (ตกไป A1 honesty)", not _fires({"branch": "สาขา 00001", "branch_no": "00001"}, None))

# 6) master ไม่มี branch → เงียบ (conservative)
_check("master ไม่มี branch → เงียบ", not _fires({"branch": "สาขา 00001", "branch_no": "00001"}, NOBR_MASTER))

# 7) บิลระบุสาขาไม่ชัด (ว่าง) → เงียบ (ปล่อย BR002/A1)
_check("บิลไม่ระบุสาขา → เงียบ", not _fires({"branch": "", "branch_no": ""}, HQ_MASTER))
_check("บิล branch label กำกวม (ไม่มีเลข/ไม่ใช่ สนญ.) → เงียบ",
       not _fires({"branch": "สาขา", "branch_no": ""}, HQ_MASTER))

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] BR004 ยิงเมื่อสาขาต่าง master + เงียบเมื่อไม่มี master/ข้อมูลไม่ชัด")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
