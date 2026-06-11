# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""parser_p2 — OBJ-MAINT layer 2 (extract คัดลอกเป๊ะ, byte-identical).
cascade toolkit จาก parser_p1 (และชั้นล่างทั้งหมด)."""
from __future__ import annotations
# [OPT-2 ก] auto re-export parser_p1.__all__ ยกเว้นที่ p2 จัดการเอง (คง minimal-interface curation):
#   • Decimal/ROUND_HALF_UP → p2 import ตรงจาก decimal (บรรทัดล่าง) = object เดียวกันทั้ง chain
#   • _RATE_MARKERS/_rightmost_num_has_decimal/_row_has_rate_marker → helper ภายใน p1 (M8 VAT-rate)
#     ที่ p2 ไม่เคย re-export ขึ้นไป (เดิมก็ไม่อยู่ในลิสต์ explicit). reexport bind object เดิม → golden ไม่ขยับ.
import parser_reexport as _rx
import parser_p1 as _up
_rx.reexport(_up, globals(), exclude=('Decimal', 'ROUND_HALF_UP', '_RATE_MARKERS',
                                      '_rightmost_num_has_decimal', '_row_has_rate_marker'))
del _rx, _up
from decimal import Decimal, ROUND_HALF_UP  # [F2/ADR-020] money-math: VAT ด้วย Decimal+HALF_UP
from parser_guards import (   # [F4 ceiling 11.06.69] ชั้นปราการ input + iv last-resort (ซอยตามเพดาน 600)
    apply_iv_lastresort_if_needed, get_files_via_drive, get_files_via_upload, _pb_iv_lastresort)

def _pb_extract_items(result, block_df, cols):
    """ดึงรายการสินค้าจาก block_df → append เข้า result['items']"""
    seq_col, name_col, qty_col, unit_col, price_col, amt_col = cols
    if seq_col is None or name_col is None:
        return

    last_seq = 0
    for r in range(len(block_df)):
        seq = block_df.iat[r, seq_col]
        name = normalize_text(block_df.iat[r, name_col])

        # 1. ดักจับเคส "ลำดับหาย" แต่มีข้อมูลสินค้า
        if pd.isna(seq) or str(seq).strip() == '':
            # [FIX-BAHTTEXT] กัน "ยอดเงินเป็นตัวอักษรไทย" (เช่น 'สองแสนแปดหมื่นสี่พันแปดร้อยสาม')
            #   ถูกนับเป็นรายการสินค้า + ฟ้อง ITM016 ผิด — ข้อความนี้คือยอดรวมเป็นคำ ไม่ใช่สินค้า
            if name and _is_thai_amount_words(name):
                continue
            if name and len(name) >= 3 and amt_col is not None:
                amt = _cell_to_num(block_df.iat[r, amt_col])   # v6: ผ่าน converter กลาง → รับยอด Text
                if amt is not None and amt > 0:
                    last_seq += 1
                    item = _pb_build_item(block_df, r, last_seq, name_col, qty_col, unit_col, price_col, amt_col)
                    if item:
                        result['items'].append(item)
                        result['issues'].append({
                            'code': 'ITM016', 'severity': 'ERROR', 'category': 'รายการสินค้า',
                            'name': 'เลขลำดับหาย (Blank)',
                            'detail': f'พบรายการ "{name[:30]}" แต่คนคีย์ข้อมูลไม่ระบุเลขลำดับ'
                        })
            continue

        # 2. เคสปกติ มีเลขลำดับ
        s = str(seq).strip().removesuffix('.0')   # [L4] ตัด .0 ท้ายเท่านั้น (เดิม replace ทั้งสตริง)
        if not (s.isdigit() and 1 <= int(s) <= 50): continue

        last_seq = int(s)
        item = _pb_build_item(block_df, r, last_seq, name_col, qty_col, unit_col, price_col, amt_col)
        if item:
            result['items'].append(item)

def _row_has_vat_marker(M, r, ncols):
    """แถว r มี cell ที่เป็น VAT rate marker หรือไม่ (M = sheet ที่ materialize แล้ว: M[r,c]==df.iat เชิงพฤติกรรม)"""
    for c in range(ncols):
        v = M[r, c]
        if pd.isna(v): continue
        if isinstance(v,(int,float)) and not isinstance(v,bool):
            try:
                if abs(float(v) - 0.07) < 0.001: return True
            except (ValueError, TypeError): pass
        if str(v).strip() in ['0.07','7%','.07']:
            return True
    return False

def _pb_find_vat_row(df, row_start, row_end, ncols):
    """หาแถวที่เป็น VAT rate (0.07/7%) — คืน row index หรือ None"""
    M = df.to_numpy(dtype=object)   # [OBJ-PERF] materialize ครั้งเดียว → _row_has_vat_marker อ่าน M[r,c] (เลี่ยง .iat ต่อแถว)
    for r in range(row_start, row_end+1):
        if _row_has_vat_marker(M, r, ncols):
            return r
    return None

def _pb_amounts_from_vatrow(df, result, vat_row, amt_col, row_start, row_end):
    """อ่าน subtotal/vat/total รอบ ๆ vat_row (logic 0.07 เดิม)
    v6: ผ่าน converter กลาง _cell_to_num → รับยอดที่เก็บเป็น Text/มี comma (NaN ถูกกันที่ตัวกลางแล้ว)"""
    for r in range(vat_row-1, max(vat_row-5, row_start-1), -1):
        v = _cell_to_num(df.iat[r, amt_col])
        if v is not None and v > 100:
            result['subtotal'] = v; break
    v = _cell_to_num(df.iat[vat_row, amt_col])
    if v is not None: result['vat'] = v
    for r in range(vat_row+1, min(vat_row+5, row_end+1)):
        v = _cell_to_num(df.iat[r, amt_col])
        if v is not None and v > 100:
            result['total'] = v; break

def _pb_finalize_amounts(result):
    """เติม/reconcile subtotal/vat/total ขั้นสุดท้าย (PATCH 5/6 + legacy)
    v9 [INTEGRITY]: ติด provenance ('ocr'|'derived'|'item_sum') ให้ทุกยอด.
      พฤติกรรมการ "เติมยอด" เดิมคงไว้ 100% (รายงานยังมีตัวเลขครบเหมือนเดิม)
      แต่บันทึกว่ายอดไหน "อ่านจากเอกสารจริง" (ocr) vs "ระบบคำนวณเอง" (derived/item_sum)
      เพื่อให้ VAT010 กันการตรวจ VAT ค่าที่ระบบคำนวณเอง = false-clean
    """
    # provenance เริ่มต้น: ค่าที่มีตั้งแต่ parse header = อ่านจากเอกสารจริง
    src = {'subtotal': 'ocr' if result['subtotal'] is not None else None,
           'vat':      'ocr' if result['vat']      is not None else None,
           'total':    'ocr' if result['total']    is not None else None}
    # PATCH 5: vat ที่เป็น rate (≤1.0) → ทิ้งก่อน reconcile (เป็นอัตรา 0.07 ไม่ใช่ยอด VAT)
    if result['vat'] is not None:
        try:
            if abs(float(result['vat'])) <= 1.0:
                result['vat'] = None
                src['vat'] = None   # ค่านี้ไม่ใช่ "ยอด VAT" จริง → ถือว่าไม่มี OCR
        except (ValueError, TypeError):
            pass
    _s, _v, _t, _conf = _reconcile_amounts(result['subtotal'], result['vat'], result['total'])
    # ค่าที่ reconcile เติมให้ (จากอัตลักษณ์ sub+vat=tot) = derived ไม่ใช่ค่าอ่านจริง
    if result['subtotal'] is None and _s is not None: src['subtotal'] = 'derived'
    if result['vat']      is None and _v is not None: src['vat']      = 'derived'
    if result['total']    is None and _t is not None: src['total']    = 'derived'
    result['subtotal'], result['vat'], result['total'] = _s, _v, _t
    result['amount_confidence'] = _conf
    # PATCH 5: vat = subtotal × 7% ถ้ายังไม่มี → ค่าที่ได้คือ derived
    if result['vat'] is None and result['subtotal'] is not None:
        result['vat'] = float((_D(result['subtotal']) * Decimal('0.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)); src['vat'] = 'derived'  # [F2/ADR-020]
        if result['total'] is None:
            result['total'] = round(float(result['subtotal']) + result['vat'], 2); src['total'] = 'derived'
    # legacy: subtotal จากผลรวมรายการ → item_sum (ไม่ใช่ยอดก่อน VAT ที่พิมพ์บนเอกสาร)
    if result['subtotal'] is None and result['items']:
        s = sum(i['amount'] or 0 for i in result['items'])
        if s > 0: result['subtotal'] = s; src['subtotal'] = 'item_sum'
    # PATCH 6: เติม vat/total ครั้งสุดท้ายหลัง subtotal ครบ → derived
    if result['subtotal'] is not None:
        try:
            _sub = float(result['subtotal'])
            if result['vat'] is None or abs(float(result['vat'] or 0)) <= 1.0:
                result['vat'] = float((_D(_sub) * Decimal('0.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)); src['vat'] = 'derived'  # [F2/ADR-020]
            if result['total'] is None:
                result['total'] = round(_sub + float(result['vat']), 2); src['total'] = 'derived'
        except (ValueError, TypeError):
            pass
    result['amount_source'] = src   # v9: provenance ใช้ใน VAT010 + รายงาน

def _iv_embedded_period_ce(iv_text):
    """(ปี ค.ศ., เดือน) ที่ฝังในเลขที่เอกสาร เช่น 'IV-69-050058' → (2026, 5). None ถ้าอ่านงวดไม่ชัด."""
    if not iv_text:
        return None
    m = re.match(r'^[A-Z]*(\d+)', re.sub(r'[^0-9A-Za-z]', '', str(iv_text)).upper())
    if not m:
        return None
    lead = m.group(1)
    for L4, ynow in ((6, _ivp_year4_to_ce), (4, _ivp_year2_to_ce)):
        if len(lead) >= L4:
            cy, _ = ynow(int(lead[:L4 - 2])); mo = int(lead[L4 - 2:L4])
            if cy is not None and 1 <= mo <= 12:
                return (cy, mo)
    return None


def _filename_period_ce(filename):
    """(ปี ค.ศ., เดือน) ที่ชื่อไฟล์ประกาศ (เดือนเดียว) เช่น 'SSN 69.05(3).xls' → (2026, 5).
    ทนชื่อไฟล์มี prefix ขยะ (เช่น hash) ; None ถ้าไม่ระบุเดือน/เป็นช่วงหลายเดือน (กันเดาผิด)."""
    base = os.path.splitext(os.path.basename(filename or ''))[0]
    if re.search(r'(?<!\d)\d{2,4}[.\-_\s]\d{1,2}\s*[-–]\s*\d{1,2}(?!\d)', base):
        return None                       # ช่วงหลายเดือน (YY.MM-MM) → ข้าม (คร่อมเดือน legit)
    for mm in re.finditer(r'(?<!\d)(\d{2,4})[.\-_](\d{1,2})', base):
        y, mo = int(mm.group(1)), int(mm.group(2))
        if not 1 <= mo <= 12:
            continue
        for lo, hi, adj in ((2558, 2582, -543), (2015, 2039, 0), (58, 82, 1957), (15, 39, 2000)):
            if lo <= y <= hi:
                return (y + adj, mo)
    return None


def _pb_prefer_period(df, result, row_start, header_end, ncols, fperiod, sheet_name=None):
    """[FIX-MULTIBLOCK] ชีตมีบล็อก IV/วันที่ของบิลเก่าค้างเทมเพลตคู่บิลจริง → เลือกตัวที่ตรง 'งวดที่ควรเป็น'
    (งวดในชื่อไฟล์ ; ถ้าไม่ระบุ → เดาจาก 'วันของชีต'). ทำงานเมื่อมี IV >=2 งวด → ชีตปกติ no-op (golden นิ่ง)."""
    M = df.to_numpy(dtype=object)
    iv_cells = []
    for r in range(row_start, header_end):
        for c in range(ncols):
            v = M[r, c]
            if pd.isna(v) or isinstance(v, (datetime, pd.Timestamp)):
                continue
            s = normalize_text(v)
            if s and re.search(r'[A-Za-z]', s) and re.search(r'\d{4,}', s) \
                    and _iv_embedded_period_ce(s) is not None:
                iv_cells.append(s)
    if len({_iv_embedded_period_ce(s) for s in iv_cells}) < 2:
        return                            # ไม่ใช่ชีตหลายบล็อก → ไม่ยุ่ง
    # ถ้าไม่มีงวดจากชื่อไฟล์ → เดาจาก 'วันของชีต' (ชื่อชีตเป็นตัวเลข = วันที่)
    if not fperiod and sheet_name is not None:
        sd = str(sheet_name).strip().lstrip('0').split('#')[0]
        if sd.isdigit():
            day = int(sd)
            for r in range(row_start, header_end):
                hit = next((d for c in range(ncols)
                            for d in [parse_date_any(M[r, c])]
                            if not pd.isna(M[r, c]) and d and d.day == day), None)
                if hit:
                    fperiod = (hit.year, hit.month); break
    if not fperiod:
        return
    fy, fm = fperiod
    cur = result.get('iv_date')
    if not (cur and cur.year == fy and cur.month == fm):
        for r in range(row_start, header_end):
            for c in range(ncols):
                d = parse_date_any(M[r, c]) if not pd.isna(M[r, c]) else None
                if d and d.year == fy and d.month == fm:
                    result['iv_date'] = d
                    result['iv_date_str'] = d.strftime('%d/%m/%Y')
                    break
            else:
                continue
            break
    if _iv_embedded_period_ce(result.get('iv_number')) != (fy, fm):
        for s in iv_cells:
            if _iv_embedded_period_ce(s) == (fy, fm):
                picked = _pick_best_iv(s, known_tax_id=result.get('tax_id'))
                if picked:
                    result['iv_number'] = picked
                    result['iv_number_raw'] = _raw_iv_form(s, picked)
                    break



def _parse_block(df, sheet_name, filename, row_start, row_end, block_idx=0):
    """parse 1 invoice block (rows row_start..row_end inclusive)
    v5.8 refactor: แตก loop ชั้นในเป็น helper (_pb_*) เพื่อลด nesting ≤6
    """
    result = {
        'file':os.path.basename(filename),'filepath':filename,
        'sheet':sheet_name if block_idx == 0 else f'{sheet_name}#{block_idx+1}',
        'block_idx':block_idx,
        'company':'','branch':'','branch_no':'','company_raw':'',
        'tax_id':'','tax_id_raw':'','address':'',
        'iv_number':'','iv_number_raw':'','iv_date':None,'iv_date_str':'',
        'items':[],'subtotal':None,'vat':None,'total':None,'issues':[],
    }
    nrows, ncols = df.shape
    if row_end is None: row_end = nrows - 1
    addr_lines = []
    header_end = min(row_start + 20, row_end + 1)

    # 1) สแกน header (company / address / tax_id / iv / date)
    _pb_scan_header(df, result, addr_lines, row_start, header_end, ncols)

    # 1b) [FIX-MULTIBLOCK] ชีตที่มีบิลเก่าค้างในเทมเพลตคู่กับบิลจริง → เลือกตัวที่งวดตรงชื่อไฟล์
    #     (no-op สำหรับชีตปกติ IV เดียว/งวดตรงอยู่แล้ว — golden ไม่ขยับ)
    _pb_prefer_period(df, result, row_start, header_end, ncols, _filename_period_ce(filename), sheet_name)

    # 1c) [F2-FIX v9.3] fallback "เลขเอกสารโดด ๆ 4-5 หลัก" (เช่น TNT '01954') — gate+logic ใน parser_guards
    #     (iv ว่าง/ขยะที่ D2-GUARD จะล้างแน่ → ลอง last-resort; corpus dormant 100% — ดู FIX_11_06_69_TH.md)
    apply_iv_lastresort_if_needed(df, result, row_start, header_end, ncols)

    # 2) fallback scan tax_id
    if not result['tax_id']:
        tid, raw, src = _scan_tax_id_block(df, row_start, row_end, ncols)
        if tid:
            result['tax_id'] = tid
            result['tax_id_raw'] = raw if raw else tid
            if src:
                result['issues'].append({'code':'TAX001','severity':'INFO','category':'เลขภาษี',
                                        'name':'fallback scan','detail':f'เจอเลขภาษีจาก {src}'})

    # 3) fallback scan branch
    if not result['branch_no']:
        bn, bl = _scan_branch_block(df, row_start, row_end, ncols)
        if bn:
            result['branch_no'] = bn
            if not result['branch']: result['branch'] = bl

    # 4) auto-fix tax_id 12 → 13
    if result['tax_id'] and len(result['tax_id']) == 12:
        result['tax_id'] = '0' + result['tax_id']
        result['issues'].append({'code':'TAX001','severity':'INFO','category':'เลขภาษี',
                                'name':'auto-fix 12→13','detail':'เลขภาษี 12 หลัก เพิ่ม 0 นำหน้าให้แล้ว'})

    result['address'] = ' '.join(addr_lines)

    # 5) ดึงรายการสินค้า (detect คอลัมน์ครั้งเดียว ใช้ต่อใน step 6)
    block_df = df.iloc[row_start:row_end+1].reset_index(drop=True)
    cols = detect_item_columns(block_df)
    _pb_extract_items(result, block_df, cols)

    # 6) ยอดเงินจาก vat_row (logic 0.07 เดิม)
    amt_col = cols[5]
    vat_row = _pb_find_vat_row(df, row_start, row_end, ncols)
    if vat_row is not None and amt_col is not None:
        _pb_amounts_from_vatrow(df, result, vat_row, amt_col, row_start, row_end)

    # 7) label-based fallback ถ้ายังขาด
    if result['vat'] is None or result['total'] is None or result['subtotal'] is None:
        _lab = _label_based_amounts(df, row_start, row_end, ncols)
        if result['subtotal'] is None: result['subtotal'] = _lab['subtotal']
        if result['vat'] is None:      result['vat']      = _lab['vat']
        if result['total'] is None:    result['total']    = _lab['total']

    # 8) reconcile + เติมค่าขั้นสุดท้าย
    _pb_finalize_amounts(result)

    # v8.3 [FIX-IV-BESTMATCH]: ลบคีย์ชั่วคราวที่ใช้เปรียบเทียบคะแนน IV — คง schema เดิม 100%
    result.pop('_iv_score', None)

    return result

def _is_tor_format(df):
    """ตรวจ signature ของ TOR-format (ต้องครบทั้ง 3):
      1. มี cell ในคอลัมน์ ≥6 ที่ตรง 'IV' + เลข 10-12 หลัก
      2. มีคำ 'เลขประจำตัวผู้เสียภาษี' อยู่ในชีต
      3. ไม่มีคำ 'ใบกำกับภาษี' / 'TAX INVOICE' (กันชนกับไฟล์ปกติ)
    """
    if df.shape[1] < 8:
        return False
    M = df.to_numpy(dtype=object)   # [OBJ-PERF] materialize ครั้งเดียว (M[r,c]==.iat เชิงพฤติกรรม, พิสูจน์ 836 ชีต/555k cell)
    has_iv = False; has_taxid = False; has_invlabel = False
    nrows = min(df.shape[0], 30)
    for r in range(nrows):
        for c in range(df.shape[1]):
            v = M[r, c]
            if pd.isna(v): continue
            s = str(v)
            if c >= 6 and re.fullmatch(r'IV\d{10,12}', s.strip()):
                has_iv = True
            if 'เลขประจำตัวผู้เสียภาษี' in s:
                has_taxid = True
            sl = s.lower()
            if 'ใบกำกับภาษี' in s or 'tax invoice' in sl:
                has_invlabel = True
    return has_iv and has_taxid and not has_invlabel

def _tor_try_date(result, v, s):
    """parse วันที่จาก cell — set result ถ้าได้ คืน True/False"""
    d = None
    if isinstance(v, datetime):
        d = v
    elif re.match(r'^(25[6-9]\d|20[2-3]\d)[-/]\d{1,2}[-/]\d{1,2}', s):
        try: d = pd.to_datetime(s).to_pydatetime()
        except Exception: d = None
    if not d: return False
    if d.year >= 2500: d = d.replace(year=d.year - 543)
    result['iv_date'] = d
    result['iv_date_str'] = d.strftime('%d/%m/%Y')
    return True

def _tor_scan_iv_date(df, result, nrows, ncols):
    """step 1: หา IV + วันที่ จาก 15 แถวแรก"""
    iv_row = None; date_row = None
    for r in range(min(15, nrows)):
        for c in range(ncols):
            v = df.iat[r, c]
            if pd.isna(v): continue
            s = str(v).strip()
            if iv_row is None and re.fullmatch(r'IV\d{10,12}', s):
                result['iv_number'] = s; result['iv_number_raw'] = s; iv_row = r
            if date_row is None and _tor_try_date(result, v, s):
                date_row = r

def _tor_cell_company(result, s, addr_parts):
    """ประมวลผล cell เดียว: company / tax_id / addr line"""
    if not result['company'] and re.match(r'^(บริษัท|ห้างหุ้นส่วน|ห้าง|บจก\.?|หจก\.?|บมจ\.?)', s):
        result['company'] = re.sub(r'\s*\(สำนักงานใหญ่\)\s*$', '', s).strip()
        if 'สำนักงานใหญ่' in s:
            result['branch_no'] = '00000'
        else:
            m_br = re.search(r'สาขา(?:ที่)?\s*(\d{1,5})', s)
            if m_br: result['branch_no'] = m_br.group(1).zfill(5)
        return
    if not result['tax_id']:
        m = re.search(r'เลขประจำตัวผู้เสียภาษี[\s:]*(\d[\d\s\-]{11,18})', s)
        if m:
            digits = re.sub(r'\D', '', m.group(1))
            if len(digits) == 13:
                result['tax_id'] = digits; result['tax_id_raw'] = s; return
    if result['company'] and not result['tax_id']:
        if not re.match(r'^(บริษัท|ห้าง|บจก|หจก|บมจ|เลขประจำ)', s):
            addr_parts.append(s)

def _tor_scan_company(df, result, nrows, ncols):
    """step 2: company / tax_id / address จากคอลัมน์ซ้าย rows 0-14"""
    addr_parts = []
    for r in range(min(15, nrows)):
        for c in range(min(3, ncols)):
            v = df.iat[r, c]
            if pd.isna(v): continue
            s = str(v).strip()
            if not s: continue
            _tor_cell_company(result, s, addr_parts)
    if addr_parts:
        result['address'] = ' '.join(addr_parts).strip()

def _tor_numval(df, r, col, ncols):
    """อ่านตัวเลขจาก cell (r,col) — คืน float หรือ None
    v6: ใช้ converter กลาง _cell_to_num (เลิก logic ซ้ำ + รับเลข Text/comma เหมือนทั้งระบบ)"""
    if col >= ncols: return None
    v = df.iat[r, col]
    if pd.isna(v): return None
    return _cell_to_num(v)

def _tor_scan_items(df, result, nrows, ncols):
    """step 3: ดึงรายการสินค้า (col2=ชื่อ, col7=ราคา, col10=qty, col11=amt) → คืน last_item_row"""
    item_seq = 0; last_item_row = -1
    for r in range(nrows):
        v_name = df.iat[r, 2] if ncols > 2 else None
        if pd.isna(v_name): continue
        name = str(v_name).strip()
        if not name or len(name) < 3: continue
        amt = _tor_numval(df, r, 11, ncols)
        price = _tor_numval(df, r, 7, ncols)
        qty = _tor_numval(df, r, 10, ncols)
        if amt is None and price is None: continue
        item_seq += 1
        result['items'].append({
            # v6.1 FIX: เพิ่ม 'name_raw' ให้ schema เท่ากับ parser หลัก
            #   (เดิมไฟล์ฟอร์แมต TOR ไม่มีคีย์นี้ → ITM004 อ่าน it['name_raw'] แล้ว KeyError
            #    กฎจึงถูกข้ามเงียบ ๆ ทุกบิล TOR — สูญเสียการตรวจคำสะกด/อักขระแปลก)
            'seq': item_seq, 'name': name, 'name_raw': name, 'qty': qty, 'unit': '',
            'price': price, 'amount': amt,
        })
        last_item_row = r
    return last_item_row

def _tor_scan_subtotal(df, result, nrows, ncols, last_item_row):
    """step 4: subtotal = row ที่มี Thai amount-in-words ใน col 0"""
    for r in range(max(0, last_item_row), nrows):
        v0 = df.iat[r, 0] if ncols > 0 else None
        if pd.isna(v0): continue
        if not re.search(r'\([^)]*(แสน|หมื่น|พัน|ร้อย|สิบ)[^)]*\)', str(v0)): continue
        v11 = df.iat[r, 11] if ncols > 11 else None
        if not pd.isna(v11):
            try: result['subtotal'] = float(str(v11).replace(',', ''))
            except (ValueError, TypeError): pass
        break

def _tor_scan_vat(df, result, nrows, ncols, last_item_row):
    """step 5: VAT = row ที่ col 10 เป็น rate 0.05-0.10"""
    for r in range(max(0, last_item_row), nrows):
        v10 = df.iat[r, 10] if ncols > 10 else None
        if pd.isna(v10): continue
        try: rate = float(v10)
        except (ValueError, TypeError): continue
        if not (0.05 <= rate <= 0.10): continue
        v11 = df.iat[r, 11] if ncols > 11 else None
        if not pd.isna(v11):
            try: result['vat'] = float(str(v11).replace(',', ''))
            except (ValueError, TypeError): pass
        break

def _tor_scan_total(df, result, nrows, ncols, last_item_row):
    """step 6: Total = เลขตัวสุดท้ายใน col 11 หลัง VAT"""
    if ncols <= 11: return
    for r in range(nrows - 1, max(0, last_item_row), -1):
        v = df.iat[r, 11]
        if pd.isna(v): continue
        try:
            fv = float(str(v).replace(',', ''))
        except (ValueError, TypeError):
            continue
        # [L5] is not None (เดิม truthiness): vat/subtotal == 0.0 ไม่ควรปิด guard dedup
        if result['vat'] is not None and abs(fv - result['vat']) < 1: continue
        if result['subtotal'] is not None and abs(fv - result['subtotal']) < 1: continue
        result['total'] = fv
        break

def _parse_tor_sheet(df, sheet_name, filename):
    """แกะใบกำกับ TOR-format ออกเป็น bill dict มาตรฐาน
    v5.8 refactor: แตก 6 ขั้นตอนเป็น helper (_tor_*) ลด nesting ≤6
    คืน dict หรือ None ถ้าหา iv_number ไม่เจอ
    """
    result = {
        'file': os.path.basename(filename), 'filepath': filename,
        'sheet': sheet_name, 'block_idx': 0,
        'company': '', 'branch': '', 'branch_no': '', 'company_raw': '',
        'tax_id': '', 'tax_id_raw': '', 'address': '',
        'iv_number': '', 'iv_number_raw': '',
        'iv_date': None, 'iv_date_str': '',
        'items': [], 'subtotal': None, 'vat': None, 'total': None,
        'issues': [],
    }
    nrows, ncols = df.shape

    _tor_scan_iv_date(df, result, nrows, ncols)
    if not result['iv_number']:
        return None
    _tor_scan_company(df, result, nrows, ncols)
    last_item_row = _tor_scan_items(df, result, nrows, ncols)
    _tor_scan_subtotal(df, result, nrows, ncols, last_item_row)
    _tor_scan_vat(df, result, nrows, ncols, last_item_row)
    _tor_scan_total(df, result, nrows, ncols, last_item_row)
    return result

def parse_sheet(df, sheet_name, filename):
    nrows = df.shape[0]

    # v5.8r: ทางแยกสำหรับไฟล์ TOR-format (ไม่มี label header)
    if _is_tor_format(df):
        b = _parse_tor_sheet(df, sheet_name, filename)
        if b and (b.get('items') or any(b.get(k) for k in ('subtotal','vat','total'))):
            return [b]
        return []

    vat_rows = _detect_vat_rows(df)
    bills = []

    # [FIX-GHOST] บิลจริงต้องมี "เนื้อหา" (รายการ หรือ ยอดเงิน) — มีแต่ iv ลอย ๆ + 0 รายการ + ไม่มียอด = บิลเงา ตัดทิ้ง
    def _is_real_bill(b):
        has_items = bool(b.get('items'))
        has_money = any(b.get(k) for k in ('subtotal', 'vat', 'total'))
        return has_items or has_money

    if len(vat_rows) <= 1:
        b = _parse_block(df, sheet_name, filename, 0, nrows-1, 0)
        if _is_real_bill(b):
            bills.append(b)
    else:
        prev = 0
        for idx, vr in enumerate(vat_rows):
            block_end = min(vr + 5, nrows - 1)
            if idx + 1 < len(vat_rows):
                block_end = min(block_end, vat_rows[idx+1] - 1)
            b = _parse_block(df, sheet_name, filename, prev, block_end, idx)
            if _is_real_bill(b):
                bills.append(b)
            prev = block_end + 1
        if prev < nrows:
            b = _parse_block(df, sheet_name, filename, prev, nrows-1, len(vat_rows))
            if _is_real_bill(b):
                bills.append(b)
    return bills

# [BUG-3 FIX 11.06.69] SYS003 sheet-pattern: เดิม .isdigit() ไม่จับ '18 (2)' / '5.1' /
#   '18#2' → ถ้าชีตหน้าต่อ parse ไม่ออก บิลหายเงียบไม่มี warning (dormant บน corpus
#   ปัจจุบันเพราะ merge สำเร็จ — แต่เป็นรู silent-failure เชิงโครงสร้าง)
_BILL_SHEETLIKE_RE = re.compile(r'^\d+(?:\.\d+)?(?:\s*\(\d+\))?(?:#\d+)?$')

def _sheet_name_looks_like_bill(name) -> bool:
    """ชื่อชีตที่ระบบถือเป็น bill-sheet: '5', '18', '5.1', '18 (2)', '5.1 (2)', '18#2'
    (รองรับ leading zeros เช่น '05')."""
    s = str(name).strip()
    if not s:
        return False
    s = s.lstrip('0') or '0'
    return bool(_BILL_SHEETLIKE_RE.match(s))

def parse_file(filepath):
    bills = []
    xl = None   # v6.1 RESOURCE: ประกาศไว้ก่อน เพื่อปิดใน finally ได้เสมอ
    _fname = os.path.basename(filepath)
    try:
        xl = read_workbook(filepath)
        for sheet in xl.sheet_names:
            try:
                df = xl.parse(sheet, header=None)
                if df.empty or df.shape[0] < 5: continue
                try: state._AUDIT_CTX['file'] = _fname; state._AUDIT_CTX['sheet'] = str(sheet)   # v6: context ให้ Text→ตัวเลข audit
                except Exception: pass
                sheet_bills = parse_sheet(df, sheet, filepath)
                for _b in sheet_bills: validate_iv_post(_b)   # [D2-GUARD] post-extraction: ปฏิเสธ iv ขยะ/เศษยอด → ว่าง (ให้ IV005/IV007 จับ)
                if not sheet_bills and _sheet_name_looks_like_bill(sheet):  # [SYS003+BUG-3] ชีต bill-pattern (รวม 'N (2)') ดึงบิลไม่ได้=ฟอร์มใหม่/ตกหล่น
                    log_system_issue('SYS003', 'Bill Not Extracted', f'ชีต {sheet} มีข้อมูลแต่ดึงบิลไม่ได้ — อาจเป็นฟอร์มใหม่/บิลตกหล่น', severity='WARNING', file=_fname, sheet=str(sheet), echo=True)
                bills.extend(sheet_bills)
            except Exception as e:
                # v6.2 OBSERVABILITY (TARGET 2): ชีตพัง = บิลในชีตนั้นหาย "เงียบ" เดิม
                #   → บันทึกเป็น SYS001 ตามรอยได้ (ไฟล์/ชีต/หลักฐาน error) แต่ยังวนชีตต่อ
                print(f'   ⚠️ ชีต {sheet}: {type(e).__name__}: {str(e)[:80]}')   # [L14] โชว์ชนิด error (เดิมตัดทิ้งซ่อนชนิด)
                log_system_issue('SYS001', 'Sheet Parsing Failure',
                                 'parse ชีตล้มเหลว — บิลในชีตนี้ถูกข้าม',
                                 severity='ERROR', file=_fname, sheet=str(sheet),
                                 exc=e, echo=False)
    except Exception as e:
        print(f'⚠️ ไฟล์เปิดไม่ได้ {_fname}: {str(e)[:80]}')
        log_system_issue('SYS001', 'File Open Failure',
                         'เปิด/อ่านไฟล์ไม่ได้ — ทั้งไฟล์ถูกข้าม',
                         severity='ERROR', file=_fname, exc=e, echo=False)
    finally:
        # v6.1 RESOURCE: ปิด workbook เสมอ — กัน file-handle/หน่วยความจำรั่วเมื่อวนอ่านไฟล์จำนวนมาก
        #   (เดิมไม่เคยปิด → รันหลายร้อย/พันไฟล์เสี่ยง OSError: Too many open files / RAM โต)
        if xl is not None:
            try: xl.close()
            except Exception: pass
    # [FIX-MERGE] รวมบิลหน้าต่อ ก่อนคืนผล
    bills = merge_continuation_bills(bills)
    # [IV002] ตรวจรูปแบบเลขที่เอกสาร เทียบกันเองในไฟล์
    bills = check_iv_format(bills)
    return bills

# [F4 ceiling 11.06.69] get_files_via_drive / get_files_via_upload ย้ายไป parser_guards.py
#   (ชั้น "ปราการรับ input" + การ์ด F1/SYS004) — import ด้านบน re-export ขึ้น chain เหมือนเดิม


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__=[n for n in list(globals().keys()) if not n.startswith('__') and n!='annotations']
