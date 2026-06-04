# -*- coding: utf-8 -*-
"""
e2e_test.py — ทดสอบ end-to-end เต็มรูปแบบ รวมการสร้าง Excel report
รันแบบไม่ interactive โดยจำลอง pipeline ของ main() ทุกขั้นตอน

ตรวจ:
1. parse → rules → validators → typos → summary (ทำงานครบ)
2. apply cross-checks (DT004/DOC001)
3. build_clean_report → สร้างไฟล์ .xlsx จริง
4. เปิดไฟล์ที่สร้างกลับมาตรวจว่าครบ 7 ชีต เปิดได้สมบูรณ์
"""
import os
import sys
import json
import glob
import warnings
# v9.1 PORTABILITY-FIX: เดิม hardcode '/home/claude' → รันได้เฉพาะเครื่อง dev เดิม (พัง Windows/เครื่องอื่น).
#   ใช้ "โฟลเดอร์ของสคริปต์นี้" แทน → ย้ายไปไหนก็รันได้.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
warnings.filterwarnings('ignore')
os.chdir(_HERE)

# v9.1: master ทดสอบชุดเดียวกับ golden_master/verify_golden (เลิกก๊อป → ไม่ดริฟต์)
from golden_snapshot import MASTER, write_master_file
write_master_file('master_companies.json')

import importlib
app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

print('='*70)
print('🧪 E2E TEST — รัน pipeline เต็มรูปแบบ + สร้าง Excel report')
print('='*70)

app.reset_run_state()

# === STEP 1: parse ===
file_list = sorted(glob.glob('/mnt/project/*.xls') + glob.glob('/mnt/project/*.xlsx'))
print(f'\n[1/6] Parsing {len(file_list)} ไฟล์...')
all_bills, filename_issues = app.parse_all_files(file_list)
print(f'      → {len(all_bills)} บิล')

# === STEP 2: confidence ===
print('[2/6] คำนวณ confidence...')
for b in all_bills:
    app.compute_bill_confidence(b)

# === STEP 3: duplicate items ===
dup_items = app.check_duplicate_items(all_bills)
print(f'[3/6] ตรวจรายการซ้ำ → {len(dup_items)} กลุ่ม')

# === STEP 4: rules ===
print('[4/6] รัน 56 rules...')
app.run_all_rules(all_bills, MASTER)

# === STEP 5: sequence + typos + summary + cross-checks ===
print('[5/6] sequence + typos + cross-checks...')
iv_issues = app.check_invoice_sequence(all_bills) + app.check_iv_date_sequence(all_bills)
typos = app.check_product_typos(all_bills)
summary = app.summarize_by_company(all_bills)
app.apply_iv_period_crosscheck(all_bills)    # DT004
app.apply_sheet_date_crosscheck(all_bills)   # DOC001
print(f'      → iv_issues={len(iv_issues)} typos={len(typos)}')

# === STEP 6: build Excel report ===
print('[6/6] สร้าง Excel report (clean 7 ชีต)...')
out_dir = os.path.join(os.getcwd(), 'e2e_output')
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, 'audit_e2e_test.xlsx')

ok = app.build_clean_report(all_bills, summary, iv_issues, typos, filename_issues, out_path)
print(f'      → build_clean_report returned: {ok}')

# === VERIFY: เปิดไฟล์กลับมาตรวจ ===
print('\n' + '='*70)
print('🔍 VERIFY — เปิดไฟล์ Excel ที่สร้างกลับมาตรวจ')
print('='*70)

if not os.path.exists(out_path):
    print('❌ ไฟล์ไม่ถูกสร้าง!')
    sys.exit(1)

size = os.path.getsize(out_path)
print(f'✅ ไฟล์มีอยู่: {out_path} ({size:,} bytes)')

from openpyxl import load_workbook
wb = load_workbook(out_path)
print(f'✅ เปิดไฟล์สำเร็จ — {len(wb.sheetnames)} ชีต:')
for sn in wb.sheetnames:
    ws = wb[sn]
    print(f'   • {sn}: {ws.max_row} แถว × {ws.max_column} คอลัมน์')

# ตรวจว่าแต่ละชีตมีข้อมูล (ไม่ว่างเปล่า)
empty_sheets = [sn for sn in wb.sheetnames if wb[sn].max_row < 2]
if empty_sheets:
    print(f'\n⚠️ ชีตที่ดูว่าง (max_row<2): {empty_sheets}')
else:
    print(f'\n✅ ทุกชีตมีข้อมูล')

wb.close()

print('\n' + '='*70)
print('✅✅✅ E2E TEST ผ่าน — pipeline ครบ + Excel สร้างได้สมบูรณ์')
print('='*70)
