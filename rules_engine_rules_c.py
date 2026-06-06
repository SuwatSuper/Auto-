# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""rules_engine_rules_c — OBJ-MAINT: กลุ่มกฎ r_* (extract คัดลอกเป๊ะ). toolkit จาก rules_engine_base.
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

def r_vat005(b,m,c):
    try:
        issues = []
        sub = b.get('subtotal'); vat = b.get('vat'); tot = b.get('total')
        if sub is not None and isinstance(sub, (int, float)) and sub < 0:
            issues.append(f"subtotal ติดลบ: {sub:,.2f}")
        if vat is not None and isinstance(vat, (int, float)) and vat < 0:
            issues.append(f"VAT ติดลบ: {vat:,.2f}")
        if tot is not None and isinstance(tot, (int, float)) and tot < 0:
            issues.append(f"total ติดลบ: {tot:,.2f}")
        # total < subtotal (เป็นไปไม่ได้ ยกเว้นมีส่วนลดมากกว่า VAT)
        if (sub is not None and tot is not None
                and isinstance(sub, (int, float)) and isinstance(tot, (int, float))
                and tot > 0 and sub > 0 and tot < sub):
            issues.append(f"total ({tot:,.2f}) < subtotal ({sub:,.2f}) — เป็นไปไม่ได้ (discount > vat?)")
        # total=0 แต่ subtotal>0
        if (sub is not None and tot is not None
                and isinstance(sub, (int, float)) and isinstance(tot, (int, float))
                and tot == 0 and sub > 0):
            issues.append(f"total=0 ทั้งที่ subtotal={sub:,.2f}")
        return issues
    except Exception:
        return []

def r_vat006(b,m,c):
    # v5.8 FIX: เช็ก type ของ total/subtotal ให้เป็นตัวเลขก่อนคำนวณ
    # [F2/ADR-020] Decimal + ROUND_HALF_UP (Financial law: ห้าม float ในเส้นเงิน); type-gate/threshold/สตริง เดิมคงไว้ทุกตัว
    tot = b.get('total'); sub = b.get('subtotal')
    if not isinstance(tot, (int, float)) or not b['items']: return []
    items_sum = sum((_D(i['amount']) for i in b['items']
                     if isinstance(i.get('amount'), (int, float))), Decimal('0'))
    if items_sum <= 0: return []
    expected_inclusive = (_D(tot) / Decimal('1.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if (abs(items_sum - expected_inclusive) < Decimal('1') and isinstance(sub, (int, float))
        and abs(items_sum - _D(sub)) > Decimal('1')):
        return [f"อาจเป็น VAT Included: items_sum={items_sum:,.2f} = total÷1.07={expected_inclusive:,.2f}"]
    return []

def r_vat007(b,m,c):
    # v5.8 FIX: เช็ก type subtotal/vat ให้เป็นตัวเลขก่อนคำนวณ
    # [F2/ADR-020] Decimal + ROUND_HALF_UP (Financial law); type-gate/threshold/สตริง เดิมคงไว้ทุกตัว
    sub = b.get('subtotal'); vat = b.get('vat')
    if not b['items'] or not isinstance(sub, (int, float)) or not isinstance(vat, (int, float)):
        return []
    if sub == 0: return []
    items_sum = sum((_D(i['amount']) for i in b['items']
                     if isinstance(i.get('amount'), (int, float))), Decimal('0'))
    sub_d = _D(sub); vat_d = _D(vat)
    if items_sum <= sub_d: return []
    discount = items_sum - sub_d
    exp_vat_post = (sub_d * Decimal('0.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    exp_vat_pre = (items_sum * Decimal('0.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if abs(vat_d - exp_vat_pre) < Decimal('0.5') and abs(vat_d - exp_vat_post) > Decimal('0.5'):
        return [f"VAT คำนวณก่อนหักส่วนลด! discount={discount:,.2f}, ควร VAT={exp_vat_post:,.2f} แต่={vat:,.2f}"]
    return []

def r_cmp005(b, m, c):
    """Company suffix consistency — ตรวจ suffix นิติบุคคล"""
    try:
        name = normalize_company_name(b.get('company', ''))
        if not name:
            return []
        issues = []
        # บริษัท ต้องมี จำกัด
        if 'บริษัท' in name and 'จำกัด' not in name:
            issues.append(f"ชื่อมี 'บริษัท' แต่ไม่มี 'จำกัด': {name[:50]}")
        # บมจ ต้องมี มหาชน
        if ('บมจ' in name or 'บมจ.' in name) and 'มหาชน' not in name:
            issues.append(f"ชื่อมี 'บมจ' แต่ไม่มี 'มหาชน': {name[:50]}")
        # หจก ไม่ควรลงท้ายด้วย 'จำกัด' ตามรูปแบบ หจก.
        if ('หจก' in name or 'หจก.' in name) and name.rstrip().endswith('จำกัด') and 'มหาชน' not in name:
            issues.append(f"ชื่อมี 'หจก' แต่ลงท้ายด้วย 'จำกัด' เฉยๆ (ควรเป็น หจก. / ห้างหุ้นส่วนจำกัด): {name[:50]}")
        return issues
    except Exception:
        return []

def r_addr004(b, m, c):
    """Bangkok vs Province address format check"""
    try:
        addr = normalize_text(b.get('address', ''))
        if not addr:
            return []
        is_bkk = 'กรุงเทพ' in addr or 'กทม' in addr
        # FIX (v8.4): เช็กแบบ substring เดิม → "เขตอุตสาหกรรม/เขตประกอบการ/แขวงการทาง" (ที่อยู่ต่างจังหวัด) โดนฟ้องผิด
        #   กันคำประสมที่ไม่ใช่ "เขต/แขวง" แบบเขตปกครองกรุงเทพ
        has_kwaeng = bool(re.search(r'แขวง(?!การทาง)', addr))
        has_khet = bool(re.search(r'เขต(?!\s*(?:อุตสาหกรรม|ประกอบการ|ปลอดอากร|ปลอดภาษี|ส่งเสริม|พัฒนา|เศรษฐกิจ|การค้า|ปกครอง|ป่าสงวน|ภาษี))', addr))
        has_tambon = 'ตำบล' in addr
        has_amphoe = 'อำเภอ' in addr
        issues = []
        if is_bkk:
            if has_tambon or has_amphoe:
                issues.append("ที่อยู่กรุงเทพฯ ไม่ควรใช้ ตำบล/อำเภอ (ควรใช้ แขวง/เขต)")
        else:
            # ต่างจังหวัด — ควรไม่ใช้ แขวง/เขต
            if (has_kwaeng or has_khet) and not is_bkk:
                issues.append("ที่อยู่ต่างจังหวัด ไม่ควรใช้ แขวง/เขต (ควรใช้ ตำบล/อำเภอ)")
        return issues
    except Exception:
        return []

def r_addr005(b, m, c):
    """Postal code validation"""
    try:
        addr = normalize_text(b.get('address', ''))
        if not addr:
            return []
        # FIX (v8.4): \b ใช้กับภาษาไทยไม่ติด (ก-๙ เป็น word char) → รหัสที่ติดตัวอักษรไทยจะหาไม่เจอ
        #   ใช้ lookaround เช็ก "ไม่ติดตัวเลขอื่น" แทน → เจอเลข 5 หลักเดี่ยวๆ แม้ติดอักษรไทย และไม่จับ 5 หลักกลางเลขยาว
        match = re.search(r'(?<!\d)(\d{5})(?!\d)', addr)
        if not match:
            return ['ไม่พบรหัสไปรษณีย์ 5 หลักในที่อยู่']
        code = int(match.group(1))
        if code < 10000 or code > 99999:
            return [f"รหัสไปรษณีย์ {code} ไม่อยู่ในช่วงที่ถูกต้อง (10000-99999)"]
        is_bkk = 'กรุงเทพ' in addr or 'กทม' in addr
        if is_bkk and not (10000 <= code <= 10999):
            return [f"รหัสไปรษณีย์ {code} ไม่ตรงกับกรุงเทพฯ (ควร 10000-10999)"]
        return []
    except Exception:
        return []

def r_tax007(b, m, c):
    """Tax ID first digit — entity type cross-check (ประเทศไทย)
    หลักแรกของเลข 13 หลัก:
      0 = นิติบุคคล (บริษัท/ห้างหุ้นส่วน ที่จดทะเบียน DBD) — ปกติของบริษัท
      1-8 = บุคคลธรรมดา (เลขบัตรประชาชน)
      9 = นิติบุคคลที่ไม่ได้จดกับ DBD บางประเภท / อื่นๆ
    ไม่ฟ้องหลักแรก '0' (เป็นค่าปกติของบริษัทไทย)
    ฟ้องเฉพาะ cross-check: ชื่อเป็นนิติบุคคล แต่เลขภาษีเป็นช่วงบุคคลธรรมดา (1-8)
    """
    try:
        t = clean_tax_id(b.get('tax_id', ''))
        if len(t) != 13 or not t.isdigit():
            return []
        first = t[0]
        name = normalize_company_name(b.get('company', ''))
        is_company = any(kw in name for kw in
                         ['บริษัท', 'บมจ', 'บจก', 'หจก', 'ห้างหุ้นส่วน', 'มหาชน'])
        # นิติบุคคล (บริษัท/หจก.) ควรขึ้นต้นด้วย '0' — ถ้าขึ้นต้น 1-8 = เลขบุคคลธรรมดา → น่าสงสัย
        if is_company and first in '12345678':
            return [f"ชื่อเป็นนิติบุคคล แต่เลขภาษีขึ้นต้นด้วย '{first}' "
                    f"(ช่วงบุคคลธรรมดา ปกตินิติบุคคลขึ้นต้น '0'): {t}"]
        return []
    except Exception:
        return []

def r_br003(b, m, c):
    """Branch consistency within file — ตรวจสาขาสม่ำเสมอในไฟล์"""
    try:
        all_bills = c.get('all_bills_for_iv_check', [])
        if not all_bills:
            return []
        this_tax = clean_tax_id(b.get('tax_id', ''))
        if not this_tax:
            return []
        this_branch = b.get('branch_no') or ''
        same_company_branches = set()
        for ob in all_bills:
            if ob is b:
                continue
            if clean_tax_id(ob.get('tax_id', '')) != this_tax:
                continue
            br = ob.get('branch_no') or ''
            same_company_branches.add(br)
        if not same_company_branches:
            return []
        # ถ้ามีทั้ง '00000' และ non-'00000' → WARNING
        has_hq = '00000' in same_company_branches or this_branch == '00000'
        has_branch = any(x != '00000' and x != '' for x in same_company_branches) or (this_branch and this_branch != '00000')
        if has_hq and has_branch:
            all_branches = same_company_branches | {this_branch}
            return [f"บริษัทเดียวกันใช้ทั้งสำนักงานใหญ่ (00000) และสาขาอื่นในไฟล์เดียวกัน: {sorted(all_branches)[:5]}"]
        return []
    except Exception:
        return []

def r_doc003(b, m, c):
    """Duplicate IV number — ฟ้อง "ใบซ้ำจริง" เท่านั้น: ผู้ขายเดียวกัน + เลข IV เดียวกัน + วันที่เดียวกัน
    FIX (v8.4): เดิมไม่เช็ควันที่ → ผู้ขายที่รีเซ็ตเลขใบทุกงวด/ทุกปี (เช่น INV-001 ปี 2025 vs 2026)
                ถูกฟ้องผิดว่าซ้ำ ทั้งที่เป็นคนละใบ. เพิ่มเงื่อนไขวันที่ตรงกัน → ฟ้องให้ตรงกับใบซ้ำของจริง
    """
    try:
        all_bills = c.get('all_bills_for_iv_check', [])
        if not all_bills:
            return []
        this_iv = b.get('iv_number', '')
        if not this_iv:
            return []
        this_tax = clean_tax_id(b.get('tax_id', ''))

        def _dkey(x):
            d = x.get('iv_date')
            return d.date() if hasattr(d, 'date') else d   # เทียบเฉพาะ "วัน" (None==None ถือว่าตรง)

        this_date = _dkey(b)
        dups = []
        for ob in all_bills:
            if ob is b:
                continue
            # v8.6 [FIX-DOC003]: กฎนี้ชื่อ "IV ซ้ำในไฟล์" → จำกัดที่ "ไฟล์เดียวกัน" เท่านั้น
            #   เดิมสแกนข้ามไฟล์ → ไฟล์สำเนา (เช่น HSH_69_05 vs HSH_69_051 เนื้อหาเดียวกัน)
            #   ทำให้ทุก IV ที่ใช้ร่วมถูกฟ้องซ้ำจำนวนมาก. บิลซ้ำข้ามไฟล์ยังถูกจับโดยชีต "บิลซ้ำ"
            #   ของ clean report (group IV+ยอด+บริษัท) → ไม่เสียสัญญาณจริง
            if ob.get('file') != b.get('file'):
                continue
            if ob.get('iv_number') != this_iv:
                continue
            if clean_tax_id(ob.get('tax_id', '')) != this_tax:
                continue
            if _dkey(ob) != this_date:        # เลขเดียวกันแต่คนละวัน = คนละใบ (รีเซ็ตเลขข้ามงวด) → ไม่ฟ้อง
                continue
            dups.append(ob.get('file', '?'))
        if dups:
            ds = this_date.strftime('%d/%m/%Y') if hasattr(this_date, 'strftime') else 'ไม่ระบุวันที่'
            return [f"IV '{this_iv}' ลงวันที่ {ds} ซ้ำกับบิลอื่น (ผู้ขาย+เลข+วันที่ตรงกัน): {dups[:3]}"]
        return []
    except Exception:
        return []

def r_dt004(b, m, c):
    """Date out of reasonable range — ตรวจปี/เดือน/วันนอกช่วงสมเหตุสมผล"""
    try:
        if not b['iv_date']:
            return []
        d = b['iv_date']
        issues = []
        yr = d.year
        # FIX (v8.3): iv_date ถูกแปลงเป็น ค.ศ. แล้ว (parser ลบ 543 ออกที่จุด normalize) → ต้องเทียบด้วยเกณฑ์ "ค.ศ." ไม่ใช่ "พ.ศ."
        #   พ.ศ. 2555 = ค.ศ. 2012 (เก่าสุดที่ยอมรับ) | พ.ศ. 2600 = ค.ศ. 2057 (ใหม่สุดก่อนถือว่าผิด/digit สลับ)
        #   บั๊กเดิม: เทียบ yr (ค.ศ. เช่น 2026) กับ 2555 (พ.ศ.) → 2026 < 2555 จริงเสมอ → ฟ้องผิดทุกใบปี 2026
        if yr > 2057:
            issues.append(f"ปี ค.ศ. {yr} (พ.ศ. {yr+543}) เกินช่วงปกติ (> พ.ศ. 2600) — น่าจะ digit สลับ")
        elif yr < 2012:
            issues.append(f"ปี ค.ศ. {yr} (พ.ศ. {yr+543}) ก่อน พ.ศ. 2555 — ตรวจสอบ")
        # [L2] ลบเช็ค mo==0/day==0/day>31 — dead code: datetime ให้ month∈1-12, day∈1-31 เสมอ
        #   (ค่านอกช่วงสร้าง datetime ไม่ได้ตั้งแต่ต้น) จึงยิงไม่ได้ → ลบแล้วไม่กระทบผลตรวจ.
        return issues
    except Exception:
        return []

def r_itm016(b, m, c):
    """Duplicate line items — รายการซ้ำในบิล"""
    try:
        if not b['items']:
            return []
        seen = {}
        dupes = []
        for it in b['items']:
            key = (
                normalize_text(it.get('name', '') or ''),
                (it.get('unit') or '').strip(),
                it.get('price'),
            )
            if key[0] == '':
                continue
            if key in seen:
                dupes.append(f"#{seen[key]} และ #{it['seq']}")
            else:
                seen[key] = it['seq']
        if dupes:
            return [f"รายการซ้ำ: {'; '.join(dupes[:5])}"]
        return []
    except Exception:
        return []

def r_itm018(b, m, c):
    """Suspicious quantity/amount — จำนวน/ยอดผิดปกติ"""
    try:
        if not b['items']:
            return []
        issues = []
        LARGE_ROUND = {99999, 999999}   # FIX (v8.4): ตัด 10000/100000 ออก — เป็นจำนวนซื้อจริงที่พบบ่อย ไม่ใช่ค่า placeholder
        for it in b['items']:
            qty = it.get('qty')
            price = it.get('price')
            amount = it.get('amount')
            if qty is None or qty == '':
                continue
            try:
                qty_f = float(qty)
                price_f = float(price) if price is not None else None
                amount_f = float(amount) if amount is not None else None
            except (TypeError, ValueError):
                continue
            # qty=0 แต่ amount != 0
            if qty_f == 0 and amount_f is not None and amount_f != 0:
                issues.append(f"#{it['seq']}: qty=0 แต่ amount={amount_f:,.2f}")
                continue
            # qty>0 แต่ amount=0 ทั้งที่ price>0
            if qty_f > 0 and amount_f == 0 and price_f is not None and price_f > 0:
                issues.append(f"#{it['seq']}: qty={qty_f} price={price_f:,.2f} แต่ amount=0")
                continue
            # qty เป็นตัวเลขกลมใหญ่ผิดปกติ
            if qty_f in LARGE_ROUND and price_f is not None and price_f > 0:
                issues.append(f"#{it['seq']}: qty={qty_f:.0f} กลมใหญ่ผิดปกติ (ตรวจสอบ)")
                continue
            # amount/qty != price (เมื่อไม่มี discount)
            # [F2/ADR-020] เลขเงิน (qty×price) คำนวณด้วย Decimal+ROUND_HALF_UP; gate/การแสดงผล (qty_f/price_f/amount_f) คงเดิมเป๊ะ
            if qty_f > 0 and price_f is not None and amount_f is not None and price_f > 0:
                expected = (_D(qty) * _D(price)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                amount_d = _D(amount)
                if abs(expected - amount_d) > Decimal('1'):
                    pct = abs(expected - amount_d) / expected * Decimal('100') if expected != 0 else Decimal('0')
                    # skip ถ้าเหมือน discount 1-50%
                    if amount_d < expected and Decimal('1') <= pct <= Decimal('50'):
                        continue
                    issues.append(f"#{it['seq']}: {qty_f}×{price_f}={expected:.2f} ≠ amount={amount_f:.2f}")
        return issues
    except Exception:
        return []

def r_vat008(b, m, c):
    """VAT zero check — ตรวจ VAT=0 ทั้งที่มียอดสูง"""
    try:
        vat = b.get('vat')
        total = b.get('total')
        subtotal = b.get('subtotal')
        items = b.get('items', [])
        if not items:
            return []
        if vat is None:
            return []
        try:
            vat_f = float(vat)
            total_f = float(total) if total is not None else 0
            sub_f = float(subtotal) if subtotal is not None else 0
        except (TypeError, ValueError):
            return []
        if vat_f != 0:
            return []
        if total_f <= 10000:
            return []
        # ถ้า subtotal ≈ total แสดงว่ายกเว้น VAT จริง
        if sub_f > 0 and abs(sub_f - total_f) < 1:
            return []
        return ["VAT เป็น 0 ทั้งที่มียอด — ตรวจสอบว่าได้รับยกเว้น VAT จริงหรือไม่"]
    except Exception:
        return []

def r_vat009(b, m, c):
    """Subtotal zero/near-zero with items"""
    try:
        items = b.get('items', [])
        subtotal = b.get('subtotal')
        total = b.get('total')
        if not items:
            return []
        if subtotal is None:
            if total is not None:
                return ["ไม่มี subtotal (มี total แต่ไม่มี subtotal)"]
            return []
        try:
            sub_f = float(subtotal)
        except (TypeError, ValueError):
            return []
        if sub_f == 0:
            return [f"มีรายการสินค้าแต่ subtotal=0"]
        return []
    except Exception:
        return []

def r_vat010(b, m, c):
    """v9 [INTEGRITY]: ยอด VAT/รวม/ก่อน VAT ที่ "ระบบคำนวณเอง" (ไม่ได้อ่านจากเอกสาร)
    ต้องไม่ถูกถือว่าผ่าน VAT001/002/003 เงียบ ๆ — เพราะกฎจะตรวจค่าที่ระบบเพิ่งคำนวณ
    = false-clean (ยืนยัน VAT ถูกทั้งที่ไม่เคยอ่าน VAT จากบิล)
    Business reason: สรรพากร/ผู้ตรวจดู "ยอด VAT ที่พิมพ์บนใบกำกับภาษี" ไม่ใช่ยอดที่เรา
      คำนวณย้อนจาก subtotal*7%. ถ้า OCR ไม่ติดช่อง VAT/ยอดรวม ต้องส่งให้คนตรวจก่อน sign-off
      (ตรงกับนโยบาย OCR: confidence ต่ำ -> คืน UNKNOWN, ยอม false-negative ดีกว่า false-positive)
    """
    src = b.get('amount_source') or {}
    derived = [k for k in ('subtotal', 'vat', 'total') if src.get(k) in ('derived', 'item_sum')]
    if not derived:
        return []   # ทุกยอดอ่านจากเอกสารจริง -> VAT001/002/003 ตรวจได้จริง ไม่ต้องเตือน
    th = {'subtotal': 'ยอดก่อน VAT', 'vat': 'ภาษี VAT', 'total': 'ยอดรวม'}
    how = {'derived': 'คำนวณจากอัตรา 7%/อัตลักษณ์', 'item_sum': 'รวมจากรายการสินค้า'}
    parts = '; '.join(f"{th[k]} ({how[src[k]]})" for k in derived)
    return [f"VAT ยังไม่ได้ตรวจกับค่าที่พิมพ์จริง - ยอดเหล่านี้ระบบเติมเอง: {parts}. "
            f"ต้องตรวจยอด VAT บนเอกสารด้วยตาก่อนยืนยัน"]


# OBJ-MAINT: auto-export ทุกชื่อ (รวม helper _ และ import) → from-import * ได้ toolkit ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
