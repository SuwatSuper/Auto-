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
}

# ไม่สแกน: backup, hidden, cache
SKIP_DIRS = {'_ORIG_BACKUP', '__pycache__', '.ruff_cache', '.git', '.vscode'}


def _loc(path):
    with open(path, encoding='utf-8') as f:
        return sum(1 for _ in f)


def main():
    over = []          # (relpath, loc) เกินเพดาน และไม่อยู่ whitelist
    whitelisted = []   # (relpath, loc) เกินแต่ whitelist ไว้
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith('.py'):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, HERE)
            n = _loc(full)
            if n <= CEILING:
                continue
            if fn in WHITELIST:
                whitelisted.append((rel, n))
            else:
                over.append((rel, n))

    print(f'[file-size ceiling] เพดาน = {CEILING} LOC/ไฟล์')
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
