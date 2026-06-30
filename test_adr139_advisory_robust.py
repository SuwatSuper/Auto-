# -*- coding: utf-8 -*-
"""test_adr139_advisory_robust.py — [ADR-139] advisory-layer robustness (golden-neutral).

(RB-02) analytics.build_unit_index key ด้วย it['name'] ดิบ (ไม่ coerce) ; รัน "ก่อน" run_rules ที่
    coerce name→str (rules_engine:289-291) → r_itm015 lookup ด้วย name ที่ coerce แล้ว → ถ้า name
    เป็น non-str (int รหัสสินค้า) key ไม่ตรง → ITM015 พลาด cross-unit conflict (false-negative).
    แก้: coerce name/unit→str ใน build_unit_index ให้ตรง. corpus str → no-op → golden-neutral.
(RPT-04) super_ultra_viewer:288 `except Exception: pass` กลืน import+runtime error เงียบสนิท
    (ขัด mandate ADR-111). แก้: ทิ้ง SYS-UNITNOTE trail. golden-neutral (report layer).
รันได้ทุกที่.
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


def main():
    print('=== [RB-02] build_unit_index coerce name/unit→str (ตรงกับ run_rules) ===')
    import analytics
    # บิลที่ item name เป็น int (รหัสสินค้า) + 2 หน่วยต่างกัน → key ต้องเป็น str '4501'
    bills = [{'items': [{'name': 4501, 'unit': 'กล่อง'}, {'name': 4501, 'unit': 'ชิ้น'}]}]
    idx = analytics.build_unit_index(bills)
    _check('4501' in idx, "key เป็น str '4501' (coerce แล้ว ตรงกับ r_itm015 lookup)")
    _check(4501 not in idx, "ไม่มี key int 4501 ดิบ (เดิม key ไม่ตรง lookup)")
    _check(idx.get('4501') == {'กล่อง', 'ชิ้น'}, "2 หน่วยรวมใต้ key เดียว (ITM015 จับ conflict ได้)")
    # str ปกติ byte-identical
    bills2 = [{'items': [{'name': 'ท่อ PVC', 'unit': 'เส้น'}]}]
    _check(analytics.build_unit_index(bills2).get('ท่อ PVC') == {'เส้น'}, "name str ปกติเหมือนเดิม")
    # None name ไม่สร้าง key ขยะ
    bills3 = [{'items': [{'name': None, 'unit': 'ชิ้น'}]}]
    _check(analytics.build_unit_index(bills3) == {} or '' not in analytics.build_unit_index(bills3),
           "name=None → ไม่ index (name='' falsy)")

    print()
    print('=== [RPT-04] super_ultra_viewer except company_unit_notes ไม่เงียบ (ทิ้ง SYS trail) ===')
    src = open(os.path.join(HERE, 'super_ultra_viewer.py'), encoding='utf-8').read()
    tree = ast.parse(src)

    def _body_calls_cun(try_node):
        """True ถ้า "body" ของ try (ไม่ใช่ handler) มี call company_unit_notes จริง (ไม่ใช่ string)."""
        for stmt in try_node.body:
            for n in ast.walk(stmt):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                        and n.func.attr == 'company_unit_notes':
                    return True
        return False

    target = [t for t in ast.walk(tree) if isinstance(t, ast.Try) and _body_calls_cun(t)]
    _check(len(target) == 1, f'พบ try เดียวที่ body เรียก company_unit_notes (พบ {len(target)})')
    if target:
        handler_ok = any('SYS-UNITNOTE' in (ast.get_source_segment(src, h) or '')
                         for h in target[0].handlers)
        _check(handler_ok, "handler ของ try นั้นทิ้ง SYS-UNITNOTE trail (ไม่ bare pass เงียบ)")

    print('=' * 60)
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} ข้อ)')
        return 1
    print('RESULT: ✅ PASS — advisory layer: unit-index coerce non-str + viewer note ไม่เงียบ')
    return 0


if __name__ == '__main__':
    sys.exit(main())
