# -*- coding: utf-8 -*-
"""rules_engine.py — AUDIT RULES ENGINE (หัวใจระบบตรวจ — 56 กฎ)

OBJ-MAINT: ซอยเพื่อ maintainability (≲600 บรรทัด/ไฟล์) แบบ pure extraction + re-export —
logic/พฤติกรรม/golden hash ไม่เปลี่ยน:
  rules_engine_base        = imports + constants + helpers/infra (toolkit รวม)
  rules_engine_rules_a/b/c  = กฎ r_* (กลุ่มละ ~1/3) ดึง toolkit จาก base
  rules_engine (ไฟล์นี้)     = re-export + PRODUCT_MASTER cluster + RULES + run_rules
หมายเหตุ: PRODUCT_MASTER + ฟังก์ชันที่อ่านมัน (r_itm009/r_itm012/whitelist) อยู่ในไฟล์นี้
  โดยตั้งใจ — เพราะ test/โค้ดอาจ rebind rules_engine.PRODUCT_MASTER แล้วฟังก์ชันต้องเห็นค่าใหม่
  (ถ้าย้ายไป base จะเป็นคนละ binding หลัง import * → patch ไม่ถึง). public API เดิมครบ."""
from __future__ import annotations
from rules_engine_base import (   # [F3 de-star] explicit — ครอบ __all__ ∪ internal ∪ rules_engine.X attr
    CFG, _build_cat_keywords, _kw_in_name, add_issue, clean_tax_id,
    find_similar_in_thai_dict, json, log_system_issue, match_company,
    normalize_company_name, normalize_text, os, re,
    state, validate_company_prefix,
)
from rules_engine_rules_a import (   # [F3 de-star] explicit — ครอบ __all__ ∪ internal ∪ rules_engine.X attr
    r_addr001, r_addr002, r_addr003, r_br001,
    r_br002, r_cmp001, r_cmp002, r_cmp003,
    r_cmp004, r_cmp006, r_doc001, r_doc002, r_dt001,
    r_dt002, r_dt003, r_itm001, r_itm002,
    r_br004, r_iv001, r_tax001, r_tax002, r_tax003,
    r_tax004, r_tax005, r_tax006,
)
from rules_engine_rules_b import (   # [F3 de-star] explicit — ครอบ __all__ ∪ internal ∪ rules_engine.X attr
    r_itm003, r_itm004, r_itm005, r_itm006,
    r_itm007, r_itm008, r_itm010, r_itm011,
    r_itm013, r_itm014, r_itm015, r_itm017,
    r_vat001, r_vat002, r_vat003, r_vat004,
)
from rules_engine_rules_c import (   # [F3 de-star] explicit — ครอบ __all__ ∪ internal ∪ rules_engine.X attr
    r_addr004, r_addr005, r_addr006, r_br003, r_cmp005,
    r_doc003, r_dt004, r_itm016, r_itm018, r_iv007,
    r_tax007, r_tax008, r_tax009, r_vat005, r_vat006, r_vat007,
    r_vat008, r_vat009, r_vat010, r_vat011,
)
from config import (CONSTRUCTION_DICT, ITM012_MIN_WORD_LEN,  # [F3] explicit — config ที่ rules_engine ใช้
                    ITM012_SIM_THRESHOLD, PYTHAINLP_WHITELIST)
# [ADD-ON v9.2] ITM019 — spell-check ช่องหน่วยสินค้า (โมดูล leaf อิสระ ไม่กระทบ logic เดิม)
from unit_detection_ext import r_itm019, r_itm020


def load_product_master():
    if not os.path.exists(CFG['PRODUCT_MASTER_FILE']): return {}
    try:
        with open(CFG['PRODUCT_MASTER_FILE'],'r',encoding='utf-8') as f:
            return json.load(f)
    except Exception: return {}

PRODUCT_MASTER = load_product_master()

def _build_product_whitelist():
    wl = set(CONSTRUCTION_DICT)
    wl |= PYTHAINLP_WHITELIST
    # เติมจาก PRODUCT_MASTER (canonical + aliases) ถ้ามี
    for canonical, info in PRODUCT_MASTER.items():
        wl.add(canonical)
        for a in info.get('aliases', []): wl.add(a)
    return wl

def validate_product_word(word):
    """ตรวจ 1 คำ → คืน dict {status, value, suggestion}
    status: 'correct' | 'similar' | 'unknown'
    - correct  : เจอใน whitelist (proper noun ที่ถูกต้อง)
    - similar  : ไม่เจอ แต่ fuzzy ใกล้เคียงคำใน whitelist ≥ threshold
    - unknown  : ไม่เจอ และไม่ใกล้เคียงอะไรเลย → คืนค่าเดิม ไม่ suggest
    """
    if state._PRODUCT_WHITELIST is None:
        state._PRODUCT_WHITELIST = _build_product_whitelist()

    # STEP 1: Normalize
    w = normalize_text(word)
    if not w:
        return {'status':'unknown','value':word,'suggestion':None}

    # STEP 2: Exact match + whitelist → correct (หยุดทันที)
    if w in state._PRODUCT_WHITELIST:
        return {'status':'correct','value':w,'suggestion':None}

    # คำสั้นเกินไป → ไม่ตัดสิน (กัน false positive)
    if len(w) < ITM012_MIN_WORD_LEN:
        return {'status':'unknown','value':word,'suggestion':None}

    # STEP 3: Fuzzy matching (ไม่ใช่ spell correction)
    best, score = find_similar_in_thai_dict(w, threshold=ITM012_SIM_THRESHOLD)

    # STEP 4: Confidence threshold
    if not best or score < ITM012_SIM_THRESHOLD:
        # ไม่ใกล้เคียงพอ → คืนค่าเดิม ไม่ suggest
        return {'status':'unknown','value':word,'suggestion':None}

    # STEP 5: Suggestion only (ไม่ replace)
    return {'status':'similar','value':w,'suggestion':best}

def r_itm009(b,m,c):
    if not PRODUCT_MASTER: return []
    o = []
    for it in b['items']:
        for canonical, info in PRODUCT_MASTER.items():
            for alias in info.get('aliases', []):
                if alias in it['name'] and canonical not in it['name']:
                    o.append(f"#{it['seq']}: ใช้ alias '{alias}' → ควรเป็น '{canonical}'"); break
    return o

def r_itm012(b,m,c):
    """v8.0: Suggestion mode — ข้ามคำที่ ITM011 จับแล้ว, ลด false positive loanword"""
    if state._PRODUCT_WHITELIST is None:
        state._PRODUCT_WHITELIST = _build_product_whitelist()

    issues = []
    seen = set()
    for it in b['items']:
        # v9.3.5 [ADR-119]: เช่นเดียวกับ r_itm011 — กัน FP จากการตัด run ไทยยาว >20 ตัวกลางคำ
        #   เก็บเฉพาะท่อนแรกของแต่ละ Thai run (run[:20]) ; เศษ (ท่อนที่ 2+) คือ fragment ขอบซ้ายปลอม
        #   → ข้าม. ปัจจุบัน ITM012 ฟ้อง 0 รายการบน corpus → golden-neutral (new tokens ⊆ old tokens
        #   เสมอ จึงเพิ่ม flag ไม่ได้) ; แก้ที่นี่ด้วยเพื่อปิด bug "คลาสเดียวกัน" ให้ครบ ไม่ให้ latent.
        thai_words = [run[:20] for run in re.findall(r'[ก-๙][ก-๙์]+', it['name'])
                      if len(run) >= 4]
        for w in thai_words:
            if w in seen: continue
            seen.add(w)
            if w in state._PRODUCT_WHITELIST: continue
            # v8.0: ข้ามคำที่มีตัวเลขผสม (รหัส/spec)
            if re.search(r'\d', w): continue
            # v8.0: ข้ามคำสั้นมาก ≤ 4 ตัวอักษร — false positive สูง
            if len(w) <= 4: continue

            res = validate_product_word(w)
            if res['status'] == 'similar' and res['suggestion']:
                _, sc = find_similar_in_thai_dict(w, threshold=ITM012_SIM_THRESHOLD)
                # v8.0: ต้องมี confidence ≥ 90 ถึงจะ suggest
                if sc < ITM012_SIM_THRESHOLD: continue
                # v8.0: ข้ามถ้า suggestion อยู่ใน whitelist (แสดงว่าต้นฉบับถูกต้อง)
                if res['suggestion'] in state._PRODUCT_WHITELIST: continue
                issues.append(
                    f"#{it['seq']}: \"{w}\" อาจพิมพ์คล้าย \"{res['suggestion']}\" "
                    f"(~{sc}%) — แนะนำตรวจสอบ")
    return issues

RULES = {
    'CMP001':{'name':'ชื่อ exact match','severity':'CRITICAL','category':'บริษัท','check':r_cmp001,'enabled':True},
    'CMP002':{'name':'คำนำหน้านิติบุคคล','severity':'ERROR','category':'บริษัท','check':r_cmp002,'enabled':True},
    'CMP003':{'name':'ไม่ใช้ชื่อแบรนด์','severity':'ERROR','category':'บริษัท','check':r_cmp003,'enabled':True},
    'CMP004':{'name':'เว้นวรรค exact','severity':'ERROR','category':'บริษัท','check':r_cmp004,'enabled':True},
    'ADDR001':{'name':'ที่อยู่ครบ','severity':'ERROR','category':'ที่อยู่','check':r_addr001,'enabled':True},
    'ADDR002':{'name':'ตัวสะกดถนน/แขวง','severity':'WARNING','category':'ที่อยู่','check':r_addr002,'enabled':True},
    'ADDR003':{'name':'ชั้น/อาคาร/ห้อง ตรงกับ master','severity':'WARNING','category':'ที่อยู่','check':r_addr003,'enabled':True},
    'TAX001':{'name':'เลขภาษี 13 หลัก','severity':'CRITICAL','category':'เลขภาษี','check':r_tax001,'enabled':True},
    'TAX002':{'name':'เลขภาษีตัวเลขล้วน','severity':'CRITICAL','category':'เลขภาษี','check':r_tax002,'enabled':True},
    'TAX003':{'name':'TaxID↔Company','severity':'CRITICAL','category':'เลขภาษี','check':r_tax003,'enabled':True},
    'TAX004':{'name':'OCR error','severity':'WARNING','category':'เลขภาษี','check':r_tax004,'enabled':True},
    'TAX005':{'name':'TaxID Reverse Lookup','severity':'CRITICAL','category':'เลขภาษี','check':r_tax005,'enabled':True},
    'TAX006':{'name':'checksum เลขภาษี (mod11)','severity':'ERROR','category':'เลขภาษี','check':r_tax006,'enabled':True},
    'BR001':{'name':'รหัสสาขา format','severity':'ERROR','category':'สาขา','check':r_br001,'enabled':True},
    'BR002':{'name':'ต้องระบุสาขา','severity':'ERROR','category':'สาขา','check':r_br002,'enabled':True},
    'BR004':{'name':'สาขาไม่ตรงทะเบียน master','severity':'ERROR','category':'สาขา','check':r_br004,'enabled':True},  # [B3] เทียบ branch บิล↔master (เมื่อมี master+branch). conservative: ไม่มี master/branch ไม่ชัด → เงียบ (ปล่อย A1 honesty)
    'DOC001':{'name':'ชีต↔วันที่','severity':'ERROR','category':'เอกสาร','check':r_doc001,'enabled':True},
    'DOC002':{'name':'IV↔วันที่ (ปิดใช้งาน v5.8k)','severity':'ERROR','category':'เอกสาร','check':r_doc002,'enabled':False},
    'IV001':{'name':'IV Prefix','severity':'WARNING','category':'เอกสาร','check':r_iv001,'enabled':True},
    'IV007':{'name':'เลขใบกำกับไม่สมเหตุสมผล (ศูนย์ล้วน/เศษยอดเงิน)','severity':'ERROR','category':'เอกสาร','check':r_iv007,'enabled':True},  # [D1] absolute validity — จับเลขขยะที่ IV002 (consistency-only) ปล่อยหลุด. ไม่พึ่ง master. conservative
    'DT001':{'name':'เดือน target','severity':'WARNING','category':'วันที่','check':r_dt001,'enabled':True},
    'DT002':{'name':'ไม่ใช่ future','severity':'WARNING','category':'วันที่','check':r_dt002,'enabled':True},
    'DT003':{'name':'พ.ศ./ค.ศ. ชัดเจน','severity':'WARNING','category':'วันที่','check':r_dt003,'enabled':True},
    'ITM001':{'name':'Qty×Price','severity':'ERROR','category':'รายการสินค้า','check':r_itm001,'enabled':True},
    'ITM002':{'name':'Running ลำดับ','severity':'ERROR','category':'รายการสินค้า','check':r_itm002,'enabled':True},
    'ITM003':{'name':'ไม่คลุมเครือ','severity':'WARNING','category':'รายการสินค้า','check':r_itm003,'enabled':True},
    'ITM004':{'name':'คำสะกด pattern','severity':'INFO','category':'รายการสินค้า','check':r_itm004,'enabled':True},
    'ITM005':{'name':'หน่วย keyword','severity':'INFO','category':'รายการสินค้า','check':r_itm005,'enabled':True},
    'ITM006':{'name':'หน่วย pattern','severity':'WARNING','category':'รายการสินค้า','check':r_itm006,'enabled':True},
    'ITM007':{'name':'ชื่อสั้น','severity':'WARNING','category':'รายการสินค้า','check':r_itm007,'enabled':True},
    'ITM008':{'name':'ราคา outlier','severity':'WARNING','category':'รายการสินค้า','check':r_itm008,'enabled':False},  # v9.2: ปิดตามคำขอลูกค้า — รายการที่ qty×price=amount ถูกต้องแต่ "ราคา/หน่วยสูง" (เช่น 4,590 vs median 58) ไม่ใช่ error แต่เป็นสินค้าแพงปกติ → กฎนี้สร้าง false positive/noise (ลูกค้าแจ้งซ้ำหลายรอบ). ITM001 (qty×price≈amount) จับเลขผิดจริงแทนอยู่แล้ว. r_itm008 เป็น pure check ไม่มี side-effect — เปิดคืนได้ถ้าต้องการ
    'ITM009':{'name':'Alias mapping','severity':'INFO','category':'รายการสินค้า','check':r_itm009,'enabled':True},
    'ITM010':{'name':'Thai char-pattern typo','severity':'WARNING','category':'รายการสินค้า','check':r_itm010,'enabled':True},
    'ITM011':{'name':'Fuzzy Thai dict','severity':'WARNING','category':'รายการสินค้า','check':r_itm011,'enabled':True},
    'ITM012':{'name':'ชื่อสินค้า suggestion','severity':'INFO','category':'รายการสินค้า','check':r_itm012,'enabled':True},
    'ITM013':{'name':'ลำดับไม่เรียง/ไม่เริ่มที่ 1','severity':'WARNING','category':'รายการสินค้า','check':r_itm013,'enabled':True},
    'ITM014':{'name':'gap ลำดับใหญ่ผิดปกติ','severity':'INFO','category':'รายการสินค้า','check':r_itm014,'enabled':True},
    'ITM015':{'name':'ชื่อเดียวกันใช้หน่วยต่าง','severity':'WARNING','category':'รายการสินค้า','check':r_itm015,'enabled':True},
    'ITM017':{'name':'จำนวน/ราคาติดลบ','severity':'WARNING','category':'รายการสินค้า','check':r_itm017,'enabled':True},
    'VAT001':{'name':'Sum=PreVAT','severity':'CRITICAL','category':'ยอดเงิน','check':r_vat001,'enabled':True},
    'VAT002':{'name':'PreVAT×0.07','severity':'CRITICAL','category':'ยอดเงิน','check':r_vat002,'enabled':True},
    'VAT003':{'name':'PreVAT+VAT=Total','severity':'CRITICAL','category':'ยอดเงิน','check':r_vat003,'enabled':True},
    'VAT004':{'name':'ปัดเศษ (ปิดใช้งาน — เจ้าของยืนยันถูกต้องแล้ว)','severity':'WARNING','category':'ยอดเงิน','check':r_vat004,'enabled':False},  # [recheck] ปิดตามคำขอเจ้าของ — ทศนิยมถูกปัดเป็น 2 ตำแหน่งเพื่อแสดงผลถูกอยู่แล้ว (float residue ไม่ใช่ error). r_vat004 เป็น pure check ไม่มี side-effect
    'VAT005':{'name':'ค่าผิดปกติ','severity':'CRITICAL','category':'ยอดเงิน','check':r_vat005,'enabled':True},
    'VAT006':{'name':'VAT Included','severity':'WARNING','category':'ยอดเงิน','check':r_vat006,'enabled':True},
    'VAT007':{'name':'Discount validation','severity':'CRITICAL','category':'ยอดเงิน','check':r_vat007,'enabled':True},
    # v8.1: new rules
    'CMP005':{'name':'suffix นิติบุคคล','severity':'ERROR','category':'บริษัท','check':r_cmp005,'enabled':True},
    'CMP006':{'name':'ชื่อไม่ตรง 100% กับ ภ.พ.20 (ตรวจเพิ่ม)','severity':'WARNING','category':'บริษัท','check':r_cmp006,'enabled':True},  # [ADD-ON v9.2] ลูกค้าขอเข้มขึ้น: ชื่อต่างตัวอักษรจาก ภ.พ.20 (โซน fuzzy≥85 ที่ CMP001 ปล่อยผ่าน) = ฟ้อง. กันซ้ำ CMP001(<85)/CMP004(เว้นวรรค)/substring. ปิดได้ด้วย enabled=False ถ้า false-positive เยอะ
    'ADDR004':{'name':'กรุงเทพ vs ต่างจังหวัด format','severity':'WARNING','category':'ที่อยู่','check':r_addr004,'enabled':True},
    'ADDR005':{'name':'รหัสไปรษณีย์','severity':'INFO','category':'ที่อยู่','check':r_addr005,'enabled':True},
    'ADDR006':{'name':'ไปรษณีย์↔จังหวัด ไม่สอดคล้อง','severity':'WARNING','category':'ที่อยู่','check':r_addr006,'enabled':True},  # [B2] generalize ทุกจังหวัด (ไม่พึ่ง master) — เว้นกรุงเทพฯ (ADDR005 ดูแล). conservative: ฟ้องเฉพาะขัดกันชัด
    'TAX007':{'name':'ประเภทนิติบุคคลจากหลักแรก','severity':'WARNING','category':'เลขภาษี','check':r_tax007,'enabled':True},
    'TAX008':{'name':'เลขภาษีเดียวชื่อต่าง (cross-bill)','severity':'CRITICAL','category':'เลขภาษี','check':r_tax008,'enabled':True},  # [B1] เลขภาษี 13 หลักตัวเดียวถูกใช้กับ "คนละบริษัทจริง" ข้ามบิล — ตรวจได้แม้ไม่มี master (จับสวมเลข/ปลอม). conservative: ฟ้องเฉพาะชื่อต่างชัด (เกณฑ์แนว CMP001)
    'TAX009':{'name':'ชื่อเดียวเลขภาษีต่าง (cross-bill)','severity':'WARNING','category':'เลขภาษี','check':r_tax009,'enabled':True},  # [BS-3/ADR-116] mirror TAX008 ทิศกลับ: ชื่อบริษัทเดียวกัน (ตรงชัด) ใช้เลขภาษี 13 หลัก ≥2 เลข → ผู้ขายรายเดียวพิมพ์เลขภาษีผิดบางใบ. conservative: ชื่อ normalize ตรงเป๊ะ + เลขครบ 13 หลัก. corpus=0 → golden-neutral
    'BR003':{'name':'สาขาสม่ำเสมอในไฟล์','severity':'WARNING','category':'สาขา','check':r_br003,'enabled':False},  # v8.4: ปิด — ผู้ขายมีทั้ง สนญ.+สาขา เป็นเรื่องปกติ ไม่ใช่ error (ฟ้องผิด/ซ้ำทุกบิล)
    'DOC003':{'name':'IV ซ้ำในไฟล์','severity':'ERROR','category':'เอกสาร','check':r_doc003,'enabled':True},
    'DT004':{'name':'ปี/วัน/เดือนนอกช่วงสมเหตุผล','severity':'WARNING','category':'วันที่','check':r_dt004,'enabled':True},
    'ITM016':{'name':'รายการซ้ำในบิล','severity':'WARNING','category':'รายการสินค้า','check':r_itm016,'enabled':True},
    'ITM018':{'name':'จำนวน/ยอดผิดปกติ','severity':'WARNING','category':'รายการสินค้า','check':r_itm018,'enabled':True},
    'ITM019':{'name':'หน่วยสินค้าผิด/ขาดหาย (ตรวจเพิ่ม)','severity':'WARNING','category':'รายการสินค้า','check':r_itm019,'enabled':True},  # [ADD-ON v9.2] ตรวจ "ช่องหน่วย": (ก) สะกดผิด/รูปไม่มาตรฐาน (ปี๊ป→ปี๊บ, แกลอน/แกนลอน→แกลลอน, ตรม.) (ข) หน่วยขาด/ดึงไม่ครบในบิลที่รายการอื่นมีหน่วย — ช่องว่างที่ ITM004/010/011 (ตรวจชื่อ) และ ITM005/006/015 (ตรวจความเหมาะสมหน่วย) ไม่ครอบ. pure check ไม่มี side-effect — ปิดได้ด้วย enabled=False
    'ITM020':{'name':'ทั้งบิลไม่มีหน่วยสินค้า','severity':'WARNING','category':'รายการสินค้า','check':r_itm020,'enabled':True},  # [ADD-ON v9.3.4 — ADR-106/P3] จับ "ทั้งใบไม่มีหน่วย": มีรายการคิดเงินแต่ไม่มีหน่วยเลยทุกรายการ (เช่น TOR_67_08 ผ้า/ซิป) — ช่องว่างที่ ITM019 (intra-bill: หน่วยขาดเฉพาะใบที่รายการอื่นมีหน่วย) จงใจข้าม. เจ้าของขอให้ระบบแจ้งเมื่อมีสินค้าแต่ไม่มีหน่วย. pure check ไม่มี side-effect — ปิดได้ด้วย enabled=False
    'VAT008':{'name':'VAT เป็นศูนย์','severity':'INFO','category':'ยอดเงิน','check':r_vat008,'enabled':True},
    'VAT009':{'name':'Subtotal เป็นศูนย์/ไม่มี','severity':'ERROR','category':'ยอดเงิน','check':r_vat009,'enabled':True},
    'VAT011':{'name':'ใบมียอดแต่ VAT=0 (ยกเว้นจริง/ลืมคิด?)','severity':'INFO','category':'ยอดเงิน','check':r_vat011,'enabled':True},  # [BS-2/ADR-115] เติมรูที่ VAT008 เว้น (sub≈total → เดาว่ายกเว้น): subtotal≥1000 + VAT≈0 + total≈subtotal → REVIEW "ยกเว้นจริงหรือลืมคิด VAT?" (ไม่ใช่ ERROR — บางใบ zero-rated). corpus=0 → golden-neutral
    'VAT010':{'name':'VAT ไม่ได้ตรวจจริง (ยอดถูกคำนวณเอง)','severity':'WARNING','category':'ยอดเงิน','check':r_vat010,'enabled':False},  # v9.1: ปิด/ลบการทำงานตามคำขอ — run_rules ข้ามกฎ enabled=False; r_vat010 เป็น pure check ไม่มี side-effect
}

# [PERF/ADR-103] ดัชนีบิลข้ามใบ (tax_id + file) — สร้างครั้งเดียวต่อ batch (cache ตาม fingerprint).
#   เดิมกฎ cross-bill (TAX008/DOC003/IV001) วน all_bills "ทุกใบ" → O(n²) ในจำนวนบิลรวม (ช้ามากที่ scale ใหญ่).
#   ดัชนีนี้ให้กฎเดินเฉพาะกลุ่มเดียวกัน (เลขภาษีเดียว / ไฟล์เดียว) = O(n) รวม.
#   กลุ่มเรียงตามลำดับ all_bills เดิม (append ตามลำดับ) → กฎเห็นบิลลำดับเดิมเป๊ะ → ผลตรวจไม่เปลี่ยน (golden-neutral).
#   cache เก็บ batch ล่าสุด 1 ชุด (audit รันทีละ batch) ; fingerprint = (id, len, id หัว, id ท้าย) กัน id-reuse ชนกัน.
_XBILL_IDX_CACHE = {'fp': None, 'tax': {}, 'file': {}}


def _xbill_indexes(all_bills):
    """คืน (tax_index, file_index) ของ batch — สร้างครั้งเดียวแล้ว cache (เรียกซ้ำต่อบิล = O(1))."""
    if not all_bills:
        return {}, {}
    fp = (id(all_bills), len(all_bills), id(all_bills[0]), id(all_bills[-1]))
    if _XBILL_IDX_CACHE['fp'] != fp:
        tax_idx, file_idx = {}, {}
        for ob in all_bills:
            t = clean_tax_id(ob.get('tax_id', ''))
            if t:
                tax_idx.setdefault(t, []).append(ob)
            file_idx.setdefault(ob.get('file'), []).append(ob)
        _XBILL_IDX_CACHE.update(fp=fp, tax=tax_idx, file=file_idx)
    return _XBILL_IDX_CACHE['tax'], _XBILL_IDX_CACHE['file']


def run_rules(bill, master_companies, file_info, unit_index=None, all_bills_ref=None):
    # [M4 ROBUSTNESS] บิลจาก parser มีคีย์เหล่านี้เสมอ (parser_p2:167/397) → setdefault = no-op
    #   กับบิลจริง (golden ไม่ขยับ). กันบิลภายนอก/บางส่วนที่ขาดคีย์ ทำกฎที่อ้าง b['items']/b['subtotal']
    #   ตรง ๆ พังเงียบเป็น SYS-* แล้ว "ข้ามการตรวจ" (กฎไม่ได้รัน) แทนที่จะรันได้.
    bill.setdefault('items', [])
    bill.setdefault('subtotal', None)
    bill.setdefault('vat', None)
    bill.setdefault('total', None)
    # [M5] guard ให้ครบจริง: เดิม setdefault แค่ 4 คีย์ แล้วไปอ้าง bill['company'] (บรรทัดนี้) + bill['sheet']
    #   (ctx ด้านล่าง) ดิบ ๆ นอก try → บิลภายนอก/บางส่วนที่ขาดคีย์ "ทั้งบิลครัช" หรือกฎ ~6 ตัวข้ามเงียบเป็น SYS-*.
    #   บิลจาก parser มีคีย์เหล่านี้ครบเสมอ → setdefault = no-op (golden ไม่ขยับ).
    # [C1 GOLDEN-FIX 2026-06-20] เดิม M5 ใส่ 'name_raw' ในลิสต์นี้ด้วย แต่ 'name_raw' เป็นคีย์ระดับ "รายการ"
    #   (parser ใส่ให้ทุก item — parser_p1._pb_build_item / parser_p2._tor_scan_items) ไม่เคยมีที่ระดับ "บิล"
    #   (result dict ออก company_raw/tax_id_raw/iv_number_raw/iv_date_str เท่านั้น). การ setdefault ที่ระดับบิล
    #   จึง "ฉีดคีย์ใหม่" name_raw='' เข้าทุกบิล → ขยับ golden snapshot hash → regression fixture แดง
    #   (engine 21d6f1a6 ≠ baseline 269ddaed). ถอด 'name_raw' ออก: ไม่มีกฎไหนอ่าน bill['name_raw'] ดิบ
    #   (อ่านผ่าน it.get('name_raw') ที่ระดับ item ทั้งคู่) → ปลอดภัย + คืน golden เดิม.
    for _k in ('company', 'tax_id', 'branch', 'branch_no', 'address', 'iv_number', 'sheet',
               'iv_date_str', 'company_raw', 'tax_id_raw', 'iv_number_raw'):
        bill.setdefault(_k, '')
        # [GAP-A 2026-06-28] coerce ฟิลด์ "ข้อความระดับบิล" เป็น str — setdefault เติมเฉพาะคีย์ที่ "หาย"
        #   แต่ถ้าคีย์มีอยู่และเป็น non-str (เซลล์ตัวเลขล้วน int/float, หรือ None) กฎที่เรียก re/.lower()/
        #   `x in field` จะครัช → run_rules ดักเป็น SYS-* แล้ว "ข้ามกฎเงียบ" = false-negative (ตรวจไม่ได้
        #   โผล่เป็น 'ตรง' หลอก). fuzz พบครัชจริง: BR001(branch)/CMP003(company)/IV001(iv_number)/
        #   TAX004(tax_id_raw). corpus จริงทุกฟิลด์เป็น str เสมอ (สแกนยืนยัน 0 non-str/0 None) → no-op
        #   → golden-NEUTRAL คง d8adc143. None→'' (ตรงกับ default ของ setdefault).
        if not isinstance(bill[_k], str):
            bill[_k] = '' if bill[_k] is None else str(bill[_k])
    bill.setdefault('iv_date', None)
    bill.setdefault('issues', [])
    # [F1 2026-06-20] บิลจาก parser มี item ครบ 7 คีย์เสมอ (seq/name/name_raw/qty/unit/price/amount)
    #   → setdefault = no-op (golden ไม่ขยับ). กันบิล "ภายนอก/บางส่วน" ที่ item ขาดคีย์: กฎ ITM001/ITM005/
    #   ITM006 + VAT001 (CRITICAL) อ้าง it['amount']/['price']/['unit']/['name'] ดิบ → KeyError → run_rules
    #   ดักเป็น SYS-* แล้ว "ข้ามกฎเงียบ" (= 'ตรวจไม่ได้' โผล่เป็น 'ตรง' หลอก ขัดปรัชญาระบบ).
    for _it in bill['items']:
        if isinstance(_it, dict):
            _it.setdefault('seq', None); _it.setdefault('name', ''); _it.setdefault('name_raw', '')
            _it.setdefault('qty', None); _it.setdefault('unit', ''); _it.setdefault('price', None)
            _it.setdefault('amount', None)
            # [GAP-A 2026-06-28] coerce ฟิลด์ "ข้อความระดับรายการ" เป็น str — เซลล์ชื่อสินค้า/หน่วยที่เป็น
            #   ตัวเลขล้วน (รหัส/โมเดล int/float) หรือช่องว่าง→None ทำ 7 กฎครัช: ITM003/004/005/007/011/
            #   012/017 (re.findall/.lower()/len()/`in`) → SYS-* → ข้ามกฎ = false-negative. corpus จริง
            #   ทุก item เป็น str เสมอ (สแกนยืนยัน 0 non-str) → no-op → golden-NEUTRAL คง d8adc143.
            #   '12345' เป็น str แล้ว กฎ ITM007 ตรวจ "ชื่อสั้น" ได้ตามตรรกะ (ไม่ใช่ข้ามเงียบ).
            for _tk in ('name', 'name_raw', 'unit'):
                if not isinstance(_it[_tk], str):
                    _it[_tk] = '' if _it[_tk] is None else str(_it[_tk])
    key, master, score = match_company(bill['company'], master_companies)
    # [MATCH-GUARD] กัน fuzzy ผูกข้ามบริษัท: partial_ratio ให้คะแนนสูงจากคำอุตสาหกรรมร่วม
    #   ("...คอนสตรัคชั่น จำกัด") → บิลของ "คนละนิติบุคคล" (เลขภาษี 13 หลักต่างจาก master ชัด ๆ)
    #   เคยถูกผูกที่ score 75-80 แล้วโดน CMP001/TAX003/ADDR001 เป็น false positive ถึงลูกค้า.
    #   guard: เลขภาษีบิลครบ 13 หลัก + ต่างจาก master + ชื่อแค่คล้าย (score<90) → ไม่ผูก (ปล่อย
    #   A1 honesty ขึ้น "ไม่มีใน master ตรวจไม่ได้"). ชื่อเหมือนมาก (≥90 รวม exact/substring=100)
    #   + เลขต่าง → "คงผูก" เพื่อให้ TAX003 จับเคสสวมเลข/พิมพ์เลขผิด (คลาสฉีหยวน) ตามเดิม.
    #   เลขภาษีบิลอ่านไม่ได้/ไม่ครบ → คงพฤติกรรมเดิม (ผูกตาม fuzzy) — conservative.
    if master is not None and score < 90:
        _bt = clean_tax_id(bill.get('tax_id') or '')
        _mt = clean_tax_id((master.get('tax_id') if isinstance(master, dict) else '') or '')
        if len(_bt) == 13 and len(_mt) == 13 and _bt != _mt:
            key, master = None, None
    bill['master_key'] = key or '(ไม่พบใน master)'
    bill['match_score'] = score
    _xb_tax, _xb_file = _xbill_indexes(all_bills_ref or [])
    ctx = {
        'sheet_name': bill['sheet'],
        'target_month': file_info.get('month') if file_info else None,
        'target_month_end': file_info.get('month_end') if file_info else None,
        'all_masters': master_companies,
        'unit_index': unit_index,
        # v5.9 FIX-2: รับ all_bills_ref เป็น parameter แทนการฝังใน bill dict (กัน circular ref)
        'all_bills_for_iv_check': all_bills_ref or [],
        # [PERF/ADR-103] ดัชนีข้ามใบ — กฎ cross-bill เดินเฉพาะกลุ่มเดียวกัน (O(n) แทน O(n²))
        'xbill_tax_index': _xb_tax,
        'xbill_file_index': _xb_file,
    }
    for code, rule in RULES.items():
        if not rule['enabled']:
            continue
        try:
            for d in (rule['check'](bill, master, ctx) or []):
                add_issue(bill, code, rule, d)
        except Exception as e:
            # v8.5 [FIX-SYS]: ไม่กลืน error เงียบ และ "ไม่ปน" ผลตรวจบิล
            #   เดิม append เข้า bill['issues'] → โผล่ใน Error Report เป็น FP/noise ทุกบิล
            #   ใหม่: route ไป log_system_issue() (มี dedupe + sidecar .jsonl + ชีต System Issues)
            #   → ชีต Error Report สะอาด แต่ความผิดพลาดยังตามรอยได้ครบ (traceable, repeatable)
            log_system_issue(code=f'SYS-{code}', name=f'กฎ {code} ทำงานผิดพลาด',
                             severity='INFO', category='SYSTEM',
                             file=bill.get('file'), sheet=bill.get('sheet'), exc=e, echo=False)
    return bill

__all__ = [
    'match_company', 'load_product_master',
    'PRODUCT_MASTER', 'add_issue', 'r_cmp001', 'normalize_company_name',
    'validate_company_prefix', 'r_cmp002', 'r_cmp003', 'r_cmp004',
    'r_addr001', 'r_addr002', 'r_addr003', 'r_tax001',
    'r_tax002', 'r_tax003', 'r_tax004', 'r_tax005',
    'r_tax006', 'r_br001', 'r_br002', 'r_doc001',
    'r_doc002', 'r_iv001', 'r_dt001', 'r_dt002',
    'r_br004', 'r_dt003', 'r_itm001', 'r_itm002', 'r_itm013',
    'r_itm014', 'r_itm015', 'r_itm017', 'r_itm003',
    'r_itm004', '_kw_in_name', 'r_itm005', 'r_itm006',
    '_build_cat_keywords', 'r_itm007', 'r_itm008', 'r_itm009',
    'r_itm010', 'r_itm011', '_build_product_whitelist', 'validate_product_word',
    'r_itm012', 'r_vat001', 'r_vat002', 'r_vat003',
    'r_vat004', 'r_vat005', 'r_vat006', 'r_vat007',
    'r_cmp005', 'r_cmp006', 'r_addr004', 'r_addr005', 'r_addr006', 'r_tax007', 'r_tax008', 'r_tax009',
    'r_br003', 'r_doc003', 'r_dt004', 'r_itm016',
    'r_itm018', 'r_vat008', 'r_vat009', 'r_vat010', 'r_vat011',
    'r_itm019', 'r_itm020', 'r_iv007',
    'RULES', 'run_rules',
]
