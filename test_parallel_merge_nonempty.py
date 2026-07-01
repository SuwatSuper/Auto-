# -*- coding: utf-8 -*-
"""test_parallel_merge_nonempty.py — STRESS: cross-worker merge ของ list ที่ "ไม่ว่าง" (Scalability)

บริบท: verify_parallel บน sandbox พิสูจน์ serial==parallel แล้ว แต่ sandbox มี system_issues=0
จึง "ยังไม่ได้ทดสอบ" การ merge _SYSTEM_ISSUES ที่ไม่ว่างข้าม worker (จุดที่ parallel_audit อ้างว่า
dedup-by-file ทำให้ปลอดภัย). เทสนี้ "บังคับ" ให้เกิด SYS001 จริง (ใส่ไฟล์ 0 ไบต์ → file_guard
ปฏิเสธ → log SYS001) แล้วยืนยันว่า serial กับ parallel(workers=2) ได้ system_issues "ตรงกันและไม่ว่าง".

self-contained: ใช้ tests/fixtures/fixture_invoices.xlsx (ไม่พึ่ง /mnt/project) + ไฟล์เสีย temp.
ต้องตั้ง PYTHONHASHSEED=0 ก่อนรัน (เหมือนทุกเทสในระบบ).
"""
import os
import sys
import glob
import shutil
import tempfile
import contextlib
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import importlib
import state

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


FIXTURE = os.path.join("tests", "fixtures", "fixture_invoices.xlsx")
if not os.path.isfile(FIXTURE):
    # เผื่อ fixture ชื่ออื่น
    cands = glob.glob(os.path.join("tests", "fixtures", "*.xlsx"))
    FIXTURE = cands[0] if cands else None

if not FIXTURE:
    print("  ⚠️ ไม่พบ fixture .xlsx — ข้ามเทส (ถือว่าผ่านแบบ no-op)")
    print("RESULT: ✅ (skipped — no fixture)")
    sys.exit(0)

app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
from parallel_audit import parse_all_files_parallel

tmp = tempfile.mkdtemp(prefix="puopuy_merge_")
try:
    v1 = os.path.join(tmp, "valid_a.xlsx")
    v2 = os.path.join(tmp, "valid_b.xlsx")
    bad = os.path.join(tmp, "bad_empty.xls")
    shutil.copy(FIXTURE, v1)
    shutil.copy(FIXTURE, v2)
    open(bad, "wb").close()                 # ไฟล์ 0 ไบต์ → file_guard ปฏิเสธ → SYS001
    file_list = [v1, bad, v2]               # bad อยู่กลาง → กระจายข้าม chunk แน่นอน

    with contextlib.redirect_stdout(io.StringIO()):
        app.reset_run_state()
        b_s, fi_s = app.parse_all_files(file_list)
        si_s = list(state._SYSTEM_ISSUES)
        tn_s = list(state._TEXT_NUM_RECOVERIES)

        b_p, fi_p = parse_all_files_parallel(file_list, workers=2)
        si_p = list(state._SYSTEM_ISSUES)
        tn_p = list(state._TEXT_NUM_RECOVERIES)

    print(f"  serial   : bills={len(b_s)} sys_issues={len(si_s)} text_num={len(tn_s)}")
    print(f"  parallel : bills={len(b_p)} sys_issues={len(si_p)} text_num={len(tn_p)}")

    _check("system_issues ไม่ว่าง (บังคับ SYS001 สำเร็จ — เส้น merge ถูกกระตุ้นจริง)", len(si_s) >= 1)
    _check("bills serial == parallel", len(b_s) == len(b_p))
    _check("system_issues serial == parallel (merge ข้าม worker ถูกต้อง)", si_s == si_p)
    _check("text_num serial == parallel", tn_s == tn_p)
    _check("filename_issues serial == parallel", fi_s == fi_p)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("=" * 56)
if _fail == 0:
    print("RESULT: ✅ cross-worker merge ของ system_issues ที่ไม่ว่าง = ตรง serial เป๊ะ")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — อย่าใช้ parallel จนกว่าจะแก้")
    sys.exit(1)
