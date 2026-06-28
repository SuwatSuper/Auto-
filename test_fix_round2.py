# -*- coding: utf-8 -*-
"""test_fix_round2.py — ตรึงการแก้รอบ 2 (M-1 master data-loss + T-1 year window)

M-1 : input_master_data ตอบ n = เพิ่ม/แก้ต่อจากเดิม (ไม่ลบของเก่า) + save_master ทำ .bak
T-1 : _ivp_year2/4_to_ce เพดานปีขยายถึง พ.ศ.2599 / ค.ศ.2056 (โซนกำกวม 40–57 คง None)
"""
import json
import os
import sys
from unittest.mock import patch

_results = []
def check(cond, msg):
    _results.append((bool(cond), msg))
    print(f"  {'✅' if cond else '❌'} {msg}")

print("=" * 64)
print("FIX ROUND 2 — M-1 master data-loss + T-1 year window")
print("=" * 64)

# ── T-1 : year windows ─────────────────────────────────────────────────────
from puopuy_dates import _ivp_year2_to_ce as y2, _ivp_year4_to_ce as y4, parse_date_any

check(y2(69) == (2026, 'พ.ศ.'), "T-1: ปี 69 → 2026 (corpus เดิมไม่ขยับ)")
check(y2(66) == (2023, 'พ.ศ.'), "T-1: ปี 66 → 2023")
check(y2(26) == (2026, 'ค.ศ.'), "T-1: ปี 26 → ค.ศ. 2026")
check(y2(83) == (2040, 'พ.ศ.'), "T-1: ปี 83 → 2040 (ระเบิดเวลาปลดแล้ว)")
check(y2(99) == (2056, 'พ.ศ.'), "T-1: ปี 99 → 2056 (เพดานใหม่)")
check(y2(40) == (None, None) and y2(57) == (None, None),
      "T-1: โซนกำกวม 40–57 ยัง None (ตั้งใจ)")
check(y4(2583) == (2040, 'พ.ศ.') and y4(2599) == (2056, 'พ.ศ.'),
      "T-1: พ.ศ. 4 หลัก 2583/2599 ตีถูก")
check(y4(2040) == (2040, 'ค.ศ.') and y4(2056) == (2056, 'ค.ศ.'),
      "T-1: ค.ศ. 4 หลัก 2040/2056 ตีถูก")
check(y4(2057) == (None, None) and y4(2557) == (None, None),
      "T-1: นอกหน้าต่าง 4 หลัก ยัง None")
check(parse_date_any('5/5/83').year == 2040, "T-1: parse_date_any('5/5/83') → 2040")
check(parse_date_any('5/5/69').year == 2026, "T-1: parse_date_any('5/5/69') → 2026")

# ── M-1 : master add-no-wipe + .bak ────────────────────────────────────────
import master as M

_MF = M.CFG['MASTER_FILE']
_BAK = _MF + '.bak'
_orig = open(_MF, encoding='utf-8').read() if os.path.exists(_MF) else None
_orig_bak = open(_BAK, encoding='utf-8').read() if os.path.exists(_BAK) else None

try:
    if os.path.exists(_BAK):
        os.remove(_BAK)
    existing = {
        'ฉี อัน คอนสตรัคชั่น': {'name': 'บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด',
                                'tax_id': '0105566206726', 'branch': 'สำนักงานใหญ่',
                                'branch_no': '00000', 'iv_prefix': 'IV',
                                'address_full': 'x', 'address_parts': {}},
        'วัชราวุธ เอ็นจิเนียริ่ง': {'name': 'หจก. วัชราวุธ', 'tax_id': '0103533033921',
                                    'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
                                    'iv_prefix': 'IV', 'address_full': 'y',
                                    'address_parts': {}},
    }
    with open(_MF, 'w', encoding='utf-8') as f:
        json.dump(existing, f, ensure_ascii=False)

    answers = iter(['n',
        '0-2055-55015-71-1\t00001\tบริษัท เถ้าแก่เนี้ย จำกัด '
        'เลขที่ 9/16 ตำบลหนองซ้ำซาก อำเภอบ้านบึง จังหวัดชลบุรี 20170',
        '', '', '', '', '', '', ''])
    with patch('builtins.input', lambda *a: next(answers)):
        result = M.input_master_data()
    M.save_master(result)   # จำลอง double-save แบบ เพิ่ม_master.py

    final = json.load(open(_MF, encoding='utf-8'))
    check(len(final) == 3 and 'ฉี อัน คอนสตรัคชั่น' in final and 'เถ้าแก่เนี้ย' in final,
          f"M-1: เพิ่มบริษัทแล้วของเดิมอยู่ครบ (ได้ {len(final)} บริษัท)")
    bak = json.load(open(_BAK, encoding='utf-8')) if os.path.exists(_BAK) else {}
    check(len(bak) == 2, f"M-1b: .bak เก็บสภาพก่อนแก้ (2 บริษัท — ได้ {len(bak)})")

    M.save_master({})   # wipe ตั้งใจ
    bak2 = json.load(open(_BAK, encoding='utf-8'))
    check(len(bak2) == 3, f"M-1b: wipe แล้วกู้จาก .bak ได้ (3 บริษัท — ได้ {len(bak2)})")
finally:
    # คืนสภาพไฟล์จริงเสมอ — เทสห้ามทิ้งร่องรอย
    if _orig is not None:
        with open(_MF, 'w', encoding='utf-8') as f:
            f.write(_orig)
    elif os.path.exists(_MF):
        os.remove(_MF)
    if _orig_bak is not None:
        with open(_BAK, 'w', encoding='utf-8') as f:
            f.write(_orig_bak)
    elif os.path.exists(_BAK):
        os.remove(_BAK)

# ── สรุป ──────────────────────────────────────────────────────────────────
_fail = [m for ok, m in _results if not ok]
print("=" * 64)
print(f"FIX ROUND 2: ผ่าน {len(_results) - len(_fail)} / ล้มเหลว {len(_fail)}")
print("=" * 64)
if _fail:
    for m in _fail:
        print(f"  • {m}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ ตรึง M-1 + T-1 ครบ")
