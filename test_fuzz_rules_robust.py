# -*- coding: utf-8 -*-
"""test_fuzz_rules_robust.py — [GAP-A] ทุกกฎที่เปิดใช้งานต้อง "รอด" fuzz matrix (ไม่ครัช→SYS→ข้ามกฎ)

บริบท (ความทนทาน 5 ปี): ใน 5 ปีจะเจอเซลล์แปลก ๆ — ชื่อสินค้าเป็นตัวเลขล้วน (รหัส/โมเดล), ช่องว่าง→None,
ยอดเงิน NaN/Inf, สตริงยาว, zero-width/full-width/emoji. ถ้ากฎครัช → `run_rules` ดักเป็น `SYS-*` (INFO)
แล้ว "ข้ามกฎเงียบ" → 'ตรวจไม่ได้' โผล่เป็น 'ตรง' หลอก = **false-negative** (ขัดปรัชญาระบบ).

แก้ (GAP-A, rules_engine.run_rules): ชั้น data-hygiene coerce ฟิลด์ข้อความ (item: name/name_raw/unit ;
bill: company/tax_id/.../iv_number ฯลฯ) เป็น str ก่อนเข้ากฎ. corpus จริงทุกฟิลด์เป็น str → no-op →
golden-NEUTRAL (d8adc143). เทสนี้ยิง fuzz ทุกกฎ "ผ่าน run_rules (เส้นจริง)" แล้วบังคับ:
  • ไม่มี SYS-* ใหม่เกิดขึ้นเลย (= ไม่ครัช ไม่ข้ามกฎ) ทุก fuzz cell
  • detection คงอยู่: ชื่อเป็นตัวเลข '12345' → ITM007 ตรวจ "ชื่อสั้น" (ไม่ใช่ข้าม) ; typo จริงยังฟ้อง

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_fuzz_rules_robust.py
"""
import os, sys, io, contextlib, warnings, importlib
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine as RE
import state
from diagnostics import system_issues_reset

PASS, FAIL = 0, []
def check(c, l):
    global PASS
    if c: PASS += 1; print(f"  ✅ {l}")
    else: FAIL.append(l); print(f"  ❌ {l}")

N_ENABLED = sum(1 for r in RE.RULES.values() if r['enabled'])

# edge values ที่จะเจอจริงใน 5 ปี (รวม non-str บนฟิลด์ข้อความ + ตัวเลขขอบบนฟิลด์ตัวเลข)
EDGE = {
    'None': None, 'empty': '', 'spaces': '   ', 'int': 12345, 'float': 45.5,
    'neg': -7, 'zero': 0, 'huge': 10**18, 'longdec': 1.0/3.0,
    'nan': float('nan'), 'inf': float('inf'), 'ninf': float('-inf'),
    'longstr': 'ก' * 1500, 'zerowidth': 'ท่อ​เหล็ก', 'fullwidth': 'ＡＢＣ１２３',
    'emoji': 'ท่อ😀เหล็ก', 'bool': True, 'list': [1, 2], 'thaicombine': 'เเป๊ปํ',
    'tab': '\t\n', 'ctrl': 'a\x00b',
}

def base_bill():
    return {'file': 'f.xls', 'sheet': '1', 'block_idx': 0,
            'company': 'บริษัท ทดสอบ จำกัด', 'company_raw': 'บริษัท ทดสอบ จำกัด',
            'tax_id': '0105500000017', 'tax_id_raw': '0105500000017',
            'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
            'address': '1 ถ.x แขวงy เขตz กทม 10000', 'iv_number': 'IV001', 'iv_number_raw': 'IV001',
            'iv_date': None, 'iv_date_str': '01/05/2026', 'subtotal': 20.0, 'vat': 1.4, 'total': 21.4,
            'items': [{'seq': 1, 'name': 'ท่อเหล็ก', 'name_raw': 'ท่อเหล็ก', 'qty': 2.0,
                       'unit': 'เส้น', 'price': 10.0, 'amount': 20.0}], 'issues': []}

ALL_BILL_FIELDS = ['company', 'company_raw', 'tax_id', 'tax_id_raw', 'address', 'branch',
                   'branch_no', 'iv_number', 'iv_number_raw', 'iv_date_str', 'sheet',
                   'subtotal', 'vat', 'total']
ALL_ITEM_FIELDS = ['name', 'name_raw', 'unit', 'qty', 'price', 'amount', 'seq']

def run_quiet(bill):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        RE.run_rules(bill, {}, {'month': None})

print("=" * 64)
print(f"FUZZ MATRIX — {N_ENABLED} กฎที่เปิดใช้งาน ต้องรอดทุก fuzz cell (ไม่เกิด SYS-*)")
print("=" * 64)

# ── [A] fuzz matrix: ทุกฟิลด์ × ทุก edge → 0 SYS-* ───────────────────────
tested = 0; sys_seen = {}
for fld in ALL_BILL_FIELDS:
    for en, ev in EDGE.items():
        b = base_bill(); b[fld] = ev
        system_issues_reset(); run_quiet(b); tested += 1
        if state._SYSTEM_ISSUES:
            sys_seen.setdefault(('bill.' + fld, en), [i['code'] for i in state._SYSTEM_ISSUES])
for fld in ALL_ITEM_FIELDS:
    for en, ev in EDGE.items():
        b = base_bill(); b['items'][0][fld] = ev
        system_issues_reset(); run_quiet(b); tested += 1
        if state._SYSTEM_ISSUES:
            sys_seen.setdefault(('item.' + fld, en), [i['code'] for i in state._SYSTEM_ISSUES])
# multi-field garbage bill (ทุกฟิลด์พังพร้อมกัน)
for en, ev in EDGE.items():
    b = base_bill()
    for fld in ALL_BILL_FIELDS: b[fld] = ev
    for fld in ALL_ITEM_FIELDS: b['items'][0][fld] = ev
    system_issues_reset(); run_quiet(b); tested += 1
    if state._SYSTEM_ISSUES:
        sys_seen.setdefault(('ALL', en), [i['code'] for i in state._SYSTEM_ISSUES])

print(f"\n[A] fuzz cells รัน = {tested}")
check(not sys_seen, f"ทุก fuzz cell ไม่เกิด SYS-* (ไม่ครัช/ไม่ข้ามกฎ) — กฎ {N_ENABLED} ตัวรอดครบ")
if sys_seen:
    for (f, en), codes in list(sys_seen.items())[:20]:
        print(f"     ❌ SYS ที่ {f}={en}: {sorted(set(codes))}")

# ── [B] detection คงอยู่ (ไม่ใช่แค่ 'ไม่ครัช' แต่ต้อง 'ยังตรวจได้') ──────────
print("\n[B] detection preserved (non-str ไม่ทำให้ 'ข้ามกฎเงียบ')")
b = base_bill(); b['items'][0]['name'] = 12345; b['items'][0]['name_raw'] = 12345
system_issues_reset(); run_quiet(b)
codes = [i.get('code') for i in b['issues']]
check('ITM007' in codes, "ชื่อสินค้า=12345 (รหัสตัวเลข) → ITM007 ตรวจ 'ชื่อสั้น' (ไม่ข้าม)")
check(not state._SYSTEM_ISSUES, "ชื่อ=12345 → ไม่มี SYS-* (กฎ ITM ทุกตัวรันได้)")

# typo จริงยังฟ้อง (recall ไม่ถอยจากการ coerce)
b = base_bill(); b['items'][0]['name'] = 'สายไฟ มั้วน 300 เมตร'; b['items'][0]['name_raw'] = 'สายไฟ มั้วน 300 เมตร'
system_issues_reset(); run_quiet(b)
check(any(c == 'ITM011' for c in [i.get('code') for i in b['issues']]), "typo จริง 'มั้วน' → ITM011 ยังฟ้อง")

# ── [C] บิลที่ทุกฟิลด์เป็น None (บิลภายนอก/ขาดข้อมูลสุดขีด) → ไม่ครัช ─────────
print("\n[C] บิล None ล้วน + item None ล้วน → ไม่ครัช (degrade graceful)")
b = {'items': [{}], 'issues': []}
system_issues_reset()
ok = True
try: run_quiet(b)
except Exception as e: ok = False; print("     exc:", e)
check(ok and not state._SYSTEM_ISSUES, "บิล/ไอเทมว่างเปล่า → run_rules ไม่ครัช + ไม่มี SYS-*")

print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL: print("   ❌", l)
    sys.exit(1)
print(f"✅ ครบ — {N_ENABLED} กฎรอด fuzz matrix ({tested} cells) + detection คงอยู่ (GAP-A ปิด)")
