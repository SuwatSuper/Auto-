# -*- coding: utf-8 -*-
"""test_adr143_thai_zip.py — [ADR-143/TN-02] เลขไทยในรหัสไปรษณีย์ ไม่ทำ ADDR006/007 FP.

บั๊ก (FP/normalization): `_ZIP_RE = r'(?<!\\d)(\\d{5})(?!\\d)'` — `\\d` ของ Python เป็น Unicode จับเลขไทย
'๘๓๐๐๐' ได้ แต่ `z[:2] in valid_pref` เทียบ '๘๓' กับ '83' (ASCII) ไม่ตรง → postal_province_mismatch
(ADDR006) / district_postal_mismatch (ADDR007) ฟ้อง "รหัส↔จังหวัดขัด" บนรหัส "ถูกแต่เขียนเลขไทย" = FP.
แก้: translate เลขไทย→อารบิก ก่อนจับรหัส (แนว ADR-114 full-width). corpus = อารบิกล้วน → no-op → golden-neutral.
รันได้ทุกที่.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thai_postal as TP

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== รหัสไปรษณีย์ถูก เขียนเลขไทย → ไม่ FP (เท่ากับเขียนอารบิก) ===')
    thai = 'เลขที่ 1 ตำบลตลาดใหญ่ อำเภอเมือง จังหวัดภูเก็ต ๘๓๐๐๐'
    ascii_ = 'เลขที่ 1 ตำบลตลาดใหญ่ อำเภอเมือง จังหวัดภูเก็ต 83000'
    _check(TP.postal_province_mismatch(thai) is None,
           "ภูเก็ต ๘๓๐๐๐ (เลขไทยถูก) → None (FP หาย)")
    _check(TP.postal_province_mismatch(thai) == TP.postal_province_mismatch(ascii_),
           "ผลเลขไทย == ผลอารบิก (สอดคล้อง)")
    _check(TP.district_postal_mismatch(thai) == TP.district_postal_mismatch(ascii_),
           "ADDR007 เลขไทย == อารบิก")

    print('=== รหัสผิดจริง (เขียนเลขไทย) → ยังฟ้อง mismatch (ไม่กลบ true-positive) ===')
    bad = 'เลขที่ 1 จังหวัดภูเก็ต ๑๐๑๑๐'   # 10110 = กทม ผิดสำหรับภูเก็ต
    res = TP.postal_province_mismatch(bad)
    _check(res is not None and res[0] == 'ภูเก็ต', "ภูเก็ต ๑๐๑๑๐ (ผิดจริง) → ยังฟ้อง mismatch")
    _check(res is not None and res[1] == '10110', "รายงานรหัสเป็นอารบิก '10110' (อ่านง่าย)")

    print('=== อารบิกล้วน (corpus-like) byte-identical ===')
    _check(TP.postal_province_mismatch(ascii_) is None, "อารบิกถูก → None (เดิม)")
    bad_ascii = 'เลขที่ 1 จังหวัดภูเก็ต 10110'
    _check(TP.postal_province_mismatch(bad_ascii) == TP.postal_province_mismatch(bad),
           "อารบิกผิด == เลขไทยผิด (สอดคล้อง)")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — เลขไทยในรหัสไปรษณีย์ไม่ FP ; รหัสผิดยังฟ้อง ; อารบิก byte-identical')
    return 0


if __name__ == '__main__':
    sys.exit(main())
