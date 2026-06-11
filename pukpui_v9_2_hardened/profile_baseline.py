# -*- coding: utf-8 -*-
"""profile_baseline.py — โปรไฟล์ parse+audit-core เพื่อ "ตรึงฐานประสิทธิภาพ" (Performance)

ทำไม: เดิมตัวเลข perf (parse 46.9s→9s) อยู่ในเอกสารแบบ claim ไม่มี artifact ที่ reproduce ได้.
สคริปต์นี้ผลิต breakdown จริง (top cumulative ของฟังก์ชันในระบบ) เพื่อ:
  • ใช้เทียบก่อน/หลังเวลามี optimization (กัน regression เงียบ)
  • ชี้ hotspot จริงให้คนดูแล (ผลล่าสุด: parse ครองเวลา ~88%, hotspot = _dic_int_run / _row_label_match)

ใช้:
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 profile_baseline.py [DATA_DIR] [TOPN]
ดีฟอลต์ DATA_DIR=/mnt/project ; ถ้าไม่มีโฟลเดอร์ ใช้ tests/fixtures (เล็ก แต่ยัง reproduce ได้).
ไม่กระทบ golden hash (อ่านอย่างเดียว ผ่านเส้นทางเดิม).
"""
import warnings; warnings.filterwarnings("ignore")
import os
import sys
import glob
import io
import contextlib
import cProfile
import pstats
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

DATA = sys.argv[1] if len(sys.argv) > 1 else "/mnt/project"
TOPN = int(sys.argv[2]) if len(sys.argv) > 2 else 25
if not os.path.isdir(DATA):
    DATA = os.path.join("tests", "fixtures")

from golden_snapshot import MASTER, write_master_file
write_master_file("master_companies.json")
import importlib
app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")

fl = sorted(glob.glob(os.path.join(DATA, "*.xls")) + glob.glob(os.path.join(DATA, "*.xlsx")))
if not fl:
    print(f"ไม่พบไฟล์ .xls/.xlsx ใน {DATA}")
    sys.exit(2)


def _run():
    app.reset_run_state()
    bills, fi = app.parse_all_files(fl)
    for b in bills:
        app.compute_bill_confidence(b)
    app.run_audit_core(bills, MASTER, isolate=True)
    return bills


_INTERNAL = ("ปุ้มปุ้ย", "parser", "rules_engine", "validators", "puopuy",
             "thai_text", "reporting", "analytics")

t0 = time.perf_counter()
with contextlib.redirect_stdout(io.StringIO()):
    pr = cProfile.Profile()
    pr.enable()
    bills = _run()
    pr.disable()
wall = time.perf_counter() - t0

print("=" * 64)
print(f"PROFILE BASELINE — data={DATA}")
print(f"  files={len(fl)}  bills={len(bills)}  wall(parse+audit-core)={wall:.2f}s")
print("=" * 64)
st = pstats.Stats(pr)
st.sort_stats("cumulative")
buf = io.StringIO()
st.stream = buf
st.print_stats(TOPN)
print("top cumulative (เฉพาะฟังก์ชันในระบบ):")
shown = 0
for line in buf.getvalue().splitlines():
    if any(k in line for k in _INTERNAL):
        print("  " + line.strip()[:120])
        shown += 1
if shown == 0:
    print("  (ไม่พบฟังก์ชันในระบบใน topN — ลองเพิ่ม TOPN)")
