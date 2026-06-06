import warnings; warnings.filterwarnings('ignore')
import os, sys, glob, hashlib, importlib, re, contextlib, io
sys.path.insert(0, os.getcwd())
from golden_snapshot import MASTER, write_master_file
write_master_file('master_companies.json')
app=importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
app.reset_run_state()
fl=sorted(glob.glob('/mnt/project/*.xls')+glob.glob('/mnt/project/*.xlsx'))
all_bills, filename_issues = app.parse_all_files(fl)
for b in all_bills: app.compute_bill_confidence(b)
app.check_duplicate_items(all_bills); app.run_all_rules(all_bills, MASTER)
iv_issues=app.check_invoice_sequence(all_bills)+app.check_iv_date_sequence(all_bills)
typos=app.check_product_typos(all_bills); summary=app.summarize_by_company(all_bills)
app.apply_iv_period_crosscheck(all_bills); app.apply_sheet_date_crosscheck(all_bills)
out='/tmp/_rd_%d.xlsx'%os.getpid()
with contextlib.redirect_stdout(io.StringIO()):
    app.build_clean_report(all_bills, summary, iv_issues, typos, filename_issues, out)
import openpyxl
# normalize ONLY wall-clock stamps (มี HH:MM) — วันที่ใบกำกับจริงไม่มีเวลา จึงไม่โดน
TS=re.compile(r'\d{2}/\d{2}/\d{4} \d{2}:\d{2}|\d{4}-\d{2}-\d{2} \d{2}:\d{2}')
wb=openpyxl.load_workbook(out, data_only=False); h=hashlib.sha256()
for ws in wb.worksheets:
    h.update(('SHEET:'+ws.title+'\n').encode())
    for row in ws.iter_rows(values_only=True):
        norm=tuple(TS.sub('<TS>',x) if isinstance(x,str) else x for x in row)
        h.update((repr(norm)+'\n').encode('utf-8'))
os.remove(out)
print('REPORT_DET_HASH', h.hexdigest())
