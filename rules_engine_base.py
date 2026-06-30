# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""rules_engine.py — AUDIT RULES ENGINE (หัวใจระบบตรวจ — 56 กฎ)

ย้ายมาจาก monolith แบบ "คัดลอกเป๊ะทุกตัวอักษร" — ห้ามแก้ logic การตรวจใดๆ.
ประกอบด้วย: match_company, add_issue, กฎ r_* ครบ 56 ข้อ, RULES registry, run_rules.

ตำแหน่งใน DAG:
    config + puopuy_core + puopuy_dates + puopuy_units   (พึ่งลงล่างเท่านั้น)
        │
        └─ [rules_engine]  ←── main late-import 4 ตัว (กัน circular): ดู _bind_from_main()
             │
             └─ orchestrator / main

⚠️ 4 dependency ที่ผูกกับ main (parser/thai_text/diagnostics ยังอยู่ใน main):
       find_similar_in_thai_dict, predict_category, pythainlp_spell_check, log_system_issue
   ใช้ late-import ผ่าน module __getattr__ → ตอนกฎเรียกใช้จริง ค่อยดึงจาก main
   (รูปแบบเดียวกับที่ validators.py ใช้สำเร็จ — main นิยามครบก่อน import rules_engine)
"""
from __future__ import annotations

import os
import re
import json
import statistics
import unicodedata
import state
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP

from rapidfuzz import fuzz

# ค่าคงที่/ตาราง/เกณฑ์ทั้งหมด (CFG, RULES thresholds, dict ฯลฯ)
from config import (CFG, COMPANY_PREFIXES, COMPANY_PREFIX_RE,  # [F3] explicit — เฉพาะที่ base ใช้เอง
                    PRODUCT_CATEGORIES, _AMBIG_SHORT_KW, _THAI_MARKS, _SI_COLOR_ADJ)

# core layer (พิสูจน์แล้วว่าผลเดิม)
from puopuy_core import (to_conf01, normalize_text, has_hidden_chars, clean_tax_id,
                         _taxid_checksum_ok, remove_branch_suffix, _raw_company_form,
                         extract_branch, safe)
from puopuy_dates import parse_date_any, _ivp_year2_to_ce, _ivp_year4_to_ce
from puopuy_units import extract_unit_hint, _unit_canon, _D, _vat_tolerance, VAT_RATE

# ---------------------------------------------------------------------------
# late-import จาก main (กัน circular import): symbol เหล่านี้ยังอยู่ใน main
#   (thai_text / diagnostics / ยังไม่ถูกแยกในพาสนี้)
#   module-level __getattr__ จะถูกเรียกเมื่อโค้ดในไฟล์นี้อ้างชื่อที่ยังไม่ถูก bind
#   → ดึงจากโมดูลหลักแบบ lazy ครั้งแรก แล้ว cache ไว้ใน globals()
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# พาส2b: thai_text + diagnostics ถูกแยกเป็นโมดูลแล้ว → import ตรงได้ (ไม่ circular,
#   เพราะ thai_text/diagnostics ไม่ import rules_engine). เลิก lazy proxy เดิม.
#   DAG สะอาด: config+core+state → diagnostics → thai_text → [rules_engine]
# ---------------------------------------------------------------------------
from diagnostics import log_system_issue
from thai_text import find_similar_in_thai_dict, predict_category, pythainlp_spell_check


# ===== match_company (ใช้เฉพาะ run_rules) =====

def _master_taxid_index(master):
    """[TAXID-JOIN/ADR-146] ทำดัชนี master ด้วย clean_tax_id(record['tax_id']) → list ของ (key, record).
    เลขภาษี 13 หลัก = กุญแจเอกลักษณ์ของนิติบุคคล (แม่นกว่าชื่อ fuzzy ทุกทาง).
    เก็บเป็น list เพราะหลาย record อาจแชร์ tax_id เดียว (สำนักงานใหญ่ + สาขา) → disambiguate ภายหลัง.
    O(n) ต่อการเรียก — master เดียวกันทั้งรัน ; corpus golden ใช้ master ว่าง → index ว่าง (no-op)."""
    idx = {}
    if not isinstance(master, dict):
        return idx
    for key, m in master.items():
        if not isinstance(m, dict):
            continue
        t = clean_tax_id(m.get('tax_id') or '')
        if len(t) == 13:
            idx.setdefault(t, []).append((key, m))
    return idx


def _pick_branch_record(cands, bill_branch_no):
    """[TAXID-JOIN/ADR-146] เลือก record ที่ตรงสาขาของบิล เมื่อหลาย record แชร์ tax_id เดียว.
    ลำดับความเชื่อ (deterministic — เรียงตาม key ก่อน ไม่พึ่ง insertion order):
      (1) branch_no ตรงเป๊ะ → (2) สำนักงานใหญ่ (00000/มีคำ 'สำนัก') → (3) ตัวแรกตาม key."""
    if len(cands) == 1:
        return cands[0]
    cands = sorted(cands, key=lambda kv: kv[0])
    bn = re.sub(r'\D', '', str(bill_branch_no or ''))
    if bn:
        bn5 = bn.zfill(5)
        for key, m in cands:
            mbn = re.sub(r'\D', '', str(m.get('branch_no') or ''))
            if mbn and mbn.zfill(5) == bn5:
                return key, m
    for key, m in cands:                       # ไม่ระบุ/ไม่ตรงสาขา → เลือกสำนักงานใหญ่
        mbn = re.sub(r'\D', '', str(m.get('branch_no') or ''))
        if mbn.zfill(5) == '00000' or 'สำนัก' in str(m.get('branch') or ''):
            return key, m
    return cands[0]


def match_company(bill_company, master, bill_tax_id=None, bill_branch_no=None):
    """หา master record ของบิล.

    [TAXID-JOIN/ADR-146] เปลี่ยน join เป็น **tax_id-primary**: เลขภาษี 13 หลักเป็น join key
      เอกลักษณ์ (ชื่อเพี้ยน/ย่อ/สลับคำ/อังกฤษ/typo ไม่ทำให้ "ข้ามการตรวจตัวตนเงียบ" อีก).
      ถ้า clean_tax_id(bill_tax_id) = 13 หลัก ตรง record ใน master → คืน record นั้น score=100
      (แหล่ง=tax_id). หลาย record แชร์ tax_id (HQ+สาขา) → disambiguate ด้วย branch_no.
    คง **name matching เดิมไว้เป็น fallback** (เมื่อบิลไม่มี tax_id / tax_id ไม่อยู่ใน master) —
      กัน regression เคส master ที่ tax_id ขาด. ไม่แก้ logic ชื่อแม้บรรทัดเดียว.
    conservative: tax_id ตรงแต่ชื่อต่างมาก → ยัง match (ด้วย tax_id) ปล่อยกฎ TAX/CMP ที่มีอยู่
      เป็นตัวฟ้องความต่าง — logic join ไม่กลบกฎ.
    golden-neutral: corpus รันด้วย master ว่าง ({}) → index ว่าง → ตก fallback ชื่อเดิมเป๊ะ.
    """
    # [HARDEN/ADR-146] load_master() คืน None ได้ (ไฟล์ไม่มี/พัง) → coerce เป็น {} กัน
    #   `for ... in master.items()` (path ชื่อ) ครัช → run_rules โยน → bumper ข้ามทั้งบิล = FN.
    #   golden-NEUTRAL: corpus ส่ง dict ({}) เสมอ → no-op.
    if not isinstance(master, dict):
        master = {}
    # --- [TAXID-JOIN/ADR-146] tax_id-primary (เดินก่อนชื่อ) ---
    bt = clean_tax_id(bill_tax_id) if bill_tax_id is not None else ''
    if len(bt) == 13:
        cands = _master_taxid_index(master).get(bt)
        if cands:
            key, m = _pick_branch_record(cands, bill_branch_no)
            return key, m, 100
    # --- name matching (fallback เดิม — คัดลอกเป๊ะ ห้ามแก้ logic) ---
    bc = normalize_text(bill_company)
    if not bc: return None, None, 0
    for key, m in master.items():
        if not isinstance(m, dict): continue          # v6: ข้าม record ที่ไม่ใช่ dict (กัน master JSON พัง)
        mn = normalize_text(m.get('name', ''))            # v6: .get กัน KeyError ถ้า master ขาดคีย์
        ma = normalize_text(m.get('name_alt', ''))
        if key in bc or (mn and mn in bc) or (ma and ma in bc):   # v6: guard ค่าว่าง — '' in bc เป็น True เสมอ (เคยจับผิด)
            return key, m, 100
    best_key, best_score = None, 0
    for key, m in master.items():
        if not isinstance(m, dict): continue
        score = max(fuzz.partial_ratio(bc, normalize_text(m.get('name', ''))),
                    fuzz.partial_ratio(bc, key))
        if score > best_score: best_score = score; best_key = key
    if best_score >= CFG['FUZZY_NAME_THRESHOLD']:
        return best_key, master[best_key], best_score
    return None, None, best_score

def add_issue(b, code, rule, detail):
    b['issues'].append({'code':code,'severity':rule['severity'],
                        'category':rule['category'],'name':rule['name'],'detail':detail})

def normalize_company_name(value) -> str:
    """ทำความสะอาดชื่อบริษัทให้อยู่ในรูปมาตรฐานก่อนตรวจสอบ.

    ขั้นตอน normalization:
      - รองรับ None และ type อื่น ๆ โดยแปลงเป็น str อย่างปลอดภัย
      - ยุบ whitespace ทุกชนิด (space / tab / newline) ที่ติดกันให้เหลือช่องเดียว
      - ตัด whitespace หัวท้าย

    Args:
        value: ค่าที่รับเข้ามา อาจเป็น str, None, หรือ type อื่น.

    Returns:
        str: ชื่อบริษัทที่ normalize แล้ว — คืน '' หาก value เป็น None.
    """
    if value is None:
        return ''
    text: str = str(value)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def validate_company_prefix(name) -> bool:
    """ตรวจสอบว่าชื่อบริษัทขึ้นต้นด้วยคำนำหน้านิติบุคคลที่ถูกต้องหรือไม่.

    คำนำหน้าที่รองรับกำหนดไว้ใน COMPANY_PREFIXES รองรับทั้งกรณีมีและ
    ไม่มีช่องว่างหลังคำนำหน้า (เช่น 'บจก. XYZ' และ 'บจกXYZ').

    Args:
        name: ชื่อบริษัทที่ต้องการตรวจสอบ อาจเป็น str, None, หรือ type อื่น.

    Returns:
        bool: True หากขึ้นต้นด้วยคำนำหน้านิติบุคคลที่ถูกต้อง,
              False หากไม่ใช่ หรือชื่อว่างเปล่า.
    """
    normalized: str = normalize_company_name(name)
    if not normalized:
        return False
    return COMPANY_PREFIX_RE.match(normalized) is not None

def _kw_in_name(kw, name):
    """v9 [ACCURACY]: keyword match แบบกัน substring ของคำอื่น สำหรับคำสั้นกำกวม
    Business reason: ITM005 เลือก "หน่วยที่ควรใช้" ตามประเภทสินค้าจาก keyword — ถ้าจับคำผิด
      จะแนะนำหน่วยผิด = false positive. เดิม 'สี' (สีทาบ้าน) ไป match ใน 'เหล็กสี่เหลี่ยม'
      (สี+่=สี่) และ 'กระดาษกาวรองทาสี' (สี เป็นท้ายคำกริยา 'ทา') → ฟ้องหน่วยผิดเป็นหน่วยสี
    หลักการ: คำยาว/เฉพาะ → substring เดิมปลอดภัยพอ; คำสั้นกำกวม → ต้องอยู่ "ต้นคำ"
      (ขึ้นต้นชื่อ หรือ หลังช่องว่าง) และต้องไม่ตามด้วยสระ/วรรณยุกต์ (กลายเป็นคำอื่น)
    [F1/ADR-087]: kw=='สี' + คำบอกสีล้วน (สีดำ/สีขาว/สีเรียบ/สีน้ำตาล…) = "สีขยายความ
      สินค้า" ไม่ใช่สินค้า "สีทาบ้าน" → ข้าม match นี้ (กัน ITM005 false-positive ของ
      สวิตช์/สายไฟ/กระเบื้อง/ซิลิโคน). ยังจับ สีน้ำ/สีน้ำมัน/สีรองพื้น/สีอะคริลิค (สีจริง)
      เพราะ token paint-type ไม่อยู่ใน _SI_COLOR_ADJ (recall คงเดิม — พิสูจน์เซลล์ใน ADR-087).
    """
    if not kw or not name or kw not in name:
        return False
    if kw not in _AMBIG_SHORT_KW:
        return True
    for mt in re.finditer(re.escape(kw), name):
        nxt = name[mt.end()] if mt.end() < len(name) else ''
        if nxt in _THAI_MARKS:            # 'สี'+'่'='สี่' ฯลฯ → คนละคำ
            continue
        prev = name[mt.start() - 1] if mt.start() > 0 else ''
        if mt.start() == 0 or prev == ' ':  # อยู่ต้นคำเท่านั้น → ถือว่าเป็นสินค้าประเภทนั้นจริง
            if kw == 'สี':                 # [F1/ADR-087] กัน 'สี'+คำบอกสี = คำขยาย ไม่ใช่สินค้าสี
                rest = name[mt.end():]
                if any(rest.startswith(c) for c in _SI_COLOR_ADJ):
                    continue
            return True
    return False

def _build_cat_keywords():
    s = set()
    for cat in PRODUCT_CATEGORIES.values():
        s.update(cat['keywords'])
    state._CAT_KEYWORDS = s


# OBJ-MAINT: auto-export ทุกชื่อ (รวม helper _ และ import) → from-import * ได้ toolkit ครบ
__all__ = [n for n in list(globals().keys()) if not n.startswith('__') and n != 'annotations']
