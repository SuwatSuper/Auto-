# -*- coding: utf-8 -*-
"""test_reset_completeness.py — GUARD (A4): reset_run_state ต้อง "ล้างครบ" — parse 2 รอบได้ผลเท่ากัน

บริบท: ระบบมี mutable caches ระดับโมดูล (state._FUZZY_DICT_CACHE / _PRODUCT_WHITELIST / pythainlp ฯลฯ).
ถ้า reset_run_state ล้างไม่ครบ → รอบที่ 2 ใน session เดียว "เห็นค่าค้างจากรอบแรก" → ผลตรวจเพี้ยน
แบบ non-deterministic (เฉพาะตอนรันหลายชุดในโปรเซสเดียว เช่น Colab/agent harness).

เทสนี้พิสูจน์ "reset completeness" เชิงประจักษ์: รัน pipeline เต็ม (parse→audit core→snapshot hash)
2 รอบในโปรเซสเดียว มี reset_run_state คั่น → golden hash ทั้งสองรอบต้อง "เท่ากันเป๊ะ".
ครอบทุก cache รวม PRODUCT_MASTER-derived (_PRODUCT_WHITELIST) โดยไม่ต้องแตะโค้ด reset.

[DECIDE GATE — A4] ทำไมไม่ reload PRODUCT_MASTER ใน reset_run_state (option ก/ข ที่เสนอ):
  • product_master.json ไม่มีจริง → PRODUCT_MASTER={} เสมอ (ไม่มี active risk)
  • test_rules_extra.py:330-350 จงใจ rebind rules_engine.PRODUCT_MASTER → ถ้า reset force-reload
    จะทับ rebind = regression ของเทสนั้น (rules_engine docstring ยืนยัน "test อาจ rebind")
  • reset_run_state ล้าง state._PRODUCT_WHITELIST (cache ที่ derive จาก PRODUCT_MASTER) อยู่แล้ว
  → จึงใช้ empirical guard นี้แทนการแตะ production reset (zero regression). บันทึกใน P3_FOLLOWUP §5 A4.

self-contained (fixtures). exit 0 = reset ครบ, 1 = พบ cache bleed.
"""
import os
import sys
import glob
import importlib

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))

from golden_snapshot import MASTER, snapshot_and_hash, write_master_file

write_master_file("master_companies.json")
app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")

_FILES = sorted(glob.glob(os.path.join(HERE, "tests", "fixtures", "*.xls"))
                + glob.glob(os.path.join(HERE, "tests", "fixtures", "*.xlsx")))


def _one_round():
    """รัน pipeline เต็มหนึ่งรอบ (เลียน golden_master) → คืน sha256 ของ snapshot."""
    app.reset_run_state()
    all_bills, filename_issues = app.parse_all_files(_FILES)
    for b in all_bills:
        app.compute_bill_confidence(b)
    core = app.run_audit_core(all_bills, MASTER, isolate=True)
    _, digest = snapshot_and_hash(_FILES, all_bills, filename_issues,
                                  core["dup_items"], core["iv_seq"], core["iv_date"],
                                  core["typos"], core["summary"])
    return digest


print("RESET COMPLETENESS (A4) — parse 2 รอบในโปรเซสเดียว ต้องได้ผลเท่ากัน")
h1 = _one_round()
h2 = _one_round()          # รอบ 2 ในโปรเซสเดียวกัน (มี reset_run_state คั่นใน _one_round)
print(f"  รอบ 1: {h1[:16]}…")
print(f"  รอบ 2: {h2[:16]}…")

ok = (h1 == h2)
print(("  ✅ " if ok else "  ❌ ") + "สองรอบเท่ากัน (reset_run_state ล้าง cache ครบ ไม่มี bleed)")
print("=" * 60)
if ok:
    print("RESULT: ✅ reset completeness OK — pipeline idempotent ข้ามรอบในโปรเซสเดียว")
    sys.exit(0)
print("RESULT: ❌ รอบ 2 ≠ รอบ 1 — มี cache ค้างข้ามรอบ (ตรวจ reset_run_state ว่าล้างครบ)")
sys.exit(1)
