# -*- coding: utf-8 -*-
"""test_adr130_seq_overflow.py — [ADR-130] _is_seq_token กัน int(float()) OverflowError
(seq cell ตัวเลขยาวมาก → float→inf → consumer ระเบิด → "บิลทั้งชีตหายเงียบ").

บั๊ก (HIGH, parser): `_is_seq_token` รับ '9'×400 (isdecimal, ไม่มี '.') = True →
consumer `_dic_item_rows` (parser_p0a) + `_pb_extract_items` (parser_p2) ทำ int(float(s))
แบบไม่กัน → OverflowError ที่ _dic_int_run มี try แต่ 2 จุดนี้ไม่มี → detect/extract ครัช
→ บิลทั้งชีตหาย (false-negative). seq จริง 1..50 (corpus หลักสูงสุด=2) → fix byte-identical.

ตรึง: (A) _is_seq_token ไม่ครัช + reject เฉพาะ inf-token ; (B) seq จริงยังรับ (1/50/'1.00') ;
(C) consumer ไม่ครัชบน garbage. golden-neutral (corpus delta=0, พิสูจน์ golden=23b315e8).
รันได้ทุกที่.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parser_p0a as P
import pandas as pd

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== [A] _is_seq_token ไม่ครัช + reject inf-token ===')
    for garbage in ('9' * 400, '1' * 1000, '9' * 309):
        try:
            r = P._is_seq_token(garbage)
            _check(r is False, f'_is_seq_token(len={len(garbage)} digits) = False (ไม่ใช่ seq, ไม่ครัช)')
        except Exception as e:
            _check(False, f'_is_seq_token ครัช: {type(e).__name__}')

    print()
    print('=== [B] seq จริงยังรับเหมือนเดิม (byte-identical) ===')
    for ok in ('1', '50', '7', '1.00', '1.0', '50.0'):
        _check(P._is_seq_token(ok) is True, f'_is_seq_token({ok!r}) = True')
    for no in ('', 'abc', '1.5', '1.01', '๕๕๕๕๕๕๕๕๕๕'.replace('๕', 'x')):
        _check(P._is_seq_token(no) is False, f'_is_seq_token({no!r}) = False')
    # huge-but-finite (≤308 digit) ยังผ่าน predicate (จะถูกตัดด้วย range 1..50 ที่ consumer)
    finite_huge = '1' + '0' * 200
    _check(P._is_seq_token(finite_huge) is True, '_is_seq_token(finite 201-digit) = True (ไม่ใช่ inf)')

    print()
    print('=== [C] consumer ไม่ครัชบน garbage seq cell ===')
    # _dic_item_rows: garbage seq ในคอลัมน์ seq → ต้องไม่ครัช (เดิม int(float) ระเบิด)
    M = pd.DataFrame([['9' * 400, 'สินค้า', 5], ['1', 'ของจริง', 3]]).to_numpy(dtype=object)
    try:
        rows = P._dic_item_rows(M, M.shape[0], 0)
        _check(0 not in rows, '_dic_item_rows ข้าม garbage row (ไม่ครัช)')
        _check(1 in rows, '_dic_item_rows ยังเก็บ seq จริง (row 1)')
    except Exception as e:
        _check(False, f'_dic_item_rows ครัช: {type(e).__name__}: {e}')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — _is_seq_token กัน OverflowError ; seq จริง byte-identical ; consumer ไม่ครัช')
    return 0


if __name__ == '__main__':
    sys.exit(main())
