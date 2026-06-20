# -*- coding: utf-8 -*-
"""test_report_det.py — GATE (A3): รายงาน Excel ต้อง deterministic (ไม่มี timestamp/order leak)

บริบท: golden_master ครอบ "ผลตรวจ" (bills/issues) แต่ "รายงาน Excel" (ชั้นแสดงผล) เดิมไม่มี gate ใน CI
(verify_report_det.py hardcode /mnt/project → รันใน CI/sandbox ไม่ได้). report ที่ไม่ deterministic
(เช่น timestamp รั่ว / ลำดับ dict ไม่นิ่ง) = รายงานเพี้ยนเงียบโดย CI จับไม่ได้.

เทสนี้พิสูจน์ "determinism เชิงสัมพัทธ์" บน fixtures: รัน verify_report_det.py 2 รอบ แล้ว REPORT_DET_HASH
ต้องตรงกันเป๊ะ → รายงานนิ่ง (no nondeterminism หลัง normalize timestamp). ใช้วิธีนี้แทนการ pin ค่า
absolute เพราะค่า absolute (เช่น fff69fc6) ผูกกับ Python/openpyxl เวอร์ชัน → เปราะข้าม 3.11/3.12
(ค่า absolute = หน้าที่ของ cert บน 106 ไฟล์จริง — ดู ⚠ NEEDS_REAL_DATA_CERT ใน HARDENING_DELIVERY).

exit 0 = report นิ่ง, 1 = ไม่นิ่ง/รันไม่ได้.
"""
import os
import re
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


def _report_hash():
    """รัน verify_report_det.py บน fixtures → ดึง REPORT_DET_HASH."""
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    env.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
    r = subprocess.run([sys.executable, os.path.join(HERE, "verify_report_det.py")],
                       capture_output=True, text=True, env=env, cwd=HERE)
    m = re.search(r"REPORT_DET_HASH\s+([0-9a-f]{64})", r.stdout or "")
    return (m.group(1) if m else None), r


print("REPORT DETERMINISM (A3) — รายงาน Excel ต้องนิ่ง (รัน 2 รอบ hash ตรงกัน)")

h1, r1 = _report_hash()
_check(f"รอบที่ 1 ได้ REPORT_DET_HASH ({(h1 or 'NONE')[:12]}…)", h1 is not None)
if h1 is None:
    print("    stderr:", (r1.stderr or r1.stdout)[-400:])
    print("=" * 60); print("RESULT: ❌ รัน verify_report_det ไม่ได้"); sys.exit(1)

h2, _ = _report_hash()
_check(f"รอบที่ 2 ได้ค่าตรงกับรอบที่ 1 (deterministic)", h1 == h2)

print("=" * 60)
if _fail == 0:
    print(f"RESULT: ✅ รายงาน Excel deterministic บน fixtures (hash {h1[:12]}… ซ้ำได้)")
    sys.exit(0)
print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — รายงานไม่ deterministic (ตรวจ timestamp/ลำดับ dict)")
sys.exit(1)
