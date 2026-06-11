# -*- coding: utf-8 -*-
"""test_golden_single_source.py — tripwire กัน "golden hash drift" ในเอกสาร/operational
(ADR-019). ไม่ต้องใช้ข้อมูลจริง — เทียบ doc ↔ baseline.json เท่านั้น รันได้ทุกที่.

หลักการ (business-reason): baseline.json._sha256 = แหล่งความจริงเดียวของค่า hash ปัจจุบัน.
ทุกพื้นผิวที่ "อ้างว่าเป็น golden ปัจจุบัน" ต้องตรงกับมัน และต้องไม่มี hash ที่ปลดระวาง
(ec61907f=81-ไฟล์, f1ac8421=106-เก่า, 7b60b01f=โบราณ, 73f5bf87=106 ก่อน F2-cont/ADR-021) หลงเหลือในพื้นผิวเหล่านั้น.
ถ้าใคร re-baseline แล้วลืมอัปเดตเอกสาร → test นี้แดงทันที (ไม่ใช่รู้ตอน ship).

หมายเหตุ: ไฟล์ "หลักฐานอดีตที่ลงวันที่ไว้" (CHANGELOG/AUDIT/ADR เก่า/validators.py
comment ฯลฯ) จงใจ "ไม่" สแกน — เลข hash เก่าในนั้นถูกต้องตามเวลานั้น (ห้ามเขียนทับ).
สแกนเฉพาะ ALLOWLIST ของพื้นผิว "ปัจจุบัน/operational" ที่ต้อง sync เท่านั้น.

exit 0 = ผ่าน, 1 = พบ drift.
"""
import os, sys, json

HERE = os.path.dirname(os.path.abspath(__file__))

# พื้นผิวที่ "อ้าง golden ปัจจุบัน" — ต้อง sync กับ baseline.json เสมอ
OPERATIONAL_SURFACES = [
    'README.md',
    'version_gate.py',
    'agents/orchestrator.py',
    '.vscode/tasks.json',
    '.vscode/launch.json',
    '_SESSION_HANDOFF.md',
    'QUICKSTART_VSCODE_TH.md',
    'INVARIANTS/DECISIONS.md',   # เฉพาะ banner/ADR-019 ส่วนบน (ทั้งไฟล์มีของเก่าด้วย → ดูหมายเหตุ §ledger ด้านล่าง)
    'constraints.txt',           # [doc-hash-fix] คำสั่ง rebuild ต้องชี้ค่าปัจจุบัน (เคยค้าง f1ac8421)
]
# หมายเหตุ: regression_full.py / verify_golden.py / golden_master.py จงใจ "ไม่" อยู่ใน list นี้ —
#   มันคือ verifier ที่ "อ่าน" baseline.json ตอน runtime (ไม่ได้ hardcode ค่า hash ไว้ในตัว) →
#   drift ไม่ได้โดยโครงสร้าง. list นี้คุมเฉพาะพื้นผิวที่ "พิมพ์/ประกาศค่า golden ปัจจุบัน" ไว้.

# hash ที่ปลดระวางแล้ว (ห้ามปรากฏในพื้นผิว "ปัจจุบัน")
#   73f5bf87 = golden 106-ไฟล์ ก่อน F2-cont (rebaseline → 35b2f7c8, ดู ADR-021)
RETIRED_PREFIXES = ('ec61907f', 'f1ac8421', '7b60b01f', '73f5bf87', '35b2f7c8', 'd3c01886')  # 35b2f7c8 ปลดระวาง 2026-06-10 (ADR-036)

# การอ้างอิงแบบ neutral ที่ยอมรับแทน literal (ชี้ไป single source โดยตรง)
NEUTRAL_REFS = ('baseline.json._sha256', 'baseline._sha256')

# DECISIONS.md เป็น append-only ledger: ส่วนล่างมี ADR เก่าที่อ้าง hash เก่าโดยชอบธรรม
# (หลักฐานอดีต). จึงสแกน "เฉพาะส่วนปัจจุบัน" = ก่อน 'ADR-LOG (append-only' (ประวัติ).
LEDGER_HISTORY_MARKER = 'ADR-LOG (append-only'


def _read(rel):
    p = os.path.join(HERE, rel)
    if not os.path.isfile(p):
        return None
    return open(p, encoding='utf-8').read()


def main():
    fails = []

    bl_path = os.path.join(HERE, 'baseline.json')
    if not os.path.isfile(bl_path):
        print('❌ ไม่พบ baseline.json — ไม่มีแหล่งความจริงให้เทียบ')
        return 1
    bl = json.load(open(bl_path, encoding='utf-8'))
    full = bl.get('_sha256') or ''
    if len(full) != 64 or any(c not in '0123456789abcdef' for c in full):
        fails.append(f'baseline._sha256 ไม่ใช่ sha256 ถูกต้อง: {full!r}')
        print('\n'.join('❌ ' + f for f in fails)); return 1
    cur = full[:8]
    n_files = bl.get('n_files')
    n_bills = bl.get('n_bills')

    print(f'[single source] baseline.json._sha256 = {full}')
    print(f'[single source] n_files={n_files}  n_bills={n_bills}  (prefix={cur})')

    # 1) พื้นผิว operational ต้องอ้าง current (literal cur หรือ neutral ref) + ห้ามมี hash ปลดระวาง
    for rel in OPERATIONAL_SURFACES:
        text = _read(rel)
        if text is None:
            fails.append(f'{rel}: ไม่พบไฟล์ (ALLOWLIST ชี้ไฟล์ที่ไม่มี — แก้ test หรือ restore ไฟล์)')
            continue

        scan = text
        if rel.endswith('DECISIONS.md'):
            idx = text.find(LEDGER_HISTORY_MARKER)
            scan = text[:idx] if idx != -1 else text   # สแกนเฉพาะส่วนปัจจุบัน ไม่แตะ ledger ประวัติ

        has_current = (cur in scan) or any(ref in scan for ref in NEUTRAL_REFS)
        if not has_current:
            fails.append(f'{rel}: ไม่อ้าง golden ปัจจุบัน ({cur}… หรือ baseline.json._sha256) เลย')

        for stale in RETIRED_PREFIXES:
            if stale != cur and stale in scan:
                ln = next((i + 1 for i, l in enumerate(scan.splitlines()) if stale in l), '?')
                fails.append(f'{rel}: พบ hash ปลดระวาง "{stale}" ในพื้นผิวปัจจุบัน (บรรทัด ~{ln}) — ต้องเป็น {cur}')

    # 1.5) GOLDEN.md = อภิธานศัพท์ hash ทางการ "แหล่งอ้างอิงเดียวสำหรับมนุษย์" (กันตื่นตูม).
    #   ต้องมี: ค่าปัจจุบัน (cur/neutral). อนุญาตให้ลิสต์ hash ปลดระวางได้ (นั่นคือหน้าที่ของมัน —
    #   อธิบายว่าแต่ละค่าคืออะไร) จึง "ไม่" อยู่ใน OPERATIONAL_SURFACES (ไม่โดนแบน retired hash).
    gm = _read('GOLDEN.md')
    if gm is None:
        fails.append('GOLDEN.md: ไม่พบ (ควรเป็นแหล่งอ้างอิง hash ทางการเดียว — กันสับสน)')
    elif not ((cur in gm) or any(ref in gm for ref in NEUTRAL_REFS)):
        fails.append(f'GOLDEN.md: ไม่อ้าง golden ปัจจุบัน ({cur}… หรือ baseline.json._sha256)')

    # 2) README ต้องระบุจำนวนไฟล์/บิลตรง baseline (derive — ไม่ hardcode ใน test)
    readme = _read('README.md') or ''
    if n_files is not None and f'{n_files} ไฟล์' not in readme:
        fails.append(f'README.md: ไม่พบ "{n_files} ไฟล์" (จำนวนไฟล์ทางการต้องตรง baseline.n_files)')
    if n_bills is not None and f'{n_bills} บิล' not in readme:
        fails.append(f'README.md: ไม่พบ "{n_bills} บิล" (จำนวนบิลทางการต้องตรง baseline.n_bills)')

    print('-' * 60)
    if fails:
        for f in fails:
            print('❌ ' + f)
        print(f'RESULT: ❌ FAIL ({len(fails)} จุด) — golden source-of-truth drift')
        return 1
    print(f'RESULT: ✅ PASS — พื้นผิว operational ทุกตัว sync กับ baseline.json ({cur}…)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
