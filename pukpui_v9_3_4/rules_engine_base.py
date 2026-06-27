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

# [ADR-119/PERF-F3] normalize ชื่อ master เป็น cost คงที่ต่อ run แต่เดิม match_company (เรียกต่อบิล)
#   re-normalize master "ทั้งก้อน ×2 รอบ" ทุกบิล → O(บิล × master) ของ normalize_text. master ใหญ่
#   (mission: หลายพันบริษัท) → ช้ามากใน production (golden test ใช้ master ว่างจึงซ่อน cost นี้).
#   แก้: precompute (key, norm_name, norm_alt, m) ครั้งเดียวต่อ master (cache fingerprint = (id,len)
#   แบบเดียวกับ _XBILL_IDX_CACHE/ADR-103) → เรียกซ้ำต่อบิล = O(1) lookup. pure precompute: ค่า/ลำดับ/
#   tie-break เท่าเดิมเป๊ะ → byte-identical (golden-neutral, มี test equivalence คุม).
_MATCH_MASTER_CACHE = {'fp': None, 'rows': None}


def _match_master_rows(master):
    fp = (id(master), len(master))
    if _MATCH_MASTER_CACHE['fp'] != fp:
        rows = []
        for key, m in master.items():
            if not isinstance(m, dict):               # ข้าม record ที่ไม่ใช่ dict (กัน master JSON พัง) — เหมือนเดิม
                continue
            rows.append((key, normalize_text(m.get('name', '')), normalize_text(m.get('name_alt', '')), m))
        _MATCH_MASTER_CACHE.update(fp=fp, rows=rows)
    return _MATCH_MASTER_CACHE['rows']


def match_company(bill_company, master):
    bc = normalize_text(bill_company)
    if not bc: return None, None, 0
    rows = _match_master_rows(master)                 # normalize master ครั้งเดียวต่อ run (เดิมทำซ้ำทุกบิล)
    for key, mn, ma, m in rows:
        if key in bc or (mn and mn in bc) or (ma and ma in bc):   # v6: guard ค่าว่าง — '' in bc เป็น True เสมอ (เคยจับผิด)
            return key, m, 100
    best_key, best_score = None, 0
    for key, mn, ma, m in rows:
        score = max(fuzz.partial_ratio(bc, mn),
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
