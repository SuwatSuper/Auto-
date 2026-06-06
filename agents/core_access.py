# -*- coding: utf-8 -*-
"""
agents/core_access.py — ประตูเดียวสู่ "เครื่องยนต์เดิม" (the proven core)

ทำไมต้องมีไฟล์นี้:
  - โมดูลหลักชื่อไทย `ปุ้มปุ้ย_ultimate_v9_modular` + พึ่ง cwd (มันทำ `from config import *` ฯลฯ)
    → การ import ตรงๆ จากหลายที่ทำให้โค้ดเลอะและเปราะ
  - รวมไว้จุดเดียว = ทุก agent เรียกผ่านชื่อ python มาตรฐาน (เช่น core.parse_all_files)
  - ทำ "import gate" แบบเดียวกับที่ระบบเดิมทำ: ถ้าฟังก์ชันที่ต้องใช้หาย → error ชัดเจนทันที
    พร้อมบอกสาเหตุ แทนที่จะเป็น AttributeError ปริศนากลาง runtime

⚠️ ไฟล์นี้ "ไม่นิยาม business logic ใหม่" — เป็นแค่ตัวกลางชี้ไปยังฟังก์ชันเดิมทั้งหมด
"""
from __future__ import annotations

import importlib
import os
import sys

# ชื่อโมดูลหลัก (ภาษาไทย) — ตั้งเป็น env override ได้เผื่อมีการเปลี่ยนชื่อไฟล์ในอนาคต
_MAIN_MODULE = os.environ.get("PUKPUI_MAIN_MODULE", "ปุ้มปุ้ย_ultimate_v9_modular")


def _ensure_cwd_on_path() -> None:
    """โมดูลหลักพึ่ง cwd (from config import *). ให้แน่ใจว่า dir ของแพ็กเกจอยู่ใน sys.path."""
    # โฟลเดอร์ที่มี agents/ อยู่ = root ของระบบ (ที่มีโมดูลหลัก + config.py)
    pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)


_ensure_cwd_on_path()

try:
    core = importlib.import_module(_MAIN_MODULE)
except Exception as _e:  # pragma: no cover - ขึ้นกับ environment
    raise ImportError(
        f"โหลดเครื่องยนต์หลัก '{_MAIN_MODULE}' ไม่สำเร็จ.\n"
        "ตรวจสอบ: (1) รันจากโฟลเดอร์ระบบ หรือมีโฟลเดอร์นั้นใน sys.path "
        "(2) ติดตั้ง deps ครบ (pandas/xlrd/openpyxl/rapidfuzz/matplotlib) "
        "(3) ไฟล์โมดูลหลักยังอยู่ครบ\n"
        f"ต้นเหตุ: {type(_e).__name__}: {_e}"
    ) from _e


# ---------------------------------------------------------------------------
# Import gate — รายชื่อ symbol จาก core ที่ agent layer พึ่ง
#   ถ้าตัวใดหาย (เช่น มีการ refactor core จนชื่อเปลี่ยน) จะ error ทันทีพร้อมรายชื่อ
#   (เลียนแบบ P0 import-guard ของระบบเดิม — ป้องกัน silent break)
# ---------------------------------------------------------------------------
_REQUIRED = [
    # io / parsing
    "parse_all_files", "get_files_via_drive", "get_files_via_upload",
    # audit core
    "run_all_rules", "RULES", "match_company",
    "run_audit_core",   # v9.1: แหล่งความจริงเดียวของลำดับศักดิ์สิทธิ์ (orchestrator ใช้)
    "compute_bill_confidence", "check_duplicate_items",
    "check_invoice_sequence", "check_iv_date_sequence",
    "check_product_typos", "summarize_by_company",
    "apply_iv_period_crosscheck", "apply_sheet_date_crosscheck",
    # primitives (ใช้ใน domain cross-check)
    "clean_tax_id", "_taxid_checksum_ok", "_D", "_vat_tolerance",
    # reporting
    "build_clean_report", "export_excel",
    # state
    "reset_run_state",
]

_missing = [n for n in _REQUIRED if not hasattr(core, n)]
if _missing:
    raise ImportError(
        "Import gate (agents): เครื่องยนต์หลักขาด symbol ที่ agent layer ต้องใช้: "
        f"{_missing}\n"
        "สาเหตุที่พบบ่อย: มีการเปลี่ยนชื่อ/ย้ายฟังก์ชันใน core โดยไม่อัปเดต agents/core_access.py\n"
        "วิธีแก้: ปรับชื่อใน _REQUIRED ให้ตรงกับ core หรือคืนชื่อเดิม"
    )


def get(name: str):
    """ดึง symbol จาก core แบบปลอดภัย (ใช้กับ optional symbol ที่ไม่อยู่ใน gate)."""
    return getattr(core, name, None)


# Decimal helper จาก core (รับประกัน semantics เดียวกับกฎ VAT)
_D = core._D                  # noqa: N816  (ชื่อตรงกับ core)
_vat_tolerance = core._vat_tolerance
clean_tax_id = core.clean_tax_id
_taxid_checksum_ok = core._taxid_checksum_ok
