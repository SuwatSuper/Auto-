# -*- coding: utf-8 -*-
"""test_file_size_ceiling.py — tripwire เพดานขนาดไฟล์ (≤600 LOC/ไฟล์) ล็อกผลงาน F4.

หลักการ (business-reason): บาร์ maintainability ของโปรเจกต์ = ไฟล์ Python แต่ละไฟล์ ≤600 LOC
(ดู roadmap F4 / HANDOFF). การซอยที่ทำไปแล้ว (verification_lenses, vendor_report, parser_p0,
config) ผ่านบาร์นี้หมด. tripwire นี้ทำให้ "ไฟล์โตกลับเกินเพดาน" = แดงทันที — บังคับให้ตัดสินใจ
อย่างรู้ตัว (ซอยต่อ หรือเพิ่ม whitelist พร้อมเหตุผล) แทนที่จะค่อย ๆ โตจนกลับมาเป็น monolith เงียบ ๆ.

WHITELIST: monolith ตัวเดียวที่ยังเกิน — เป็นเป้า F4/F3 รอบถัดไป (split คู่กับการกำจัด import*).
ไม่ต้องใช้ข้อมูลจริง รันได้ทุกที่. exit 0 = ผ่าน, 1 = พบไฟล์เกินเพดานนอก whitelist.
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CEILING = 600

# ไฟล์ที่อนุญาตให้เกินชั่วคราว (พร้อมเหตุผล) — ต้องมีแผนจัดการ
# [SPLIT #3 เสร็จ] monolith 1365 LOC → แตกเป็น 4 ไฟล์ (top 265 / base / funcs / consts) ทุกไฟล์ ≤600
# → whitelist ว่าง: ทุกไฟล์ในโปรเจกต์อยู่ใต้เพดานแล้ว (ห้ามโตกลับเป็น monolith เงียบ ๆ)
WHITELIST = {
    # parser_p2.py: ชั้น extract byte-identical + re-export chain (parser_p0→p0a→p1→p2) — ซอยยากโดยไม่
    #   กระทบสัญญา re-export/golden. เกินเพดานมาก่อนแล้ว (602) + เพิ่ม guard [H2] _is_seq_token กัน
    #   superscript ทำ "บิลทั้งชีตหาย". แผน: รอบ maintenance ถัดไปแยก toolkit (_pb_*) ออกเป็น parser_p3.
    'parser_p2.py': 'extract+re-export chain ซอยยาก (byte-identical/golden); แผนแยก _pb_* → parser_p3 รอบหน้า',
    # parser_p1.py: chain เดียวกัน (_pb_* header/block toolkit) — เดิม 600 พอดี, ADR-055 เพิ่ม guard
    #   money-serial (เซลล์เงิน 30000-70000 ถูกอ่านเป็นวันที่) ที่ call-site _pb_scan_header → 605.
    #   ซอยร่วมแผนเดียวกับ parser_p2 (_pb_* → parser_p3) รอบ maintenance ถัดไป.
    'parser_p1.py': 'header/block _pb_* chain (byte-identical/golden); ADR-055 money-serial guard; แผนแยก _pb_* → parser_p3 รอบหน้า',
    # validators.py: ADR-057 เพิ่ม LONG-format DOC001 guard (apply_sheet_date_crosscheck — precompute
    #   filepath→{N:set(date)} กัน ".M"=ลำดับย่อยถูกอ่านเป็นเดือน) ที่ golden-path. เดิมชิดเพดาน → 620.
    #   guard logic แยกออกยากโดยไม่กระทบสัญญา/golden. แผน: รอบ F4 ถัดไปแยกชั้น crosscheck → validators_xcheck.
    'validators.py': 'rule-application + ADR-057 DOC001 LONG guard (golden-path); แผนแยกชั้น crosscheck → validators_xcheck รอบ F4 ถัดไป',
    # rules_engine_rules_a.py: ADR-058 เพิ่ม SHORT-format DOC001 guard ใน r_doc001 (2-signal:
    #   corroborated day-naming + ไม่มี copy-sibling) กัน FP "เทมเพลตก๊อป/บิลเดี่ยว". เดิมชิดเพดาน → 625
    #   (trim docstring แล้ว). chain เดียวกับ rules_engine_base (de-star re-export). แผน: แยกตระกูล DOC/DT
    #   → rules_engine_rules_doc รอบ F4 ถัดไป (คู่กับการกำจัด import* ที่เหลือ).
    'rules_engine_rules_a.py': 'rule-pack A + ADR-058 DOC001 SHORT guard (de-star re-export chain/golden); แผนแยกตระกูล DOC/DT → rules_engine_rules_doc รอบ F4 ถัดไป',
    # rules_engine_rules_c.py: rule-pack C (TAX/DT/VAT/IV cross-bill) ใน de-star re-export chain (golden-path,
    #   ซอยยากเท่า a/b). ADR-115 (VAT011 ใบมียอดแต่ VAT=0) + ADR-116 (TAX009 ชื่อเดียวเลขภาษีต่าง) เพิ่ม 2 กฎ
    #   ปิด detection blind spot (corpus=0/golden-neutral) → เดิมชิดเพดาน → 652. แผน: รอบ F4 ถัดไปแยกตระกูล
    #   VAT → rules_engine_rules_vat คู่กับการกำจัด import* ที่เหลือ.
    'rules_engine_rules_c.py': 'rule-pack C cross-bill (de-star re-export chain/golden); ADR-115 VAT011 + ADR-116 TAX009 ปิด blind spot (corpus=0); แผนแยกตระกูล VAT → rules_engine_rules_vat รอบ F4 ถัดไป',
    # unit_detection_ext.py: report-layer ADD-ON (advisory/golden-neutral — ไม่กระทบ baseline hash).
    #   ADR-091 เพิ่ม _FAMILIES + _unit_family_key (จัดกลุ่มหน่วยพ้องตามตระกูล) แก้ note "ปนไทย+อังกฤษ"
    #   ให้ flag เฉพาะหน่วยเดียวกัน 2 สคริปต์ (เมตร/m, กก./kg) ตัด FP → 600 ชิดเพดาน เป็น 618.
    #   เป็น report layer ล้วน ซอยปลอดภัย. แผน: รอบ maintenance ถัดไปแยก _FAMILIES + _unit_family_key
    #   ออกเป็น unit_families.py (data + lookup) ให้ unit_detection_ext เหลือเฉพาะ note-builder.
    'unit_detection_ext.py': 'report-layer ADD-ON (golden-neutral); ADR-091 family-based unit note (เมตร/m, กก./kg); แผนแยก _FAMILIES → unit_families.py รอบหน้า',
    # super_ultra_viewer.py: ตัวสร้าง company_summary (report layer ล้วน — advisory/golden-neutral, ไม่กระทบ
    #   baseline hash). ADR-099 เพิ่ม (ก) ยุบ ชื่อบจ./สาขา ตาม unique mismatch (เดิม list ทุกใบ ~4,900 ตัวอักษร →
    #   1 บรรทัด) + (ข) ตัด file_spec_unit_lang_notes (FP 31/33 ไฟล์). เดิม 600 ชิดเพดาน → 607. monolith viewer
    #   ซอยปลอดภัย (golden-neutral). แผน: รอบ F4 ถัดไปแยก _pinpoint_field + field-render → viewer_pinpoint.py.
    'super_ultra_viewer.py': 'report-layer company_summary builder (golden-neutral); ADR-099 ยุบ ชื่อบจ./สาขา + ตัด spec-unit FP; แผนแยก _pinpoint_field → viewer_pinpoint.py รอบ F4 ถัดไป',
}

# ไม่สแกน: backup, hidden, cache, build, virtualenv — ไม่ใช่ "source ของโปรเจกต์"
#   [ADR-126] เดิม skip แค่ 5 ชื่อ → maintainer ที่ทำสิ่งมาตรฐาน (`python -m venv .venv` ซึ่ง
#   .gitignore รองรับอยู่แล้ว / รัน make_release สร้าง dist/ / mypy สร้าง .mypy_cache) ทำให้
#   tripwire แดง "ปลอม" บนไลบรารีภายนอก (rich/xlrd/numpy 600+ LOC) — false-red ที่กัดความเชื่อใน
#   safety net เอง (เพดานนี้มีไว้คุม "ไฟล์โปรเจกต์" ไม่ใช่ deps). เพิ่ม env/build/cache dirs ทั้งหมด.
SKIP_DIRS = {
    '_ORIG_BACKUP', '__pycache__', '.ruff_cache', '.git', '.vscode',
    '.mypy_cache', '.pytest_cache', 'dist', 'build', '.eggs', '.tox', 'node_modules',
}


def _is_skip_dir(parent, name):
    """ข้ามไดเรกทอรีที่ "ไม่ใช่ source โปรเจกต์": ชื่อใน SKIP_DIRS, prefix `.venv*`,
    `*.egg-info`, หรือ "ราก virtualenv" (มีไฟล์ pyvenv.cfg — จับ venv ได้ทุกชื่อไม่ว่าตั้งชื่ออะไร).
    pyvenv.cfg คือ marker มาตรฐานของ venv ทุกตัว → ครอบ venv/env/.venv_xxx ที่ไม่อยู่ในชื่อ skip."""
    if name in SKIP_DIRS:
        return True
    if name.startswith('.venv') or name.endswith('.egg-info'):
        return True
    if os.path.isfile(os.path.join(parent, name, 'pyvenv.cfg')):
        return True
    return False


def _loc(path):
    with open(path, encoding='utf-8') as f:
        return sum(1 for _ in f)


def scan(root):
    """เดิน root, คืน (over, whitelisted) = list ของ (relpath, loc) ที่เกินเพดาน.
    ข้าม dir env/build/cache ด้วย _is_skip_dir (ดู [ADR-126])."""
    over, whitelisted = [], []
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not _is_skip_dir(r, d)]
        for fn in files:
            if not fn.endswith('.py'):
                continue
            full = os.path.join(r, fn)
            rel = os.path.relpath(full, root)
            n = _loc(full)
            if n <= CEILING:
                continue
            if fn in WHITELIST:
                whitelisted.append((rel, n))
            else:
                over.append((rel, n))
    return over, whitelisted


def _selftest():
    """[ADR-126] ตรวจ "ตัวกรอง dir" ของ tripwire เองก่อนสแกนจริง — กัน regress ที่ทำให้
    tripwire กลับไปแดงปลอมบน venv/deps. คืน list ข้อความ failure (ว่าง = ผ่าน).

    business-reason: เพดานไฟล์มีไว้คุม "ไฟล์โปรเจกต์" — ถ้า _is_skip_dir พังจะนับ deps
    (rich/xlrd 600+ LOC) เป็นไฟล์เกินเพดาน = false-red กัดความเชื่อใน safety net. self-test
    นี้ทำให้ "ตัวกรองพัง" = แดงทันทีพร้อมเหตุ (ไม่ใช่ไปรู้ตอน maintainer สร้าง .venv ใน tree)."""
    fails = []
    here = os.path.dirname(os.path.abspath(__file__))
    # (A) ชื่อ env/build/cache ต้องถูกข้าม ; source ต้องไม่ถูกข้าม
    for nm in ('.venv', '.venv_puopuy', 'dist', 'build', '.mypy_cache',
               '.pytest_cache', '.tox', 'node_modules', 'pkg.egg-info', '__pycache__'):
        if not _is_skip_dir(here, nm):
            fails.append(f'A: ควรข้าม {nm!r} แต่ไม่ข้าม')
    for nm in ('agents', 'tests', 'INVARIANTS', 'rules_engine'):
        if _is_skip_dir(here, nm):
            fails.append(f'A: ไม่ควรข้าม source {nm!r} แต่ข้าม')
    big = '\n'.join(f'x{i}=1' for i in range(CEILING + 100)) + '\n'   # > เพดาน
    with tempfile.TemporaryDirectory() as td:
        # (B) "ราก virtualenv" ตั้งชื่อแปลก (มี pyvenv.cfg) ต้องถูกจับ
        os.makedirs(os.path.join(td, 'customenv'))
        with open(os.path.join(td, 'customenv', 'pyvenv.cfg'), 'w') as f:
            f.write('home = /usr/bin\n')
        if not _is_skip_dir(td, 'customenv'):
            fails.append('B: ควรข้าม venv ชื่อแปลก (มี pyvenv.cfg) แต่ไม่ข้าม')
        if _is_skip_dir(td, 'realsrc'):
            fails.append('B: ไม่ควรข้าม dir ปกติที่ไม่มี pyvenv.cfg')
        # (C) end-to-end: ไฟล์ใหญ่ใน venv/dist/build ถูกข้าม แต่ไฟล์โปรเจกต์เกินเพดานยังถูกจับ
        for sub in ('.venv/lib', 'customenv/lib', 'dist', 'build', '.mypy_cache'):
            os.makedirs(os.path.join(td, sub), exist_ok=True)
            with open(os.path.join(td, sub, 'huge.py'), 'w', encoding='utf-8') as f:
                f.write(big)
        os.makedirs(os.path.join(td, 'pkg'), exist_ok=True)
        with open(os.path.join(td, 'pkg', 'toobig.py'), 'w', encoding='utf-8') as f:
            f.write(big)
        with open(os.path.join(td, 'ok.py'), 'w', encoding='utf-8') as f:
            f.write('y = 1\n')
        over, _wl = scan(td)
        over_rel = {r for r, _ in over}
        if not any(r.endswith('toobig.py') for r in over_rel):
            fails.append('C: ไฟล์โปรเจกต์เกินเพดาน (pkg/toobig.py) ควรถูกจับ แต่ไม่ถูกจับ')
        leaked = sorted(r for r in over_rel if not r.endswith(os.path.join('pkg', 'toobig.py')))
        if leaked:
            fails.append(f'C: ไฟล์ใน venv/dist/build ไม่ควรถูกนับ แต่หลุดมา: {leaked}')
    return fails


def main():
    # [ADR-126] ตรวจตัวกรอง dir ของ tripwire ก่อน — ถ้าพังให้แดงทันที (ไม่สแกนต่อ)
    st = _selftest()
    if st:
        print('[file-size ceiling] ❌ self-test ตัวกรอง dir ล้มเหลว:')
        for m in st:
            print(f'   • {m}')
        print('RESULT: ❌ FAIL — _is_skip_dir/scan ผิด (จะนับ deps เป็นไฟล์เกินเพดาน). แก้ก่อน.')
        return 1

    over, whitelisted = scan(HERE)
    print(f'[file-size ceiling] เพดาน = {CEILING} LOC/ไฟล์ (self-test ตัวกรอง dir ✅)')
    if whitelisted:
        print('whitelist (เกินได้ชั่วคราว พร้อมเหตุผล):')
        for rel, n in sorted(whitelisted):
            base = os.path.basename(rel)
            print(f'  ⏳ {rel} ({n}) — {WHITELIST[base]}')
    print('-' * 60)
    if over:
        for rel, n in sorted(over):
            print(f'❌ {rel} ({n} LOC) เกินเพดาน {CEILING} และไม่อยู่ whitelist')
        print(f'RESULT: ❌ FAIL ({len(over)} ไฟล์) — ซอยไฟล์ หรือเพิ่ม whitelist พร้อมเหตุผล/แผน')
        return 1
    print(f'RESULT: ✅ PASS — ทุกไฟล์ ≤{CEILING} LOC (ยกเว้น whitelist {len(whitelisted)} ไฟล์ที่มีแผน)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
