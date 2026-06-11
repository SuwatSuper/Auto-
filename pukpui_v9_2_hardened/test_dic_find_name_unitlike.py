# -*- coding: utf-8 -*-
"""test_dic_find_name_unitlike.py — [F3-FIX v9.3] กันคอลัมน์หน่วยชนะการเลือกคอลัมน์ชื่อสินค้า

เคสจริง (SSN 11.06.69): สินค้าชื่อสั้น ('Fan' = 3 ตัว) ไม่ผ่านเกณฑ์ text (len>3) →
คะแนนคอลัมน์ชื่อจริงแพ้คอลัมน์หน่วย ('Pcs.' = 4 ตัว ผ่านทุกแถว) → name_col ชี้คอลัมน์หน่วย
→ ชื่อสินค้า='Pcs.' + หน่วยว่างทั้งบิล. กติกาใหม่: ผู้ชนะที่ "ค่าซ้ำเดียวล้วน" แพ้ให้
คู่แข่งที่ "หลากหลาย + ข้อความยาวกว่า" ; เคสกำกวมทุกแบบคงผลเดิมเป๊ะ (golden ไม่ขยับ).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parser_p0a import _dic_find_name  # noqa: E402

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


def M_of(rows):
    return np.array(rows, dtype=object)


# โครง: col0=seq, col1=ชื่อ, col2=หน่วย (จำลองย่อจาก SSN ชีต '9')
print("[N1] เคส SSN: ชื่อสั้น 'Fan' ทำคอลัมน์ชื่อแพ้คอลัมน์หน่วย → กติกาใหม่ต้องเลือกคอลัมน์ชื่อ")
M = M_of([
    [1, "Tube",              "Pcs."],
    [2, "Fan",               "Pcs."],
    [3, "หลอด 280",          "Pcs."],
    [4, "Avolites Quartz",   "Pcs."],
    [5, "Moving Tourist M7", "Pcs."],
])
got = _dic_find_name(M, 3, 0, [0, 1, 2, 3, 4])
check(got == 1, f"name_col = 1 (คอลัมน์ชื่อจริง) — got={got}")

print("[N2] เคสปกติ (ชื่อยาวพอทุกแถว) → ผลเดิม: คอลัมน์ชื่อชนะตามคะแนน")
M = M_of([
    [1, "Dongle capture",  "Pcs."],
    [2, "Cable 1to2",      "Pcs."],
    [3, "Cable Power Con", "Pcs."],
    [4, "Storm 1500",      "Pcs."],
])
got = _dic_find_name(M, 3, 0, [0, 1, 2, 3])
check(got == 1, f"name_col = 1 (พฤติกรรมเดิม) — got={got}")

print("[N3] เคสอันตราย: ชื่อซ้ำเดียวล้วน + หน่วยหลากหลาย 'แต่ข้อความสั้นกว่า' → ต้องคงผลเดิม (คอลัมน์ชื่อ)")
M = M_of([
    [1, "ปูนฉาบสำเร็จ", "ถุงใหญ่"],
    [2, "ปูนฉาบสำเร็จ", "กล่อง"],
    [3, "ปูนฉาบสำเร็จ", "ลังไม้"],
    [4, "ปูนฉาบสำเร็จ", "ถุงเล็ก"],
])
# คอลัมน์ชื่อ: cnt=4, tlen=4*11=44 (ซ้ำเดียวล้วน) | หน่วย: cnt=4 distinct=4 tlen=22 < 44 → ห้ามสลับ
got = _dic_find_name(M, 3, 0, [0, 1, 2, 3])
check(got == 1, f"name_col = 1 (ไม่สลับเมื่อคู่แข่ง tlen น้อยกว่า) — got={got}")

print("[N4] มีคอลัมน์เดียวผ่านเกณฑ์ (เป็นค่าซ้ำเดียวล้วน) → ไม่มีคู่แข่ง → คงผลเดิม")
M = M_of([
    [1, "Pcs.", None],
    [2, "Pcs.", None],
    [3, "Pcs.", None],
])
got = _dic_find_name(M, 3, 0, [0, 1, 2])
check(got == 1, f"name_col = 1 (พฤติกรรมเดิม ไม่มีตัวเลือกอื่น) — got={got}")

print("[N5] ไม่มีคอลัมน์ข้อความเลย → None (เดิม)")
M = M_of([
    [1, 10, 99.0],
    [2, 20, 88.0],
])
got = _dic_find_name(M, 3, 0, [0, 1])
check(got is None, f"name_col = None — got={got}")

print("[N6] เสมอกันหลายคอลัมน์ (ไม่มีค่าซ้ำเดียวล้วน) → ตัวซ้ายสุดตามกติกาเดิม")
M = M_of([
    [1, "เหล็กฉาก มอก.", "เหล็กกล่อง A"],
    [2, "เหล็กแบน 2นิ้ว", "เหล็กกล่อง B"],
])
got = _dic_find_name(M, 3, 0, [0, 1])
check(got == 1, f"เสมอ → ซ้ายสุด (เดิม) — got={got}")

print()
print(f"ผล: ✅ {_PASS} | ❌ {_FAIL}")
sys.exit(0 if _FAIL == 0 else 1)
