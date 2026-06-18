# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""rules_engine_rules_b — OBJ-MAINT: กลุ่มกฎ r_* (extract คัดลอกเป๊ะ). toolkit จาก rules_engine_base.
ห้ามแก้ logic — golden byte-identical."""
from __future__ import annotations
from rules_engine_base import (   # [F3 de-star] explicit re-export shim (split-base chain; เดิม `import *`)
    CFG, COMPANY_PREFIXES, COMPANY_PREFIX_RE, Counter,
    Decimal, PRODUCT_CATEGORIES, ROUND_HALF_UP, _AMBIG_SHORT_KW,
    _D, _THAI_MARKS, _build_cat_keywords, _ivp_year2_to_ce,
    _ivp_year4_to_ce, _kw_in_name, _raw_company_form, _taxid_checksum_ok,
    _unit_canon, _vat_tolerance, VAT_RATE, add_issue, clean_tax_id,
    datetime, defaultdict, extract_branch, extract_unit_hint,
    find_similar_in_thai_dict, fuzz, has_hidden_chars, json,
    log_system_issue, match_company, normalize_company_name, normalize_text,
    os, parse_date_any, predict_category, pythainlp_spell_check,
    re, remove_branch_suffix, safe, state,
    statistics, timedelta, to_conf01, unicodedata,
    validate_company_prefix,
)  # noqa: F401  (re-export ขึ้น chain — หลายชื่อไม่ได้ใช้ภายในไฟล์นี้)
from config import (CONSTRUCTION_DICT, PYTHAINLP_WHITELIST, SPELLING_PATTERNS,  # [F3] explicit — config ที่ rules_b ใช้
                    THAI_TYPO_PATTERNS, UNIT_RULES, VAGUE_KEYWORDS)

def r_itm013(b,m,c):
    if not b['items'] or len(b['items']) < 2: return []
    seqs = [i['seq'] for i in b['items']]
    o = []
    if seqs != sorted(seqs):
        rev_pairs = []
        for i in range(len(seqs)-1):
            if seqs[i] > seqs[i+1]:
                rev_pairs.append(f"#{seqs[i]}→#{seqs[i+1]}")
        if rev_pairs:
            o.append(f"ลำดับไม่เรียง: {', '.join(rev_pairs[:5])}")
    if seqs and min(seqs) != 1:
        o.append(f"ไม่เริ่มที่ 1: เริ่มที่ #{min(seqs)}")
    return o

def r_itm014(b,m,c):
    if not b['items'] or len(b['items']) < 3: return []
    seqs = sorted(set([i['seq'] for i in b['items']]))
    o = []
    gaps = []
    for i in range(len(seqs)-1):
        gap = seqs[i+1] - seqs[i]
        if gap > 10:
            gaps.append(f"#{seqs[i]}→#{seqs[i+1]} (ห่าง {gap})")
    if gaps:
        o.append(f"พบ gap ใหญ่: {', '.join(gaps[:3])}")
    return o

def r_itm015(b,m,c):
    if not b['items']: return []
    idx = c.get('unit_index')
    if not idx: return []
    o = []
    seen = set()
    for it in b['items']:
        if not it['unit'] or it['name'] in seen: continue
        seen.add(it['name'])
        units = idx.get(it['name'], set())
        # v8.6 [FIX-ITM015]: ยุบหน่วยพ้องความหมายก่อน (กก.=กิโลกรัม) → ฟ้องเฉพาะที่ "ต่างกลุ่ม" จริง
        canon = {_unit_canon(u) for u in units}
        if len(canon) > 1:
            o.append(f"#{it['seq']} \"{it['name'][:35]}\" — ใช้หน่วย {sorted(units)} ในชุดเดียวกัน")
    return o

def r_itm017(b,m,c):
    """v7.2: ตรวจค่าติดลบผิดปกติในบรรทัดรายการ — "จำนวน" หรือ "ราคา/หน่วย" ติดลบ
    บนบรรทัดที่คิดเงินจริง (เกือบไม่มีทางถูกต้องในใบกำกับภาษีปกติ)
    - ข้ามบรรทัดส่วนลด/เครดิตโน้ตที่อาจติดลบโดยตั้งใจ
    - ตรวจเฉพาะค่าที่เป็นตัวเลขจริง (ไม่ฟ้องค่าว่าง/None → กัน false positive จาก parse ไม่ครบ)
    - ไม่ฟ้อง 'ยอดรวม' ติดลบ (ปล่อย VAT005 จับ) — เน้นเฉพาะจำนวน/ราคาต่อหน่วย
    """
    o = []
    for it in b['items']:
        name = it.get('name', '') or ''
        nl = name.lower()
        if any(k in nl for k in ('discount', 'credit')) or any(k in name for k in ('ส่วนลด', 'เครดิต', 'หักส่วนลด')):
            continue
        q, p = it.get('qty'), it.get('price')
        bad = []
        if isinstance(q, (int, float)) and not isinstance(q, bool) and q < 0:
            bad.append(f"จำนวน={q:g}")
        if isinstance(p, (int, float)) and not isinstance(p, bool) and p < 0:
            bad.append(f"ราคา/หน่วย={p:g}")
        if bad:
            o.append(f"#{it['seq']} \"{name[:35]}\" — ค่าติดลบผิดปกติ: {', '.join(bad)}")
    return o

def r_itm003(b,m,c):
    o = []
    for it in b['items']:
        for kw in VAGUE_KEYWORDS:
            if kw in it['name'] and len(it['name']) < 40:
                o.append(f"#{it['seq']}: \"{it['name']}\" คลุมเครือ"); break
    return o

def r_itm004(b,m,c):
    """v8.0: ตรวจ SPELLING_PATTERNS + hidden chars; ห้ามซ้ำกับ ITM010"""
    UNIT_OK = re.compile(r"\d+\s*(?:มม|ซม|นิ้ว|เมตร|ม|กก|ก)\.?|\d+['\"]")
    o = []
    seen_msgs = set()
    for it in b['items']:
        raw = it.get('name_raw') or it.get('name') or ''
        raw_nfc = unicodedata.normalize('NFC', raw)
        for pat, msg in SPELLING_PATTERNS:
            if not msg: continue
            if pat == r'\s{2,}': continue  # space ซ้อน — ไม่เตือน
            try:
                mt = re.search(pat, raw_nfc)
            except re.error:
                continue
            if not mt: continue
            if UNIT_OK.fullmatch(mt.group(0).strip()): continue
            key = (it['seq'], msg)
            if key in seen_msgs: continue
            seen_msgs.add(key)
            o.append(f"#{it['seq']}: {msg} ({it['name'][:40]})")
        hidden = has_hidden_chars(raw)
        if hidden:
            o.append(f"#{it['seq']}: อักขระแปลก {hidden}")
    return o

def r_itm005(b,m,c):
    """v5.8j: Reasonable unit match — synonym groups + INFO severity for soft mismatch"""
    # หน่วยที่ใช้แทนกันได้ (synonym groups)
    UNIT_SYNONYMS = [
        {'แกลลอน','กระป๋อง','ถัง','ปี๊บ','กล.'},          # ของเหลว/สี
        {'ลิตร','มล.','ล.','cc'},                          # ปริมาตร
        {'กก.','กิโล','กิโลกรัม','ก.ก.','kg'},            # น้ำหนัก
        {'แผ่น','ผืน','บาน'},                              # แผ่นวัสดุ
        {'ม้วน','โรล','roll'},
        {'ชุด','เซ็ต','set','คู่'},
        {'เส้น','ท่อน','อัน'},
        {'ก้อน','ลูก','ตัว'},
        {'ถุง','กระสอบ','แพ็ค','พาเลท','กล่อง','ลัง'},
    ]
    # decor override (จาก v5.8g)
    DECOR_KW = ['มู่ลี่', 'ม่าน', 'ตกแต่ง']
    DECOR_UNITS = ['ชุด', 'บาน', 'เมตร', 'ม.', 'ผืน']

    def _same_group(u1, u2):
        for grp in UNIT_SYNONYMS:
            if any(g in u1 for g in grp) and any(g in u2 for g in grp):
                return True
        return False

    o = []
    for it in b['items']:
        if not it['unit']: continue
        # decor override
        if any(kw in it['name'] for kw in DECOR_KW):
            if not any(u in it['unit'] for u in DECOR_UNITS):
                o.append(f"#{it['seq']} \"{it['name'][:30]}\" — หน่วย={it['unit']} ควร {DECOR_UNITS[:3]} (decor)")
            continue
        for kw, exp in UNIT_RULES:
            if _kw_in_name(kw, it['name']):   # v9: กัน substring คำสั้นกำกวม (สี/สาย/หิน/ปูน...)
                # ตรงเป๊ะ → ผ่าน
                if any(u in it['unit'] for u in exp): break
                # synonym match → ผ่าน (ไม่ flag)
                if any(_same_group(it['unit'], e) for e in exp): break
                # ไม่เข้า group ไหนเลย → flag เป็น INFO (เบากว่า WARNING)
                o.append(f"#{it['seq']} \"{it['name'][:30]}\" — หน่วย={it['unit']} อาจไม่เหมาะ (ปกติใช้ {exp[:2]}) [soft]")
                break
    return o

def r_itm006(b,m,c):
    """v5.8j: ไม่ infer sale unit จาก spec dimension ในชื่อ
    Spec = ตัวเลข+หน่วยวัด (มม./ซม./ม./นิ้ว/กก./ลิตร) → IGNORE
    เช่น 'ท่อเหล็กกลม 6 ม.' → 6 ม. เป็น spec ไม่ใช่หน่วยขาย
    """
    # หน่วยที่ "เป็น spec" เสมอ ห้ามถือเป็น sale unit
    SPEC_ONLY_UNITS = {'มม.','ซม.','นิ้ว','mm','cm','inch','"','\'\'','กก.','ลิตร','มล.','cc','วัตต์','W','V','A'}
    # 'ม.' (เมตร) ก็เป็น spec ในบริบทเหล็ก/ท่อ/สาย — ห้าม flag
    SPEC_CONTEXT_KW = ['ท่อ','เหล็ก','สาย','ลวด','เชือก','แท่ง','เส้น']

    o = []
    for it in b['items']:
        if not it['unit']: continue
        hint = extract_unit_hint(it['name'])
        if not hint: continue
        # ถ้า hint เป็น spec-only unit → ข้าม
        if hint in SPEC_ONLY_UNITS: continue
        # v8.6 [FIX-ITM006b]: hint 'แผ่น' ในที่นี้มาจาก "มิติ NxN" เท่านั้น (ไม่ได้มาจากคำว่า 'แผ่น')
        #   → มิติหน้าตัด เช่น 60x30x10มม. ของ "เหล็กรูปตัวซี" (ขายเป็นเส้น) ถูกอนุมานเป็นแผ่นผิด ๆ
        #   เชื่อ 'แผ่น' เฉพาะเมื่อชื่อมีคำบ่งชี้ "แผ่น" จริง — ไม่งั้นเป็น FP หน้าตัดเหล็กรูปพรรณ
        if hint == 'แผ่น' and not any(k in it['name'] for k in
                ('แผ่น','เพลท','เพลต','plate','ไม้อัด','ยิปซั่ม','ยิปซัม','ฝ้า','กระเบื้อง','ไฟเบอร์','สังกะสี','เมทัลชีท')):
            continue
        # ถ้า hint = 'ม.' หรือ 'เมตร' และชื่อสินค้ามี context ของเหล็ก/ท่อ/สาย → ข้าม (เพราะเป็น spec ความยาว)
        # v8.6 [FIX-ITM006]: 'เมตร/ม.' เป็น "สเปกความยาว" ไม่ใช่หน่วยขาย เมื่อ
        #   (ก) ชื่อมี context เหล็ก/ท่อ/สาย (เดิม) หรือ
        #   (ข) ชื่อมีวลีบอกความยาวชัดเจน เช่น "ยาว 2 เมตร" / "ความยาว 5 เมตร" / "1 เมตร" (เลข+เมตร)
        #   → เลิกฟ้องผิดสินค้าที่บอกความยาวในชื่อแต่ขายเป็น เส้น/PCS. (เพลา/สลิง/ฯลฯ)
        if hint in {'เมตร','ม.'}:
            if any(kw in it['name'] for kw in SPEC_CONTEXT_KW):
                continue
            if re.search(r'(?:ยาว|ความยาว)?\s*\d+(?:\.\d+)?\s*(?:เมตร|ม\.)', it['name']):
                continue
        # เหลือเฉพาะกรณีที่ hint น่าจะเป็น sale unit จริง ๆ
        # v8.6 [FIX-ITM006c]: ยอมรับหน่วยพ้องความหมายด้วย (แกลลอน≈กระป๋อง) — สอดคล้องกับ ITM005/ITM015
        #   ฟ้องเฉพาะเมื่อ "ไม่ใช่ substring ของกัน" และ "คนละกลุ่มหน่วยพ้อง" จริง
        if (hint not in it['unit'] and it['unit'] not in hint
                and _unit_canon(hint) != _unit_canon(it['unit'])):
            o.append(f"#{it['seq']} \"{it['name'][:50]}\" — ในชื่อระบุ \"{hint}\" แต่หน่วย=\"{it['unit']}\"")
    return o

def r_itm007(b,m,c):
    """v8.0: skip whitelist/dict/keyword + รองรับ unit-only names + รหัสสินค้า"""
    if state._CAT_KEYWORDS is None: _build_cat_keywords()
    o = []
    for it in b['items']:
        name = it['name']
        if len(name) >= CFG['MIN_PRODUCT_NAME_LEN']: continue
        # dict + whitelist ถูกต้อง
        if name in CONSTRUCTION_DICT: continue
        if name in PYTHAINLP_WHITELIST: continue
        # มี keyword หมวด
        if any(kw in name for kw in state._CAT_KEYWORDS): continue
        # มี spec ตัวเลข+หน่วย
        if re.search(r'\d', name) and (
            re.search(r'\d+(?:[/x×.\-]\d+)?\s*(?:กก\.|ก\.ก\.|กรัม|ลิตร|มล\.|มม\.|ซม\.|ม\.|นิ้ว|W|kg|ml|cm|mm|VA|kW|kVA)', name, re.IGNORECASE)
            or re.search(r'\d+[/x×]\d+', name)
            or re.fullmatch(r'\d+(?:\.\d+)?\s*(?:mm|cm|m|kg|g|ml|l|W|V|A|kW|"|\'\')', name, re.IGNORECASE)
        ): continue
        # v8.0: รหัสสินค้า เช่น "A-123", "MC-7" — มีขีด+ตัวเลข = ถูกต้อง
        if re.search(r'[A-Za-z]\s*[-/]\s*\d+|\d+\s*[-/]\s*[A-Za-z]', name): continue
        # v8.6 [FIX-ITM007]: คำไทยล้วน 2-3 ตัวก็เป็นชื่อสินค้าจริงได้ (พรม/หิน/สี/ปูน...)
        #   ลดเกณฑ์ >=4 → >=2 เลิกฟ้องผิด "ชื่อสั้น"; ยังจับ 1 ตัวอักษร/อักขระปนขยะ/ชื่อที่ถูกตัดจริง
        if re.fullmatch(r'[ก-๙]+', name) and len(name) >= 2: continue
        # v8.0: มี CONSTRUCTION_DICT stem ใน name → ถูกต้อง
        if any(stem in name for stem in CONSTRUCTION_DICT if len(stem) >= 3): continue
        o.append(f"#{it['seq']}: ชื่อสั้นเกินไป '{name}' ({len(name)} ตัวอักษร)")
    return o

def r_itm008(b,m,c):
    """v5.8q PATCH 15: Price outlier — ตรวจเฉพาะเมื่อคอลัมน์เชื่อถือได้
    เงื่อนไขเข้มขึ้น: ถ้า qty×price≈amount ไม่ผ่านส่วนใหญ่ → คอลัมน์เพี้ยน → เงียบ
    ปล่อย ITM001 จับเรื่องตัวเลขแทน (ITM001 เช็คความสัมพันธ์ ไม่ต้องเดา)
    """
    if len(b['items']) < 5: return []   # PATCH 15: ต้องมี ≥5 รายการ (เดิม 3) — กันบิลเล็กเดาผิด

    # === Gate 1: qty×price ≈ amount ต้องผ่าน ≥80% ของรายการ ===
    # ถ้าไม่ผ่าน = detect คอลัมน์เพี้ยน → เงียบทั้งบิล
    ok = 0; total = 0
    for it in b['items']:
        if not (it['qty'] and it['price'] and it['amount']): continue
        if it['amount'] == 0: continue
        total += 1
        if abs(it['qty']*it['price'] - it['amount']) / abs(it['amount']) < 0.02:
            ok += 1
    if total < 3: return []                      # ข้อมูลครบไม่พอ → เงียบ
    if ok / total < 0.8: return []               # คอลัมน์ไม่น่าเชื่อถือ → เงียบ

    # === Gate 2: median ราคา ต้องสมเหตุผลเทียบ amount ===
    prices = [it['price'] for it in b['items'] if it['price'] and it['price'] > 0]
    amts = [it['amount'] for it in b['items'] if it['amount'] and it['amount'] > 0]
    if len(prices) < 5 or not amts: return []
    median = statistics.median(prices)
    median_amt = statistics.median(amts)
    if median == 0: return []
    # ราคา/หน่วย ไม่ควรสูงกว่ายอดรวมรายการ — ถ้าสูงกว่า = คอลัมน์เพี้ยน → เงียบ
    if median > median_amt: return []

    # === ตรวจ outlier จริง (ผ่าน gate ทั้งสองแล้ว = คอลัมน์เชื่อถือได้) ===
    o = []
    for it in b['items']:
        if not it['price'] or it['price'] <= 0: continue
        # ข้ามรายการที่ qty×price ไม่ตรง amount (รายการนั้นน่าสงสัยอยู่แล้ว ITM001 จับ)
        if it['qty'] and it['amount'] and it['amount'] != 0:
            if abs(it['qty']*it['price'] - it['amount']) / abs(it['amount']) >= 0.02:
                continue
        ratio = it['price'] / median
        if ratio > CFG['PRICE_OUTLIER_RATIO'] or ratio < (1 / CFG['PRICE_OUTLIER_RATIO']):
            o.append(f"#{it['seq']}: ราคา/หน่วย {it['price']:,.2f} ผิดปกติ (median={median:,.2f}, {ratio:.1f}×)")
    return o

def r_itm010(b,m,c):
    issues = []
    for it in b['items']:
        # v5.9 [FIX-ITM010]: ตรวจทั้ง name และ name_raw + บังคับ NFC
        #   กันกรณีตัวอักษรไทยไม่ normalize (สระ/วรรณยุกต์เรียงต่างรูป) แล้ว pattern match ไม่ติด
        hay = unicodedata.normalize('NFC',
                f"{it.get('name','') or ''} {it.get('name_raw','') or ''}")
        seen_pats = set()
        for pat, msg in THAI_TYPO_PATTERNS:
            if msg and re.search(pat, hay):
                if msg in seen_pats: continue
                seen_pats.add(msg)
                match = re.search(pat, hay)
                snippet = match.group(0) if match else ''
                issues.append(f"#{it['seq']}: {msg} [พบ: \"{snippet}\"] ใน \"{it['name'][:40]}\"")  # v9: เลิกใส่ลูกศรซ้ำ (msg มีคำแก้อยู่แล้ว) — เดิมโชว์ 'ผิด → ถูก → ผิด' สับสน
    return issues

def r_itm011(b,m,c):
    """v8.0: เพิ่ม PYTHAINLP_WHITELIST guard + confidence tier + ข้าม pure-number-suffix"""
    issues = []
    seen_global = set()  # dedup ข้ามรายการในบิลเดียวกัน
    for it in b['items']:
        # v8.0: ≥4 ตัวอักษร (เดิม ≥3) — ลด false positive คำสั้น
        thai_words = re.findall(r'[ก-๙][ก-๙์]{3,19}', it['name'])
        seen = set()
        for w in thai_words:
            if w in seen or w in seen_global: continue
            if w in CONSTRUCTION_DICT or w in PYTHAINLP_WHITELIST: continue
            seen.add(w); seen_global.add(w)
            # v8.0: ข้ามคำที่มีตัวเลขผสม — มักเป็นรหัส/spec ไม่ใช่ typo
            if re.search(r'\d', w): continue
            best, score = find_similar_in_thai_dict(w)
            if not best or w == best: continue
            # v8.0: Tier by confidence
            if score >= 95:
                tier = 'สะกดผิดชัดเจน'
            elif score >= 88:
                tier = 'อาจสะกดผิด'
            else:
                tier = 'ใกล้เคียง (ตรวจสอบ)'
            issues.append(f"#{it['seq']}: \"{w}\" ใกล้เคียง \"{best}\" (~{score}%) — {tier}")
    return issues

def r_vat001(b,m,c):
    if not b['items'] or b['subtotal'] is None: return []
    items_d = [_D(i['amount']) for i in b['items'] if i['amount'] is not None]
    if not items_d: return []
    s = sum(items_d, Decimal('0'))
    sub = _D(b['subtotal'])
    if sub is None: return []
    diff = abs(s - sub)
    tol = _vat_tolerance(sub)
    if diff > tol:
        return [f"ผลรวมรายการ={s:,.2f} ≠ subtotal={sub:,.2f} (ต่าง {diff:,.2f}, tol {tol:.2f})"]
    return []

def r_vat002(b,m,c):
    """tolerance 0.50 บาท (OBJ-0/ADR-005: ตรงกฎโดเมน VAT 7% เป๊ะ) + skip ถ้า vat ≤ 1.0 (เป็น rate ไม่ใช่ amount)"""
    if b['subtotal'] is None or b['vat'] is None: return []
    sub = _D(b['subtotal']); vat = _D(b['vat'])
    if sub is None or vat is None: return []
    # v5.8g: ถ้า vat ≤ 1.0 → มันคือ rate (เช่น 0.07) ไม่ใช่ amount → skip
    if abs(vat) <= Decimal('1.00'):
        return []
    expected = (sub * VAT_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    diff = abs(expected - vat)
    if diff < Decimal('0.50'):   # OBJ-0 (ADR-005): ยอมต่างเฉพาะเศษปัด "< 0.50" (ฟ้องเมื่อ ≥0.50; pin: test_vat002_tolerance.py)
        return []
    return [f"VAT ควร {expected:,.2f} แต่={vat:,.2f} (ต่าง {diff:,.2f})"]

def r_vat003(b,m,c):
    """v5.8L: tolerance 1 บาท
    ถ้า total ถูกต้อง (total-sub ≈ sub*7%) แต่ช่อง vat เก็บ rate 0.07
    → ไม่ flag เลย (ไม่ใช่ความผิดพลาดของเอกสาร แค่ parser อ่านช่อง vat ได้ rate)
    """
    if b['subtotal'] is None or b['total'] is None: return []
    sub = _D(b['subtotal']); vat = _D(b['vat']) or Decimal('0'); tot = _D(b['total'])
    if sub is None or tot is None: return []
    expected = (sub + vat).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    diff = abs(expected - tot)
    if diff < Decimal('1.00'):
        return []
    # ถ้า total ถูกต้องอยู่แล้ว (total-sub ≈ 7% ของ sub) → ช่อง vat แค่อ่านได้ rate, ไม่ใช่ error
    actual_vat = tot - sub
    expected_vat = (sub * VAT_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if abs(actual_vat - expected_vat) < Decimal('1.00'):
        return []  # total ถูก → ไม่ต้องแจ้งเตือน
    return [f"Total ควร {expected:,.2f} แต่={tot:,.2f} (ต่าง {diff:,.2f})"]

def r_vat004(b,m,c):
    """v5.8q PATCH 4A: round(value, 2) ก่อนเช็คทศนิยม
    vat=32678.0286 เป็น floating-point residue — Excel/UI แสดง 32678.03 อยู่แล้ว
    หลัง round 2 ตำแหน่ง ค่าที่แสดงจริงมี ≤2 ตำแหน่งเสมอ → ไม่ flag
    """
    o = []
    for f, v in [('subtotal',b['subtotal']),('vat',b['vat']),('total',b['total'])]:
        if v is None: continue
        try:
            fv = float(v)
        except (ValueError, TypeError):
            continue
        rounded = round(fv, CFG['ROUNDING_DECIMALS'])
        dec_str = f'{rounded:.{CFG["ROUNDING_DECIMALS"]}f}'.split('.')[-1].rstrip('0')
        if len(dec_str) > CFG['ROUNDING_DECIMALS']:
            o.append(f"{f}={v} > {CFG['ROUNDING_DECIMALS']} ตำแหน่ง")
    return o


# OBJ-MAINT: auto-export ทุกชื่อ (รวม helper _ และ import) → from-import * ได้ toolkit ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
