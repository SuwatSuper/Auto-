# -*- coding: utf-8 -*-
"""test_label_amounts_equiv.py — [OPT-1b] differential guard: _label_based_amounts หลัง optimize
   (normalize ทั้งแถวครั้งเดียว) ต้อง byte-identical กับ implementation เดิม (เรียก _row_label_match 3×/แถว).

ราก: _label_based_amounts เรียก _row_label_match 3 ครั้ง/แถว → recompute normalize_text ซ้ำ ≤3×/เซลล์
  (hot loop 35,661 ครั้ง/~2.5s, PERF_BASELINE:26). optimize = normalize ทั้งแถวครั้งเดียวแล้ว reuse
  กับ 3 label set. normalize_text เป็น total → precompute ให้ผลเท่า short-circuit เดิมทุก path.

oracle = สร้าง _label_based_amounts เวอร์ชันเดิม inline โดยใช้ `_row_label_match` ที่ "ไม่ถูกแตะ"
  (ยังอยู่ในโมดูล) → เทียบ dict ผลลัพธ์บนคลังบล็อกสังเคราะห์ (label/ยอด/อัตรา/เลข 7 vs 7.00/OCR สระหาย).

    PYTHONHASHSEED=0 python3 test_label_amounts_equiv.py
exit 0 = ผ่าน, 1 = พบความต่าง (= optimize เปลี่ยนพฤติกรรม → ห้าม merge)
"""
import os
import sys
import io
import contextlib
import warnings
import random

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import numpy as np
import pandas as pd

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
import parser as P          # noqa: F401  (ผูก A2 reachability)
import parser_p1 as P1

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def _orig_label_based_amounts(df, row_start, row_end, ncols):
    """verbatim ก่อน OPT-1b — ใช้ P1._row_label_match (ไม่ถูกแตะ) เป็น oracle อิสระ."""
    subs = []; vats = []; tots = []
    M = df.to_numpy(dtype=object)
    for r in range(row_start, min(row_end + 1, df.shape[0])):
        if P1._row_label_match(M, r, ncols, P1._LBL_TOTAL):
            n = P1._rightmost_num(M, r, ncols, min_val=0)
            if n is not None: tots.append(n)
            continue
        if P1._row_label_match(M, r, ncols, P1._LBL_VAT):
            n = P1._rightmost_num(M, r, ncols)
            _is_rate7 = (n == 7 and (P1._row_has_rate_marker(M, r, ncols)
                                     or not P1._rightmost_num_has_decimal(M, r, ncols)))
            if n is not None and not (abs(n - 0.07) < 0.001 or _is_rate7):
                vats.append(n)
            continue
        if P1._row_label_match(M, r, ncols, P1._LBL_SUBTOTAL):
            n = P1._rightmost_num(M, r, ncols, min_val=0)
            if n is not None: subs.append(n)
            continue
    return {
        'subtotal': max(subs) if subs else None,
        'vat': vats[-1] if vats else None,
        'total': max(tots) if tots else None,
    }


# label จริงจากโมดูล (เพื่อยิงเส้น match ของจริง)
_T = list(P1._LBL_TOTAL); _V = list(P1._LBL_VAT); _S = list(P1._LBL_SUBTOTAL)
_NUM_FORMS = ['1,234.50', '100', '107', '7', '7.00', '0.07', '50.00', '-5', '1000000',
              '12,345', '0', '99.99', '7.0', ' 250 ', '1.234,56']
_RATE = ['%', 'อัตรา', 'เรต', 'rate', '7%', 'VAT 7%']
_NOISE = ['สินค้า', 'ราคา', 'จำนวน', 'หน่วย', '', None, 'ชื่อบริษัท', 'ที่อยู่', 'เลขที่']


def _rand_row(rng, ncols):
    """สุ่มแถว: label(total/vat/sub)+เลข / rate-row / noise / ว่าง — วางคอลัมน์สุ่ม."""
    row = [None] * ncols
    kind = rng.choice(['total', 'vat', 'vat', 'sub', 'noise', 'noise', 'rate', 'empty'])
    if kind == 'empty':
        return row
    if kind == 'noise':
        for c in range(ncols):
            row[c] = rng.choice(_NOISE)
        return row
    if kind == 'rate':
        lc = rng.randrange(ncols)
        row[lc] = rng.choice(_V) + ' ' + rng.choice(_RATE)
        nc = rng.randrange(ncols)
        row[nc] = rng.choice(['7', '7.00', '7%', '0.07'])
        return row
    labset = {'total': _T, 'vat': _V, 'sub': _S}[kind]
    lc = rng.randrange(ncols)
    lab = rng.choice(labset)
    # บางครั้งเติม noise รอบ label / ทำให้สระหาย (OCR) เพื่อยิงเส้น _strip_thai_marks
    row[lc] = rng.choice(['', 'รวม ', 'ยอด']) + lab
    nc = rng.randrange(ncols)
    row[nc] = rng.choice(_NUM_FORMS)
    # อาจมีเลขหลายคอลัมน์ (ทดสอบ rightmost)
    if rng.random() < 0.4:
        row[rng.randrange(ncols)] = rng.choice(_NUM_FORMS)
    return row


def _rand_block(rng):
    ncols = rng.randint(2, 8)
    nrows = rng.randint(0, 14)
    rows = [_rand_row(rng, ncols) for _ in range(nrows)]
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    return df, ncols


def main():
    print("OPT-1b DIFFERENTIAL — _label_based_amounts ต้อง byte-identical กับโค้ดเดิม")
    rng = random.Random(20260606)
    n = 0; mismatch = 0
    # 1) random blocks
    for _ in range(2500):
        df, ncols = _rand_block(rng)
        if df.shape[1] == 0 or df.shape[0] == 0:
            rs, re_ = 0, 0
        else:
            rs = rng.randrange(df.shape[0])
            re_ = rng.randrange(rs, df.shape[0])
        got = P1._label_based_amounts(df, rs, re_, ncols)
        exp = _orig_label_based_amounts(df, rs, re_, ncols)
        n += 1
        if got != exp:
            mismatch += 1
            if mismatch <= 5:
                print(f"    block#{n} rs={rs} re={re_} ncols={ncols}: got={got} exp={exp}")
    # 2) edge: ว่าง / คอลัมน์เดียว / ช่วงเกินขอบ
    for df, ncols, rs, re_ in [
        (pd.DataFrame(), 0, 0, 0),
        (pd.DataFrame({'a': ['รวมเงิน', 100]}), 1, 0, 1),
        (pd.DataFrame({'a': [None, None]}), 1, 0, 5),
    ]:
        got = P1._label_based_amounts(df, rs, re_, ncols)
        exp = _orig_label_based_amounts(df, rs, re_, ncols)
        n += 1
        if got != exp:
            mismatch += 1
            print(f"    edge: got={got} exp={exp}")

    check(mismatch == 0, f"_label_based_amounts byte-identical ({n} บล็อก, ต่าง={mismatch})")
    print("=" * 70)
    if not FAIL:
        print(f"RESULT: ✅ OPT-1b byte-identical — ผ่าน ({n} บล็อก, 0 ต่าง)")
        return 0
    print(f"RESULT: ❌ ไม่ผ่าน — OPT-1b เปลี่ยนพฤติกรรม (ห้าม merge)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
