# -*- coding: utf-8 -*-
"""test_dashboard_smoke.py — controller ของ Dashboard (.exe) ต้องรัน pipeline จบ + คืนสรุป

ทดสอบ "ชั้นตรรกะ" ของ dashboard.run_audit แบบ headless (ไม่ต้องมีจอ/Tk) บน fixtures:
  • resolve_files หาไฟล์ถูก
  • run_audit รันสายตรวจครบ → ok=True + เขียน Excel จริง + คืนจำนวนบริษัท/บิล
  • ไม่ throw แม้โฟลเดอร์ว่าง (คืน error ใน dict)
GUI (launch) ต้องมี Tk/จอ → ไม่เทสที่นี่ (controller แยกจาก GUI โดยตั้งใจ).
advisory ล้วน — ไม่แตะ golden.

    PYTHONHASHSEED=0 python3 test_dashboard_smoke.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import io
import os
import sys
import contextlib
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import dashboard as D

PASS, FAIL = 0, []


def chk(cond, label):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


print("DASHBOARD CONTROLLER SMOKE — run_audit (headless) บน fixtures")

# resolve_files
chk(len(D.resolve_files("tests/fixtures")) >= 1, "resolve_files เจอไฟล์ใน fixtures")
chk(D.resolve_files("/no/such/dir") == [], "resolve_files โฟลเดอร์ไม่มี → []")

# โฟลเดอร์ว่าง → error ใน dict (ไม่ throw)
_empty = tempfile.mkdtemp()
r0 = D.run_audit(_empty, report_dir=tempfile.mkdtemp(), log=lambda m: None)
chk(r0["ok"] is False and "ไม่พบไฟล์" in r0["error"], "โฟลเดอร์ว่าง → ok=False + error ชัด (ไม่ throw)")

# รันจริงบน fixtures → ok + Excel + นับได้
_out = tempfile.mkdtemp()
with contextlib.redirect_stdout(io.StringIO()):     # กลืน tqdm/print ของ pipeline
    r = D.run_audit("tests/fixtures", report_dir=_out, master_path=None, log=lambda m: None)
chk(r["ok"] is True, f"run_audit fixtures → ok (error={r['error'][:80]})")
chk(r["n_files"] >= 1 and r["n_bills"] >= 1, "นับไฟล์/บิลได้ (>0)")
chk(r["n_companies"] >= 1, "นับบริษัทได้ (>0)")
chk(r["n_clean"] + r["n_recheck"] == r["n_companies"], "ตรง+รีเช็ค = จำนวนบริษัท (สอดคล้อง)")
chk(bool(r["report_path"]) and os.path.exists(r["report_path"]), "เขียน Excel จริง (report_path มีอยู่)")

# open_path ปลอดภัยกับ path ว่าง/ไม่มี (ไม่ throw)
chk(D.open_path("") is False and D.open_path("/no/such/file") is False, "open_path path ว่าง/ไม่มี → False (ไม่ throw)")

print("=" * 60)
if not FAIL:
    print(f"RESULT: ✅ dashboard controller ทำงานครบ — ผ่าน {PASS} เคส (headless)")
    sys.exit(0)
print(f"RESULT: ❌ ไม่ผ่าน {len(FAIL)}/{PASS + len(FAIL)} เคส")
sys.exit(1)
