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

from rules_engine import RULES
from config import FIELD_CODES

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("FIELD_CODES COVERAGE — แดชบอร์ดต้องเห็นทุกกฎที่ enabled")

# รหัสทั้งหมดที่ map ในแดชบอร์ด
mapped = set()
for _label, codes in FIELD_CODES:
    mapped.update(codes)

all_rule_codes = set(RULES.keys())
enabled_codes = {c for c, r in RULES.items() if r.get("enabled", True)}

# 1) ทุกกฎที่ "เปิดใช้งาน" ต้องอยู่ในแดชบอร์ด (มิฉะนั้น error จริงโชว์ "ตรง" หลอก)
missing_enabled = sorted(enabled_codes - mapped)
_check(
    f"FIELD_CODES ครอบคลุมทุกกฎ enabled (ขาด: {missing_enabled or 'ไม่มี'})",
    not missing_enabled,
)

# 2) ไม่อ้างรหัสที่ไม่มีจริงใน RULES (กัน dead code/typo ในตาราง map)
unknown = sorted(mapped - all_rule_codes)
_check(
    f"FIELD_CODES ไม่อ้างรหัสที่ไม่มีใน RULES (เกิน: {unknown or 'ไม่มี'})",
    not unknown,
)

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ แดชบอร์ดเห็นทุกกฎ — ไม่มี false-clean จากรหัสตกหล่น")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — เพิ่ม/แก้ FIELD_CODES ใน config.py ให้ตรงกับ RULES")
    sys.exit(1)
