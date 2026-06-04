# -*- coding: utf-8 -*-
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

import pandas as pd

import state
from config import *
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
                new_bill['vat'] = round(_sub * 0.07, 2)
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

def _dic_int_run(df, c):
    """เก็บ int 1..50 ในคอลัมน์ c"""
    ints = []
    for v in df.iloc[:, c].dropna():
        try:
            n = int(float(str(v)))
        except (ValueError, TypeError):
            continue
        if 1 <= n <= 50: ints.append(n)
    return ints

def _dic_find_seq(df, ncols):
    """หา seq_col = คอลัมน์ลำดับ 1..50 — คืน col index หรือ None"""
    seq_col, best = None, 0
    for c in range(ncols):
        ints = _dic_int_run(df, c)
        if ints and ints[0] == 1 and max(ints) <= len(ints)+2:
            score = len(ints)*10 - c
            if score > best:
                best = score; seq_col = c
    return seq_col

def _dic_item_rows(M, nrows, seq_col):
    """หาแถวที่เป็นรายการสินค้า (seq 1..50) — M = sheet materialize แล้ว (M[r,c]==df.iat เชิงพฤติกรรม)"""
    return [r for r in range(nrows)
            if pd.notna(M[r, seq_col])
            and str(M[r, seq_col]).strip().replace('.0','').isdigit()
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

def detect_item_columns(df):
    """v5.8j + v5.8 refactor: แตกเป็น helper (_dic_*) ลด nesting ≤6
    - detect qty/price ด้วย qty×price≈amount (ทน column-swap)
    """
    nrows, ncols = df.shape
    seq_col = _dic_find_seq(df, ncols)
    if seq_col is None: return (None,)*6

    M = df.to_numpy(dtype=object)   # [OBJ-PERF] materialize ครั้งเดียว → _dic_* ต่อ-cell อ่าน M[r,c] (seq ใช้ df: column-vectorized)
    item_rows = _dic_item_rows(M, nrows, seq_col)
    if not item_rows: return seq_col, None, None, None, None, None

    name_col = _dic_find_name(M, ncols, seq_col, item_rows)
    amt_col = _dic_find_amt(M, ncols, seq_col, item_rows)

    qty_col = price_col = unit_col = None
    if name_col is not None and amt_col is not None and amt_col > name_col+1:
        nums_c, text_c = _dic_collect_numeric(M, item_rows, name_col, amt_col)
        qty_col, price_col = _dic_pick_qty_price(M, item_rows, amt_col, nums_c)
        if qty_col is not None:
            unit_col = _dic_pick_unit(text_c, qty_col, price_col, name_col)

    return seq_col, name_col, qty_col, unit_col, price_col, amt_col

def _compute_col_confidence(df, seq_col, qty_col, price_col, amt_col):
    """ADR-015: ความเชื่อมั่นของชุดคอลัมน์ที่ detect ได้ → 'HIGH' | 'LOW'.
    HIGH = qty×price ≈ amount (tol 2%) ผ่าน ≥50% ของ item rows (seq 1..50) ; ไม่งั้น 'LOW'.
    คอลัมน์หลักขาด/ตรวจไม่ได้ → 'LOW' (fail-safe: ไม่โยน exception ไม่เดามั่ว).
    เดิมฟังก์ชันนี้ "หายไป" → detect_item_columns_safe เป็น dead-on-arrival (NameError)."""
    if seq_col is None or qty_col is None or price_col is None or amt_col is None:
        return 'LOW'
    try:
        M = df.to_numpy(dtype=object)
        item_rows = _dic_item_rows(M, df.shape[0], seq_col)
        if not item_rows:
            return 'LOW'
        ok = chk = 0
        for r in item_rows:
            try:
                qf = float(M[r, qty_col]); pf = float(M[r, price_col]); af = float(M[r, amt_col])
            except (TypeError, ValueError):
                continue
            if af == 0:
                continue
            chk += 1
            if abs(qf * pf - af) / abs(af) < 0.02:
                ok += 1
        if chk == 0:
            return 'LOW'
        return 'HIGH' if ok / chk >= 0.5 else 'LOW'
    except Exception:
        return 'LOW'

def detect_item_columns_safe(df):
    """Additive wrapper รอบ detect_item_columns เดิม.
    คืน tuple เดิม 6 ค่า + ค่าที่ 7: col_confidence ('HIGH' | 'LOW')

      (seq_col, name_col, qty_col, unit_col, price_col, amt_col, col_confidence)

    HIGH = qty×price≈amount validate ผ่าน ≥50% ของ item rows
    LOW  = ไม่ผ่าน → detect_item_columns เดิมจะ fallback min/max
    """
    result = detect_item_columns(df)              # 6-tuple เดิม ไม่แตะ
    seq_col, name_col, qty_col, unit_col, price_col, amt_col = result
    conf = _compute_col_confidence(df, seq_col, qty_col, price_col, amt_col)
    return (*result, conf)

def _pick_best_iv_safe(text):
    """wrapper รอบ logic ของ _pick_best_iv — คืน (iv, ระดับความมั่นใจ)
      HIGH = คะแนนชนะ > 15  | LOW = 5-15 | NONE = ไม่มี candidate ผ่าน
    [FIX-IV] รองรับ IV ตัวเลขล้วน (ไม่มีอักษรนำ)
    """
    if not text:
        return None, 'NONE'
    s = str(text)

    # [FIX-IV] {1,5} → {0,5} : ตัวอักษรนำหน้าเป็น optional
    candidates = []
    for m in re.finditer(r'\b([A-Z]{0,5}[-\s]?\d{2,}(?:[-\s]?\d+)*)\b', s, re.IGNORECASE):
        _digit_only = re.sub(r'\D', '', m.group(1).upper())
        if len(_digit_only) < 6 or len(_digit_only) > 13:
            continue
        cand = m.group(1).upper().replace(' ', '').replace('-', '')
        # [FIX-IV] กัน match ว่างจาก {0,5}
        if not cand: continue
        candidates.append((cand, m.start(), m.group(1)))
    if not candidates:
        return None, 'NONE'

    LABELS = ['IV', 'INVOICE', 'INV', 'INV NO', 'INV.NO', 'NO.', 'NO ', 'เลขที่',
              'เลขที่ใบกำกับ', 'ใบกำกับ', 'เลขที่เอกสาร', 'DOC', 'DOC.', 'DOC NO',
              'BILL', 'BILL NO', 'TAX INVOICE']
    ANTI_PREFIX = ['TAX', 'BR', 'ITEM', 'CODE', 'SKU', 'PRODUCT', 'REF',
                   'PO', 'DO', 'BANK', 'ACCT', 'HS', 'ZIP', 'TEL', 'FAX',
                   'MOO', 'RD', 'ID', 'NO']
    ANTI_CONTEXT = ['ภาษี', 'เลขประจำตัว', 'TAX ID', 'TAX NO', 'รหัสสินค้า',
                    'รหัส', 'PO NO', 'DO NO', 'ที่อยู่', 'โทร']
    s_upper = s.upper()

    scored = []
    for cand, pos, raw in candidates:
        score = 0
        digits_part = re.sub(r'\D', '', cand)
        score += len(digits_part) * 2
        if any(lbl in s_upper[max(0, pos-30):pos] for lbl in LABELS):
            score += 20
        if re.match(r'^(IV|INV|CB|JRN|JV|RV|PV|J\d)', cand):
            score += 15
        # [FIX-IV] ให้คะแนน IV ตัวเลขล้วนแบบ ปปดด-running = +30
        #          (ก่อนหน้านี้ขาดไป ทำให้ _safe ให้คะแนนไม่ตรงกับ _pick_best_iv)
        _digits = re.sub(r'\D', '', cand)
        if re.fullmatch(r'\d{6,12}', _digits):
            _yy = int(_digits[:2]); _mm = int(_digits[2:4])
            if 60 <= _yy <= 79 and 1 <= _mm <= 12:
                score += 30
        # [FIX-IV] อักษร 1 ตัว + เลข 6+ = รหัสสินค้า = -20 (sync กับ _pick_best_iv)
        # v8.6 [FIX-IV-JSERIES]: เพิ่ม 'J\d' ใน exclusion ให้ตรงกับโบนัส IV-prefix (กัน J26050089 โดนโทษจนแพ้ยอดเงิน)
        if re.fullmatch(r'[A-Z]\d{6,}', cand) and not re.match(r'^(IV|INV|CB|JRN|JV|RV|PV|J\d)', cand):
            score -= 20
        prefix_letters = re.match(r'^([A-Z]+)', cand)
        if prefix_letters and prefix_letters.group(1) in ANTI_PREFIX:
            score -= 25
        ctx = s_upper[max(0, pos-30):min(len(s), pos+len(raw)+10)]
        if any(anti in ctx for anti in ANTI_CONTEXT):
            score -= 15
        if re.fullmatch(r'\d{13}', cand):
            score -= 30
        scored.append((score, cand))

    scored.sort(reverse=True)
    best_score, best_cand = scored[0]
    if best_score < 5:
        return None, 'NONE'
    if best_score <= 15:
        return best_cand, 'LOW'
    return best_cand, 'HIGH'

def _has_suspat_in_iv(iv):
    """หาตัวอักษรน่าสงสัยที่ขนาบด้วยตัวเลข เช่น O ระหว่าง 2 กับ 6
    คืน list ตัวอักษรที่น่าสงสัย — ว่างเปล่า = ปกติ
    ไม่แก้อะไร แค่ชี้ว่ามีตัวน่าสงสัย
    """
    SUSPECT = {'O', 'o', 'I', 'l'}   # ตัวที่หน้าตาคล้ายเลข 0/1
    chars = list(str(iv))
    found = []
    for i, ch in enumerate(chars):
        if ch not in SUSPECT:
            continue
        prev_d = i > 0 and chars[i-1].isdigit()
        next_d = i < len(chars) - 1 and chars[i+1].isdigit()
        if prev_d or next_d:
            found.append(ch)
    return found

def check_iv_format(bills):
    """ตรวจ iv_number ของทุกบิลในไฟล์เดียวกัน เทียบกันเอง
    เจอผิด → เพิ่ม issue code IV002 (ERROR) ลง bill['issues']
    ไม่แก้ตัวเลข ไม่เดา — แจ้งอย่างเดียว
    """
    from collections import Counter

    have_iv = [b for b in bills if b.get('iv_number')]

    # --- เกณฑ์ 0a [v5.9 FIX-IV-RAW]: อักขระแปลกปลอมในเลขเอกสารจริง ---
    #   เช็คจาก iv_number_raw (ตามที่พิมพ์ในเอกสารจริง) ไม่ใช่ตัวที่ clean แล้ว
    #   จับ . / , ฯลฯ ที่หลุดมา เช่น "IV6905-2000.6" — ทำได้แม้มีบิลใบเดียว
    for b in have_iv:
        iv_raw = str(b.get('iv_number_raw') or b['iv_number'])
        bad = re.sub(r'[A-Z0-9\-\s]', '', iv_raw.upper())  # เหลือเฉพาะอักขระแปลก
        if bad:
            b['issues'].append({
                'code': 'IV002', 'severity': 'ERROR', 'category': 'เอกสาร',
                'name': 'เลขที่เอกสารมีอักขระแปลกปลอม',
                'detail': f'เลขที่เอกสาร "{iv_raw}" มีอักขระผิดปกติ: '
                          f'{sorted(set(bad))} (น่าจะพิมพ์ผิด เช่น เคาะจุด/ทับ แทนตัวเลข) '
                          f'— เปิดไฟล์ต้นฉบับแก้ให้เป็นเลขเอกสารที่ถูกต้อง'
            })

    # --- เกณฑ์ 0: ตัวอักษรน่าสงสัยปนในเลข (ทำได้แม้มีบิลใบเดียว) ---
    for b in have_iv:
        if any(i.get('code') == 'IV002' for i in b['issues']):
            continue
        iv = str(b.get('iv_number_raw') or b['iv_number'])
        suspects = _has_suspat_in_iv(iv)
        if suspects:
            b['issues'].append({
                'code': 'IV002', 'severity': 'ERROR', 'category': 'เอกสาร',
                'name': 'เลขที่เอกสารมีตัวอักษรน่าสงสัย',
                'detail': f'เลขที่เอกสาร "{iv}" มีตัวอักษร {suspects} ปนอยู่ในกลุ่มตัวเลข '
                          f'(อาจพิมพ์ O แทน 0 หรือ I แทน 1) — ควรเปิดไฟล์ต้นฉบับตรวจสอบ'
            })

    # เกณฑ์ 1-3 ต้องมีบิล ≥2 ใบ ถึงเทียบกันได้
    if len(have_iv) < 2:
        return bills

    # --- เกณฑ์ 1: อักขระแปลกปลอม (IV ปกติมีแค่ A-Z 0-9 ขีด) ---
    for b in have_iv:
        iv = str(b['iv_number'])
        bad = re.sub(r'[A-Z0-9\-]', '', iv.upper())
        if bad:
            if any(i.get('code') == 'IV002' for i in b['issues']):
                continue
            b['issues'].append({
                'code': 'IV002', 'severity': 'ERROR', 'category': 'เอกสาร',
                'name': 'เลขที่เอกสารมีอักขระแปลกปลอม',
                'detail': f'เลขที่เอกสาร "{iv}" มีอักขระผิดปกติ: {list(bad)} '
                          f'— ควรเปิดไฟล์ต้นฉบับตรวจสอบ'
            })

    # --- เกณฑ์ 2: ความยาวรวมไม่ตรงกลุ่ม ---
    lengths = [len(str(b['iv_number'])) for b in have_iv]
    common_len, common_cnt = Counter(lengths).most_common(1)[0]
    if common_cnt >= len(have_iv) * 0.6:
        for b in have_iv:
            iv = str(b['iv_number'])
            if len(iv) != common_len:
                if any(i.get('code') == 'IV002' for i in b['issues']):
                    continue
                b['issues'].append({
                    'code': 'IV002', 'severity': 'ERROR', 'category': 'เอกสาร',
                    'name': 'เลขที่เอกสารยาวผิดปกติ',
                    'detail': f'เลขที่เอกสาร "{iv}" ยาว {len(iv)} ตัว '
                              f'แต่บิลส่วนใหญ่ในไฟล์ยาว {common_len} ตัว '
                              f'— ควรเปิดไฟล์ต้นฉบับตรวจสอบ'
                })

    # --- เกณฑ์ 3: จำนวนตัวเลขล้วนไม่ตรงกลุ่ม ---
    digit_lens = [len(re.sub(r'\D', '', str(b['iv_number']))) for b in have_iv]
    cd_len, cd_cnt = Counter(digit_lens).most_common(1)[0]
    if cd_cnt >= len(have_iv) * 0.6:
        for b in have_iv:
            iv = str(b['iv_number'])
            dl = len(re.sub(r'\D', '', iv))
            if dl != cd_len:
                if any(i.get('code') == 'IV002' for i in b['issues']):
                    continue
                b['issues'].append({
                    'code': 'IV002', 'severity': 'ERROR', 'category': 'เอกสาร',
                    'name': 'เลขที่เอกสารจำนวนหลักผิดปกติ',
                    'detail': f'เลขที่เอกสาร "{iv}" มี {dl} หลัก '
                              f'แต่บิลส่วนใหญ่มี {cd_len} หลัก '
                              f'— ควรเปิดไฟล์ต้นฉบับตรวจสอบ'
                })

    return bills

def _addr_parse_confidence(parts, mandatory_keys):
    """ดูว่าที่อยู่ที่แกะออกมา ครบ field สำคัญพอไหม
      parts          = dict ผลจาก parse_address_input
      mandatory_keys = set ของ key ที่จำเป็น
      คืน 'HIGH' ถ้าเจอ ≥60% ของ field จำเป็น, ไม่งั้น 'LOW'
    """
    if not mandatory_keys:
        return 'HIGH'
    found = sum(1 for k in mandatory_keys if parts.get(k))
    return 'HIGH' if found / len(mandatory_keys) >= 0.60 else 'LOW'


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__=[n for n in list(globals().keys()) if not n.startswith('__') and n!='annotations']
