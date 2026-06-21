# -*- coding: utf-8 -*-
"""test_typing_leaf.py — TRIPWIRE: ชั้น leaf utility ต้อง " type-annotated ครบ + ผ่าน mypy"

บริบท: โค้ดส่วนใหญ่ของระบบ (parser/rules ที่ใช้ re-export chain แบบ dynamic) ไม่เหมาะกับ
static typing ทั้งก้อน (mypy มอง name ที่มาทาง reexport เป็น undefined → false positive เพียบ).
แต่ "ชั้น leaf utility" — puopuy_core / puopuy_dates / puopuy_units / core_utils — เป็นโมดูล
self-contained (ไม่พึ่ง re-export chain) จึง type ครบและ type-check ได้จริง.

เทสนี้ตรึงสัญญานั้น: ทุกฟังก์ชันใน 4 โมดูลนี้ต้องมี annotation ครบ (--disallow-untyped-defs /
--disallow-incomplete-defs) และ mypy ต้องไม่พบ error. ถ้าใครเพิ่มฟังก์ชันใหม่แบบไม่ใส่ type
หรือทำ type พัง → เทสนี้แดง. (annotation เป็น metadata เท่านั้น + ทุกไฟล์มี
`from __future__ import annotations` → ไม่ถูก evaluate ตอนรัน → golden hash ไม่ขยับ.)

mypy ไม่ได้ติดตั้ง → SKIP อย่างนุ่มนวล (เหมือน coverage gate ใน run_ci.sh) เพื่อไม่บล็อก
สภาพแวดล้อม minimal. GitHub CI ติดตั้ง mypy แล้วบังคับจริง (ดู .github/workflows/ci.yml).
exit 0 = ผ่าน/skip, 1 = พบ untyped def หรือ type error.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

# [A2 reachability] ผูกเทสเข้ากับ production graph — โมดูลที่เทสนี้คุม (ต้อง import ได้สะอาดด้วย)
import puopuy_core      # noqa: E402,F401
import puopuy_dates     # noqa: E402,F401
import puopuy_units     # noqa: E402,F401
import core_utils       # noqa: E402,F401

LEAF_MODULES = ["puopuy_core.py", "puopuy_dates.py", "puopuy_units.py", "core_utils.py"]

print("TYPING LEAF — ชั้น leaf utility ต้อง type-annotated ครบ + ผ่าน mypy")

try:
    from mypy import api as mypy_api
except Exception:
    print("  ⏭️  SKIP — ไม่พบ mypy (pip install mypy) → ข้ามการตรวจชนิด")
    print("RESULT: ✅ SKIP (typing gate ใช้เมื่อมี mypy เท่านั้น — GitHub CI บังคับจริง)")
    sys.exit(0)

args = [
    "--ignore-missing-imports",       # config/state/pandas ไม่มี stub — ไม่ใช่ประเด็นของ leaf
    "--disallow-untyped-defs",        # ทุก def ต้องมี annotation
    "--disallow-incomplete-defs",     # ห้าม annotate ครึ่ง ๆ กลาง ๆ
    "--no-error-summary",
    "--no-color-output",
    *[os.path.join(HERE, m) for m in LEAF_MODULES],
]
stdout, stderr, status = mypy_api.run(args)

if stdout.strip():
    print(stdout.rstrip())
if stderr.strip():
    print(stderr.rstrip())

print("=" * 60)
if status != 0:
    print(f"RESULT: ❌ FAIL — mypy พบปัญหาใน leaf layer (exit {status})")
    sys.exit(1)
print(f"RESULT: ✅ leaf layer type-annotated ครบ + ผ่าน mypy ({len(LEAF_MODULES)} โมดูล)")
sys.exit(0)
