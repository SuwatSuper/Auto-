# -*- coding: utf-8 -*-
"""test_unit_missing_rules.py — ล็อกพฤติกรรม P2/P3 (ADR-105/106).

ตรึง:
  • ITM020 (`r_itm020`) flag เมื่อ "ทั้งบิล" ไม่มีหน่วย แต่มีรายการคิดเงิน (เคส TOR_67_08).
  • ITM020 "ไม่" flag เมื่อมีรายการที่มีหน่วยจริงปนอยู่ (เป็น intra-bill = ITM019 จับแทน).
  • _norm ตัดอักขระความกว้างศูนย์ (ZWNJ/ZWSP/BOM).
  • _is_real_unit ปฏิเสธค่าว่าง + หัวคอลัมน์ที่หลุด ('Unit'/'หน่วย'/ZWNJ+Unit).
  • คำในข้อความหน่วยขาด = ข้อเท็จจริง (ไม่มีคำ "ดึงมาไม่ครบ").

golden-fixture-independent: ทดสอบฟังก์ชันตรงๆ ด้วยบิลสังเคราะห์ (ไม่แตะ baseline_fixture).
"""
import sys
import unit_detection_ext as ux

_fail = []


def _check(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        _fail.append(msg)


def _bill(items):
    return {"company": "ทดสอบ", "file": "TEST.xlsx",
            "items": [dict(seq=i + 1, **it) for i, it in enumerate(items)]}


def main():
    print("=== [A] _norm ตัดอักขระความกว้างศูนย์ ===")
    _check(ux._norm("Set\u200c") == "Set", "Set+ZWNJ → 'Set'")
    _check(ux._norm("\u200cUnit") == "Unit", "ZWNJ+Unit → 'Unit'")
    _check(ux._norm("กก.\u200b") == "กก.", "กก.+ZWSP → 'กก.'")
    _check(ux._norm("\ufeffm") == "m", "BOM+m → 'm'")

    print("\n=== [B] _is_real_unit ปฏิเสธว่าง + หัวคอลัมน์หลุด ===")
    _check(not ux._is_real_unit(""), "'' → ไม่ใช่หน่วยจริง")
    _check(not ux._is_real_unit(None), "None → ไม่ใช่หน่วยจริง")
    _check(not ux._is_real_unit("\u200cUnit"), "ZWNJ+Unit (หัวคอลัมน์หลุด) → ไม่ใช่หน่วยจริง")
    _check(not ux._is_real_unit("Unit"), "'Unit' → ไม่ใช่หน่วยจริง")
    _check(not ux._is_real_unit("หน่วย"), "'หน่วย' → ไม่ใช่หน่วยจริง")
    _check(ux._is_real_unit("ท่อน"), "'ท่อน' → หน่วยจริง")
    _check(ux._is_real_unit("PCS"), "'PCS' → หน่วยจริง")

    print("\n=== [C] ITM020 'ทั้งบิลไม่มีหน่วย' (เคส TOR_67_08) ===")
    b_all_blank = _bill([{"name": "ผ้า", "unit": "", "amount": 30000},
                         {"name": "ซิป", "unit": "", "amount": 46200}])
    out = ux.r_itm020(b_all_blank, None, None)
    _check(len(out) == 1 and "ทั้งบิลไม่มีหน่วยสินค้า" in out[0],
           "ทุกรายการไม่มีหน่วย + มียอด → ITM020 flag")
    _check("2 รายการ" in out[0] and "ผ้า" in out[0] and "ซิป" in out[0],
           "ITM020 ระบุจำนวน + ชื่อรายการ")

    print("\n=== [D] ITM020 ต้อง 'ไม่' flag เมื่อเป็น intra-bill (ITM019 จับแทน) ===")
    b_mixed = _bill([{"name": "ผ้า", "unit": "", "amount": 30000},
                     {"name": "เหล็ก", "unit": "เส้น", "amount": 5000}])
    _check(ux.r_itm020(b_mixed, None, None) == [],
           "บางรายการมีหน่วย (เส้น) → ITM020 ไม่ยิง (เป็นงานของ ITM019)")
    # และ ITM019 ต้องยังจับ intra-bill นี้
    itm019 = ux.detect_missing_units_in_bill(b_mixed["items"])
    _check(any("ไม่มีหน่วยสินค้า" in m for m in itm019),
           "ITM019 (intra-bill) ยังจับรายการ ผ้า ที่หน่วยขาด")

    print("\n=== [E] header 'Unit' หลุด = หน่วยขาด (ADR-105) ===")
    b_hdr = _bill([{"name": "กล้อง", "unit": "\u200cUnit", "amount": 1000},
                   {"name": "เสา", "unit": "pcs", "amount": 2000}])
    itm019h = ux.detect_missing_units_in_bill(b_hdr["items"])
    _check(any("กล้อง" in m for m in itm019h),
           "รายการที่หน่วย='Unit'(หัวคอลัมน์หลุด) → ถูกตรวจเป็นหน่วยขาด")

    print("\n=== [F] คำต้องเป็นข้อเท็จจริง (ไม่มี 'ดึงมาไม่ครบ') ===")
    all_msgs = " ".join(ux.detect_missing_units_in_bill(b_mixed["items"]) +
                        ux.r_itm020(b_all_blank, None, None))
    _check("ดึงมาไม่ครบ" not in all_msgs, "ไม่มีคำ 'ดึงมาไม่ครบ' (สื่อว่าระบบพลาด)")
    _check("ช่องหน่วยว่างในต้นฉบับ" in all_msgs, "ใช้คำ 'ช่องหน่วยว่างในต้นฉบับ'")

    print()
    if _fail:
        print(f"RESULT: ❌ FAIL — {len(_fail)} เคส")
        sys.exit(1)
    print("RESULT: ✅ PASS — ITM020/ZWNJ/header/wording ตรึงครบ (ADR-105/106)")


if __name__ == "__main__":
    main()
