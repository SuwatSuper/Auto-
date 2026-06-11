# -*- coding: utf-8 -*-
"""verify_parallel.py — พิสูจน์ parse_all_files_parallel == parse_all_files (serial) เป๊ะ.
ใช้: PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_parallel.py [DATA_DIR] [WORKERS]
ตรวจ: golden digest (bills+audit-core) + จำนวน system_issues/text_num + ลำดับ → ต้องตรง serial.
WORKERS>1 บังคับให้เกิดการ merge หลาย chunk แม้ CPU เดียว (ทดสอบ logic merge).
"""
import warnings; warnings.filterwarnings('ignore')
import os, sys, glob, contextlib, io
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
DATA = sys.argv[1] if len(sys.argv) > 1 else '/mnt/project'
WORKERS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
from golden_snapshot import MASTER, snapshot_and_hash, write_master_file
write_master_file('master_companies.json')
import importlib, state
app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
from parallel_audit import parse_all_files_parallel
fl = sorted(glob.glob(os.path.join(DATA, '*.xls')) + glob.glob(os.path.join(DATA, '*.xlsx')))

def pipeline(bills, fi):
    for b in bills: app.compute_bill_confidence(b)
    core = app.run_audit_core(bills, MASTER, isolate=True)
    _, dig = snapshot_and_hash(fl, bills, fi, core['dup_items'], core['iv_seq'],
                               core['iv_date'], core['typos'], core['summary'])
    return dig

with contextlib.redirect_stdout(io.StringIO()):
    app.reset_run_state(); b_s, fi_s = app.parse_all_files(fl)
    si_s, tn_s = list(state._SYSTEM_ISSUES), list(state._TEXT_NUM_RECOVERIES); dig_s = pipeline(b_s, fi_s)
    b_p, fi_p = parse_all_files_parallel(fl, workers=WORKERS)
    si_p, tn_p = list(state._SYSTEM_ISSUES), list(state._TEXT_NUM_RECOVERIES); dig_p = pipeline(b_p, fi_p)

ok = (dig_s == dig_p and si_s == si_p and tn_s == tn_p and len(b_s) == len(b_p))
print(f'files={len(fl)} workers={WORKERS}')
print(f'serial   : bills={len(b_s)} sys_issues={len(si_s)} text_num={len(tn_s)} golden={dig_s}')
print(f'parallel : bills={len(b_p)} sys_issues={len(si_p)} text_num={len(tn_p)} golden={dig_p}')
print('RESULT:', '✅ serial==parallel (golden+issues+recoveries ตรงเป๊ะ)' if ok else '❌ ต่าง — อย่าใช้ parallel จนกว่าจะแก้')
sys.exit(0 if ok else 1)
