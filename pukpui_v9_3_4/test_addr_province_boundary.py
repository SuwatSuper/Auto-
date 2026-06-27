# -*- coding: utf-8 -*-
"""test_addr_province_boundary.py — ตรึง ADR-110: province_in_address ต้องจับชื่อจังหวัดแบบ
'word-boundary' ไม่ใช่ substring ดิบ — กัน false-positive ADDR006 เมื่อชื่อจังหวัดสั้น
(เลย/ตาก/น่าน/ตรัง/ตราด/แพร่) บังเอิญเป็นส่วนของคำอื่น.

หลักการ (regression guard):
  A) ชื่อจังหวัดสั้นที่อยู่ "กลางคำอื่น" → ต้องไม่ถูกจับ (เลยกว่า/ตากสิน/น่านฟ้า → None).
  B) การระบุจังหวัดจริง (จังหวัดX / จ.X / X ติดเว้นวรรค-เลขไปรษณีย์) → ยังจับได้.
  C) postal↔province mismatch จริง → ยังฟ้อง (recall ไม่ถอย).
golden-neutral: ADDR006 ฟ้อง 0× บน corpus ทั้งก่อน/หลัง (พิสูจน์ golden_master = 31013a31).
ไม่ใช้ข้อมูลจริง รันได้ทุกที่. exit 0 = ผ่าน, 1 = ล้มเหลว.
"""
import sys

from thai_postal import province_in_address, postal_province_mismatch

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("ADDR PROVINCE WORD-BOUNDARY — ADR-110 (กัน substring false-positive)")

# A) false-positive: ชื่อจังหวัดเป็น substring กลางคำอื่น → ไม่จับ
fp = [
    ("เลยกว่า", "บริษัท เลยกว่าใคร จำกัด 99/9 กรุงเทพ 10250"),
    ("ตากสิน",  "เลขที่ 5 ตากสิน ธนบุรี กรุงเทพ 10600"),
    ("น่านฟ้า", "ร้านน่านฟ้า 12 ถนนสุขุมวิท กรุงเทพ 10110"),
    ("ตราดี",   "หจก. ตราดีมาก 1 ถนนพระราม 9 กรุงเทพ 10310"),
]
for name, addr in fp:
    _check(f"ไม่จับจังหวัดในคำ '{name}' (FP)", province_in_address(addr) is None)

# B) true-positive: การระบุจังหวัดจริง → ยังจับได้
tp = [
    ("จังหวัดเลย", "123 ตำบลในเมือง อำเภอเมือง จังหวัดเลย 42000", "เลย"),
    ("จ.ตาก",      "9 หมู่ 2 อ.เมือง จ.ตาก 63000", "ตาก"),
    ("น่าน+zip",   "55 หมู่1 ตำบลในเวียง อำเภอเมือง น่าน 55000", "น่าน"),
    ("ตราด",       "10 ถนนหลัก ตำบลบางพระ อำเภอเมือง ตราด 23000", "ตราด"),
]
for name, addr, exp in tp:
    _check(f"ยังจับจังหวัดจริง '{name}' = {exp}", province_in_address(addr) == exp)

# C) mismatch จริง → ยังฟ้อง (recall ไม่ถอย): เลย=prefix 42 แต่ zip 50xxx (เชียงใหม่)
mm = postal_province_mismatch("123 ถนนหลัก จังหวัดเลย 50000")
_check("ยังฟ้อง mismatch จริง (เลย + 50000)", bool(mm) and mm[0] == "เลย")
# สอดคล้องกัน (เลย + 42xxx) → ไม่ฟ้อง
_check("ไม่ฟ้องเมื่อสอดคล้อง (เลย + 42000)",
       postal_province_mismatch("123 ถนนหลัก จังหวัดเลย 42000") is None)

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ PASS — ADR-110 word-boundary ครบ (กัน FP + recall ไม่ถอย)")
    sys.exit(0)
print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน")
sys.exit(1)
