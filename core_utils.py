# -*- coding: utf-8 -*-
"""core_utils.py — Shared Helpers (leaf layer ของ DAG)

ฟังก์ชัน "ฐานราก/ตัวช่วย" ที่หลายโมดูลใช้ร่วม — ย้ายมาจาก main แบบ **คัดลอกเป๊ะ** (logic เดิม 100%).
จุดประสงค์: ให้ analytics/reporting นำเข้าตัวช่วยจากที่นี่ แทนการวิ่งกลับไปขอจาก main
            → ตัด circular dependency (analytics -> main, reporting -> main) ให้โค้ดไหลทางเดียว

ตำแหน่งใน DAG (พึ่งเฉพาะ leaf — ไม่พึ่ง main/validators/analytics/reporting):
    config + puopuy_core  →  [core_utils]  →  (ใช้โดย analytics, reporting, main)
"""
from __future__ import annotations

import re
from datetime import datetime

from config import _PP20_LABELS  # [F3] explicit (เดิม `from config import *`)
from puopuy_core import normalize_text


def clean_pp20_address(raw):
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


def parse_address_input(addr_text):
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


def sort_bills_by_date(bills):
    return sorted(bills, key=lambda b: (b['iv_date'] or datetime.max, b['file'], str(b['sheet'])))


__all__ = ['clean_pp20_address', 'parse_address_input', 'sort_bills_by_date']
