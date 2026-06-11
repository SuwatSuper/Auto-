# -*- coding: utf-8 -*-
"""parser_guards.py — ชั้น "ปราการรับ input" + IV last-resort (ซอยจาก parser_p2 ตามเพดาน ≤600 LOC)

ครอบ 2 หน้าที่ที่เป็น "ด่านหน้า" ของ pipeline (FIX 11.06.69 — ดู FIX_11_06_69_TH.md):
  • file discovery + การ์ดไฟล์ชื่อซ้ำ (F1/SYS004): get_files_via_drive / get_files_via_upload
  • fallback เลขเอกสารโดด 4-5 หลัก (F2): _pb_iv_lastresort / apply_iv_lastresort_if_needed

โมดูลนี้เป็น leaf (import เฉพาะ stdlib + pandas + core_utils; diagnostics แบบ lazy)
→ ไม่มี import cycle. parser_p2 re-export ชื่อทั้งหมดขึ้น chain เหมือนเดิม (object เดียวกัน).
"""
from __future__ import annotations

import glob
import os
import re
from datetime import datetime

import pandas as pd

from core_utils import iv_digits_garbage   # [F2] gate: iv ขยะ (D2-GUARD จะล้างทิ้ง) = ว่าง


def get_files_via_drive(folder_path):
    found = []
    for p in ['*.xls', '*.xlsx']:
        found += glob.glob(os.path.join(folder_path, '**', p), recursive=True)
    # v6.0 FIX-8: กรองไฟล์ที่ไม่ใช่บิลจริง — กันพังเงียบ/ผลเพี้ยน
    #   1. ไฟล์ lock ชั่วคราวของ Excel (~$xxx.xlsx) ที่เกิดตอนเปิดไฟล์ค้างไว้
    #   2. ไฟล์รายงานของระบบเอง (audit_v58_xxx.xlsx) กันถูกอ่านซ้ำเป็นบิล
    clean = []
    for f in found:
        base = os.path.basename(f)
        if base.startswith('~$'):
            continue                          # Excel temp lock file
        if base.startswith('audit_v58_'):
            continue                          # ไฟล์ output ของระบบเอง
        clean.append(f)
    # [F1-GUARD v9.3] ชื่อไฟล์ซ้ำ "คนละโฟลเดอร์" จาก recursive scan → กันบิลถูกนับซ้ำเงียบ
    #   เหตุ: สแกน '**' recursive — ถ้าในโฟลเดอร์ input มีโฟลเดอร์ย่อย (แบ็คอัพ/สำเนา) ที่มีไฟล์
    #   "ชื่อเดียวกัน" ไฟล์จะถูก parse ซ้ำ และเพราะบิลเก็บ file เป็น basename → DOC003 ฟ้องซ้ำตัวเอง,
    #   ยอด/จำนวนบิลของบริษัทนั้นคูณเท่าจำนวนสำเนา "โดยไม่มีคำเตือน" (เคสจริง 11.06.69: ×2).
    #   ทางแก้: เก็บตัว path ตื้นสุด (ไฟล์หลักหน้าโฟลเดอร์) ข้ามสำเนาในโฟลเดอร์ย่อย + เตือนดัง + log SYS004.
    #   พฤติกรรมเมื่อ "ไม่มีชื่อซ้ำ" = เดิมเป๊ะ (golden path ไม่กระทบ — harness ใช้ glob ของตัวเอง).
    by_base = {}
    for f in clean:
        by_base.setdefault(os.path.basename(f), []).append(f)
    deduped = []
    for base, paths in sorted(by_base.items()):
        if len(paths) == 1:
            deduped.append(paths[0])
            continue
        # ตื้นสุดก่อน (จำนวน separator น้อยสุด) → ผูกลำดับด้วย path string ให้ deterministic
        ranked = sorted(paths, key=lambda p: (os.path.normpath(p).count(os.sep), os.path.normpath(p)))
        keep, skipped = ranked[0], ranked[1:]
        deduped.append(keep)
        print(f'   🛑 [SYS004] ไฟล์ชื่อซ้ำกันในโฟลเดอร์ input: "{base}" พบ {len(paths)} ที่ — '
              f'ใช้ {os.path.normpath(keep)} | ข้าม: ' + ', '.join(os.path.normpath(s) for s in skipped))
        print('      (ถ้าตั้งใจให้เป็น "คนละบิล" จริง กรุณาเปลี่ยนชื่อไฟล์ให้ไม่ซ้ำกันแล้วรันใหม่)')
        try:  # lazy import กัน import-cycle; logger ห้ามทำให้งานหลักล้ม
            from diagnostics import log_system_issue
            log_system_issue(code='SYS004', severity='WARNING', category='ไฟล์',
                             name='ไฟล์ชื่อซ้ำในโฟลเดอร์ input (recursive scan)',
                             detail=f'"{base}" พบ {len(paths)} path — ใช้ {os.path.normpath(keep)} '
                                    f'ข้าม {len(skipped)} สำเนา: '
                                    + '; '.join(os.path.normpath(s) for s in skipped),
                             file=base, echo=False)
        except Exception:
            pass
    # [C1] ลำดับไฟล์นิ่ง: เดิม glob ไม่เรียง → production ≠ golden/harness ที่ sort อยู่แล้ว
    #   caller อื่นทุกตัว sort อยู่แล้ว → แก้ที่ต้นทางเดียวให้ production reproduce hash ที่รับรองไว้
    return sorted(deduped)


def get_files_via_upload():
    """VS Code: ไม่มีปุ่มอัปโหลดแบบ Colab → อ่านไฟล์ .xls/.xlsx จากโฟลเดอร์ในเครื่อง
    ค่าเริ่มต้น = โฟลเดอร์ปัจจุบัน (ที่รันสคริปต์อยู่). พิมพ์ path เองได้
    """
    folder = input('📁 ใส่ path โฟลเดอร์ที่มีไฟล์ .xls/.xlsx (Enter = โฟลเดอร์ปัจจุบัน): ').strip().strip('"').strip("'")
    if not folder:
        folder = '.'
    if not os.path.isdir(folder):
        print(f'❌ ไม่พบโฟลเดอร์: {folder}')
        return []
    files_found = get_files_via_drive(folder)
    print(f'📂 พบ {len(files_found)} ไฟล์ใน "{os.path.abspath(folder)}"')
    return files_found


def _pb_iv_lastresort(df, result, row_start, header_end, ncols):
    """[F2-FIX v9.3] ดึง "เลขเอกสารโดด ๆ 4-5 หลัก" เป็น IV เมื่อสแกนปกติไม่เจออะไรเลย

    เคสจริง (TNT 11.06.69): layout มีเลขเดียว '01954' มุมขวาบน (string, ไม่มี label/prefix,
    ใต้เลขเป็น cell วันที่) — _pick_best_iv ตัด candidate <6 หลักทิ้ง → iv ว่าง → IV005 ฟ้อง
    "ไม่มีเลขที่ใบกำกับ ต้องเติมเลขที่" ทั้งที่เลขเอกสารมีจริงในไฟล์ (false alarm).

    เงื่อนไขปลอดภัย (กันจับ zip/จำนวน/serial มั่ว):
      • ทำงานเฉพาะเมื่อ result['iv_number'] ว่างหลังสแกนปกติทั้ง header (corpus: dormant 100%)
      • cell ต้องเป็น "ตัวเลขล้วน 4-5 หลักทั้ง cell" — string ตรง ^\\d{4,5}$ หรือจำนวนเต็ม
        1..99999 ที่ "ไม่อยู่ช่วง excel serial 20000..60000" (กันวันที่เก็บเป็นเลข)
      • ต้องมีสัญญาณตำแหน่งเอกสารอย่างน้อย 1 อย่าง: อยู่ครึ่งขวาของชีต หรือมี cell วันที่
        อยู่ใกล้ (รัศมีแมนฮัตตัน ≤2) — มุมซ้าย/ที่อยู่/รหัสไปรษณีย์โดดจึงไม่เข้าเกณฑ์
      • หลาย candidate → คะแนนสูงสุดชนะ (ขวา +10, วันที่ใกล้ +20, ความยาวหลัก ×2);
        เสมอ → แถวบนสุดก่อน แล้วคอลัมน์ขวาสุด (deterministic)
    """
    try:
        M = df.to_numpy(dtype=object)
        nrows = M.shape[0]
        hi = min(header_end, nrows)
        # ตำแหน่ง cell วันที่ในโซน header (ใช้เช็คความใกล้)
        date_pos = []
        for r in range(row_start, hi):
            for c in range(ncols):
                v = M[r, c]
                if isinstance(v, (datetime, pd.Timestamp)):
                    date_pos.append((r, c))
        cands = []
        for r in range(row_start, hi):
            for c in range(ncols):
                v = M[r, c]
                if pd.isna(v):
                    continue
                tok = None
                if isinstance(v, str):
                    s = v.strip()
                    if re.fullmatch(r'\d{4,5}', s):
                        tok = s
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    f = float(v)
                    if f == int(f) and 1 <= int(f) <= 99999:
                        iv_int = int(f)
                        if not (20000 <= iv_int <= 60000):    # กัน excel date serial
                            s = str(iv_int)
                            if len(s) >= 4:
                                tok = s
                if tok is None:
                    continue
                score = len(tok) * 2
                right = c >= (ncols // 2)
                near_date = any(abs(r - dr) + abs(c - dc) <= 2 for dr, dc in date_pos)
                if right:
                    score += 10
                if near_date:
                    score += 20
                if not (right or near_date):    # ไม่มีสัญญาณตำแหน่งเอกสารเลย → ไม่รับ
                    continue
                cands.append((score, -r, c, tok))   # tie: แถวบนสุด (r น้อย) → คอลัมน์ขวาสุด
        if not cands:
            return
        cands.sort(reverse=True)
        tok = cands[0][3]
        result['iv_number'] = tok
        result['iv_number_raw'] = tok
    except Exception:
        return                                       # fallback ห้ามทำให้ parser ล้ม


def apply_iv_lastresort_if_needed(df, result, row_start, header_end, ncols):
    """[F2-FIX v9.3] gate ของ step 1c ใน _parse_block: iv ว่าง "หรือ" เป็นเลขขยะที่
    D2-GUARD (validate_iv_post) จะปฏิเสธทิ้งภายหลังแน่นอน → ลอง last-resort.

    (เคส TNT จริง: weak-fallback คว้าเศษ float ของยอด VAT '…0000000002' → จะถูกล้างเป็น ''
     ตอน post → IV005 false alarm ทั้งที่เลขเอกสาร '01954' มีจริงในไฟล์)
    corpus 834 บิล: iv ว่างหลัง post = 0 → ทั้ง gate dormant 100% บน corpus (golden ไม่ขยับโดยพิสูจน์)
    """
    _iv_now = str(result.get('iv_number') or '').strip()
    if (not _iv_now) or iv_digits_garbage(_iv_now):
        _pb_iv_lastresort(df, result, row_start, header_end, ncols)


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
