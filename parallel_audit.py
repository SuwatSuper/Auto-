# -*- coding: utf-8 -*-
"""parallel_audit.py — OBJ-PERF (ADR-009): parse ไฟล์แบบขนาน (process pool) ผลเท่า serial เป๊ะ.

ADDITIVE / opt-in: **ไม่แตะ** parse_all_files เดิม. แต่ละ worker เรียก parse_all_files (ตัวเดิม)
บน "chunk ต่อเนื่อง" ของ file_list แล้ว parent merge ตามลำดับ chunk (= ลำดับ file_list).

ทำไม merge ตรง serial:
  • all_bills / filename_issues — ต่อกันตามลำดับไฟล์ (parse_all_files รักษาลำดับในแต่ละ chunk)
  • _SYSTEM_ISSUES — dedup key = (code, file, sheet, exc/name) **มี file** → คนละไฟล์คนละ key
    → dedup ภายใน worker = dedup ทั้งระบบ (ไม่มี dup ข้าม worker) → ต่อกันตามลำดับไฟล์พอ
  • _TEXT_NUM_RECOVERIES — ต่อกันตามลำดับ + เคารพ cap รวม (_MAX_TEXT_NUM_RECOVERIES)

determinism: ตั้ง PYTHONHASHSEED=0 ก่อนรัน (fork สืบทอด hash seed ของ parent) + merge ตามลำดับ
→ ไม่ขึ้นกับลำดับเสร็จของ worker. พิสูจน์ serial==parallel ด้วย golden digest + det-report-hash.
"""
import os
import importlib
from concurrent.futures import ProcessPoolExecutor

_APP_MOD = 'ปุ้มปุ้ย_ultimate_v9_modular'


def _worker(chunk):
    """parse chunk หนึ่งในโปรเซสลูก — reset state ของตัวเอง แล้วคืน bills/issues snapshot."""
    import state
    app = importlib.import_module(_APP_MOD)
    app.reset_run_state()
    bills, filename_issues = app.parse_all_files(chunk)
    return bills, filename_issues, list(state._SYSTEM_ISSUES), list(state._TEXT_NUM_RECOVERIES)


def parse_all_files_parallel(file_list, workers=None):
    """drop-in แทน parse_all_files แบบขนาน — คืน (all_bills, filename_issues) เท่า serial เป๊ะ.

    workers: จำนวนโปรเซส (ดีฟอลต์ = os.cpu_count()). ตั้ง >1 เพื่อทดสอบ merge แม้ CPU เดียว.
    """
    import state
    app = importlib.import_module(_APP_MOD)
    file_list = list(file_list)
    if not file_list:
        app.reset_run_state()
        return [], []

    n = workers or (os.cpu_count() or 1)
    n = max(1, min(n, len(file_list)))
    k = (len(file_list) + n - 1) // n
    chunks = [file_list[i:i + k] for i in range(0, len(file_list), k)]   # ต่อเนื่อง → รักษาลำดับ

    with ProcessPoolExecutor(max_workers=n) as ex:
        results = list(ex.map(_worker, chunks))   # ex.map รักษาลำดับ input

    # merge ในโปรเซสแม่ ตามลำดับ chunk (= ลำดับ file_list)
    app.reset_run_state()
    all_bills = []
    filename_issues = []
    cap = getattr(state, '_MAX_TEXT_NUM_RECOVERIES', 20000)
    for bills, fi, sys_issues, text_num in results:
        all_bills.extend(bills)
        filename_issues.extend(fi)
        state._SYSTEM_ISSUES.extend(sys_issues)      # ไม่มี dup ข้าม worker (dk มี file)
        for rec in text_num:
            if len(state._TEXT_NUM_RECOVERIES) >= cap:
                break
            state._TEXT_NUM_RECOVERIES.append(rec)
    # rebuild SEEN จาก issues ที่ merge แล้ว (กัน re-log ซ้ำในเฟสหลัง parse เท่าที่ทำได้)
    for iss in state._SYSTEM_ISSUES:
        state._SYSTEM_ISSUE_SEEN.add((iss.get('code'), iss.get('file'), iss.get('sheet'), iss.get('name')))
    return all_bills, filename_issues
