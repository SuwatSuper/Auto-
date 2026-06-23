#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_date_parse_characterization.py — ตาข่ายล็อกพฤติกรรม parse_date_any ทุกสาขา (ADR-053)

ที่มา: บั๊ก ADR-052 (P4 เปลี่ยน ^anchor→re.search → ที่อยู่ "2/12-2/13" ถูกอ่านเป็น 1970) หลุด
ออกมาได้เพราะ "ไม่มีเทสที่ล็อกว่าที่อยู่ต้องไม่เป็นวันที่". เทสนี้ตรึงพฤติกรรมทุกสาขา (datetime/serial/
Thai-month/2-digit/4-digit/leap/adversarial/null) ด้วยค่าที่ถูกต้อง ณ golden ae84d3f0 — ใครแก้
parse_date_any แล้วสาขาใดเพี้ยน เทสนี้แดงทันที (ไม่ต้องรอ golden hash บนคลังใหญ่).

รันเดี่ยว:  python3 test_date_parse_characterization.py   (exit 0 = ผ่าน)
อยู่ในชุด:  run_ci.sh
"""
import sys, warnings
warnings.filterwarnings('ignore')
from datetime import datetime
from puopuy_dates import parse_date_any

# (ชื่อเคส, input, ค่าที่ต้องได้ '%Y-%m-%d' หรือ None) — ล็อก ณ golden ae84d3f0
CASES = [
    # --- datetime objects ---
    ('dt_ce_passthru',   datetime(2026, 5, 2),  '2026-05-02'),   # ค.ศ. ปกติ → คงเดิม
    ('dt_be_minus543',   datetime(2569, 5, 2),  '2026-05-02'),   # พ.ศ.2569 → -543 (M1/สาขา datetime)
    ('dt_be_badleap',    datetime(2568, 2, 29), None),           # 29ก.พ.พ.ศ.อธิกสุรทินที่ ค.ศ.ไม่ใช่ → safe()=None (M1: เดิมครัช)

    # --- serial ตัวเลข ---
    ('ser_ce_inrange',   46150.0,   '2026-05-08'),   # CE serial 30000-70000 (xldate)
    ('ser_be_raw_float', 244471.0,  '2026-05-02'),   # serial เก็บปี พ.ศ.ตรงๆ (float) → ADR-053 DT-FIX2
    ('ser_be_raw_int',   244471,    '2026-05-02'),   # เหมือนกันแบบ int
    ('ser_zero',         0,         None),
    ('ser_negative',    -1,         None),
    ('ser_huge',         99999999,  None),
    ('ser_oob_year',     280000,    None),            # พ.ศ.2666→ค.ศ.2123 นอกช่วง 2015-2056 → reject

    # --- สตริงเดือนไทย ---
    ('thai_2digit',      '2 พ.ค. 69',     '2026-05-02'),
    ('thai_4digit',      '15 ม.ค. 2569',  '2026-01-15'),
    ('thai_yr68',        '1 เม.ย. 68',    '2025-04-01'),

    # --- สตริงตัวเลข ปี 2 หลัก ---
    ('num2_be',          '5/5/69',           '2026-05-05'),   # พ.ศ.69
    ('num2_ce',          '1/1/15',           '2015-01-01'),   # ค.ศ.15
    ('num2_label_th',    'วันที่ 11/05/69',   '2026-05-11'),   # P4: label นำหน้า (re.search)
    ('num2_label_en',    'Date: 5/5/69',     '2026-05-05'),   # P4
    ('num2_with_time',   '5/5/69 10:00:00',  '2026-05-05'),

    # --- สตริงตัวเลข ปี 4 หลัก ---
    ('num4_be',          '11/05/2569',  '2026-05-11'),
    ('num4_iso_be',      '2569-05-11',  '2026-05-11'),
    ('num4_iso_ce',      '2026-05-11',  '2026-05-11'),
    ('num4_be_leap',     '29/02/2567',  '2024-02-29'),   # อธิกสุรทิน พ.ศ.2567=ค.ศ.2024 (recheck#5)

    # --- ADVERSARIAL: เลขคล้ายวันที่แต่ไม่ใช่วันที่ → ต้อง None ทั้งหมด ---
    ('adv_addr1',        '99/1 หมู่ 5 ตำบลคลองหนึ่ง',                None),
    ('adv_addr_range',   'เลขที่ 88/8-88/9 ซอย 3',                   None),
    ('adv_phone',        '02-123-4567',                              None),
    ('adv_taxid',        '0-1335-62004-42-6',                        None),
    ('adv_addr2',        '123/45 ถนนพหลโยธิน',                       None),
    ('adv_room',         'ห้อง 5/5 ชั้น 12',                          None),
    ('adv_ivnum',        'IV690502-11',                              None),
    ('adv_seq',          'ลำดับ 1/12',                                None),
    ('adv_dim',          '2.5/3.0 เมตร',                             None),
    ('adv_postal',       '12150',                                    None),
    ('adv_regr_1970',    '2/12-2/13 หมู่ที่ 3 ตำบลลำไทร อำเภอลำลูกกา', None),  # ← เคสบั๊ก ADR-052 (เดิม 1970-02-12)

    # --- null/empty ---
    ('null_none',        None,            None),
    ('null_empty',       '',              None),
    ('null_nan',         float('nan'),    None),
]


def main() -> int:
    fails = []
    for name, v, want in CASES:
        try:
            r = parse_date_any(v)
        except Exception as e:
            fails.append(f'{name}: ครัช {type(e).__name__}: {e}'); continue
        got = r.strftime('%Y-%m-%d') if r is not None else None
        if got != want:
            fails.append(f'{name}: got {got!r} ≠ want {want!r}  (input={v!r})')

    print('=' * 60)
    print(f'parse_date_any characterization — {len(CASES)} เคส')
    print('=' * 60)
    if fails:
        print(f'❌ FAIL {len(fails)}/{len(CASES)}')
        for f in fails:
            print('  -', f)
        return 1
    print(f'✅ PASS {len(CASES)}/{len(CASES)} — ทุกสาขาตรึงตรง golden ae84d3f0')
    # tripwire ย่อ: เคสบั๊กเดิมต้องไม่กลับมา
    assert parse_date_any('2/12-2/13 หมู่ที่ 3') is None, 'REGRESSION ADR-052: ที่อยู่ถูกอ่านเป็นวันที่!'
    return 0


if __name__ == '__main__':
    sys.exit(main())
