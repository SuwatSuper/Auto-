# -*- coding: utf-8 -*-
"""test_adr144_thai_month_ambiguous.py — [ADR-144/VDU-1] เดือนไทย + ปี 2 หลัก "กำกวม" → None
ให้สอดคล้องสาขา D/M/YY (m_yy) แทนที่จะ fabricate วันมั่ว.

บั๊ก (VDU — date fabrication): สาขา "เดือนไทย" ของ parse_date_any เดิมใช้
    if _ce is None: year = year + 2500   (แล้ว -543)
สำหรับปี 2 หลักที่ _ivp_year2_to_ce คืน None (ช่วงกำกวม 00-14 / 40-57) → "fabricate" วันมั่ว:
  '5 พ.ค. 45' → 2002 ; '1 ม.ค. 13' → 1970   ← ขัดสาขา D/M/YY (m_yy) ที่คืน None ในเคสเดียวกัน
  + ขัดเจตนา ADR-052 ("ห้ามเดาวันให้ที่อยู่/ปีกำกวมชนะ date จริง").
แก้ (ADR-144): _ce is None → break → ตก None เหมือน m_yy. corpus ปี 66-69 ∈ 58-99 → _ce≠None
  → byte-identical (golden ไม่ขยับ). รันได้ทุกที่ (ไม่พึ่ง corpus).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import puopuy_dates as PD

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def _y(v):
    """parse → ปี ค.ศ. (หรือ None)"""
    d = PD.parse_date_any(v)
    return None if d is None else d.year


def main():
    print('=== เดือนไทย + ปีกำกวม (00-14 / 40-57) → None (ไม่ fabricate) ===')
    # 45 ∈ 40-57 (กำกวม) — เดิม fabricate 2002
    _check(PD.parse_date_any('5 พ.ค. 45') is None, "'5 พ.ค. 45' (45 กำกวม) → None")
    # 13 ∈ 00-14 (กำกวม) — เดิม fabricate 1970
    _check(PD.parse_date_any('1 ม.ค. 13') is None, "'1 ม.ค. 13' (13 กำกวม) → None")
    _check(PD.parse_date_any('15 ส.ค. 50') is None, "'15 ส.ค. 50' (50 กำกวม) → None")
    _check(PD.parse_date_any('1 ก.ค. 00') is None, "'1 ก.ค. 00' (00 กำกวม) → None")

    print('=== สอดคล้องสาขา D/M/YY (m_yy) — เดือนไทย == slash ในเคสกำกวม ===')
    _check(PD.parse_date_any('5 พ.ค. 45') == PD.parse_date_any('5/5/45'),
           "'5 พ.ค. 45' == '5/5/45' (ทั้งคู่ None)")
    _check(PD.parse_date_any('1 ม.ค. 13') == PD.parse_date_any('1/1/13'),
           "'1 ม.ค. 13' == '1/1/13' (ทั้งคู่ None)")

    print('=== ปีในช่วงรู้จัก (corpus-range) → byte-identical (golden ไม่ขยับ) ===')
    # 58-99 = พ.ศ.ย่อ → ค.ศ.
    _check(_y('5 พ.ค. 69') == 2026, "'5 พ.ค. 69' → 2026 (พ.ศ.2569)")
    _check(_y('1 ม.ค. 66') == 2023, "'1 ม.ค. 66' → 2023 (พ.ศ.2566)")
    _check(_y('15 ส.ค. 67') == 2024, "'15 ส.ค. 67' → 2024 (พ.ศ.2567)")
    # 15-39 = ค.ศ.ย่อ
    _check(_y('1 ม.ค. 25') == 2025, "'1 ม.ค. 25' → 2025 (ค.ศ.ย่อ)")
    # ปี 4 หลัก (เดือนไทย) ไม่กระทบ
    _check(_y('5 พ.ค. 2569') == 2026, "'5 พ.ค. 2569' (4 หลัก) → 2026 (ไม่แตะ)")
    _check(_y('5 พ.ค. 2026') == 2026, "'5 พ.ค. 2026' (ค.ศ. 4 หลัก) → 2026")

    print('=== วันที่ตรง (day/month) ของปีรู้จักต้องถูกครบ — กัน regression ===')
    d = PD.parse_date_any('15 ส.ค. 67')
    _check(d is not None and (d.month, d.day) == (8, 15), "'15 ส.ค. 67' → 2024-08-15 (เดือน/วันถูก)")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — เดือนไทยปีกำกวม→None สอดคล้อง m_yy ; ปีรู้จัก byte-identical')
    return 0


if __name__ == '__main__':
    sys.exit(main())
