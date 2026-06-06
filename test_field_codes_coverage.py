# -*- coding: utf-8 -*-
"""test_field_codes_coverage.py — TRIPWIRE: แดชบอร์ดผู้บริหารต้อง "เห็นทุกกฎ"

บริบท (P0-FIX):
  display_executive_dashboard() คำนวณสถานะรายฟิลด์จาก config.FIELD_CODES เท่านั้น.
  ถ้ารหัสใน RULES (ที่ enabled) ไม่ถูก map เข้า FIELD_CODES → field_status() มองไม่เห็น →
  บริษัทที่มี error จริง (เช่น CMP005=ชื่อบจ.ไม่ครบ / DOC003=IV ซ้ำ / VAT009=ยอดก่อน VAT เป็นศูนย์)
  กลับขึ้น "ตรง" สีเขียวในแดชบอร์ด = false-clean ที่อันตราย.

เทสนี้ตรึงสองสัญญา:
  • FIELD_CODES ครอบคลุม "ทุกรหัส RULES ที่ enabled" (กันรหัสตกหล่น → false-clean)
  • FIELD_CODES ไม่อ้างรหัสที่ไม่มีใน RULES (กัน dead code / typo)

self-contained: อ่านจาก config.RULES + config.FIELD_CODES ตรง ๆ (deterministic, ไม่พึ่ง /mnt/project).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import FIELD_CODES
import code_registry as REG

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("FIELD_CODES COVERAGE — แดชบอร์ดต้องเห็นทุกรหัสที่ emit ได้จริง")

# รหัสทั้งหมดที่ map ในแดชบอร์ด
mapped = set()
for _label, codes in FIELD_CODES:
    mapped.update(codes)

emittable = REG.emittable_codes()   # กฎที่เปิด + รหัสจาก parser/crosscheck (แหล่งเดียว)
known = REG.known_codes()           # กฎทั้งหมด (รวมปิด) + external

# 1) ทุกรหัสที่ emit ได้จริง ต้องอยู่ในแดชบอร์ด (มิฉะนั้น error จริงโชว์ "ตรง" หลอก)
missing = sorted(emittable - mapped)
_check(
    f"FIELD_CODES ครอบคลุมทุกรหัสที่ emit ได้ (ขาด: {missing or 'ไม่มี'})",
    not missing,
)

# 2) ไม่อ้างรหัสแปลกปลอม/typo (ทุกรหัสในตารางต้องเป็นรหัสที่ระบบรู้จัก)
unknown = sorted(mapped - known)
_check(
    f"FIELD_CODES ไม่อ้างรหัสแปลกปลอม (เกิน: {unknown or 'ไม่มี'})",
    not unknown,
)

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ แดชบอร์ดเห็นทุกกฎ — ไม่มี false-clean จากรหัสตกหล่น")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — เพิ่ม/แก้ FIELD_CODES ใน config.py ให้ตรงกับ RULES")
    sys.exit(1)
