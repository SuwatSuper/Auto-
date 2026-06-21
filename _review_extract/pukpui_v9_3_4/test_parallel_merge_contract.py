# -*- coding: utf-8 -*-
"""test_parallel_merge_contract.py — [ADR-PMERGE] regression gate ของ parallel merge.

ยิงเข้า parallel_audit._merge_results "โดยตรง" (production path) ครอบ 3 จุดที่ corpus อ้างอิง
สะอาด (sys_issues=0 / text_num=0) ทำให้ verify_parallel ผ่านแบบ vacuous — gate นี้จึงปิดช่องนั้น:

  [#3]   exc-based system issue  : SEEN key ต้องรวม exc-type จริง (เดิม rebuild จาก dict → key ผิด
                                   → re-log ซ้ำในเฟสหลัง parse → serial≠parallel เงียบ)
  [#4a]  file=None ซ้ำข้าม worker : ต้อง dedup เหลือเท่า serial (เดิม blind extend → นับซ้ำ)
  [#cap] text_num cap            : ต้องอ่านจาก config (เดิม getattr(state,…) → fallback 20000 เสมอ)

ground truth = serial: log ชุดเดียวกันในรอบ reset เดียว แล้วเทียบ count + SEEN set.
ใช้ REAL diagnostics logger (key เป็นของจริงรวม exc-type) — ไม่ mock.

รัน: PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_parallel_merge_contract.py
exit code 0 = ผ่าน, 1 = มี check ตก (ใช้ใน run_ci.sh / ci.yml).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import state            # noqa: E402
import diagnostics      # noqa: E402
import config           # noqa: E402
from parallel_audit import _merge_results   # noqa: E402

_FAILS = []


def check(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        _FAILS.append(name)


def _reset_local():
    diagnostics.system_issues_reset()
    state._TEXT_NUM_RECOVERIES.clear()


def _worker_payload(log_calls=(), recoveries=()):
    """จำลอง worker หนึ่งตัว: reset → log ผ่าน REAL logger → คืน 5-tuple แบบ _worker คืนจริง."""
    _reset_local()
    for kw in log_calls:
        diagnostics.log_system_issue(echo=False, **kw)
    for rec in recoveries:
        state._TEXT_NUM_RECOVERIES.append(rec)
    return ([], [],
            list(state._SYSTEM_ISSUES), list(state._SYSTEM_ISSUE_KEYS),
            list(state._TEXT_NUM_RECOVERIES))


def _serial_seen(all_calls):
    """ground truth: log ทุก call ในรอบ reset เดียว (= พฤติกรรม serial) → (count, SEEN set)."""
    _reset_local()
    for kw in all_calls:
        diagnostics.log_system_issue(echo=False, **kw)
    return len(state._SYSTEM_ISSUES), set(state._SYSTEM_ISSUE_SEEN)


def main():
    print("=" * 70)
    print("TEST parallel _merge_results — guards: #3 exc-key / #4a file=None / #cap")
    print("=" * 70)

    # ── #3 — exc-based key ต้องตรง serial (รวม exc-type, ไม่ใช่ name) ─────────────
    call_exc = dict(code='SYS001', name='Sheet Parsing Failure',
                    file='KRR_69_012.xls', sheet='Sheet1', exc=ValueError('bad cell'))
    w0 = _worker_payload([call_exc])
    ser_n, ser_seen = _serial_seen([call_exc])
    _merge_results([w0])
    check("#3 SEEN key has real exc-type 'ValueError' (not the issue name)",
          ('SYS001', 'KRR_69_012.xls', 'Sheet1', 'ValueError') in state._SYSTEM_ISSUE_SEEN)
    check("#3 merged SEEN == serial SEEN", state._SYSTEM_ISSUE_SEEN == ser_seen)
    check("#3 merged issue count == serial", len(state._SYSTEM_ISSUES) == ser_n == 1)
    check("#3 _SYSTEM_ISSUE_KEYS aligned 1:1 with _SYSTEM_ISSUES",
          len(state._SYSTEM_ISSUE_KEYS) == len(state._SYSTEM_ISSUES))

    # ── #3b — exc-key suppresses a later re-log (เฟสหลัง parse) เหมือน serial ────
    #   หลัง merge มี SEEN ที่ถูกต้องแล้ว → log ซ้ำ (code,file,sheet,exc-type) เดิม ต้องถูก suppress
    before = len(state._SYSTEM_ISSUES)
    diagnostics.log_system_issue(echo=False, code='SYS001', name='Sheet Parsing Failure',
                                 file='KRR_69_012.xls', sheet='Sheet1',
                                 exc=ValueError('encountered again'))
    after = len(state._SYSTEM_ISSUES)
    check("#3b post-merge re-log of same exc-key is suppressed (no dup)", after == before)

    # ── #4a — file=None ซ้ำข้าม 2 worker ต้อง dedup เหลือ 1 (= serial) ───────────
    call_none = dict(code='SYS050', name='Global Warning', file=None)
    wA = _worker_payload([call_none])
    wB = _worker_payload([call_none])
    ser_n2, ser_seen2 = _serial_seen([call_none, call_none])
    _merge_results([wA, wB])
    check("#4a file=None dup across workers deduped to serial count (=1)",
          len(state._SYSTEM_ISSUES) == ser_n2 == 1)
    check("#4a merged SEEN == serial SEEN", state._SYSTEM_ISSUE_SEEN == ser_seen2)

    # ── #4b — distinct file issues ต้อง "ไม่" ถูก dedup (กัน over-dedup) ─────────
    cf1 = dict(code='SYS001', name='File Open Failure', file='A.xls', exc=OSError('x'))
    cf2 = dict(code='SYS001', name='File Open Failure', file='B.xls', exc=OSError('x'))
    wP = _worker_payload([cf1])
    wQ = _worker_payload([cf2])
    sn, ss = _serial_seen([cf1, cf2])
    _merge_results([wP, wQ])
    check("#4b distinct-file issues preserved (count == serial == 2)",
          len(state._SYSTEM_ISSUES) == sn == 2)
    check("#4b merged SEEN == serial SEEN", state._SYSTEM_ISSUE_SEEN == ss)

    # ── #cap — cap ต้องมาจาก config (monkeypatch=5 เพื่อเผยบั๊ก hardcoded-20000) ──
    _orig = config._MAX_TEXT_NUM_RECOVERIES
    try:
        config._MAX_TEXT_NUM_RECOVERIES = 5
        wX = _worker_payload(recoveries=[{'i': i, 'w': 'X'} for i in range(4)])
        wY = _worker_payload(recoveries=[{'i': i, 'w': 'Y'} for i in range(4)])  # total 8 > cap
        _merge_results([wX, wY])
        check("#cap merge honors config cap (=5), not hardcoded 20000",
              len(state._TEXT_NUM_RECOVERIES) == 5)
        # serial-equivalent prefix: 4 จาก X + 1 จาก Y (ตามลำดับ chunk)
        kept = state._TEXT_NUM_RECOVERIES
        check("#cap kept = global prefix ตามลำดับ chunk (4×X + 1×Y)",
              [r['w'] for r in kept] == ['X', 'X', 'X', 'X', 'Y'])
    finally:
        config._MAX_TEXT_NUM_RECOVERIES = _orig

    # ── #empty — results ว่าง ต้องไม่ระเบิด + state สะอาด ───────────────────────
    _merge_results([])
    check("#empty merge of [] → no issues, no recoveries",
          len(state._SYSTEM_ISSUES) == 0 and len(state._TEXT_NUM_RECOVERIES) == 0)

    print("-" * 70)
    if _FAILS:
        print(f"❌ FAIL: {len(_FAILS)} check ตก → {_FAILS}")
        return 1
    print("✅ PASS — parallel merge ครบทุก guard (#3 / #4a / #cap) ตรง serial")
    return 0


if __name__ == '__main__':
    sys.exit(main())
