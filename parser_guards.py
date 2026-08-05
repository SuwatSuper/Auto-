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
# [ADR-174] ชุด prefix 2 หลักของรหัสไปรษณีย์ไทยทุกจังหวัด — ใช้กัน last-resort หยิบ zip เป็นเลขเอกสาร
from thai_postal import PROVINCE_POSTAL_PREFIXES as _PPP
PROVINCE_POSTAL_PREFIXES_2 = {p for _prefs in _PPP.values() for p in _prefs}
del _PPP


# [ADR-174/BUGHUNT M-F2] path สำเนาชื่อซ้ำที่ SYS004 "ข้าม" ในรอบสแกนล่าสุด — ให้ _move_processed_files
#   เก็บเข้าซับโฟลเดอร์ "สำเนาซ้ำ_ข้าม" ด้วย. เดิมสำเนาค้างในโฟลเดอร์ input → รอบถัดไปชื่อไม่ซ้ำแล้ว
#   → ถูกตรวจซ้ำ "เงียบสนิท" เป็นบิลใหม่ (เคสจริง 11.06.69 backup-subfolder). reset ทุกครั้งที่สแกนใหม่.
SYS004_SKIPPED_DUP_PATHS = []

def get_files_via_drive(folder_path):
    SYS004_SKIPPED_DUP_PATHS.clear()   # [ADR-174] รายการของ "รอบสแกนนี้" เท่านั้น
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
        # [M2] กันตรวจ output ของระบบเองซ้ำ: ตารางสรุปบริษัท company_summary*.xlsx (เดิมกรองแค่ audit_v58_)
        if base.startswith('company_summary'):
            continue
        # [M2] ข้ามไฟล์ใน "ตรวจแล้ว_*" (โฟลเดอร์ปลายทางของไฟล์ที่ตรวจแล้ว) — กัน recursive scan
        #   หยิบกลับมาตรวจซ้ำรอบหน้าเมื่อ report_dir อยู่ใน/เท่ากับ data_dir (เช่น fallback REPORT_DIR=cwd).
        if any(part.startswith('ตรวจแล้ว_') for part in os.path.normpath(f).split(os.sep)):
            continue
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
        SYS004_SKIPPED_DUP_PATHS.extend(skipped)   # [ADR-174] ให้ AUTO เก็บสำเนาเข้าที่ ไม่ค้างให้ตรวจซ้ำรอบหน้า
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
                # [ADR-174/BUGHUNT] กัน token "ปีเปล่า ๆ" (2569 ทั้ง พ.ศ./ค.ศ. — layout ไทยพิมพ์ปีเป็น
                #   เลขใกล้ cell วันที่ = ผ่านสัญญาณ near_date พอดี) และ "รหัสไปรษณีย์" (5 หลักในแถว
                #   ที่มีคำที่อยู่) ถูกหยิบเป็นเลขเอกสาร — ตรง safety-claim ใน docstring ที่เดิมไม่ถูกบังคับจริง.
                #   IV005 ฟ้อง "ไม่มีเลขที่เอกสาร" อย่างซื่อตรงดีกว่าได้เลขมั่ว (false negative < false positive
                #   ไม่ใช้กับ identity ของเอกสาร). corpus: last-resort dormant 100% → golden ไม่ขยับ.
                if len(tok) == 4 and not tok.startswith('0') and (1990 <= int(tok) <= 2100 or 2500 <= int(tok) <= 2650):
                    continue   # ปี ค.ศ./พ.ศ. เป็นไปได้ → ไม่รับเป็น IV
                if len(tok) == 5 and tok[:2] in PROVINCE_POSTAL_PREFIXES_2:
                    _rowtxt = ' '.join(str(M[r, cc]) for cc in range(ncols) if not pd.isna(M[r, cc]))
                    if any(k in _rowtxt for k in ('ถนน', 'ตำบล', 'อำเภอ', 'แขวง', 'เขต', 'จังหวัด', 'ต.', 'อ.', 'จ.', 'กรุงเทพ', 'กทม')):
                        continue   # รหัสไปรษณีย์ในแถวที่อยู่ → ไม่รับเป็น IV
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
    except Exception as e:
        # [ADR-111] fallback ห้ามทำให้ parser ล้ม — แต่ "ห้ามเงียบสนิท": ทิ้งร่องรอย SYS ให้ตามได้
        #   (สอดคล้อง mandate diagnostics: เลิก except:pass ที่มองไม่เห็น). logger ห้ามทำให้ล้มซ้ำ.
        try:
            from diagnostics import log_system_issue
            log_system_issue(code='SYS-IVLAST', severity='WARNING', category='ระบบ',
                             name='iv last-resort ล้ม (ข้าม ไม่กระทบผลตรวจ)',
                             detail=f'{type(e).__name__}: {e}', echo=False)
        except Exception:
            pass
        return


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


def _bill_amount_strings(result):
    """คืน set ของ "ยอดเงินบนบิล" ในรูป string เลขจำนวนเต็ม (เฉพาะค่าที่ลงตัวพอดี)
    ครอบ subtotal / vat / total + ยอดรายการสินค้า. ใช้เทียบกันเลขที่เอกสารชนยอด.
    (ยอดที่มีเศษทศนิยม เช่น 181123.5 ไม่ถูกแปลงเป็น string เลขเต็ม จึงไม่ชนเลขเอกสารอยู่แล้ว)"""
    amts = set()

    def _add(a):
        if isinstance(a, (int, float)) and not isinstance(a, bool):
            try:
                if a == int(a):
                    amts.add(str(int(a)))
            except (ValueError, OverflowError):
                pass

    for k in ('subtotal', 'vat', 'total'):
        _add(result.get(k))
    for it in (result.get('items') or []):
        _add(it.get('amount'))
    return amts


def reject_iv_equal_amount(df, result, row_start, header_end, ncols):
    """[F-MONEYIV v9.3.1] กัน "ยอดเงินบนบิล" ถูกอ่านเป็นเลขที่เอกสาร แล้วกู้เลขจริงคืน.

    เคสจริง (SHS 69.05 เพิ่ม — 21 บิล): _parse_block ตั้ง header_end = row_start+20 ซึ่ง
      "ครอบทั้งชีต" รวมแถวยอดรวม (subtotal/total). _pick_best_iv รับเลขล้วน ≥5 หลัก →
      subtotal 6 หลัก เช่น '200500' (score 27) ชนะเลขเอกสารจริง 5 หลัก '05070' (score 25)
      เพราะ pandas อ่านยอดที่ลงตัวเป็น int (สตริง '200500' ไม่มี '.0') → money-guard เดิม
      (\\.\\d) ไม่ทำงาน. ผล: iv = ยอดเงิน → IV003 (เลขซ้ำข้ามวัน), DT004/period-embed,
      IV004 (เลขไม่ไล่เรียง) ฟ้องผิดทั้งชุด แม้บิลถูกต้อง.

    Invariant ที่บังคับ: "เลขที่เอกสาร ≠ ยอดเงินใด ๆ บนบิลเดียวกัน" (จริงเสมอเชิงธุรกิจ).
      ถ้า iv == ยอด → ล้าง iv แล้วเรียก last-resort (หาเลขโดด 4-5 หลักในโซน header ที่
      ติดวันที่/อยู่ครึ่งขวา เช่น '05070' ที่อยู่ติด cell วันที่) มาแทนเลขที่ถูกต้อง.

    ความปลอดภัย/golden: corpus 834 บิล สแกนแล้วไม่มีบิลใด iv == ยอดของตัวเอง (0 ราย) →
      เงื่อนไข if ไม่เคยเป็นจริงบน corpus → dormant 100% → golden hash ไม่ขยับ (พิสูจน์ด้วย
      golden_master ก่อน/หลัง). ทำงานเฉพาะไฟล์ที่ misread จริงเท่านั้น.
    """
    raw_iv = str(result.get('iv_number') or '').strip()
    iv = re.sub(r'\D', '', raw_iv)
    if not iv:
        return
    # [ADR-136] เฉพาะ iv "ตัวเลขล้วน" ถึงเข้าข่าย money-misread (ยอดเงินถูกอ่านเป็นเลขเอกสาร).
    #   iv ที่มีตัวอักษร (เช่น 'IV-1250' = เลขเอกสารจริง) ห้ามล้างเพราะ digits บังเอิญตรงยอด:
    #   เดิม re.sub ตัดอักษรทิ้ง → '1250' → ถ้ายอดบิล=1250 จะล้างเลขเอกสารจริงทิ้ง = false-positive.
    #   money-misread จริง (เช่น subtotal '200500') เป็นตัวเลขล้วนอยู่แล้ว → ยังจับได้. corpus delta=0.
    if not raw_iv.isdigit():
        return
    if iv in _bill_amount_strings(result):
        result['iv_number'] = ''
        result['iv_number_raw'] = ''
        result['_iv_score'] = -(10 ** 9)
        apply_iv_lastresort_if_needed(df, result, row_start, header_end, ncols)


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
