# -*- coding: utf-8 -*-
"""test_iv_money_misread.py — [F-MONEYIV v9.3.1] กัน "ยอดเงินบนบิล" ถูกอ่านเป็นเลขที่เอกสาร

เคสจริง (SHS 69.05 เพิ่ม — 21 บิล): _parse_block ตั้ง header_end = row_start+20 ครอบทั้งชีต
รวมแถวยอดรวม → _pick_best_iv รับเลขล้วน ≥5 หลัก → subtotal 6 หลัก เช่น '200500' (score 27)
ชนะเลขเอกสารจริง 5 หลัก '05070' (score 25) เพราะ pandas อ่านยอดที่ลงตัวเป็น int (ไม่มี '.0')
→ money-guard เดิม (\\.\\d) ไม่ทำงาน. ผล: iv = ยอดเงิน → IV003 (เลขซ้ำข้ามวัน),
DT004/period-embed (ยอด 202000→ฝังงวด 2020), IV004 (ไม่ไล่เรียง) ฟ้องผิดทั้งชุดแม้บิลถูก.

Invariant ที่ล็อก: "เลขที่เอกสาร ≠ ยอดเงินใด ๆ บนบิลเดียวกัน". ถ้า iv == ยอด → ล้าง iv แล้ว
เรียก last-resort กู้เลขจริง (เลขโดด 4-5 หลักที่ติดวันที่/อยู่ครึ่งขวา).

golden: corpus 834 บิล ไม่มีบิลใด iv == ยอดของตัวเอง → guard dormant 100% → hash ไม่ขยับ.
"""
import os
import re
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser_guards import reject_iv_equal_amount, _bill_amount_strings  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond, label):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ✅ {label}")
    else:
        _FAIL += 1
        print(f"  ❌ {label}")


def df_of(rows, ncols):
    grid = []
    for r in rows:
        row = [None] * ncols
        for c, v in r.items():
            row[c] = v
        grid.append(row)
    return pd.DataFrame(np.array(grid, dtype=object))


# ---------------------------------------------------------------------------
# [V1] _bill_amount_strings: ยอดจำนวนเต็ม → string เลขเต็ม; ยอดมีเศษทศนิยม → ไม่เข้า set
print("[V1] _bill_amount_strings: subtotal/vat/total + ยอดรายการ (เฉพาะที่ลงตัว)")
res = {
    'subtotal': 200500.0, 'vat': 14035.0, 'total': 214535.0,
    'items': [{'amount': 50000.0}, {'amount': 100000.5}],   # 100000.5 มีเศษ → ตัดทิ้ง
}
amts = _bill_amount_strings(res)
check(amts == {'200500', '14035', '214535', '50000'},
      f"set ถูกต้อง (ตัด 100000.5 ทิ้ง) — got={sorted(amts)}")

# ---------------------------------------------------------------------------
# [V2] core: iv == subtotal → ล้าง + กู้เลขจริง '05070' (ติดวันที่ครึ่งขวา)
print("[V2] iv == subtotal (200500) → กู้คืนเป็น '05070'")
df = df_of([
    {0: 'บริษัท ไทย ยู คิง จำกัด'},
    {0: 'เลขประจำตัวผู้เสียภาษี 0105558123914'},
    {},
    {},
    {20: '05070'},                 # เลขเอกสารจริง
    {20: datetime(2569, 5, 4)},    # วันที่ติดใต้เลข (Manhattan dist = 1)
], ncols=23)
res = {'iv_number': '200500', 'iv_number_raw': '200500',
       'subtotal': 200500.0, 'vat': 14035.0, 'total': 214535.0, 'items': []}
reject_iv_equal_amount(df, res, 0, 20, 23)
check(res['iv_number'] == '05070', f"iv กู้เป็น '05070' — got={res['iv_number']!r}")
check(res['iv_number_raw'] == '05070', f"iv_raw กู้เป็น '05070' — got={res['iv_number_raw']!r}")

# ---------------------------------------------------------------------------
# [V3] dormancy: iv ถูกต้อง (ไม่ตรงยอดใด) → guard ต้องไม่แตะ (พิสูจน์ golden-neutral)
print("[V3] iv ถูกต้องอยู่แล้ว (≠ ยอด) → guard dormant ไม่เปลี่ยนค่า")
df = df_of([{20: '05070'}, {20: datetime(2569, 5, 4)}], ncols=23)
res = {'iv_number': '05070', 'iv_number_raw': '05070',
       'subtotal': 200500.0, 'vat': 14035.0, 'total': 214535.0, 'items': []}
reject_iv_equal_amount(df, res, 0, 20, 23)
check(res['iv_number'] == '05070', f"iv คงเดิม '05070' — got={res['iv_number']!r}")

# ---------------------------------------------------------------------------
# [V4] iv == ยอด "รายการสินค้า" (ไม่ใช่แค่ subtotal) → ก็ต้องถูกปฏิเสธ
print("[V4] iv == ยอดรายการสินค้า (50000) → กู้คืนเป็น '05070'")
df = df_of([
    {0: 'บริษัท ไทย ยู คิง จำกัด'},
    {},
    {},
    {},
    {20: '05070'},
    {20: datetime(2569, 5, 4)},
], ncols=23)
res = {'iv_number': '50000', 'iv_number_raw': '50000',
       'subtotal': 200500.0, 'vat': 14035.0, 'total': 214535.0,
       'items': [{'amount': 50000.0}]}
reject_iv_equal_amount(df, res, 0, 20, 23)
check(res['iv_number'] == '05070', f"iv กู้เป็น '05070' — got={res['iv_number']!r}")

# ---------------------------------------------------------------------------
# [V5] iv ว่าง → guard ไม่ทำอะไร (ไม่ใช่หน้าที่ของ guard นี้ — IV005 จัดการเอง)
print("[V5] iv ว่าง → reject_iv_equal_amount ไม่ทำงาน (return เร็ว)")
res = {'iv_number': '', 'iv_number_raw': '', 'subtotal': 200500.0,
       'vat': 14035.0, 'total': 214535.0, 'items': []}
df = df_of([{20: '05070'}, {20: datetime(2569, 5, 4)}], ncols=23)
reject_iv_equal_amount(df, res, 0, 20, 23)
check(res['iv_number'] == '', f"iv ยังว่าง (ไม่กู้มั่ว) — got={res['iv_number']!r}")

# ---------------------------------------------------------------------------
# [V6] integration บนไฟล์จริง (ถ้ามี): SHS 21 บิล ต้องได้เลขเรียง 05029..05746 ครบ
#      presence-gated — ไม่มีไฟล์ (CI/เครื่อง Tor) → ข้ามอย่างสุภาพ ไม่ทำเทสล้ม
SHS = '/mnt/user-data/uploads/SHS_69_05_เพ__ม.xls'
EXPECTED = ['05029', '05070', '05112', '05144', '05171', '05206', '05245',
            '05294', '05309', '05351', '05380', '05414', '05458', '05499',
            '05526', '05558', '05601', '05642', '05677', '05715', '05746']
if os.path.exists(SHS):
    print("[V6] integration: parse ไฟล์ SHS จริง → เลขเอกสารเรียงครบ + ไม่มี iv==ยอด")
    import parser_p2 as P
    bills = P.parse_file(SHS)
    got = [str(b.get('iv_number') or '') for b in bills]
    check(len(bills) == 21, f"ได้ 21 บิล — got={len(bills)}")
    check(got == EXPECTED, f"เลขเอกสารตรง expected ทั้ง 21 — got={got}")
    bad = []
    for b in bills:
        ivd = re.sub(r'\D', '', str(b.get('iv_number') or ''))
        for k in ('subtotal', 'vat', 'total'):
            v = b.get(k)
            if isinstance(v, (int, float)) and v == int(v) and str(int(v)) == ivd:
                bad.append((b.get('iv_number'), k))
    check(not bad, f"ไม่มีบิลใด iv == ยอดเงิน — bad={bad}")
else:
    print("[V6] integration: ข้าม (ไม่พบไฟล์ SHS อัปโหลด — เป็นเทส presence-gated)")

print()
print(f"ผล: ✅ {_PASS} | ❌ {_FAIL}")
sys.exit(0 if _FAIL == 0 else 1)
