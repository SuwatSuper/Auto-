# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""parser.py — DATA EXTRACTION LAYER (กลืนไฟล์ Excel → แกะโครงสร้างบิล)

ย้ายมาจาก monolith แบบ "คัดลอกเป๊ะทุกตัวอักษร" — logic เดิม 100%.
ครอบคลุม: read_workbook, column detection (_dic_*), invoice (_pick_best_iv/check_iv_format),
identity (taxid/branch scan), amounts (vat/label/reconcile), address, block parser (_pb_*),
TOR format (_tor_*), parse_sheet, parse_file, _raw_iv_form, Text→ตัวเลข audit.

⚠️ audit state (_AUDIT_CTX / _TEXT_NUM_RECOVERIES) อยู่ใน state.py
   (reset ผ่าน .clear() → main alias เห็น object เดียวกัน — pattern เดียวกับ _SYSTEM_ISSUES)

ตำแหน่งใน DAG:
    config + state + puopuy_core + puopuy_dates + puopuy_units + diagnostics + thai_text
        │
        └─ [parser]  ←── main เรียก parse_file/parse_sheet ผ่าน re-export
"""
from __future__ import annotations

import os
import re
import glob
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP  # [F2/ADR-020] money-math: VAT ด้วย Decimal+HALF_UP

import pandas as pd

import state
# [F3] ลบ `from config import *` — parser_p0a ไม่ใช้ config (re-export ย้ายไป parser_p1 ที่ใช้จริง)
from puopuy_core import (to_conf01, normalize_text, has_hidden_chars, clean_tax_id,
                         _taxid_checksum_ok, remove_branch_suffix, _raw_company_form,
                         extract_branch, safe)
from puopuy_dates import parse_date_any, _ivp_year2_to_ce, _ivp_year4_to_ce
from puopuy_units import extract_unit_hint, _unit_canon, _D, _vat_tolerance
from diagnostics import log_system_issue, _trim_cache
from thai_text import (find_similar_in_thai_dict, predict_category, pythainlp_spell_check,
                       detect_ocr_input, normalize_ocr, formal_language_score, gen_explanation)

try:
    import xlrd          # .xls เก่า — ไม่มีก็รัน .xlsx ได้ (เหมือน main เดิม)
except Exception:
    xlrd = None

# [P-DAG พาส3a] ฟังก์ชันระดับชื่อไฟล์/รวมหน้า — ย้ายมาจาก main (verbatim, logic เดิม)
#   parse_filename: แกะ code/ปี/เดือน(ช่วง)/วัน จากชื่อไฟล์
#   _declared_period_from_filename: คืน (ปีพ.ศ., เซ็ตเดือน) เฉพาะเมื่อชื่อไฟล์ระบุช่วงเดือนชัด
#   merge_continuation_bills: รวมบิลข้ามชีต (หน้าต่อ) ตาม IV+ลำดับ seq
#   → parser พึ่งตัวเองได้ ไม่ต้อง lazy-import กลับ main อีก (ลบ _from_main)


def merge_continuation_bills(bills):
    """รวมบิลที่ถูก parse แยกชีต แต่จริง ๆ เป็นใบเดียวกัน (หน้าต่อ).

    เกณฑ์รวม (ต้องครบทั้ง 2 ข้อ):
      1. iv_number ตรงกันเป๊ะ (ในไฟล์เดียวกัน)
      2. ลำดับสินค้าต่อเนื่อง — seq แรกของชีตถัดไป > seq สุดท้ายของชีตก่อน
         (#8→#9 = ต่อ | #1→#1 = คนละบิล แม้ IV เผลอซ้ำ)

    ไม่รวม → คืนบิลเดิมไม่แตะ. รวม → ยุบเป็นบิลเดียว เอา items มาต่อกัน
    แล้วคำนวณ subtotal/vat/total ใหม่จาก items ที่ครบ
    """
    if not bills:
        return bills

    groups = defaultdict(list)
    order = []
    for b in bills:
        iv = (b.get('iv_number') or '').strip()
        # ไม่มี IV → ไม่จับกลุ่ม (กันรวมมั่ว) ใช้ id ทำ key เฉพาะตัว
        key = iv if iv else f'__noiv_{id(b)}'
        if key not in groups:
            order.append(key)
        groups[key].append(b)

    merged = []
    for key in order:
        grp = groups[key]
        if len(grp) == 1:
            merged.append(grp[0])
            continue

        # IV ซ้ำ → เรียงตาม seq เริ่มต้นของแต่ละชีต
        def _min_seq(b):
            seqs = [it['seq'] for it in b.get('items', []) if it.get('seq') is not None]
            return min(seqs) if seqs else 999
        grp_sorted = sorted(grp, key=_min_seq)

        base = grp_sorted[0]
        combined_items = list(base.get('items', []))
        used_sheets = [str(base.get('sheet', ''))]

        for nxt in grp_sorted[1:]:
            nxt_seqs = [it['seq'] for it in nxt.get('items', []) if it.get('seq') is not None]
            cur_max = max((it['seq'] for it in combined_items
                           if it.get('seq') is not None), default=0)
            # ต่อเนื่องจริง → ผนวก
            if nxt_seqs and min(nxt_seqs) > cur_max:
                combined_items += nxt.get('items', [])
                used_sheets.append(str(nxt.get('sheet', '')))
            else:
                # IV ซ้ำแต่ลำดับไม่ต่อ = คนละบิล → แยกไว้ตามเดิม
                merged.append(nxt)

        if len(used_sheets) > 1:
            # มีการรวมจริง → สร้างบิลใหม่จาก base + items ที่ต่อมา
            new_bill = dict(base)
            new_bill['items'] = combined_items
            new_bill['sheet'] = ' + '.join(used_sheets)
            new_bill['_merged_pages'] = used_sheets
            # v5.9 FIX-5: รวม issues จากทุกชีตที่ถูกผนวก (เดิมเก็บแค่ชีตแรก)
            combined_issues = list(base.get('issues', []))
            for nxt_bill in grp_sorted[1:]:
                if str(nxt_bill.get('sheet', '')) in used_sheets:
                    combined_issues.extend(nxt_bill.get('issues', []))
            new_bill['issues'] = combined_issues
            # คำนวณ subtotal ใหม่จาก items ที่ครบ (qty×price)
            _sub = 0.0
            for it in combined_items:
                q, p = it.get('qty'), it.get('price')
                if isinstance(q, (int, float)) and isinstance(p, (int, float)):
                    _sub += q * p
            if _sub > 0:
                new_bill['subtotal'] = round(_sub, 2)
                # [F2/ADR-020] VAT ด้วย Decimal+ROUND_HALF_UP แล้ว cast กลับ float (คงชนิดที่เก็บ → hash ขยับเฉพาะเมื่อค่าปัดเศษต่างจริง)
                new_bill['vat'] = float((_D(_sub) * Decimal('0.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
                new_bill['total'] = round(_sub + new_bill['vat'], 2)
            new_bill['issues'].append({
                'code': 'IV001', 'severity': 'INFO', 'category': 'เอกสาร',
                'name': 'รวมบิลข้ามหน้า',
                'detail': f'บิล {key} รวมจาก {len(used_sheets)} ชีต: {", ".join(used_sheets)} '
                          f'({len(combined_items)} รายการ)'
            })
            merged.append(new_bill)
        else:
            # ไม่ได้รวมอะไรเลย → คืน base เดิม
            merged.append(base)

    return merged

def parse_filename(filename):
    """v5.8 [FIX-8]: รองรับ filename ที่มีช่วงเดือน เช่น 'TSH 69.03-04.xls'"""
    base = re.sub(r'\.(xls|xlsx)$', '', os.path.basename(filename), flags=re.IGNORECASE)
    info = {'code':'','year':None,'month':None,'month_end':None,'day':None}
    m = re.match(r'^([A-Za-zก-๙]+)', base)
    if m: info['code'] = m.group(1)
    # v5.8: ตรวจ pattern "YY.MM-MM" หรือ "YYYY.MM-MM" ก่อน
    m_range = re.search(r'(\d{2,4})[\.\-_\s](\d{1,2})\s*[-–]\s*(\d{1,2})(?!\d)', base)
    if m_range:
        try:
            y = int(m_range.group(1))
            mm1 = int(m_range.group(2)); mm2 = int(m_range.group(3))
            if 1 <= mm1 <= 12 and 1 <= mm2 <= 12 and mm1 <= mm2:
                info['year'] = 2500+y if y<100 else (y+543 if y<2500 else y)
                info['month'] = mm1
                info['month_end'] = mm2
                return info
        except (ValueError, TypeError):
            # คาดได้: ตัวเลขใน group แปลงไม่ได้ → ตกไป legacy logic (None/ค่าเริ่มต้นถูกต้อง)
            # error ชนิดอื่นที่ไม่คาด ปล่อยลอยขึ้นไปให้ขอบเขตชีต (SYS001) บันทึก ไม่กลืนเงียบ
            pass
    # fallback: legacy logic
    nums = [int(n) for n in re.findall(r'\d+', base)]
    if len(nums) >= 1:
        y = nums[0]
        info['year'] = 2500+y if y<100 else (y+543 if y<2500 else y)
    if len(nums) >= 2:
        if 1 <= nums[1] <= 12: info['month'] = nums[1]
    if len(nums) >= 3:
        if 1 <= nums[2] <= 31: info['day'] = nums[2]
    return info

def _declared_period_from_filename(filename):
    """v8.5 [FIX-XMONTH]: คืน (year_be|None, set_of_months|None) ที่ "ชื่อไฟล์ประกาศไว้ชัดเจน".
    - ใช้เฉพาะเมื่อชื่อไฟล์ระบุ "ช่วงเดือน" จริง (เช่น 69.03-04) → คืนเซ็ตเดือนในช่วง
    - ถ้าไม่มีช่วงเดือนชัดเจน (เดือนเดียว/ไม่ระบุ) → คืน (year, None)
      เพื่อบอก caller ว่า "ห้าม suppress" → พฤติกรรมเดิมทุกประการ
    ปลอดภัยเสมอ: ไม่ throw
    """
    try:
        info = parse_filename(filename)
    except Exception:
        return (None, None)
    mm1, mm2 = info.get('month'), info.get('month_end')
    if mm1 and mm2 and 1 <= mm1 <= mm2 <= 12:
        return (info.get('year'), set(range(mm1, mm2 + 1)))
    return (info.get('year'), None)

def read_workbook(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.xls' and xlrd is None:   # v8.2: .xls ต้องมี xlrd — แจ้งชัดแทน error ปริศนา (ไฟล์นี้จะถูกข้าม)
        raise RuntimeError('ไฟล์ .xls ต้องติดตั้ง xlrd ก่อน:  pip install xlrd  (หรือบันทึกเป็น .xlsx)')
    return pd.ExcelFile(filepath, engine='xlrd' if ext=='.xls' else 'openpyxl')

def _find_unit_col(text_c, qty_col, price_col, name_col):
    """v5.8o: หา unit_col แบบมองทั้งสองฝั่ง — รองรับ unit อยู่ก่อน qty
    (เช่นไฟล์ TKH: หน่วย→จำนวน→ราคา) ไม่ใช่แค่ระหว่าง qty-price
    เลือกคอลัมน์ข้อความที่อยู่หลังชื่อสินค้า และใกล้ qty ที่สุด
    """
    if not text_c or qty_col is None:
        return None
    cands = [c for c in text_c if c > name_col]
    if not cands:
        return None
    cands.sort(key=lambda c: abs(c - qty_col))
    return cands[0]

def _dic_int_run(M, c):
    """เก็บ int 1..50 ในคอลัมน์ c
    [OPT-1] อ่านจาก M = df.to_numpy(dtype=object) (materialize ครั้งเดียวใน detect_item_columns)
      แทน df.iloc[:,c].dropna() ต่อคอลัมน์ — เดิมเป็น hot loop 16,553 ครั้ง บน 106 ไฟล์.
      ความถูกต้อง (byte-identical): M[r,c] ≡ df.iat[r,c] เชิงพฤติกรรม (พิสูจน์ 836 ชีต/555k cell,
      DECISIONS §OBJ-PERF) และ `for v in M[:,c] if not pd.isna(v)` ≡ `df.iloc[:,c].dropna()`
      (ข้ามค่า null ตามลำดับแถวเหมือนกัน). per-value `int(float(str(v)))` + ช่วง 1..50 ไม่แตะ.
      ตรึงด้วย test_dic_int_run_equiv.py (differential vs implementation เดิม)."""
    ints = []
    for v in M[:, c]:
        if pd.isna(v):
            continue
        try:
            n = int(float(str(v)))
        except (ValueError, TypeError):
            continue
        if 1 <= n <= 50: ints.append(n)
    return ints

# [FIX-BAHTTEXT] ตัวตรวจ "ยอดเงินเป็นตัวอักษรไทย" (บาทตัวอักษร) เพื่อกันถูกนับเป็น "รายการสินค้า"
#   ปัญหาจริงจากลูกค้า: ITM016 ฟ้อง 'พบรายการ "สองแสนแปดหมื่นสี่พันแปดร้อยสาม" แต่คนคีย์ข้อมูล
#   ไม่ระบุเลขลำดับ' — ทั้งที่ข้อความนั้นคือ "ยอดรวมเป็นคำ" ไม่ใช่สินค้า (ไม่ต้องมีลำดับ).
#   หมายเหตุ: ตัวแปลง "คำไทย→ตัวเลข" แบบบังคับต้องมีคำว่า "บาท" จะจับเคสนี้ไม่ได้
#   (ยอดเป็นคำล้วนไม่มี 'บาท') จึงต้องมีตัวตรวจเฉพาะที่ทนกว่าในชั้น parser.
_THAI_NUM_WORD_RE = re.compile(
    r'(ศูนย์|หนึ่ง|สอง|สาม|สี่|ห้า|หก|เจ็ด|แปด|เก้า|สิบ|ยี่สิบ|ยี่|เอ็ด|'
    r'ร้อย|พัน|หมื่น|แสน|ล้าน|บาท|ถ้วน|สตางค์)')

def _is_thai_amount_words(s):
    """True ถ้า s เป็น 'ยอดเงินเป็นตัวอักษรไทย' (ไม่ใช่ชื่อสินค้า).
    เกณฑ์ (เข้มเพื่อกัน false positive กับชื่อสินค้าที่บังเอิญมีคำเลข 1 คำ):
      • พบ 'คำเลขไทย/หน่วยเงิน' ≥ 3 คำ  (ยอดจริงยาวเสมอ เช่น สอง-แสน-แปด-หมื่น-…)
      • ตัดคำเลข+ช่องว่าง/วงเล็บ/จุลภาคออกแล้ว เหลือ 'เศษที่ไม่ใช่ตัวเลขคำ' ≤ 2 อักขระ
        (= ทั้งสตริงเป็นจำนวนเป็นคำล้วน; ยอมเศษเล็กน้อยจาก OCR)
    ตัวอย่าง True : 'สองแสนแปดหมื่นสี่พันแปดร้อยสาม', 'ห้าแสนแปดพันสองร้อยห้าสิบบาทถ้วน'
    ตัวอย่าง False: 'แผ่นสเตนเลส 304', 'เครื่องฉีดน้ำแรงดันสูง 1500 บาร์', 'ตราว่าว แป้ง 1 กก.'
    """
    if not s:
        return False
    s = str(s).strip()
    tokens = _THAI_NUM_WORD_RE.findall(s)
    if len(tokens) < 3:
        return False
    residue = _THAI_NUM_WORD_RE.sub('', s)
    residue = re.sub(r'[\s\(\)\-,\.]', '', residue)
    return len(residue) <= 2

def _is_seq_run(ints):
    """ints (เรียงตามแถว) เป็น 'คอลัมน์ลำดับสินค้า' ที่น่าเชื่อถือหรือไม่.

    [FIX-CONT] เกณฑ์เดิม `ints[0]==1` บังคับให้ลำดับต้อง 'เริ่มที่ 1' →
      บิลหลายหน้า (หน้าต่อเริ่ม #9,10,11,…) ถูกปฏิเสธ แล้วระบบไป lock คอลัมน์ qty
      ที่บังเอิญเป็น 1,1,1 เป็น seq ผิด → name_col=None → ดึงรายการได้ 0 → merge หน้าต่อล้ม
      → บิลถูกนับซ้ำ/ยอดรวมเกินจริง.
    เกณฑ์ใหม่ (ครอบคลุมหน้าแรก+หน้าต่อ, ทน 'ลำดับซ้ำจากการคีย์', แต่กันคอลัมน์ qty/ราคา):
      • 1 ค่า  : ยอมรับเฉพาะ '1' (คงพฤติกรรมเดิมของบิลรายการเดียวหน้าแรก)
      • ≥2 ค่า : (1) non-decreasing — ไล่ขึ้นไม่ลด (ยอมเลขซ้ำ เช่น 5,5 ที่คนคีย์ลำดับซ้ำ)
                 (2) spans       — ปลายมากกว่าต้นจริง (กัน qty ค่าเดียวซ้ำ เช่น 1,1,1,1 ที่ max==min)
                 (3) dense       — max-min+1 ≤ n+2 (ยอม gap/ซ้ำเล็กน้อย, กันคอลัมน์เลขกระจาย)
    ผลลัพธ์:
      [1,2,3,…]       ✓  [1,2,4] ✓ (gap)  [1,2,3,4,5,5,6,7] ✓ (ซ้ำ — บิลจริง)
      [9,10,11,12]    ✓  (แก้บั๊กหน้าต่อ)
      [1,1,1,1] ✗ (qty: ไม่มี span)   [20,10,10,1,…] ✗ (qty/ราคา: ไม่ non-decreasing)
    """
    if not ints:
        return False
    if len(ints) == 1:
        return ints[0] == 1
    non_decreasing = all(ints[i+1] >= ints[i] for i in range(len(ints)-1))
    spans = ints[-1] > ints[0]
    dense = (ints[-1] - ints[0] + 1) <= len(ints) + 2
    return non_decreasing and spans and dense

def _dic_find_seq(M, ncols):
    """หา seq_col = คอลัมน์ลำดับสินค้า — คืน col index หรือ None.
    รองรับทั้งหน้าแรก (เริ่ม #1) และหน้าต่อ (เริ่ม #N) ผ่าน _is_seq_run.
    [OPT-1] รับ M (object ndarray จาก df.to_numpy(dtype=object)) แทน df —
      detect_item_columns materialize M ครั้งเดียวแล้วใช้ร่วม seq-detect + _dic_* per-cell ที่เหลือ."""
    seq_col, best = None, 0
    for c in range(ncols):
        ints = _dic_int_run(M, c)
        if _is_seq_run(ints):
            score = len(ints)*10 - c
            if score > best:
                best = score; seq_col = c
    return seq_col

def _dic_item_rows(M, nrows, seq_col):
    """หาแถวที่เป็นรายการสินค้า (seq 1..50) — M = sheet materialize แล้ว (M[r,c]==df.iat เชิงพฤติกรรม)"""
    return [r for r in range(nrows)
            if pd.notna(M[r, seq_col])
            and str(M[r, seq_col]).strip().removesuffix('.0').isdigit()   # [L4] ตัด .0 ท้ายเท่านั้น (เดิม replace ทั้งสตริง → '1.05'→'15')
            and 1 <= int(float(str(M[r, seq_col]))) <= 50]

def _dic_text_score(M, c, item_rows):
    """นับ cell ข้อความใน item_rows ของคอลัมน์ c → (count, total_len)"""
    cnt = tlen = 0
    for r in item_rows:
        v = M[r, c]
        if pd.isna(v): continue
        s = str(v).strip()
        if len(s) > 3 and not re.match(r'^[\d.,\s\-]+$', s):
            cnt += 1; tlen += len(s)
    return cnt, tlen

def _dic_find_name(M, ncols, seq_col, item_rows):
    """หา name_col = คอลัมน์ข้อความหลัง seq ที่มีเนื้อหามากสุด"""
    name_col, best_name = None, 0
    for c in range(seq_col+1, ncols):
        cnt, tlen = _dic_text_score(M, c, item_rows)
        if cnt >= max(1, len(item_rows)//2):
            sc = cnt*100 + tlen
            if sc > best_name:
                best_name = sc; name_col = c
    return name_col

_NUM_FULL_RE = re.compile(r'-?\d+(?:\.\d+)?')   # [OBJ-PERF] precompile (เรียกต่อ-cell บ่อย)
def _cell_to_num(v):
    """v5.8 refactor: helper ลด nesting — แปลง cell เป็น float หรือ None
    v6 CENTRAL: ตัวแปลงเลข "ทั่วไป" กลางตัวเดียวของทั้งระบบ (qty/price/amount/subtotal/vat/total
                + ชั้นตรวจจับคอลัมน์ + TOR) รองรับเลขที่เก็บเป็น Text/มี comma และกัน bool
                หมายเหตุ: ตัวแปลง "วันที่" / "เลขภาษี 13 หลัก" เป็นคนละตัว (เฉพาะทาง) โดยตั้งใจ
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        f = float(v)
        return None if f != f else f         # v6.x: กัน NaN (nan != nan) → ไม่ให้ nan หลุดไปปนยอด/คะแนน
    s = str(v).strip().replace(',', '')
    if _NUM_FULL_RE.fullmatch(s):
        return float(s)
    return None

def _dic_find_amt(M, ncols, seq_col, item_rows):
    """หา amt_col = คอลัมน์ขวาสุดที่มีตัวเลข > 100
    v6: ผ่าน converter กลาง _cell_to_num → หา amt_col เจอแม้ยอดเก็บเป็น Text"""
    for c in range(ncols-1, seq_col, -1):
        nums = []
        for r in item_rows:
            fv = _cell_to_num(M[r, c])
            if fv is not None and fv > 100:
                nums.append(fv)
        if len(nums) >= max(1, len(item_rows)//2):
            return c
    return None

def _dic_collect_numeric(M, item_rows, name_col, amt_col):
    """เก็บ numeric/text columns ระหว่าง name กับ amount → (nums_c, text_c)"""
    nums_c, text_c = [], []
    for c in range(name_col+1, amt_col):
        nvs, tvs = [], []
        for r in item_rows:
            v = M[r, c]
            if pd.isna(v): continue
            fv = _cell_to_num(v)              # v6: ผ่าน converter กลาง → รับเลขที่เก็บเป็น Text ด้วย
            if fv is not None:
                nvs.append(fv)
            else:
                s = str(v).strip()
                if s and not re.match(r'^[\d.,\s]+$', s): tvs.append(s)
        if nvs: nums_c.append((c, nvs))
        if tvs: text_c.append(c)
    return nums_c, text_c

def _dic_score_combo(M, item_rows, amt_col, qc, pc):
    """ทดสอบ qty×price ≈ amount บนทุก item row → (ok, total)"""
    ok = total = 0
    for r in item_rows:
        q = _cell_to_num(M[r, qc]); p = _cell_to_num(M[r, pc]); a = _cell_to_num(M[r, amt_col])
        if q is None or p is None or a is None: continue
        if a == 0: continue
        total += 1
        if abs(q*p - a) / max(abs(a), 1) < 0.02:
            ok += 1
    return ok, total

def _dic_pick_qty_price(M, item_rows, amt_col, nums_c):
    """เลือก qty_col/price_col จาก nums_c — คืน (qty_col, price_col)"""
    if len(nums_c) == 1:
        return nums_c[0][0], None
    if len(nums_c) < 2:
        return None, None
    best_combo = None; best_ok = -1
    for i in range(len(nums_c)):
        for j in range(len(nums_c)):
            if i == j: continue
            qc, pc = nums_c[i][0], nums_c[j][0]
            ok, total = _dic_score_combo(M, item_rows, amt_col, qc, pc)
            if total > 0 and ok > best_ok:
                best_ok = ok; best_combo = (qc, pc, ok, total)
    if best_combo and best_combo[3] > 0 and best_combo[2] / best_combo[3] >= 0.5:
        return best_combo[0], best_combo[1]
    # fallback heuristic เดิม (min=qty, max=price)
    nums_c_sorted = sorted(nums_c, key=lambda x: max(x[1]))
    return nums_c_sorted[0][0], nums_c_sorted[-1][0]

def _dic_pick_unit(text_c, qty_col, price_col, name_col):
    """เลือก unit_col — ระหว่าง qty-price ก่อน, ไม่เจอใช้ _find_unit_col"""
    if price_col is not None:
        for c in text_c:
            if min(qty_col, price_col) < c < max(qty_col, price_col):
                return c
    return _find_unit_col(text_c, qty_col, price_col, name_col)


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__=[n for n in list(globals().keys()) if not n.startswith('__') and n!='annotations']
