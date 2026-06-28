# -*- coding: utf-8 -*-
"""test_itm001_lumpsum.py — ล็อก ADR-107/P4: กัน ITM001 ฟ้องปลอม "V×V≠V" บนใบเหมารวม/บริการ.

อาการที่เจ้าของรายงาน: รายการ ITM001 ขึ้นยาวเป็นพรืด ทุกบรรทัด `V×V=V² แต่=V`
  คือ qty=price=amount=ค่าเดียวกัน — เป็นไปไม่ได้จริง (amount=amount² ได้เฉพาะ amount≤1).
ต้นเหตุ: parser `_dic_pick_qty_price` เดาคอลัมน์ qty/price เสมอแม้ qty×price ไม่ validate
  → คว้าคอลัมน์ที่ค่า=ยอด (ราคา/หน่วย==ยอด เพราะ qty=1) มาเป็นทั้ง qty และ price.

ตรึงสองชั้น:
  (A) parser: ถ้าไม่มีคู่ qty/price validate แม้แต่แถวเดียว → คืน (None,None) ไม่เดา.
  (B) rule:   r_itm001 ข้ามรายการ qty==price==amount (defense-in-depth).

golden-safe: corpus แตะ fallback = 0 ครั้ง และมีรายการ qty==price==amount = 0 → golden ไม่ขยับ.
"""
import sys
import numpy as np
import parser_p0a as P

_fail = []


def _check(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        _fail.append(msg)


def main():
    print("=== [A] parser _dic_pick_qty_price: ใบเหมารวม → ไม่เดาคอลัมน์ ===")
    # 2 คอลัมน์ตัวเลข ค่าเท่ายอดทั้งคู่ (ราคา/หน่วย==ยอด, qty=1) — ไม่มีคู่ใด qty×price≈amount
    M = np.array([
        [1, 'ค่าบริการ A', 70560.75, 70560.75],
        [2, 'ค่าบริการ B', 22897.20, 22897.20],
        [3, 'ค่าบริการ C', 24205.61, 24205.61],
    ], dtype=object)
    nums = [(2, [70560.75, 22897.20, 24205.61]), (3, [70560.75, 22897.20, 24205.61])]
    q, p = P._dic_pick_qty_price(M, [0, 1, 2], 3, nums)
    _check(q is None and p is None,
           "ใบที่ qty×price validate ไม่ผ่านเลย → (None,None) ไม่เดา (กัน qty=price=amount)")

    print("\n=== [B] parser: ใบปกติ (qty×price==amount) ยังเลือก qty/price ถูก ===")
    M2 = np.array([
        [1, 'เหล็ก', 2, 35280.0, 70560.0],
        [2, 'ท่อ',   5, 4579.44, 22897.2],
        [3, 'แผ่น',  3, 8068.54, 24205.62],
    ], dtype=object)
    nums2 = [(2, [2, 5, 3]), (3, [35280.0, 4579.44, 8068.54]), (4, [70560.0, 22897.2, 24205.62])]
    q2, p2 = P._dic_pick_qty_price(M2, [0, 1, 2], 4, nums2)
    _check(q2 == 2 and p2 == 3, "ใบที่ validate ได้ → เลือก qty_col/price_col จริง (ไม่ regress)")

    print("\n=== [C] r_itm001: ข้ามรายการ qty==price==amount (artifact) ===")
    import rules_engine as RE
    r_itm001 = RE.RULES['ITM001']['check']
    bill_art = {'items': [
        {'seq': 1, 'name': 'ค่าบริการ', 'qty': 70560.75, 'price': 70560.75, 'amount': 70560.75},
    ]}
    out = r_itm001(bill_art, None, None)
    _check(out == [], "qty==price==amount → ITM001 ไม่ฟ้อง (เป็น artifact ไม่ใช่ error)")

    print("\n=== [D] r_itm001: ยังจับ qty×price≠amount จริง (ไม่ over-suppress) ===")
    bill_real = {'items': [
        {'seq': 1, 'name': 'เหล็ก', 'qty': 2, 'price': 100.0, 'amount': 999.0},   # 2×100=200≠999
    ]}
    out2 = r_itm001(bill_real, None, None)
    _check(any('แต่=999' in m for m in out2), "qty×price≠amount จริง → ยังฟ้องตามเดิม")

    print()
    if _fail:
        print(f"RESULT: ❌ FAIL — {len(_fail)} เคส")
        sys.exit(1)
    print("RESULT: ✅ PASS — ITM001 ไม่ฟ้องปลอม V×V (ADR-107) + ไม่ regress การจับจริง")


if __name__ == "__main__":
    main()
