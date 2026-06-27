# -*- coding: utf-8 -*-
"""test_adr119_audit_fixes.py — [ADR-119] whole-system audit fixes (golden-neutral)

ครอบบั๊กที่พบจากการรีเช็คทั้งระบบ (5 subagents: perf/robustness/resource/rules/parser) — ทุกข้อ corpus delta=0:
  • Robustness F1: _cell_to_num สาขา string ปล่อย ±inf เข้ายอดเงินเงียบ → กัน non-finite (เหมือนสาขา numeric)
  • Robustness F2: _cell_to_num(int ใหญ่ >1.8e308) → OverflowError ไม่ถูกดัก → คืน None
  • Rules F1: ADDR001 \\b\\d{5}\\b หา zip ติดอักษรไทยไม่เจอ (false ERROR) → lookaround
  • Rules F1b: ADDR001 ไม่รับ 'กทม' → เพิ่ม
  • Perf F3: match_company memoize master normalize (byte-identical กับ logic เดิม)
  • Report R1/R2: ชีต xlsx เขียน control char ดิบ → IllegalCharacterError ทั้งไฟล์ → sanitize

self-contained (ไม่พึ่ง corpus). exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


# ── Robustness F1/F2: _cell_to_num ────────────────────────────────────────────
from parser_p0a import _cell_to_num
_check("F1 string ตัวเลขยาว 9*400 → None (เดิม inf เข้ายอดเงินเงียบ)", _cell_to_num('9' * 400) is None)
_check("F1 accounting-neg (9*400) → None (เดิม -inf)", _cell_to_num('(' + '9' * 400 + ')') is None)
_check("F2 huge int 9*309 → None (เดิม OverflowError crash)", _cell_to_num(int('9' * 309)) is None)
_check("ค่าปกติไม่ regress: '12345'→12345.0", _cell_to_num('12345') == 12345.0)
_check("ค่าปกติไม่ regress: '1,234.50'→1234.5", _cell_to_num('1,234.50') == 1234.5)
_check("ค่าปกติไม่ regress: '(100.00)'→-100.0", _cell_to_num('(100.00)') == -100.0)
_check("ค่าปกติไม่ regress: 999999999999.99 (13 หลัก) finite", _cell_to_num('999999999999.99') == 999999999999.99)

# ── Rules F1/F1b: ADDR001 ─────────────────────────────────────────────────────
from rules_engine_rules_a import r_addr001
def _A(addr):
    return r_addr001({'address': addr}, None, {})
_check("F1 zip ติดอักษรไทย 'กรุงเทพฯ10110' → เงียบ (เดิม false ERROR)",
       _A('123 ถ.สุขุมวิท กรุงเทพฯ10110') == [])
_check("zip เว้นวรรค 'กรุงเทพ 10110' → เงียบ (ไม่ regress)", _A('123 ถ.สุขุมวิท กรุงเทพ 10110') == [])
_check("F1b 'กทม.' → เงียบ (เดิมรับแค่ 'กรุงเทพ')", _A('1 ถ.พระราม4 กทม. 10500') == [])
_check("ไม่มี zip จริง → ยังฟ้อง", 'ไม่พบรหัสไปรษณีย์ 5 หลัก' in _A('123 ถ.สุขุมวิท กรุงเทพ'))
_check("ไม่มีจังหวัด/เขต → ยังฟ้อง", any('จังหวัด' in x for x in _A('123 ซอย 5 10110')))
_check("ที่อยู่ว่าง → ฟ้องไม่พบที่อยู่", _A('') == ['ไม่พบที่อยู่'])
# zip 5 หลักต้องไม่ match เลข 6+ หลัก (lookaround กันเลขยาว)
_check("เลข 6 หลักไม่นับเป็น zip", 'ไม่พบรหัสไปรษณีย์ 5 หลัก' in _A('123 ถ.x กรุงเทพ 123456'))

# ── Perf F3: match_company byte-equivalent กับ logic เดิม ──────────────────────
from rules_engine_base import match_company, normalize_text, fuzz, CFG
def _old_match(bc_in, master):
    bc = normalize_text(bc_in)
    if not bc:
        return None, None, 0
    for key, mm in master.items():
        if not isinstance(mm, dict):
            continue
        mn = normalize_text(mm.get('name', '')); ma = normalize_text(mm.get('name_alt', ''))
        if key in bc or (mn and mn in bc) or (ma and ma in bc):
            return key, mm, 100
    bk, bs = None, 0
    for key, mm in master.items():
        if not isinstance(mm, dict):
            continue
        sc = max(fuzz.partial_ratio(bc, normalize_text(mm.get('name', ''))), fuzz.partial_ratio(bc, key))
        if sc > bs:
            bs = sc; bk = key
    if bs >= CFG['FUZZY_NAME_THRESHOLD']:
        return bk, master[bk], bs
    return None, None, bs
_suf = ['จำกัด', 'มหาชน', 'คอนสตรัคชั่น', 'กรุ๊ป', 'เทรดดิ้ง']
_master = {}
for i in range(120):
    nm = 'บริษัท ' + chr(0x0e01 + i % 40) + chr(0x0e01 + (i * 7) % 40) + ' ' + _suf[i % len(_suf)]
    _master['K%03d' % i] = {'name': nm, 'name_alt': (nm.replace('บริษัท', 'บจก.') if i % 3 else ''), 'tax_id': '01055%08d' % i}
_master['BAD'] = 'not-a-dict'
_names = [v['name'] for k, v in _master.items() if isinstance(v, dict)]
_bills = _names[:40] + [n.replace('บริษัท', '') for n in _names[40:60]] + ['บริษัท ไม่มีจริง จำกัด', '', None]
_mis = 0
for b in _bills:
    o = _old_match(b, _master); n = match_company(b, _master)
    if (o[0], o[2]) != (n[0], n[2]) or (o[1] is not n[1]):
        _mis += 1
_check(f"F3 match_company == logic เดิม ({len(_bills)} เคส, master 120) — byte-identical", _mis == 0)

# ── Report R1/R2: sanitize control char → xlsx เซฟผ่าน ────────────────────────
import openpyxl
import build_consolidated_report as _bcr
_wb = openpyxl.Workbook()
_bcr._write_sheet(_wb, 'T', [{'file': 'f\x07', 'sheet': 's', 'iv': 'i', 'spot': 'x', 'category': 'c',
                              'summary': 'sum\x07', 'codes': 'X', 'n_codes': 1, 'max_severity': 'INFO', 'example': 'e\x07'}])
try:
    _bcr  # noqa
    _buf = io.BytesIO(); _wb.save(_buf); _r2 = True
except Exception:
    _r2 = False
_check("R2 consolidated report เขียน control char → เซฟผ่าน (เดิม IllegalCharacterError)", _r2)

import reporting_p0 as _rp
_rp._SYSTEM_ISSUES.append({'severity': 'INFO', 'code': 'SYS-X', 'category': 'SYSTEM',
                           'name': 'n', 'file': 'f\x07', 'sheet': 's', 'detail': 'd\x07et'})
try:
    import pandas as _pd
    with _pd.ExcelWriter(io.BytesIO()) as _w:
        _rp._xlsx_sheet_system_issues(_w)
    _r1 = True
except Exception:
    _r1 = False
finally:
    _rp._SYSTEM_ISSUES.clear()
_check("R1 System Issues sheet เขียน control char → เซฟผ่าน", _r1)

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] ADR-119 audit fixes — robustness/rules/perf/report ครบ golden-neutral")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
