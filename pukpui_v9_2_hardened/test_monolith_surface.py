# -*- coding: utf-8 -*-
"""
test_monolith_surface.py — tripwire ล็อก "พื้นผิวสาธารณะ" ของ monolith (v9.2 / งาน P1)

ทำไมต้องมีไฟล์นี้ (สำคัญมากสำหรับงาน de-star + split):
  - โมดูลภายนอกทุกตัว (agents/core_access, main.py, viewers, golden_master, test_*)
    เข้าถึง monolith ผ่าน `importlib.import_module(...)` แล้วใช้ `app.<name>` (getattr)
    — *ไม่มีใคร* ทำ `from monolith import *` หรือ `import X`
  - ดังนั้น `__all__` ของ monolith **ไม่คุม** การเข้าถึงเหล่านี้เลย; การ์ดที่แท้จริง
    ของ "contract" คือ "ชื่อต้องยังเป็น attribute ของ module อยู่"
  - งาน P1 (เลิก `import *` 11 จุด + split) เสี่ยงตัด re-export ที่ภายนอกพึ่งโดยไม่รู้ตัว
    → เทสนี้จับทันที (เร็วกว่ารอ golden พังหรือ AttributeError กลาง runtime)

contract = union ของ 4 แหล่ง (ดึงแบบ dynamic เท่าที่ทำได้ เพื่อไม่ดริฟต์):
  (A) agents/core_access._REQUIRED            — 22 ชื่อที่ agent layer การันตี (import-gate)
  (B) 4 ชื่อที่ core_access bind ตรง ๆ        — _D / _vat_tolerance / clean_tax_id / _taxid_checksum_ok
  (C) ชื่อที่โค้ดภายนอกเข้าถึงจริงเชิงประจักษ์ — สแกน `app.<name>` ทั้ง tree (ฝังเป็น snapshot)
  (D) ชื่อที่ agent resolve แบบ dynamic        — `core.get("…")` ใน verification lenses
      (บทเรียน de-star P1: กลุ่มนี้ไม่โผล่เป็น app.<name>/_REQUIRED จึงพลาดง่าย —
       golden/regression/test_agents ไม่จับ เพราะ agent อยู่นอก snapshot; เทส lens unit จับ)

รันแบบ standalone (ไม่แตะ engine source):
    python3 test_monolith_surface.py
"""
import io
import os
import sys
import contextlib
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_fail = 0


def _check(cond, ok_msg, fail_msg):
    global _fail
    if cond:
        print(f"  ✅ {ok_msg}")
    else:
        _fail += 1
        print(f"  ❌ {fail_msg}")


# (C) snapshot ของชื่อที่โค้ดภายนอกเข้าถึงจริงผ่าน app.<name> (สแกน ณ งาน P1)
#     ถ้าวันใดมีโค้ดภายนอกเรียกชื่อใหม่จาก monolith ให้เพิ่มที่นี่ (และต้องมีใน monolith)
_ACCESSED_VIA_APP = [
    "_D", "_SYSTEM_ISSUES", "_taxid_checksum_ok", "_vat_tolerance",
    "addon_check_withholding", "apply_iv_period_crosscheck",
    "apply_sheet_date_crosscheck", "build_clean_report", "build_unit_index",
    "check_duplicate_items", "check_invoice_sequence", "check_iv_date_sequence",
    "check_product_typos", "clean_tax_id", "compute_bill_confidence", "main",
    "parse_all_files", "reset_run_state", "run_all_rules", "run_audit_core",
    "summarize_by_company",
]

# (B) ชื่อที่ core_access.py bind ตรงตอนโหลด module (นอกเหนือจาก _REQUIRED)
_CORE_ACCESS_DIRECT = ["_D", "_vat_tolerance", "clean_tax_id", "_taxid_checksum_ok"]

# (D) ชื่อที่ agent layer resolve แบบ "dynamic" ผ่าน core_access.get("…") / core.get("…")
#     — getattr(core, name, None) → ถ้าหาย lens degrade เงียบ (return 0) แต่ "ผล" ผิด
#       (เทส lens unit จับ แต่ golden/regression/test_agents ไม่จับ เพราะ agent อยู่นอก snapshot)
#     บทเรียน de-star P1: ชื่อกลุ่มนี้ *ไม่ปรากฏ* เป็น app.<name> หรือใน _REQUIRED จึงพลาดง่าย
#   _DYNAMIC_REQUIRED = ต้องมีจริง (baseline monolith มี + lens ต้องใช้ให้ผลถูก)
_DYNAMIC_REQUIRED = ["audit_today", "detect_iv_period_mismatch"]
#   _DYNAMIC_OPTIONAL = shoulder feature ที่ degrade ได้ + baseline ไม่เคยมี (ห้าม fail ถ้าไม่มี)
_DYNAMIC_OPTIONAL = ["run_addon_pack"]


def _scan_agent_dynamic_lookups():
    """สแกน agents/*.py หา literal core.get("X") / core_access.get("X") — กันลืมจัดประเภท
    เมื่อมีคนเพิ่ม dynamic-lookup ใหม่ในอนาคต (self-maintaining guard)."""
    import re
    found = set()
    agents_dir = os.path.join(HERE, "agents")
    pat = re.compile(r"(?:core|core_access)\.get\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]")
    if os.path.isdir(agents_dir):
        for fn in os.listdir(agents_dir):
            if fn.endswith(".py"):
                try:
                    found |= set(pat.findall(
                        open(os.path.join(agents_dir, fn), encoding="utf-8").read()))
                except Exception:
                    pass
    return found


def main():
    print("[monolith surface] ตรวจว่า monolith ยังเปิดเผย contract ครบ (getattr-based)")

    # โหลด core_access จริง → ได้ทั้ง (A) _REQUIRED และตัว monolith ที่มันชี้ไป
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            from agents import core_access
            mono = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
    except Exception as e:  # pragma: no cover
        print(f"  ❌ โหลด core_access / monolith ไม่สำเร็จ — {type(e).__name__}: {e}")
        print("-" * 64)
        print("RESULT: ❌ FAIL — import ไม่ผ่าน")
        sys.exit(1)

    required = list(getattr(core_access, "_REQUIRED", []))
    _check(len(required) >= 22,
           f"อ่าน core_access._REQUIRED ได้ ({len(required)} ชื่อ)",
           f"core_access._REQUIRED ผิดปกติ ({len(required)} ชื่อ)")

    # union ของ contract ทั้งหมด (A+B+C+D-required)
    contract = sorted(set(required) | set(_CORE_ACCESS_DIRECT)
                      | set(_ACCESSED_VIA_APP) | set(_DYNAMIC_REQUIRED))

    # (D-guard) สแกน agents/ หา dynamic-lookup ใหม่ที่ยังไม่ถูกจัดประเภท
    classified = (set(_DYNAMIC_REQUIRED) | set(_DYNAMIC_OPTIONAL)
                  | set(required) | set(_ACCESSED_VIA_APP))
    found_dyn = _scan_agent_dynamic_lookups()
    unclassified = sorted(found_dyn - classified)
    _check(not unclassified,
           f"dynamic core.get() ใน agents จัดประเภทครบ ({len(found_dyn)} ชื่อ)",
           f"พบ core.get() ใหม่ที่ยังไม่จัดประเภท → ต้องระบุเป็น REQUIRED/OPTIONAL: {unclassified}")

    # (A) ทุกชื่อใน _REQUIRED ต้อง resolve ผ่าน core_access.get(...)
    missing_req = [n for n in required if core_access.get(n) is None]
    _check(not missing_req,
           "core_access._REQUIRED ครบทุกตัว (gate ผ่าน)",
           f"core_access gate ขาด: {missing_req}")

    # (A+B+C) ทุกชื่อใน contract ต้องเป็น attribute จริงของ monolith
    missing_attr = [n for n in contract if not hasattr(mono, n)]
    _check(not missing_attr,
           f"monolith เปิดเผย contract ครบ {len(contract)} ชื่อ",
           f"monolith ขาด attribute: {missing_attr}")

    # callable ที่ควร callable (กันกรณีถูก overwrite เป็นค่าอื่นโดยไม่ตั้งใจ)
    must_callable = [
        "parse_all_files", "run_audit_core", "run_all_rules",
        "compute_bill_confidence", "build_clean_report", "export_excel",
        "reset_run_state", "match_company", "clean_tax_id", "main",
    ]
    not_callable = [n for n in must_callable
                    if hasattr(mono, n) and not callable(getattr(mono, n))]
    _check(not not_callable,
           "ฟังก์ชันหลักใน contract ยัง callable",
           f"ชื่อใน contract ไม่ callable แล้ว: {not_callable}")

    print("-" * 64)
    if _fail == 0:
        print(f"RESULT: ✅ PASS — monolith surface contract ครบ ({len(contract)} ชื่อ, getattr-safe)")
        sys.exit(0)
    else:
        print(f"RESULT: ❌ FAIL — {_fail} ข้อ")
        sys.exit(1)


if __name__ == "__main__":
    main()
