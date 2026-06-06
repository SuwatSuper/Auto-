# -*- coding: utf-8 -*-
"""test_code_tables_consistency.py — TRIPWIRE: ตารางนำเสนอทุกตัวต้องตามทันรหัสที่ emit ได้ (P3)

บริบท:
  รหัส issue ถูกนำเสนอใน 3 ตารางที่ taxonomy ต่างกัน —
    • code_labels.MAP                  (field/label/lane รายโค้ด)  → viewers / Super-Ultra
    • config.FIELD_CODES               (กลุ่มฟิลด์)                  → executive dashboard
    • vendor_report_base.FIELD_LAYOUT  (prefix + VAT เจาะจง)         → รายงานรายผู้ขาย
  ไม่มี single source → เคย drift เงียบ (FIELD_CODES ตกหล่น 12 รหัส → false-clean).
  เทสนี้ผูกทุกตารางเข้ากับ "แหล่งความจริงเดียว" code_registry.emittable_codes() :
  เพิ่มกฎ/รหัสใหม่แล้วลืมอัปเดตตารางไหน → เทสแดง พร้อมบอกชัดว่าลืมตารางใด + รหัสใด.

  (FIELD_CODES มีเทสเฉพาะ test_field_codes_coverage.py แล้ว — ที่นี่คุม MAP + FIELD_LAYOUT.)

self-contained: อ่าน MAP/FIELD_LAYOUT/registry ตรง ๆ + ใช้ตัว match จริง (_match) ของรายงานผู้ขาย.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import code_registry as REG
from code_labels import MAP
from agents.vendor_report_base import FIELD_LAYOUT, _match

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("CODE-TABLE CONSISTENCY — MAP + FIELD_LAYOUT ต้องตามทันรหัสที่ emit ได้")

emittable = REG.emittable_codes()
known = REG.known_codes()

# ── code_labels.MAP (viewers / Super-Ultra) ──────────────────────────────────
map_keys = set(MAP.keys())
# 1) ทุกรหัสที่ emit ได้ ต้องมี label/field/lane ใน MAP (ไม่งั้น viewer แสดงเป็น default มั่ว)
map_missing = sorted(emittable - map_keys)
_check(f"MAP ครอบคลุมทุกรหัสที่ emit ได้ (ขาด: {map_missing or 'ไม่มี'})", not map_missing)
# 2) MAP ไม่อ้างรหัสแปลกปลอม/typo
map_unknown = sorted(map_keys - known)
_check(f"MAP ไม่อ้างรหัสแปลกปลอม (เกิน: {map_unknown or 'ไม่มี'})", not map_unknown)

# ── vendor FIELD_LAYOUT (รายงานรายผู้ขาย) — ใช้ _match จริง (prefix/exact) ─────
def _covered_by_layout(code: str) -> bool:
    return any(_match(code, spec) for _label, spec in FIELD_LAYOUT)

layout_missing = sorted(c for c in emittable if not _covered_by_layout(c))
_check(
    f"FIELD_LAYOUT ครอบคลุมทุกรหัสที่ emit ได้ (ขาด: {layout_missing or 'ไม่มี'})",
    not layout_missing,
)

# ── [B6] Tier-1 agent set ต้องเป็นแหล่งเดียว (กันก๊อปซ้ำ drift) ───────────────
from agents._shared import TIER1
import mesh_contract as _MC
_check(
    f"Tier-1 set: _shared.TIER1 == mesh.DEFAULT_TIER1 (={tuple(TIER1)})",
    tuple(TIER1) == tuple(_MC.DEFAULT_TIER1),
)

print("=" * 64)
if _fail == 0:
    print("RESULT: ✅ MAP + FIELD_LAYOUT ตามทันรหัสที่ emit ได้ครบ — ไม่มี drift")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — อัปเดตตารางที่ขาดให้ตรง code_registry.emittable_codes()")
    sys.exit(1)
