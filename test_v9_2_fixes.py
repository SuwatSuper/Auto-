# -*- coding: utf-8 -*-
"""test_v9_2_fixes.py — regression test สำหรับบั๊ก 4 ตัวที่แก้ใน v9.2

รันแบบ standalone (ไม่ใช่ pytest):  PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_v9_2_fixes.py

ครอบคลุม:
  FIX1  บิลหน้าต่อ — _is_seq_run รับลำดับไม่เริ่มที่ 1 (9,10,11,12) + ทนลำดับซ้ำ (5,5)
        แต่กันคอลัมน์ qty (1,1,1,1 / 20,10,…) → detect_item_columns บนหน้าต่อหา name เจอ
  FIX2  บาทตัวอักษร — _is_thai_amount_words + ไม่นับเป็นรายการ/ไม่ฟ้อง ITM016
  FIX4  VAT marker — _detect_vat_rows ไม่ตัดแถวรายการที่ qty=7, แต่จับแถว VAT ที่ติด label
  FIX3  ITM008 ปิดใน RULES — run_rules ไม่ปล่อย ITM008 แม้มี outlier (ฟังก์ชัน r_itm008 ยังอยู่)
  INTG  ไฟล์จริง: TKH_69_0462 (merge หน้าต่อ → 12 รายการ), KNT_69_051 ช.23 (4 รายการ)
"""
from __future__ import annotations
import os, sys
import pandas as pd

import parser as P
import rules_engine as R

PASS = 0
FAIL = []

def check(cond, msg):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL.append(msg)
        print(f"  ❌ {msg}")

DATA = os.environ.get('PUOPUY_DATA_DIR', '/mnt/project')

# ───────────────────────── FIX1: _is_seq_run ─────────────────────────
print("\n[FIX1] _is_seq_run — ลำดับสินค้า (หน้าแรก/หน้าต่อ/ลำดับซ้ำ) vs qty")
check(P._is_seq_run([1,2,3,4,5,6,7,8]) is True,  "[1..8] หน้าแรก → seq")
check(P._is_seq_run([1,2,4]) is True,            "[1,2,4] มี gap เล็ก → seq (คงเดิม)")
check(P._is_seq_run([9,10,11,12]) is True,       "[9,10,11,12] หน้าต่อ → seq (FIX)")
check(P._is_seq_run([1,2,3,4,5,5,6,7]) is True,  "[..5,5..] คีย์ลำดับซ้ำ → seq (ทนได้)")
check(P._is_seq_run([1,1,1,1]) is False,         "[1,1,1,1] qty ค่าเดียวซ้ำ → ไม่ใช่ seq")
check(P._is_seq_run([20,10,10,1,1,1,1,1]) is False, "[20,10,…] qty ไม่ไล่ขึ้น → ไม่ใช่ seq")
check(P._is_seq_run([1]) is True,                "[1] รายการเดียวเริ่ม 1 → seq")
check(P._is_seq_run([5]) is False,               "[5] เดี่ยวไม่ใช่ 1 → ไม่ใช่ seq")
check(P._is_seq_run([2,5,9,14]) is False,        "[2,5,9,14] กระจายกว้าง → ไม่ใช่ seq (กัน)")

# detect_item_columns บน "หน้าต่อ" (seq เริ่ม 9) ต้องหา name เจอ (seq อยู่ซ้ายของ name)
cont = pd.DataFrame([
    ['9',  'สินค้า A', 'set', '1', '100', '', '100'],
    ['10', 'สินค้า B', 'set', '1', '200', '', '200'],
    ['11', 'สินค้า C', 'set', '1', '300', '', '300'],
    ['12', 'สินค้า D', 'set', '1', '400', '', '400'],
])
cols = P.detect_item_columns(cont)
check(cols[0] == 0, f"หน้าต่อ: seq_col=0 (ได้ {cols[0]})")
check(cols[1] is not None, f"หน้าต่อ: name_col ไม่เป็น None (ได้ {cols[1]})")

# ───────────────────────── FIX2: บาทตัวอักษร ─────────────────────────
print("\n[FIX2] _is_thai_amount_words — ยอดเป็นคำ vs ชื่อสินค้า")
for s in ['สองแสนแปดหมื่นสี่พันแปดร้อยสาม',
          'ห้าแสนแปดพันสองร้อยห้าสิบบาทถ้วน',
          'หกหมื่นสี่พันหกร้อยห้าสิบเจ็ดบาทเก้าสิบเอ็ดสตางค์']:
    check(P._is_thai_amount_words(s) is True, f"ยอดเป็นคำ → True : {s[:28]}")
for s in ['แผ่นสเตนเลส 304 2B ผิวมัน 0.7 มม.', 'เครื่องฉีดน้ำแรงดันสูง 1500 บาร์',
          'ตราว่าว แป้งอเนกประสงค์ 1 กก.', 'ชุดกันสารเคมีแรงดันสูง']:
    check(P._is_thai_amount_words(s) is False, f"ชื่อสินค้า → False : {s[:28]}")

# บาทตัวอักษร (seq ว่าง) แทรกในบล็อก → ต้องไม่ถูกนับเป็นรายการ + ไม่ฟ้อง ITM016
df_bt = pd.DataFrame([
    ['เลขที่','','','','','','IV99999'],
    ['บริษัท ทดสอบ จำกัด','','','','','',''],
    ['1','สินค้า ก','ชิ้น','2','50','','100'],
    ['2','สินค้า ข','ชิ้น','3','100','','300'],
    ['','สี่ร้อยบาทถ้วน','','','','','400'],
    ['','','ภาษีมูลค่าเพิ่ม','','','0.07','28'],
    ['','','รวมทั้งสิ้น','','','','428'],
])
bills_bt = P.parse_sheet(df_bt, 'BT', 'bt.xls')
nit = len(bills_bt[0]['items']) if bills_bt else -1
i016 = sum(1 for b in bills_bt for i in b.get('issues',[]) if i.get('code')=='ITM016')
check(nit == 2, f"บาทตัวอักษรไม่ถูกนับเป็นรายการ (ได้ {nit} รายการ ควร 2)")
check(i016 == 0, f"ไม่ฟ้อง ITM016 จากบาทตัวอักษร (ได้ {i016})")

# ───────────────────────── FIX4: VAT marker ─────────────────────────
print("\n[FIX4] _detect_vat_rows — qty=7 ไม่ใช่ VAT, แต่ label+7 = VAT")
# แถวรายการที่ qty=7 (ไม่มี label ภาษี) → ต้องไม่ใช่ VAT row
df_q7 = pd.DataFrame([
    ['1','เหล็ก','','','','','','','','','','','7','เส้น','100','0','700'],
    ['2','ไม้','','','','','','','','','','','7','เส้น','50','0','350'],
])
vr_q7 = P._detect_vat_rows(df_q7)
check(0 not in vr_q7 and 1 not in vr_q7, f"แถว qty=7 ไม่ถูกนับเป็น VAT (ได้ vat_rows={vr_q7})")
# แถวที่มี label 'ภาษีมูลค่าเพิ่ม' + '7' → ต้องเป็น VAT row
df_v7 = pd.DataFrame([['สินค้า','','','',''], ['เหล็ก','','','','100'],
                      ['','','ภาษีมูลค่าเพิ่ม','','7'], ['','','รวม','','107']])
check(2 in P._detect_vat_rows(df_v7), "แถว label ภาษี + 7 → เป็น VAT row (คงเจตนาเดิม)")
# แถว 0.07 (numeric) → VAT เสมอ
df_007 = pd.DataFrame([['x', 0.07]])
check(0 in P._detect_vat_rows(df_007), "0.07 numeric → VAT row")

# ───────────────────────── FIX3: ITM008 ปิด ─────────────────────────
print("\n[FIX3] ITM008 ปิดใน RULES (run_rules ไม่ปล่อย) — ฟังก์ชันยังอยู่")
check(R.RULES['ITM008']['enabled'] is False, "RULES['ITM008'].enabled == False")
check(callable(R.r_itm008), "ฟังก์ชัน r_itm008 ยังคงอยู่ (เปิดคืนได้)")
# บิล outlier ราคา/หน่วย: ผ่าน run_rules ต้องไม่มี ITM008
oi = [{'seq':i,'name':f'ของ{i}','qty':1,'unit':'ชิ้น','price':100,'amount':100,
       'name_raw':f'ของ{i}'} for i in range(1,6)]
oi.append({'seq':6,'name':'ของแพง','qty':1,'unit':'ชิ้น','price':100000,'amount':100000,'name_raw':'ของแพง'})
bill = {'company':'บ. ทดสอบ จำกัด','branch':'','branch_no':'','tax_id':'0105500000017','address':'',
        'iv_number':'IV1','iv_date':None,'iv_date_str':'','items':oi,
        'subtotal':100500,'vat':7035,'total':107535,'issues':[],'sheet':'1','file':'t.xls'}
R.run_rules(bill, {}, {'month':None,'month_end':None})
itm008_fired = [i for i in bill['issues'] if i.get('code')=='ITM008']
check(len(itm008_fired) == 0, f"run_rules ไม่ปล่อย ITM008 (ได้ {len(itm008_fired)})")

# ───────────────────────── INTG: ไฟล์จริง ─────────────────────────
print("\n[INTG] ไฟล์จริง (ถ้ามี) — หน้าต่อ merge + รายการครบ")
def _bills(fn):
    p = os.path.join(DATA, fn)
    return P.parse_file(p) if os.path.exists(p) else None

bb = _bills('TKH_69_0462.xls')
if bb is None:
    print("  ⏭️  ข้าม (ไม่พบ TKH_69_0462.xls)")
else:
    target = [b for b in bb if (b.get('iv_number') or '') == 'CB69040146']
    check(len(target) == 1, f"TKH_69_0462: IV CB69040146 = 1 บิล (merge หน้าต่อ) (ได้ {len(target)})")
    if target:
        n = len(target[0]['items'])
        check(n == 12, f"TKH_69_0462: บิลนั้นมี 12 รายการ (#1-12) (ได้ {n})")
        check(abs((target[0].get('subtotal') or 0) - 1530235.72) < 1.0,
              f"TKH_69_0462: subtotal ≈ 1,530,235.72 (ได้ {target[0].get('subtotal')})")

bk = _bills('KNT_69_051.xls')
if bk is None:
    print("  ⏭️  ข้าม (ไม่พบ KNT_69_051.xls)")
else:
    t23 = [b for b in bk if (b.get('iv_number') or '') == 'IV6905637']
    check(len(t23) == 1, f"KNT_69_051: IV6905637 = 1 บิล (ได้ {len(t23)})")
    if t23:
        n = len(t23[0]['items'])
        check(n == 4, f"KNT_69_051 ช.23: 4 รายการ (เดิมพังเหลือ 2) (ได้ {n})")
        check(abs((t23[0].get('subtotal') or 0) - 60428.0) < 1.0,
              f"KNT_69_051 ช.23: subtotal = 60,428 (ได้ {t23[0].get('subtotal')})")

# ───────────────────────── สรุป ─────────────────────────
print("\n" + "="*64)
print(f"V9.2 FIXES: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("="*64)
if FAIL:
    for m in FAIL:
        print("  •", m)
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ บั๊ก 4 ตัวถูกแก้และมี regression guard ครบ")
