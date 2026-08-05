# -*- coding: utf-8 -*-
"""test_adr142_date_2digit_fallback.py — [ADR-142] ตัด '%d/%m/%y' fallback ที่ fabricate วันปี 2 หลัก.

บั๊ก (กลาง, false-negative · golden-path): `parse_date_any` มี strptime fallback `'%d/%m/%y'` ที่
ตีปี 2 หลักด้วย pivot 1969 ของ Python (yy<=68→20yy) "หลัง" สาขา m_yy (Thai-aware) ปฏิเสธไปแล้ว:
  - '29/2/68' (พ.ศ.2568=ค.ศ.2025 ไม่อธิกสุรทิน → 29ก.พ.ไม่มีจริง) → m_yy ล้ม → fallback → 2068-02-29
    (2068 อธิกสุรทิน) = "วันอนาคต 43 ปี" แทน flag DT006 = false-negative.
  - '12/2/13' (ปีกำกวม 00-14 ที่ ADR-052 จงใจคืน None) → fallback → 2013 = ที่อยู่ชนะ date cell จริง.
แก้: ตัด '%d/%m/%y' (m_yy ครอบ D/M/YY valid ทุกตัวอยู่แล้ว). corpus 66-69 → m_yy คืนก่อน ไม่ถึง fallback
→ byte-identical (golden=23b315e8). ปีกำกวม/วันไม่มีจริง → None → DT006/bad-date ทำงาน.
รันได้ทุกที่.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from puopuy_dates import parse_date_any

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== วันเสีย/กำกวม → None (ไม่ fabricate วันอนาคต) = DT006/bad-date ทำงาน ===')
    _check(parse_date_any('29/2/68') is None,
           "'29/2/68' → None (29ก.พ.พ.ศ.2568=2025 ไม่มีจริง ; ไม่ใช่ 2068-02-29)")
    _check(parse_date_any('12/2/13') is None,
           "'12/2/13' → None (ปีกำกวม 00-14, ADR-052 ; ไม่ใช่ 2013)")
    _check(parse_date_any('5/5/45') is None,
           "'5/5/45' → None (ปีกำกวม 40-57 ; ไม่ fabricate 2045)")

    print('=== วันปี 2 หลัก valid (พ.ศ.ย่อ) คงเดิม byte-identical (m_yy จัดการ) ===')
    import datetime as _dt
    _check(parse_date_any('5/5/69') == _dt.datetime(2026, 5, 5), "'5/5/69' → 2026-05-05 (เดิม)")
    _check(parse_date_any('11/05/69') == _dt.datetime(2026, 5, 11), "'11/05/69' → 2026-05-11 (เดิม)")
    _check(parse_date_any('1/1/66') == _dt.datetime(2023, 1, 1), "'1/1/66' → 2023-01-01 (เดิม)")
    _check(parse_date_any('วันที่ 5/5/69') == _dt.datetime(2026, 5, 5), "label นำหน้ายังได้ (m_yy re.search)")

    print('=== format อื่นไม่กระทบ (ISO / 4-หลัก / พ.ศ.4หลัก) ===')
    _check(parse_date_any('2026-05-11') == _dt.datetime(2026, 5, 11), "ISO เดิม")
    _check(parse_date_any('5/5/2026') == _dt.datetime(2026, 5, 5), "'%d/%m/%Y' 4-หลัก เดิม")
    _check(parse_date_any('29/2/2567') == _dt.datetime(2024, 2, 29), "พ.ศ.4หลักอธิกสุรทิน (2024) เดิม")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — ตัด fallback fabricate วันปี 2 หลัก ; valid byte-identical ; วันเสีย→None→DT006')
    return 0


if __name__ == '__main__':
    sys.exit(main())
