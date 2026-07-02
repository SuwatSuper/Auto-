# -*- coding: utf-8 -*-
"""
verify_corpus_manifest.py — แยก "data drift" ออกจาก "code drift" [ADR-158]

ปัญหาที่แก้: golden ข้อมูลจริง (baseline.json) คำนวณจาก /mnt/project (corpus สด).
  ถ้า corpus เปลี่ยน (เพิ่ม/ลบ/แก้บิล) golden จะไม่ reproduce — แต่ "ไม่ใช่ code bug".
  เดิมแยกไม่ออกว่า golden เพี้ยนเพราะ (ก) data เปลี่ยน [rebaseline ปกติ] หรือ
  (ข) code พัง [ต้องสืบด่วน] → เสียเวลา forensic. tool นี้ตอบทันทีว่าเป็นอันไหน.

วิธีใช้:
    python3 verify_corpus_manifest.py [data_dir]     # default /mnt/project

ผลลัพธ์:
    MATCH  (exit 0) → corpus ตรง manifest → golden ต้อง reproduce; ถ้า regression แดง = CODE BUG
    DRIFT  (exit 3) → corpus เปลี่ยน → golden คาดว่าจะเปลี่ยน = rebaseline ปกติ (ไม่ใช่ code bug)

หลังยืนยันว่าเป็น data-drift ที่ "ตั้งใจ" แล้ว rebaseline ด้วย:
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 \\
        python3 golden_master.py . baseline.json <data_dir>
    # แล้ว regenerate manifest: python3 verify_corpus_manifest.py <data_dir> --write
    # แล้ว sync พื้นผิว: python3 test_golden_single_source.py (จะบอกจุดที่ต้องอัป)
"""
import os, sys, json, hashlib, glob

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, 'corpus_manifest.json')


def _hash_dir(data_dir):
    files = sorted(glob.glob(os.path.join(data_dir, '*.xls')) +
                   glob.glob(os.path.join(data_dir, '*.xlsx')))
    out = {}
    for fp in files:
        with open(fp, 'rb') as f:
            out[os.path.basename(fp)] = hashlib.sha256(f.read()).hexdigest()
    return out


def _write_manifest(data_dir):
    """regenerate manifest หลัง rebaseline (ต้องรัน golden_master ก่อน เพื่อให้ baseline.json ใหม่)."""
    cur = _hash_dir(data_dir)
    try:
        bl = json.load(open(os.path.join(HERE, 'baseline.json'), encoding='utf-8'))
    except Exception as e:
        print(f'❌ อ่าน baseline.json ไม่ได้: {e}'); return 1
    out = {
        "_purpose": "ตรึงสถานะ corpus /mnt/project ที่ผูกกับ golden ปัจจุบัน — ใช้แยก 'data drift' "
                    "(rebaseline ปกติ) ออกจาก 'code drift' (bug ต้องสืบ). ดู verify_corpus_manifest.py + ADR-158.",
        "golden_real_corpus": bl.get("_sha256", ""),
        "golden_fixture": "ad0c9dad6fb31bc28251605c1dbad9bf165299d19d11c4752e743477fa6c0749",
        "n_files": len(cur),
        "n_bills": bl.get("n_bills"),
        "adr": "ADR-157 (+2 typo) / ADR-158 (manifest)",
        "files": cur,
    }
    with open(MANIFEST, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, sort_keys=True, indent=1)
    print(f'✅ เขียน corpus_manifest.json ใหม่: {len(cur)} ไฟล์, golden={bl.get("_sha256","")[:16]}')
    return 0


def main():
    data_dir = '/mnt/project'
    write = False
    for a in sys.argv[1:]:
        if a == '--write':
            write = True
        else:
            data_dir = a

    if write:
        return _write_manifest(data_dir)

    if not os.path.isfile(MANIFEST):
        print('❌ ไม่พบ corpus_manifest.json — สร้างครั้งแรก: python3 verify_corpus_manifest.py <data_dir> --write')
        return 1
    try:
        man = json.load(open(MANIFEST, encoding='utf-8'))
    except (json.JSONDecodeError, OSError, ValueError) as e:
        print(f'❌ corpus_manifest.json เสียหาย/อ่านไม่ได้ ({type(e).__name__}: {str(e)[:60]})')
        print('   แก้: regenerate ด้วย `python3 verify_corpus_manifest.py <data_dir> --write` (หลัง golden_master)')
        return 2
    expected = man.get('files', {})
    golden = man.get('golden_real_corpus', '')[:16]

    if not os.path.isdir(data_dir):
        print(f'ℹ ไม่พบโฟลเดอร์ข้อมูล {data_dir} — ข้ามการเช็ค manifest (ไม่มี corpus บนเครื่องนี้).')
        return 0

    cur = _hash_dir(data_dir)
    exp_set, cur_set = set(expected), set(cur)
    added = sorted(cur_set - exp_set)
    removed = sorted(exp_set - cur_set)
    changed = sorted(k for k in (exp_set & cur_set) if expected[k] != cur[k])

    print('=' * 64)
    print(f'[corpus manifest] data={data_dir}')
    print(f'[corpus manifest] คาดไว้ {len(expected)} ไฟล์ (golden {golden}…) · พบจริง {len(cur)} ไฟล์')
    print('=' * 64)

    if not (added or removed or changed):
        print('✅ MATCH — corpus ตรง manifest เป๊ะทุกไฟล์.')
        print('   → golden ข้อมูลจริงต้อง reproduce เป็น', golden + '…')
        print('   → ถ้า regression_full ข้อมูลจริงแดง = "CODE DRIFT" (bug จริง ต้องสืบ ไม่ใช่ data).')
        return 0

    print('⚠  DRIFT — corpus เปลี่ยนจาก manifest:')
    if added:   print(f'   + เพิ่ม {len(added)} ไฟล์: ' + ', '.join(added[:12]) + (' …' if len(added) > 12 else ''))
    if removed: print(f'   − ลบ  {len(removed)} ไฟล์: ' + ', '.join(removed[:12]) + (' …' if len(removed) > 12 else ''))
    if changed: print(f'   ~ แก้เนื้อหา {len(changed)} ไฟล์: ' + ', '.join(changed[:12]) + (' …' if len(changed) > 12 else ''))
    print('-' * 64)
    print('นี่คือ "DATA DRIFT" — golden ข้อมูลจริงคาดว่าจะเปลี่ยน = เรื่องปกติ ไม่ใช่ code bug.')
    print('  • ถ้า "ตั้งใจ" เปลี่ยน corpus (เพิ่มบิลเดือนใหม่ ฯลฯ) → rebaseline:')
    print('      PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1 \\')
    print('          python3 golden_master.py . baseline.json ' + data_dir)
    print('      python3 verify_corpus_manifest.py ' + data_dir + ' --write   # อัป manifest')
    print('      python3 test_golden_single_source.py                 # บอกพื้นผิวที่ต้อง sync')
    print('  • ถ้า "ไม่ได้ตั้งใจ" (ไฟล์ถูกแก้/หายโดยพลาด) → restore ไฟล์ให้ตรง manifest ก่อน.')
    print('  • fixture golden (ad0c9dad) ไม่เกี่ยวกับ corpus → ยัง reproduce เสมอ (ตัวพิสูจน์ code จริง).')
    return 3


if __name__ == '__main__':
    sys.exit(main())
