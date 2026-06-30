# -*- coding: utf-8 -*-
"""conftest.py — ทำให้ `pytest` รันชุดเทสของโปรเจกต์ได้ "โดยไม่แตะไฟล์เทสเลย"

ปัญหา (#2 maintainability debt): ไฟล์เทสของระบบนี้เป็น **standalone script** (รันด้วย
`python3 test_x.py`) มี execution + `sys.exit()` ที่ระดับ module. ถ้า pytest พยายาม *import*
มาเป็น test module → โค้ดรันตอน collect แล้ว `sys.exit()` ทำ pytest **ครัชทั้ง session**
(INTERNALERROR: caught unexpected SystemExit). นี่คือเหตุที่ `pytest` ใช้ไม่ได้มาแต่เดิม.

ทางแก้ (zero-touch, low-risk): แทนที่จะ rewrite ~38 ไฟล์ (เสี่ยง + ขัดกฎ "ไม่แตะ logic เทส")
→ ใช้ **custom collector** ที่ "รันแต่ละสคริปต์เป็น subprocess" (พฤติกรรมเดียวกับ run_ci.sh เป๊ะ)
แล้วถือว่า exit 0 = ผ่าน. pytest จึง **ไม่เคย import** ไฟล์เทส → module-level sys.exit ไม่กระทบ collect อีก.

คู่กับ pyproject `[tool.pytest.ini_options] python_files` ที่ปิด builtin python-collector ของไฟล์เหล่านี้.
ไม่กระทบ run_ci.sh / golden / business logic เลย (conftest ถูกโหลดเฉพาะตอนรัน pytest เท่านั้น;
run_ci.sh ไม่เรียก pytest).
"""
import os
import sys
import subprocess

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))

# สคริปต์เทสที่ต้องการ args ให้ตรงกับ run_ci.sh (ที่เหลือรัน bare เหมือน run_ci.sh)
#   test_agents.py default DATA=/mnt/project (ไม่มีใน CI) → ต้องชี้ fixtures
_ARGS = {
    "test_agents.py": [".", "tests/fixtures"],
    "test_agent_conformance.py": ["."],
}

# สคริปต์ที่ "ชื่อเข้าเกณฑ์" แต่ run_ci.sh จงใจไม่รัน → pytest ก็ต้องไม่รัน (ให้ชุด == run_ci.sh)
#   e2e_test.py: e2e harness ที่ hard-glob /mnt/project (ไม่มีใน CI/sandbox) — ใช้กับข้อมูลจริงเท่านั้น
_EXCLUDE = {"e2e_test.py"}


def _is_script_test(name: str) -> bool:
    if name in _EXCLUDE:
        return False
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def pytest_collect_file(parent, file_path):
    """ดัก test_*.py / *_test.py → ให้ ScriptFile (รัน subprocess) แทน builtin python import."""
    if _is_script_test(file_path.name):
        return ScriptFile.from_parent(parent, path=file_path)
    return None


class ScriptFile(pytest.File):
    def collect(self):
        yield ScriptItem.from_parent(self, name=self.path.name)


class _ScriptFail(Exception):
    def __init__(self, name, rc, out, err):
        super().__init__(f"{name} exited {rc}")
        self.name, self.rc, self.out, self.err = name, rc, out, err

    def report(self) -> str:
        out = (self.out or "")[-2500:]
        err = (self.err or "")[-1200:]
        return f"[{self.name}] exit code {self.rc}\n--- stdout (tail) ---\n{out}\n--- stderr (tail) ---\n{err}"


class ScriptItem(pytest.Item):
    def runtest(self):
        env = dict(os.environ)
        env.setdefault("PYTHONHASHSEED", "0")          # invariant — ตรงกับ run_ci.sh / golden
        env.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
        args = _ARGS.get(self.path.name, [])
        r = subprocess.run(
            [sys.executable, str(self.path), *args],
            capture_output=True, text=True, env=env, cwd=_HERE,
        )
        if r.returncode != 0:
            raise _ScriptFail(self.path.name, r.returncode, r.stdout, r.stderr)

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, _ScriptFail):
            return excinfo.value.report()
        return super().repr_failure(excinfo)

    def reportinfo(self):
        return self.path, 0, f"script: {self.path.name}"
