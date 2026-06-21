# -*- coding: utf-8 -*-
"""
golden_master.py — ตาข่ายนิรภัยพิสูจน์ "ผลลัพธ์เหมือนเดิม 100%"

รัน pipeline เต็มของระบบ (เรียกฟังก์ชันสาธารณะตรงตาม e2e_test.py) บนข้อมูลจริง
แล้ว serialize ผลลัพธ์ทุกชั้นเป็น JSON canonical (sort_keys) + คำนวณ SHA256

วิธีใช้:
    python golden_master.py <path_to_package_dir> <out_snapshot.json>

แนวคิด: เรียกสคริปต์นี้กับ "โค้ดเดิม" → ได้ baseline.json
        เรียกอีกครั้งกับ "โค้ดใหม่ (refactored)" → ได้ refactored.json
        ถ้า SHA256 ตรงกัน = พฤติกรรม/ผลลัพธ์เหมือนเดิมเป๊ะทุก field
"""
import os, sys, json, glob, importlib, warnings, io, contextlib
warnings.filterwarnings('ignore')

PKG_DIR = sys.argv[1] if len(sys.argv) > 1 else '.'
OUT     = sys.argv[2] if len(sys.argv) > 2 else 'snapshot.json'
DATA    = sys.argv[3] if len(sys.argv) > 3 else '/mnt/project'
print(f"[golden_master] pkg={PKG_DIR} out={OUT} data={DATA}", file=sys.stderr)  # [v9.3 STEP7] กันสับ arg

sys.path.insert(0, PKG_DIR)
os.chdir(PKG_DIR)

# v9.1 DECOUPLE: MASTER + canonical + โครง snapshot/hash มาจากแหล่งความจริงเดียว
#   (เดิม inline ที่นี่ + ก๊อปซ้ำใน verify_golden.py → เสี่ยงดริฟต์). verify_golden.py import ชุดเดียวกัน.
from golden_snapshot import MASTER, snapshot_and_hash, write_master_file
write_master_file('master_companies.json')
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
    app.reset_run_state()

    file_list = sorted(glob.glob(os.path.join(DATA, '*.xls')) + glob.glob(os.path.join(DATA, '*.xlsx')))
    all_bills, filename_issues = app.parse_all_files(file_list)
    for b in all_bills:
        app.compute_bill_confidence(b)
    # v9.1 DECOUPLE: เรียก "แหล่งความจริงเดียว" ตัวเดียวกับ main()/orchestrator
    #   (เดิม inline ลำดับซ้ำที่นี่ — เสี่ยงดริฟต์จาก main). ผล/ลำดับ/hash เท่าเดิมเป๊ะ.
    _core = app.run_audit_core(all_bills, MASTER, isolate=True)
    dup_items = _core['dup_items']
    iv_seq    = _core['iv_seq']
    iv_date   = _core['iv_date']
    typos     = _core['typos']
    summary   = _core['summary']

snapshot, digest = snapshot_and_hash(file_list, all_bills, filename_issues,
                                     dup_items, iv_seq, iv_date, typos, summary)
snapshot['_sha256'] = digest

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(snapshot, f, ensure_ascii=False, sort_keys=True, indent=1)

# สรุปสั้นๆ ออก stderr (ไม่ปนกับ snapshot)
sys.stderr.write(f'BILLS={len(all_bills)} FILES={len(file_list)} '
                 f'fn_issues={len(filename_issues)} dup={len(dup_items)} '
                 f'iv_seq={len(iv_seq)} iv_date={len(iv_date)} typos={len(typos)} '
                 f'companies={len(summary)}\n')
print(digest)
