# -*- coding: utf-8 -*-
"""coverage_gate.py — เกต coverage โมดูลแกน (OBJ-TEST) — line ≥90% + วัด branch

รันชุดเทสที่ครอบโมดูลแกนใต้ coverage (--branch) แล้วรายงาน line% / branch% / combined%
ต่อ "กลุ่มโมดูล" (module group). เกตที่ระดับกลุ่ม → ทนต่อการซอยไฟล์ (OBJ-MAINT):
  เดิม rules_engine เป็นไฟล์เดียว ; หลังซอยเป็น base + rules_a/b/c + shell ยังนับ
  "รวมทั้งตระกูล" เป็นหน่วยเดียว (ความหมายของเกตเท่าเดิม — ไม่ถูกหลอกด้วย granularity).

นโยบายเกต (DECISIONS.md §6, §6.1):
  • LINE gate  : บังคับ ≥ PUOPUY_COV_MIN (ดีฟอลต์ 90) ต่อกลุ่ม — พฤติกรรมเดิม
  • BRANCH gate: บังคับ ≥ PUOPUY_COV_BRANCH_MIN เฉพาะเมื่อตั้ง env ; ไม่ตั้ง = รายงานเฉย ๆ

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 coverage_gate.py
exit 0 = ผ่าน, 1 = ต่ำกว่าเกณฑ์
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
THRESHOLD = float(os.environ.get("PUOPUY_COV_MIN", "90"))
_bmin_raw = os.environ.get("PUOPUY_COV_BRANCH_MIN")
BRANCH_MIN = float(_bmin_raw) if _bmin_raw not in (None, "") else None

# กลุ่มโมดูลแกน: (ป้าย, [ไฟล์ในกลุ่ม]) — เกตที่ระดับ "รวมกลุ่ม"
GROUPS = [
    ("parser (family)", [
        "parser.py", "parser_p0.py", "parser_p1.py", "parser_p2.py",
    ]),
    ("rules_engine (family)", [
        "rules_engine.py", "rules_engine_base.py",
        "rules_engine_rules_a.py", "rules_engine_rules_b.py", "rules_engine_rules_c.py",
    ]),
    ("validators.py", ["validators.py"]),
    ("puopuy_units.py", ["puopuy_units.py"]),
]
# source = ทุกไฟล์ในทุกกลุ่ม
_allfiles = [f for _, fs in GROUPS for f in fs]
SOURCE = ",".join(os.path.splitext(f)[0] for f in _allfiles)
TESTS = [
    'test_rules_c_decimal_gates.py',
    ["test_rules_coverage.py"], ["test_rules_extra.py"], ["test_rules_extra2.py"],
    ["test_rules_typo_branch.py"],   # r_itm004/r_itm010 typo emit branches (rules_b)
    # [ADR-088] เพิ่มเทส characterization ที่มีอยู่แล้ว (ADR-084/087) เข้า measurement —
    #   exercise _kw_in_name color-exclusion (line 142/144) + r_itm005 branches ที่ fixture ไม่ถึง.
    #   ไม่ใช่เทสปั้นเพื่อคะแนน: เป็นเทสจริงที่เขียนไว้แล้ว แค่ coverage_gate ไม่ได้รวมตอนวัด.
    ["test_itm005_precision.py"], ["test_typo_decisions_lock.py"],
    # [B/D] กฎใหม่ — ครอบ branch ของ r_tax008/r_addr006/r_br004/r_iv007 (มิฉะนั้น branch coverage ตก)
    ["test_tax008.py"], ["test_addr006.py"], ["test_br004.py"], ["test_iv007.py"],
    # [BS-1..4] กฎ/พาธใหม่ — ครอบ branch ของ r_vat011/r_tax009 (rules_c) + _tor_try_date (parser_p2)
    ["test_bs2_vat011_zero.py"], ["test_bs3_tax009_samename.py"], ["test_bs4_dt006_tor_calendar.py"],
    # [ADR-119] audit fixes — ครอบ branch ใหม่: _cell_to_num inf/overflow (parser_p0a), ADDR001 lookaround
    #   (rules_a), r_iv001/r_tax008/match_company precompute path (rules_a/c/base)
    ["test_adr119_audit_fixes.py"],
    ["test_units_extra.py"], ["test_validators.py"], ["test_validators_extra.py"],
    ["test_validators_coverage.py"], ["test_validators_branch.py"],
    ["test_validators_missing_checks.py"],   # DT005/IV005/DT006/IV006 emit+skip+idempotent branches
    ["test_crosscheck_idempotency.py"],
    ["test_parser_helpers.py"], ["test_parser_extra.py"],
    ["test_parser_extra2.py"], ["test_parser_negative.py"], ["test_pinned_logic.py"],
    ["test_parser_branch.py"], ["test_iv_parser_guard.py"],   # [D2] guard branch ใน _pb_try_iv
    ["regression_full.py", ".", "tests/fixtures", "tests/fixtures/baseline_fixture.json"],
]
env = dict(os.environ, PYTHONHASHSEED="0", PUOPUY_AUDIT_DATE="2026-06-02")
PY = sys.executable

print("=" * 64)
print(f"COVERAGE GATE — line ต้อง ≥ {THRESHOLD:.0f}% (ต่อกลุ่ม)", end="")
if BRANCH_MIN is not None:
    print(f" + branch ต้อง ≥ {BRANCH_MIN:.0f}%")
else:
    print("  (branch: วัด+รายงาน ไม่บังคับ)")
print("=" * 64)
subprocess.run([PY, "-m", "coverage", "erase"], env=env, check=False)
for t in TESTS:
    subprocess.run([PY, "-m", "coverage", "run", "-a", "--branch", f"--source={SOURCE}", *t],
                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
subprocess.run([PY, "-m", "coverage", "json", "-o", ".coverage.json", "-q"], env=env, check=False)

with open(".coverage.json", encoding="utf-8") as _cov_f:
    data = json.load(_cov_f)
files = {os.path.basename(p): info for p, info in data.get("files", {}).items()}


def _agg(file_names):
    """รวมตัวนับดิบของไฟล์ในกลุ่ม → (line%, branch%, combined%, found_any)."""
    ns = cl = nb = cb = 0
    found = False
    for fn in file_names:
        info = files.get(fn)
        if info is None:
            continue
        found = True
        s = info["summary"]
        ns += s.get("num_statements", 0)
        cl += s.get("covered_lines", 0)
        nb += s.get("num_branches", 0)
        cb += s.get("covered_branches", 0)
    line = (100.0 * cl / ns) if ns else 0.0
    branch = (100.0 * cb / nb) if nb else 100.0
    combined = (100.0 * (cl + cb) / (ns + nb)) if (ns + nb) else 0.0
    return line, branch, combined, found


fail = []
print(f"\n{'group':24} {'line':>7} {'branch':>8} {'combined':>9}")
print("-" * 52)
tot_ns = tot_cl = tot_nb = tot_cb = 0
for label, fnames in GROUPS:
    line, branch, comb, found = _agg(fnames)
    if not found:
        print(f"  {label:22} {'N/A':>7}  (ไม่พบใน coverage)")
        fail.append(f"{label}: ไม่พบข้อมูล coverage")
        continue
    for fn in fnames:
        s = files.get(fn, {}).get("summary", {})
        tot_ns += s.get("num_statements", 0); tot_cl += s.get("covered_lines", 0)
        tot_nb += s.get("num_branches", 0); tot_cb += s.get("covered_branches", 0)
    line_ok = line >= THRESHOLD
    branch_ok = (BRANCH_MIN is None) or (branch >= BRANCH_MIN)
    flag = "✅" if (line_ok and branch_ok) else "❌"
    print(f"  {label:22} {line:>6.1f}% {branch:>7.1f}% {comb:>8.1f}%  {flag}")
    if not line_ok:
        fail.append(f"{label}: line {line:.1f}% < {THRESHOLD:.0f}%")
    if BRANCH_MIN is not None and branch < BRANCH_MIN:
        fail.append(f"{label}: branch {branch:.1f}% < {BRANCH_MIN:.0f}%")

tl = (100.0 * tot_cl / tot_ns) if tot_ns else 0.0
tb = (100.0 * tot_cb / tot_nb) if tot_nb else 100.0
tc = (100.0 * (tot_cl + tot_cb) / (tot_ns + tot_nb)) if (tot_ns + tot_nb) else 0.0
print(f"  {'TOTAL (แกน)':22} {tl:>6.1f}% {tb:>7.1f}% {tc:>8.1f}%")

print("\n" + "=" * 64)
if fail:
    for x in fail:
        print(f"  • {x}")
    print("RESULT: ❌ coverage ต่ำกว่าเกณฑ์")
    sys.exit(1)
msg = f"line ≥ {THRESHOLD:.0f}%"
if BRANCH_MIN is not None:
    msg += f" + branch ≥ {BRANCH_MIN:.0f}%"
print(f"RESULT: ✅ ทุกกลุ่มแกนผ่าน ({msg})")
sys.exit(0)
