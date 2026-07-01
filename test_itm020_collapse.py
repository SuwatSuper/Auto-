# -*- coding: utf-8 -*-
"""test_itm020_collapse.py — ล็อก ADR-108/UX: ยุบ ITM020 (ทั้งบิลไม่มีหน่วยสินค้า) เป็น
"สรุปต่อไฟล์" 1 บรรทัด/ไฟล์ (นับบิล) ไม่ร่ายทีละบิล — ทั้ง company_summary และ vendor_report.

เจ้าของแย้ง: บริษัทเดียว 50 บิลไม่มีหน่วย → รายงานพ่นทีละบิล 50 บรรทัด ดูเหมือนเครื่องดัมพ์.
ต้องสรุปสั้น "ไฟล์ X: N บิลไม่มีหน่วยสินค้าทั้งบิล" ; typo รายการสินค้าจริง (มี seq) คงชี้ทีละตัว.
advisory-only — ไม่แตะ golden 31013a31.
"""
import sys

_fail = []


def _check(msg, cond):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        _fail.append(msg)


def main():
    # ── (A) company_summary: super_ultra_viewer._pinpoint_field ──
    print("=== [A] company_summary — ยุบ ITM020 ต่อไฟล์ + typo คงรายตัว ===")
    import super_ultra_viewer as suv
    F_ITEM = suv.F_ITEM
    entries = [
        {"code": "ITM020", "prefix": "TOR", "date": "02.08.2024", "seq": None,
         "detail": "ทั้งบิลไม่มีหน่วยสินค้า — 2 รายการคิดเงินไม่มีหน่วย (ช่องหน่วยว่างในต้นฉบับ): #1 \"ผ้า\", #2 \"ซิป\""},
        {"code": "ITM020", "prefix": "TOR", "date": "03.08.2024", "seq": None,
         "detail": "ทั้งบิลไม่มีหน่วยสินค้า — 1 รายการคิดเงินไม่มีหน่วย (ช่องหน่วยว่างในต้นฉบับ): #1 \"ผ้า\""},
        {"code": "ITM020", "prefix": "TOR", "date": "05.08.2024", "seq": None,
         "detail": "ทั้งบิลไม่มีหน่วยสินค้า — 3 รายการคิดเงินไม่มีหน่วย (ช่องหน่วยว่างในต้นฉบับ): #1 \"ผ้า\""},
        {"code": "ITM004", "prefix": "TKH", "date": "14.05.2026", "seq": 3,
         "detail": '#3: "ปี๊ป" น่าจะเป็น "ปี๊บ"'},
    ]
    out = suv._pinpoint_field(F_ITEM, entries)
    _check("ITM020 ยุบเป็น 'ไฟล์ TOR: 3 บิล...' (นับบิลถูก)",
           "ไฟล์ TOR: 3 บิลไม่มีหน่วยสินค้าทั้งบิล" in out)
    _check("ยุบเหลือ 1 บรรทัดสรุป (ไม่ใช่ 3)",
           out.count("บิลไม่มีหน่วยสินค้าทั้งบิล") == 1)
    _check("ไม่ร่ายทีละบิล (ไม่มี 'ทั้งบิลไม่มีหน่วยสินค้า — N รายการ')",
           "ทั้งบิลไม่มีหน่วยสินค้า — " not in out)
    _check("typo รายการสินค้าจริงยังชี้รายตัว (TKH ปี๊ป)",
           "ปี๊ป" in out and "TKH" in out)

    # ── (B) vendor_report: _item_field_text ──
    print("\n=== [B] vendor_report — ยุบ ITM020 ต่อไฟล์ ===")
    from agents.vendor_report_ext import _item_field_text
    vbills = [
        {"file": "TOR_67_08.xls", "iv_date_str": "02/08/2024",
         "issues": [{"code": "ITM020", "detail": "ทั้งบิลไม่มีหน่วยสินค้า — 2 รายการ: #1 \"ผ้า\""}]},
        {"file": "TOR_67_08.xls", "iv_date_str": "03/08/2024",
         "issues": [{"code": "ITM020", "detail": "ทั้งบิลไม่มีหน่วยสินค้า — 1 รายการ: #1 \"ผ้า\""}]},
        {"file": "TOR_67_08.xls", "iv_date_str": "05/08/2024",
         "issues": [{"code": "ITM020", "detail": "ทั้งบิลไม่มีหน่วยสินค้า — 3 รายการ: #1 \"ผ้า\""}]},
    ]
    out2 = _item_field_text(vbills)
    _check("ITM020 ยุบเป็น 'ไฟล์ TOR: 3 บิล...'",
           "ไฟล์ TOR: 3 บิลไม่มีหน่วยสินค้าทั้งบิล" in out2)
    _check("ไม่ร่ายทีละบิล",
           "ทั้งบิลไม่มีหน่วยสินค้า — " not in out2)

    print()
    if _fail:
        print(f"RESULT: ❌ FAIL — {len(_fail)} เคส")
        sys.exit(1)
    print("RESULT: ✅ PASS — ITM020 สรุปต่อไฟล์ (ADR-108) ทั้งสองรายงาน + typo คงรายตัว")


if __name__ == "__main__":
    main()
