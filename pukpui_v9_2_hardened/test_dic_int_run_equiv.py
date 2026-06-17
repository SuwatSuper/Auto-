# -*- coding: utf-8 -*-
"""test_dic_int_run_equiv.py — [OPT-1] differential guard: _dic_int_run / detect_item_columns
   หลัง optimize (อ่าน M = df.to_numpy(dtype=object)) ต้อง byte-identical กับ implementation เดิม
   (df.iloc[:,c].dropna()) ทุก path.

ราก (OPT-1, HANDOFF): _dic_find_seq เรียก _dic_int_run ต่อคอลัมน์ด้วย df.iloc[:,c].dropna()
  → hot loop 16,553 ครั้ง/106 ไฟล์ (~3.9s, PERF_BASELINE). optimize = materialize M ครั้งเดียว
  ใน detect_item_columns แล้วอ่าน M[:,c] (M[r,c] ≡ df.iat[r,c], พิสูจน์ 836 ชีต/555k cell).

เทสนี้คือ "ตาข่าย byte-identical" ที่รันได้ "โดยไม่ต้องมี 106 ไฟล์จริง": เก็บ implementation
เดิมไว้ inline (_orig_*) แล้วเทียบกับของจริงในโมดูล (P.*) บนคลังอินพุตทรหด — รวมเคสที่ข้อมูลจริง
แทบไม่โผล่ (วันที่/บูลีน/วิทยาศาสตร์/เลขไทย/comma/None/NaT/ทศนิยมยาว/ค่าใกล้จำนวนเต็ม). ผ่านเมื่อ
0 ต่าง ทุกคอลัมน์ + ทุก detect_item_columns 6-tuple. (เมื่อเจ้าของรันบน 106 ไฟล์ → ยังเป็น guard)

    PYTHONHASHSEED=0 python3 test_dic_int_run_equiv.py
exit 0 = ผ่าน, 1 = พบความต่าง (= optimize เปลี่ยนพฤติกรรม → ห้าม merge)
"""
import os
import sys
import io
import contextlib
import warnings
import random
from datetime import datetime

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
import parser as P

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def _capture(fn, *args):
    """รันแล้วคืน ('ok', result) หรือ ('err', ExcTypeName) — เทียบ "พฤติกรรมเหมือนกัน"
       รวมถึงกรณี raise. (หมายเหตุ v9.3.1: 'inf'/'1e400' เคยทำ OverflowError ทั้งสองเส้น
       — ตอนนี้ except ครอบ OverflowError แล้ว → ทั้งคู่คืน [] เหมือนกัน). optimize ต้องโปร่งใสทุกเส้น."""
    try:
        return ('ok', fn(*args))
    except Exception as e:
        return ('err', type(e).__name__)


# ─────────────────────────────────────────────────────────────────────────────
# implementation เดิม (verbatim ก่อน OPT-1) — oracle อิสระจากโค้ดที่กำลังทดสอบ
# ─────────────────────────────────────────────────────────────────────────────
def _orig_dic_int_run(df, c):
    """โค้ดเดิม: df.iloc[:,c].dropna() + int(float(str(v))) + ช่วง 1..50.
    [BUGHUNT v9.3.1] except ครอบ OverflowError ด้วย (ตรงกับ fix ใน parser_p0a) — ทั้งเส้น
    OPT-1 (M-based) และเส้นอ้างอิงนี้ต้องกัน 'inf'/'1e400' เหมือนกัน (differential ยังคง byte-identical)."""
    ints = []
    for v in df.iloc[:, c].dropna():
        try:
            n = int(float(str(v)))
        except (ValueError, TypeError, OverflowError):
            continue
        if 1 <= n <= 50:
            ints.append(n)
    return ints


def _orig_dic_find_seq(df, ncols):
    """โค้ดเดิม: เรียก _orig_dic_int_run ต่อคอลัมน์ (scoring เดิม ผ่าน P._is_seq_run ที่ไม่แตะ)."""
    seq_col, best = None, 0
    for c in range(ncols):
        ints = _orig_dic_int_run(df, c)
        if P._is_seq_run(ints):
            score = len(ints) * 10 - c
            if score > best:
                best = score
                seq_col = c
    return seq_col


def _orig_detect_item_columns(df):
    """โค้ดเดิม: seq-detect บน df, materialize M หลัง early-return, ที่เหลือใช้ helper M-based เดิม
       (helper เหล่านี้ไม่ถูกแตะใน OPT-1 → เรียกของจริงได้ตรง ๆ เพื่อโฟกัสความต่างที่ seq-detect)."""
    nrows, ncols = df.shape
    seq_col = _orig_dic_find_seq(df, ncols)
    if seq_col is None:
        return (None,) * 6
    M = df.to_numpy(dtype=object)
    item_rows = P._dic_item_rows(M, nrows, seq_col)
    if not item_rows:
        return seq_col, None, None, None, None, None
    name_col = P._dic_find_name(M, ncols, seq_col, item_rows)
    amt_col = P._dic_find_amt(M, ncols, seq_col, item_rows)
    qty_col = price_col = unit_col = None
    if name_col is not None and amt_col is not None and amt_col > name_col + 1:
        nums_c, text_c = P._dic_collect_numeric(M, item_rows, name_col, amt_col)
        qty_col, price_col = P._dic_pick_qty_price(M, item_rows, amt_col, nums_c)
        if qty_col is not None:
            unit_col = P._dic_pick_unit(text_c, qty_col, price_col, name_col)
    return seq_col, name_col, qty_col, unit_col, price_col, amt_col


# ─────────────────────────────────────────────────────────────────────────────
# คลังอินพุตทรหด
# ─────────────────────────────────────────────────────────────────────────────
def _torture_columns():
    """ลิสต์คอลัมน์ (list ของ list-ค่า) ที่อัดเคสยาก — แต่ละอันยาวเท่ากัน (7)."""
    NaN = float('nan')
    return [
        [1, 2, 3, 4, 5, 6, 7],                                  # int ล้วน
        [1, 2, 3, 4, 5, NaN, 7],                                # มี NaN → float64
        [9, 10, 11, 12, 13, 14, 15],                            # หน้าต่อ (เริ่ม 9)
        [1.0, 2.9, 49.999999, 50.0, 51.0, 0.5, NaN],            # float ขอบช่วง
        ['1', '2', '3', 'x', '5.0', ' 7 ', ''],                 # string ปนตัวอักษร/ช่องว่าง/ว่าง
        [1, '2', 3.0, None, 'abc', NaN, '5,000'],               # object ผสม + comma
        [True, False, True, False, True, False, True],          # บูลีน → ต้องได้ []
        [100, 1e20, -3, 0, 25, 999, NaN],                       # ใหญ่/วิทยาศาสตร์/ลบ/ศูนย์
        ['๑', '5', 'สาม', None, '12', '49', '50'],              # เลขไทย (จับไม่ได้) + อารบิก
        [1, 1, 1, 1, 1, 1, 1],                                  # qty คงที่ (ไม่ span)
        [20, 10, 10, 1, 5, 3, 2],                               # qty/ราคา (ไม่ non-decreasing)
        [datetime(2026, 6, 6), datetime(2025, 1, 1), 3, 4, 5, 6, 7],   # วันที่ (str→ValueError→skip)
        [pd.NaT, pd.NaT, 1, 2, 3, 4, 5],                        # NaT → dropna/isna ต้องตรงกัน
        ['1.05', '2.0', '15', '1.9', '49.9', '50.1', '0.9'],    # ทศนิยม-ใกล้ขอบ (truncation)
        [2.9999999999999996, 3.0000000000000004, 48.5, 49.5, 50.5, 1.4999, NaN],  # ปัดเศษ binary
        ['', '', '', '', '', '', ''],                           # ว่างล้วน
        [NaN, NaN, NaN, NaN, NaN, NaN, NaN],                    # NaN ล้วน
        ['  3  ', '\t4\n', ' 5 ', '6', '7', '8', '9'],          # whitespace หลากแบบ
        ['1,234', '12', '-5', '+7', '07', '008', '13'],         # comma/เครื่องหมาย/นำศูนย์
        [51, 52, 100, 0, -1, 999, 1000],                        # นอกช่วง 1..50 ทั้งหมดยกเว้น?
        ['nan', 'inf', '-inf', '3', '4', 'NaN', '5'],           # คำพิเศษที่ float() รับ (inf/nan)
    ]


def _random_invoice_df(rng):
    """สร้าง DataFrame คล้ายชีตบิลจริง: seq + name + qty + price + amount + คอลัมน์ขยะ
       เรียงสุ่ม + แถว header noise + แถวว่าง — เพื่อยิง _dic_find_seq/detect ครบ branch."""
    n_items = rng.randint(0, 18)
    seq_start = rng.choice([1, 1, 1, 5, 9, 12])              # หน้าแรก/หน้าต่อ
    seqs = list(range(seq_start, seq_start + n_items))
    if n_items >= 3 and rng.random() < 0.3:
        # ใส่ซ้ำ/gap เล็กน้อย (ทน real data)
        i = rng.randrange(len(seqs))
        seqs[i] = seqs[max(0, i - 1)]
    cols = {}
    cols['seq'] = seqs
    cols['name'] = [rng.choice(['สินค้า', 'แผ่นเหล็ก', 'ท่อ PVC', 'บริการ', 'ค่าขนส่ง']) +
                    str(rng.randint(1, 999)) for _ in range(n_items)]
    cols['qty'] = [rng.randint(1, 40) for _ in range(n_items)]
    cols['price'] = [round(rng.uniform(1, 5000), 2) for _ in range(n_items)]
    cols['amount'] = [round(cols['qty'][i] * cols['price'][i], 2) for i in range(n_items)]
    # คอลัมน์ขยะ
    for j in range(rng.randint(0, 3)):
        kind = rng.choice(['empty', 'text', 'num', 'mixed'])
        if kind == 'empty':
            cols[f'z{j}'] = [None] * n_items
        elif kind == 'text':
            cols[f'z{j}'] = [rng.choice(['ชิ้น', 'กล่อง', 'EA', '']) for _ in range(n_items)]
        elif kind == 'num':
            cols[f'z{j}'] = [rng.choice([rng.randint(1, 100), float('nan'), 0]) for _ in range(n_items)]
        else:
            cols[f'z{j}'] = [rng.choice([rng.randint(1, 60), 'x', None, str(rng.randint(1, 50))])
                             for _ in range(n_items)]
    items = list(cols.keys())
    rng.shuffle(items)
    body = pd.DataFrame({k: cols[k] for k in items})
    # header noise rows (string) + แถวว่างบน/ล่าง
    n_head = rng.randint(0, 3)
    header_rows = []
    for _ in range(n_head):
        header_rows.append({k: rng.choice(['บริษัท', 'ใบกำกับภาษี', 'ลำดับ', None, '']) for k in items})
    head = pd.DataFrame(header_rows) if header_rows else pd.DataFrame(columns=items)
    df = pd.concat([head, body], ignore_index=True)
    return df


def _edge_frames():
    """DataFrame ขอบ: ว่าง/0คอลัมน์/เซลล์เดียว/คอลัมน์เดียว."""
    return [
        pd.DataFrame(),                                  # 0x0
        pd.DataFrame({'a': []}),                         # 1 col, 0 row
        pd.DataFrame({'a': [1]}),                        # 1 cell
        pd.DataFrame({'a': [1, 2, 3]}),                  # seq-only
        pd.DataFrame(index=range(5)),                    # 0 col, 5 row
        pd.DataFrame({'a': [None, None], 'b': [None, None]}),  # all null
    ]


def main():
    print("OPT-1 DIFFERENTIAL — _dic_int_run / detect_item_columns ต้อง byte-identical กับโค้ดเดิม")

    frames = []
    # 1) คอลัมน์ทรหด — ประกอบเป็น df หลายคอลัมน์ + เดี่ยว
    tcols = _torture_columns()
    frames.append(pd.DataFrame({f'c{i}': col for i, col in enumerate(tcols)}))
    for i, col in enumerate(tcols):
        frames.append(pd.DataFrame({f'c{i}': col}))
    # 2) random invoice-like (เมล็ดคงที่ → reproducible)
    rng = random.Random(20260606)
    for _ in range(1500):
        frames.append(_random_invoice_df(rng))
    # 3) edge
    frames.extend(_edge_frames())

    n_col_checks = 0
    n_detect_checks = 0
    col_mismatch = 0
    detect_mismatch = 0

    for fi, df in enumerate(frames):
        ncols = df.shape[1]
        # per-column: _dic_int_run(M,c) == _orig_dic_int_run(df,c)
        if ncols and df.shape[0]:
            M = df.to_numpy(dtype=object)
            for c in range(ncols):
                got = _capture(P._dic_int_run, M, c)
                exp = _capture(_orig_dic_int_run, df, c)
                n_col_checks += 1
                if got != exp:
                    col_mismatch += 1
                    if col_mismatch <= 5:
                        print(f"    [col] frame#{fi} col{c}: got={got} exp={exp}")
        # end-to-end: detect_item_columns(df) == _orig_detect_item_columns(df) (รวมเส้น exception)
        got_t = _capture(P.detect_item_columns, df)
        exp_t = _capture(_orig_detect_item_columns, df)
        n_detect_checks += 1
        if got_t != exp_t:
            detect_mismatch += 1
            if detect_mismatch <= 5:
                print(f"    [detect] frame#{fi}: got={got_t} exp={exp_t}")

    check(col_mismatch == 0, f"_dic_int_run byte-identical ({n_col_checks} คอลัมน์, ต่าง={col_mismatch})")
    check(detect_mismatch == 0,
          f"detect_item_columns 6-tuple byte-identical ({n_detect_checks} เฟรม, ต่าง={detect_mismatch})")

    print("=" * 70)
    print(f"checks: per-column={n_col_checks}  detect={n_detect_checks}")
    if not FAIL:
        print(f"RESULT: ✅ OPT-1 byte-identical — ผ่าน {PASS} กลุ่ม "
              f"({n_col_checks} คอลัมน์ + {n_detect_checks} เฟรม, 0 ต่าง)")
        return 0
    print(f"RESULT: ❌ ไม่ผ่าน {len(FAIL)} กลุ่ม — OPT-1 เปลี่ยนพฤติกรรม (ห้าม merge)")
    for f in FAIL:
        print(f"   - {f}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
