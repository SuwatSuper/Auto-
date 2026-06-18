# -*- coding: utf-8 -*-
"""test_package_integrity.py — TRIPWIRE: deliverable zip ต้องไม่พังจากชื่อไฟล์ไทย

บริบท (บทเรียนจริง): `git archive` ไม่ตั้ง UTF-8 flag → unzip แตกชื่อไฟล์ไทยเพี้ยน →
โมดูลหลัก "ปุ้มปุ้ย_ultimate_v9_modular.py" หาย → แพ็กพังเงียบ (รัน 15/50). package.sh แก้ด้วย
Python zipfile (ตั้ง flag 0x800). เทสนี้รัน package.sh จริงแล้ว "ตรวจซ้ำอย่างอิสระ" ว่าแพ็กดี:
  1) โมดูลหลัก (ชื่อไทย) อยู่ในแพ็ก
  2) ทุก entry ชื่อ non-ASCII มี UTF-8 flag (0x800) → unzip แตกได้ทุกที่
  3) ไม่มี .git/__pycache__/*.pyc/master_companies.json/.env หลุดเข้าแพ็ก (กันข้อมูลรั่ว)

ถ้าใครทำ packaging พังอีก (เช่นกลับไปใช้ git archive) → เทสนี้แดงทันที.
self-contained: รัน package.sh ไปไฟล์ temp แล้วตรวจด้วย zipfile (ไม่แตะ dist/ จริง).
"""
import os
import sys
import subprocess
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PREFIX = "pukpui_v9_3_4"
MAIN = f"{PREFIX}/ปุ้มปุ้ย_ultimate_v9_modular.py"
JUNK_SUBSTR = ("/.git/", "__pycache__", "/master_companies.json")

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


print("PACKAGE INTEGRITY — deliverable zip ต้องไม่พังจากชื่อไฟล์ไทย")

# guard: เทสนี้มีความหมายเฉพาะใน "source repo" (package.sh ใช้ git ls-files).
#   ในแพ็กที่แตกแล้ว (ไม่มี .git) → SKIP อย่างนุ่มนวล (ไม่ทำ run_ci ในแพ็กที่ส่งมอบพัง).
_git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                      capture_output=True, text=True, cwd=HERE)
if _git.returncode != 0 or _git.stdout.strip() != "true":
    print("  ⏭️  SKIP — ไม่ใช่ git repo (แพ็กที่แตกแล้ว) → ข้ามการตรวจ packaging")
    print("RESULT: ✅ SKIP (เทส packaging ใช้เฉพาะใน source repo)")
    sys.exit(0)

with tempfile.TemporaryDirectory() as td:
    out = os.path.join(td, "deliver.zip")
    r = subprocess.run(["bash", os.path.join(HERE, "package.sh"), out],
                       capture_output=True, text=True, cwd=HERE)
    _check(f"package.sh รันสำเร็จ (rc={r.returncode})", r.returncode == 0)
    if r.returncode != 0:
        print("    stderr:", (r.stderr or r.stdout)[-400:])
        print("=" * 60)
        print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — package.sh พัง")
        sys.exit(1)

    with zipfile.ZipFile(out) as z:
        infos = z.infolist()
        names = set(z.namelist())

        _check("โมดูลหลัก (ชื่อไทย) อยู่ในแพ็ก", MAIN in names)

        no_flag = [i.filename for i in infos
                   if any(ord(c) > 127 for c in i.filename) and not (i.flag_bits & 0x800)]
        _check(f"ทุก entry ชื่อ non-ASCII มี UTF-8 flag (พลาด: {len(no_flag)})", not no_flag)

        junk = [n for n in names
                if any(j in n for j in JUNK_SUBSTR) or n.endswith((".pyc", ".env"))]
        _check(f"ไม่มี cache/secret หลุดเข้าแพ็ก (พบ: {junk[:3]})", not junk)

        n_thai = sum(1 for n in names if any(ord(c) > 127 for c in n))
        print(f"     (แพ็ก {len(names)} entry · ไฟล์ชื่อไทย {n_thai})")

print("=" * 60)
if _fail == 0:
    print("RESULT: ✅ deliverable zip สมบูรณ์ — ชื่อไฟล์ไทยไม่พัง + ไม่มีข้อมูลรั่ว")
    sys.exit(0)
print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — ตรวจ package.sh")
sys.exit(1)
