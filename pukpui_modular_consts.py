# -*- coding: utf-8 -*-
"""pukpui_modular_consts — [SPLIT #3 slice-3] (no-op หลัง [L3])

เดิมไฟล์นี้ทำ `.update()` ขยาย CONSTRUCTION_DICT แบบ side-effect — แต่จะทำงาน "ก็ต่อเมื่อ"
ถูก import ผ่าน pukpui_modular_base เท่านั้น → โค้ดที่ import config/webverify/thai_text/rules_engine
ตรง ๆ (เทส/เครื่องมือ) เห็น CONSTRUCTION_DICT ชุดเล็ก (ไม่ enrich) → ITM011/012 fuzzy เพี้ยน.

[L3] ย้าย enrichment ทั้งหมดไปไว้ที่ "เจ้าของข้อมูล" คือ config_base.py (ต่อท้ายนิยาม CONSTRUCTION_DICT)
ให้ enrich แบบ unconditional ทุกเส้นทาง import. ไฟล์นี้คงไว้เป็น no-op เพื่อความเข้ากันได้ย้อนหลัง
(pukpui_modular_base ยัง `import pukpui_modular_consts` อยู่ — ไม่ต้องแก้ และไม่มี side-effect ซ้ำ).
golden ไม่ขยับ: ชุดคำสุดท้ายเท่าเดิมเป๊ะ (263 คำ) — แค่ย้ายจุดนิยามให้แน่นอน.
"""
from __future__ import annotations

# enrichment ทั้งหมดอยู่ที่ config_base.CONSTRUCTION_DICT แล้ว — ที่นี่ไม่ต้องทำอะไร (idempotent).
