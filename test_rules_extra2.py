# -*- coding: utf-8 -*-
"""test_rules_extra2.py — [OBJ-1D ต่อยอด รอบ 2] ดัน rules_engine.py ให้สูงกว่า 90% ต่อ

แตะกิ่งที่เหลือ 2 กลุ่ม:
  1) กิ่ง "guard / degrade ปลอดภัย": กฎต้องไม่ crash เมื่อรับบิลพิการ (None / ค่าอ่านไม่ได้)
     — ทุกกฎที่มี try/except ของตัวเอง ต้องคืน [] ไม่โยน exception (สัญญาความทนทาน)
  2) กิ่งฟ้อง/กิ่งเงื่อนไขเฉพาะ ที่ข้อมูลจริงไม่วิ่งผ่าน (range เดือน, digit swap, สาขาปนกัน ฯลฯ)
  3) run_rules SYS-handler: ฉีดกฎที่โยน exception → ต้อง route ไป log_system_issue ไม่ปนผลบิล

ทุก assert ผูกกับพฤติกรรมที่ควรเป็น. เป็น pure check → ไม่กระทบ golden hash.
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_rules_extra2.py
"""
import os
import sys
import io
import contextlib
import warnings
import datetime as dt

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import state
import rules_engine as R

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def fires(out, label, must_contain=None):
    ok = bool(out)
    if ok and must_contain is not None:
        ok = any(must_contain in str(x) for x in out)
    check(ok, label + ("" if ok else f"  → {out}"))


def silent(out, label):
    check(out == [] or out is None, label + (f"  (ควรเงียบ ได้ {out})" if out else ""))


M = {'name': 'บริษัท ทดสอบ ระบบ จำกัด', 'name_alt': '', 'tax_id': '0105566206726',
     'branch': 'สำนักงานใหญ่', 'address': 'เลขที่ 99 ถนนพระราม4 กรุงเทพมหานคร 10110',
     'iv_prefix': 'IV'}


def ctx(**over):
    c = {'sheet_name': '1', 'target_month': None, 'target_month_end': None,
         'all_masters': {'ทดสอบ': M}, 'unit_index': None, 'all_bills_for_iv_check': []}
    c.update(over)
    return c


def item(seq, name, qty, unit, price, amount, name_raw=None):
    return {'seq': seq, 'name': name, 'name_raw': name_raw if name_raw is not None else name,
            'qty': qty, 'unit': unit, 'price': price, 'amount': amount}


def base_bill(**over):
    b = {'company': 'บริษัท ทดสอบ ระบบ จำกัด', 'company_raw': '', 'tax_id': '0105566206726',
         'tax_id_raw': '0105566206726', 'address': '', 'branch': '', 'branch_no': '',
         'iv_number': '', 'iv_number_raw': '', 'iv_date': None, 'sheet': '1',
         'items': [], 'subtotal': None, 'vat': None, 'total': None, 'issues': [], 'file': 'KRR_69_05.xls'}
    b.update(over)
    return b


print("=" * 64)
print("RULES EXTRA 2 — guard/degrade + กิ่งเฉพาะ + SYS-handler")
print("=" * 64)

# ─────────────────────────────────────────────────────────────
print("\n[R1] helpers + guard ต้น ๆ")
check(R.normalize_company_name(None) == '', "normalize_company_name(None) → '' (137)")
check(R.validate_company_prefix('') is False, "validate_company_prefix('') → False (158)")
fires(R.r_cmp002(base_bill(company=''), M, ctx()), "CMP002 ไม่มีชื่อบริษัท → 'ไม่พบชื่อบริษัท' (165)",
      must_contain='ไม่พบ')
silent(R.r_cmp004({'company': '', 'company_raw': ''}, M, ctx()), "CMP004 ค่า raw ว่าง → เงียบ (194)")

# ─────────────────────────────────────────────────────────────
print("\n[R2] กิ่งเฉพาะที่ข้อมูลจริงไม่วิ่งผ่าน")
# TAX003: bill 12 หลัก = master 13 หลัก (ขาด 0 นำ) → ฟ้องแบบ '12 หลัก' (332)
fires(R.r_tax003(base_bill(tax_id='105566206726'), {'tax_id': '0105566206726', 'name': 'X'}, ctx()),
      "TAX003 bill 12 หลัก = master '0'+12 → ฟ้อง (332)", must_contain='12 หลัก')
# IV001: มี prefix แต่ไม่มี context bills → return [] (417)
silent(R.r_iv001(base_bill(iv_number='IV6905001'), M, ctx(all_bills_for_iv_check=[])),
       "IV001 ไม่มี context bills → เงียบ (417)")
# IV001: 2 บิล prefix A/B (50/50) — dominant <80% → return [] (439)
b_iv = base_bill(iv_number='XY6905001', tax_id='0105566206726')
others = [base_bill(iv_number='AB6905002', tax_id='0105566206726'),
          base_bill(iv_number='CD6905003', tax_id='0105566206726')]
silent(R.r_iv001(b_iv, M, ctx(all_bills_for_iv_check=others)),
       "IV001 prefix บิลนี้ต่างจากกลุ่ม แต่กลุ่มไม่เด่นชัด (<80%) → เงียบ (439)")
# DT001: มีช่วงเดือน (target_month_end) แต่วันที่นอกช่วง → ฟ้อง (448-449)
fires(R.r_dt001(base_bill(iv_date=dt.date(2026, 5, 10)), M, ctx(target_month=3, target_month_end=4)),
      "DT001 วันที่เดือน 5 นอกช่วง 03-04 → ฟ้อง (448-449)", must_contain='ไม่อยู่ในช่วง')
# DT003: iv_date.year throw (string) → except → [] (493-494)
silent(R.r_dt003(base_bill(iv_date='ไม่ใช่วันที่'), M, ctx()), "DT003 iv_date พิการ → except เงียบ (493-494)")
# ITM002: seq แปลงเป็นเลขไม่ได้ → except pass (529)
silent(R.r_itm002(base_bill(items=[item('abc', 'ของ', 1, 'ชิ้น', 10, 10)]), M, ctx()),
       "ITM002 seq ไม่ใช่ตัวเลข → except pass (529)")
# ITM005: decor (ม่าน) แต่หน่วยไม่ใช่หน่วย decor → ฟ้อง (708-710)
fires(R.r_itm005(base_bill(items=[item(1, 'ม่านปรับแสง', 1, 'กก.', 100, 100)]), M, ctx()),
      "ITM005 ม่าน + หน่วย 'กก.' (ไม่ใช่ decor) → ฟ้อง (708-710)", must_contain='decor')
# validate_product_word: เริ่มต้น whitelist None → สร้างใหม่ (923)
state._PRODUCT_WHITELIST = None
res_w = R.validate_product_word('เหล็ก')
check(isinstance(res_w, dict) and 'status' in res_w, "validate_product_word เริ่ม whitelist None → init แล้วทำงาน (923)")
# VAT001: subtotal อ่านเป็น Decimal ไม่ได้ → _D None → return [] (990)
silent(R.r_vat001(base_bill(subtotal='ไม่ใช่เลข', items=[item(1, 'x', 1, 'ชิ้น', 10, 10)]), M, ctx()),
       "VAT001 subtotal แปลง Decimal ไม่ได้ → เงียบ (990)")

# ─────────────────────────────────────────────────────────────
print("\n[R3] DT004 / ITM016 / ITM018 / VAT008-009 — กิ่งฟ้อง/guard")
fires(R.r_dt004(base_bill(iv_date=dt.date(2060, 5, 1)), M, ctx()),
      "DT004 ปี ค.ศ. 2060 > 2057 → ฟ้อง (digit สลับ)", must_contain='เกินช่วง')
fires(R.r_dt004(base_bill(iv_date=dt.date(2010, 5, 1)), M, ctx()),
      "DT004 ปี ค.ศ. 2010 < 2012 → ฟ้อง (เก่าเกิน)", must_contain='ก่อน')
# ITM016: ชื่อว่าง → ข้าม (1318) + รายการซ้ำจริง → ฟ้อง
fires(R.r_itm016(base_bill(items=[
        item(1, '', 1, 'ชิ้น', 10, 10),                 # ชื่อว่าง → continue (1318)
        item(2, 'เหล็กเส้น', 1, 'เส้น', 50, 50),
        item(3, 'เหล็กเส้น', 1, 'เส้น', 50, 50)]), M, ctx()),
      "ITM016 ข้ามชื่อว่าง (1318) + จับรายการซ้ำจริง", must_contain='ซ้ำ')
# ITM018: qty เป็นข้อความ → except continue (1347-1348) ; และ qty=0 amount!=0 → ฟ้อง
fires(R.r_itm018(base_bill(items=[
        item(1, 'ของแปลก', 'abc', 'ชิ้น', 10, 10),       # qty='abc' → float() fail → continue (1347-1348)
        item(2, 'ของศูนย์', 0, 'ชิ้น', 10, 500)]), M, ctx()),
      "ITM018 qty ข้อความ → ข้าม (1347-1348) + qty=0 amount≠0 → ฟ้อง", must_contain='qty=0')
# VAT008: vat=None → return [] (1385)
silent(R.r_vat008(base_bill(vat=None, total=50000, items=[item(1, 'x', 1, 'ชิ้น', 100, 100)]), M, ctx()),
       "VAT008 vat=None → เงียบ (1385)")
# VAT008: vat แปลงเป็นเลขไม่ได้ → return [] (1390-1391)
silent(R.r_vat008(base_bill(vat='ไม่ใช่เลข', total=50000, items=[item(1, 'x', 1, 'ชิ้น', 100, 100)]), M, ctx()),
       "VAT008 vat อ่านไม่ได้ → เงียบ (1390-1391)")
# VAT008: fire — vat=0, total สูง, subtotal ต่างจาก total
fires(R.r_vat008(base_bill(vat=0, total=50000, subtotal=10000,
                           items=[item(1, 'x', 1, 'ชิ้น', 100, 100)]), M, ctx()),
      "VAT008 vat=0 ทั้งที่ยอดสูง → ฟ้อง", must_contain='VAT เป็น 0')
# VAT009: ไม่มี subtotal แต่มี total → ฟ้อง (1413-1414)
fires(R.r_vat009(base_bill(subtotal=None, total=1070, items=[item(1, 'x', 1, 'ชิ้น', 100, 100)]), M, ctx()),
      "VAT009 มี total ไม่มี subtotal → ฟ้อง", must_contain='ไม่มี subtotal')
# VAT009: ไม่มีทั้ง subtotal/total → return [] (1415)
silent(R.r_vat009(base_bill(subtotal=None, total=None, items=[item(1, 'x', 1, 'ชิ้น', 100, 100)]), M, ctx()),
       "VAT009 ไม่มี subtotal/total → เงียบ (1415)")
# VAT009: subtotal=0 ทั้งที่มีรายการ → ฟ้อง (1420-1421)
fires(R.r_vat009(base_bill(subtotal=0, items=[item(1, 'x', 1, 'ชิ้น', 100, 100)]), M, ctx()),
      "VAT009 subtotal=0 ทั้งที่มีรายการ → ฟ้อง", must_contain='subtotal=0')

# ─────────────────────────────────────────────────────────────
print("\n[R4] BR003 / DOC003 — context guard")
silent(R.r_br003(base_bill(), M, ctx(all_bills_for_iv_check=[])), "BR003 ไม่มี context bills → เงียบ (1206)")
# BR003: มี bills แต่คนละ tax → same_company_branches ว่าง → [] (1220)
silent(R.r_br003(base_bill(tax_id='0105566206726', branch_no='00001'), M,
                 ctx(all_bills_for_iv_check=[base_bill(tax_id='9999999999999', branch_no='00002')])),
       "BR003 ไม่มีบิล vendor เดียวกัน → เงียบ (1220)")
# BR003: vendor เดียวกันแต่สาขาเหมือนกันหมด → ไม่ปนกัน → [] (1227)
silent(R.r_br003(base_bill(tax_id='0105566206726', branch_no='00001'), M,
                 ctx(all_bills_for_iv_check=[base_bill(tax_id='0105566206726', branch_no='00001')])),
       "BR003 vendor เดียวกัน สาขาเหมือนกัน → ไม่ฟ้อง (1227)")
# BR003: fire — สำนักงานใหญ่ปนสาขา
fires(R.r_br003(base_bill(tax_id='0105566206726', branch_no='00000'), M,
                ctx(all_bills_for_iv_check=[base_bill(tax_id='0105566206726', branch_no='00007')])),
      "BR003 สำนักงานใหญ่ปนสาขาในไฟล์เดียว → ฟ้อง", must_contain='สำนักงานใหญ่')
silent(R.r_doc003(base_bill(iv_number='IV01'), M, ctx(all_bills_for_iv_check=[])),
       "DOC003 ไม่มี context bills → เงียบ (1240)")
silent(R.r_cmp005(base_bill(company=''), M, ctx()), "CMP005 ชื่อบริษัทว่าง → เงียบ (1111)")

# ─────────────────────────────────────────────────────────────
print("\n[R5] degrade ปลอดภัย — กฎมี try/except ของตัวเอง รับบิล None ต้องไม่ crash")
for name, fn in [('CMP002', R.r_cmp002), ('VAT005', R.r_vat005), ('CMP005', R.r_cmp005),
                 ('ADDR004', R.r_addr004), ('ADDR005', R.r_addr005), ('TAX007', R.r_tax007),
                 ('DT004', R.r_dt004), ('ITM016', R.r_itm016), ('ITM018', R.r_itm018),
                 ('VAT008', R.r_vat008), ('VAT009', R.r_vat009),
                 ('BR003', R.r_br003), ('DOC003', R.r_doc003), ('TAX007', R.r_tax007)]:
    try:
        out = fn(None, M, ctx())
        ok = (out == [])
    except Exception:
        ok = False
    check(ok, f"{name}(bill=None) → except ภายในกฎ คืน [] ไม่ crash")

# ─────────────────────────────────────────────────────────────
print("\n[R6] run_rules SYS-handler — ฉีดกฎที่โยน exception → log SYS ไม่ปนผลบิล (1528-1535)")
_inject_code = 'ZZZTEST'
R.RULES[_inject_code] = {
    'name': 'กฎทดสอบที่จงใจพัง', 'severity': 'INFO', 'category': 'TEST', 'enabled': True,
    'check': lambda b, m, c: (_ for _ in ()).throw(RuntimeError('forced-rule-failure (test)')),
}
try:
    bill = base_bill(company='บริษัท ทดสอบ ระบบ จำกัด')
    with contextlib.redirect_stdout(io.StringIO()):
        out_bill = R.run_rules(bill, {'ทดสอบ': M}, {'month': None})
    # กฎพังต้องไม่โยนออกมา และต้องไม่ทิ้ง issue ของกฎพังลง bill (route ไป System Issues)
    leaked = any(i.get('code') == _inject_code for i in out_bill['issues'])
    check(out_bill is bill and not leaked,
          "กฎพัง → run_rules ไม่ crash + ไม่ปน issue ลงบิล (route ไป SYS log)")
finally:
    R.RULES.pop(_inject_code, None)
check(_inject_code not in R.RULES, "ถอนกฎทดสอบออกจาก RULES (ไม่ทิ้ง state ค้าง)")

# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
if FAIL:
    print(f"RULES EXTRA 2: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    print("=" * 64)
    sys.exit(1)
else:
    print(f"RULES EXTRA 2: ผ่าน {PASS} / ล้มเหลว 0")
    print("=" * 64)
    print("RESULT: ✅ guard/degrade + กิ่งเฉพาะ + SYS-handler ครบ + ไม่กระทบ golden hash")
    sys.exit(0)
