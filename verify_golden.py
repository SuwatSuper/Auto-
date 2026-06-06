# -*- coding: utf-8 -*-
"""verify_golden.py — พิสูจน์ "เส้น agent == เส้น engine" (byte-identical ของผลตรวจ)

รัน pipeline ผ่าน **ชั้น agent** (agents.orchestrator.run_pipeline, write_report=False)
แล้ว serialize ผลตรวจหลักด้วย canonical/SHA256 *สูตรเดียวกับ golden_master.py* →
ถ้า hash ตรงกับ golden_master (เส้น engine) = ชั้น agent ไม่เปลี่ยนผลตรวจเลย.

วิธีใช้:
    # 1) สร้าง baseline จากเส้น engine
    PYTHONHASHSEED=0 python3 golden_master.py . baseline.json /path/to/data
    # 2) ตรวจว่าเส้น agent ให้ผลตรงกัน
    PYTHONHASHSEED=0 python3 verify_golden.py . baseline.json /path/to/data
       → "AGENT == BASELINE : ✅"  ถ้า hash ตรง

ออก exit code 0 = ตรง, 1 = ไม่ตรง (ใช้ใน CI ได้).
⚠ ต้องตั้ง MASTER ให้ตรงกับ golden_master (ไฟล์นี้ใช้ชุดเดียวกัน) ผลถึงเทียบกันได้.
"""
import os, sys, json, glob, warnings, io, contextlib
warnings.filterwarnings('ignore')

PKG_DIR = sys.argv[1] if len(sys.argv) > 1 else '.'
BASELINE = sys.argv[2] if len(sys.argv) > 2 else 'baseline.json'
DATA = sys.argv[3] if len(sys.argv) > 3 else '/mnt/project'

sys.path.insert(0, PKG_DIR)
os.chdir(PKG_DIR)

# v9.1 DECOUPLE: MASTER + canonical + โครง snapshot/hash มาจากแหล่งความจริงเดียว
#   (เดิม inline ที่นี่ + ก๊อปซ้ำใน golden_master.py → เสี่ยงดริฟต์ → false mismatch). ใช้ชุดเดียวกัน.
from golden_snapshot import MASTER, snapshot_and_hash, write_master_file
write_master_file('master_companies.json')


_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    from agents.orchestrator import run_pipeline
    file_list = sorted(glob.glob(os.path.join(DATA, '*.xls')) + glob.glob(os.path.join(DATA, '*.xlsx')))
    options = {"write_report": False, "lean": True, "enable_ai": False, "source": "drive"}
    ctx = run_pipeline(MASTER, file_list, options)

# snapshot keys/order = เหมือน golden_master เป๊ะ (สูตรเดียวกันจาก golden_snapshot → hash ตรงโดยโครงสร้าง)
_snapshot, agent_hash = snapshot_and_hash(
    file_list, ctx.bills, ctx.filename_issues,
    ctx.dup_items, ctx.iv_seq, ctx.iv_date, ctx.typos, ctx.summary)

sys.stderr.write(f'[agent] BILLS={len(ctx.bills)} FILES={len(file_list)} '
                 f'fn_issues={len(ctx.filename_issues)} dup={len(ctx.dup_items)} '
                 f'iv_seq={len(ctx.iv_seq)} iv_date={len(ctx.iv_date)} typos={len(ctx.typos)} '
                 f'companies={len(ctx.summary)}\n')
print(f'agent_hash    = {agent_hash}')

# เทียบกับ baseline (ถ้ามี)
if os.path.isfile(BASELINE):
    try:
        base = json.load(open(BASELINE, encoding='utf-8'))
        base_hash = base.get('_sha256')
        print(f'baseline_hash = {base_hash}')
        ok = (base_hash == agent_hash)
        print(f'AGENT == BASELINE : {"✅" if ok else "❌"}')
        sys.exit(0 if ok else 1)
    except Exception as e:
        sys.stderr.write(f'⚠️ อ่าน baseline ไม่ได้: {e}\n')
        sys.exit(2)
else:
    sys.stderr.write(f'⚠️ ไม่พบ baseline "{BASELINE}" — พิมพ์ agent_hash อย่างเดียว\n')
    sys.exit(0)
