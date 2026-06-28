# -*- coding: utf-8 -*-
"""parallel_audit.py — OBJ-PERF (ADR-009): parse ไฟล์แบบขนาน (process pool) ผลเท่า serial เป๊ะ.

ADDITIVE / opt-in: **ไม่แตะ** parse_all_files เดิม. แต่ละ worker เรียก parse_all_files (ตัวเดิม)
บน "chunk ต่อเนื่อง" ของ file_list แล้ว parent merge ตามลำดับ chunk (= ลำดับ file_list).

ทำไม merge ตรง serial:
  • all_bills / filename_issues — ต่อกันตามลำดับไฟล์ (parse_all_files รักษาลำดับในแต่ละ chunk)
  • _SYSTEM_ISSUES — parent dedup ด้วย "key จริงของ logger" (code, file, sheet, exc-type/name)
    ที่ worker คืนมาผ่าน _SYSTEM_ISSUE_KEYS → เลียน serial เป๊ะ แม้มี key ที่ file=None ซ้ำข้าม worker
    (ไม่ reconstruct key จาก dict — dict ไม่เก็บ exc-type; การ reconstruct เดิมจึงผิดสำหรับ exc-issue)
  • _TEXT_NUM_RECOVERIES — ต่อกันตามลำดับ + เคารพ cap รวม (config._MAX_TEXT_NUM_RECOVERIES)

determinism: typo ordering เป็น hash-seed-sensitive → บังคับ PYTHONHASHSEED=0 (assert ใน
parse_all_files_parallel; ครอบทั้ง fork ที่สืบทอด env และ spawn/forkserver ที่อ่าน env ใหม่) +
pin start method (fork ถ้ามี) + merge ตามลำดับ chunk → ไม่ขึ้นกับลำดับเสร็จของ worker.
พิสูจน์ serial==parallel ด้วย golden digest + det-report-hash (CI [8c]) และ unit-test _merge_results.
"""
import os
import sys
import importlib
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor

_APP_MOD = 'ปุ้มปุ้ย_ultimate_v9_modular'


def _worker(chunk):
    """parse chunk หนึ่งในโปรเซสลูก — reset state ของตัวเอง แล้วคืน bills/issues snapshot.

    คืน _SYSTEM_ISSUE_KEYS (key จริงของ logger รวม exc-type) มาด้วย เพื่อให้ parent merge
    dedup ข้าม worker ได้ตรง serial — ไม่ reconstruct key จาก dict (ซึ่งไม่มี exc-type).
    """
    import state
    app = importlib.import_module(_APP_MOD)
    app.reset_run_state()
    bills, filename_issues = app.parse_all_files(chunk)
    return (bills, filename_issues,
            list(state._SYSTEM_ISSUES), list(state._SYSTEM_ISSUE_KEYS),
            list(state._TEXT_NUM_RECOVERIES))


def _merge_results(results):
    """รวมผล worker ตามลำดับ chunk (= ลำดับ file_list) ให้ผลเท่า serial เป๊ะ.

    mutate state (_SYSTEM_ISSUES/_SYSTEM_ISSUE_SEEN/_SYSTEM_ISSUE_KEYS/_TEXT_NUM_RECOVERIES)
    แล้วคืน (all_bills, filename_issues). แยกออกมาเป็นฟังก์ชันล้วนเพื่อ **unit-test path ที่เสี่ยง
    สุด** (dedup system-issue ข้าม worker + cap text_num) ได้โดยไม่ต้อง spawn และไม่พึ่ง corpus
    ที่บังเอิญสะอาด (sys_issues=0) ซึ่งทำให้ verify_parallel ผ่านแบบ vacuous.

    contract ต่อ result: (bills, filename_issues, sys_issues, sys_keys, text_num)
      • sys_keys = dedup key จริงของ logger (รวม exc-type) เรียงตรงกับ sys_issues 1:1
    """
    import state
    from config import _MAX_TEXT_NUM_RECOVERIES as _CAP   # [FIX-cap] cap อยู่ใน config ไม่ใช่ state
    app = importlib.import_module(_APP_MOD)
    app.reset_run_state()        # ล้าง trail/SEEN/KEYS/text_num ก่อน merge (.clear() คง identity)
    all_bills = []
    filename_issues = []
    for bills, fi, sys_issues, sys_keys, text_num in results:
        all_bills.extend(bills)
        filename_issues.extend(fi)
        # [FIX#3/#4a] dedup ด้วย "key จริง" จาก worker → เลียน serial เป๊ะ:
        #   • กัน dup ข้าม worker สำหรับ key ที่ file=None (เดิม blind extend → นับซ้ำ)
        #   • ใช้ exc-type ที่ logger ใช้จริง (เดิม rebuild จาก dict ที่ไม่มี exc-type → key ผิด)
        for iss, key in zip(sys_issues, sys_keys):
            if key in state._SYSTEM_ISSUE_SEEN:
                continue
            state._SYSTEM_ISSUE_SEEN.add(key)
            state._SYSTEM_ISSUES.append(iss)
            state._SYSTEM_ISSUE_KEYS.append(key)
        # text_num: ต่อกันตามลำดับ chunk + เคารพ cap รวมจาก config (worker เก็บเป็น prefix อยู่แล้ว
        #   → global prefix ตามลำดับไฟล์ = serial เป๊ะ)
        for rec in text_num:
            if len(state._TEXT_NUM_RECOVERIES) >= _CAP:
                break
            state._TEXT_NUM_RECOVERIES.append(rec)
    return all_bills, filename_issues


def parse_all_files_parallel(file_list, workers=None):
    """drop-in แทน parse_all_files แบบขนาน — คืน (all_bills, filename_issues) เท่า serial เป๊ะ.

    workers: จำนวนโปรเซส (ดีฟอลต์ = os.cpu_count()). ตั้ง >1 เพื่อทดสอบ merge แม้ CPU เดียว.
    """
    import state
    app = importlib.import_module(_APP_MOD)

    # [FIX#1 DETERMINISM] typo ordering เป็น hash-seed-sensitive → ทุก worker ต้องใช้ seed=0:
    #   fork สืบทอด state ของ parent; spawn/forkserver อ่าน PYTHONHASHSEED ใหม่จาก env →
    #   ทั้งสองกรณีต้องมี PYTHONHASHSEED=0 "ใน env จริง" มิฉะนั้น serial≠parallel เงียบ
    #   (golden เป็น serial-only จับไม่ได้). ปฏิเสธชัด ๆ ดีกว่าผลที่ reproduce ไม่ได้
    #   — monolith ครอบ try/except อยู่แล้ว จะ fallback→serial ให้เอง.
    # [M7] เช็ค "ผลจริง" ไม่ใช่แค่ค่า env: ภายใต้ fork ลูกสืบทอด hash-seed ของ parent ที่อาจสุ่มอยู่
    #   แม้ env ถูกตั้งภายหลัง. sys.flags.hash_randomization == 0 ก็ต่อเมื่อ interpreter ถูกสตาร์ท
    #   ด้วย PYTHONHASHSEED=0 จริง → กัน serial≠parallel เงียบ (golden เป็น serial-only จับไม่ได้).
    if sys.flags.hash_randomization or os.environ.get('PYTHONHASHSEED') != '0':
        raise RuntimeError(
            'parse_all_files_parallel ต้องการ PYTHONHASHSEED=0 ตั้งก่อนเปิด interpreter '
            '(typo ordering เป็น hash-seed-sensitive) — export PYTHONHASHSEED=0 ก่อนรัน หรือใช้ serial path แทน')

    file_list = list(file_list)
    if not file_list:
        app.reset_run_state()
        return [], []

    n = workers or (os.cpu_count() or 1)
    n = max(1, min(n, len(file_list)))   # อนุญาต over-subscribe (n>cpu) โดยตั้งใจ: ให้เทสต์ merge
                                         #   หลาย chunk ได้แม้ CPU เดียว (อย่า clamp ด้วย cpu_count)
    k = (len(file_list) + n - 1) // n
    chunks = [file_list[i:i + k] for i in range(0, len(file_list), k)]   # ต่อเนื่อง → รักษาลำดับ

    # [FIX#1] pin start method ให้พฤติกรรมเสถียรข้าม Python version (3.14 เปลี่ยน default→forkserver).
    #   ใช้ fork ถ้ามี (Linux/CI); det มาจาก env-guard ด้านบนแล้ว จึงปลอดภัยแม้ระบบไม่มี fork.
    try:
        _ctx = mp.get_context('fork')
    except ValueError:
        _ctx = mp.get_context()

    with ProcessPoolExecutor(max_workers=n, mp_context=_ctx) as ex:
        results = list(ex.map(_worker, chunks))   # ex.map รักษาลำดับ input

    return _merge_results(results)
