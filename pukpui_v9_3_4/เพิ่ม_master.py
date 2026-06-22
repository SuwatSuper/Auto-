# -*- coding: utf-8 -*-
"""เพิ่ม_master.py — ใส่/แก้ Master (ภ.พ.20) ครั้งเดียว แล้วบันทึกลง master_companies.json

[v9.2 งาน A] เดิมโหมด AUTO สร้าง "stub บริษัททดสอบ" ทับ master_companies.json ทำให้ผู้ใช้
ใส่ master จริงไม่ได้ และรายงานขึ้น "ตรง" หลอกในช่องชื่อบจ./เลขภาษี. สคริปต์นี้คืนช่องใส่
master ให้ผู้ใช้: รันครั้งเดียวเพื่อกรอกข้อมูลบริษัทอ้างอิง (วางข้อความ ภ.พ.20 ได้) จากนั้น
"กด Run ระบบหลัก" จะหยิบ master_companies.json ไปใช้ตรวจ "ชื่อบจ./เลขภาษี" ให้อัตโนมัติตลอด.

ใช้ฟังก์ชันเดิมใน master.py (input_master_data + save_master) — ไม่แตะ engine/golden hash.

วิธีรัน:
    python3 เพิ่ม_master.py
    หรือเมนู Run ใน VS Code: "➕ ใส่ Master (master_companies.json)"

หมายเหตุ: สคริปต์นี้เป็นแบบโต้ตอบ (ถามทีละช่อง / วางข้อความได้) — ต้องรันในเทอร์มินัลจริง.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
os.chdir(_HERE)  # ให้ master_companies.json เขียนข้าง ๆ สคริปต์/ระบบหลักเสมอ

from master import input_master_data, save_master, load_master  # noqa: E402


def main() -> int:
    print("=" * 70)
    print("➕ ใส่ Master (ภ.พ.20)  →  master_companies.json")
    print("=" * 70)
    print("• วางข้อความ ภ.พ.20 ทั้งก้อนได้ (ก๊อปจากเว็บ/PDF) — ระบบจะแยกช่องให้")
    print("• บรรทัดว่าง = จบการกรอกบริษัทนั้น;  จบทั้งหมด = บรรทัดว่างตอนเริ่มบริษัทใหม่")
    print("-" * 70)

    master = input_master_data()   # โต้ตอบ + validate + กัน key ซ้ำ (logic เดิมใน master.py)
    if not master:
        print("\n❌ ไม่ได้ใส่บริษัทใดเลย — ไม่บันทึก (master_companies.json คงเดิม)")
        return 1

    save_master(master)            # เขียน master_companies.json (json indent=2)
    cur = load_master() or {}
    print("\n" + "=" * 70)
    print(f"✅ บันทึก master แล้ว: {len(cur)} บริษัท")
    for k in cur:
        print(f"   • {k}")
    print("=" * 70)
    print("ทีนี้ 'กด Run ระบบหลัก' จะใช้ master นี้ตรวจชื่อบจ./เลขภาษีให้อัตโนมัติ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
