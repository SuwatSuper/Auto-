# -*- coding: utf-8 -*-
"""test_adr138_gate_robust.py — [ADR-138] แก้ false-green/splat ใน QA tripwires (golden-neutral tooling).

(GOV-02) coverage_gate.TESTS[0] เคยเป็น bare string → `*t` splat เป็นตัวอักษรทีละตัว → coverage
    รันไฟล์ชื่อ 't'/'e'/... (เงียบ) → test_rules_c_decimal_gates "ไม่เคยถูกวัด". แก้: ทุก entry เป็น list.
(GOV-03) version_gate._policy: เวอร์ชันแปลงเลขไม่ได้ (LV_UNKNOWN, เช่น 'dev') ของ dep หัวใจ → เดิม
    WARN (false-green). แก้: FAIL. env ปกติ (เลขสะอาด) → LV_OK ไม่กระทบ.

หมายเหตุ: ตรวจ coverage_gate.TESTS ด้วย AST (ห้าม import — coverage_gate รัน gate ทั้งหมดตอน import).
golden-neutral (QA tooling, นอก audit pipeline). รันได้ทุกที่.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FAILS = []


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def _coverage_tests_via_ast():
    """อ่าน list literal TESTS จาก coverage_gate.py ด้วย AST (ไม่ import = ไม่รัน gate)."""
    src = open(os.path.join(HERE, 'coverage_gate.py'), encoding='utf-8').read()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == 'TESTS' and isinstance(node.value, ast.List):
                    return node.value.elts
    return None


def main():
    print('=== [GOV-02] coverage_gate.TESTS ทุก entry เป็น list (ไม่ splat เป็นตัวอักษร) ===')
    elts = _coverage_tests_via_ast()
    _check(elts is not None, 'พบ TESTS = [...] ใน coverage_gate.py')
    if elts is not None:
        non_list = [ast.dump(e)[:40] for e in elts if not isinstance(e, ast.List)]
        _check(not non_list, f'ทุก entry เป็น list literal (เจอ non-list: {non_list})')
        # ยืนยัน test_rules_c_decimal_gates อยู่ในรูป list ([...]) ไม่ใช่ bare string
        has_rc = any(isinstance(e, ast.List) and e.elts
                     and isinstance(e.elts[0], ast.Constant)
                     and e.elts[0].value == 'test_rules_c_decimal_gates.py' for e in elts)
        _check(has_rc, "test_rules_c_decimal_gates.py อยู่ในรูป ['...'] (ถูกวัดจริง)")

    print()
    print('=== [GOV-03] version_gate: LV_UNKNOWN (เวอร์ชันแปลงไม่ได้) ของ dep หัวใจ = FAIL ===')
    import version_gate as VG   # guarded (if __name__) → import ปลอดภัย
    _check(VG.parse_version('dev') == tuple(), "parse_version('dev') = () (แปลงไม่ได้)")
    _check(VG.diff_level('2.2.2', 'dev') == VG.LV_UNKNOWN, "diff_level('2.2.2','dev') = LV_UNKNOWN")
    crit = sorted(VG.REQUIRED_CRITICAL)[0] if VG.REQUIRED_CRITICAL else 'pandas'
    _check(VG._policy(crit, VG.LV_UNKNOWN, strict=False) == VG.ST_FAIL,
           f"_policy({crit}, LV_UNKNOWN) = FAIL (เดิม WARN false-green)")
    _check(VG._policy('python', VG.LV_UNKNOWN, strict=False) == VG.ST_FAIL,
           "_policy(python, LV_UNKNOWN) = FAIL")
    _check(VG._policy(crit, VG.LV_OK, strict=False) == VG.ST_OK,
           f"_policy({crit}, LV_OK) = OK (env ปกติเลขสะอาด ไม่กระทบ)")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — QA tripwires: ไม่ splat, ไม่ false-green เวอร์ชันหัวใจ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
