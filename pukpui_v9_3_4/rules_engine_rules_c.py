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
    _unit_canon, _vat_tolerance, VAT_RATE, add_issue, clean_tax_id,
    datetime, defaultdict, extract_branch, extract_unit_hint,
    find_similar_in_thai_dict, fuzz, has_hidden_chars, json,
    log_system_issue, match_company, normalize_company_name, normalize_text,
    os, parse_date_any, predict_category, pythainlp_spell_check,
    re, remove_branch_suffix, safe, state,
    statistics, timedelta, to_conf01, unicodedata,
    validate_company_prefix,
)  # noqa: F401  (re-export ขึ้น chain — หลายชื่อไม่ได้ใช้ภายในไฟล์นี้)
from thai_postal import postal_province_mismatch  # [B2] ตาราง prefix ไปรษณีย์→จังหวัด (data-driven)
from core_utils import iv_digits_garbage, iv_amount_fragment  # [D1/D2] เลขใบกำกับขยะ (single-source ใช้ร่วม parser guard)

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

def _safe_items_sum(b):
    """[ADR-109] ผลรวม amount ของรายการ แบบกัน bool/None/non-finite — ต่อยอด ADR-069 (C-1) โดยตรง.
    ADR-069 กัน inf/NaN/bool ให้ tot/sub/vat แล้ว แต่ "ตกหล่น" ที่ items aggregation:
      • bool ⊂ int → ผ่าน isinstance((int,float)) → _D(bool)=None
      • เซลล์ amount = inf/NaN (เช่น '1e400') → _D()=None
    เดิม `sum(_D(...) ...)` เจอ None → Decimal+None = TypeError (ไม่ใช่ ArithmeticError) หลุด except ที่
    ห่อแค่ quantize → run_rules กลืนเป็น SYS-VAT00x → กฎ CRITICAL VAT007 (ตรวจ VAT ก่อนหักส่วนลด) ถูกข้าม
    เงียบ = false-negative. กัน bool + None ก่อนบวก (เลีย type-gate ที่ tot/sub/vat ทำถูกแล้ว).
    golden-neutral: corpus ทุก amount เป็น number finite ไม่ใช่ bool → ลำดับ/ผลบวกเท่าเดิมเป๊ะ
    (พิสูจน์ golden_master ก่อน/หลัง = 31013a31). ดู INVARIANTS/DECISIONS.md §ADR-109."""
    s = Decimal('0')
    for i in b['items']:
        a = i.get('amount')
        if isinstance(a, (int, float)) and not isinstance(a, bool):
            d = _D(a)
            if d is not None:
                s += d
    return s

def r_vat006(b,m,c):
    # v5.8 FIX: เช็ก type ของ total/subtotal ให้เป็นตัวเลขก่อนคำนวณ
    # [F2/ADR-020] Decimal + ROUND_HALF_UP (Financial law: ห้าม float ในเส้นเงิน); type-gate/threshold/สตริง เดิมคงไว้ทุกตัว
    tot = b.get('total'); sub = b.get('subtotal')
    # [BUGFIX recheck] กัน bool (bool ⊂ int) — _D(bool)=None → None/Decimal ครัช → กฎถูก skip เงียบ
    if not isinstance(tot, (int, float)) or isinstance(tot, bool) or not b.get('items'): return []
    items_sum = _safe_items_sum(b)   # [ADR-109] กัน bool/None/non-finite item amount → ครัช → กฎข้ามเงียบ
    if items_sum <= 0: return []
    # [C-1/ADR-069] เงิน non-finite (inf/NaN จากเซลล์ "inf"/"1e400"/เลขยาว ≥309 หลัก ผ่านเส้น _tor_scan_*)
    #   → _D()=None → เดิม None/Decimal เป็น TypeError (ไม่ใช่ ArithmeticError) หลุด except → run_rules กลืน
    #   เป็น SYS-VAT006 → กฎถูกข้ามเงียบ (false-negative). กัน None ก่อนคำนวณ (เลียน VAT001 ที่ทำถูกอยู่แล้ว).
    tot_d = _D(tot)
    if tot_d is None:
        return []
    try:                                              # [L1] ห่อ quantize เหมือน r_itm001/018: ยอด >10²⁷ → InvalidOperation
        expected_inclusive = (tot_d / Decimal('1.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except ArithmeticError:
        return []
    sub_d = _D(sub) if isinstance(sub, (int, float)) and not isinstance(sub, bool) else None
    if (abs(items_sum - expected_inclusive) < Decimal('1') and sub_d is not None
        and abs(items_sum - sub_d) > Decimal('1')):
        return [f"อาจเป็น VAT Included: items_sum={items_sum:,.2f} = total÷1.07={expected_inclusive:,.2f}"]
    return []

def r_vat007(b,m,c):
    # v5.8 FIX: เช็ก type subtotal/vat ให้เป็นตัวเลขก่อนคำนวณ
    # [F2/ADR-020] Decimal + ROUND_HALF_UP (Financial law); type-gate/threshold/สตริง เดิมคงไว้ทุกตัว
    sub = b.get('subtotal'); vat = b.get('vat')
    # [BUGFIX recheck] กัน bool (bool ⊂ int) — _D(bool)=None → เปรียบเทียบ Decimal/None ครัช → skip เงียบ
    if (not b.get('items') or not isinstance(sub, (int, float)) or isinstance(sub, bool)
            or not isinstance(vat, (int, float)) or isinstance(vat, bool)):
        return []
    if sub == 0: return []
    items_sum = _safe_items_sum(b)   # [ADR-109] กัน bool/None/non-finite item amount → ครัช → กฎข้ามเงียบ
    sub_d = _D(sub); vat_d = _D(vat)
    # [C-1/ADR-069] เงิน non-finite → _D=None → เดิม Decimal<=None เป็น TypeError หลุด except → VAT007 (CRITICAL)
    #   ถูกข้ามเงียบ (false-negative). กัน None ก่อนเทียบ.
    if sub_d is None or vat_d is None:
        return []
    if items_sum <= sub_d: return []
    discount = items_sum - sub_d
    try:                                              # [L1] ห่อ quantize: ยอด >10²⁷ → InvalidOperation (⊂ ArithmeticError)
        exp_vat_post = (sub_d * VAT_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        exp_vat_pre = (items_sum * VAT_RATE).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except ArithmeticError:
        return []
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
        # [BUGFIX recheck #6] ใช้เลข 5 หลัก "ตัวท้ายสุด" เป็นไปรษณีย์ (สอดคล้อง _addr_parse_smart ที่ใช้ zips[-1])
        #   เดิม re.search คว้าตัวแรก → เลขบ้าน/ห้อง 5 หลักที่นำหน้าไปรษณีย์ถูกตีเป็นไปรษณีย์ → false positive
        # [L·ADDR005/ADR-071] ตัดส่วน "เบอร์โทร/แฟกซ์" ก่อนหาไปรษณีย์ — กันเลข 5 หลักท้าย (เช่น "โทร 99999")
        #   ถูกเลือกเป็นไปรษณีย์แทนเลขจริง (zips[-1]). ไม่มี keyword โทร → ใช้ทั้งที่อยู่เหมือนเดิม (golden-neutral).
        addr_for_zip = re.split(r'โทร|โทรศัพท์|tel|fax|แฟกซ์|มือถือ', addr, maxsplit=1, flags=re.IGNORECASE)[0]
        zips = re.findall(r'(?<!\d)(\d{5})(?!\d)', addr_for_zip)
        if not zips:
            return ['ไม่พบรหัสไปรษณีย์ 5 หลักในที่อยู่']
        code = int(zips[-1])
        if code < 10000 or code > 99999:
            return [f"รหัสไปรษณีย์ {code} ไม่อยู่ในช่วงที่ถูกต้อง (10000-99999)"]
        is_bkk = 'กรุงเทพ' in addr or 'กทม' in addr
        if is_bkk and not (10000 <= code <= 10999):
            return [f"รหัสไปรษณีย์ {code} ไม่ตรงกับกรุงเทพฯ (ควร 10000-10999)"]
        return []
    except Exception:
        return []

def r_addr006(b, m, c):
    """[B2] รหัสไปรษณีย์ ↔ จังหวัด ไม่สอดคล้อง (generalize ทุกจังหวัด, ไม่พึ่ง master).

    ฟอร์แมตถูก ≠ ตรงพื้นที่: เช่นที่อยู่เขียน 'เชียงใหม่' แต่ไปรษณีย์ 10250 (กรุงเทพ). ใช้ตาราง
    prefix→จังหวัด (thai_postal — derive จากข้อมูลจริง 77 จังหวัด). ฟ้องเฉพาะ "ขัดกันชัด" =
    ไม่มีไปรษณีย์ใดในที่อยู่ prefix ตรงจังหวัดที่ระบุเลย. conservative: ดึงจังหวัด/ไปรษณีย์ไม่ได้ → เงียบ.
    ไม่ทับ ADDR005: เว้นกรุงเทพฯ (ADDR005 ดูแลช่วง 10xxx แล้ว).
    """
    try:
        res = postal_province_mismatch(normalize_text(b.get('address', '')))
        if not res:
            return []
        province, postal, prefix = res
        return [f"รหัสไปรษณีย์ {postal} (ขึ้นต้น {prefix}) ไม่สอดคล้องจังหวัด '{province}' ในที่อยู่ "
                "— ตรวจที่อยู่/รหัสไปรษณีย์ว่าตรงพื้นที่จริง"]
    except Exception:
        return []

# ── [B1] TAX008 — เลขภาษีเดียวกันแต่ชื่อบริษัทต่างกันจริง (cross-bill, ไม่พึ่ง master) ───────────
_TAX008_BRANCH_RE = re.compile(r'\(?\s*(?:สำนักงานใหญ่|สนญ\.?|สาขา\S*)\s*\)?')

def _tax008_name(s):
    """normalize ชื่อบริษัท + ตัด marker สาขา/สนญ. — ต่างแค่ 'สาขา/สำนักงานใหญ่' = บริษัทเดียวกัน."""
    s = _TAX008_BRANCH_RE.sub('', normalize_text(s))
    return re.sub(r'\s+', ' ', s).strip()

def _tax008_same(a, b):
    """ชื่อเดียวกันไหม — เกณฑ์แนวเดียว CMP001 (exact / substring ย่อ-เต็ม / fuzzy token_sort ≥ 85).
    ขาดชื่อฝั่งใด → ถือว่า 'เดียวกัน' (conservative: ไม่ฟ้องเมื่อข้อมูลไม่พอ)."""
    if not a or not b:
        return True
    if a == b or a in b or b in a:
        return True
    return fuzz.token_sort_ratio(a, b) >= 85

def r_tax008(b, m, c):
    """[B1] เลขภาษีเดียวกันแต่ชื่อบริษัทต่างกันจริง ข้ามบิล (internal consistency — ไม่พึ่ง master).

    จับคลาส เจ.อาร์./ฉีหยวน: เลขภาษี 13 หลักตัวเดียวถูกใช้กับ 'คนละบริษัทกันจริง' = สัญญาณสวมเลข/ปลอม.
    conservative (false-negative ดีกว่า false-positive): ฟ้องเฉพาะชื่อที่ "ต่างกันชัด" — ต่างแค่
    เว้นวรรค/(สำนักงานใหญ่)/สาขา/ลำดับคำ/ย่อ-เต็ม = ชื่อเดียวกัน ไม่ฟ้อง (เกณฑ์แนว CMP001).
    เงียบเมื่อ: ไม่มี all_bills_ref / tax ไม่ครบ 13 หลัก / บิลไม่มีชื่อบริษัท.
    """
    all_bills = c.get('all_bills_for_iv_check', [])
    if not all_bills:
        return []
    this_tax = clean_tax_id(b.get('tax_id', ''))
    if len(this_tax) != 13 or not this_tax.isdigit():       # เชื่อว่า "เลขเดียวกัน" เฉพาะเลขที่สมบูรณ์
        return []
    this_name = _tax008_name(b.get('company', ''))
    if not this_name:
        return []
    conflicts = []
    # [PERF/ADR-103] เดินเฉพาะกลุ่มเลขภาษีเดียวกัน (ดัชนี) แทน scan all_bills ทั้งหมด — กลุ่มเรียงเดิม → ผลเท่าเดิม
    scan = c.get('xbill_tax_index', {}).get(this_tax, all_bills)
    for ob in scan:
        if ob is b or clean_tax_id(ob.get('tax_id', '')) != this_tax:
            continue
        nm = _tax008_name(ob.get('company', ''))
        if nm and not _tax008_same(this_name, nm) and nm not in conflicts:
            conflicts.append(nm)
    if not conflicts:
        return []
    others = '; '.join(sorted(conflicts)[:3])
    return [f"เลขภาษี {this_tax} ใช้กับชื่อบริษัทต่างกัน: บิลนี้ '{b.get('company','')}' | อื่น '{others}' "
            "— ตรวจการสวมเลข/เลขปลอม"]

# ── [BS-3] TAX009 — ชื่อบริษัทเดียวกัน แต่เลขภาษีต่างกัน ข้ามบิล (mirror TAX008 ทิศกลับ; ไม่พึ่ง master) ──
#   cache ดัชนี ชื่อ-normalize → {เลขภาษี: [บิล]} ต่อ batch (mirror _XBILL_IDX_CACHE ใน rules_engine).
#   fingerprint = (id,len,id หัว,id ท้าย) กัน id-reuse ชนกัน ; เรียกซ้ำต่อบิล = O(1).
_BS3_NAME_IDX = {'fp': None, 'idx': {}}


def _bs3_name_index(all_bills):
    """ดัชนี _tax008_name(ชื่อ) → {เลขภาษี13หลัก: [บิล]} — เก็บเฉพาะบิลที่เลขภาษีครบ 13 หลัก (conservative)."""
    fp = (id(all_bills), len(all_bills), id(all_bills[0]), id(all_bills[-1])) if all_bills else None
    if _BS3_NAME_IDX['fp'] != fp:
        idx = {}
        for ob in all_bills:
            nm = _tax008_name(ob.get('company', ''))
            t = clean_tax_id(ob.get('tax_id', ''))
            if nm and len(t) == 13 and t.isdigit():
                idx.setdefault(nm, {}).setdefault(t, []).append(ob)
        _BS3_NAME_IDX.update(fp=fp, idx=idx)
    return _BS3_NAME_IDX['idx']


def r_tax009(b, m, c):
    """[BS-3] ชื่อบริษัทเดียวกัน (ตรงชัด) แต่เลขภาษี 13 หลัก "ต่างกัน" ข้ามบิล — ผู้ขายรายเดียว
    พิมพ์เลขภาษีผิดบางใบ. mirror ของ TAX008 (เลขเดียว/ชื่อต่าง) ในทิศกลับ (ชื่อเดียว/เลขต่าง).
    conservative (false-negative ดีกว่า false-positive): ฟ้องเฉพาะชื่อ normalize ตรงกันเป๊ะ
    (ตัด marker สาขา/สนญ./ยุบเว้นวรรค) + เลขครบ 13 หลักทุกฝั่ง → "เลขใดเลขหนึ่งน่าจะพิมพ์ผิด".
    เงียบเมื่อ: ไม่มี all_bills_ref / เลขไม่ครบ 13 หลัก / ไม่มีชื่อ / ชื่อนี้ใช้เลขเดียว.
    """
    all_bills = c.get('all_bills_for_iv_check', [])
    if not all_bills:
        return []
    this_tax = clean_tax_id(b.get('tax_id', ''))
    if len(this_tax) != 13 or not this_tax.isdigit():       # เชื่อ "เลขต่างกัน" เฉพาะเลขที่สมบูรณ์
        return []
    this_name = _tax008_name(b.get('company', ''))
    if not this_name:
        return []
    by_tax = _bs3_name_index(all_bills).get(this_name, {})
    others = sorted(t for t in by_tax if t != this_tax)     # เลขภาษีอื่นภายใต้ชื่อเดียวกัน
    if not others:
        return []
    shown = ', '.join([this_tax] + others[:3])
    return [f"ชื่อบริษัทเดียวกัน '{b.get('company','')}' ใช้เลขภาษีต่างกัน {len(others) + 1} เลข ({shown}) "
            "— เลขใดเลขหนึ่งน่าจะพิมพ์ผิด ตรวจสอบ"]

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
        # [L·DOC003/ADR-072] ไม่มีวันที่ → guard "รีเซ็ตเลขข้ามงวด" (None!=None=False) ล่ม → ฟ้องซ้ำหลอก.
        #   ยืนยัน "งวดเดียวกัน" ไม่ได้ → ไม่ฟ้อง (DT005 จับ missing-date อยู่แล้ว → ไม่เสียสัญญาณ).
        if this_date is None:
            return []
        dups = []
        # [PERF/ADR-103] กฎนี้จำกัด "ไฟล์เดียวกัน" อยู่แล้ว → เดินเฉพาะกลุ่มไฟล์เดียวกัน (ดัชนี) แทน scan ทั้งหมด
        scan = c.get('xbill_file_index', {}).get(b.get('file'), all_bills)
        for ob in scan:
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
        mo = d.month
        day = d.day
        # NB: เช็คนี้ "ไม่ตาย" — รองรับ date-like object (duck-typed) ที่ month/day นอกช่วงได้
        #   (datetime จริงสร้างไม่ได้ แต่ของจำลอง/พาธอื่นได้) — มีเทสตรึงไว้ (test_rules_extra)
        if mo == 0:
            issues.append(f"เดือน = 0 ผิดปกติ")
        if mo > 12:                                   # [L3] เดือน >12 (date-like จำลอง/พาธอื่น); real datetime สร้างไม่ได้ → golden-neutral
            issues.append(f"เดือน {mo} > 12 ผิดปกติ")
        if day == 0:
            issues.append(f"วัน = 0 ผิดปกติ")
        if day > 31:
            issues.append(f"วัน {day} > 31 ผิดปกติ")
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
            # [M·ITM016/ADR-070] เดิม key=(ชื่อ,หน่วย,ราคา/หน่วย) ไม่รวม qty/amount → รายการแยกจริง
            #   (สินค้าเดียวกัน ราคา/หน่วยเท่ากัน แต่ qty ต่าง = คนละบรรทัด) ถูกฟ้อง "รายการซ้ำ" ผิด.
            #   เพิ่ม qty+amount → ฟ้องเฉพาะบรรทัดที่ "เหมือนกันทุกค่า" (= ซ้ำจริง).
            key = (
                normalize_text(it.get('name', '') or ''),
                (it.get('unit') or '').strip(),
                it.get('price'),
                it.get('qty'),
                it.get('amount'),
            )
            if key[0] == '':
                continue
            # [L7] price=None → ข้าม dedup: เดิม key=(name,unit,None) ชนกันแม้ qty/amount ต่าง → flag ซ้ำหลอก
            #   (false positive). conservative ตามปรัชญา false-negative ดีกว่า false-positive. corpus จริงราคาครบ → ไม่กระทบ.
            if it.get('price') is None:
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
                # [F2-exempt] display-only + type-gate — ไม่ใช่เส้นตัดสินเงิน:
                #   qty_f/price_f/amount_f ใช้ (1) เป็น type-gate รับ/ปฏิเสธ input ชุดเดิมเป๊ะ
                #   (2) เช็ค exact-zero/membership (ไม่มี tolerance) (3) format ข้อความ.
                #   เลขเงินจริง (qty×price vs amount + tolerance 1) คำนวณด้วย Decimal ด้านล่างแล้ว (ADR-020).
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
            # [F2/v9.3 STEP3] float() คงไว้เป็น "type-gate" เท่านั้น (รับ/ปฏิเสธ input ชุดเดิมเป๊ะ —
            # โครง try/except เดิม) ; เส้นตัดสินเงินทั้งหมดย้ายไป Decimal ด้านล่าง (ADR-020/F2).
            vat_f = float(vat)            # F2-exempt: gate เท่านั้น ไม่ใช้ตัดสิน
            total_f = float(total) if total is not None else 0    # F2-exempt: gate เท่านั้น
            sub_f = float(subtotal) if subtotal is not None else 0  # F2-exempt: gate เท่านั้น
        except (TypeError, ValueError):
            return []
        vat_d = _D(vat)
        total_d = _D(total) if total is not None else Decimal('0')
        sub_d = _D(subtotal) if subtotal is not None else Decimal('0')
        if vat_d is None or total_d is None or sub_d is None:
            return []                     # _D แปลงไม่ได้ทั้งที่ float ผ่าน (เคสประดิษฐ์) → เงียบแบบ conservative
        if vat_d != 0:
            return []
        if total_d <= Decimal('10000'):
            return []
        # ถ้า subtotal ≈ total แสดงว่ายกเว้น VAT จริง
        if sub_d > 0 and abs(sub_d - total_d) < Decimal('1'):
            return []
        return ["VAT เป็น 0 ทั้งที่มียอด — ตรวจสอบว่าได้รับยกเว้น VAT จริงหรือไม่"]
    except Exception:
        return []

# ── [BS-2/ADR-115] VAT011 — ใบมียอดแต่ VAT=0 และ total≈subtotal (ไม่ได้บวก VAT) → REVIEW ─────────────
#   เติม "รู" ที่ VAT008 จงใจเว้น: VAT008 เงียบเมื่อ sub≈total (เดาว่า "ยกเว้น VAT จริง") → ใบที่
#   "ลืมคิด VAT" (pre=100/vat=0/total=100) จึงหลุดเงียบทุกกฎ. VAT011 ฟ้องกรณีนั้นเป็น "ข้อสังเกต/รีเช็ค"
#   (ไม่ใช่ ERROR — บางใบ zero-rated ยกเว้นจริง). เกณฑ์ยอด (เจ้าของเคาะ BS-2): subtotal ≥ 1,000 บาท
#   — กัน noise ใบจิ๋ว/ของแถม. ไม่ทับ VAT008 (VAT008 ต้อง sub≠total ; VAT011 ต้อง sub≈total). corpus=0 → golden-neutral.
_VAT011_MIN_SUBTOTAL = Decimal('1000')   # ใต้เกณฑ์นี้ไม่ฟ้อง (ปรับได้ — เจ้าของกำหนดที่ BS-2)


def r_vat011(b, m, c):
    """[BS-2] ใบมียอด (pre-VAT ≥ เกณฑ์) แต่ VAT=0 และ total≈subtotal (ไม่ได้บวก VAT 7%) → REVIEW.
    "ยกเว้นภาษีจริง หรือ ลืมคิด VAT?" — ไม่ตั้งเป็น ERROR (บางใบ zero-rated ยกเว้นจริง).
    เงียบเมื่อ: ไม่มีรายการ / subtotal|vat|total = None / subtotal < เกณฑ์ / vat ไม่ใช่ ~0 /
    total ≠ subtotal (ใบบวก VAT จริง → total = sub×1.07 ≠ sub → เงียบ → ไม่กวนใบถูก)."""
    try:
        items = b.get('items', [])
        if not items:
            return []
        subtotal, vat, total = b.get('subtotal'), b.get('vat'), b.get('total')
        if subtotal is None or vat is None or total is None:
            return []
        sub_d, vat_d, tot_d = _D(subtotal), _D(vat), _D(total)
        if sub_d is None or vat_d is None or tot_d is None:
            return []
        if sub_d < _VAT011_MIN_SUBTOTAL:               # ใต้เกณฑ์ → ไม่ฟ้อง (กัน noise ใบยอดต่ำ/ของแถม)
            return []
        if abs(vat_d) > Decimal('0.50'):               # VAT มีจริง (ไม่ใช่ ~0) → ไม่ใช่เคสนี้
            return []
        if abs(tot_d - sub_d) >= Decimal('0.50'):      # total ≠ subtotal → บวก VAT/ยอดอื่นแล้ว → ใบถูก เงียบ
            return []
        return [f"ใบมียอด {sub_d:,.2f} แต่ VAT=0 (total≈ยอดก่อนภาษี) "
                "— ยกเว้นภาษีจริงหรือลืมคิด VAT? รีเช็ค"]
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
            sub_f = float(subtotal)       # F2-exempt: type-gate เท่านั้น (acceptance เดิมเป๊ะ)
        except (TypeError, ValueError):
            return []
        sub_d = _D(subtotal)
        if sub_d is None:
            return []
        if sub_d == 0:
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

# ── [D1] IV007 — เลขใบกำกับ/เอกสาร "ไม่สมเหตุสมผล" (absolute validity, ไม่พึ่ง master/บิลอื่น) ──────
def r_iv007(b, m, c):
    """[D1] เลขใบกำกับ 'ไม่สมเหตุสมผล' (ค่าสัมบูรณ์) — จับเลขขยะที่ IV002 (consistency-only) ปล่อยหลุด.

    เช่น '0000000002'/'00000000001' (เศษ float ของยอด VAT), '0000000000', '1111111111'. ตรวจได้แม้ไม่มี
    master + ไม่ต้องเทียบบิลอื่น. conservative (false-negative ดีกว่า false-positive): เลขที่มีรูปแบบ
    สมเหตุผล (หลายหลักไม่ซ้ำ เช่น IV6905000279, 01954) → เงียบ. ว่าง → ปล่อย IV005 (validators) ดูแล.
    หมายเหตุ: D2-guard (parser) อาจตั้ง iv ว่างไปแล้วตั้งแต่ parse → IV005 จับ ; IV007 = safety-net ชั้นกฎ.
    """
    iv = str(b.get('iv_number', '') or '').strip()
    if not iv:
        return []
    if re.sub(r'\D', '', iv) == '':
        return []                                   # ไม่มีตัวเลขเลย (รหัสตัวอักษรล้วน) → ไม่ตัดสินที่นี่
    reason = iv_digits_garbage(iv)                   # single-source (core_utils) — ใช้ร่วม parser D2-guard
    if reason:
        return [f"เลขใบกำกับ{reason}: '{iv}' — ไม่ใช่เลขจริง"]
    if iv_amount_fragment(iv, b.get('subtotal'), b.get('vat'), b.get('total')):
        return [f"เลขใบกำกับตรงกับเศษทศนิยมของยอดเงินในบิล: '{iv}' — parser น่าจะคว้าเลขจากยอดเงินผิด"]
    return []


# OBJ-MAINT: auto-export ทุกชื่อ (รวม helper _ และ import) → from-import * ได้ toolkit ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
