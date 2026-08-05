# -*- coding: utf-8 -*-
"""test_reachability.py — KEYSTONE GUARD (A1+A2): ฆ่า "floating module" + "CI เขียวบนโค้ดตาย" ถาวร

ราก: งานที่ผ่านมาเคยมี (ก) โค้ดที่ถูกแต่ไม่ถูก wire เข้า production (floating) (ข) เทสที่เขียวบน
โค้ดตาย (เช่น test_puopuy_ingest ทดสอบ adapter ที่ไม่มีใครเรียก). เทสนี้ทำให้ทั้งสองอย่าง
"merge ไม่ผ่าน" โดยวิเคราะห์ import-closure แบบ static (AST — ไม่ import จริง, ไม่กระทบ golden).

A1 REACHABILITY: ทุกโมดูล non-test ต้อง reachable จาก entrypoint จริง
    (ปุ้มปุ้ย_ultimate_v9_modular / main / run_agents) + dynamic agent load (agents/__init__:_LAZY)
    หรืออยู่ใน ALLOWLIST (standalone tools ที่มี __main__ ของตัวเอง / test-support).
    โมดูลที่ "ไม่มีใครในกราฟ production เรียก" และไม่อยู่ allowlist = floating → FAIL.

A2 CI↔PRODUCTION LINKAGE: ทุก test_*.py ต้อง import โมดูลที่อยู่ในกราฟ reachable อย่างน้อย 1 ตัว
    (กันเทสที่ทดสอบเฉพาะโค้ดตาย → CI เขียวลวง).

static (AST) ล้วน — ไม่ execute โมดูล, hash ไม่ขยับ. exit 0 = ผ่าน, 1 = พบ floating/dead-test.
"""
import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# entrypoint จริงของระบบ (root ของกราฟ production)
ENTRYPOINTS = ["ปุ้มปุ้ย_ultimate_v9_modular", "main", "run_agents"]

# standalone tools — แต่ละตัวมี __main__ ของตัวเอง (เป็น entry ของมันเอง ไม่ถูก entry หลัก import)
ALLOWLIST_TOOLS = {
    "verify_golden", "smoke_test", "golden_master", "regression_full", "regression_oracle",
    "doctor", "diagnose_merged_cells", "parse_canary", "coverage_gate", "profile_baseline",
    "verify_parallel", "verify_report_det", "build_consolidated_report", "เพิ่ม_master", "e2e_test",
    "_audit_iv_truth",   # [8d] ตรวจ iv-number ตรงเซลล์จริง (อิสระจาก golden) — standalone, มี __main__
    "make_release",      # [ADR-053] ประตูปล่อยแพ็กเกจ (build→extract→verify→hash gate) — standalone CLI, มี __main__
    "verify_corpus_manifest",  # [ADR-158] แยก data-drift ↔ code-drift — standalone CLI, มี __main__
    "sanitize_for_sharing",    # [ADR-159] สร้างแพ็ก shareable ปลอด PII — standalone CLI, มี __main__
    "machine_check",           # [ADR-163] เช็คเครื่องใหม่/ซ้อมกู้ (stdlib ล้วน) — standalone CLI, มี __main__
    "backup_kit",              # [ADR-163] bundle สำรอง+verify (ปิด gap 3-2-1) — standalone CLI, มี __main__
    # [ADR-193] ORACLE อิสระ (§3.1 BUGHUNT) — โปรแกรมแยกที่อ่าน/คำนวณเองแล้วเทียบกับ engine
    #   ใช้พิสูจน์บั๊กและ reproduce หลักฐานซ้ำได้ (ไม่อยู่ใน production path โดยตั้งใจ:
    #   oracle ต้อง "ไม่แชร์โค้ด" กับสิ่งที่มันตรวจ มิฉะนั้นบั๊กเดียวกันจะกลบกันเอง). standalone CLI.
    "oracle_suite",            # เทียบยอด/provenance/บรรทัด/ครบชีต/เลขซ้ำ/normalize/เลขคณิต/เลขภาษี
    "oracle_itm_matrix",       # เมทริกซ์บรรทัดรายการ: ผิดจริงแล้วกฎไหนจับ (จับ false-clean ITM)
    "oracle_zero_lines",       # วัดผลกระทบช่องโหว่ 'ศูนย์ถูกมองเป็นค่าหาย' บนข้อมูลจริง
    "oracle_failopen",         # จับกฎที่กลืน exception แล้วรายงานว่า 'ผ่าน' (fail-open)
    "qa_toolchain_gate",       # [ADR-194] เครื่องมือเกตต้องตรง pin — standalone CLI, มี __main__
}
# test-support: โมดูลที่ "ตั้งใจให้เทสใช้" (ไม่ใช่ production path) — เช่น registry รหัสกลางสำหรับ guard
ALLOWLIST_TEST_SUPPORT = {"code_registry"}

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


def _discover():
    """คืน {module_id: path} ของโมดูล local (root *.py + agents/*.py). agents/__init__ = 'agents'."""
    local = {}
    for f in glob.glob(os.path.join(HERE, "*.py")):
        local[os.path.splitext(os.path.basename(f))[0]] = f
    for f in glob.glob(os.path.join(HERE, "agents", "*.py")):
        local["agents." + os.path.splitext(os.path.basename(f))[0]] = f
    local["agents"] = os.path.join(HERE, "agents", "__init__.py")
    return local


def _edges(path):
    """ชื่อโมดูลที่ไฟล์นี้ import (รองรับ relative ใน agents + importlib.import_module(const))."""
    out = set()
    pkg = "agents" if os.sep + "agents" + os.sep in path or path.endswith(os.path.join("agents", "__init__.py")) else ""
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception:
        return out
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.level and pkg:                      # relative import ภายใน agents/
                out.add(f"agents.{n.module}" if n.module else "agents")
                for a in n.names:
                    out.add(f"agents.{a.name}")
            elif n.module:
                out.add(n.module)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "import_module":
            if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                out.add(n.args[0].value)
    return out


def _closure(local):
    """BFS import-closure จาก entrypoints + tools + dynamic agent load (ทุก agents.*)."""
    seen = set()
    stack = [s for s in (ENTRYPOINTS + list(ALLOWLIST_TOOLS)) if s in local]
    stack += [m for m in local if m.startswith("agents.")]   # dynamic agent load (agents/__init__:69)
    while stack:
        m = stack.pop()
        if m in seen or m not in local:
            continue
        seen.add(m)
        for ref in _edges(local[m]):
            if ref in local and ref not in seen:
                stack.append(ref)
    return seen


def main():
    local = _discover()
    reachable = _closure(local)
    is_test = lambda m: m.split(".")[-1].startswith("test_") or m == "conftest"

    print("REACHABILITY GUARD (A1+A2) — ฆ่า floating module + CI เขียวบนโค้ดตาย")
    print(f"  โมดูล local={len(local)} · reachable(prod+tools+agents)={len(reachable)}")

    # A1: ไม่มี non-test module นอก allowlist ที่ไม่ reachable
    floating = sorted(
        m for m in local
        if not is_test(m) and m not in reachable
        and m not in ALLOWLIST_TOOLS and m not in ALLOWLIST_TEST_SUPPORT and m != "agents"
    )
    _check(f"A1 ไม่มี floating module (พบ: {floating or 'ไม่มี'})", not floating)

    # A2: ทุก test_*.py import โมดูลที่ reachable อย่างน้อย 1 (ไม่ทดสอบเฉพาะโค้ดตาย)
    linked_set = reachable | ALLOWLIST_TOOLS | ALLOWLIST_TEST_SUPPORT
    dead_tests = []
    for m, path in local.items():
        if not (m.startswith("test_")):
            continue
        imported_local = {r for r in _edges(path) if r in local}
        if imported_local and not (imported_local & linked_set):
            dead_tests.append(m)
    _check(f"A2 ไม่มีเทสที่ทดสอบเฉพาะโค้ดตาย (พบ: {sorted(dead_tests) or 'ไม่มี'})", not dead_tests)

    print("=" * 64)
    if _fail == 0:
        print("RESULT: ✅ ไม่มี floating module + ทุกเทสผูกกับ production — กราฟสะอาด")
        return 0
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — wire โค้ดเข้า entrypoint, retire โค้ดตาย, "
          f"หรือเพิ่มใน ALLOWLIST พร้อมเหตุผล")
    return 1


if __name__ == "__main__":
    sys.exit(main())
