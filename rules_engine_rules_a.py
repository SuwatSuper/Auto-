# -*- coding: utf-8 -*-
"""rules_engine_rules_a — OBJ-MAINT: กลุ่มกฎ r_* (extract คัดลอกเป๊ะ). toolkit จาก rules_engine_base.
ห้ามแก้ logic — golden byte-identical."""
from __future__ import annotations
from rules_engine_base import *  # noqa: F401,F403

def r_cmp001(b,m,c):
    try:
        if not m: return []
        bc, mc = normalize_text(b['company']), normalize_text(m.get('name',''))
        mc_alt = normalize_text(m.get('name_alt',''))
        if not mc: return []
        # Exact / substring match
        if bc == mc or mc in bc or (mc_alt and mc_alt in bc):
            return []
        # Fuzzy fallback (v8.1): token_sort_ratio ≥ 85 → ผ่าน (แค่ช่องว่าง/ลำดับคำต่าง)
        score = fuzz.token_sort_ratio(bc, mc)
        if score >= 85:
            return []
        alt_score = fuzz.token_sort_ratio(bc, mc_alt) if mc_alt else 0
        best_score = max(score, alt_score)
        return [f"ในไฟล์: {bc[:60]} | master: {mc[:60]} (fuzzy={best_score}%)"]
    except Exception:
        return []

def r_cmp002(b,m,c):
    """v8.1: ใช้ validate_company_prefix + ตรวจ typo prefix"""
    try:
        normalized = normalize_company_name(b.get('company'))
        if not normalized:
            return ['ไม่พบชื่อบริษัท']
        # ตรวจ typo prefixes ก่อน
        for typo in COMPANY_TYPO_PREFIXES:
            if normalized.startswith(typo):
                return [f"คำนำหน้าน่าจะพิมพ์ผิด: '{typo}' (ควรเป็น 'บริษัท'?): {normalized[:50]}"]
        if not validate_company_prefix(normalized):
            return [f"ขาดคำนำหน้านิติบุคคล: {normalized[:50]}"]
        return []
    except Exception:
        return []

def r_cmp003(b,m,c):
    if not b['company']: return []
    for br in BRAND_BLACKLIST:
        if br.lower() in b['company'].lower():
            return [f"พบชื่อแบรนด์ '{br}'"]
    return []

def r_cmp004(b,m,c):
    """v5.9 [FIX-CMP004]: จับ "ชื่อเดียวกันแต่จำนวนเว้นวรรคไม่ตรง master"
    ของเดิมพังเพราะ normalize_text ยุบ \\s+ เป็นช่องเดียวทั้งคู่ → ไม่มีทางต่าง
    แก้: เทียบจากค่าดิบ (company_raw) ที่คงช่องว่างจริงไว้
      - ถ้ายุบช่องว่างแล้วยัง "ต่างตัวอักษร" → ปล่อย CMP001 จัดการ (ไม่ใช่เรื่องเว้นวรรค)
      - ถ้ายุบแล้วเท่ากัน แต่ค่าดิบต่าง = เว้นวรรคเกิน/ขาด → แจ้งเตือน
    """
    if not m: return []
    bc_raw = b.get('company_raw') or remove_branch_suffix(b.get('company',''))
    mc_raw = _raw_company_form(m.get('name',''))
    if not bc_raw or not mc_raw:
        return []
    collapse = lambda s: re.sub(r'\s+', ' ', s).strip()
    bc_c, mc_c = collapse(bc_raw), collapse(mc_raw)
    if bc_c != mc_c:
        return []   # ต่างที่ตัวอักษรจริง ไม่ใช่เว้นวรรค → CMP001 รับผิดชอบ
    if bc_raw.strip() != mc_raw.strip():
        vis = lambda s: s.strip().replace(' ', '␣')
        bsp = bc_raw.strip().count(' ')
        msp = mc_raw.strip().count(' ')
        return [f"เว้นวรรคไม่ตรงกับ master (ชื่อเดียวกันแต่จำนวนช่องว่างต่าง): "
                f"ไฟล์มี {bsp} ช่องว่าง / master มี {msp} ช่องว่าง — "
                f"ไฟล์='{vis(bc_raw)}' | master='{vis(mc_raw)}' (␣ = ช่องว่าง)"]
    return []

def r_addr001(b,m,c):
    """v8.1: normalize space รอบ '/' + standalone validation เมื่อไม่มี master"""
    bv = normalize_text(b['address'])
    if not bv: return ['ไม่พบที่อยู่']
    # v8.1: Standalone validation เมื่อ master=None หรือไม่มี address_parts
    if not m or not m.get('address_parts'):
        issues = []
        # ตรวจรหัสไปรษณีย์ 5 หลัก
        if not re.search(r'\b\d{5}\b', bv):
            issues.append('ไม่พบรหัสไปรษณีย์ 5 หลัก')
        # ตรวจว่ามีอย่างน้อย 1 ใน จังหวัด/เขต/อำเภอ/แขวง/ตำบล
        has_loc = any(kw in bv for kw in ['จังหวัด','เขต','อำเภอ','แขวง','ตำบล','กรุงเทพ'])
        if not has_loc:
            issues.append('ไม่พบจังหวัด/เขต/อำเภอ/แขวง/ตำบล')
        return issues

    # ตัด whitespace รอบ '/' ให้เป็น compact: "3 / 182" → "3/182"
    def _compact(s):
        return re.sub(r'\s*/\s*', '/', s)
    bv_compact = _compact(bv)
    # version ที่ '/' แทนด้วย space: "3/182" → "3 182"
    bv_spaced = bv_compact.replace('/', ' ')

    MANDATORY = {'house_no','moo','subdistrict','district','province'}
    label = {'house_no':'เลขที่','moo':'หมู่ที่','soi':'ซอย','road':'ถนน',
             'subdistrict':'แขวง/ตำบล','district':'เขต/อำเภอ','province':'จังหวัด','zipcode':'รหัสไปรษณีย์'}
    errors = []; infos = []
    for k, v in (m.get('address_parts') or {}).items():
        if not v: continue
        v_compact = _compact(v)
        v_spaced = v_compact.replace('/', ' ')
        # match แบบ flexible: ตรงเป๊ะ หรือ '/' = space
        if v_compact in bv_compact or v_spaced in bv_spaced:
            continue
        if k in ('soi','road') and fuzz.partial_ratio(v_compact, bv_compact) >= CFG['FUZZY_SOI_THRESHOLD']:
            continue
        if k in MANDATORY:
            errors.append(f"{label.get(k,k)} {v}")
        elif k == 'zipcode':
            errors.append(f"{label.get(k,k)} {v}")
        else:
            infos.append(f"{label.get(k,k)} {v}")
    out = []
    if errors:
        out.append(f"ขาด {len(errors)} จุด: {'; '.join(errors[:4])}")
    if infos:
        out.append(f"ไม่พบ {'; '.join(infos[:3])} (อาจไม่มีในเอกสาร)")
    return out

def r_addr002(b,m,c):
    if not m: return []
    bv = normalize_text(b['address']); issues = []
    keys = {'road':(r'ถนน([^\s]+)','ถนน'),
            'subdistrict':(r'(?:แขวง|ตำบล)([^\s]+)','แขวง/ตำบล'),
            'district':(r'(?:เขต|อำเภอ)([^\s]+)','เขต/อำเภอ'),
            'province':(r'จังหวัด([^\s]+)','จังหวัด')}
    for field, (pat, label) in keys.items():
        expected = (m.get('address_parts') or {}).get(field)
        if not expected or expected in bv: continue
        for w in re.findall(pat, bv):
            score = fuzz.ratio(w, expected)
            if 70 < score < 100:
                issues.append(f"{label} อาจสะกดผิด: '{w}' (~{score}%) ควรเป็น '{expected}'"); break
    return issues

def r_addr003(b, m, c):
    """v5.8s: ตรวจชั้น/อาคาร/ห้องเลขที่ — เทียบบิลกับ master 2 ทาง
       parse_address_input ไม่ครอบฟิลด์เหล่านี้ จึงต้องเช็กเองตรงนี้
       เคสที่จับ:
         • บิลโผล่ 'ชั้นที่ 21' มาทั้งที่ master ไม่มี (อาจเปลี่ยน vendor / เอกสารผิด)
         • master มี 'อาคาร XX' แต่บิลไม่มี (อาจเอกสารใหม่ตกหล่น)
    """
    if not m: return []
    bv = normalize_text(b.get('address', ''))
    mv = normalize_text(m.get('address_full', ''))
    if not bv or not mv: return []

    patterns = [
        ('ชั้น',       r'(?:ชั้นที่|ชั้น)\s*([0-9]+)'),
        ('อาคาร',      r'อาคาร\s*([^\s,]{1,30})'),
        ('ห้องเลขที่', r'(?:ห้องเลขที่|ห้อง)\s*([^\s,]{1,15})'),
    ]
    diffs = []
    for label, pat in patterns:
        bill_vals = set(re.findall(pat, bv))
        master_vals = set(re.findall(pat, mv))
        for v in bill_vals - master_vals:
            if not any(fuzz.ratio(v, mv_x) >= 85 for mv_x in master_vals):
                diffs.append(f"บิลมี {label} {v} (master ไม่มี)")
        for v in master_vals - bill_vals:
            if not any(fuzz.ratio(v, bv_x) >= 85 for bv_x in bill_vals):
                diffs.append(f"master มี {label} {v} (บิลไม่มี)")
    if diffs:
        return ['; '.join(diffs[:4])]
    return []

def r_tax001(b,m,c):
    t = clean_tax_id(b['tax_id'])
    if not t: return ['ไม่พบเลขภาษี']
    if len(t) != 13:
        if len(t) == 12: return [f"12 หลัก — อาจขาด 0 นำหน้า: {t}"]
        return [f"ความยาว {len(t)} หลัก"]
    return []

def r_tax002(b,m,c):
    """v5.8d: จับเลข 13 หลักที่อนุญาต separator (space, -, .) → clean → validate"""
    raw = b.get('tax_id_raw','')
    if not raw: return []
    text = str(raw)
    # 1. จับกลุ่ม 13 หลักที่อนุญาต separator
    match = re.search(r'(?<!\d)(?:\d[\-\.\s]*){12}\d(?!\d)', text)
    if not match:
        return [f"ไม่พบเลขภาษี 13 หลักใน: '{text[:50]}'"]
    # 2. clean → ตัวเลขล้วน
    tax_id = re.sub(r'\D', '', match.group(0))
    if len(tax_id) != 13:
        return [f"เลขภาษีไม่ใช่ 13 หลัก: '{tax_id}' ({len(tax_id)} หลัก)"]
    return []

def r_tax003(b,m,c):
    if not m or not b['tax_id'] or not m.get('tax_id'): return []   # v6: ไม่เทียบถ้า master ไม่มีเลขภาษี (กัน KeyError + ฟ้องผิด)
    bt, mt = clean_tax_id(b['tax_id']), clean_tax_id(m.get('tax_id',''))
    if bt != mt:
        if len(bt) == 12 and ('0'+bt) == mt:
            return [f"ในไฟล์ {bt} (12 หลัก) | master {mt}"]
        return [f"เลขภาษี {bt} ไม่ตรงกับ '{m.get('name','')}' ({mt}) — อันตราย"]
    return []

def r_tax004(b,m,c):
    raw = b.get('tax_id_raw','')
    if not raw: return []
    cand = re.search(r'[\d\-OIlSZBoQqi]{10,}', raw)
    if cand:
        susp = set(cand.group()) & OCR_SUSPICIOUS
        if susp: return [f"อักขระน่าสงสัย (OCR?): {sorted(susp)}"]
    return []

def r_tax005(b,m,c):
    if not b['tax_id']: return []
    bt = clean_tax_id(b['tax_id'])
    all_masters = c.get('all_masters', {})
    matched = None
    for key, mm in all_masters.items():
        if clean_tax_id(mm.get('tax_id','')) == bt:        # v6: .get กัน KeyError
            matched = mm; break
    if matched and m and clean_tax_id(matched.get('tax_id','')) != clean_tax_id(m.get('tax_id','')):
        return [f"⚠️ TaxID {bt} เป็นของ '{matched.get('name','')}' — แต่ในบิลใช้ชื่อ '{b['company']}'"]
    return []

def r_tax006(b,m,c):
    """v7: ตรวจ checksum เลขภาษี 13 หลัก (mod 11) — จับเลขปลอม/พิมพ์ผิดที่ "นับหลักครบ" แต่ผิดจริง
    ฟ้องเฉพาะกรณี 13 หลักล้วนแต่ checksum ไม่ผ่าน → ไม่ทับซ้อน TAX001 (ความยาว) / TAX002 (ตัวเลขล้วน)
    deterministic ไม่เดา → false positive แทบเป็นศูนย์ (เลขภาษีไทยที่ถูกต้องผ่าน checksum เสมอ)"""
    t = clean_tax_id(b['tax_id'])
    if len(t) != 13 or not t.isdigit():
        return []                       # ความยาว/ตัวเลข ปล่อยให้ TAX001/TAX002 จัดการ
    if _taxid_checksum_ok(t):
        return []
    return [f"checksum หลักที่ 13 ไม่ผ่าน: {t} — เลขภาษีน่าจะพิมพ์ผิด/ไม่ถูกต้อง"]

def r_br001(b,m,c):
    if 'สำนัก' in (b.get('branch') or ''):
        if b['branch_no'] != '00000':
            return [f"สำนักงานใหญ่ ควร 00000 แต่={b['branch_no'] or 'ไม่มี'}"]
        return []
    if not b['branch_no']: return ['ไม่พบรหัสสาขา']
    if not re.match(r'^\d{5}$', b['branch_no']):
        return [f"รหัสสาขา {b['branch_no']} ไม่ใช่ 5 หลัก"]
    return []

def r_br002(b,m,c):
    if not b['branch'] and not b['branch_no']:
        return ['ไม่ระบุ สำนักงานใหญ่/สาขา (ต้องลงทุกบิล)']
    return []

def r_doc001(b,m,c):
    if not b['iv_date']: return []
    sd = str(b['sheet']).lstrip('0')
    if sd.isdigit() and int(sd) != b['iv_date'].day:
        return [f"ชีต={b['sheet']} แต่วันที่={b['iv_date'].day}"]
    return []

def r_doc002(b,m,c):
    """v5.8k: ไม่ parse ปี/เดือนจาก IV (format ไม่แน่นอน)
    แต่ละบริษัทใช้ format ต่างกัน:
    - IV681104xxxx → 68=พ.ศ.ปี, 11=เดือน, 04=วัน (Thai)
    - J25110023     → 25=ค.ศ.ปี, 11=เดือน, 0023=running (Gregorian)
    - INV-2025-001  → ปี ค.ศ. 4 หลัก
    ไม่มีทาง parse ได้ universal → ปิดการตรวจ
    """
    return []

def r_iv001(b,m,c):
    """v5.8j: ไม่ hardcode prefix จาก master
    ตรวจ consistency ภายในไฟล์/vendor แทน:
    - ดู prefix ทั้งหมดของ vendor นี้ในไฟล์เดียวกัน
    - ถ้า prefix ของบิลนี้ไม่ใช่ prefix หลัก (majority) → flag เป็น WARNING
    - ถ้าเป็น prefix เดียวที่ใช้ทั้งหมด → ไม่ flag (แม้จะไม่ตรง master)
    """
    if not b['iv_number']: return []
    # extract prefix = ตัวอักษรขึ้นต้น (ก่อนตัวเลขแรก)
    m_pre = re.match(r'^([A-Za-z]+)', b['iv_number'])
    if not m_pre: return []
    this_prefix = m_pre.group(1).upper()

    # ดึง all bills ของ vendor เดียวกันในไฟล์เดียวกันจาก context
    all_bills_in_ctx = c.get('all_bills_for_iv_check', [])
    if not all_bills_in_ctx:
        # ไม่มี context → ไม่ flag (เพราะไม่มีข้อมูลเทียบ consistency)
        return []

    same_vendor_file = []
    bv = clean_tax_id(b.get('tax_id','')) or normalize_text(b.get('company','')).upper()
    for ob in all_bills_in_ctx:
        if ob.get('file') != b.get('file'): continue
        ov = clean_tax_id(ob.get('tax_id','')) or normalize_text(ob.get('company','')).upper()
        if ov != bv: continue
        if not ob.get('iv_number'): continue
        mp = re.match(r'^([A-Za-z]+)', ob['iv_number'])
        if mp: same_vendor_file.append(mp.group(1).upper())

    if len(same_vendor_file) < 2: return []  # ข้อมูลไม่พอตัดสิน
    prefix_counts = Counter(same_vendor_file)
    dominant_prefix, dom_count = prefix_counts.most_common(1)[0]

    # ถ้า prefix ของบิลนี้ตรงกับ dominant → ผ่าน
    if this_prefix == dominant_prefix: return []
    # ถ้า dominant ครอง ≥80% และบิลนี้ใช้ prefix อื่น → inconsistent
    if dom_count / len(same_vendor_file) >= 0.8:
        return [f"Prefix='{this_prefix}' ต่างจาก prefix หลักของ vendor นี้ในไฟล์เดียวกัน "
                f"('{dominant_prefix}' = {dom_count}/{len(same_vendor_file)} บิล)"]
    return []

def r_dt001(b,m,c):
    """v5.8 [FIX-8]: รองรับ target_month_end (filename month range)"""
    if not b['iv_date']: return []
    tm = c.get('target_month'); tme = c.get('target_month_end')
    if not tm: return []
    bm = b['iv_date'].month
    if tme:
        if not (tm <= bm <= tme):
            return [f"วันที่ {b['iv_date'].strftime('%d/%m/%Y')} ไม่อยู่ในช่วงเดือน {tm:02d}-{tme:02d}"]
    else:
        if bm != tm:
            return [f"วันที่ {b['iv_date'].strftime('%d/%m/%Y')} ไม่ตรงเดือน {tm:02d}"]
    return []

def r_dt002(b,m,c):
    if not b['iv_date']:
        return []
    # v7.1: เทียบ "วันที่" ตามเวลาไทย (UTC+7) ไม่อิงนาฬิกาเซิร์ฟเวอร์
    #   → จับวันอนาคตได้ตั้งแต่ 1 วัน (พรุ่งนี้ขึ้นไป) โดยไม่ฟ้องผิดจาก timezone
    #     (เซิร์ฟเวอร์ UTC ช่วงเช้ามืดไทยเคยมองใบ "วันนี้" เป็นอนาคต → ตัดปัญหานี้)
    # v9 [REPRO-FIX]: ใช้ audit_today() (ฉีด env PUOPUY_AUDIT_DATE ได้) แทน datetime.now()
    #   เพื่อให้ผลตรวจ reproducible — default ยังเป็นวันนี้เวลาไทยเหมือนเดิมทุกประการ
    today_th = audit_today()
    ivd = b['iv_date']
    iv_day = ivd.date() if hasattr(ivd, 'date') else ivd     # รองรับทั้ง datetime/date — กัน crash
    grace = CFG.get('FUTURE_DATE_GRACE_DAYS', 0)
    if iv_day > today_th + timedelta(days=grace):
        return [f"วันที่ {ivd.strftime('%d/%m/%Y')} เป็น future"]
    return []

def r_dt003(b,m,c):
    try:
        if not b['iv_date']: return []
        yr = b['iv_date'].year
        issues = []
        # ตรวจ digit swap เช่น 2658 แทน 2568, 2856 แทน 2568
        def _is_digit_swap_of(y, ref):
            return sorted(str(y)) == sorted(str(ref))
        current_year_be = audit_today().year + 543
        if yr > 2030 and yr < 2500:
            issues.append(f"ปี {yr} อาจคลุมเครือ (ค.ศ./พ.ศ.?)")
        elif 2500 <= yr <= 2600:
            # ตรวจ digit swap กับปีปัจจุบัน พ.ศ. เช่น 2658 แทน 2568
            if yr != current_year_be and _is_digit_swap_of(yr, current_year_be):
                issues.append(f"ปี {yr} อาจเป็น digit swap ของ {current_year_be} (สลับหลัก?)")
            elif yr < 2550:
                issues.append(f"ปี {yr} เก่ามาก (ก่อน พ.ศ. 2550)")
            elif yr > current_year_be + 1:
                issues.append(f"ปี {yr} เกินปีปัจจุบัน {current_year_be}")
        elif yr > 2600:
            issues.append(f"ปี {yr} ผิดปกติ (เกิน พ.ศ. 2600 — digit สลับ?)")
        return issues
    except Exception:
        return []

def r_itm001(b,m,c):
    """v5.8 [FIX-7]: ตรวจ plausible discount → skip flag
    v7.2: ถ้า "เกือบทั้งใบ" qty×price ไม่ตรง amount → น่าจะ detect/สลับคอลัมน์ผิด
          (ไม่ใช่หลายรายการพิมพ์ผิดอิสระ) → สรุปบรรทัดเดียว ชี้ต้นเหตุจริง แทน flood ราย ๆ
    """
    out = []
    checkable = 0
    for it in b['items']:
        if not (it['qty'] and it['price'] and it['amount']): continue
        checkable += 1
        e = round(it['qty']*it['price'], 2)
        diff = abs(e - it['amount'])
        if diff <= CFG['AMOUNT_TOLERANCE']: continue
        # v5.8: ตรวจว่าน่าจะเป็นส่วนลด
        if e > 0 and 0 < it['amount'] < e:
            discount_pct = (1 - it['amount']/e) * 100
            if CFG['DISCOUNT_MIN_PCT'] <= discount_pct <= CFG['DISCOUNT_MAX_PCT']:
                continue  # legit discount, skip flag
        out.append(f"#{it['seq']}: {it['qty']}×{it['price']}={e:.2f} แต่={it['amount']:.2f}")
    # v7.2: ผิดกระจายเกือบทั้งใบ (ตรวจได้ ≥5 รายการ และไม่ผ่าน ≥60%) → ชี้ต้นเหตุคอลัมน์ ไม่ flood
    if checkable >= 5 and len(out) >= max(3, int(checkable * 0.6)):
        return [f"จำนวน×ราคา ไม่ตรงยอด {len(out)}/{checkable} รายการ — "
                f"น่าจะจับ/สลับคอลัมน์ (จำนวน/ราคา/ยอด) ผิด มากกว่าหลายรายการพิมพ์ผิดอิสระ "
                f"— ตรวจการ map คอลัมน์ของใบนี้"]
    return out

def r_itm002(b,m,c):
    if not b['items']: return []

    # ดึงลำดับมาทำเป็นตัวเลขจำนวนเต็ม
    seqs = []
    for i in b['items']:
        try: seqs.append(int(float(i['seq'])))
        except Exception: pass
    if not seqs: return []

    seqs_set = set(seqs)
    o = []

    # 1. เช็กซ้ำ
    dups = [n for n, x in Counter(seqs).items() if x > 1]
    if dups: o.append(f"ลำดับซ้ำ: {dups}")

    # 2. เช็กฟันหลอ (gap) ขาดตัวไหน แจ้งตัวนั้น
    start, end = min(seqs), max(seqs)
    expected_seq = set(range(1, end + 1))
    missing = expected_seq - seqs_set

    if missing:
        missing_sorted = sorted(list(missing))
        if len(missing_sorted) <= 10:
            o.append(f"ลำดับขาดหาย (ฟันหลอ): {missing_sorted}")
        else:
            o.append(f"ลำดับขาดหาย {len(missing_sorted)} รายการ (เช่น {missing_sorted[:3]}...)")

    return o


# OBJ-MAINT: auto-export ทุกชื่อ (รวม helper _ และ import) → from-import * ได้ toolkit ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
