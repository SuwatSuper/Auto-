# -*- coding: utf-8 -*-
"""test_adr135_mesh_reset.py — [ADR-135] Orchestrator.run() เริ่ม mesh สะอาดทุกครั้ง (กัน state leak).

บั๊ก: run() เดิม `if ctx.mesh is None: ctx.mesh = FindingsMesh()` ; `reset_run_state()` ไม่แตะ
ctx.mesh. mesh append-only (publish→append) → "ใช้ ctx ซ้ำ" ข้าม run() 2 รอบ → findings สะสมซ้ำ
(fixture: 29→59) = state leak ข้ามการรัน. แก้: run() สร้าง mesh ใหม่เสมอ (run() = full pipeline).

ตรึง: run() 2 รอบบน ctx เดียวกัน → mesh count เท่ากัน (idempotent). golden-neutral (mesh = advisory,
ไม่อยู่ใน snapshot ; agent==engine ยืนยันแยก). รันบน fixtures (ไม่ต้องข้อมูลจริง).
"""
import os
import sys
import glob
import io
import contextlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def main():
    from agents.orchestrator import Orchestrator
    from agents.contracts import PipelineContext

    files = sorted(glob.glob(os.path.join(os.path.dirname(__file__), 'tests', 'fixtures', '*.xlsx')))
    _check(bool(files), f'พบ fixture xlsx ({len(files)})')

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ctx = PipelineContext(master={}, file_list=files,
                              options={'write_report': False, 'enable_ai': False})
        orch = Orchestrator(logger=lambda m: None)
        orch.run(ctx)
        n1 = ctx.mesh.count()
        bills1 = len(ctx.bills)
        orch.run(ctx)              # ใช้ ctx ซ้ำ (full run รอบ 2)
        n2 = ctx.mesh.count()
        bills2 = len(ctx.bills)

    print(f'  mesh count: run1={n1}  run2(same ctx)={n2}')
    _check(n1 > 0, 'run1 มี findings (pipeline ทำงานจริง)')
    _check(n2 == n1, f'run2 mesh เท่า run1 ({n2}=={n1}) — ไม่สะสมซ้ำ (state leak ปิด)')
    _check(bills2 == bills1, f'จำนวนบิลคงที่ ({bills2}=={bills1}) — reset_run_state ทำงาน')

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — run() เริ่ม mesh สะอาดทุกครั้ง ; รัน 2 รอบ ctx เดียว ผลเท่ากัน')
    return 0


if __name__ == '__main__':
    sys.exit(main())
