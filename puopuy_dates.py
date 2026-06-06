# -*- coding: utf-8 -*-
"""puopuy_dates.py — DATE / IV-PERIOD parsing (core layer)

ฟังก์ชันแปลง/ตีความวันที่ และปีของงวด IV (พ.ศ./ค.ศ. 2–4 หลัก)
ย้ายมาจาก monolith แบบคัดลอกเป๊ะทุกตัวอักษร — logic เดิม 100%.

ตำแหน่งใน DAG:  config + puopuy_core(safe)  →  [puopuy_dates]  →  parser/validators  →  main
"""
import re
from datetime import datetime
import pandas as pd
from config import THAI_MONTHS
from puopuy_core import safe

try:
    import xlrd                       # v8.2: ใช้เฉพาะอ่านไฟล์ .xls (เก่า) — ไม่มีก็รัน .xlsx ได้ปกติ ไม่ crash ตอน import
except Exception:
    xlrd = None


def parse_date_any(v):
    if v is None or (isinstance(v, float) and pd.isna(v)): return None
    if isinstance(v, datetime):
        d = v
        if d.year > 2400: d = d.replace(year=d.year - 543)
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
                    if year < 100: year += 2500
                    if year > 2400: year -= 543
                    return datetime(year, mn, day)
                except Exception: pass
    # v8.6 [FIX-DATE-BE2]: วันที่ข้อความปีย่อ 2 หลัก (เช่น "5/5/69") = ปี พ.ศ. ย่อ (25YY) ในเอกสารไทย
    #   เดิมตก strptime '%d/%m/%y' → Python ตีความ "69" = ค.ศ. 1969 (ผิด) → DT004/IV003/IV004 ฟ้องผิด
    #   แก้ให้สอดคล้องกับสาขา "เดือนไทย" ด้านบน: 25YY (พ.ศ.) → -543 = ค.ศ. (69 → 2569 → 2026)
    m_yy = re.match(r'^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2})\s*$', s)
    if m_yy:
        try:
            day = int(m_yy.group(1)); mon = int(m_yy.group(2)); year = int(m_yy.group(3)) + 2500
            if year > 2400: year -= 543
            if 1 <= mon <= 12 and 1 <= day <= 31:
                return datetime(year, mon, day)
        except Exception: pass
    for fmt in ['%Y-%m-%d %H:%M:%S','%Y-%m-%d','%d/%m/%Y','%d/%m/%y','%d-%m-%Y','%d.%m.%Y']:
        try:
            d = datetime.strptime(s[:19] if len(s)>=19 else s[:10], fmt)
            if d.year > 2400: d = d.replace(year=d.year - 543)
            return d
        except Exception: pass
    return None


def _ivp_year2_to_ce(yy):
    """ปี 2 หลัก → (ปี ค.ศ., ฐาน) หรือ (None, None) ถ้าไม่อยู่ช่วงปีจริง"""
    if 58 <= yy <= 82:                 # พ.ศ. 2 หลัก (2558–2582)
        return (2500 + yy) - 543, 'พ.ศ.'
    if 15 <= yy <= 39:                 # ค.ศ. 2 หลัก (2015–2039)
        return 2000 + yy, 'ค.ศ.'
    return None, None

def _ivp_year4_to_ce(yyyy):
    """ปี 4 หลัก → (ปี ค.ศ., ฐาน) หรือ (None, None) ถ้าไม่อยู่ช่วงปีจริง"""
    if 2558 <= yyyy <= 2582:           # พ.ศ. 4 หลัก
        return yyyy - 543, 'พ.ศ.'
    if 2015 <= yyyy <= 2039:           # ค.ศ. 4 หลัก
        return yyyy, 'ค.ศ.'
    return None, None


__all__ = ["parse_date_any", "_ivp_year2_to_ce", "_ivp_year4_to_ce"]
