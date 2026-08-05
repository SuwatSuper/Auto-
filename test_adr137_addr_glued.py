# -*- coding: utf-8 -*-
"""test_adr137_addr_glued.py — [ADR-137] _pb_try_address_line รับ "เลขที่123"/"หมู่ที่4" แบบ glued.

บั๊ก (sibling ADR-125): branch-1 ใช้ `เลขที่ \\d+` (space เดียวบังคับ) → บรรทัด "เลขที่123 ถนน..."
(label ติดเลข ไม่เว้นวรรค) ตกทุก branch → ทิ้งทั้งบรรทัด → บ้านเลขที่หาย → ADDR001 ฟ้อง "ไม่พบเลขที่".
แก้: `เลขที่\\s*\\d+`/`หมู่ที่\\s*\\d+` (superset — space เดียวยัง match). golden-neutral (corpus delta=0).

ตรึง: (A) glued ถูกเก็บ ; (B) รูปเว้นวรรคเดิม byte-identical ; (C) ไม่เก็บบรรทัดที่ไม่ใช่ที่อยู่. รันได้ทุกที่.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parser_p1 import _pb_try_address_line

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def _collect(s):
    lines = []
    _pb_try_address_line(lines, s)
    return lines


def main():
    print('=== [A] glued "เลขที่123"/"หมู่ที่4" ถูกเก็บ (เดิมถูกทิ้ง) ===')
    _check(_collect('เลขที่123 ถนนสุขุมวิท') == ['เลขที่123 ถนนสุขุมวิท'],
           "'เลขที่123 ถนนสุขุมวิท' ถูกเก็บ")
    _check(_collect('หมู่ที่4 ตำบลบางพลี') == ['หมู่ที่4 ตำบลบางพลี'],
           "'หมู่ที่4 ตำบลบางพลี' ถูกเก็บ (มี ตำบล อยู่แล้วด้วย)")

    print('=== [B] รูปเว้นวรรคเดิม byte-identical ===')
    _check(_collect('เลขที่ 123 ถนนสุขุมวิท') == ['เลขที่ 123 ถนนสุขุมวิท'],
           "'เลขที่ 123 ...' (space เดียว) ยังเก็บ (เดิม)")
    _check(_collect('หมู่ที่ 4 ตำบลบางพลี') == ['หมู่ที่ 4 ตำบลบางพลี'],
           "'หมู่ที่ 4 ...' ยังเก็บ (เดิม)")
    _check(_collect('แขวงคลองเตย เขตคลองเตย') == ['แขวงคลองเตย เขตคลองเตย'],
           "บรรทัด แขวง/เขต ยังเก็บ (เดิม)")

    print('=== [C] บรรทัดที่ไม่ใช่ที่อยู่ — ไม่เก็บ ===')
    _check(_collect('บริษัท ทดสอบ จำกัด') == [], "ชื่อบริษัทไม่ถูกเก็บ")
    _check(_collect('สีทาถนน TOA 3ลิตร') == [], "บรรทัดสินค้า (ไม่มี anchor) ไม่ถูกเก็บ")
    _check(_collect('เลขที่บัญชี ธนาคาร') == [], "'เลขที่บัญชี' (ไม่มีเลขตาม) ไม่ถูกเก็บ")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — glued เลขที่/หมู่ที่ ถูกเก็บ ; รูปเดิม byte-identical ; non-addr ไม่เก็บ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
