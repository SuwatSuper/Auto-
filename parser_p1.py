# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""parser_p1 — OBJ-MAINT layer 1 (extract คัดลอกเป๊ะ, byte-identical).
cascade toolkit จาก parser_p0 (และชั้นล่างทั้งหมด)."""
from __future__ import annotations
from parser_p0 import (   # [F3 de-star] explicit re-export shim (split-base chain; เดิม `import *`)
    Counter, Decimal, ROUND_HALF_UP, _D,
    _NUM_FULL_RE, _THAI_NUM_WORD_RE, _addr_parse_confidence, _cell_to_num,
    _compute_col_confidence, _declared_period_from_filename, _dic_collect_numeric, _dic_find_amt,
    _dic_find_name, _dic_find_seq, _dic_int_run, _dic_item_rows,
    _dic_pick_qty_price, _dic_pick_unit, _dic_score_combo, _dic_text_score,
    _find_unit_col, _has_suspat_in_iv, _is_seq_run, _is_thai_amount_words,
    _ivp_year2_to_ce, _ivp_year4_to_ce, _pick_best_iv_safe, _raw_company_form,
    _taxid_checksum_ok, _trim_cache, _unit_canon, _vat_tolerance,
    check_iv_format, clean_tax_id, datetime, defaultdict,
    detect_item_columns, detect_item_columns_safe, detect_ocr_input, extract_branch,
    extract_unit_hint, find_similar_in_thai_dict, formal_language_score, gen_explanation,
    glob, has_hidden_chars, log_system_issue, merge_continuation_bills,
    normalize_ocr, normalize_text, os, parse_date_any,
    parse_filename, pd, predict_category, pythainlp_spell_check,
    re, read_workbook, remove_branch_suffix, safe,
    state, to_conf01, unicodedata, xlrd,
)  # noqa: F401  (re-export ขึ้น chain — หลายชื่อไม่ได้ใช้ภายในไฟล์นี้)
from config import (_ADDRESS_HINT_KEYWORDS, _LBL_SUBTOTAL, _LBL_TOTAL, _LBL_VAT,  # [F3] explicit — config ที่ parser_p1 ใช้
                    _MAX_TEXT_NUM_RECOVERIES, _TAXID_KW, _TAX_CONTEXT_KEYWORDS)

def _detect_vat_rows(df):
    nrows, ncols = df.shape
    # [OBJ-PERF] materialize ทั้งชีตครั้งเดียว → เลี่ยง pandas .iat per-cell (boxing แพง)
    #   M[r,c] เท่ากับ df.iat[r,c] เชิงพฤติกรรม: พิสูจน์ 836 ชีต/555,176 cell (isna/str/ตัวเลข/float ตรงหมด)
    #   ใช้ dtype=object เท่านั้น (per-element boxing) — ไม่ unify dtype ข้ามคอลัมน์ (กับดักที่ทำ _FastFrame พัง)
    M = df.to_numpy(dtype=object)
    # [FIX-VATMARK] คำบ่งบอก "บริบทภาษี" ในแถว — ใช้ปลดล็อก marker เลขกำกวม ('7'/'7.00')
    #   ที่ชนกับ "จำนวนสินค้า=7". เดิมลิสต์มี '7'/'7.00' ตรง ๆ → ทุกแถวรายการที่ qty=7
    #   ถูกตัดเป็นแถว VAT (พิสูจน์บนคอร์ปัส: เซลล์ '7'/'7.00' เป๊ะ 49 เซลล์ อยู่ใน "แถวรายการ"
    #   ทั้งหมด ไม่ใช่ VAT สักเซลล์) → parse_sheet หั่นบล็อกผิดกลางรายการ → รายการหาย/บิลซ้ำ.
    VAT_CONTEXT = ('ภาษีมูลค่าเพิ่ม', 'vat', 'ร้อยละ', 'มูลค่าเพิ่ม')
    vat_rows = []
    for r in range(nrows):
        # แถวนี้มี "บริบทภาษี" ไหม (เพื่ออนุญาต marker เลขกำกวม)
        row_has_vat_label = False
        for c in range(ncols):
            v = M[r, c]
            if pd.notna(v) and isinstance(v, str):
                low = v.lower()
                if any(tok in low for tok in VAT_CONTEXT):
                    row_has_vat_label = True
                    break
        for c in range(ncols):
            v = M[r, c]
            if pd.notna(v):
                # อัตรา 0.07 (numeric) = VAT ชัดเจน — ไม่ต้องมี label (VAT จริง 684 เซลล์มาทางนี้)
                try:
                    if isinstance(v,(int,float)) and abs(float(v) - 0.07) < 0.001:
                        vat_rows.append(r); break
                except (ValueError, TypeError, OverflowError):
                    # คาดได้: ค่าเซลล์แปลงเป็นเลขไม่ได้ → ข้ามเซลล์ (ไม่ใช่ VAT row — ถูกต้อง)
                    # error ชนิดอื่นปล่อยขึ้นขอบเขตชีต (SYS001 file/sheet) แทนการกลืนเงียบ
                    pass
                s = str(v).strip()
                # รูปแบบ "อัตราร้อยละ" ที่ชัดเจน (มี % หรือ .07) — ไม่ต้องมี label
                if s in ['0.07', '.07', '7%', '7 %']:
                    vat_rows.append(r); break
                # เลขกำกวม '7'/'7.00' = ยอมรับเฉพาะเมื่อแถวมี "บริบทภาษี" (กันชนกับจำนวนสินค้า)
                if s in ['7', '7.00'] and row_has_vat_label:
                    vat_rows.append(r); break
    return vat_rows
    return vat_rows

def _pick_best_iv(text, known_tax_id=None, return_score=False):
    # v8.3 [FIX-IV-BESTMATCH]: เพิ่ม return_score เพื่อให้ผู้เรียกเปรียบเทียบคะแนน
    #   ข้าม cell ได้ (best-match-wins) — ค่า default เดิมคืน str เหมือนเดิมทุกประการ
    _NOSCORE = (None, -10**9)
    if not text: return _NOSCORE if return_score else None
    s = str(text)

    _tax_digits = re.sub(r'\D', '', str(known_tax_id)) if known_tax_id else ''

    candidates = []
    for m in re.finditer(r'\b([A-Z]{0,5}[-\s]?\d{2,}(?:[-\s]?\d+)*)\b', s, re.IGNORECASE):
        _digit_only = re.sub(r'\D', '', m.group(1).upper())
        # [ปรับจูน] ลดเกณฑ์ลงมารับเลข 5 หลัก เพื่อเก็บ 04883 และ 244469
        if len(_digit_only) < 5 or len(_digit_only) > 13: continue
        cand = m.group(1).upper().replace(' ','').replace('-','')
        if not cand: continue
        # v5.9 [FIX-IV-TAXID]: ตัด candidate ที่เป็น "เลขภาษี" ทิ้ง — ทนเลข 0 นำหน้า
        #   บั๊กเดิม: cand 12 หลัก "125548006451" ≠ tax_id 13 หลัก "0125548006451"
        #   → ไม่ถูกตัด → เลขภาษีถูกหยิบมาเป็นเลขเอกสาร (โชว์ผิดตั้งแต่ต้นทาง)
        _cd = re.sub(r'\D', '', cand)
        if _tax_digits and len(_cd) >= 12 and _cd.lstrip('0') == _tax_digits.lstrip('0'):
            continue
        pos = m.start()
        # v9.1 [FIX-IV-MONEY]: เลขล้วน (ไม่มีอักษรนำ) ที่ตามด้วยจุดทศนิยมทันที = "จำนวนเงิน" ไม่ใช่เลขเอกสาร
        #   เช่น "102158.25" / "1,234.50" → กันยอดเงินถูกหยิบเป็นเลข IV (เลขจริงเช่น 04883 ต้องชนะ)
        #   IV ที่มีอักษรนำ (IV.../J.../CB...) ไม่โดน เพราะเช็คว่า cand ขึ้นต้นด้วยตัวเลขเท่านั้น
        _is_money = (cand[:1].isdigit() and re.match(r'\.\d', s[m.end():m.end()+2]) is not None)
        candidates.append((cand, pos, m.group(1), _is_money))

    if not candidates: return _NOSCORE if return_score else None

    LABELS = ['IV', 'INVOICE', 'INV', 'INV NO', 'INV.NO', 'NO.', 'NO ', 'เลขที่',
              'เลขที่ใบกำกับ', 'ใบกำกับ', 'เลขที่เอกสาร', 'DOC', 'DOC.', 'DOC NO',
              'BILL', 'BILL NO', 'TAX INVOICE']
    ANTI_PREFIX = ['TAX', 'BR', 'ITEM', 'CODE', 'SKU', 'PRODUCT', 'REF',
                   'PO', 'DO', 'BANK', 'ACCT', 'HS', 'ZIP', 'TEL', 'FAX',
                   'MOO', 'RD', 'ID', 'NO']
    # [ปรับจูน] เพิ่มคำดักทางรหัสไปรษณีย์
    ANTI_CONTEXT = ['ภาษี', 'เลขประจำตัว', 'TAX ID', 'TAX NO', 'รหัสสินค้า',
                    'รหัส', 'PO NO', 'DO NO', 'ที่อยู่', 'โทร', 'กรุงเทพ', 'แขวง', 'เขต', 'จ.']

    s_upper = s.upper()

    scored = []
    for cand, pos, raw, is_money in candidates:
        score = 0

        # v9.1 [FIX-IV-MONEY]: จำนวนเงิน (เลขล้วน + จุดทศนิยม) ติดลบแรง — กันยอดเงินถูกหยิบเป็นเลขเอกสาร
        if is_money:
            score -= 40

        digits_part = re.sub(r'\D','',cand)
        score += len(digits_part) * 2

        # [ปรับจูน] ให้คะแนนทำเล: ถ้าเลขกองอยู่ส่วนบนของเอกสาร (300 อักษรแรก) +15 คะแนน
        if pos < 300:
            score += 15

        context_around = s_upper[max(0, pos-30):min(len(s), pos+len(raw)+10)]

        # [ปรับจูน] เกราะป้องกันรหัสไปรษณีย์: ถ้าเลข 5 หลัก แล้วแถวนั้นมีคำว่ากรุงเทพ/เขต/แขวง หัก 50 คะแนน
        if len(digits_part) == 5 and any(word in context_around for word in ['กรุงเทพ', 'เขต', 'แขวง', 'จังหวัด', 'อำเภอ']):
            score -= 50

        context_before = s_upper[max(0, pos-30):pos]
        if any(lbl in context_before for lbl in LABELS):
            score += 20

        if re.match(r'^(IV|INV|CB|JRN|JV|RV|PV|J\d)', cand):
            score += 15

        _digits = re.sub(r'\D','',cand)
        if 6 <= len(_digits) <= 12:
            _yy = int(_digits[:2]); _mm = int(_digits[2:4])
            if 60 <= _yy <= 79 and 1 <= _mm <= 12:
                score += 30

        # v8.6 [FIX-IV-JSERIES]: exclusion ของโทษ product-code ต้องตรงกับโบนัส IV-prefix ด้านบน
        #   เดิมขาด 'J\d' → IV ซีรีส์ J (เช่น J26050089) โดนโทษ -20 จนแพ้ "เลขจำนวนเปล่า" (ยอดเงิน)
        #   → หยิบยอดเงินมาเป็นเลขเอกสาร ทำให้ IV002/IV003/IV004 ฟ้องผิด
        if re.fullmatch(r'[A-Z]\d{6,}', cand) and not re.match(r'^(IV|INV|CB|JRN|JV|RV|PV|J\d)', cand):
            score -= 20

        prefix_letters = re.match(r'^([A-Z]+)', cand)
        if prefix_letters and prefix_letters.group(1) in ANTI_PREFIX:
            score -= 25

        if any(anti in context_around for anti in ANTI_CONTEXT):
            score -= 15

        if re.fullmatch(r'\d{12,13}', cand):
            score -= 30

        scored.append((score, cand))

    scored.sort(reverse=True)
    if scored[0][0] < 5:
        return _NOSCORE if return_score else None
    return (scored[0][1], scored[0][0]) if return_score else scored[0][1]

def _extract_taxid_safe(s):
    """ดึงเลขภาษี 13 หลักอย่างปลอดภัย — คืน digits หรือ None
    A. มี keyword ภาษี → ดึงเลขหลัง keyword
    B. เลข 13 หลักติดกันสนิท (ไม่มีเลขอื่นชนหัวท้าย)
    C. pattern เลขภาษีคั่น -/space (d-dddd-ddddd-dd-d)
    ไม่ทำ: เอาเลขกระจายในประโยคมาต่อกัน
    """
    if not s: return None
    txt = str(s); low = txt.lower()
    # A: หลัง keyword
    for kw in _TAXID_KW:
        idx = low.find(kw.lower())
        if idx >= 0:
            after = txt[idx+len(kw):]
            m = re.search(r'([\d][\d\-\s]{11,30}[\d])', after)
            if m:
                d = re.sub(r'\D', '', m.group(1))
                if len(d) == 13: return d
                if len(d) == 12: return '0' + d
    # B: 13 หลักติดกันสนิท
    m = re.search(r'(?<!\d)(\d{13})(?!\d)', txt)
    if m: return m.group(1)
    # C: pattern คั่น -/space
    m = re.search(r'(?<!\d)(\d[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d)(?!\d)', txt)
    if m:
        d = clean_tax_id(m.group(1))
        if len(d) == 13: return d
    return None

def _taxid_from_cell(v, r, c):
    """ดึงเลขภาษีจาก cell เดียว — คืน (digits, raw, src) หรือ (None,None,None)"""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            if v == int(v):
                digits = str(int(v))
                if len(digits) == 13: return digits, digits, f'numeric cell [r{r},c{c}]'
                if len(digits) == 12: return '0' + digits, digits, f'numeric cell (lost 0) [r{r},c{c}]'
        except (ValueError, OverflowError):
            pass
        return None, None, None
    s = str(v).strip()
    if not s: return None, None, None
    m = re.search(r'(\d[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d)', s)
    if m:
        digits = clean_tax_id(m.group(1))
        if len(digits) == 13: return digits, s, f'formatted [r{r},c{c}]'
        if len(digits) == 12: return '0' + digits, s, f'formatted 12-digit [r{r},c{c}]'
    cleaned = re.sub(r'[\s\-]', '', s)
    if re.fullmatch(r'\d{13}', cleaned): return cleaned, s, f'pure 13-digit [r{r},c{c}]'
    if re.fullmatch(r'\d{12}', cleaned): return '0' + cleaned, s, f'pure 12-digit [r{r},c{c}]'
    return None, None, None

def _scan_tax_id_block(df, row_start, row_end, ncols):
    """ค้นเลขภาษีในทั้ง block (v5.8 refactor: ดึง per-cell ออกเป็น helper)"""
    for r in range(row_start, min(row_start + 30, row_end + 1)):
        for c in range(ncols):
            v = df.iat[r, c]
            if pd.isna(v): continue
            tid, raw, src = _taxid_from_cell(v, r, c)
            if tid: return tid, raw, src
    return None, None, None

def _scan_branch_block(df, row_start, row_end, ncols):
    """v5.8 [FIX-3]: ค้นรหัสสาขา/สนญ. ในทั้ง block (ไม่จำกัดแค่ company line)
    Returns: (branch_no, branch_label) หรือ (None, None)
    """
    for r in range(row_start, min(row_start + 30, row_end + 1)):
        for c in range(ncols):
            v = df.iat[r, c]
            if pd.isna(v): continue
            s = normalize_text(v)
            if not s: continue
            # สำนักงานใหญ่
            if 'สำนักงานใหญ่' in s or re.search(r'\bสนญ\b', s):
                return '00000', 'สำนักงานใหญ่'
            # สาขา + ตัวเลข
            m = re.search(r'สาขา\s*(?:ที่|เลข\s*ที่|#|no\.?)?\s*:?\s*(\d{1,5})', s)
            if m:
                no = m.group(1).zfill(5)
                return no, f'สาขา {m.group(1)}'
            # Branch No. / Branch ID
            m = re.search(r'(?:branch|br)[\s.#:]*(?:no\.?|id)?\s*[:#]?\s*(\d{1,5})', s, re.IGNORECASE)
            if m:
                no = m.group(1).zfill(5)
                return no, f'Branch {m.group(1)}'
    return None, None

_THAI_MARKS_RE = re.compile(r'[\u0e30-\u0e3a\u0e47-\u0e4e]')   # [OBJ-PERF] precompile (ถูกเรียก ~1M ครั้ง)
def _strip_thai_marks(s):
    """ตัดสระ/วรรณยุกต์ เพื่อ match label ที่ OCR ทำสระหาย เช่น 'รวมเงน'='รวมเงิน'"""
    return _THAI_MARKS_RE.sub('', s)

def _label_in_text(s, labels):
    """v5.8 refactor: helper ลด nesting — เช็ค label ใน s ตัวเดียว"""
    for lab in labels:
        ll = lab.lower()
        if ll in s: return True
        if len(ll) >= 4 and _strip_thai_marks(ll) and _strip_thai_marks(ll) in _strip_thai_marks(s):
            return True
    return False

def _row_label_match(M, r, ncols, labels):
    """แถว r มี cell ที่มี label ตัวใดตัวหนึ่งหรือไม่ (รองรับ OCR สระหาย) — M = sheet materialize แล้ว"""
    for c in range(ncols):
        v = M[r, c]
        if pd.isna(v): continue
        s = normalize_text(v).lower()
        if not s: continue
        if _label_in_text(s, labels):
            return True
    return False

def _rightmost_num(M, r, ncols, min_val=None):
    """หาเลขขวาสุดในแถว r (รองรับ '1,234.50' แบบ string) — คืน None ถ้าไม่มี ; M = sheet materialize แล้ว"""
    for c in range(ncols-1, -1, -1):
        v = M[r, c]
        if pd.isna(v): continue
        fv = _cell_to_num(v)
        if fv is None: continue
        if min_val is not None and fv < min_val: continue
        return fv
    return None

def audit_text_num_reset():
    """ล้าง log ตอนเริ่มรอบใหม่ (กัน state ค้างข้ามรอบใน Colab/session ยาว)"""
    try:
        state._TEXT_NUM_RECOVERIES.clear()
        state._AUDIT_CTX['file'] = '-'; state._AUDIT_CTX['sheet'] = '-'
    except Exception:
        pass

def _record_text_num(field, raw, val):
    """บันทึก 1 เคสที่เซลล์ Text ถูกกู้เป็นตัวเลข — ปลอดภัยเสมอ"""
    try:
        if not isinstance(raw, str):
            return
        if len(state._TEXT_NUM_RECOVERIES) >= _MAX_TEXT_NUM_RECOVERIES:
            return
        state._TEXT_NUM_RECOVERIES.append({
            'ไฟล์': state._AUDIT_CTX.get('file', '-'),
            'ชีต': state._AUDIT_CTX.get('sheet', '-'),
            'ช่อง': field,
            'ค่าในเซลล์ (Text)': raw.strip()[:40],
            'อ่านเป็นตัวเลข': val,
        })
    except Exception:
        pass

def audit_text_num_summary(echo=True):
    """สรุปเซลล์ Text→ตัวเลข ที่กู้คืนได้ — คืน list (เอาไปทำชีต/พิมพ์ต่อได้)"""
    recs = list(state._TEXT_NUM_RECOVERIES)
    if echo:
        try:
            if not recs:
                print('✅ Audit (Text→ตัวเลข): ไม่มีเซลล์ตัวเลขที่เก็บเป็น Text — ข้อมูลตัวเลขสะอาด')
            else:
                by_field = Counter(r['ช่อง'] for r in recs)
                by_file = Counter(r['ไฟล์'] for r in recs)
                print(f'🔎 Audit (Text→ตัวเลข): กู้คืน {len(recs)} เซลล์ '
                      f"({', '.join(f'{k}×{v}' for k, v in by_field.items())})")
                print('   ไฟล์ที่พบมากสุด: '
                      + ', '.join(f'{os.path.basename(str(f))}×{n}' for f, n in by_file.most_common(3)))
                for r in recs[:5]:
                    print(f"   • {os.path.basename(str(r['ไฟล์']))}/{r['ชีต']} "
                          f"[{r['ช่อง']}] \"{r['ค่าในเซลล์ (Text)']}\" → {r['อ่านเป็นตัวเลข']}")
                if len(recs) > 5:
                    print(f'   ... และอีก {len(recs)-5} เซลล์')
        except Exception:
            pass
    return recs

def _label_based_amounts(df, row_start, row_end, ncols):
    """fallback: หา subtotal/vat/total จาก label คำ — สแกน block ครั้งเดียว O(n)
    เก็บทุกแถวที่ match แล้วเลือกตัวเหมาะสุด (กัน TOTAL/Sub Total โผล่หลายจุด)
    """
    subs = []; vats = []; tots = []
    M = df.to_numpy(dtype=object)   # [OBJ-PERF] materialize ครั้งเดียว/บล็อก → _row_label_match/_rightmost_num อ่าน M[r,c]
    for r in range(row_start, min(row_end+1, df.shape[0])):
        if _row_label_match(M, r, ncols, _LBL_TOTAL):
            n = _rightmost_num(M, r, ncols, min_val=0)
            if n is not None: tots.append(n)
            continue
        if _row_label_match(M, r, ncols, _LBL_VAT):
            n = _rightmost_num(M, r, ncols)
            if n is not None and not (abs(n-0.07) < 0.001 or n == 7):
                vats.append(n)
            continue
        if _row_label_match(M, r, ncols, _LBL_SUBTOTAL):
            n = _rightmost_num(M, r, ncols, min_val=0)
            if n is not None: subs.append(n)
            continue
    # subtotal/total จริง = ยอดมากสุด (ยอดรวม > ยอดรายหน้า/รายบรรทัด)
    return {
        'subtotal': max(subs) if subs else None,
        'vat': vats[-1] if vats else None,
        'total': max(tots) if tots else None,
    }

def _reconcile_amounts(sub, vat, tot):
    """เติมค่าที่ขาดด้วยความสัมพันธ์ sub+vat=tot — เฉพาะเมื่อมี evidence ≥2/3 ค่า
    ไม่เสกตัวเลข: ถ้ามี ≤1 ค่า → คืนตามเดิม. คืน confidence ('high'|'low')
    """
    have = sum(x is not None for x in (sub, vat, tot))
    if have == 3:
        if abs((sub+vat) - tot) < max(1.0, abs(tot)*0.01):
            return sub, vat, tot, 'high'
        return sub, vat, tot, 'low'   # ครบแต่ไม่ balance → low (ไม่แก้ตัวเลข)
    if have == 2:
        if sub is None: sub = round(tot - vat, 2)
        elif vat is None: vat = round(tot - sub, 2)
        elif tot is None: tot = round(sub + vat, 2)
        return sub, vat, tot, 'high'
    return sub, vat, tot, 'low'       # evidence ไม่พอ → ไม่เสก

def _looks_like_address(s):
    """v5.8p: True เมื่อเซลล์มีคำที่อยู่ และไม่มีคำเลขภาษี"""
    if not s: return False
    s_str = str(s)
    s_low = s_str.lower()
    if any(kw.lower() in s_low for kw in _TAX_CONTEXT_KEYWORDS):
        return False
    return any(kw in s_str for kw in _ADDRESS_HINT_KEYWORDS)

def _pb_try_company(result, s):
    """ถ้ายังไม่มี company และ s เป็นชื่อบริษัท → set company/branch"""
    if result['company'] or not re.match(r'^(บริษัท|ห้างหุ้นส่วน|ห้าง|กิจการ|บจก|หจก|บมจ)', s):
        return
    result['company'] = remove_branch_suffix(s)
    result['branch'] = extract_branch(s)
    m_br = re.search(r'สาขา[^\d]*(\d+)', s)
    if m_br: result['branch_no'] = m_br.group(1).zfill(5)
    elif 'สำนักงานใหญ่' in s: result['branch_no'] = '00000'

def _pb_try_address_line(addr_lines, s):
    """เก็บบรรทัดที่อยู่ (ไม่ใช่ชื่อบริษัท) เข้า addr_lines"""
    if re.match(r'^(บริษัท|ห้าง|กิจการ)', s):
        return
    if re.search(r'(เลขที่ \d+|ตำบล|แขวง|หมู่ที่ \d+)', s):
        if s not in addr_lines: addr_lines.append(s)
    elif re.search(r'(เขต|อำเภอ|จังหวัด|กรุงเทพ)', s) and len(s) < 200:
        if s not in addr_lines: addr_lines.append(s)

def _pb_taxid_from_numeric(v):
    """ดึง tax_id จาก numeric cell — คืน (digits, raw) หรือ (None, None)"""
    if not (isinstance(v, (int, float)) and not isinstance(v, bool)):
        return None, None
    try:
        iv = int(v) if v == int(v) else None
    except (ValueError, OverflowError):
        return None, None
    if iv is None: return None, None
    digits = str(iv)
    if len(digits) == 13: return digits, str(v)
    if len(digits) == 12: return '0' + digits, str(v)
    return None, None

def _pb_taxid_from_string(s):
    """ดึง tax_id จาก string cell — คืน (digits, raw) หรือ (None, None)"""
    m = re.search(r'(\d[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d)', s)
    if m:
        cand = clean_tax_id(m.group(1))
        if len(cand) == 13: return cand, s
        if len(cand) == 12: return '0' + cand, s
    safe_tid = _extract_taxid_safe(s)
    if safe_tid: return safe_tid, s
    return None, None

def _pb_try_taxid(result, v, s):
    """ถ้ายังไม่มี tax_id → ลอง numeric ก่อน แล้ว string"""
    if result['tax_id']: return
    tid, raw = _pb_taxid_from_numeric(v)
    if tid:
        result['tax_id'] = tid; result['tax_id_raw'] = raw; return
    tid, raw = _pb_taxid_from_string(s)
    if tid:
        result['tax_id'] = tid; result['tax_id_raw'] = raw

def _raw_iv_form(text, cleaned_iv):
    """คืนเลขที่เอกสารตามที่ปรากฏในเอกสารจริง (มีขีด/เว้นวรรค/จุด/ทับ ฯลฯ)
    หาไม่เจอ → คืนเลขแบบลบขีด (ของเดิม) เพื่อไม่ให้พัง

    v5.9 [FIX-IV-RAW] regex เดิมตัดที่ตัวอักษรแปลก เช่น '.' ทำให้
      'IV6905-2000.6' กลายเป็น 'IV6905-2000' (หาย '.6') — โชว์ไม่ตรงบิล
      แก้: ขยาย regex ให้รับ . / , ภายใน token ด้วย แล้ว match แบบ
      "ตัวเลข/อักษรของ token ขึ้นต้นด้วย cleaned_iv" (เพราะ cleaned อาจสั้นกว่า)
      → คืนค่าตามที่พิมพ์ในเอกสารจริงครบทุกตัว
    """
    if not text or not cleaned_iv:
        return cleaned_iv
    target = re.sub(r'[^0-9A-Za-z]', '', str(cleaned_iv)).upper()
    if not target:
        return cleaned_iv
    s = str(text)
    # token แบบกว้าง: ยอมให้มี - space . / , คั่นภายในได้ (เก็บอักขระแปลกไว้)
    for m in re.finditer(r'([A-Z]{0,5}[-\s.,/]?\d{1,}(?:[-\s.,/]?\d+)*)',
                         s, re.IGNORECASE):
        tok = m.group(1)
        alnum = re.sub(r'[^0-9A-Za-z]', '', tok).upper()
        # ตรงเป๊ะ หรือ token เริ่มต้นด้วย cleaned (กรณี cleaned ถูกตัดสั้นเพราะอักขระแปลก)
        if alnum == target or alnum.startswith(target):
            return re.sub(r'\s+', ' ', tok.strip()).upper()
    return cleaned_iv

def _pb_try_iv(result, v, s):
    """ดึง IV แบบ best-match-wins ทั่วทั้ง header (v8.3 [FIX-IV-BESTMATCH])

    บั๊กเดิม (first-match-wins): หยุดที่ cell แรกที่เจอเลขคล้าย IV
      → ถ้าเลขภาษีผู้ซื้อ/เลข 12-13 หลัก วางอยู่ "คอลัมน์ซ้าย" ของ IV จริง
        จะถูกล็อกผิดทันที แล้ว guard `if result['iv_number']: return`
        กันไม่ให้ประเมิน IV จริงที่อยู่คอลัมน์ขวาเลย
      ตัวอย่างไฟล์ CHM: row 6 มีเลข 255560001625 (คอลัมน์ 13-16, คะแนน ~9-11)
        มาก่อน IV จริง 'IV6905-020013' (คอลัมน์ 21, คะแนน 80) → อ่านผิดทุกชีต

    แก้: เก็บ candidate ที่ "คะแนนสูงสุด" ข้ามทุก cell ของ header
      เก็บคะแนนปัจจุบันไว้ที่ result['_iv_score'] (คีย์ชั่วคราว ถูก pop ทิ้งใน _parse_block)
      IV จริง (มี prefix IV/INV หรือรหัส ปปดด ถูกต้อง) จะชนะเลขภาษีที่ติดโทษ -30 เสมอ
      ไฟล์ที่อ่านถูกอยู่แล้ว: candidate คะแนนสูงสุด = ตัวที่ first-match เคยเลือก → ผลไม่เปลี่ยน
    """
    # ข้าม cell วันที่ กัน "2569-05-02 00:00:00" ถูกจับเป็น IV
    if isinstance(v, (datetime, pd.Timestamp)) or re.match(r'^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}', s):
        return
    _cur = result.get('_iv_score', -10**9)
    picked, score = _pick_best_iv(s, known_tax_id=result.get('tax_id'), return_score=True)
    if picked is not None:
        if score > _cur:
            result['iv_number'] = picked
            result['iv_number_raw'] = _raw_iv_form(s, picked)
            result['_iv_score'] = score
        return
    # fallback อ่อน (อักษรนำ 1-4 ตัว + เลข 6-12) — คะแนนต่ำสุด (1)
    #   ใช้เฉพาะเมื่อยังไม่มี candidate ที่คะแนนดีกว่า; ให้ scored จริงภายหลังชนะได้เสมอ
    if _cur < 1:
        m = re.search(r'\b([A-Z]{1,4}[-\s]?\d{6,12})\b', s, re.IGNORECASE)
        if m:
            result['iv_number'] = m.group(1).upper().replace(' ', '').replace('-', '')
            result['iv_number_raw'] = m.group(1).strip().upper()
            result['_iv_score'] = 1

def _pb_scan_header(df, result, addr_lines, row_start, header_end, ncols):
    """สแกน header rows — เก็บ company/address/tax_id/iv/date (depth ตื้น)"""
    M = df.to_numpy(dtype=object)   # [OBJ-PERF] materialize ครั้งเดียว/บล็อก (M[r,c]==.iat เชิงพฤติกรรม, พิสูจน์แล้ว)
    for r in range(row_start, header_end):
        for c in range(ncols):
            v = M[r, c]
            if pd.isna(v): continue
            s = normalize_text(v)
            if not s: continue
            _had_company = bool(result['company'])
            _pb_try_company(result, s)
            # v5.9 [FIX-CMP004]: เพิ่งเซ็ต company → เก็บค่าดิบ (คงช่องว่างเดิม) ไว้เทียบเว้นวรรค
            if not _had_company and result['company']:
                result['company_raw'] = _raw_company_form(v)
            _pb_try_address_line(addr_lines, s)
            _pb_try_taxid(result, v, s)
            _pb_try_iv(result, v, s)
            if not result['iv_date']:
                d = parse_date_any(v)
                if d:
                    result['iv_date'] = d
                    result['iv_date_str'] = d.strftime('%d/%m/%Y')

def _pb_build_item(block_df, r, seq, name_col, qty_col, unit_col, price_col, amt_col):
    """สร้าง 1 item dict จากแถว r — คืน None ถ้าไม่มีชื่อ
    v6 STABILITY: ดึงตัวเลขผ่าน _cell_to_num (รองรับเลขที่เก็บเป็น Text/มี comma ใน Excel)
                  + ดักเซลล์ว่าง (NaN) → None แทนที่จะกลายเป็น float('nan') ปนยอดรวม
                  + บันทึก audit เมื่อกู้ตัวเลขจากเซลล์ Text (ความโปร่งใส)
    """
    name = normalize_text(block_df.iat[r, name_col])
    if not name: return None
    raw = str(block_df.iat[r, name_col]).strip() if pd.notna(block_df.iat[r, name_col]) else ''
    def _get_num(c_idx, field):
        if c_idx is None: return None
        v = block_df.iat[r, c_idx]
        if pd.isna(v): return None
        num = _cell_to_num(v)
        if num is not None and isinstance(v, str):   # เซลล์ Text ถูกกู้เป็นตัวเลข → บันทึก audit
            _record_text_num(field, v, num)
        return num
    qty = _get_num(qty_col, 'qty')
    unit = normalize_text(block_df.iat[r, unit_col]) if unit_col is not None else ''
    price = _get_num(price_col, 'price')
    amt = _get_num(amt_col, 'amount')
    return {
        'seq':seq,'name':name,'name_raw':raw,
        'qty':qty,
        'unit':unit,
        'price':price,
        'amount':amt,
    }


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__=[n for n in list(globals().keys()) if not n.startswith('__') and n!='annotations']
