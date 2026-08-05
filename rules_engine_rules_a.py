# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""rules_engine_rules_a — OBJ-MAINT: กลุ่มกฎ r_* (extract คัดลอกเป๊ะ). toolkit จาก rules_engine_base.
ห้ามแก้ logic — golden byte-identical."""
from __future__ import annotations
from rules_engine_base import (   # [F3 de-star] explicit re-export shim (split-base chain; เดิม `import *`)
    CFG, COMPANY_PREFIXES, COMPANY_PREFIX_RE, Counter,
    Decimal, PRODUCT_CATEGORIES, ROUND_HALF_UP, _AMBIG_SHORT_KW,
    _D, _THAI_MARKS, _build_cat_keywords, _ivp_year2_to_ce,
    _ivp_year4_to_ce, _kw_in_name, _raw_company_form, _taxid_checksum_ok,
    _unit_canon, _vat_tolerance, add_issue, clean_tax_id,
    datetime, defaultdict, extract_branch, extract_unit_hint,
    find_similar_in_thai_dict, fuzz, has_hidden_chars, json,
    log_system_issue, match_company, normalize_company_name, normalize_text,
    os, parse_date_any, predict_category, pythainlp_spell_check,
    re, remove_branch_suffix, safe, state,
    statistics, timedelta, to_conf01, unicodedata,
    validate_company_prefix,
)  # noqa: F401  (re-export ขึ้น chain — หลายชื่อไม่ได้ใช้ภายในไฟล์นี้)
from config import (BRAND_BLACKLIST, COMPANY_TYPO_PREFIXES,  # [F3] explicit — config ที่ rules_a ใช้
                    OCR_SUSPICIOUS, audit_today)
from core_utils import parse_address_input  # v9.2 SMART-ADDR: parse 2 ฝั่งด้วย parser เดียวกัน

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
        # v9.3: ผู้ขายบุคคลธรรมดา/ร้าน ไม่ต้องมีคำนำหน้านิติบุคคล → ไม่ฟ้อง
        #   (เลขภาษีไม่ขึ้นต้น '0' = บุคคลธรรมดา ; หรือชื่อขึ้นต้น นาย/นาง/นางสาว/ร้าน)
        _tid = clean_tax_id(b.get('tax_id', ''))
        if (_tid and not _tid.startswith('0')) or re.match(r'^(นาย|นาง|นางสาว|น\.ส\.|ร้าน)', normalized):
            return []
        if not validate_company_prefix(normalized):
            return [f"ขาดคำนำหน้านิติบุคคล: {normalized[:50]}"]
        return []
    except Exception:
        return []

def r_cmp003(b,m,c):
    if not b['company']: return []
    comp = b['company']
    for br in BRAND_BLACKLIST:
        # [M·CMP003/ADR-065] เดิม substring ดิบ → 'CP'∈"CPF Trading", 'Tops'∈"Laptops" ฟ้องผิด.
        #   แบรนด์ทั้งหมดเป็นอักษรละติน → match แบบขอบคำ (ไม่ติดตัวอักษร/ตัวเลขละตินอื่น) กัน FP.
        if re.search(r'(?<![A-Za-z0-9])' + re.escape(br) + r'(?![A-Za-z0-9])', comp, re.IGNORECASE):
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

def r_cmp006(b, m, c):
    """[ADD-ON v9.2] ชื่อบริษัทไม่ตรง 100% กับ ภ.พ.20 — โซน fuzzy ที่ CMP001 ปล่อยผ่าน.

    ลูกค้าขอ "ต่างตัวอักษร = ฟ้อง" (เข้มขึ้น). ฟ้องเฉพาะโซนที่ CMP001 (CRITICAL) ไม่จับ:
      ยกเว้น (= เงียบ): ไม่มี master / ตัวอักษรตรง (ต่างแค่เว้นวรรค = CMP004) /
                        master เป็น substring ของชื่อบิล (เช่นมี '(สำนักงานใหญ่)' ต่อท้าย) /
                        fuzzy < 85 (CMP001 จัดการแล้ว — กันฟ้องซ้ำ).
    advisory: เป็น WARNING/เลน CHECK — โชว์ในสรุปบริษัท (ชื่อบจ.) + Excel. ปิดได้ด้วย enabled=False.
    """
    if not m:
        return []
    bc_raw = b.get('company_raw') or b.get('company', '') or ''
    mc_raw = _raw_company_form(m.get('name', '')) or ''
    nospace = lambda s: re.sub(r'\s+', '', s).strip()
    bcn, mcn = nospace(bc_raw), nospace(mc_raw)
    if not bcn or not mcn:
        return []
    if bcn == mcn:
        return []                      # ตัวอักษรตรง (ต่างแค่เว้นวรรค → CMP004)
    if mcn in bcn or bcn in mcn:
        return []                      # substring (suffix สำนักงานใหญ่/มหาชน ฯลฯ) = ยอมรับ
    score = fuzz.token_sort_ratio(normalize_text(b.get('company', '')),
                                  normalize_text(m.get('name', '')))
    if score < 85:
        return []                      # CMP001 (CRITICAL) จับโซนนี้แล้ว — กันฟ้องซ้ำ
    # [report-fix] เดิม [:45] ตัดชื่อยาวกลางคำ ('...จำกัด'→'...จำ') หลอกตาในรายงาน — ชื่อจริงยาวสุด 67 ตัว
    #   → ตัดที่ 80 + '…' เฉพาะเมื่อยาวเกินจริง (ชื่อจริงทั้งหมดในคอร์ปัสแสดงเต็ม ไม่ตัด)
    _bc = bc_raw.strip(); _mc = mc_raw.strip()
    _bc = _bc if len(_bc) <= 80 else _bc[:79] + "…"
    _mc = _mc if len(_mc) <= 80 else _mc[:79] + "…"
    return [f"ชื่อไม่ตรง 100% กับ ภ.พ.20: บิล='{_bc}' / ภ.พ.20='{_mc}' (เหมือน {score}%)"]

# ════════════════════════════════════════════════════════════════════════════
# v9.2 SMART-ADDR (ADR-014) — เทียบที่อยู่ "ทีละ field" (generic ทุกที่อยู่ ไม่ hardcode)
#   เลิก "เทียบข้อความเป็นก้อน" (ต้นเหตุ false alarm: ลำดับ/ช่องว่าง/label ฟอร์ม)
#   → parse 2 ฝั่งเป็น field + normalize + เทียบด้วย token_sort_ratio. ใช้ร่วม ADDR001/ADDR003
# ════════════════════════════════════════════════════════════════════════════
_ADDR_FUZZ_MIN = 90                                       # token_sort_ratio ≥ 90 = field เดียวกัน
_ADDR_EMPTY = {'', '-', '–', '—', 'n/a', 'na', 'ไม่มี'}    # ค่าว่าง/ขีด/label เปล่า = ไม่นับ
# v9.2 [ADDR-FULL]: เทียบ master "ครบทุก field" ไม่มีรู — แบ่งตาม "ความเชื่อถือได้ของ parser":
#   STRICT (ฟ้องถ้าต่าง/ขาด — parser เชื่อถือได้ เพราะมี label/เลขชัด):
#     เลขที่(house_no) + ไปรษณีย์(zipcode) + แขวง/ตำบล + เขต/อำเภอ + หมู่(moo)
#   SOFT (ฟ้องเฉพาะ "มีทั้งคู่แต่ต่างจริง" — กัน FP จากกรณี parser ดึงไม่ได้/ไม่มี label):
#     CORE/ERROR: จังหวัด(province)  ·  SUB/WARNING: ซอย(soi) + ถนน(road)
#   SUB_STRICT (WARNING, รายละเอียดอาคาร): อาคาร + ชั้น + ห้อง
#   เดิมตก province/moo/soi/road (parse แล้วแต่ไม่เคยรายงาน) → ปิดรูครบทุก field
_ADDR_ANCHOR = ('zipcode', 'district', 'subdistrict', 'house_no', 'moo')   # STRICT core
_ADDR_CORE_SOFT = ('province',)                                            # SOFT core (ฟ้องเฉพาะต่างจริง)
_ADDR_SUB = ('building', 'floor', 'room')                                  # STRICT sub
_ADDR_SUB_SOFT = ('soi', 'road')                                           # SOFT sub (ฟ้องเฉพาะต่างจริง)
_ADDR_LABEL = {'house_no':'เลขที่','moo':'หมู่','soi':'ซอย','road':'ถนน',
               'subdistrict':'แขวง/ตำบล','district':'เขต/อำเภอ','province':'จังหวัด',
               'zipcode':'รหัสไปรษณีย์','building':'อาคาร','floor':'ชั้น','room':'ห้อง'}

def _addr_is_empty(v):
    """ค่า field ว่าง/ขีด/label ฟอร์มเปล่า → ไม่นับว่ามีข้อมูล"""
    return re.sub(r'\s+','',str(v or '')).lower() in _ADDR_EMPTY

def _addr_val(s):
    """normalize 'ค่า' ก่อนเทียบ: ลบช่องว่างทั้งหมด + รวมคำพ้องจังหวัด (กทม.=กรุงเทพมหานคร)"""
    s = re.sub(r'\s+','',str(s or ''))
    s = re.sub(r'^(กทม\.?|กรุงเทพฯ?|กรุงเทพมหานคร)$','กรุงเทพมหานคร',s)
    return s

def _addr_extra(text):
    """ดึง อาคาร/ชั้น/ห้อง (parse_address_input ไม่ครอบ). จับเลขที่ตามหลังแม้คั่น space ('พี 23'='พี23')"""
    t = normalize_text(text or ''); out = {}
    for key, pat in (('building', r'อาคาร\s*([^\s,]+(?:\s+\d+(?:/\d+)?)?)'),
                     ('floor',    r'(?:ชั้นที่|ชั้น)\s*([0-9]{1,3})'),
                     ('room',     r'(?:ห้องเลขที่|ห้อง)\s*([^\s,]+(?:\s+\d+)?)')):
        mm = re.search(pat, t)
        if mm and not _addr_is_empty(mm.group(1)):
            out[key] = mm.group(1).strip()
    return out

def _addr_parse_smart(text):
    """parse ที่อยู่ → field มาตรฐาน. label-based (parse_address_input) + heuristic เมื่อไม่มี label"""
    t = normalize_text(text or '')
    parts = dict(parse_address_input(t))   # house_no/moo/soi/road/subdistrict/district/province/zipcode
    parts.update(_addr_extra(t))           # + building/floor/room
    zips = re.findall(r'\b(\d{5})\b', t)   # heuristic: ไปรษณีย์ = เลข 5 หลักท้ายสุด
    if zips: parts['zipcode'] = zips[-1]
    if not parts.get('house_no'):          # heuristic: เลขนำหน้า เช่น "5/32", "99"
        mm = re.match(r'\s*([0-9]+(?:[/\-][0-9]+)*)', t)
        if mm: parts['house_no'] = mm.group(1)
    if not parts.get('province') and re.search(r'กรุงเทพ|กทม', t):
        parts['province'] = 'กรุงเทพมหานคร'
    # heuristic: แขวง/เขต "ไม่มี label" (เช่น "หนองบอน ประเวศ") → เดาจาก 2 token ไทยท้าย ก่อนจังหวัด
    #   ปลอดภัย: ค่าที่เดามาเทียบ master ด้วย fuzz≥90 อยู่ดี — เดาผิดก็ไม่ match (ไม่ดับของจริง)
    if not parts.get('district') or not parts.get('subdistrict'):
        tail = re.sub(r'\b\d{5}\b.*$', '', t)
        tail = re.sub(r'(กรุงเทพมหานคร|กรุงเทพฯ?|กทม\.?|จังหวัด\s*\S+)\s*$', '', tail).strip()
        _skip = ('ซอย','ตรอก','ถนน','อาคาร','ชั้น','ห้อง','เลขที่','หมู่','หมู่บ้าน')
        thai = [w for w in re.split(r'\s+', tail)
                if re.fullmatch(r'[ก-๙]{2,}', w) and not any(w.startswith(s) for s in _skip)]
        if len(thai) >= 2:
            parts.setdefault('district', thai[-1])
            parts.setdefault('subdistrict', thai[-2])
    return {k: v for k, v in parts.items() if not _addr_is_empty(v)}

def _addr_field_match(bv, mv):
    """เทียบค่า field: True=ตรง, False=ต่างจริง, None=ทะเบียนไม่มี (ไม่ต้องเช็ค)"""
    if _addr_is_empty(mv): return None
    if _addr_is_empty(bv): return False
    a, b2 = _addr_val(bv), _addr_val(mv)
    if a == b2: return True
    if len(a) >= 4 and len(b2) >= 4 and (a in b2 or b2 in a): return True  # ยาวพอ → containment
    return fuzz.token_sort_ratio(a, b2) >= _ADDR_FUZZ_MIN

def _addr_smart_diff(b, m):
    """แกนกลาง ADDR: parse 2 ฝั่ง → เทียบทีละ field. คืน anchor_ok / core(ERROR) / sub(WARNING)"""
    bp = _addr_parse_smart(b.get('address', ''))
    # [ADR-172/BUGHUNT] type-gate: master เป็น JSON ที่ user แก้มือได้ — address_parts ที่ไม่ใช่ dict
    #   (เช่น str) เดิมทำ dict(str) ครัช ValueError → ADDR001/003 ดับเงียบทุกบิลของผู้ขายนั้น (SYS-* INFO).
    #   load_master validate แค่ระดับบน (ADR-165) คลาสนี้หลุด. master ปกติ/ว่าง = no-op.
    _mp_raw = m.get('address_parts')
    mp = dict(_mp_raw) if isinstance(_mp_raw, dict) else {}
    # v9.3 [FIX-HOUSENO]: re-derive house_no สดจาก address_full ด้วย parser ปัจจุบัน
    #   กัน master เก่าที่เคย save house_no ผิด (เช่นจับ 'ห้องเลขที่ 104' เป็นบ้านเลขที่)
    _mfull = m.get('address_full', '') or m.get('address', '')
    if _mfull:
        _fresh_hn = parse_address_input(_mfull).get('house_no')
        if _fresh_hn:
            mp['house_no'] = _fresh_hn
    mp.update(_addr_extra(_mfull))
    res = {f: _addr_field_match(bp.get(f), mp.get(f)) for f in set(list(bp) + list(mp))}
    # SOFT = ฟ้องเฉพาะ "บิลมีค่า + ต่างจริง" (ไม่ฟ้อง 'บิลไม่มี' เพราะ parser อาจดึงไม่ได้)
    _soft_hit = lambda f: res.get(f) is False and not _addr_is_empty(bp.get(f))
    anchor_ok = (all(res.get(f) is not False for f in _ADDR_ANCHOR)
                 and not any(_soft_hit(f) for f in _ADDR_CORE_SOFT))
    core = []
    for f in _ADDR_ANCHOR:                                  # STRICT: ต่าง/ขาด = ฟ้อง
        if res.get(f) is False:
            lbl, mv, bv = _ADDR_LABEL.get(f, f), mp.get(f, ''), bp.get(f, '')
            core.append(f"ไม่พบ{lbl} (ทะเบียน: {mv})" if _addr_is_empty(bv)
                        else f"{lbl}ไม่ตรง (บิล: {bv} / ทะเบียน: {mv})")
    for f in _ADDR_CORE_SOFT:                               # SOFT core: เฉพาะมีทั้งคู่แต่ต่าง
        if _soft_hit(f):
            core.append(f"{_ADDR_LABEL.get(f, f)}ไม่ตรง (บิล: {bp.get(f, '')} / ทะเบียน: {mp.get(f, '')})")
    sub = []
    for f in _ADDR_SUB:                                     # STRICT sub: ต่าง/ขาด = เตือน
        if res.get(f) is False:
            lbl, mv, bv = _ADDR_LABEL.get(f, f), mp.get(f, ''), bp.get(f, '')
            sub.append(f"ทะเบียนมี{lbl} {mv} (บิลไม่มี)" if _addr_is_empty(bv)
                       else f"{lbl}ต่าง (บิล: {bv} / ทะเบียน: {mv})")
    for f in _ADDR_SUB_SOFT:                                # SOFT sub: เฉพาะมีทั้งคู่แต่ต่าง
        if _soft_hit(f):
            sub.append(f"{_ADDR_LABEL.get(f, f)}ต่าง (บิล: {bp.get(f, '')} / ทะเบียน: {mp.get(f, '')})")
    return {'anchor_ok': anchor_ok, 'core': core, 'sub': sub}

def r_addr001(b,m,c):
    """v9.2 SMART (ADR-014): เทียบที่อยู่ทีละ field — ลำดับ/ช่องว่าง/label ต่างไม่เตือน.
    anchor (ไปรษณีย์+เขต+แขวง+เลขที่) ตรงครบ = ที่อยู่ถูก ; ERROR เฉพาะ anchor ที่ต่างจริง"""
    bv = normalize_text(b.get('address', ''))
    if not bv: return ['ไม่พบที่อยู่']
    # standalone (ไม่มี master / address_parts) — คงพฤติกรรมเดิมเป๊ะ
    if not m or not m.get('address_parts'):
        issues = []
        if not re.search(r'\b\d{5}\b', bv):
            issues.append('ไม่พบรหัสไปรษณีย์ 5 หลัก')
        if not any(kw in bv for kw in ['จังหวัด','เขต','อำเภอ','แขวง','ตำบล','กรุงเทพ']):
            issues.append('ไม่พบจังหวัด/เขต/อำเภอ/แขวง/ตำบล')
        return issues
    diff = _addr_smart_diff(b, m)
    if diff['anchor_ok']:
        return []   # anchor ครบ → ดับ false alarm (ลำดับ/space/soi/road ต่างไม่ฟ้อง)
    return [f"ที่อยู่ไม่ตรงทะเบียน: {'; '.join(diff['core'][:4])}"] if diff['core'] else []

def r_addr002(b,m,c):
    if not m: return []
    bv = normalize_text(b['address']); issues = []
    keys = {'road':(r'ถนน([^\s]+)','ถนน'),
            'subdistrict':(r'(?:แขวง|ตำบล)([^\s]+)','แขวง/ตำบล'),
            'district':(r'(?:เขต|อำเภอ)([^\s]+)','เขต/อำเภอ'),
            'province':(r'จังหวัด([^\s]+)','จังหวัด')}
    _mp2 = m.get('address_parts')
    if not isinstance(_mp2, dict): _mp2 = {}   # [ADR-172] type-gate เดียวกับ _addr_smart_diff (str.get ครัช)
    for field, (pat, label) in keys.items():
        expected = _mp2.get(field)
        if not expected or expected in bv: continue
        for w in re.findall(pat, bv):
            # [M·ADDR002/ADR-068] ต่างแค่ "เว้นวรรค" ไม่ใช่สะกดผิด (สอดคล้อง ADDR001 ที่ strip space):
            #   master เก็บถนน 2 token ("พระราม 4") แต่ regex นี้คว้า token เดียว ("พระราม4") → เดิม fuzz~93% ฟ้องผิด.
            if w.replace(' ', '') == (expected or '').replace(' ', ''):
                break
            score = fuzz.ratio(w, expected)
            if 70 < score < 100:
                issues.append(f"{label} อาจสะกดผิด: '{w}' (~{score}%) ควรเป็น '{expected}'"); break
    return issues

def r_addr003(b, m, c):
    """v9.2 SMART (ADR-014): อาคาร/ชั้น/ห้อง — เทียบหลัง normalize (space/label/ลำดับไม่ทำให้ฟ้อง).
    เตือน WARNING เฉพาะ sub-field ที่ต่าง/ขาดจริง (ใช้แกน _addr_smart_diff ร่วมกับ ADDR001)"""
    if not m: return []
    diff = _addr_smart_diff(b, m)
    return ['; '.join(diff['sub'][:4])] if diff['sub'] else []

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
    if not matched:
        return []
    # v9.2 [FIX-TAX005]: ฟ้องเมื่อ tax เป็นของ matched แต่ "ชื่อในบิล ≠ เจ้าของ tax"
    #   (กัน FP ด้วย token_sort ≥ 85 = ชื่อยังใกล้เคียงพอ — calibrated แยก 'บริษัท เอ' จาก 'บริษัท บี').
    # [TAXID-JOIN/ADR-147] เดิมมี guard `same_owner` = (matched.tax == m.tax) นำหน้า — กันฟ้องเมื่อบิล
    #   match master เป็น "เจ้าของ tax" ตามชื่อ. หลังเปลี่ยน join เป็น tax_id-primary (ADR-146) m =
    #   "เจ้าของ tax" เสมอเมื่อ tax อยู่ใน master → same_owner จริงเสมอ → TAX005 เงียบทุกเคส = กลบกฎ
    #   anti-fraud สวมเลข (เจ.อาร์./ฉีหยวน). ตัวแบ่ง "เจ้าของจริง vs สวมเลข" ที่ถูกคือ "ชื่อในบิลตรง
    #   เจ้าของ tax หรือไม่" (token_sort ≥ 85) ไม่ใช่ความเท่ากันของ tax → ถอด same_owner ออก เหลือ
    #   guard ชื่อตัวเดียว (เกณฑ์เดิมของผู้เขียน). golden-NEUTRAL: corpus master ว่าง → matched=None
    #   → return [] ก่อนถึงจุดนี้ (กฎ dormant บน corpus เหมือนเดิม).
    if fuzz.token_sort_ratio(normalize_text(b.get('company','')),
                             normalize_text(matched.get('name',''))) >= 85:
        return []   # ชื่อบิลยังใกล้เคียงเจ้าของ tax พอ → ไม่ฟ้อง (กัน false-positive ชื่อย่อ/รูปต่างเล็กน้อย)
    return [f"⚠️ TaxID {bt} เป็นของ '{matched.get('name','')}' — แต่ในบิลใช้ชื่อ '{b['company']}'"]

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
    # [M·BR/ADR-066] เดิม substring 'สำนัก' → label สาขาที่มีคำนี้ (เช่น "สาขา สำนักงานพระราม9")
    #   ถูกตีเป็นสนญ. → ฟ้อง "ควร 00000" ผิด ทั้งที่ branch_no ถูก. แก้เป็น "สำนักงานใหญ่"/"สนญ" เต็มคำ.
    if 'สำนักงานใหญ่' in (b.get('branch') or '') or 'สนญ' in (b.get('branch') or ''):
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

# ── [B3] BR004 — เทียบสาขาในบิลกับ branch ในทะเบียน master (เมื่อ master มี branch) ───────────
_BR004_NO_RE = re.compile(r'(\d{5})')

def _branch_key(branch_no, branch_label):
    """canonical สาขา: '00000'=สำนักงานใหญ่ / เลขสาขา 5 หลัก ; None = ระบุไม่ชัด (อย่าตัดสิน)."""
    bn = str(branch_no or '').strip()
    if re.match(r'^\d{5}$', bn):
        return bn
    lbl = str(branch_label or '').strip()
    if 'สำนักงานใหญ่' in lbl or 'สนญ' in lbl:   # [M·BR/ADR-066] เต็มคำ กัน "สาขา สำนัก..." ถูกตีเป็นสนญ.
        return '00000'
    mb = _BR004_NO_RE.search(lbl)
    if mb:
        return mb.group(1).zfill(5)
    return None

def r_br004(b, m, c):
    """[B3] เทียบสาขาในบิลกับทะเบียน master (เมื่อมี master + master มี branch).

    BR001/BR002 เช็คแค่ "รูปแบบ/มีหรือไม่" ไม่ใช่ "ตรง master". BR004 เติมส่วน "ตรง master".
    conservative: ไม่มี master match / master ไม่มี branch / บิลระบุสาขาไม่ชัด → เงียบ
    (กรณีไม่มี master จัดการที่ชั้น honesty A1 = ช่องสาขา 'ตรวจไม่ได้'). ฟ้องเฉพาะเมื่อ "ต่างกันชัด".
    """
    if not m:
        return []
    mkey = _branch_key(m.get('branch_no'), m.get('branch'))
    if mkey is None:
        return []
    bkey = _branch_key(b.get('branch_no'), b.get('branch'))
    if bkey is None:
        return []
    if bkey != mkey:
        _bn = 'สำนักงานใหญ่' if bkey == '00000' else f'สาขา {bkey}'
        _mn = 'สำนักงานใหญ่' if mkey == '00000' else f'สาขา {mkey}'
        return [f"สาขาในบิล ({_bn}) ไม่ตรงทะเบียน ({_mn}) ของ '{m.get('name','')}'"]
    return []

def r_doc001(b,m,c):
    """[SHORT] ชื่อชีตเลขล้วน (bare integer) = "วันของเดือน" เทียบ iv_date.day.
    [ADR-058] guard false positive: flag ก็ต่อเมื่อ (a) ไฟล์มี ≥2 ชีตเลขล้วน "ตรงวัน"
    (day-naming จริง) และ (b) ชีตนี้ไม่มี Excel copy-sibling "N (k)" (เทมเพลตก๊อป).
    คง true positive (SHS_68_02 "6") · ลบ FP (TNT_69_03 "2", TSH_69_039 "1") · "ระงับ"
    อย่างเดียว ไม่เพิ่ม flag. ground-truth/พิสูจน์เต็ม: INVARIANTS/DECISIONS.md §ADR-058.
    """
    if not b['iv_date']: return []
    sd = str(b['sheet']).lstrip('0')
    # [M·DOC001/ADR-067] เพิ่ม guard ช่วงวัน 1–31 (สอดคล้องเส้นพี่น้อง apply_sheet_date_crosscheck [V-F3]):
    #   เดิมชื่อชีตเลขล้วน >31 ("32"/"100"/"2026" = สรุป/ปี/ดัชนี) ถูกตีเป็น "วัน" แล้วฟ้องไม่ตรง iv_date ผิด.
    # [ADR-172/BUGHUNT] .isdecimal() — digit ที่ int() ไม่รับ ('²','①') เดิมครัชเป็น SYS-DOC001 ข้ามกฎรายบิล
    if not (sd.isdecimal() and 1 <= int(sd) <= 31 and int(sd) != b['iv_date'].day):
        return []
    # --- [ADR-058] 2-signal guard (รันเฉพาะตอนจะ flag เท่านั้น → cost ~O(bills) แค่เคสหายาก) ---
    n_int = int(sd)
    my_file = b.get('filepath') or b.get('file')
    siblings = c.get('all_bills_for_iv_check') or []
    _sib_re = re.compile(r'^0*%d\s*\(\d+\)$' % n_int)   # copy-sibling "N (k)"
    has_copy_sibling = False
    _corrob_sheets = set()                              # ชีตเลขล้วนที่ตรงวันตัวเอง (distinct)
    # [PERF/ADR-103] เดินเฉพาะกลุ่มไฟล์เดียวกัน (ดัชนี) แทน scan siblings ทั้งหมด — ตัวกรองไฟล์เดิมคงไว้ (golden-neutral)
    _scan = c.get('xbill_file_index', {}).get(b.get('file'), siblings)
    for ob in _scan:
        if (ob.get('filepath') or ob.get('file')) != my_file:
            continue
        osh = str(ob.get('sheet', '')).strip()
        if _sib_re.match(osh):
            has_copy_sibling = True                     # signal (b) ล้มเหลว
        osd = osh.lstrip('0')
        od = ob.get('iv_date')
        if osd.isdecimal() and od and int(osd) == od.day:   # [ADR-172] isdecimal — กัน int() ครัช ('²')
            _corrob_sheets.add(osd)                     # signal (a) สะสม
    if len(_corrob_sheets) >= 2 and not has_copy_sibling:
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
    # [PERF/ADR-103] กฎนี้จำกัด "ไฟล์เดียวกัน" อยู่แล้ว → เดินเฉพาะกลุ่มไฟล์เดียวกัน (ดัชนี) แทน scan ทั้งหมด
    scan = c.get('xbill_file_index', {}).get(b.get('file'), all_bills_in_ctx)
    for ob in scan:
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
        current_ce = audit_today().year
        # [M-1/ADR-064] เดิม hardcode `yr > 2030` = ระเบิดเวลา: พอเวลาจริงถึง ค.ศ. 2031 บิลปกติทุกใบ
        #   (iv_date เป็น ค.ศ. แล้ว) เข้าแบรนช์นี้ → `_is_digit_swap_of(yr+543, current_year_be)` ที่ yr+543==current_year_be
        #   เป็นจริงเสมอ → ฟ้อง "digit swap ของตัวเอง"/"ปีคลุมเครือ" ผิดทุกใบตั้งแต่ปีที่ 5. แก้ให้ขอบเขต "ตามเวลา"
        #   เหมือนแบรนช์ พ.ศ. (current+1) → บิลปีปัจจุบัน/ปีหน้า ไม่เข้า. golden-neutral (corpus ≤2026 + audit 2026
        #   → yr ไม่เกิน current_ce+1 ทั้งก่อน/หลัง).
        if yr > current_ce + 1 and yr < 2500:
            # [BUGFIX recheck #9] parser แปลง พ.ศ.→ค.ศ. (−543) แล้ว → digit-swap ของ "ปีปัจจุบัน" จึงมาตกที่ ค.ศ. band นี้
            #   (เดิม logic digit-swap อยู่ใน band 2500-2600 ที่ไม่มีทางถึงหลังแปลง → ตาย). เช็ก (yr+543) แทน
            if _is_digit_swap_of(yr + 543, current_year_be):
                issues.append(f"ปี {yr} (พ.ศ. {yr+543}) อาจเป็น digit swap ของ {current_year_be} (สลับหลัก?)")
            else:
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
        # [ADR-193] "ศูนย์" ไม่ใช่ "ค่าหาย" — เดิมคัดด้วยความจริงเชิงตรรกะ
        #   `not (qty and price and amount)` ซึ่งใน Python ทำให้ 0/0.0 (ค่าที่ "อ่านได้จริง"
        #   จากเซลล์) ถูกจัดชั้นเดียวกับ None (ค่าที่ "หาย") แล้วข้ามเงียบ. ผลคือบรรทัด
        #   qty=5 price=0 amount=500 หลุด ITM001 ; และหลุด ITM018 ด้วย (ทุกสาขาที่เทียบ
        #   qty×price ต้องการ price_f > 0) → ไม่มีกฎไหนจับ = false-clean (ยอดไม่ถูกตรวจ
        #   แต่รีพอร์ตขึ้น "ตรง"). คัดด้วย `is None` = "ค่าหายจริง" เท่านั้น ตรงเจตนาเดิม.
        #   0×0=0 ยังลงตัว → บรรทัดศูนย์ล้วนเงียบเหมือนเดิม (ไม่เกิด false positive).
        #   corpus จริง 0 บรรทัดที่มีศูนย์ (real_cases 0/80, fixtures 0/3) → golden-NEUTRAL.
        if it['qty'] is None or it['price'] is None or it['amount'] is None: continue
        # [ADR-107/P4] qty==price==amount = เป็นไปไม่ได้จริง (amount=amount² ได้เฉพาะ amount≤1) →
        #   artifact การ map คอลัมน์ (ราคา/หน่วย==ยอด ถูกคว้าเป็นทั้ง qty/price ในใบเหมารวม/บริการ)
        #   ไม่ใช่ error จริง → ข้าม ไม่นับ checkable ไม่ flag. (root fix อยู่ที่ parser
        #   _dic_pick_qty_price คืน None เมื่อ validate ไม่ผ่าน — guard นี้คือ defense-in-depth.)
        try:
            if _D(it['qty']) == _D(it['price']) == _D(it['amount']) and float(it['amount']) > 1:
                continue
        except (ArithmeticError, ValueError, TypeError):
            pass
        checkable += 1
        # [F2/ADR-020] เลขเงิน (qty×price) ด้วย Decimal+ROUND_HALF_UP (เหมือน r_itm ใน rules_c);
        #   gate/threshold/การแสดงผล (:.2f) คงเดิมเป๊ะ — เปลี่ยนเฉพาะ arithmetic ออกจาก float
        # [L4] ห่อ try เหมือน r_itm018: qty×price มหึมา → quantize ระเบิด InvalidOperation (⊂ ArithmeticError).
        #   เดิม r_itm001 ไม่ห่อ (ต่างจาก r_itm018) → SYS-ITM001 ข้าม "ทั้งกฎ" ของบิลนั้น. ข้อมูลจริง ≤1.6e8 ไม่ถึง.
        try:
            e = (_D(it['qty']) * _D(it['price'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            amount_d = _D(it['amount'])
            diff = abs(e - amount_d)
            if diff <= _D(CFG['AMOUNT_TOLERANCE']): continue
            # [ADR-189] ส่วนลดต้อง "พิสูจน์ได้จากเอกสาร" ไม่ใช่ "สันนิษฐานจากช่วงตัวเลข".
            #   เดิม: ยอดอยู่ในช่วง 1–50% ต่ำกว่า qty×price → ถือว่าเป็นส่วนลด → ข้ามเงียบ
            #   = ยอดที่พิมพ์ผิดจริงในแถบนั้นทั้งแถบถูกกลืน (ระบบตรวจสอบยอมรับไม่ได้).
            #   ใหม่: parser เก็บ it['discount'] ไว้เมื่อหาเซลล์ส่วนลดในแถวเดียวกันที่กระทบยอดได้เป๊ะ
            #   → มีส่วนลดจริง = กระทบยอดลงตัว → ข้าม (ไม่ใช่ error) ; ไม่มี = ฟ้องเสมอ (ไม่เดาแทนผู้ใช้).
            _disc = it.get('discount')
            if _disc is not None:
                try:
                    _net = (_D(it['qty']) * _D(it['price']) * (Decimal('1') - _D(_disc))
                            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    if abs(_net - amount_d) <= _D(CFG['AMOUNT_TOLERANCE']):
                        continue        # ส่วนลดบนเอกสารกระทบยอดได้เป๊ะ → ยอดถูกต้อง
                except (ArithmeticError, ValueError, TypeError):
                    pass
                out.append(f"#{it['seq']}: {it['qty']}×{it['price']} ลด {float(_disc)*100:.0f}% "
                           f"ควรได้ {_net:.2f} แต่={it['amount']:.2f}")
                continue
            out.append(f"#{it['seq']}: {it['qty']}×{it['price']}={e:.2f} แต่={it['amount']:.2f} "
                       f"(ไม่พบส่วนลดในเอกสาร)")
        except (ArithmeticError, ValueError, TypeError):
            continue
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
    # [L2] กัน DoS: seq มหึมา (เช่น 5,000,000 จากเซลล์ขยะ) ทำ set(range(1,end+1)) กิน RAM/ช้าหลายวินาที.
    #   บิลจริง seq ≤ ~50 (parser cap) → เพดาน 10000 ไม่กระทบ (golden-neutral). เกิน → ฟ้องผิดช่วงแทนสร้าง set ยักษ์.
    if end > 10000:
        o.append(f"ลำดับสูงสุด={end} ผิดช่วงปกติ — น่าจะอ่านเลขลำดับผิด")
        return o
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
