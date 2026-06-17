# -*- coding: utf-8 -*-
"""parser_reexport.py — [OPT-2 ก] ตัวช่วย auto re-export สำหรับ split-base chain ของ parser
   (parser_p0a → parser_p0 → parser_p1 → parser_p2).

ราก (B2/[F3], HANDOFF): เดิมแต่ละชั้นทำ `from <upstream> import (A, B, C, ...)` แบบ "ลิสต์มือ"
  ~57–95 ชื่อ/ชั้น. เพิ่ม/ลบ/ย้าย 1 สัญลักษณ์ต้นน้ำ → ต้องไล่แก้ลิสต์ปลายน้ำทุกชั้น มิฉะนั้น
  ImportError ทั้ง chain (blast radius สูง = รากงอกบั๊ก).

วิธี (zero-star, byte-identical): ดึง "ทุกชื่อใน upstream.__all__" (ยกเว้น exclude ที่ปลายน้ำ
  จัดการเอง) เข้าสู่ namespace ปลายน้ำ โดย **bind object เดิม** (`getattr`) — ไม่ใช่ `import *`
  (กันรากปัญหา surface-leak เดิม เช่น 'annotations' รั่ว — DECISIONS §). โค้ดที่ถูกรันคือ object
  เดิมทุกตัว → golden hash ไม่ขยับ. blast radius ของ chain ภายในลดเหลือ ~0 (ต้นน้ำเพิ่มชื่อ →
  ปลายน้ำเห็นเอง). ตรึงความครบถ้วน+identity ด้วย test_parser_chain_integrity.py.

หมายเหตุ: parser.py (ชั้นบนสุด = public API) **ยังคง explicit __all__ โดยเจตนา** — เป็น contract
  ที่ต้อง curate ด้วยมือ (ไม่ใช่ debt). helper นี้ใช้กับ "edge ภายใน" เท่านั้น.
"""
from __future__ import annotations


def reexport(upstream, target_globals, exclude=()):
    """คัดทุกชื่อใน ``upstream.__all__`` (ยกเว้น ``exclude``) เข้าสู่ ``target_globals``
    ด้วย binding เดิม (object เดียวกับ upstream).

    คืน list ของชื่อที่ re-export (ไว้ debug/ตรวจ). ออกแบบให้ deterministic:
    เรียงตามลำดับใน ``upstream.__all__`` เป๊ะ.
    """
    ex = set(exclude)
    names = [n for n in getattr(upstream, "__all__", ()) if n not in ex]
    for n in names:
        target_globals[n] = getattr(upstream, n)
    return names
