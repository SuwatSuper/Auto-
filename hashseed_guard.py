# -*- coding: utf-8 -*-
"""hashseed_guard.py — บังคับ PYTHONHASHSEED=0 บน entry production (re-exec ครั้งเดียว)

ทำไม (P2-FIX):
  ผลตรวจบางส่วน (เช่น suggestion การสะกด ITM011/ITM012 ผ่าน find_similar_in_thai_dict)
  สร้าง candidate จากการวนชุด (set) → ลำดับขึ้นกับ hash seed → ตอนคะแนนเสมอกัน rapidfuzz
  อาจเลือกคนละคำตามค่า seed. golden ถูกสร้างใต้ PYTHONHASHSEED=0 (CI/VS Code ตั้งให้).
  แต่เส้น production ที่รันนอก VS Code (เช่น `python3 main.py` ในเทอร์มินัลเปล่า) ไม่ได้ตั้ง →
  ผลอาจ "ไม่ตรง golden" เงียบ ๆ. โมดูลนี้บังคับให้ entry production วิ่งใต้เงื่อนไขเดียวกับ golden.

ใช้ (เรียกให้เร็วที่สุด ก่อน import โมดูลหลัก/ก่อนคำนวณใด ๆ):
    if __name__ == "__main__":
        from hashseed_guard import enforce_hashseed
        enforce_hashseed()

stdlib-only โดยเจตนา (import ได้ก่อนทุกอย่าง ไม่ดึง dependency หนัก).
"""
import os
import sys


def enforce_hashseed() -> None:
    """ถ้า hash randomization เปิดอยู่ และยังไม่ได้ตั้ง PYTHONHASHSEED=0 → re-exec โปรเซสด้วย seed 0.

    - no-op ถ้า seed=0 อยู่แล้ว (VS Code/CI/เครื่องมือ golden ตั้งให้) → ไม่มี overhead.
    - re-exec ครั้งเดียว: PYTHONHASHSEED=0 ปิด hash randomization → รอบสองเงื่อนไขเป็นเท็จ ไม่วน.
    - คง sys.argv เดิมครบ (อาร์กิวเมนต์/อินเทอร์แอกทีฟไม่หาย).
    """
    if sys.flags.hash_randomization and os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, *sys.argv])
