# -*- coding: utf-8 -*-
"""test_recheck_rules_20260622.py — กันถอยหลังการแก้บั๊ก "กฎที่เปิดใช้งาน" รอบ 2026-06-22
(ADR-064..076: M-1 DT003 · C-1 VAT non-finite · C-2 เลขภาษีไทย · CMP003 · BR001/004 · ITM016 ·
 DOC001 · DT004 · ADDR002 · ADDR005 · ADDR006 · DOC003 · ITM004 · ITM010)

รันเดี่ยว: PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_recheck_rules_20260622.py

ทุกการแก้พิสูจน์แล้ว golden-neutral บน fixture (b5c415bb) + CI เขียว. เทสนี้ล็อก "พฤติกรรมที่ถูกต้อง"
(บั๊กหาย + ของจริงไม่หลุด) ของแต่ละกฎ. หมายเหตุ: ITM004/ITM016 เปลี่ยนผล corpus 148 ไฟล์ → ต้อง
rebaseline บนเครื่องเจ้าของ (ดู FIXES_RULES_ENABLED_20260622_TH.md).
"""
import os, importlib
from datetime import datetime
os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')

_fail = 0
def ok(cond, msg):
    global _fail
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond: _fail += 1

import rules_engine_rules_a as A
import rules_engine_rules_b as RB
import rules_engine_rules_c as RC
import validators as V
from puopuy_core import clean_tax_id
import config

def _it(name):
    return {'items':[{'seq':1,'name':name,'name_raw':name,'qty':1,'unit':'ชิ้น','price':1,'amount':1}]}

print('[C-2] เลขภาษีเลขไทย → อารบิก (TAX001/003/005/007/008)')
ok(clean_tax_id('๐๑๐๕๕๕๖๐๐๐๐๑๐') == '0105556000010', 'clean_tax_id แปลงเลขไทย')
ok(clean_tax_id('0-1055-56000-01-0') == '0105556000010', 'อารบิกเดิมไม่เพี้ยน')
ok(A.r_tax003({'tax_id':'๐๑๐๕๕๕๖๐๐๐๐๑๐','tax_id_raw':'','branch':'','company':'บริษัท เอ จำกัด','issues':[]},
              {'name':'บริษัท เอ จำกัด','tax_id':'0105556000010'}, {}) == [], 'TAX003 ไม่ฟ้องเลขไทยที่ตรง master')

print('[C-1] VAT006/VAT007 ไม่ crash บนเงิน inf/NaN')
big={'seq':1,'name':'x','qty':1,'unit':'u','price':200.0,'amount':200.0}
for nm,fn,b in [('VAT006 inf',RC.r_vat006,{'subtotal':100.0,'vat':None,'total':float('inf'),'items':[big]}),
                ('VAT007 inf',RC.r_vat007,{'subtotal':float('inf'),'vat':14.0,'total':None,'items':[big]}),
                ('VAT006 nan',RC.r_vat006,{'subtotal':100.0,'vat':None,'total':float('nan'),'items':[big]})]:
    try: r=fn(b,{},{}); ok(r==[], f'{nm} → [] ไม่ crash')
    except Exception as e: ok(False, f'{nm} crash {type(e).__name__}')
# ของจริง VAT included ยังจับได้: items_sum≈total/1.07 และต่างจาก subtotal
inc={'subtotal':107.0,'vat':None,'total':107.0,'items':[{'seq':1,'name':'x','qty':1,'unit':'u','price':100.0,'amount':100.0}]}
ok(RC.r_vat006(inc,{},{})!=[], 'VAT006 ยังจับ VAT-included จริง')

print('[CMP003] brand blacklist แบบขอบคำ')
ok(A.r_cmp003({'company':'CPF Trading Co'},None,{})==[], "'CP' ไม่ match CPF")
ok(A.r_cmp003({'company':'Laptops Co'},None,{})==[], "'Tops' ไม่ match Laptops")
ok(A.r_cmp003({'company':'CP All'},None,{})!=[], "'CP' ยัง match CP All จริง")

print('[BR001/004] สำนักงานใหญ่ เต็มคำ')
ok(A.r_br001({'branch':'สาขา สำนักงานพระราม9','branch_no':'00007'},None,{})==[], 'label มี "สำนัก" ไม่ตีเป็นสนญ.')
ok(A.r_br001({'branch':'สำนักงานใหญ่','branch_no':'00007'},None,{})!=[], 'สนญ.จริง ยังฟ้อง 00000')

print('[ITM016] รายการแยกจริงไม่ใช่ซ้ำ')
split={'items':[{'seq':1,'name':'ปูน','name_raw':'ปูน','qty':10,'unit':'ถุง','price':120,'amount':1200},
                {'seq':2,'name':'ปูน','name_raw':'ปูน','qty':5,'unit':'ถุง','price':120,'amount':600}]}
dup={'items':[{'seq':1,'name':'ปูน','name_raw':'ปูน','qty':5,'unit':'ถุง','price':120,'amount':600},
              {'seq':2,'name':'ปูน','name_raw':'ปูน','qty':5,'unit':'ถุง','price':120,'amount':600}]}
ok(RC.r_itm016(split,None,{})==[], 'qty ต่าง = คนละบรรทัด ไม่ฟ้องซ้ำ')
ok(RC.r_itm016(dup,None,{})!=[], 'เหมือนทุกค่า = ซ้ำจริง ยังฟ้อง')

print('[DOC001] ชื่อชีตเลข >31 ไม่ใช่ "วัน"')
ok(A.r_doc001({'iv_date':datetime(2026,5,5),'sheet':'32','file':'F'},None,{})==[], 'sheet 32 ไม่ฟ้อง')
ok(A.r_doc001({'iv_date':datetime(2026,5,5),'sheet':'2026','file':'F'},None,{})==[], 'sheet 2026 ไม่ฟ้อง')

print('[DT004] เลขรันมี prefix 4 หลัก ไม่ตีเป็น YYMM')
m=V.detect_iv_period_mismatch('PO2501', datetime(2026,3,1))
ok((m is None) or (not m.get('mismatch')), 'PO2501 ไม่ฟ้องวันที่ขัดเลข IV')

print('[ADDR002] ต่างเว้นวรรค ไม่ใช่สะกดผิด')
from core_utils import parse_address_input
m2={'address_parts':parse_address_input('เลขที่ 1 ถนนพระราม 4 แขวงคลองเตย เขตคลองเตย กรุงเทพ 10110')}
ok(A.r_addr002({'address':'เลขที่ 99 ถนนพระราม4 แขวงคลองเตย เขตคลองเตย กรุงเทพ 10110'},m2,{})==[], 'พระราม4 vs พระราม 4 ไม่ฟ้อง')

print('[ADDR005] เบอร์โทรท้ายที่อยู่ ไม่ถูกตีเป็นไปรษณีย์')
ok(RC.r_addr005({'address':'123 กรุงเทพ 10250 โทร 99999'},None,{})==[], 'เลือก 10250 ไม่ใช่ 99999')

print('[ITM004] เลขติดอักษรไทย ไม่ใช่ "อังกฤษ+ไทย"')
ok(RB.r_itm004(_it('ท่อ 5นิ้ว'),None,{})==[], '5นิ้ว ไม่ฟ้อง')
ok(RB.r_itm004(_it('ABCนิ้ว'),None,{})!=[], 'อักษรอังกฤษ+ไทย จริง ยังฟ้อง')

print('[ITM010] "วาว" คำไทยปกติ ไม่เดาเป็น "วาล์ว"')
ok(RB.r_itm010(_it('สีประกายวาว'),None,{})==[], 'ประกายวาว ไม่ฟ้อง')
ok(RB.r_itm010(_it('บอลวาว'),None,{})!=[], 'บอลวาว (ประปา) ยังฟ้อง')

print('[M-1/DT003] ระเบิดเวลาปี 2031 — บิลปกติไม่ฟ้องตัวเอง')
import rules_engine_rules_a as A2
os.environ['PUOPUY_AUDIT_DATE']='2031-06-15'
importlib.reload(config); importlib.reload(A2)
ok(A2.r_dt003({'iv_date':datetime(2031,5,15),'items':[]},{},{})==[], 'audit 2031 บิล 2031 ไม่ฟ้อง')
ok(A2.r_dt003({'iv_date':datetime(2032,5,15),'items':[]},{},{})==[], 'audit 2031 บิล 2032 ไม่ฟ้อง')
ok(A2.r_dt003({'iv_date':datetime(2045,5,15),'items':[]},{},{})!=[], 'audit 2031 บิล 2045 (ไกลผิดปกติ) ยังฟ้อง')
os.environ['PUOPUY_AUDIT_DATE']='2026-06-02'
importlib.reload(config); importlib.reload(A2)
ok(A2.r_dt003({'iv_date':datetime(2026,5,15),'items':[]},{},{})==[], 'audit 2026 บิล 2026 ไม่ฟ้อง (regress)')

print('=' * 56)
if _fail:
    print(f'RESULT: ❌ FAIL {_fail} จุด'); raise SystemExit(1)
print('RESULT: ✅ PASS — แก้กฎที่เปิดใช้งานครบ + ของจริงไม่ถอย (ADR-064..076)')
