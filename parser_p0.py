# -*- coding: utf-8 -*-
# ruff: noqa: F401, F811  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""parser_p0.py — DATA EXTRACTION LAYER (ส่วนต่อจาก parser_p0a) — column detection หลัก + invoice + address

ซอยจาก parser_p0 เดิม (660 LOC) แบบ "คัดลอกเป๊ะทุกตัวอักษร" — logic/golden ไม่เปลี่ยน.
โครง cascade: parser_p0a (ฐาน: filename/merge/workbook/_dic_* helpers) ← [parser_p0 ไฟล์นี้]
  ครอบ: detect_item_columns(+safe/_compute_col_confidence), _pick_best_iv_safe, check_iv_format, _addr_parse_confidence.
ทุกชื่อจาก parser_p0a ดึงผ่าน `import *` → ผู้บริโภคปลายน้ำ (parser_p1) ยัง `from parser_p0 import *` ได้เหมือนเดิม.
"""
from __future__ import annotations

from parser_p0a import (   # [F3 de-star] explicit re-export shim (split-base chain; เดิม `import *`)
    Counter, Decimal, ROUND_HALF_UP, _D,
    _NUM_FULL_RE, _THAI_NUM_WORD_RE, _cell_to_num, _declared_period_from_filename,
    _dic_collect_numeric, _dic_find_amt, _dic_find_name, _dic_find_seq,
    _dic_int_run, _dic_item_rows, _dic_pick_qty_price, _dic_pick_unit,
    _dic_score_combo, _dic_text_score, _find_unit_col, _is_seq_run,
    _is_thai_amount_words, _ivp_year2_to_ce, _ivp_year4_to_ce, _raw_company_form,
    _taxid_checksum_ok, _trim_cache, _unit_canon, _vat_tolerance,
    clean_tax_id, datetime, defaultdict, detect_ocr_input,
    extract_branch, extract_unit_hint, find_similar_in_thai_dict, formal_language_score,
    gen_explanation, glob, has_hidden_chars, log_system_issue,
    merge_continuation_bills, normalize_ocr, normalize_text, os,
    parse_date_any, parse_filename, pd, predict_category,
    pythainlp_spell_check, re, read_workbook, remove_branch_suffix,
    safe, state, to_conf01, unicodedata,
    xlrd,
)  # noqa: F401  (re-export ขึ้น chain — หลายชื่อไม่ได้ใช้ภายในไฟล์นี้)

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
