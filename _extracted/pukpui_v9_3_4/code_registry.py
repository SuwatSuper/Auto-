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
  (import โดยเทส + ชีต Rules ของรายงาน [A2] เพื่อโชว์สถานะกฎ ; golden hash ผลตรวจบิล
   ไม่ใช่ RULES/Excel → ไม่กระทบ golden).
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
    "IV005": "validators.apply_missing_iv_check (บิลไม่มีเลขที่ใบกำกับ)",
    "DT006": "validators.apply_bad_date_check (วันที่ไม่มีจริงในปฏิทิน)",
    "IV006": "validators.apply_abbrev_invoice_check (ใบกำกับภาษีอย่างย่อ)",
}


# ── [A2] สถานะกฎที่ "โปร่งใส" — กันสถิติหลอกตา (โฆษณา "56 กฎ" แต่บางกฎไม่ทำงาน) ──────────────
#   แยกกฎเป็น 3 กลุ่มพร้อมเหตุผล. "ห้ามนับ disabled/unavailable เป็น active coverage".
#   หมายเหตุ: ชั้น metadata ล้วน — ไม่เปลี่ยนพฤติกรรม runtime/golden (golden hash ผลตรวจบิล ไม่ใช่ RULES).
#
# กลุ่ม 2 — "ปิดโดยตั้งใจ" (enabled=False) + เหตุผลกำกับ (ต้องครอบทุกกฎที่ enabled=False ; test คุม)
DISABLED_BY_DESIGN = {
    "VAT004": "เจ้าของสั่งปิด — ยอดที่ปัดทศนิยมเป็น 2 ตำแหน่งเพื่อแสดงผลถูกต้องอยู่แล้ว (float residue ไม่ใช่ error)",
    "VAT010": "เจ้าของสั่งปิด — ยอด VAT/total ที่ระบบคำนวณเอง (derived) ไม่ตรวจ",
    "ITM008": "false positive — ราคา/หน่วยสูงเป็นสินค้าแพงปกติ (ITM001 จับเลขผิดจริงแทนอยู่แล้ว)",
    "BR003":  "ผู้ขายมีทั้ง สนญ.+สาขา เป็นเรื่องปกติ ไม่ใช่ error (ฟ้องผิด/ซ้ำทุกบิล)",
    "DOC002": "parse งวดจาก IV แบบ universal ไม่ได้ (รูปเลขที่เอกสารหลากหลายเกินจะเดางวด)",
}

# กลุ่ม 3 — "เปิดแต่ทำงานไม่ได้" เพราะขาด resource (ตายเงียบ ไม่ใช่ปิด) : code → (resource, อธิบาย)
UNAVAILABLE_RESOURCE = {
    "ITM009": ("product_master.json",
               "ตรวจ alias สินค้า — ถ้าไม่มี PRODUCT_MASTER กฎคืน [] เงียบ (เปิดแต่ไม่เคยยิง)"),
}


def product_master_available() -> bool:
    """resource ของ ITM009 (และ whitelist ITM012) — product_master.json โหลดได้และไม่ว่างไหม."""
    try:
        from rules_engine import PRODUCT_MASTER
        return bool(PRODUCT_MASTER)
    except Exception:
        return False


def disabled_by_design_codes() -> set:
    """กฎที่ปิดโดยตั้งใจ (enabled=False ใน RULES) — แหล่งความจริง = RULES (DISABLED_BY_DESIGN ให้เหตุผล)."""
    return {c for c, r in RULES.items() if not r.get("enabled", True)}


def unavailable_rule_codes() -> set:
    """กฎที่ enabled=True แต่ทำงานไม่ได้เพราะขาด resource ณ ตอนนี้ (เช่น ITM009 ไม่มี product_master.json)."""
    out = set()
    en = enabled_rule_codes()
    if "ITM009" in en and not product_master_available():
        out.add("ITM009")
    return out


def active_rule_codes() -> set:
    """กฎที่ 'ทำงานจริง' = เปิด และไม่ติด resource — ชุดนี้เท่านั้นที่นับเป็น active coverage."""
    return enabled_rule_codes() - unavailable_rule_codes()


def rule_status(code: str) -> str:
    """สถานะกฎ 1 รหัส: 'active' | 'disabled-by-design' | 'unavailable-resource'."""
    if code in disabled_by_design_codes():
        return "disabled-by-design"
    if code in unavailable_rule_codes():
        return "unavailable-resource"
    return "active"


def rule_status_reason(code: str) -> str:
    """เหตุผลกำกับสถานะ (ว่างถ้า active)."""
    if code in DISABLED_BY_DESIGN:
        return DISABLED_BY_DESIGN[code]
    if code in UNAVAILABLE_RESOURCE:
        res, why = UNAVAILABLE_RESOURCE[code]
        return f"ขาด {res}: {why}"
    return ""


def rule_status_report() -> dict:
    """สรุปสถานะกฎ 3 กลุ่ม (รหัส + เหตุผล) — สำหรับ coverage/dashboard (กันสถิติหลอกตา)."""
    return {
        "active": sorted(active_rule_codes()),
        "disabled-by-design": {c: rule_status_reason(c) for c in sorted(disabled_by_design_codes())},
        "unavailable-resource": {c: rule_status_reason(c) for c in sorted(unavailable_rule_codes())},
    }


def format_rule_coverage() -> str:
    """ข้อความสรุป coverage กฎแบบอ่านง่าย (ใช้ใน dashboard/ท้ายการรัน). active ไม่รวม disabled/unavailable."""
    rep = rule_status_report()
    n_all = len(all_rule_codes())
    lines = [f"RULE COVERAGE — ทั้งหมด {n_all} กฎ | active {len(rep['active'])} "
             f"| ปิดโดยตั้งใจ {len(rep['disabled-by-design'])} "
             f"| เปิดแต่ขาด resource {len(rep['unavailable-resource'])}"]
    for c, why in rep["disabled-by-design"].items():
        lines.append(f"  [disabled-by-design] {c}: {why}")
    for c, why in rep["unavailable-resource"].items():
        lines.append(f"  [unavailable-resource] {c}: {why}")
    return "\n".join(lines)


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
