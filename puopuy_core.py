# -*- coding: utf-8 -*-
"""puopuy_core.py — LEAF UTILITY LAYER (ชั้นล่างสุดของ DAG)

ฟังก์ชัน normalize/clean/validate ระดับ primitive ที่ "ไม่มี side effect"
และไม่พึ่งฟังก์ชันอื่นในระบบ (พึ่งแค่ re / unicodedata / pandas และกันเอง).
ย้ายมาจาก monolith แบบคัดลอกเป๊ะทุกตัวอักษร — logic เดิม 100%.

ตำแหน่งใน DAG:  config/state  →  [puopuy_core]  →  parser/rules/reporting  →  main
"""
from __future__ import annotations

from typing import Any, Callable

import re
import unicodedata
import pandas as pd


def to_conf01(score_0_to_100: Any) -> float:
    try: return max(0.0, min(1.0, float(score_0_to_100) / 100.0))
    except Exception: return 0.0


def normalize_text(s: Any) -> str:
    if s is None or (isinstance(s, float) and pd.isna(s)): return ''
    s = str(s).replace('\xa0',' ').replace('\u200b','').replace('\ufeff','').replace('\u3000',' ')
    s = unicodedata.normalize('NFC', s)
    # สระอำที่ถูกพิมพ์แบบแยกส่วน: nikhahit ◌ํ (U+0E4D) + สระอา า (U+0E32) → สระอำ ำ (U+0E33)
    #   เรนเดอร์เหมือนกันแต่ NFC ไม่ fold ให้ → ทำให้ match literal 'สำนักงานใหญ่'/'จำกัด' พลาด (เช่น 'สํานักงานใหญ่')
    s = s.replace('\u0e4d\u0e32', '\u0e33')
    s = re.sub(r'\s+', ' ', s)                              # ยุบช่องว่าง/บรรทัดก่อน (คงขอบคำ)
    return re.sub(r'[\x00-\x1F\x7F-\x9F]', '', s).strip()   # แล้วค่อยลบ control chars กัน openpyxl/Excel พัง

def has_hidden_chars(s: Any) -> list[str]:
    """v5.8 [FIX-4] + v5.8q PATCH 1: เตือนเฉพาะ NBSP/ZWS/BOM
    (space ธรรมดาซ้อน → normalize เงียบ ๆ ไม่เตือน)"""
    if not s: return []
    s = str(s); out = []
    if '\xa0' in s: out.append('NBSP (Non-Breaking Space — มักจาก copy PDF/Word)')
    if '\u200b' in s: out.append('ZWS (Zero-Width Space — มองไม่เห็น)')
    if '\ufeff' in s: out.append('BOM (Byte-Order Mark — header ของไฟล์ unicode)')
    return out

_THAI_ARABIC_DIGITS = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')  # [C-2/ADR-074] เลขไทย → อารบิก
# [BS-1/ADR-114] เลข full-width ０-９ (U+FF10–FF19) → อารบิก. เจอบ่อยตอน copy เลขภาษีจาก PDF/ระบบบางตัว
#   เดิม translate ไม่ครอบ full-width แล้ว re.sub([^0-9]) (ASCII) ตัดทิ้ง → เลขภาษีหายทั้งก้อน → ''
#   → ระบบขึ้น "ไม่พบเลขภาษี" หลอก + checksum/เทียบทะเบียน/TAX005/008 ทำไม่ได้ (corpus=0 → golden-neutral)
_FULLWIDTH_DIGITS = str.maketrans('０１２３４５６７８９', '0123456789')


def clean_tax_id(s: Any) -> str:
    """ตัดอักขระทั้งหมดที่ไม่ใช่ตัวเลข + รองรับ Excel quirks
    v5.8b: handle float (.0 suffix), int, apostrophe prefix
    [C-2/ADR-074] แปลงเลขไทย ๐-๙ → อารบิกก่อน strip — เดิม re.sub(\\D) แบบ Unicode รับเลขไทยเป็น "หลัก"
    แต่ไม่แปลง → ผ่าน TAX001/002 ว่า valid แต่เทียบ master อารบิกไม่ตรง → TAX003 ฟ้อง "อันตราย" ผิด
    + TAX005/008 (anti-fraud สวมเลข) พลาด. แปลงจุดเดียวที่นี่ ครอบทุกกฎเลขภาษี."""
    if s is None: return ''
    # v5.8b: ถ้าเป็น numeric → แปลงเป็น int ก่อน (ตัด .0 จาก xlrd float)
    if isinstance(s, float):
        try:
            if s == int(s): s = int(s)
        except (ValueError, OverflowError): pass
    if isinstance(s, int):
        return str(s)
    t = str(s)
    # Excel's leading apostrophe (text prefix)
    if t.startswith("'") or t.startswith("\u2018"): t = t[1:]
    # v5.8b: ตัด trailing .0 ที่มาจาก float → string
    t = re.sub(r'\.0+$', '', t)
    t = t.replace('\xa0','').replace('\u200b','').replace('\ufeff','').replace('\u3000','')
    for dash in ['–','—','−','‐']:
        t = t.replace(dash, '-')
    t = t.translate(_THAI_ARABIC_DIGITS)   # [C-2/ADR-074] เลขไทย → อารบิก ก่อน strip
    t = t.translate(_FULLWIDTH_DIGITS)     # [BS-1/ADR-114] full-width ０-９ → อารบิก ก่อน strip
    return re.sub(r'[^0-9]', '', t)        # ASCII digits เท่านั้น (กันเลข Unicode อื่นหลุดเป็น "หลัก")

def _taxid_checksum_ok(digits: Any) -> bool:
    """v7: ตรวจ checksum เลขประจำตัวผู้เสียภาษี/บัตรประชาชนไทย 13 หลัก (mod 11)
       หลักที่ 13 = (11 - (Σ d_i × (13-i) , i=0..11) mod 11) mod 10
       คืน True ถ้าผ่าน / False ถ้าไม่ผ่าน
       รับเฉพาะสตริงตัวเลข 13 หลัก — กรณีอื่นคืน True (= ไม่ตัดสินที่นี่ ให้กฎความยาว/ตัวเลขจัดการ)
       ออกแบบให้ปลอดภัย: ผิดปกติใด ๆ → คืน True (ไม่สร้าง false positive)
    """
    if not (isinstance(digits, str) and len(digits) == 13 and digits.isdigit()):
        return True
    try:
        s = sum(int(digits[i]) * (13 - i) for i in range(12))
        return (11 - (s % 11)) % 10 == int(digits[12])
    except Exception:
        return True

def remove_branch_suffix(name: Any) -> str:
    return re.sub(r'\s*\((สำนักงานใหญ่|สาขา[^\)]*)\)\s*$', '', normalize_text(name)).strip()

def _raw_company_form(value: Any) -> str:
    """v5.9 [FIX-CMP004]: คืนชื่อบริษัทแบบ "ดิบ" — คงจำนวนช่องว่างเดิมไว้
    (ต่างจาก normalize_text ที่ยุบ \\s+ เป็นช่องเดียว ทำให้ตรวจเว้นวรรคเกินไม่ได้)
    ทำแค่: ล้างอักขระล่องหน (NBSP/ZWS/BOM/ideographic space), NFC, ตัด suffix สาขา/สนญ.
    """
    if value is None:
        return ''
    s = str(value)
    s = s.replace('\xa0', ' ').replace('\u200b', '').replace('\ufeff', '').replace('\u3000', ' ')
    s = unicodedata.normalize('NFC', s)
    s = re.sub(r'\s*\((สำนักงานใหญ่|สาขา[^\)]*)\)\s*$', '', s)
    return s.strip()

def extract_branch(name: Any) -> str:
    m = re.search(r'\((สำนักงานใหญ่|สาขา[^\)]*)\)', str(name))
    return m.group(1) if m else ''

def safe(fn: Callable[[], Any], default: Any = None) -> Any:
    try: return fn()
    except Exception: return default


__all__ = [
    "to_conf01", "normalize_text", "has_hidden_chars", "clean_tax_id",
    "_taxid_checksum_ok", "remove_branch_suffix", "_raw_company_form", "extract_branch", "safe",
]
