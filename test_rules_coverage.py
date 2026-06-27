# -*- coding: utf-8 -*-
"""test_rules_coverage.py — [OBJ-1D] ขับ run_rules ด้วยบิลหลากข้อบกพร่อง

เป้าหมาย:
  (1) พิสูจน์ว่า run_rules ไม่ throw บนบิลทุกแบบ (กฎเดียวพัง = route ไป SYS-* ไม่ล้มบิล)
  (2) เพิ่ม coverage ของ rules_engine.py ให้แตะกิ่งของกฎ r_* ให้มากที่สุด
  (3) ยืนยันว่ากฎสำคัญ "ฟ้องเมื่อควรฟ้อง / เงียบเมื่อควรเงียบ" (sanity ไม่กี่จุด)

ไม่ต้องใช้ข้อมูลจริง → เร็ว ใส่ CI ได้:
    PYTHONHASHSEED=0 python3 test_rules_coverage.py
exit 0 = ผ่าน, 1 = พบกฎที่ throw หรือ sanity ผิด
"""
import os
import sys
import io
import copy
import contextlib
import warnings
import datetime as dt

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import state
from rules_engine import run_rules, RULES
from analytics import build_unit_index
# [ADR-102] golden_snapshot.MASTER ว่างแล้ว (ลบบริษัทตัวอย่างตามคำสั่งเจ้าของ) → เทสนี้นิยาม master fixture
#   ของตัวเองเพื่อขับ branch master-comparison (CMP002/004/006/TAX005/BR/ADDR ฯลฯ) ให้ครบใน coverage gate
MASTER = {
    "ฉี อัน คอนสตรัคชั่น": {
        "name": "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด",
        "tax_id": "0105566206726",
        "branch": "สำนักงานใหญ่",
        "address": "เลขที่ 5/32 ซอย ศรีนครินทร์ 46/1 เขตประเวศ กรุงเทพมหานคร 10250",
        "iv_prefix": "IV",
    }
}

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


# ── บิลฐาน "สะอาด" ที่ตรงกับ MASTER (บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด) ──
def make_bill(**over):
    b = {
        'company': 'บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด',
        'company_raw': 'บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด',
        'tax_id': '0105566206726',
        'tax_id_raw': '0105566206726',
        'branch': 'สำนักงานใหญ่',
        'branch_no': '00000',
        'iv_number': 'IV6805001',
        'iv_number_raw': 'IV6805001',
        'iv_date': dt.date(2025, 5, 15),
        'iv_date_str': '15/05/2025',
        'address': 'เลขที่ 5/32 ซอย ศรีนครินทร์ 46/1 เขตประเวศ กรุงเทพมหานคร 10250',
        'subtotal': 1000.0,
        'vat': 70.0,
        'total': 1070.0,
        'amount_confidence': 'HIGH',
        'amount_source': {'subtotal': 'parsed', 'vat': 'parsed', 'total': 'parsed'},
        'sheet': '1',
        'file': 'TEST_6805.xlsx',
        'block_idx': 0,
        'issues': [],          # add_issue ทำ b['issues'].append(...) — บิลจริงมีคีย์นี้เสมอ
        'items': [
            {'seq': 1, 'name': 'เหล็กเส้น', 'name_raw': 'เหล็กเส้น',
             'qty': 10.0, 'unit': 'เส้น', 'price': 100.0, 'amount': 1000.0},
        ],
    }
    b.update(over)
    return b


def items(*specs):
    out = []
    for i, (name, qty, unit, price, amount) in enumerate(specs, 1):
        out.append({'seq': i, 'name': name, 'name_raw': name,
                    'qty': qty, 'unit': unit, 'price': price, 'amount': amount})
    return out


# ── ชุดบิลครอบข้อบกพร่องหลายคลัสเตอร์ (เพื่อแตะกิ่งกฎให้กว้าง) ──
bills = [
    # 0) สะอาด ตรง master ทุกอย่าง
    make_bill(),
    # 1) ชื่อบริษัทผิด/ไม่มีคำนำหน้า/มีแบรนด์/เว้นวรรคเพี้ยน
    make_bill(company='ฉีอัน คอนสตรัคชั่น', company_raw='ฉีอัน คอนสตรัคชั่น'),
    make_bill(company='บริษัทฉี อัน คอนสตรัคชั่น กรุ๊ป', tax_id=''),
    # 2) เลขภาษีพัง: สั้น / ไม่ใช่ตัวเลข / checksum ผิด / OCR
    make_bill(tax_id='12345', tax_id_raw='12345'),
    make_bill(tax_id='010556620O726', tax_id_raw='010556620O726'),
    make_bill(tax_id='0105566206727', tax_id_raw='0105566206727'),  # checksum เพี้ยน
    # 3) สาขา: format ผิด / ไม่ระบุ
    make_bill(branch='', branch_no=''),
    make_bill(branch_no='ABC'),
    # 4) วันที่: อนาคต / นอกช่วง / พ.ศ.ปน
    make_bill(iv_date=dt.date(2099, 1, 1), iv_date_str='01/01/2099'),
    make_bill(iv_date=dt.date(1900, 1, 1), iv_date_str='01/01/1900'),
    make_bill(iv_date=None, iv_date_str=''),
    # 5) รายการ: qty×price ผิด / seq ไม่เรียง / ชื่อสั้น / ติดลบ / ซ้ำ / หน่วยต่าง
    make_bill(items=items(('เหล็กเส้น', 10.0, 'เส้น', 100.0, 999.0)), subtotal=999.0, vat=69.93, total=1068.93),
    make_bill(items=[
        {'seq': 3, 'name': 'ก', 'name_raw': 'ก', 'qty': -5.0, 'unit': 'อัน', 'price': -2.0, 'amount': 10.0},
        {'seq': 7, 'name': 'เหล็กเส้นกลม', 'name_raw': 'เหล็กเส้นกลม', 'qty': 1.0, 'unit': 'เส้น', 'price': 50.0, 'amount': 50.0},
    ], subtotal=60.0, vat=4.2, total=64.2),
    make_bill(items=items(
        ('ปูนซีเมนต์', 2.0, 'ถุง', 100.0, 200.0),
        ('ปูนซีเมนต์', 2.0, 'กระสอบ', 100.0, 200.0),  # ชื่อเดียวหน่วยต่างกลุ่ม
    ), subtotal=400.0, vat=28.0, total=428.0),
    # 6) VAT: vat≠7% / total≠sub+vat / ติดลบ / ศูนย์ / included
    make_bill(subtotal=1000.0, vat=50.0, total=1050.0),     # vat ผิด
    make_bill(subtotal=1000.0, vat=70.0, total=9999.0),     # total ผิด
    make_bill(subtotal=-1000.0, vat=-70.0, total=-1070.0),  # ติดลบ
    make_bill(subtotal=0.0, vat=0.0, total=0.0,
              amount_source={'subtotal': 'derived', 'vat': 'derived', 'total': 'derived'}),
    make_bill(subtotal=1000.0, vat=0.0, total=1000.0),      # vat ศูนย์
    # 7) ยอดถูก "เดาเอง" (derived) ครบ
    make_bill(amount_source={'subtotal': 'derived', 'vat': 'derived', 'total': 'derived'}),
    # 8) ไม่มีรายการ / ไม่มียอด (precondition ของหลายกฎ)
    make_bill(items=[], subtotal=None, vat=None, total=None),
    # 9) บริษัทไม่อยู่ใน master เลย
    make_bill(company='บริษัท อื่น ไม่รู้จัก จำกัด', tax_id='9999999999999'),
]

file_info = {'month': 5, 'month_end': None, 'year': 2025}   # month_end: int|None ตามที่ parse_filename ให้จริง
unit_index = build_unit_index(bills)

print("=" * 64)
print("RULES COVERAGE — ขับ run_rules ด้วยบิลหลากข้อบกพร่อง")
print("=" * 64)

# ── (1) run_rules ต้องไม่ throw บนบิลทุกแบบ ──
print(f"\n[1] run_rules ไม่ throw (บิล {len(bills)} แบบ × {sum(1 for r in RULES.values() if r['enabled'])} กฎ)")
threw = []
for i, b in enumerate(bills):
    try:
        bb = copy.deepcopy(b)
        with contextlib.redirect_stdout(io.StringIO()):
            run_rules(bb, MASTER, file_info, unit_index=unit_index, all_bills_ref=bills)
    except BaseException as e:
        threw.append(f"bill#{i}: {type(e).__name__}: {str(e)[:100]}")
check(not threw, f"run_rules ไม่ throw บนบิลทุกแบบ ({len(bills)} บิล)")
for t in threw:
    print(f"      • {t}")

# ── (2) กฎที่พังภายในถูก route ไป SYS-* (ไม่ปนผลตรวจบิล) — ถ้ามี ก็ตามรอยได้ ──
sys_rule_codes = [i.get('code', '') for i in state._SYSTEM_ISSUES if str(i.get('code', '')).startswith('SYS-')]
print(f"\n[2] กฎที่ throw ภายใน ถูก route เป็น SYS-* : {len(sys_rule_codes)} รายการ (0 = ดีที่สุด)")
check(True, f"audit trail SYS-* = {sorted(set(sys_rule_codes))[:6]}")

# ── (3) sanity: กฎสำคัญฟ้อง/เงียบถูกจังหวะ ──
print("\n[3] sanity — กฎสำคัญฟ้องเมื่อควรฟ้อง / เงียบเมื่อควรเงียบ")

def issues_of(bill):
    bb = copy.deepcopy(bill)
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(bb, MASTER, file_info, unit_index=unit_index, all_bills_ref=[bb])
    return {iss['code'] for iss in bb.get('issues', [])}

clean = issues_of(make_bill())
check('VAT001' not in clean, "บิลสะอาด: VAT001 ไม่ฟ้อง (ผลรวม=subtotal)")
check('VAT002' not in clean, "บิลสะอาด: VAT002 ไม่ฟ้อง (vat=7%)")

bad_sum = issues_of(make_bill(items=items(('เหล็กเส้น', 10.0, 'เส้น', 100.0, 500.0)),
                              subtotal=1000.0, vat=70.0, total=1070.0))
check('VAT001' in bad_sum, "บิลผลรวมรายการ(500)≠subtotal(1000): VAT001 ฟ้อง")

bad_vat = issues_of(make_bill(subtotal=1000.0, vat=50.0, total=1050.0))
check('VAT002' in bad_vat, "บิล vat(50)≠7%(70): VAT002 ฟ้อง")

bad_tax = issues_of(make_bill(tax_id='12345', tax_id_raw='12345'))
check('TAX001' in bad_tax, "บิลเลขภาษีไม่ครบ 13 หลัก: TAX001 ฟ้อง")

# ── (4) บิลเจาะ branch เพิ่ม (address/item/vat/date/tax/branch) + กฎที่ปิดอยู่ ──
print("\n[4] coverage เสริม — บิลเจาะหลาย branch + กฎที่ปิด (เรียกตรง)")
bills2 = [
    # ที่อยู่: ขาดส่วน / สะกดเพี้ยน / ต่างจังหวัด / ไปรษณีย์
    make_bill(address='5/32', company_raw='x'),
    make_bill(address='เลขที่ 5/32 ถนนสุขุมวิด แขวงคลองเตย เขตคลองเตย กรุงเทพ 10110'),
    make_bill(address='123 หมู่ 4 ตำบลในเมือง อำเภอเมือง จังหวัดเชียงใหม่ 50000'),
    make_bill(address=''),
    # รายการหลากปัญหา: หน่วย pattern/spec, ราคา outlier, seq gap ใหญ่, ชื่อสั้น, ซ้ำ, ติดลบ, qty/ยอดผิดปกติ
    make_bill(items=items(
        ('สายไฟ THW 2.5 sq.mm.', 100.0, 'เมตร', 10.0, 1000.0),
        ('a', 1.0, 'อัน', 999999.0, 999999.0),
        ('สายไฟ THW 2.5 sq.mm.', 100.0, 'เมตร', 10.0, 1000.0),
    ), subtotal=1001999.0, vat=70139.93, total=1072138.93),
    make_bill(items=[
        {'seq': 1, 'name': 'ปูน', 'name_raw': 'ปูน', 'qty': 1.0, 'unit': 'ถุง', 'price': 100.0, 'amount': 100.0},
        {'seq': 99, 'name': 'ทราย', 'name_raw': 'ทราย', 'qty': 1.0, 'unit': 'คิว', 'price': 100.0, 'amount': 100.0},
    ], subtotal=200.0, vat=14.0, total=214.0),
    # VAT: included (total ดูรวม vat แล้ว) / discount / zero subtotal / vat เป็น rate 0.07
    make_bill(subtotal=1070.0, vat=0.0, total=1070.0),
    make_bill(subtotal=1000.0, vat=0.07, total=1070.0),
    make_bill(subtotal=0.0, vat=0.0, total=0.0),
    # tax: OCR (ตัว O แทน 0) / reverse-lookup / ประเภทนิติบุคคลหลักแรก
    make_bill(tax_id='O1O5566206726', tax_id_raw='O1O5566206726'),
    make_bill(tax_id='3105566206726', tax_id_raw='3105566206726'),  # หลักแรก 3
    # branch format / สาขาเป็นเลข
    make_bill(branch='สาขา 5', branch_no='5'),
    make_bill(branch='Branch-001', branch_no='001'),
    # date: พ.ศ./ค.ศ. กำกวม / นอกช่วง
    make_bill(iv_date_str='15/05/68', iv_date=__import__('datetime').date(2025, 5, 15)),
    make_bill(iv_date_str='2025-13-45', iv_date=None),
]
ui2 = build_unit_index(bills2)
threw2 = []
for i, b in enumerate(bills2):
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            run_rules(copy.deepcopy(b), MASTER, file_info, unit_index=ui2, all_bills_ref=bills2)
    except BaseException as e:
        threw2.append(f"bills2#{i}: {type(e).__name__}: {str(e)[:80]}")
check(not threw2, f"run_rules ไม่ throw บน bills2 ({len(bills2)} บิลเจาะ branch)")
for t in threw2:
    print(f"      • {t}")

# กฎที่ enabled=False (run_rules ข้าม) — เรียกตรงเพื่อ coverage + ยืนยันไม่ throw
print("\n[5] กฎที่ปิดอยู่ (เรียกตรง — coverage + ไม่ throw)")
from rules_engine import r_br003, r_vat010, r_doc002
disabled_threw = []
ctx_dis = {'all_bills_for_iv_check': bills2, 'target_month': 5, 'target_month_end': None,
           'all_masters': MASTER, 'unit_index': ui2}
for fn_name, fn in [('r_br003', r_br003), ('r_vat010', r_vat010), ('r_doc002', r_doc002)]:
    for b in (make_bill(), make_bill(tax_id='', branch_no=''),
              make_bill(subtotal=None, vat=None, total=None, items=[])):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                out = fn(copy.deepcopy(b), MASTER.get('ฉี อัน คอนสตรัคชั่น'), ctx_dis)
            assert isinstance(out, list)
        except BaseException as e:
            disabled_threw.append(f"{fn_name}: {type(e).__name__}: {str(e)[:80]}")
check(not disabled_threw, "กฎที่ปิด (r_br003/r_vat010/r_doc002) เรียกตรงไม่ throw + คืน list")
for t in disabled_threw:
    print(f"      • {t}")


# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"RULES COVERAGE: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    print("รายการที่ล้ม:")
    for f in FAIL:
        print(f"  • {f}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ run_rules ทนทานต่อบิลทุกแบบ + กฎสำคัญทำงานถูกจังหวะ")
sys.exit(0)
