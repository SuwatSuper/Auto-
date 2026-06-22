#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_release.py — ประตูปล่อยแพ็กเกจ: build → extract → verify → ส่งได้เฉพาะถ้า hash == baseline (ADR-053)

ที่มา: ADR-052 — แพ็กเกจ RECHECK ถูกส่งออกทั้งที่โค้ดให้ hash bcfcaf37 ≠ baseline ba9deda0 (CI จับได้
แต่ขั้น packaging ไม่ได้บังคับรัน). สคริปต์นี้ทำให้ "สร้าง zip ที่ไม่ reproduce golden" เป็นไปไม่ได้:
  1) build zip จาก source (ตัด junk/ไฟล์ generate)
  2) extract zip ไป temp สะอาด (Python zipfile — กันชื่อไทยเพี้ยน)
  3) รัน regression_full (engine==agent==baseline) + check_invariants บน "tree ที่แตกจาก zip จริง"
  4) เทียบ engine hash == baseline.json._sha256
  → ผ่านครบ = เก็บ zip ; พลาดข้อใด = ลบ zip ทิ้ง + exit 1 (ส่งไม่ได้)

ใช้:  PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 make_release.py <pkg_dir> <data_dir> <out.zip>
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile

# ไฟล์/โฟลเดอร์ที่ "ห้ามแพ็ก" (generate ตอนรัน / ขยะ / artifact)
EXCLUDE_DIRS = {'__pycache__', 'e2e_output', '.git', '.pytest_cache', '.mypy_cache'}
EXCLUDE_EXACT = {'master_companies.json'}            # stub ที่ write_master_file สร้าง (ADR-049) — regenerate เอง
EXCLUDE_SUFFIX = ('.orig', '.log', '.pyc', '.user.bak', '.tmp')


def _iter_files(root: str):
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            if f in EXCLUDE_EXACT or f.endswith(EXCLUDE_SUFFIX):
                continue
            yield os.path.join(r, f)


def _build_zip(pkg_dir: str, out_zip: str) -> int:
    pkg_dir = os.path.normpath(pkg_dir)
    base = os.path.basename(pkg_dir)                  # เก็บ prefix โฟลเดอร์ระบบไว้ (เหมือนแพ็กเกจเดิม)
    parent = os.path.dirname(os.path.abspath(pkg_dir))
    files = sorted(_iter_files(pkg_dir))
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = os.path.join(base, os.path.relpath(p, pkg_dir))
            z.write(p, arc)                          # zipfile ตั้ง UTF-8 flag เอง → ชื่อไทยรอด
    return len(files)


def _run(cmd, cwd) -> tuple[int, str]:
    env = dict(os.environ, PYTHONHASHSEED='0',
               PUOPUY_AUDIT_DATE=os.environ.get('PUOPUY_AUDIT_DATE', '2026-06-02'),
               PUOPUY_OFFLINE='1')
    p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr)


def main() -> int:
    if len(sys.argv) != 4:
        print('ใช้: python3 make_release.py <pkg_dir> <data_dir> <out.zip>'); return 2
    pkg_dir, data_dir, out_zip = sys.argv[1], sys.argv[2], sys.argv[3]

    # baseline hash ที่ต้องตรง
    baseline_hash = json.load(open(os.path.join(pkg_dir, 'baseline.json')))['_sha256']
    print('=' * 64)
    print('MAKE RELEASE — build → extract → verify (ห้ามส่งถ้า drift)')
    print(f'  pkg      : {pkg_dir}')
    print(f'  data     : {data_dir}')
    print(f'  out      : {out_zip}')
    print(f'  baseline : {baseline_hash[:24]}')
    print('=' * 64)

    # [1] build
    n = _build_zip(pkg_dir, out_zip)
    print(f'[1] build zip ... {n} ไฟล์')

    # [2] extract → temp สะอาด
    tmp = tempfile.mkdtemp(prefix='mkrel_')
    try:
        with zipfile.ZipFile(out_zip) as z:
            z.extractall(tmp)
            mangled = [x for x in z.namelist() if '#U' in x or '\ufffd' in x]
        if mangled:
            print(f'❌ ชื่อไฟล์เพี้ยน {len(mangled)} รายการ — ส่งไม่ได้'); _fail(out_zip); return 1
        extracted_pkg = os.path.join(tmp, os.path.basename(os.path.normpath(pkg_dir)))
        print(f'[2] extract → temp สะอาด (ชื่อไทยครบ)')

        # [3] oracle บน tree ที่แตกจาก zip จริง
        rc, out = _run([sys.executable, 'regression_full.py', '.', data_dir], extracted_pkg)
        ok_reg = (rc == 0 and 'ผ่านทั้งหมด' in out)
        print(f'[3a] regression_full (engine==agent==baseline) ... {"✅" if ok_reg else "❌"}')
        rc2, out2 = _run([sys.executable, 'INVARIANTS/check_invariants.py'], extracted_pkg)
        ok_inv = (rc2 == 0)
        print(f'[3b] check_invariants (fixture+pin) ............... {"✅" if ok_inv else "❌"}')

        # [4] engine hash == baseline
        snap = os.path.join(tmp, '_rel_engine.json')
        rc3, _ = _run([sys.executable, 'golden_master.py', '.', snap, data_dir], extracted_pkg)
        got = json.load(open(snap))['_sha256'] if os.path.isfile(snap) else '(none)'
        ok_hash = (got == baseline_hash)
        print(f'[4] shipped-tree engine hash = {got[:24]} ... {"✅ ตรง" if ok_hash else "❌ DRIFT"}')

        if ok_reg and ok_inv and ok_hash:
            print('=' * 64)
            print(f'✅ RELEASE OK — {out_zip} reproduce golden {baseline_hash[:16]}')
            print('=' * 64)
            return 0
        print('=' * 64)
        print('❌ RELEASE ปฏิเสธ — แพ็กเกจไม่ reproduce golden → ลบ zip ทิ้ง')
        print('=' * 64)
        _fail(out_zip)
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _fail(out_zip: str):
    try:
        if os.path.isfile(out_zip):
            os.remove(out_zip)
    except OSError:
        pass


if __name__ == '__main__':
    sys.exit(main())
