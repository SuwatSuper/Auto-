# -*- coding: utf-8 -*-
"""test_sys_summary.py — [A5] สรุป SYS-* ท้ายการรัน ทำให้ silent skip มองเห็นได้

บริบท: เมื่อกฎ crash บนบางบิล run_rules → log_system_issue('SYS-<code>') และ "ไม่ใส่" ใน
bill['issues'] → บิลนั้นข้ามกฎนั้นเงียบจากรายงานหลัก. ต้องมีบรรทัดสรุป SYS-* ท้ายการรัน
(รวม rule crash) เพื่อให้คนเห็นว่า "มีการข้ามกฎเงียบ" — ไม่เปลี่ยน routing เดิม.

ตรึง:
  • 0 SYS → ข้อความยืนยันชัด "ไม่มีกฎข้ามเงียบ" (ไม่ใช่เงียบหาย)
  • parse SYS (SYS001) → นับครบ แต่ไม่เตือน rule crash
  • rule crash (SYS-<code>) → เตือน "กฎข้ามเงียบ" + ระบุรหัสกฎที่ข้าม
  • format_sys_summary อ่าน arg/state อย่างเดียว — ไม่เปลี่ยน routing/golden

exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from diagnostics import format_sys_summary

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _iss(code):
    return {"code": code, "name": "x", "detail": "", "severity": "INFO", "category": "SYSTEM"}


# 1) ไม่มี SYS → ยืนยันชัด (ไม่เงียบหาย)
s0 = format_sys_summary([])
_check("0 SYS → ระบุ '0' + 'ไม่มีกฎข้ามเงียบ'", "0" in s0 and "ไม่มีกฎข้ามเงียบ" in s0)

# 2) parse SYS อย่างเดียว (SYS001) → นับครบ ไม่เตือน rule crash
s1 = format_sys_summary([_iss("SYS001"), _iss("SYS001")])
_check("parse SYS: นับ 2 รายการ + SYS001×2", "2 รายการ" in s1 and "SYS001×2" in s1)
_check("parse SYS: ไม่เตือน 'กฎข้ามเงียบ' (ไม่ใช่ rule crash)", "กฎข้ามเงียบ" not in s1)

# 3) rule crash (SYS-<code>) → เตือน + ระบุรหัสกฎที่ข้าม
s2 = format_sys_summary([_iss("SYS-CMP001"), _iss("SYS-VAT002"), _iss("SYS-CMP001")])
_check("rule crash: นับ 3 รายการ", "3 รายการ" in s2)
_check("rule crash: เตือน 'กฎข้ามเงียบ (rule crash)'", "กฎข้ามเงียบ (rule crash)" in s2)
_check("rule crash: ระบุรหัสกฎที่ข้าม (CMP001 + VAT002)", "CMP001" in s2 and "VAT002" in s2)
_check("rule crash: นับครั้ง crash ถูก (3 ครั้ง)", "3 ครั้ง" in s2)

# 4) ผสม parse + rule crash → เตือน rule crash + นับรวมถูก
s3 = format_sys_summary([_iss("SYS001"), _iss("SYS-ITM001")])
_check("mixed: นับรวม 2 + เตือน rule crash (ITM001)",
       "2 รายการ" in s3 and "กฎข้ามเงียบ" in s3 and "ITM001" in s3)

# 5) default arg อ่าน state (ไม่ throw บน state ว่าง/มีของ)
import state as _state
_save = list(_state._SYSTEM_ISSUES)
try:
    _state._SYSTEM_ISSUES.clear()
    _check("default (state ว่าง) → '0'", "0" in format_sys_summary())
finally:
    _state._SYSTEM_ISSUES[:] = _save

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] สรุป SYS-* ท้ายการรัน — silent skip มองเห็นได้")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
