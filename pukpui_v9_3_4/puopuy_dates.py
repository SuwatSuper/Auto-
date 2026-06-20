# -*- coding: utf-8 -*-
"""puopuy_dates.py — DATE / IV-PERIOD parsing (core layer)

ฟังก์ชันแปลง/ตีความวันที่ และปีของงวด IV (พ.ศ./ค.ศ. 2–4 หลัก)
ย้ายมาจาก monolith แบบคัดลอกเป๊ะทุกตัวอักษร — logic เดิม 100%.

ตำแหน่งใน DAG:  config + puopuy_core(safe)  →  [puopuy_dates]  →  parser/validators  →  main
"""
from __future__ import annotations

from typing import Any

import re
from datetime import datetime
import pandas as pd
from config import THAI_MONTHS
from puopuy_core import safe

try:
    import xlrd                       # v8.2: ใช้เฉพาะอ่านไฟล์ .xls (เก่า) — ไม่มีก็รัน .xlsx ได้ปกติ ไม่ crash ตอน import
except Exception:
    xlrd = None


def parse_date_any(v: Any) -> datetime | None:
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    if isinstance(v, datetime):
        d = v
        # [M1] กัน ValueError: 29 ก.พ. ของปี พ.ศ.อธิกสุรทินที่ ค.ศ.(ปี-543) ไม่ใช่ปีอธิกสุรทิน
        #   (เช่น datetime(2568,2,29) → replace 2025 ระเบิด "day out of range"). เดิมไม่ห่อ → ครัช
        #   หลุดถึง parse_file → "ไฟล์ทั้งไฟล์หาย". safe() คืน None แทน. วันปกติ → เหมือนเดิม (golden ไม่ขยับ).
        if d.year > 2400:
            return safe(lambda: v.replace(year=v.year - 543))
        return d
    if isinstance(v, (int, float)):
        if 30000 < v < 70000:
            if xlrd is not None:
                return safe(lambda: xlrd.xldate_as_datetime(v, 0))
            # [M9] ไม่มี xlrd → fallback pandas (Excel serial origin 1899-12-30). เดิมคืน None
            #   เพราะ xlrd.xldate_as_datetime โยน AttributeError แล้ว safe() กลืน → iv_date หาย.
            #   golden ไม่ขยับ: เครื่อง golden มี xlrd → กิ่งนี้ไม่ทำงาน.
            return safe(lambda: (pd.Timestamp('1899-12-30') + pd.to_timedelta(int(v), unit='D')).to_pydatetime())
        return None
    s = str(v).strip()
    for thai_month, mn in THAI_MONTHS.items():
        if thai_month in s:
            m = re.search(r'(\d{1,2})\s*' + re.escape(thai_month) + r'\s*(\d{2,4})', s)
            if m:
                try:
                    day = int(m.group(1)); year = int(m.group(2))
                    if year < 100:
                        # [P1-FIX วันที่ 2 หลัก] ใช้กติกาเดียวกับ _ivp_year2_to_ce (กัน divergence 2 ที่):
                        #   58-82=พ.ศ.ย่อ→ค.ศ., 15-39=ค.ศ.ย่อ (2015-2039). นอกช่วง→ถือเป็น พ.ศ.ย่อเดิม.
                        _ce = _ivp_year2_to_ce(year)[0]
                        year = _ce if _ce is not None else year + 2500
                    if year > 2400: year -= 543
                    return datetime(year, mn, day)
                except Exception: pass
    # v8.6 [FIX-DATE-BE2]: วันที่ข้อความปีย่อ 2 หลัก (เช่น "5/5/69") = ปี พ.ศ. ย่อ (25YY) ในเอกสารไทย
    #   เดิมตก strptime '%d/%m/%y' → Python ตีความ "69" = ค.ศ. 1969 (ผิด) → DT004/IV003/IV004 ฟ้องผิด
    #   แก้ให้สอดคล้องกับสาขา "เดือนไทย" ด้านบน: 25YY (พ.ศ.) → -543 = ค.ศ. (69 → 2569 → 2026)
    # [L9] อนุญาตเวลาต่อท้าย (เช่น '5/5/69 10:00:00') — เดิม anchor $ ตัดทิ้ง → ตก strptime → None
    m_yy = re.match(r'^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?\s*$', s)
    if m_yy:
        try:
            day = int(m_yy.group(1)); mon = int(m_yy.group(2)); yy = int(m_yy.group(3))
            # [P1-FIX วันที่ 2 หลัก] เดิมตี yy เป็น พ.ศ.ย่อเสมอ (yy+2500-543) → "1/1/15"→1972 ผิด.
            #   ใช้กติกาเดียวกับ _ivp_year2_to_ce: 15-39=ค.ศ.(2015-2039), 58-82=พ.ศ.→ค.ศ.(2015-2039).
            #   นอกช่วงรู้จัก→ถือเป็น พ.ศ.ย่อเดิม. ปี 66-69 (corpus ปัจจุบัน) อยู่ช่วง 58-82 → ผลเท่าเดิมเป๊ะ.
            _ce = _ivp_year2_to_ce(yy)[0]
            year = _ce if _ce is not None else (yy + 2500) - 543
            if 1 <= mon <= 12 and 1 <= day <= 31:
                return datetime(year, mon, day)
        except Exception: pass
    for fmt in ['%Y-%m-%d %H:%M:%S','%Y-%m-%d','%d/%m/%Y','%d/%m/%y','%d-%m-%Y','%d.%m.%Y']:
        try:
            d = datetime.strptime(s[:19] if len(s)>=19 else s[:10], fmt)
            if d.year > 2400: d = d.replace(year=d.year - 543)
            return d
        except Exception: pass
    # [BUGFIX recheck #5] กู้วันอธิกสุรทินปี พ.ศ. 4 หลัก (fallback หลัง strptime ล้ม) —
    #   strptime สร้าง datetime(2567,2,29) "ก่อน" ลบ 543 → 2567 ไม่ใช่ปีอธิกสุรทิน → ล้ม →
    #   คืน None ทั้งที่ 29/2/2567 (=ค.ศ.2024) เป็นวันจริง. ที่นี่แปลงปี "ก่อน" สร้าง datetime จึงผ่าน.
    #   วางเป็น fallback ท้ายสุด → วันปกติยังวิ่งผ่าน strptime เดิมทุกเคส (golden ไม่ขยับ).
    for _m4 in (re.match(r'^\s*(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\s*$', s),        # ปีหน้า: yyyy-mm-dd
                re.match(r'^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})\s*$', s)):     # ปีหลัง: dd/mm/yyyy
        if not _m4:
            continue
        try:
            g = _m4.groups()
            if len(g[0]) == 4:                       # yyyy-mm-dd
                yr4, mon, day = int(g[0]), int(g[1]), int(g[2])
            else:                                    # dd/mm/yyyy
                day, mon, yr4 = int(g[0]), int(g[1]), int(g[2])
            if yr4 > 2400:                           # พ.ศ. → ค.ศ. (เกณฑ์เดียวกับ strptime path)
                yr4 -= 543
            return datetime(yr4, mon, day)           # สร้างหลังแปลงปี → อธิกสุรทินถูกต้อง
        except Exception:
            pass
    return None


def _ivp_year2_to_ce(yy: int) -> tuple[int | None, str | None]:
    """ปี 2 หลัก → (ปี ค.ศ., ฐาน) หรือ (None, None) ถ้าไม่อยู่ช่วงปีจริง
    [T-1 FIX 11.06.69] ขยายเพดาน 82→99 / 39→56 (เดิมหมดอายุ พ.ศ.2582/ค.ศ.2039 —
    ระเบิดเวลา: ปี 83+ จะตก fallback yy+2500-543 ได้ปีเพี้ยน). ช่วง 40–57 คงตีความไม่ได้
    โดยตั้งใจ (กำกวมระหว่างฐาน — คืน None ให้ชั้นบนตัดสิน). corpus ปัจจุบัน 66–69 ไม่กระทบ."""
    if 58 <= yy <= 99:                 # พ.ศ. 2 หลัก (2558–2599)
        return (2500 + yy) - 543, 'พ.ศ.'
    if 15 <= yy <= 39:                 # ค.ศ. 2 หลัก (2015–2039)
        return 2000 + yy, 'ค.ศ.'
    return None, None

def _ivp_year4_to_ce(yyyy: int) -> tuple[int | None, str | None]:
    """ปี 4 หลัก → (ปี ค.ศ., ฐาน) หรือ (None, None) ถ้าไม่อยู่ช่วงปีจริง
    [T-1 FIX 11.06.69] ขยายเพดานเช่นเดียวกับปี 2 หลัก (2582→2599 / 2039→2056)."""
    if 2558 <= yyyy <= 2599:           # พ.ศ. 4 หลัก
        return yyyy - 543, 'พ.ศ.'
    if 2015 <= yyyy <= 2056:           # ค.ศ. 4 หลัก
        return yyyy, 'ค.ศ.'
    return None, None


__all__ = ["parse_date_any", "_ivp_year2_to_ce", "_ivp_year4_to_ce"]
