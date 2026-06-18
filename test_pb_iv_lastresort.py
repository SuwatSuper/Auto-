# -*- coding: utf-8 -*-
"""test_pb_iv_lastresort.py — [F2-FIX v9.3] fallback "เลขเอกสารโดด ๆ 4-5 หลัก" (layout TNT)

เคสจริง (TNT 11.06.69): layout มีเลขเดียว '01954' มุมขวาบน (string, ไม่มี label/prefix,
ใต้เลขเป็น cell วันที่) → _pick_best_iv ตัด <6 หลักทิ้ง + weak-fallback คว้าเศษ float ของยอด
('0000000002') → D2-GUARD ล้างทิ้ง → IV005 "ไม่มีเลขที่ใบกำกับ" false alarm.
กติกาใหม่: gate (ว่าง/ขยะ) + สแกนเลขโดด 4-5 หลักที่มีสัญญาณตำแหน่งเอกสาร (ครึ่งขวา/ติดวันที่).
"""
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser_p2 import _pb_iv_lastresort  # noqa: E402
from core_utils import iv_digits_garbage  # noqa: E402

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


print("[V1] เคส TNT: '01954' (string) ครึ่งขวา + วันที่ใต้เลข → ต้องถูกเลือก")
df = df_of([
    {0: 'บริษัท ดีดัง จำกัด'},
    {0: 'เลขประจำตัวผู้เสียภาษี 0745564003202'},
    {},
    {},
    {},
    {20: '01954'},
    {20: datetime(2569, 1, 2)},
], ncols=23)
res = {'iv_number': '', 'iv_number_raw': ''}
_pb_iv_lastresort(df, res, 0, 20, 23)
check(res['iv_number'] == '01954', f"iv = '01954' — got={res['iv_number']!r}")

print("[V2] เลข 5 หลักโดดมุมซ้าย ไม่มีวันที่ใกล้ (เช่น zip ในที่อยู่แยก cell) → ต้องไม่รับ")
df = df_of([
    {0: 'บริษัท ทดสอบ จำกัด'},
    {0: '11110'},
    {},
], ncols=23)
res = {'iv_number': '', 'iv_number_raw': ''}
_pb_iv_lastresort(df, res, 0, 20, 23)
check(res['iv_number'] == '', f"ไม่จับ zip มุมซ้าย — got={res['iv_number']!r}")

print("[V3] ตัวเลข excel serial (20000..60000 เป็น number) → ต้องไม่รับ (กันวันที่เก็บเป็นเลข)")
df = df_of([
    {20: 45123.0},
    {20: datetime(2569, 1, 2)},
], ncols=23)
res = {'iv_number': '', 'iv_number_raw': ''}
_pb_iv_lastresort(df, res, 0, 20, 23)
check(res['iv_number'] == '', f"ไม่จับ serial 45123 — got={res['iv_number']!r}")

print("[V4] หลาย candidate → คะแนนสูงสุดชนะ (ขวา+ติดวันที่ ชนะ ขวาอย่างเดียว)")
df = df_of([
    {20: '1100'},
    {},
    {},
    {},
    {},
    {20: '01954'},
    {20: datetime(2569, 1, 2)},
], ncols=23)
res = {'iv_number': '', 'iv_number_raw': ''}
_pb_iv_lastresort(df, res, 0, 20, 23)
check(res['iv_number'] == '01954', f"'01954' (ติดวันที่) ชนะ '1100' — got={res['iv_number']!r}")

print("[V5] จำนวนเต็มเก็บเป็น number 4-5 หลัก (นอกช่วง serial) ครึ่งขวา → รับและแปลงเป็น str")
df = df_of([
    {20: 1954.0},
    {20: datetime(2569, 1, 2)},
], ncols=23)
res = {'iv_number': '', 'iv_number_raw': ''}
_pb_iv_lastresort(df, res, 0, 20, 23)
check(res['iv_number'] == '1954', f"number 1954.0 → '1954' — got={res['iv_number']!r}")

print("[V6] gate ขยะ: '0000000002' (เศษ float ยอด) ต้องถูกตีเป็นขยะ / '01954' ต้องไม่ใช่ขยะ")
check(iv_digits_garbage('0000000002') is not None, "'0000000002' = ขยะ (placeholder)")
check(iv_digits_garbage('01954') is None, "'01954' ไม่ใช่ขยะ (รอด D2-GUARD)")

print("[V7] เลข 6 หลักขึ้นไป (เกินขอบเขต fallback) → ไม่รับ (เป็นหน้าที่ตัว extract หลัก)")
df = df_of([
    {20: '123456'},
    {20: datetime(2569, 1, 2)},
], ncols=23)
res = {'iv_number': '', 'iv_number_raw': ''}
_pb_iv_lastresort(df, res, 0, 20, 23)
check(res['iv_number'] == '', f"ไม่จับ 6 หลัก — got={res['iv_number']!r}")

print()
print(f"ผล: ✅ {_PASS} | ❌ {_FAIL}")
sys.exit(0 if _FAIL == 0 else 1)
