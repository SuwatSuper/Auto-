# -*- coding: utf-8 -*-
"""test_crosscheck_idempotency.py — TRIPWIRE: cross-check ที่มี side-effect ต้อง IDEMPOTENT

บริบท (จากการตรวจ Maintainability/Reliability + ADR-017):
  ฟังก์ชัน cross-check (apply_sheet_date_crosscheck=DOC001, apply_iv_period_crosscheck=DT004,
  _iv_check_cross_day=IV003, _iv_check_ascending=IV004) "เติม issue ลงบิล" เป็น side-effect.
  เดิมเรียกซ้ำ = issue ซ้ำ = golden hash เพี้ยน (ตรึงด้วยวินัย "เรียกครั้งเดียว").
  ADR-017 ทำให้ idempotent โดยโครงสร้าง (_append_issue_unique): เรียกซ้ำ → ไม่เพิ่มซ้ำ.
  เทสนี้ตรึงคุณสมบัตินั้น:
    • เรียก 1 ครั้ง → ฟ้อง 1 (สัญญา)
    • เรียก 2 ครั้ง → ยังคง 1 (idempotent — ถ้าใครถอด guard ออก เทสนี้ fail ทันที)

self-contained: สร้าง bill ขั้นต่ำเอง ไม่พึ่ง /mnt/project (deterministic).
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validators import apply_sheet_date_crosscheck, apply_iv_period_crosscheck

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


# ── DOC001: sheet "01.05" ไม่ตรง iv_date 10/05 → ต้องฟ้อง ──────────────────────
def _bill_doc001():
    return {"iv_date": date(2025, 5, 10), "sheet": "01.05", "issues": []}


b = _bill_doc001()
apply_sheet_date_crosscheck([b])
n1 = sum(1 for i in b["issues"] if i.get("code") == "DOC001")
apply_sheet_date_crosscheck([b])        # เรียกซ้ำโดยตั้งใจ
n2 = sum(1 for i in b["issues"] if i.get("code") == "DOC001")

_check("DOC001 เรียก 1 ครั้ง → ฟ้อง 1 (สัญญา)", n1 == 1)
_check("DOC001 เรียก 2 ครั้ง → ยังคง 1 (idempotent ตาม ADR-017)", n2 == 1)


# ── DT004: iv_date งวด 05/2025 แต่เลข IV ฝังงวด 06/2025 → ต้องฟ้อง ──────────────
def _bill_dt004():
    # เลข INV-202506-001 ฝังงวด 2025-06 ; iv_date เป็น 2025-05 → mismatch
    return {"iv_date": date(2025, 5, 15), "iv_number": "INV-202506-001",
            "iv_number_raw": "INV-202506-001", "issues": []}


b2 = _bill_dt004()
apply_iv_period_crosscheck([b2])
m1 = sum(1 for i in b2["issues"] if i.get("code") == "DT004")
apply_iv_period_crosscheck([b2])        # เรียกซ้ำโดยตั้งใจ
m2 = sum(1 for i in b2["issues"] if i.get("code") == "DT004")

_check("DT004 เรียก 1 ครั้ง → ฟ้อง 1 (สัญญา)", m1 == 1)
_check("DT004 เรียก 2 ครั้ง → ยังคง 1 (idempotent ตาม ADR-017)", m2 == 1)

print("=" * 56)
if _fail == 0:
    print("RESULT: ✅ cross-check idempotency ถูกตรึงเป็น invariant (ADR-017)")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — idempotency เสีย ต้องตรวจ _append_issue_unique + golden")
    sys.exit(1)
