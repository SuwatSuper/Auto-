# -*- coding: utf-8 -*-
"""
test_run_addon_pack_guard.py — tripwire ล็อกการแก้ bug `run_addon_pack` (v9.2)

บริบท:
  - `run_addon_pack` ไม่เคยถูก port เข้า modular (ไม่มี def/import ใดผูกชื่อนี้)
  - เดิม monolith เรียกตรง ๆ ที่ main() (โหมดเต็ม, LEAN_REPORT=False)
    → NameError ทันทีหลัง export_excel สำเร็จ → ทั้งรอบพังก่อนถึง verification/analytics
  - import * บังจาก linter (เป็นแค่ F405 ไม่ใช่ F821) จึงไม่ถูกจับ
  - agents/report_agent.py จัดมันเป็น "shoulder feature" (optional + พังไม่ล้มรายงานหลัก) อยู่แล้ว
  - การแก้: ทำให้ monolith สอดคล้องกับสัญญาเดียวกัน (optional getattr + try/except)

เทสนี้พิสูจน์/ล็อก:
  1. landmine หาย — ไม่มีการเรียก `run_addon_pack(` แบบ unguarded ใน monolith อีก
  2. monolith ใช้ optional lookup `globals().get('run_addon_pack')`
  3. agent path ใช้สัญญา optional เดียวกัน (`core.get("run_addon_pack")`)
  4. runtime: `run_addon_pack` ยัง "ไม่ผูก" จริง → การ guard เป็นรูปแบบที่ถูกต้อง (ไม่ใช่ over-engineering)

รันแบบ standalone (ไม่แตะ engine source):
    python3 test_run_addon_pack_guard.py
"""
import io
import os
import re
import sys
import contextlib
import importlib

HERE = os.path.dirname(os.path.abspath(__file__))
MONOLITH = os.path.join(HERE, 'ปุ้มปุ้ย_ultimate_v9_modular.py')
REPORT_AGENT = os.path.join(HERE, 'agents', 'report_agent.py')

_fail = 0


def _check(cond, ok_msg, bad_msg):
    global _fail
    if cond:
        print(f'  ✅ {ok_msg}')
    else:
        print(f'  ❌ {bad_msg}')
        _fail += 1


def _strip_comments(src: str) -> str:
    """ตัดบรรทัดคอมเมนต์ (เริ่มด้วย #) ออก เพื่อไม่ให้ comment-mention ทำให้ regex หลอก"""
    out = []
    for line in src.splitlines():
        s = line.lstrip()
        if s.startswith('#'):
            continue
        # ตัด inline comment แบบหยาบ (พอสำหรับ static check ของ call pattern)
        out.append(line.split('#', 1)[0])
    return '\n'.join(out)


print('=' * 64)
print('TRIPWIRE — run_addon_pack guard (v9.2 stability fix)')
print('=' * 64)

mono_src = open(MONOLITH, encoding='utf-8').read()
mono_code = _strip_comments(mono_src)
agent_src = open(REPORT_AGENT, encoding='utf-8').read()
agent_code = _strip_comments(agent_src)

# (1) ไม่มี unguarded direct call `run_addon_pack(` ในโค้ด (นอกคอมเมนต์)
direct_calls = re.findall(r'(?<![.\'"])\brun_addon_pack\s*\(', mono_code)
_check(
    len(direct_calls) == 0,
    'ไม่มีการเรียก run_addon_pack( แบบ unguarded ใน monolith (landmine หาย)',
    f'ยังพบ direct call run_addon_pack( {len(direct_calls)} จุด — NameError landmine กลับมา!',
)

# (2) monolith ใช้ optional lookup globals().get('run_addon_pack')
_check(
    "globals().get('run_addon_pack')" in mono_code
    or 'globals().get("run_addon_pack")' in mono_code,
    "monolith ใช้ optional lookup globals().get('run_addon_pack')",
    "monolith ไม่พบ optional lookup globals().get('run_addon_pack')",
)

# (3) agent path ใช้สัญญา optional เดียวกัน
_check(
    'core.get("run_addon_pack")' in agent_code
    or "core.get('run_addon_pack')" in agent_code,
    'agents/report_agent.py ใช้สัญญา optional เดียวกัน (core.get run_addon_pack)',
    'agents/report_agent.py ไม่ใช้ optional contract เดิม (สัญญาเพี้ยน)',
)

# (4) runtime: run_addon_pack ยังไม่ถูกผูกใน monolith namespace → guard เป็นรูปแบบที่ถูกต้อง
sys.path.insert(0, HERE)
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    m = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
bound = hasattr(m, 'run_addon_pack')
_check(
    not bound,
    'runtime: run_addon_pack ยัง unbound จริง → optional guard เป็นรูปแบบที่ถูกต้อง',
    'runtime: run_addon_pack ถูกผูกแล้ว — ถ้าตั้งใจ port มา ให้ปรับ guard/เทสนี้ตามจริง',
)

print('-' * 64)
if _fail == 0:
    print('RESULT: ✅ PASS — run_addon_pack ถูก guard เป็น shoulder feature สอดคล้องทั้งระบบ')
    sys.exit(0)
else:
    print(f'RESULT: ❌ FAIL — {_fail} ข้อ')
    sys.exit(1)
