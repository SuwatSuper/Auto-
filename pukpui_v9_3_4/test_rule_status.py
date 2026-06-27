# -*- coding: utf-8 -*-
"""test_rule_status.py — [A2] coverage รายงานสถานะกฎ "ตามจริง" (กันสถิติหลอกตา)

บริบท: ระบบโฆษณา "56 กฎ" แต่บางกฎไม่ทำงาน — VAT010/ITM008/BR003/DOC002 ปิดอยู่,
ITM009 เปิดแต่ตายเพราะไม่มี product_master.json. ถ้านับรวมเป็น active = สถิติหลอกตา.

ตรึงสัญญา (code_registry — ชั้น metadata, golden-neutral):
  • แยกกฎ 3 กลุ่ม: active / disabled-by-design / unavailable-resource — เป็น partition (ไม่ทับ/ไม่ขาด)
  • ทุกกฎที่ปิด (enabled=False) ต้องมีเหตุผลกำกับใน DISABLED_BY_DESIGN (ไม่มีเหตุผลลอย/ขาด)
  • active "ไม่นับ" disabled และ unavailable (กัน false coverage)
  • ITM009 (เปิด แต่ขาด product_master.json) = unavailable-resource ไม่ใช่ active

exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import code_registry as REG
from rules_engine import RULES

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


active = REG.active_rule_codes()
disabled = REG.disabled_by_design_codes()
unavail = REG.unavailable_rule_codes()
all_codes = REG.all_rule_codes()
enabled = REG.enabled_rule_codes()

print(f"[สถานะกฎ] ทั้งหมด {len(all_codes)} | active {len(active)} | "
      f"disabled-by-design {len(disabled)} | unavailable-resource {len(unavail)}")

# 1) partition: active ∪ disabled ∪ unavailable = ทั้งหมด, และไม่ทับกัน
_check("active ∪ disabled ∪ unavailable = กฎทั้งหมด (ไม่ขาด)",
       (active | disabled | unavail) == all_codes)
_check("active ∩ disabled = ว่าง", not (active & disabled))
_check("active ∩ unavailable = ว่าง", not (active & unavail))
_check("disabled ∩ unavailable = ว่าง", not (disabled & unavail))

# 2) disabled = enabled=False เป๊ะ ; ทุกตัวมีเหตุผล (ไม่มีเหตุผลขาด/เกิน)
real_disabled = {c for c, r in RULES.items() if not r.get("enabled", True)}
_check(f"disabled_by_design = เซ็ต enabled=False จริง ({sorted(real_disabled)})",
       disabled == real_disabled)
_check("ทุกกฎที่ปิด มีเหตุผลใน DISABLED_BY_DESIGN (ไม่ขาด)",
       all(c in REG.DISABLED_BY_DESIGN for c in disabled))
_check("DISABLED_BY_DESIGN ไม่มีเหตุผลลอย (ทุก key เป็นกฎที่ปิดจริง)",
       set(REG.DISABLED_BY_DESIGN) == disabled)
for c in ("VAT010", "ITM008", "BR003", "DOC002"):
    _check(f"{c} = disabled-by-design + มีเหตุผล",
           c in disabled and bool(REG.rule_status_reason(c)))

# 3) active ไม่นับ disabled/unavailable (กัน false coverage)
_check("active ⊆ enabled (active ต้องเปิดอยู่)", active <= enabled)
_check("ไม่มี disabled ใน active", not (disabled & active))
_check("ไม่มี unavailable ใน active", not (unavail & active))

# 4) ITM009 — เปิด แต่ถ้าไม่มี product_master.json = unavailable (ไม่ใช่ active)
_check("ITM009 enabled=True ใน RULES", RULES["ITM009"].get("enabled", False) is True)
if not REG.product_master_available():
    _check("ไม่มี product_master.json → ITM009 = unavailable-resource (ไม่ใช่ active)",
           "ITM009" in unavail and "ITM009" not in active
           and REG.rule_status("ITM009") == "unavailable-resource")
    _check("ITM009 มีเหตุผลระบุ resource ที่ขาด (product_master.json)",
           "product_master.json" in REG.rule_status_reason("ITM009"))
else:
    _check("มี product_master.json → ITM009 = active", "ITM009" in active)

# 5) format_rule_coverage อ่านได้ + ระบุทั้ง disabled และ unavailable
txt = REG.format_rule_coverage()
_check("format_rule_coverage มีหัว 'RULE COVERAGE' + นับ active",
       "RULE COVERAGE" in txt and "active" in txt)
_check("format_rule_coverage ระบุ disabled-by-design + unavailable-resource",
       "disabled-by-design" in txt and "unavailable-resource" in txt)

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] coverage สถานะกฎตามจริง — ไม่นับ disabled/unavailable เป็น active")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
