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

# ไฟล์/โฟลเดอร์ที่ "ห้ามแพ็ก" (generate ตอนรัน / ขยะ / artifact / env / ข้อมูลลูกค้า PII)
#   [ADR-129] เดิม os.walk ตัดแค่ 5 dir → "ลืม" corpus/ (148 ไฟล์ PII ลูกค้า), .venv, dist, รายงาน PII
#   → make_release ใส่ลง zip ที่ส่งออก (PII leak) โดย hash gate ไม่จับ (corpus ไม่กระทบ hash). ตัดให้ครบ
#   ตาม .gitignore (ข้อมูลจริง/env/build) + เก็บ vendor/wheels (จงใจ include เพื่อ offline) + self-check ปิดท้าย.
EXCLUDE_DIRS = {'__pycache__', 'e2e_output', '.git', '.pytest_cache', '.mypy_cache',
                '.ruff_cache', '.vscode', 'dist', 'build', '.eggs', '.tox', 'node_modules', 'corpus'}
EXCLUDE_EXACT = {'master_companies.json',            # stub ที่ write_master_file สร้าง (ADR-049) — regenerate เอง
                 'snapshot.json',                    # [ADR-078] output ของ golden_master.py (default OUT) — ไม่ใช่ source
                 '_iv_truth_report.json',            # [ADR-078] output ของ _audit_iv_truth.py (CI [8d] เขียนลง cwd) — ไม่ใช่ source
                 'audit_charts.png', 'audit_dashboard_report.html',  # [ADR-129] รายงาน PII (derive จากข้อมูลจริง)
                 'audit_system_issues.jsonl', '.coverage', '.coverage.json'}
EXCLUDE_PREFIX = ('company_summary', 'ตัวอย่างผลลัพธ์', '_f1_')   # [ADR-129] รายงาน/ไฟล์ทดลอง PII (.gitignore)
EXCLUDE_SUFFIX = ('.orig', '.log', '.pyc', '.user.bak', '.tmp')


def _skip_dir(parent: str, name: str, data_abs: str) -> bool:
    """[ADR-129] dir ที่ "ไม่แพ็ก": ชื่อใน EXCLUDE_DIRS, prefix .venv*, ราก virtualenv (pyvenv.cfg),
    หรือ "โฟลเดอร์ข้อมูล (data_dir)" ที่ผู้ใช้ส่งมา (= ข้อมูลลูกค้า ไม่ใช่ source)."""
    if name in EXCLUDE_DIRS or name.startswith('.venv') or name.endswith('.egg-info'):
        return True
    full = os.path.join(parent, name)
    if os.path.isfile(os.path.join(full, 'pyvenv.cfg')):
        return True
    if data_abs and os.path.realpath(full) == data_abs:    # โฟลเดอร์ข้อมูลที่ส่งมา (corpus จริง)
        return True
    return False


def _iter_files(root: str, data_abs: str = ''):
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not _skip_dir(r, d, data_abs)]
        for f in files:
            if f in EXCLUDE_EXACT or f.endswith(EXCLUDE_SUFFIX) or f.startswith(EXCLUDE_PREFIX):
                continue
            if f.endswith('.bak') and '.json.' in f:        # *.json.*.bak (golden rebaseline backup, .gitignore)
                continue
            yield os.path.join(r, f)


def _build_zip(pkg_dir: str, out_zip: str, data_abs: str = '') -> int:
    pkg_dir = os.path.normpath(pkg_dir)
    base = os.path.basename(pkg_dir)                  # เก็บ prefix โฟลเดอร์ระบบไว้ (เหมือนแพ็กเกจเดิม)
    files = sorted(_iter_files(pkg_dir, data_abs))
    with zipfile.ZipFile(out_zip, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            arc = os.path.join(base, os.path.relpath(p, pkg_dir))
            z.write(p, arc)                          # zipfile ตั้ง UTF-8 flag เอง → ชื่อไทยรอด
    return len(files)


# [ADR-129] self-check: ห้ามมี PII/ข้อมูลลูกค้า/env หลุดเข้า zip ที่จะส่ง (defense-in-depth — แม้ exclude
#   ตกหล่น ก็ "ส่งไม่ได้"). อนุญาต tests/fixtures + tests/real_cases (ข้อมูลทดสอบย่อที่ commit ตั้งใจ).
_PII_MARKERS = ('/corpus/', 'master_companies.json', '/.venv', 'pyvenv.cfg', '/dist/',
                'audit_charts.png', 'audit_dashboard_report.html', 'audit_system_issues.jsonl',
                'snapshot.json', '_iv_truth_report.json', 'company_summary', 'ตัวอย่างผลลัพธ์')


def _zip_pii(zip_path: str, data_abs: str) -> list:
    """คืนรายชื่อ entry ใน zip ที่เป็น PII/ข้อมูลลูกค้า/env (ต้องว่าง มิฉะนั้นส่งไม่ได้)."""
    data_base = os.path.basename(os.path.normpath(data_abs)) if data_abs else ''
    bad = []
    with zipfile.ZipFile(zip_path) as z:
        for n in z.namelist():
            low = n
            if any(m in low for m in _PII_MARKERS):
                bad.append(n); continue
            if low.endswith('.bak') and '.json.' in low:
                bad.append(n); continue
            # โฟลเดอร์ข้อมูลที่ผู้ใช้ส่งมา (เผื่อชื่ออื่นที่ไม่ใช่ 'corpus')
            if data_base and f'/{data_base}/' in f'/{low}':
                bad.append(n)
    return bad


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
    # [ADR-129] ข้อมูล (corpus) = "ของลูกค้า ไม่แพ็ก" — verify ด้วย path เดิม (absolute) ไม่ใช่สำเนาใน zip.
    #   portable-golden strip path อยู่แล้ว → hash ไม่ขึ้นกับตำแหน่ง corpus (relative/absolute ได้ผลเท่ากัน).
    data_abs = os.path.abspath(data_dir)

    # baseline hash ที่ต้องตรง
    baseline_hash = json.load(open(os.path.join(pkg_dir, 'baseline.json')))['_sha256']
    print('=' * 64)
    print('MAKE RELEASE — build → extract → verify (ห้ามส่งถ้า drift)')
    print(f'  pkg      : {pkg_dir}')
    print(f'  data     : {data_dir}')
    print(f'  out      : {out_zip}')
    print(f'  baseline : {baseline_hash[:24]}')
    print('=' * 64)

    # [1] build (ข้าม corpus/master/รายงาน/.venv — data_abs ใช้กันโฟลเดอร์ข้อมูลออก)
    n = _build_zip(pkg_dir, out_zip, data_abs)
    print(f'[1] build zip ... {n} ไฟล์')

    # [1b] [ADR-129] self-check: PII/ข้อมูลลูกค้า/env ห้ามหลุดเข้า zip (ส่งไม่ได้ถ้าพบ)
    pii = _zip_pii(out_zip, data_abs)
    if pii:
        print(f'❌ พบ PII/ข้อมูลลูกค้า/env ใน zip {len(pii)} รายการ — ส่งไม่ได้: {pii[:5]}')
        _fail(out_zip); return 1
    print('[1b] PII/data self-check ... ✅ (ไม่มี corpus/master/รายงาน/.venv หลุด)')

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

        # [3] oracle บน tree ที่แตกจาก zip จริง — corpus อ่านจาก path เดิม (absolute, ไม่อยู่ใน zip)
        rc, out = _run([sys.executable, 'regression_full.py', '.', data_abs], extracted_pkg)
        ok_reg = (rc == 0 and 'ผ่านทั้งหมด' in out)
        print(f'[3a] regression_full (engine==agent==baseline) ... {"✅" if ok_reg else "❌"}')
        rc2, out2 = _run([sys.executable, 'INVARIANTS/check_invariants.py'], extracted_pkg)
        ok_inv = (rc2 == 0)
        print(f'[3b] check_invariants (fixture+pin) ............... {"✅" if ok_inv else "❌"}')

        # [4] engine hash == baseline
        snap = os.path.join(tmp, '_rel_engine.json')
        rc3, _ = _run([sys.executable, 'golden_master.py', '.', snap, data_abs], extracted_pkg)
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
