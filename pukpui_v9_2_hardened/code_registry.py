# -*- coding: utf-8 -*-
"""code_registry.py — แหล่งความจริงเดียวของ "จักรวาลรหัสตรวจ" (P3)

ปัญหาเดิม (จากการตรวจ Maintainability):
  รหัส issue ถูก *สร้าง (emit)* จาก 3 ชั้น —
    1) parser  (เช่น IV002 ใน parser_p0)
    2) rules engine (RULES 56 กฎ)
    3) validators crosscheck (IV003/IV004)
  และถูก *นำเสนอ* ใน 3 ตารางที่ใช้ taxonomy ต่างกันโดยตั้งใจ —
    • code_labels.MAP            (field รายโค้ด + label คน + เลน)  → viewers / Super-Ultra
    • config.FIELD_CODES         (กลุ่มฟิลด์ + ลิสต์โค้ด)          → executive dashboard
    • vendor_report_base.FIELD_LAYOUT (prefix + VAT เจาะจง)         → รายงานรายผู้ขาย
  ไม่มี "แหล่งความจริงเดียว" ของชุดรหัส → ตารางนำเสนอ drift จาก RULES เงียบ ๆ
  (เคยพบ FIELD_CODES ตกหล่น 12 รหัส → แดชบอร์ดโชว์ 'ตรง' หลอก).

ไฟล์นี้รวม "ความจริงเรื่องรหัส" ไว้ที่เดียว เพื่อให้ test_code_tables_consistency.py /
test_field_codes_coverage.py ใช้ยืนยันว่า "ทุกตารางนำเสนอครอบคลุมรหัสที่ emit ได้จริง".
→ เพิ่มกฎ/รหัสใหม่แล้วลืมอัปเดตตารางไหน = CI แดงทันที พร้อมบอกชัดว่าลืมตารางใด.

หมายเหตุ: ไฟล์นี้ "ไม่เปลี่ยนพฤติกรรม runtime" — เป็นชั้น metadata/ตรวจสอบล้วน
  (import โดยเทสเท่านั้น; ไม่ถูก import โดย engine/รายงาน → ไม่กระทบ golden).
"""
from __future__ import annotations

from rules_engine import RULES

# ── รหัสที่ "ชั้น parser/crosscheck" สร้างเอง (ไม่ผ่าน RULES registry) ─────────────
#   ระบุที่มาให้ตามรอยได้ — ถ้าเพิ่มรหัสนอก RULES ในอนาคต ต้องมาขึ้นทะเบียนที่นี่
EXTERNAL_EMITTED = {
    "IV002": "parser_p0 (เลขใบกำกับผิดรูปแบบ)",
    "IV003": "validators._iv_check_cross_day (เลขใบกำกับซ้ำข้ามวัน)",
    "IV004": "validators._iv_check_ascending (เลขใบกำกับไม่ไล่ตามวัน)",
    "DT005": "validators.apply_missing_date_check (บิลไม่มีวันที่)",
}


def enabled_rule_codes() -> set:
    """รหัสกฎที่ 'เปิดใช้งาน' (enabled=True) ใน RULES."""
    return {c for c, r in RULES.items() if r.get("enabled", True)}


def all_rule_codes() -> set:
    """รหัสกฎทั้งหมดใน RULES (รวมที่ปิดอยู่)."""
    return set(RULES.keys())


def emittable_codes() -> set:
    """รหัสที่ 'ปรากฏบนบิลจริงได้' = กฎที่เปิด + รหัสจากชั้น parser/crosscheck.

    นี่คือชุดที่ "ตารางนำเสนอทุกตัวต้องครอบคลุม" (มิฉะนั้น issue จริงจะไม่มี label/ฟิลด์รองรับ).
    """
    return enabled_rule_codes() | set(EXTERNAL_EMITTED)


def known_codes() -> set:
    """รหัสที่ระบบ 'รู้จัก' ทั้งหมด (กฎทั้งหมดรวมที่ปิด + external).

    ใช้กัน 'โค้ดแปลกปลอม/typo' ในตารางนำเสนอ: ทุกรหัสในตารางต้องเป็นสมาชิกของชุดนี้.
    """
    return all_rule_codes() | set(EXTERNAL_EMITTED)
