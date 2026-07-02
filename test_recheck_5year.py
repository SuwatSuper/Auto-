# -*- coding: utf-8 -*-
"""test_recheck_5year.py — กันถอยหลังการแก้ "ความพร้อม 5 ปี" รอบ 2026-06-22
   (ADR-061 master .bak stub-aware · ADR-062 report retention · ADR-063 utf-8 console)

รันเดี่ยว: PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_recheck_5year.py
ทั้งหมดเป็นการแก้ golden-neutral (ไม่แตะ engine/parser/rules) — เทสนี้ตรวจ "พฤติกรรมการกัน"
ไม่ใช่ผลตรวจ. golden ยืนยันแยกที่ check_invariants.py + regression_full.py.
"""
import os, json, tempfile
os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')

_fail = 0


def _ok(cond, msg):
    global _fail
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        _fail += 1


# ── ADR-061: save_master ต้องไม่เอา stub สำรองทับ .bak ของจริง ──────────────
print('[1] ADR-061 master.save_master รู้จัก stub (กัน .bak กู้คืนของจริงถูกทับ)')
import master
with tempfile.TemporaryDirectory() as d:
    mf = os.path.join(d, 'master_companies.json')
    bak = mf + '.bak'
    _orig = master.CFG
    try:
        master.CFG = dict(_orig); master.CFG['MASTER_FILE'] = mf   # rebind (CFG จริงเป็น mappingproxy)
        real = {'บริษัท ก จำกัด': {'tax_id': '1111111111111'},
                'บริษัท ข จำกัด': {'tax_id': '2222222222222'}}
        # .bak = ของจริง 2 บริษัท
        with open(bak, 'w', encoding='utf-8') as f:
            json.dump(real, f, ensure_ascii=False)
        # live = stub (1 บริษัท + _golden_stub → key count = 2 = ของจริง → เดิมจะทับ)
        stub = {'ฉี อัน คอนสตรัคชั่น จำกัด': {'tax_id': '0105566206726'}, '_golden_stub': True}
        with open(mf, 'w', encoding='utf-8') as f:
            json.dump(stub, f, ensure_ascii=False)
        # ผู้ใช้ save master ใหม่ (ใหญ่กว่า) — เดิม guard นับ key จะ copy stub→.bak ทับของจริง
        master.save_master({'บริษัท ก จำกัด': {'tax_id': '1111111111111'},
                            'บริษัท ข จำกัด': {'tax_id': '2222222222222'},
                            'บริษัท ค จำกัด': {'tax_id': '3333333333333'}})
        with open(bak, 'r', encoding='utf-8') as f:
            bak_after = json.load(f)
        _ok('_golden_stub' not in bak_after, '.bak ไม่ถูก stub ทับ (ไม่มี _golden_stub)')
        _ok('บริษัท ก จำกัด' in bak_after, '.bak ยังเก็บข้อมูลจริง (บริษัท ก)')
    finally:
        master.CFG = _orig

# ── ADR-061b: ของจริงที่ "หด" ยังต้องกัน .bak (พฤติกรรมเดิม ADR-040 ไม่ถอย) ──
print('[2] ADR-040 ยังอยู่: ของจริงหด/ว่าง ไม่ทับ .bak ที่ครบกว่า')
with tempfile.TemporaryDirectory() as d:
    mf = os.path.join(d, 'master_companies.json'); bak = mf + '.bak'
    _orig = master.CFG
    try:
        master.CFG = dict(_orig); master.CFG['MASTER_FILE'] = mf
        big = {'a': {'tax_id': '1'}, 'b': {'tax_id': '2'}, 'c': {'tax_id': '3'}}
        with open(bak, 'w', encoding='utf-8') as f:
            json.dump(big, f, ensure_ascii=False)
        with open(mf, 'w', encoding='utf-8') as f:    # live = ของจริง 1 บริษัท (ไม่ใช่ stub)
            json.dump({'a': {'tax_id': '1'}}, f, ensure_ascii=False)
        master.save_master({})                         # save ว่าง
        with open(bak, 'r', encoding='utf-8') as f:
            _ok(len(json.load(f)) == 3, '.bak ยังครบ 3 (shrink-guard เดิมทำงาน)')
    finally:
        master.CFG = _orig

# ── ADR-062: _prune_old_reports default ปิด / เปิดแล้วลบเฉพาะเก่า ─────────────
print('[3] ADR-062 report retention: default ปิด · เปิดแล้วลบเฉพาะ artifact เก่า')
from pukpui_modular_funcs import _prune_old_reports
with tempfile.TemporaryDirectory() as d:
    old = os.path.join(d, 'audit_v58_20200101_000000.xlsx')
    new = os.path.join(d, 'audit_v58_20260101_000000.xlsx')
    other = os.path.join(d, 'สำคัญห้ามลบ.xlsx')   # ไฟล์ผู้ใช้ ไม่ตรง pattern
    for p in (old, new, other):
        open(p, 'w').close()
    os.utime(old, (1, 1))   # mtime เก่ามาก (1970)
    # default ปิด (0) → ต้องไม่ลบอะไร
    _prune_old_reports(d, '0')
    _ok(os.path.exists(old), 'default ปิด: ไฟล์เก่ายังอยู่ (พฤติกรรมเดิม)')
    # เปิด 30 วัน → ลบ old, เก็บ new + ไฟล์ผู้ใช้
    _prune_old_reports(d, '30')
    _ok(not os.path.exists(old), 'เปิด retention: ลบไฟล์เก่า audit_v58_ ปี 2020')
    _ok(os.path.exists(new), 'เก็บไฟล์ audit_v58_ ใหม่ไว้')
    _ok(os.path.exists(other), 'ไม่แตะไฟล์ผู้ใช้ที่ไม่ตรง pattern')

# ── ADR-063: _ensure_utf8_console ต้องไม่ throw + idempotent ─────────────────
print('[4] ADR-063 utf-8 console: เรียกแล้วไม่ crash + เรียกซ้ำได้')
import importlib
M = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
try:
    M._ensure_utf8_console(); M._ensure_utf8_console()
    _ok(True, '_ensure_utf8_console() เรียกซ้ำได้ ไม่ throw')
except Exception as e:
    _ok(False, f'_ensure_utf8_console crash: {type(e).__name__}: {e}')

print('=' * 56)
if _fail:
    print(f'RESULT: ❌ FAIL {_fail} จุด'); raise SystemExit(1)
print('RESULT: ✅ PASS — การแก้ 5-year (ADR-061/062/063) ครบ + ของเดิมไม่ถอย')
