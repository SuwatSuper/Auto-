# -*- coding: utf-8 -*-
"""test_parse_canary.py — pin test ของ parse-rate canary

ยืนยันว่า logic เทียบโปรไฟล์ (_compare) จับ regression แบบ 836→52 ได้:
  - clean      → ไม่มี fail
  - bill drop  → fail (ยอดรวมร่วงเกินเกณฑ์)
  - collapsed  → fail (ไฟล์ยังอยู่แต่ได้ 0 บิล = ลายเซ็นของ _FastFrame regression)
  - missing    → warn เท่านั้น (data หาย ≠ parser พัง)
และ _profile บน fixture ให้ 3 บิล/1 ไฟล์ (ตรงกับ golden fixture).
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse_canary as pc  # noqa: E402

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


BASE = {
    "_kind": pc.KIND,
    "n_files": 3,
    "n_bills": 30,
    "parse_rate": 10.0,
    "n_zero_files": 0,
    "zero_files": [],
    "per_file": {"a.xls": 10, "b.xls": 12, "c.xls": 8},
}


def _now(per_file, zero_files=None):
    nb = sum(per_file.values())
    nf = len(per_file) + len(zero_files or [])
    return {
        "n_files": nf,
        "n_bills": nb,
        "parse_rate": round(nb / nf, 4) if nf else 0.0,
        "n_zero_files": len(zero_files or []),
        "zero_files": sorted(zero_files or []),
        "per_file": per_file,
    }


print("=" * 64)
print("TEST parse_canary")
print("=" * 64)

# 1) clean — เท่าเดิมเป๊ะ → ไม่มี fail
fails, _ = pc._compare(_now({"a.xls": 10, "b.xls": 12, "c.xls": 8}), BASE, 10.0)
check("clean: ไม่มี fail", fails == [])

# 2) bill drop — ยอดรวมร่วง 30→15 (−50%) → fail
fails, _ = pc._compare(_now({"a.xls": 5, "b.xls": 6, "c.xls": 4}), BASE, 10.0)
check("bill drop −50%: มี fail", any("บิลรวมร่วง" in f for f in fails))

# 3) collapsed — ไฟล์ยังอยู่ (เป็น zero_file) แต่ได้ 0 บิล = ลายเซ็น 836→52 → fail
#    a,b ยุบเหลือ 0 (อยู่ใน zero_files = ยังถูกเห็นแต่ parse ไม่ออกบิล)
now_collapsed = _now({"c.xls": 8}, zero_files=["a.xls", "b.xls"])
fails, _ = pc._compare(now_collapsed, BASE, 10.0)
check("collapsed (ไฟล์อยู่แต่ 0 บิล): มี fail", any("ได้ 0 บิล" in f for f in fails))

# 4) missing only — ไฟล์หายจาก data จริง (ไม่อยู่ทั้ง per_file/zero_files) → warn ไม่ fail
#    ทำให้ยอดไม่ร่วงเกินเกณฑ์ (ลบ c.xls ที่ 8 จาก 30 = −26.7% > 10 → จะ fail bill).
#    ใช้เกณฑ์ 40% เพื่อแยกทดสอบ "missing => warn" ออกจาก "bill drop => fail".
now_missing = _now({"a.xls": 10, "b.xls": 12})  # c.xls หายไป
fails, warns = pc._compare(now_missing, BASE, 40.0)
check("missing only (เกณฑ์ 40%): ไม่มี fail", fails == [])
check("missing only: มี warn 'หายจากชุดข้อมูล'", any("หายจากชุดข้อมูล" in w for w in warns))

# 5) _profile บน fixture → 3 บิล / 1 ไฟล์ (ตรง golden fixture)
here = os.path.dirname(os.path.abspath(__file__))
prof = pc._profile(os.path.join(here, "tests", "fixtures"))
check("profile(fixture): 1 ไฟล์", prof["n_files"] == 1)
check("profile(fixture): 3 บิล", prof["n_bills"] == 3)

print("=" * 64)
print(f"RESULT: {'✅' if FAIL == 0 else '❌'}  ผ่าน {PASS} / ล้มเหลว {FAIL}")
sys.exit(0 if FAIL == 0 else 1)
