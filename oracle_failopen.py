# -*- coding: utf-8 -*-
"""oracle_failopen.py — ORACLE §3.3: จับ "กฎที่กลืน exception แล้วรายงานว่าผ่าน"

หลักการ: ติด sys.settrace ดัก event 'exception' ทุกครั้งที่เกิดใน frame ของไฟล์กฎ
แล้วดูว่ามัน "โผล่ออกมาถึง run_rules" (→ กลายเป็น SYS-* = ซื่อสัตย์) หรือ
"ถูกกลืนใน except ของกฎเอง" (→ return [] = บอกว่าผ่านทั้งที่ตรวจไม่สำเร็จ = fail-open)

รัน:  python3 oracle_failopen.py
"""
import sys
import os
import io
import contextlib
from collections import Counter, defaultdict

import rules_engine as RE

RULE_FILES = ("rules_engine_rules_a.py", "rules_engine_rules_b.py",
              "rules_engine_rules_c.py", "rules_engine.py")

swallowed = Counter()      # (code, exc_type, where, fn) -> n
_cur_code = None
_pending = []              # exception ที่เกิดในรอบเรียกปัจจุบัน


def _tracer(frame, event, arg):
    if event == "exception" and _cur_code:
        fn = os.path.basename(frame.f_code.co_filename)
        if fn in RULE_FILES:
            _pending.append((_cur_code, arg[0].__name__,
                             f"{fn}:{frame.f_lineno}", frame.f_code.co_name))
    return _tracer


def probe(bill, master=None, ctx=None):
    """รันทุกกฎกับบิลหนึ่ง แล้วบันทึกว่ากฎไหนกลืน exception"""
    global _cur_code
    ctx = ctx or {'sheet_name': bill.get('sheet'), 'target_month': None,
                  'target_month_end': None, 'all_masters': {}, 'unit_index': None,
                  'all_bills_for_iv_check': [], 'xbill_tax_index': {},
                  'xbill_file_index': {}, 'xbill_iv_index': {}}
    out = {}
    for code, rule in RE.RULES.items():
        if not rule.get('enabled'):
            continue
        _cur_code = code
        _pending.clear()
        sys.settrace(_tracer)
        try:
            out[code] = rule['check'](bill, master, ctx) or []
            raised = False
        except Exception:
            raised = True
            out[code] = None            # โผล่ถึง run_rules → SYS-* (ซื่อสัตย์)
        finally:
            sys.settrace(None)
            _cur_code = None
        # นับเป็น "กลืน" เฉพาะเมื่อ exception เกิดขึ้นแต่ "ไม่โผล่ออกมา"
        #   (โผล่ออกมา = run_rules ดักเป็น SYS-* = ซื่อสัตย์ ไม่ใช่ fail-open)
        if not raised:
            for k in _pending:
                swallowed[k] += 1
        _pending.clear()
        out[code] = (out[code], raised)
    return out


# ── บิลปกติ (baseline) ────────────────────────────────────────────
GOOD = {
    'file': 'x.xls', 'sheet': '1', 'block_idx': 0,
    'company': 'บริษัท ทดสอบ จำกัด', 'company_raw': 'บริษัท ทดสอบ จำกัด',
    'tax_id': '0105556123456', 'tax_id_raw': '0105556123456',
    'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
    'address': '1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    'address_raw': '1 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    'iv_number': 'IV69050001', 'iv_number_raw': 'IV-69050001',
    'iv_date': None, 'iv_date_str': '05/05/2026',
    'subtotal': 100.0, 'vat': 7.0, 'total': 107.0,
    'amount_source': {'subtotal': 'ocr', 'vat': 'ocr', 'total': 'ocr'},
    'items': [{'seq': 1, 'name': 'ท่อพีวีซี', 'name_raw': 'ท่อพีวีซี', 'qty': 2.0,
               'unit': 'เส้น', 'price': 50.0, 'amount': 100.0, 'discount': None}],
    'issues': [],
}

# ── ชุดบิล "ผิดรูป" ตาม §3.5 (ค่าที่ parser อนาคต/ไฟล์พังอาจให้มา) ──
MUTANTS = {}
for fld, vals in {
    'company':   [None, 123, float('nan'), b'x'],
    'tax_id':    [None, 12345, float('nan')],
    'address':   [None, 42, float('nan')],
    'iv_number': [None, 6.9e9, float('nan')],
    'branch':    [None, 7],
    'branch_no': [None, 5],
    'iv_date_str': [None, 20260505],
    'subtotal':  ['100', None, float('nan'), float('inf'), -100.0],
    'vat':       ['7', None, float('nan'), float('inf')],
    'total':     ['107', None, float('nan'), float('inf')],
}.items():
    for i, v in enumerate(vals):
        b = dict(GOOD)
        b['items'] = [dict(GOOD['items'][0])]
        b['issues'] = []
        b[fld] = v
        MUTANTS[f"{fld}={v!r}"] = b

for ifld, vals in {
    'qty': [None, '2', float('nan'), float('inf'), True],
    'price': [None, '50', float('nan'), float('inf'), True],
    'amount': [None, '100', float('nan'), float('inf'), True],
    'name': [None, 123, float('nan')],
    'unit': [None, 7, float('nan')],
    'seq': [None, 'x'],
    'discount': ['5', float('nan')],
}.items():
    for v in vals:
        b = dict(GOOD)
        it = dict(GOOD['items'][0]); it[ifld] = v
        b['items'] = [it]; b['issues'] = []
        MUTANTS[f"item.{ifld}={v!r}"] = b

print("=" * 74)
print("ORACLE FAIL-OPEN — กฎที่กลืน exception แล้วบอกว่า 'ผ่าน'")
print("=" * 74)

with contextlib.redirect_stdout(io.StringIO()):
    probe(dict(GOOD, items=[dict(GOOD['items'][0])], issues=[]))
base_sw = set(swallowed)
swallowed.clear()

raised_map = defaultdict(list)
for name, b in MUTANTS.items():
    with contextlib.redirect_stdout(io.StringIO()):
        res = probe(b)
    for code, (_out, raised) in res.items():
        if raised:
            raised_map[code].append(name)

print(f"\nบิลผิดรูปที่ทดสอบ: {len(MUTANTS)} แบบ · กฎที่เปิดใช้: "
      f"{sum(1 for r in RE.RULES.values() if r.get('enabled'))}")

print("\n── [A] กฎที่ exception 'โผล่ถึง run_rules' (→ SYS-* ซื่อสัตย์) ──")
if raised_map:
    for code in sorted(raised_map):
        print(f"  {code}: {len(raised_map[code])} เคส  เช่น {raised_map[code][:3]}")
else:
    print("  (ไม่มี — run_rules coercion กันไว้หมด)")

print("\n── [B] กฎที่ 'กลืน exception เอง' แล้ว return [] (= fail-open) ──")
agg = defaultdict(Counter)
for (code, etype, where, fn), n in swallowed.items():
    agg[code][(etype, where, fn)] += n
if agg:
    for code in sorted(agg):
        print(f"\n  {code}:")
        for (etype, where, fn), n in agg[code].most_common():
            print(f"     {etype:22s} @ {where}  ใน {fn}()  ×{n}")
else:
    print("  (ไม่มี)")

print("\n" + "=" * 74)
print(f"สรุป: fail-open {len(agg)} กฎ · honest-SYS {len(raised_map)} กฎ")
