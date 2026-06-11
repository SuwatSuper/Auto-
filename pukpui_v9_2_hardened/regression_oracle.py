# -*- coding: utf-8 -*-
"""
regression_oracle.py — เครื่องมือพิสูจน์ "พฤติกรรมเดิม 100%" สำหรับการแก้โค้ดครั้งต่อไป

วิธีใช้:
    # 1) สร้าง baseline จากโค้ดที่ทำงานถูกต้องแล้ว (ทำครั้งเดียว)
    python regression_oracle.py freeze

    # 2) หลังแก้โค้ดโครงสร้าง → ตรวจว่าผลตรวจไม่เปลี่ยน
    python regression_oracle.py check
    #   exit 0 + ✅ PASS = พฤติกรรมเดิม 100% → merge ได้
    #   exit 1 + ❌ FAIL = ผลตรวจเปลี่ยน → พิมพ์ field ที่ต่าง

หลักการ:
  - รัน pipeline เต็ม (parse → rules → validators → typos → cross-checks)
  - สร้าง "behavioral fingerprint" ของทุก field ที่เป็นผลตรวจ
  - ตัด timestamp (เวลาสร้างรายงาน) ออก เพราะต่างทุกครั้งโดยธรรมชาติ
  - เทียบ fingerprint ก่อน/หลัง — ต้องตรงทุก byte

ENV:
  PYTHONHASHSEED=0   (harness pin ให้เอง — ผลเสถียรแม้ไม่ pin หลังแก้ P0-determinism)
  PUKPUI_TEST_DIR    โฟลเดอร์ไฟล์ทดสอบ (default: /mnt/project)
"""
import os
import sys
import json
import glob
import hashlib
import warnings

# pin hash seed เพื่อ baseline ที่ทำซ้ำได้ (แม้โค้ดจะ deterministic แล้วก็ pin ไว้กันเหนียว)
if os.environ.get('PYTHONHASHSEED') != '0':
    os.environ['PYTHONHASHSEED'] = '0'
    os.execv(sys.executable, [sys.executable] + sys.argv)

warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

BASELINE_FILE = os.path.join(HERE, 'oracle_baseline.json')
TEST_DIR = os.environ.get('PUKPUI_TEST_DIR', '/mnt/project')

# v9.1: master ทดสอบชุดเดียวกับ golden_master/verify_golden/test_agents (เลิกก๊อป → ไม่ดริฟต์)
from golden_snapshot import MASTER


def _num(v):
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except (ValueError, TypeError):
        return None


def build_fingerprint():
    """รัน pipeline เต็มแล้วคืน fingerprint dict (ทุก field ที่เป็นผลตรวจ)"""
    # [STUB-MARKER] เขียน stub พร้อม marker (เฉพาะไฟล์ — MASTER dict ใน RAM ไม่เปลี่ยน)
    json.dump({**MASTER, "_golden_stub": True},
              open('master_companies.json', 'w', encoding='utf-8'),
              ensure_ascii=False)

    import importlib
    app = importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
    app.reset_run_state()

    file_list = sorted(glob.glob(os.path.join(TEST_DIR, '*.xls')) +
                       glob.glob(os.path.join(TEST_DIR, '*.xlsx')))
    if not file_list:
        print(f'❌ ไม่พบไฟล์ทดสอบใน {TEST_DIR}')
        sys.exit(2)

    all_bills, filename_issues = app.parse_all_files(file_list)
    for b in all_bills:
        app.compute_bill_confidence(b)
    dup_items = app.check_duplicate_items(all_bills)
    app.run_all_rules(all_bills, MASTER)
    iv_issues = app.check_invoice_sequence(all_bills) + app.check_iv_date_sequence(all_bills)
    typos = app.check_product_typos(all_bills)
    summary = app.summarize_by_company(all_bills)
    app.apply_iv_period_crosscheck(all_bills)
    app.apply_sheet_date_crosscheck(all_bills)

    fp = {}
    fp['n_files'] = len(file_list)
    fp['n_bills'] = len(all_bills)
    fp['n_filename_issues'] = len(filename_issues)
    fp['n_dup_items'] = len(dup_items)
    fp['n_iv_issues'] = len(iv_issues)
    fp['n_typos'] = len(typos)
    fp['n_system_issues'] = len(app._SYSTEM_ISSUES)

    # ยอดเงินทุกบิล (สำคัญที่สุด)
    amounts = []
    for b in all_bills:
        amounts.append({
            'file': b.get('file', ''), 'sheet': str(b.get('sheet', '')),
            'iv': str(b.get('iv_number', '')),
            'subtotal': _num(b.get('subtotal')), 'vat': _num(b.get('vat')),
            'total': _num(b.get('total')), 'n_items': len(b.get('items', [])),
        })
    amounts.sort(key=lambda x: (x['file'], x['sheet'], x['iv']))
    fp['amounts'] = amounts

    # กฎที่ trigger ต่อบิล
    bill_issues = []
    for b in all_bills:
        codes = sorted(str(i.get('rule', i.get('code', i.get('type', ''))))
                       for i in b.get('issues', []))
        bill_issues.append({
            'file': b.get('file', ''), 'sheet': str(b.get('sheet', '')),
            'iv': str(b.get('iv_number', '')), 'issue_codes': codes,
        })
    bill_issues.sort(key=lambda x: (x['file'], x['sheet'], x['iv']))
    fp['bill_issues'] = bill_issues

    # typo pairs (เทียบแบบ set — normalize ลำดับภายในคู่)
    typo_pairs = sorted(set(
        tuple(sorted([str(t.get('name1', t.get('word1', ''))),
                      str(t.get('name2', t.get('word2', '')))]))
        for t in typos
    ))
    fp['typo_pairs'] = [list(p) for p in typo_pairs]

    # iv sequence issues
    iv_list = sorted(
        ({'type': str(i.get('type', '')), 'iv': str(i.get('iv', '')),
          'severity': str(i.get('severity', ''))} for i in iv_issues),
        key=lambda x: (x['type'], x['iv'], x['severity'])
    )
    fp['iv_issues_detail'] = iv_list

    return fp


def fp_hash(fp):
    return hashlib.sha256(
        json.dumps(fp, ensure_ascii=False, sort_keys=True).encode('utf-8')
    ).hexdigest()


def cmd_freeze():
    print('🧊 สร้าง baseline fingerprint...')
    fp = build_fingerprint()
    json.dump(fp, open(BASELINE_FILE, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2, sort_keys=True)
    print(f'✅ Baseline บันทึกแล้ว → {BASELINE_FILE}')
    print(f'   hash: {fp_hash(fp)}')
    print(f'   บิล: {fp["n_bills"]} | typos: {fp["n_typos"]} | '
          f'iv_issues: {fp["n_iv_issues"]} | system: {fp["n_system_issues"]}')


def cmd_check():
    if not os.path.exists(BASELINE_FILE):
        print(f'❌ ไม่พบ baseline ({BASELINE_FILE}) — รัน `freeze` ก่อน')
        sys.exit(2)
    baseline = json.load(open(BASELINE_FILE, encoding='utf-8'))
    print('🔬 รัน pipeline เทียบกับ baseline...')
    current = build_fingerprint()

    h_base = fp_hash(baseline)
    h_curr = fp_hash(current)

    if h_base == h_curr:
        print(f'\n✅✅✅ PASS — พฤติกรรมเดิม 100% (hash ตรง: {h_curr[:16]}…)')
        print(f'   บิล: {current["n_bills"]} | typos: {current["n_typos"]} | '
              f'iv_issues: {current["n_iv_issues"]}')
        sys.exit(0)

    print(f'\n❌ FAIL — ผลตรวจเปลี่ยน!')
    print(f'   baseline hash: {h_base[:16]}…')
    print(f'   current  hash: {h_curr[:16]}…')
    print('\n--- field ที่ต่าง ---')

    # เทียบ field counts ก่อน
    for k in ['n_files', 'n_bills', 'n_filename_issues', 'n_dup_items',
              'n_iv_issues', 'n_typos', 'n_system_issues']:
        if baseline.get(k) != current.get(k):
            print(f'  {k}: baseline={baseline.get(k)} → current={current.get(k)}')

    # ยอดเงิน
    if baseline['amounts'] != current['amounts']:
        print('  ⚠️ amounts (ยอดเงิน) ต่าง:')
        bmap = {(a['file'], a['sheet'], a['iv']): a for a in baseline['amounts']}
        for a in current['amounts']:
            key = (a['file'], a['sheet'], a['iv'])
            if bmap.get(key) != a:
                print(f'     {key}: {bmap.get(key)} → {a}')
                break

    # กฎที่ trigger
    if baseline['bill_issues'] != current['bill_issues']:
        print('  ⚠️ bill_issues (กฎที่ trigger) ต่าง:')
        bmap = {(b['file'], b['sheet'], b['iv']): b['issue_codes']
                for b in baseline['bill_issues']}
        for b in current['bill_issues']:
            key = (b['file'], b['sheet'], b['iv'])
            if bmap.get(key) != b['issue_codes']:
                print(f'     {key}:')
                print(f'       baseline: {bmap.get(key)}')
                print(f'       current:  {b["issue_codes"]}')
                break

    # typos
    if baseline['typo_pairs'] != current['typo_pairs']:
        bset = set(tuple(p) for p in baseline['typo_pairs'])
        cset = set(tuple(p) for p in current['typo_pairs'])
        only_b = bset - cset
        only_c = cset - bset
        print('  ⚠️ typo_pairs ต่าง:')
        if only_b:
            print(f'     หายไป: {[list(x) for x in only_b][:3]}')
        if only_c:
            print(f'     เพิ่มมา: {[list(x) for x in only_c][:3]}')

    # iv issues
    if baseline['iv_issues_detail'] != current['iv_issues_detail']:
        print('  ⚠️ iv_issues_detail ต่าง')

    sys.exit(1)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'freeze':
        cmd_freeze()
    elif cmd == 'check':
        cmd_check()
    else:
        print(f'ใช้: python {os.path.basename(__file__)} [freeze|check]')
        sys.exit(2)


if __name__ == '__main__':
    main()
