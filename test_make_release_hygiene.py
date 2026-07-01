# -*- coding: utf-8 -*-
"""test_make_release_hygiene.py — [ADR-129] ตาข่ายนิรภัย: make_release ต้อง "ไม่แพ็ก" ข้อมูลลูกค้า/PII/env.

บั๊กเดิม (HIGH): make_release._iter_files เดิน os.walk โดยตัดแค่ 5 dir → ใส่ corpus/ (148 ไฟล์
PII ลูกค้า: ชื่อบริษัท/เลขภาษี/ที่อยู่/ยอดเงิน) + .venv/dist/รายงาน ลง release zip ที่ส่งออก.
hash gate ไม่จับเพราะ corpus ไม่กระทบ hash (golden = ผลตรวจ ไม่ใช่รายชื่อไฟล์). คำเชิญ §10 จริง
`make_release.py . corpus out.zip` (pkg='.' มี corpus/) → PII leak.

แก้ (ADR-129): (ก) ตัด corpus (=data_dir), .venv*, dist/build/cache, รายงาน PII ออกจากการแพ็ก ;
(ข) verify ด้วย corpus path เดิม (absolute) ไม่ใช่สำเนาใน zip (portable-golden strip path → hash เท่าเดิม) ;
(ค) self-check `_zip_pii` ปฏิเสธ release ถ้าพบ PII หลุด (defense-in-depth).

เทสนี้ล็อก: keep vendor/wheels + source + tests/fixtures + tests/real_cases ; drop corpus/master/.venv/dist/รายงาน ;
self-check จับ PII แต่ไม่จับ source/fixture. golden-neutral (เทส/tooling). รันได้ทุกที่.
"""
import os
import sys
import zipfile
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_release as M

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    print('=== [A] _skip_dir: env/build/data ข้าม ; source/vendor ไม่ข้าม ===')
    with tempfile.TemporaryDirectory() as td:
        data_abs = os.path.join(td, 'corpus')
        os.makedirs(data_abs)
        os.makedirs(os.path.join(td, 'customenv'))
        with open(os.path.join(td, 'customenv', 'pyvenv.cfg'), 'w') as f:
            f.write('home=/usr/bin\n')
        for nm in ('corpus', '.venv', '.venv_x', 'dist', 'build', '.mypy_cache',
                   'node_modules', 'customenv', 'pkg.egg-info'):
            _check(M._skip_dir(td, nm, data_abs), f'ข้าม {nm!r}')
        for nm in ('agents', 'tests', 'vendor', 'INVARIANTS'):
            _check(not M._skip_dir(td, nm, data_abs), f'ไม่ข้าม {nm!r}')

    print()
    print('=== [B] _iter_files: drop corpus/PII ; keep source/fixtures/vendor ===')
    with tempfile.TemporaryDirectory() as td:
        def w(rel, content='x'):
            p = os.path.join(td, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write(content)
        w('parser_p1.py')
        w('baseline.json', '{}')
        w('tests/fixtures/fixture_invoices.xlsx', 'fx')
        w('tests/real_cases/KRR_69_05.xls', 'rc')
        w('vendor/wheels/pandas.whl', 'whl')
        w('corpus/KRR_69_057.xls', 'PII')
        w('master_companies.json', '{}')
        w('company_summary_x.txt', 'PII')
        w('audit_charts.png', 'PII')
        w('baseline.json.20260601.bak', 'bak')
        os.makedirs(os.path.join(td, '.venv', 'lib'))
        w('.venv/lib/huge.py')
        os.makedirs(os.path.join(td, 'dist'))
        w('dist/old_release.zip', 'z')
        data_abs = os.path.realpath(os.path.join(td, 'corpus'))
        got = {os.path.relpath(p, td) for p in M._iter_files(td, data_abs)}
        keep = ['parser_p1.py', 'baseline.json',
                os.path.join('tests', 'fixtures', 'fixture_invoices.xlsx'),
                os.path.join('tests', 'real_cases', 'KRR_69_05.xls'),
                os.path.join('vendor', 'wheels', 'pandas.whl')]
        drop = [os.path.join('corpus', 'KRR_69_057.xls'), 'master_companies.json',
                'company_summary_x.txt', 'audit_charts.png', 'baseline.json.20260601.bak',
                os.path.join('.venv', 'lib', 'huge.py'), os.path.join('dist', 'old_release.zip')]
        for k in keep:
            _check(k in got, f'แพ็ก {k}')
        for d in drop:
            _check(d not in got, f'ไม่แพ็ก {d}')

    print()
    print('=== [C] _zip_pii self-check (ปฏิเสธ PII ; ผ่าน source/fixture) ===')
    with tempfile.TemporaryDirectory() as td:
        zp = os.path.join(td, 'rel.zip')
        with zipfile.ZipFile(zp, 'w') as z:
            z.writestr('pkg/parser_p1.py', 'x')
            z.writestr('pkg/tests/real_cases/KRR_69_05.xls', 'rc')
            z.writestr('pkg/corpus/KRR_69_057.xls', 'PII')
            z.writestr('pkg/master_companies.json', '{}')
            z.writestr('pkg/.venv/lib/x.py', 'x')
            z.writestr('pkg/company_summary_x.txt', 'PII')
        bad = set(M._zip_pii(zp, os.path.realpath('corpus')))
        _check(any('corpus' in b for b in bad), 'self-check จับ corpus PII')
        _check(any('master_companies' in b for b in bad), 'self-check จับ master')
        _check(any('.venv' in b for b in bad), 'self-check จับ .venv')
        _check(any('company_summary' in b for b in bad), 'self-check จับ รายงาน')
        _check(not any('parser_p1' in b for b in bad), 'self-check ไม่จับ source (parser_p1.py)')
        _check(not any('real_cases' in b for b in bad), 'self-check ไม่จับ tests/real_cases (data ทดสอบที่ commit)')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — make_release ไม่แพ็ก PII/ข้อมูลลูกค้า/env + self-check ปิดท้าย')
    return 0


if __name__ == '__main__':
    sys.exit(main())
