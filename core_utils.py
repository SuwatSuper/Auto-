# -*- coding: utf-8 -*-
"""core_utils.py — Shared Helpers (leaf layer ของ DAG)

ฟังก์ชัน "ฐานราก/ตัวช่วย" ที่หลายโมดูลใช้ร่วม — ย้ายมาจาก main แบบ **คัดลอกเป๊ะ** (logic เดิม 100%).
จุดประสงค์: ให้ analytics/reporting นำเข้าตัวช่วยจากที่นี่ แทนการวิ่งกลับไปขอจาก main
            → ตัด circular dependency (analytics -> main, reporting -> main) ให้โค้ดไหลทางเดียว

ตำแหน่งใน DAG (พึ่งเฉพาะ leaf — ไม่พึ่ง main/validators/analytics/reporting):
    config + puopuy_core  →  [core_utils]  →  (ใช้โดย analytics, reporting, main)
"""
from __future__ import annotations

from typing import Any

import math
import re
from datetime import datetime

from config import _PP20_LABELS  # [F3] explicit (เดิม `from config import *`)
from puopuy_core import normalize_text

try:                                    # [L4] อักขระควบคุมที่ openpyxl ปฏิเสธ
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE as _XL_ILLEGAL
except Exception:
    _XL_ILLEGAL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _df_safe(df):
    """[L4 2026-06-20] เตรียม DataFrame ก่อน to_excel (full-mode report): sanitize อักขระควบคุม (\\x07) ใน
    เซลล์ข้อความ (กัน IllegalCharacterError = export คืน False) + coerce float NaN/±inf → 0 (กัน `or 0`
    ปล่อย nan เป็นเซลล์ว่าง). คลีนสตริง/เลขจำกัดไม่เปลี่ยน → report-determinism ไม่ขยับ.
    (วางที่ leaf นี้ ไม่ใช่ reporting_p0 เพื่อคงไฟล์นั้น ≤600 LOC ตาม invariant F4)."""
    def _c(v):
        if isinstance(v, str):
            return _XL_ILLEGAL.sub('', v)
        if isinstance(v, float) and not math.isfinite(v):
            return 0
        return v
    try:
        return df.map(_c)
    except Exception:
        return df


def clean_pp20_address(raw: Any) -> str:
    """ล้างที่อยู่ที่ก๊อปจากเว็บ ภ.พ.20 — ตัด label ที่ตามด้วย '-' (ไม่มีข้อมูล)
    เก็บเฉพาะ label ที่มีข้อมูลจริง คืนเป็นบรรทัดเดียว
    เช่น 'อาคาร - ห้องเลขที่ - เลขที่ 450/18 ตรอก/ซอย - ถนนอนามัยงามเจริญ ...'
      → 'เลขที่ 450/18 ถนนอนามัยงามเจริญ ...'
    """
    if not raw:
        return ''
    s = str(raw)
    # รวมบรรทัด/tab → ช่องว่างเดียว
    s = re.sub(r'[\r\n\t]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # normalize dash ทุกชนิด → '-'
    for dash in ['–','—','−','‐','‑']:
        s = s.replace(dash, '-')

    # ตัด pattern "label -" (label ตามด้วยขีดที่ไม่มีข้อมูล)
    # ครอบทั้ง "อาคาร -", "อาคาร-", "ห้องเลขที่ - ", "ตรอก/ซอย -"
    labels_re = '|'.join(re.escape(l) for l in sorted(_PP20_LABELS, key=len, reverse=True))
    # label + (ช่องว่าง?) + '-' + (ตามด้วยช่องว่างหรือ label ถัดไปหรือจบ)
    s = re.sub(rf'(?:{labels_re})\s*-(?=\s|$)', ' ', s)

    # เก็บกวาดขีดเดี่ยว ๆ ที่ลอยอยู่ (มี space ขนาบ) แต่คงขีดในชื่อ เช่น 450/18 ไม่โดน
    s = re.sub(r'(?<=\s)-(?=\s)', ' ', s)
    s = re.sub(r'^-\s|\s-$', ' ', s)

    # ยุบช่องว่างซ้ำ
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def parse_address_input(addr_text: Any) -> dict[str, str]:
    """v5.8 [FIX-2]: เพิ่ม ซ. ใน soi pattern"""
    parts = {}
    addr_text = normalize_text(addr_text)
    pats = [
        # v9.3 [FIX-HOUSENO]: 'เลขที่' = บ้านเลขที่จริง แต่ต้องไม่ไปจับ 'ห้องเลขที่ 104' (เลขห้อง)
        #   ภพ.20 วาง 'ห้องเลขที่ 104 ... เลขที่ 303/1' → เดิม regex จับ 104 (เลขห้อง) เป็นบ้านเลขที่ผิด
        ('house_no', r'(?<!ห้อง)เลขที่\s*([^\s]+)'),
        ('moo', r'หมู่ที่\s*(\d+)'),
        # v5.8: เพิ่ม "ซ." (ซอย แบบย่อ)
        # v5.8 [FIX-2]: รองรับ "ตรอก/ซอย", "ซ.", "ตรอก-ซอย", และมีช่องว่างระหว่าง
        ('soi', r'(?:ตรอก\s*[/\-]?\s*ซอย|ซอย|ตรอก|ซ\.)\s*([^\s,/]+(?:\s+\d+(?:/\d+)?)?)'),
        ('road', r'ถนน\s*([^\s]+(?:\s+[^\s]+)?)'),
        ('subdistrict', r'(?:แขวง|ตำบล)\s*([^\s]+)'),
        ('district', r'(?:เขต|อำเภอ)\s*([^\s]+)'),
        ('province', r'จังหวัด\s*([^\s]+)'),
        ('zipcode', r'\b(\d{5})\b'),
    ]
    for key, pat in pats:
        m = re.search(pat, addr_text)
        if m: parts[key] = m.group(1).strip()
    if 'province' not in parts and 'กรุงเทพ' in addr_text:
        parts['province'] = 'กรุงเทพมหานคร'
    return parts


def sort_bills_by_date(bills: list[dict]) -> list[dict]:
    return sorted(bills, key=lambda b: (b['iv_date'] or datetime.max, b['file'], str(b['sheet'])))


def iv_digits_garbage(iv: Any) -> str | None:
    """[D1/D2] เลขใบกำกับ (เฉพาะส่วนตัวเลข) เป็น 'ขยะ' ไหม — คืนเหตุผล (str) หรือ None ถ้าปกติ.

    single-source ใช้ร่วม: r_iv007 (กฎ flag) + parser guard _pb_try_iv (กัน parser คว้าเศษ float ของยอด
    เป็นเลขเอกสาร เช่น '1416233.0000000002' → '0000000002'). conservative: เลขรูปแบบสมเหตุผล → None.
    """
    digits = re.sub(r'\D', '', str(iv or ''))
    if not digits:
        return None
    if set(digits) == {'0'}:                               # ศูนย์ล้วน
        return "เป็นศูนย์ล้วน"
    if len(digits) >= 4 and len(set(digits)) == 1:         # เลขเดียวซ้ำทั้งหมด
        return "เป็นเลขเดียวซ้ำทั้งหมด"
    if len(digits) >= 8 and len(digits.lstrip('0')) <= 2:  # placeholder (ศูนย์นำเกือบทั้งหมด)
        return f"เป็น placeholder (ศูนย์นำเกือบทั้งหมด เหลือ '{digits.lstrip('0') or '0'}')"
    return None


def iv_amount_fragment(iv: Any, subtotal: Any = None, vat: Any = None, total: Any = None) -> bool:
    """[D1/D2] เลข iv เป็น 'เศษทศนิยม/ตรงทั้งก้อนของยอดเงิน' ไหม — จับ parser คว้าเศษ float ของยอด
    (เช่น iv '0000000002' จาก VAT '1416233.0000000002'). conservative: ยาว ≥6 ถึงเทียบ. single-source."""
    digits = re.sub(r'\D', '', str(iv or ''))
    if not digits or len(digits) < 6:
        return False
    for v in (total, vat, subtotal):
        if not isinstance(v, (int, float)):
            continue
        s = repr(float(v))
        if digits == re.sub(r'\D', '', s):                 # iv = ทั้งก้อนตัวเลขของยอด
            return True
        if '.' in s:
            frac = re.sub(r'\D', '', s.split('.', 1)[1])
            if frac and (digits == frac or (len(frac) >= 6 and digits in frac)):
                return True
    return False


def validate_iv_post(bill: dict | None) -> bool:
    """[D2-GUARD] post-extraction: ปฏิเสธ iv_number ที่เป็นเลขขยะ/มาจากยอดเงิน → ตั้งว่าง (mutate).

    เรียก "หลัง parse ครบ" (มีทั้ง iv + ยอด) — ไม่แก้ flow การ extract. ถ้า iv เป็น all-zeros/ซ้ำ/
    placeholder หรือเป็นเศษ/ตรงยอดเงิน → ตั้ง iv_number='' เพื่อให้ IV005 (ไม่มีเลข)/IV007 จับ
    ("ซื่อสัตย์กว่าโชว์เลขผิด"). คืน True ถ้าปฏิเสธ. conservative: เลขรูปแบบสมเหตุผล → ไม่แตะ.
    """
    b = bill or {}
    iv = str(b.get('iv_number', '') or '').strip()
    if not iv:
        return False
    if iv_digits_garbage(iv) or iv_amount_fragment(iv, b.get('subtotal'), b.get('vat'), b.get('total')):
        b['iv_number'] = ''
        b['iv_number_raw'] = ''
        return True
    return False


__all__ = ['clean_pp20_address', 'parse_address_input', 'sort_bills_by_date',
           'iv_digits_garbage', 'iv_amount_fragment', 'validate_iv_post']
