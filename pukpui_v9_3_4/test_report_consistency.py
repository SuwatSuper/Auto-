# -*- coding: utf-8 -*-
"""test_report_consistency.py — TRIPWIRE: Excel กับ Notepad (สรุปบริษัท) ต้อง "ตรงกัน"

เคสแดงที่ลูกค้าแจ้ง: Excel ขึ้น CRITICAL ERROR แต่รีพอร์ต Notepad กลับบอก "ถูกต้อง/ตรง".
สาเหตุเชิงโครงสร้าง: code_labels เลน REVIEW/MASTER + Precision Council ทำให้บางกฎ "ฟ้องใน
Excel (bill['issues']) แต่ถูกซ่อนในสรุปบริษัท". เทสนี้กันทั้งคลาส:

  [A] STATIC GUARANTEE — ทุกกฎ CRITICAL/ERROR ที่ "เปิดอยู่" ต้องอยู่เลน fix/check (โผล่ Notepad)
      และต้องไม่มีกฎใดเหลือเลน MASTER (มิฉะนั้น 'ฟ้องแล้วแต่โชว์ ไม่มี master ตรวจไม่ได้')
  [B] FIRING+SURFACING — บิลที่ทริกเกอร์กฎสำคัญ → โค้ดที่ฟ้องใน issues (Excel)
      ต้องปรากฏในช่อง fix/check ของบล็อกสรุปบริษัท (Notepad) ไม่หล่นเป็น 'ตรง'

ใช้ master ทดสอบของโปรเจกต์ (golden_snapshot.MASTER) — ชุดเดียวกับ test_rules_coverage.
    PYTHONHASHSEED=0 PUOPUY_ALLOW_VERSION_MISMATCH=1 python3 test_report_consistency.py
"""
import os
import sys
import io
import copy
import contextlib
import datetime as dt
import warnings

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

with contextlib.redirect_stdout(io.StringIO()):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

from rules_engine import RULES, run_rules
from code_labels import lane_of, field_of, FIX, CHECK
from golden_snapshot import MASTER
import super_ultra_viewer as V

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


# ════════════════════ [A] STATIC GUARANTEE ════════════════════
print("\n[A] ทุกกฎ CRITICAL/ERROR ที่เปิด → ต้องอยู่เลนที่ขึ้น Notepad (fix/check)")
hidden_ce, master_lane = [], []
for code, r in RULES.items():
    if not r.get('enabled'):
        continue
    ln = lane_of(code)
    if ln == 'master':
        master_lane.append(code)
    if r['severity'] in ('CRITICAL', 'ERROR') and ln not in (FIX, CHECK, 'note'):
        hidden_ce.append((code, r['severity'], ln))
check(not hidden_ce, f"ไม่มี CRITICAL/ERROR ซ่อนใน Notepad (พบ: {hidden_ce})")
check(not master_lane, f"ไม่มีกฎเลน MASTER (กัน 'ฟ้องแล้วโชว์ ไม่มี master') (พบ: {master_lane})")


# ════════════════════ [B] FIRING + SURFACING ════════════════════
print("\n[B] บิลที่ทริกเกอร์กฎสำคัญ → โค้ดที่ฟ้อง (Excel) ต้องขึ้นช่องใน Notepad")

_KEY = list(MASTER.keys())[0]
_MN = MASTER[_KEY]['name']
_TID = MASTER[_KEY]['tax_id']
_ADDR = MASTER[_KEY].get('address', '')


def base(**over):
    b = {
        'company': _MN, 'company_raw': _MN, 'tax_id': _TID, 'tax_id_raw': _TID,
        'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        'iv_number': 'IV6905001', 'iv_number_raw': 'IV6905001',
        'iv_date': dt.date(2025, 5, 15), 'iv_date_str': '15/05/2025',
        'address': _ADDR, 'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
        'sheet': '1', 'file': 'TST_69.05.xls', 'block_idx': 0, 'issues': [],
        'items': [{'seq': 1, 'name': 'เหล็กเส้น', 'name_raw': 'เหล็กเส้น',
                   'qty': 10.0, 'unit': 'เส้น', 'price': 100.0, 'amount': 1000.0}],
    }
    b.update(over)
    return b


def items(*specs):
    return [{'seq': i, 'name': n, 'name_raw': n, 'qty': q, 'unit': u, 'price': p, 'amount': a}
            for i, (n, q, u, p, a) in enumerate(specs, 1)]


# บิลทริกเกอร์รายกฎ (severity CRITICAL/ERROR ที่ตรวจได้โดยไม่ต้องมีหลายบิล)
TRIGGERS = {
    'CMP002': base(company='ฉี อัน คอนสตรัคชั่น กรุ๊ป', company_raw='ฉี อัน คอนสตรัคชั่น กรุ๊ป'),  # ไม่มีคำนำหน้า
    'CMP004': base(company_raw=_MN.replace(' ', '  ', 1)),                                          # เว้นวรรคเกิน
    'TAX001': base(tax_id='12345', tax_id_raw='12345'),                                             # ไม่ครบ 13
    'TAX002': base(tax_id='010556620O726', tax_id_raw='010556620O726'),                             # มีตัวอักษร
    'TAX006': base(tax_id='0105566206727', tax_id_raw='0105566206727'),                            # checksum เพี้ยน
    'TAX005': base(company='บริษัท เจ.อาร์. (ประเทศไทย) จำกัด',                                      # tax เป็นของ master แต่ชื่อคนละเจ้า
                   company_raw='บริษัท เจ.อาร์. (ประเทศไทย) จำกัด'),
    'BR002': base(branch='', branch_no=''),                                                         # ไม่ระบุสาขา
    'VAT002': base(subtotal=1000.0, vat=50.0, total=1050.0),                                        # vat≠7%
    'VAT003': base(subtotal=1000.0, vat=70.0, total=9999.0),                                        # total≠sub+vat
    'VAT001': base(items=items(('เหล็กเส้น', 10.0, 'เส้น', 100.0, 500.0)),                           # Σรายการ≠subtotal
                   subtotal=1000.0, vat=70.0, total=1070.0),
    'ITM001': base(items=items(('เหล็กเส้น', 3.0, 'เส้น', 100.0, 999.0)),                            # qty×price≠amount
                   subtotal=999.0, vat=69.93, total=1068.93),
}

file_info = {'month': 5, 'month_end': None, 'year': 2025}
for code, bill in TRIGGERS.items():
    bb = copy.deepcopy(bill)
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(bb, MASTER, file_info, unit_index={}, all_bills_ref=[bb])
        rows = V.build([bb], master_present=True)
    excel_codes = {i['code'] for i in bb['issues']}            # ฝั่ง Excel
    fired = code in excel_codes
    # ฝั่ง Notepad: ช่องที่ขึ้นปัญหา (fix/check) ของบล็อก
    prob_fields = set(rows[0]['fix']) | set(rows[0]['check']) if rows else set()
    surfaced = field_of(code) in prob_fields
    ce_consistent = True
    for c in excel_codes:                                       # ทุก critical/error ที่ฟ้อง ต้องขึ้น Notepad
        if RULES.get(c, {}).get('severity') in ('CRITICAL', 'ERROR') and field_of(c) not in prob_fields:
            ce_consistent = False
    check(fired and surfaced and ce_consistent,
          f"{code}: ฟ้องใน Excel={fired} → ขึ้นช่อง '{field_of(code)}' ใน Notepad={surfaced} (consistent={ce_consistent})")


print("\n" + "=" * 64)
if FAIL:
    print(f"REPORT-CONSISTENCY: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    sys.exit(1)
print(f"REPORT-CONSISTENCY: ผ่าน {PASS} / ล้มเหลว 0")
print("=" * 64)
print("RESULT: ✅ Excel กับ Notepad ตรงกัน — ไม่มี critical/error ที่ฟ้องใน Excel แต่ซ่อนใน Notepad")
sys.exit(0)
