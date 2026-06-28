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
    'Makefile',                  # [drift-fix 2026-06] help text เคยค้าง ec61907f/d8bcde85 — ปิดช่องที่เคยทำ drift
    '.github/workflows/ci.yml',  # [drift-fix 2026-06] comment/step-name ต้องชี้ค่าปัจจุบัน (เคยค้าง 81 ไฟล์/ec61907f)
    'MAINTENANCE.md',            # [drift-fix 2026-06] how-to-maintain ต้องชี้ค่าปัจจุบัน ไม่ใช่ f1ac8421
    'CLAUDE.md',                 # [ADR-086] cold-start contract — เคย drift ค้าง ae84d3f0 (ไม่ถูกเฝ้า → session อนาคตคาดค่าผิด) → ปิดช่องถาวร
    'run_ci.sh',                 # [ADR-086] comment baseline — เคย drift ค้าง ba9deda0 → ปิดช่องถาวร
]
# หมายเหตุ: regression_full.py / verify_golden.py / golden_master.py จงใจ "ไม่" อยู่ใน list นี้ —
#   มันคือ verifier ที่ "อ่าน" baseline.json ตอน runtime (ไม่ได้ hardcode ค่า hash ไว้ในตัว) →
#   drift ไม่ได้โดยโครงสร้าง. list นี้คุมเฉพาะพื้นผิวที่ "พิมพ์/ประกาศค่า golden ปัจจุบัน" ไว้.

# hash ที่ปลดระวางแล้ว (ห้ามปรากฏในพื้นผิว "ปัจจุบัน")
#   73f5bf87 = golden 106-ไฟล์ ก่อน F2-cont (rebaseline → 35b2f7c8, ดู ADR-021)
RETIRED_PREFIXES = ('d8adc143', '31013a31', '9aded0ad', 'a5b39d00', '5f23e9f4', '587db268', '853ce4ab', '08e6abfd', 'ae84d3f0', 'ec61907f', 'f1ac8421', '7b60b01f', '73f5bf87', '35b2f7c8', 'd3c01886', 'd6b23d12', 'bb042554', '662c9132', 'df91493f', 'ddd06191', 'ba9deda0', '0563245c', 'be6398d2', 'c50fec27', 'd0330308')  # d8adc143 ปลดระวาง 2026-06-28 (ADR-121: เจ้าของอนุมัติเลิกฟ้อง "เจียร์" หลังค้นเน็ต [TOA/HomePro ใช้ "เจียร์" มี ์ = มาตรฐานวงการ] — ลบ ITM010 pattern + whitelist แผ่นเจียร์ → −6 flag [TKH_69_0513], เพิ่ม 0 → 0c575c61) · d8adc143 เคยเป็น golden ของ ADR-119 (FP บสังกะสี −1) + ADR-120 (GAP-A robustness golden-neutral) · 31013a31 ปลดระวาง 2026-06-28 (ADR-119: r_itm011/r_itm012 ตัด FP คลาส "ตัดคำกลางคำ" — เก็บเฉพาะท่อนแรกของ Thai run, ลบ ITM011 "บสังกะสี"×1 [KNT_69_012, เซลล์จริง "ชุบสังกะสี" ถูก ตัวแบ่งคำ 20-char ตัดเป็น "ชุ|บสังกะสี"], เพิ่ม 0, recall typo จริงคงครบ → d8adc143) · 9aded0ad ปลดระวาง 2026-06-27 (ADR-104/105/106: P1 หน่วยปนภาษาราย-ไฟล์ [report, golden-neutral] + P2 ZWNJ/header-strip + คำ 'ไม่มีหน่วย' + P3 ITM020 ทั้งบิลไม่มีหน่วย → ITM020 +52, ITM019 +9 [header 'Unit' ถูกตรวจเป็นหน่วยขาด], ลบ 0, FP=0 → 31013a31) · d0330308 ปลดระวาง 2026-06-26 (ADR-102: ลบบริษัทตัวอย่าง ฉี อัน ออกจาก golden_snapshot.MASTER ตามคำสั่งเจ้าของ → golden = พฤติกรรม 'master ว่าง {}' = default จริงที่ ship ; CMP006 −50 จุด (ฉี อัน ไม่มี master เทียบ) → 9aded0ad) · a5b39d00 ปลดระวาง 2026-06-24 (ADR-095: +typo สึตำ/เปือย/เหลือง-ตำ จาก completeness check +4 flag → d0330308) · 5f23e9f4 ปลดระวาง 2026-06-24 (ADR-094: เพิ่ม typo 16 ตัวจาก exhaustive all-token scan +31 flag FP=0 → a5b39d00) · 587db268 ปลดระวาง 2026-06-24 (ADR-092: typo วาวล์/แป็ป/ครีลิ +9 flag → 5f23e9f4) · 853ce4ab ปลดระวาง 2026-06-23 (ADR-087 F1: ITM005 'สี'+color-adj exclusion → −64 FP, recall คงเดิม → 587db268) · ae84d3f0 ปลดระวาง 2026-06-22 (ADR-064..076 deep audit: M-1 r_dt003 time-bomb + FP-reduction ITM004/ITM010/ITM016/DT004 + non-finite money + ADDR005/DOC003 → 08e6abfd) · c50fec27 ปลดระวาง 2026-06-21 (ADR-058 DOC001 SHORT-format FP guard: TNT_69_03 "2" เทมเพลตก๊อป + TSH_69_039 "1" บิลเดี่ยว) · be6398d2 ปลดระวาง 2026-06-20 (ADR-057 DOC001 sub-index/template FP guard) · 0563245c ปลดระวาง 2026-06-20 (ADR-056 ITM010/011 FP-whitelist: บริสุทธิ์/กระเบื้องพื้น) · ba9deda0 ปลดระวาง 2026-06-20 (ADR-055 DT-money-serial-misread fix) · ddd06191 ปลดระวาง 2026-06-19 (ADR-051 DT001-012-fix) · 35b2f7c8 ปลดระวาง 2026-06-10 (ADR-036) · d6b23d12 ปลดระวาง 2026-06-18 (ADR-044) · bb042554 ปลดระวาง 2026-06-18 (ADR-046) · 662c9132 ปลดระวาง 2026-06-18 (ADR-047) · df91493f ปลดระวาง 2026-06-19 (ADR-048: corpus 106→148 + BR สํา + TKH discount)

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

    # 1.7) FIXTURE golden (3 บิล) — แกนคนละตัวกับ corpus. เคย drift จริง (d8bcde85 → 269ddaed หลัง ADR-041)
    #   เพราะ "ไม่มีใครเฝ้า": Makefile/ci.yml/MAINTENANCE อ้างค่าเก่าค้างทั้งที่ baseline_fixture.json
    #   ถูก rebaseline แล้ว. แกนนี้ปิดช่องนั้น — อ่านค่าปัจจุบันจาก baseline_fixture.json (single source)
    #   แล้วบังคับให้พื้นผิวที่ "พูดถึง fixture golden" อ้างค่าปัจจุบัน + ห้ามมี fixture hash ปลดระวาง.
    fx_path = os.path.join(HERE, 'tests', 'fixtures', 'baseline_fixture.json')
    cur_fix = ''
    if os.path.isfile(fx_path):
        fxfull = (json.load(open(fx_path, encoding='utf-8')).get('_sha256') or '')
        if len(fxfull) == 64:
            cur_fix = fxfull[:8]
    if not cur_fix:
        fails.append('tests/fixtures/baseline_fixture.json: อ่าน _sha256 ไม่ได้ (fixture single source หาย)')
    else:
        RETIRED_FIXTURE_PREFIXES = ('d8bcde85', '269ddaed', 'b5c415bb')   # b5c415bb ปลดระวาง 2026-06-26 (ADR-102 — ลบ master ฉี อัน → fixture rebaseline 72cb832c) · 269ddaed ปลดระวาง 2026-06-21 (ADR-058 SHORT guard: fixture ชีต 2/4/6 เลิกฟ้อง DOC001 → b5c415bb) · d8bcde85 = fixture hash ก่อน ADR-041 (float decimal tail) — ปลดระวาง
        FIXTURE_SURFACES = ['Makefile', '.github/workflows/ci.yml', 'MAINTENANCE.md']
        for rel in FIXTURE_SURFACES:
            text = _read(rel)
            if text is None:
                continue
            if cur_fix not in text:
                fails.append(f'{rel}: ไม่อ้าง fixture golden ปัจจุบัน ({cur_fix}…) — เคยค้างค่าเก่า')
            for stale in RETIRED_FIXTURE_PREFIXES:
                if stale != cur_fix and stale in text:
                    ln = next((i + 1 for i, l in enumerate(text.splitlines()) if stale in l), '?')
                    fails.append(f'{rel}: พบ fixture hash ปลดระวาง "{stale}" (บรรทัด ~{ln}) — ต้องเป็น {cur_fix}')
        if gm is not None and cur_fix not in gm:
            fails.append(f'GOLDEN.md: ไม่อ้าง fixture golden ปัจจุบัน ({cur_fix}…) ในตารางอภิธานศัพท์')

    # 2) README ต้องระบุจำนวนไฟล์/บิลตรง baseline (derive — ไม่ hardcode ใน test)
    readme = _read('README.md') or ''
    if n_files is not None and f'{n_files} ไฟล์' not in readme:
        fails.append(f'README.md: ไม่พบ "{n_files} ไฟล์" (จำนวนไฟล์ทางการต้องตรง baseline.n_files)')
    if n_bills is not None and f'{n_bills} บิล' not in readme:
        fails.append(f'README.md: ไม่พบ "{n_bills} บิล" (จำนวนบิลทางการต้องตรง baseline.n_bills)')

    # 3) เวอร์ชัน — แหล่งความจริงเดียว = config_base.APP_VERSION. เคย drift (v9.1/v9.2/v9.3 ปนกัน
    #    ข้าม README/README_PACKAGE/อ่านก่อนใช้). ดึงค่าจาก source ด้วย regex (ไม่ import เลี่ยงพึ่ง openpyxl)
    #    แล้วบังคับให้ title ของเอกสารผู้ใช้ทุกฉบับสะกด "v<APP_VERSION>" ตรงกัน.
    import re as _re
    cfg_txt = _read('config_base.py') or ''
    m = _re.search(r'APP_VERSION\s*=\s*"([^"]+)"', cfg_txt)
    if not m:
        fails.append('config_base.py: อ่าน APP_VERSION ไม่ได้ (แหล่งความจริงเดียวของเวอร์ชันหาย)')
    else:
        ver = m.group(1)
        for rel in ('README.md', 'README_PACKAGE_TH.md', 'อ่านก่อนใช้.md', 'QUICKSTART_VSCODE_TH.md'):
            txt = _read(rel)
            if txt is None:
                continue
            if f'v{ver}' not in txt.splitlines()[0]:
                fails.append(f'{rel}: title ไม่ตรง APP_VERSION (ต้องมี "v{ver}") — เวอร์ชัน drift')

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
