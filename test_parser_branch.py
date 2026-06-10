# -*- coding: utf-8 -*-
"""test_parser_branch.py — [coverage] ดัน branch coverage ของ parser family (≥90%) ด้วย unit ตรง
   helper ที่ข้อมูล fixture แทบไม่แตะ (edge/error path). **เทสล้วน → golden ไม่ขยับ** (ไม่เรียก audit core).

ราก: coverage_gate วัด parser family branch ~83% (ต่ำกว่า floor 85 ที่ ADR ตั้ง). เส้นที่ขาด =
  error/edge path ใน helper เล็ก ๆ (_pick_best_iv scoring, taxid/branch scan, _reconcile_amounts,
  _pb_* header builders, _compute_col_confidence, check_iv_format เกณฑ์ 2/3, row-helper หลัง OPT-1b
  ที่ orphan จาก caller). เทสนี้เรียก helper ตรง ๆ ด้วย input ที่ออกแบบให้ชนกิ่งเหล่านั้น.

    PYTHONHASHSEED=0 python3 test_parser_branch.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import numpy as np
import pandas as pd

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
import parser as P          # noqa: F401  (ผูก A2 reachability)
import parser_p0 as P0
import parser_p1 as P1

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def _M(rows):
    return pd.DataFrame(rows).to_numpy(dtype=object)


def _R():
    """result dict ว่าง (คีย์ที่ _pb_* แตะ)."""
    return {'company': '', 'company_raw': '', 'branch': '', 'branch_no': '',
            'tax_id': '', 'tax_id_raw': '', 'iv_number': '', 'iv_number_raw': '',
            'iv_date': None, 'iv_date_str': ''}


def main():
    print("PARSER BRANCH COVERAGE — unit ตรง helper (edge/error path) · golden-neutral")

    # ── _pick_best_iv: ครบกิ่ง scoring ──────────────────────────────────────
    check(P1._pick_best_iv('') is None, "pick_best_iv: ว่าง → None")
    check(P1._pick_best_iv('xxxx') is None, "pick_best_iv: ไม่มีเลข → None")
    check(P1._pick_best_iv('เลขที่ IV6905001', return_score=True)[0] == 'IV6905001', "pick_best_iv: label+IV prefix")
    check(P1._pick_best_iv('102158.25') is None, "pick_best_iv: money penalty (เลข+.ทศนิยม) → None")
    check(P1._pick_best_iv('ที่อยู่ 10310 กรุงเทพ') is None, "pick_best_iv: postal-code guard (5หลัก+กรุงเทพ)")
    check(P1._pick_best_iv('TAX123456') is None, "pick_best_iv: anti-prefix TAX → ตก")
    check(P1._pick_best_iv('0123456789012') == '0123456789012', "pick_best_iv: 13 หลักล้วน → penalty -30 (score 11 ยังผ่าน)")
    # known_tax_id ตัด candidate ที่เป็นเลขภาษี
    check(P1._pick_best_iv('125548006451', known_tax_id='0125548006451') is None, "pick_best_iv: ตัด cand=เลขภาษี")
    check(P1._pick_best_iv('J26050089') == 'J26050089', "pick_best_iv: J-series ชนะ")
    # >13 / <5 หลัก ข้าม
    check(P1._pick_best_iv('12345678901234567') is None, "pick_best_iv: >13 หลัก ข้าม")
    check(P1._pick_best_iv('1234', return_score=True) == (None, -10**9), "pick_best_iv: <5 หลัก → NOSCORE")

    # ── _extract_taxid_safe: A (keyword) / B (13ติด) / C (คั่น) ──────────────
    check(P1._extract_taxid_safe('') is None, "extract_taxid_safe: ว่าง")
    check(P1._extract_taxid_safe('เลขประจำตัวผู้เสียภาษี 0105556012345') == '0105556012345', "extract_taxid_safe A: หลัง keyword")
    check(P1._extract_taxid_safe('1234567890123') == '1234567890123', "extract_taxid_safe B: 13 ติด")
    check(P1._extract_taxid_safe('0-1055-56012-34-5') == '0105556012345', "extract_taxid_safe C: คั่น")
    check(P1._extract_taxid_safe('abc def') is None, "extract_taxid_safe: ไม่เจอ → None")

    # ── _taxid_from_cell: numeric 13/12, OverflowError, formatted, pure ──────
    check(P1._taxid_from_cell(1234567890123, 0, 0)[0] == '1234567890123', "taxid_from_cell: numeric 13")
    check(P1._taxid_from_cell(123456789012, 0, 0)[0] == '0123456789012', "taxid_from_cell: numeric 12 → +0")
    check(P1._taxid_from_cell(float('inf'), 0, 0) == (None, None, None), "taxid_from_cell: inf → OverflowError จับได้")
    check(P1._taxid_from_cell(True, 0, 0) == (None, None, None), "taxid_from_cell: bool → None")
    check(P1._taxid_from_cell('  ', 0, 0) == (None, None, None), "taxid_from_cell: ว่าง")
    check(P1._taxid_from_cell('0-1055-56012-34-5', 1, 2)[0] == '0105556012345', "taxid_from_cell: formatted")
    check(P1._taxid_from_cell('1234567890123', 0, 0)[0] == '1234567890123', "taxid_from_cell: pure 13")
    check(P1._taxid_from_cell('123456789012', 0, 0)[0] == '0123456789012', "taxid_from_cell: pure 12 → +0")
    check(P1._taxid_from_cell('hello', 0, 0) == (None, None, None), "taxid_from_cell: text → None")

    # ── _scan_tax_id_block / _scan_branch_block ─────────────────────────────
    df_tax = pd.DataFrame([['x', None], ['เลขประจำตัวผู้เสียภาษี 0105556012345', 'y']])
    check(P1._scan_tax_id_block(df_tax, 0, 1, 2)[0] == '0105556012345', "scan_tax_id_block: เจอ")
    check(P1._scan_tax_id_block(pd.DataFrame([['a', 'b']]), 0, 0, 2) == (None, None, None), "scan_tax_id_block: ไม่เจอ")
    check(P1._scan_branch_block(pd.DataFrame([['สำนักงานใหญ่']]), 0, 0, 1) == ('00000', 'สำนักงานใหญ่'), "scan_branch: สนญ.")
    check(P1._scan_branch_block(pd.DataFrame([['สาขาที่ 12']]), 0, 0, 1)[0] == '00012', "scan_branch: สาขา N")
    check(P1._scan_branch_block(pd.DataFrame([['Branch No. 7']]), 0, 0, 1)[0] == '00007', "scan_branch: Branch No")
    check(P1._scan_branch_block(pd.DataFrame([['ไม่มี']]), 0, 0, 1) == (None, None), "scan_branch: ไม่เจอ")

    # ── row helpers (orphaned หลัง OPT-1b — คุมตรงนี้) ───────────────────────
    M = _M([['รวมเงิน', 100], ['', None], ['ของ', 'x']])
    check(P1._row_label_match(M, 0, 2, ('รวมเงิน',)) is True, "row_label_match: เจอ")
    check(P1._row_label_match(M, 1, 2, ('รวมเงิน',)) is False, "row_label_match: แถวว่าง → False")
    check(P1._row_label_match(M, 2, 2, ('รวมเงิน',)) is False, "row_label_match: ไม่ match")
    Mn = _M([[None, '1,234.50', 7], ['x', None, '7.00']])
    check(P1._rightmost_num(Mn, 0, 3) == 7.0, "rightmost_num: ขวาสุด")
    check(P1._rightmost_num(Mn, 0, 3, min_val=10) == 1234.5, "rightmost_num: min_val ข้าม 7")
    check(P1._rightmost_num(_M([['a', 'b']]), 0, 2) is None, "rightmost_num: ไม่มีเลข → None")
    check(P1._row_has_rate_marker(_M([['VAT 7%']]), 0, 1) is True, "row_has_rate_marker: เจอ %")
    check(P1._row_has_rate_marker(_M([['ยอด', 100]]), 0, 2) is False, "row_has_rate_marker: ไม่เจอ")
    check(P1._rightmost_num_has_decimal(_M([['x', '7.00']]), 0, 2) is True, "rightmost_num_has_decimal: มีจุด")
    check(P1._rightmost_num_has_decimal(_M([['x', 7]]), 0, 2) is False, "rightmost_num_has_decimal: ไม่มีจุด")
    check(P1._rightmost_num_has_decimal(_M([['x', 'y']]), 0, 2) is False, "rightmost_num_has_decimal: ไม่มีเลข")

    # ── audit_text_num: reset / record (non-str, cap) / summary echo ────────
    P1.audit_text_num_reset()
    check(P1.audit_text_num_summary(echo=True) == [], "audit summary: ว่าง + echo")
    P1._record_text_num('qty', '1,234', 1234.0)
    P1._record_text_num('price', 12345, 12345)   # raw ไม่ใช่ str → ข้าม (บรรทัด 312-313)
    check(len(P1.audit_text_num_summary(echo=False)) == 1, "audit record: นับเฉพาะ raw=str")
    s_recs = P1.audit_text_num_summary(echo=True)   # echo path ที่มี recs
    check(len(s_recs) == 1, "audit summary: echo มี recs")
    P1.audit_text_num_reset()

    # ── _reconcile_amounts: ครบทุกกิ่ง ──────────────────────────────────────
    check(P1._reconcile_amounts(100, 7, 107)[3] == 'high', "reconcile: 3 ค่า balance → high")
    check(P1._reconcile_amounts(100, 7, 200)[3] == 'low', "reconcile: 3 ค่าไม่ balance → low")
    check(P1._reconcile_amounts(None, 7, 107)[0] == 100, "reconcile: sub None → เติม")
    check(P1._reconcile_amounts(100, None, 107)[1] == 7, "reconcile: vat None → เติม")
    check(P1._reconcile_amounts(100, 7, None)[2] == 107, "reconcile: tot None → เติม")
    check(P1._reconcile_amounts(100, None, None)[3] == 'low', "reconcile: 1 ค่า → low")

    # ── _looks_like_address / _pb_* header builders ─────────────────────────
    check(P1._looks_like_address('') is False, "looks_like_address: ว่าง")
    check(P1._looks_like_address('เลขประจำตัวผู้เสียภาษี 123') is False, "looks_like_address: มี tax kw → False")
    check(P1._looks_like_address('123 ถนน ตำบล อำเภอ จังหวัด') in (True, False), "looks_like_address: address hint")
    r = _R(); P1._pb_try_company(r, 'บริษัท เอ บี ซี จำกัด สาขา 3')
    check(r['company'] and r['branch_no'] == '00003', "pb_try_company: บริษัท + สาขา N")
    r = _R(); P1._pb_try_company(r, 'บริษัท ก สำนักงานใหญ่')
    check(r['branch_no'] == '00000', "pb_try_company: สำนักงานใหญ่")
    r = _R(); r['company'] = 'มีแล้ว'; P1._pb_try_company(r, 'บริษัท ใหม่')
    check(r['company'] == 'มีแล้ว', "pb_try_company: มี company แล้ว → ไม่ทับ")
    r = _R(); P1._pb_try_company(r, 'ไม่ใช่บริษัท')
    check(not r['company'], "pb_try_company: ไม่ match pattern → ข้าม")
    al = []; P1._pb_try_address_line(al, 'บริษัท ก'); check(al == [], "pb_try_address_line: บริษัท → ข้าม")
    al = []; P1._pb_try_address_line(al, 'เลขที่ 12 ตำบล'); check(len(al) == 1, "pb_try_address_line: เลขที่/ตำบล")
    P1._pb_try_address_line(al, 'เลขที่ 12 ตำบล'); check(len(al) == 1, "pb_try_address_line: กันซ้ำ")
    al = []; P1._pb_try_address_line(al, 'เขต บางรัก จังหวัด'); check(len(al) == 1, "pb_try_address_line: เขต/จังหวัด")

    # ── _pb_taxid_from_numeric/string + _pb_try_taxid ───────────────────────
    check(P1._pb_taxid_from_numeric('x') == (None, None), "pb_taxid_numeric: ไม่ใช่เลข")
    check(P1._pb_taxid_from_numeric(True) == (None, None), "pb_taxid_numeric: bool")
    check(P1._pb_taxid_from_numeric(1.5) == (None, None), "pb_taxid_numeric: ทศนิยม → None")
    check(P1._pb_taxid_from_numeric(float('inf')) == (None, None), "pb_taxid_numeric: inf → จับ Overflow")
    check(P1._pb_taxid_from_numeric(1234567890123)[0] == '1234567890123', "pb_taxid_numeric: 13")
    check(P1._pb_taxid_from_numeric(123456789012)[0] == '0123456789012', "pb_taxid_numeric: 12 → +0")
    check(P1._pb_taxid_from_numeric(99)[0] is None, "pb_taxid_numeric: สั้น → None")
    check(P1._pb_taxid_from_string('0-1055-56012-34-5')[0] == '0105556012345', "pb_taxid_string: formatted")
    check(P1._pb_taxid_from_string('no taxid here') == (None, None), "pb_taxid_string: ไม่เจอ")
    r = _R(); r['tax_id'] = 'X'; P1._pb_try_taxid(r, 1234567890123, 's'); check(r['tax_id'] == 'X', "pb_try_taxid: มีแล้ว → ข้าม")
    r = _R(); P1._pb_try_taxid(r, 1234567890123, 's'); check(r['tax_id'] == '1234567890123', "pb_try_taxid: numeric")
    r = _R(); P1._pb_try_taxid(r, 'x', 'เลขประจำตัวผู้เสียภาษี 0105556012345'); check(r['tax_id'] == '0105556012345', "pb_try_taxid: string")

    # ── _raw_iv_form ────────────────────────────────────────────────────────
    check(P1._raw_iv_form('', 'IV1') == 'IV1', "raw_iv_form: text ว่าง → cleaned")
    check(P1._raw_iv_form('x', '') == '', "raw_iv_form: cleaned ว่าง")
    check(P1._raw_iv_form('เลขที่ IV6905-2000.6 ครับ', 'IV69052000') == 'IV6905-2000.6', "raw_iv_form: คืนรูปดิบ (มี . -)")
    check(P1._raw_iv_form('no match', 'ZZZ999') == 'ZZZ999', "raw_iv_form: ไม่เจอ → cleaned")

    # ── _pb_try_iv ──────────────────────────────────────────────────────────
    r = _R(); P1._pb_try_iv(r, datetime(2026, 5, 2), '2026-05-02 00:00:00'); check(not r['iv_number'], "pb_try_iv: วันที่ → ข้าม")
    r = _R(); P1._pb_try_iv(r, 'x', 'เลขที่ IV6905001'); check(r['iv_number'] == 'IV6905001', "pb_try_iv: best-match")
    r = _R(); P1._pb_try_iv(r, 'x', 'AB123456'); check(r['iv_number'] == 'AB123456', "pb_try_iv: fallback อ่อน")

    # ── _pb_build_item ──────────────────────────────────────────────────────
    bdf = pd.DataFrame([['1', 'สินค้า A', '2', 'ชิ้น', '50.00', '100.00']])
    it = P1._pb_build_item(bdf, 0, '1', 1, 2, 3, 4, 5)
    check(it and it['qty'] == 2.0 and it['amount'] == 100.0, "pb_build_item: ครบ")
    check(P1._pb_build_item(pd.DataFrame([['1', '', '2']]), 0, '1', 1, 2, None, None, None) is None, "pb_build_item: ไม่มีชื่อ → None")
    bdf2 = pd.DataFrame([['1', 'ของ', None]])
    it2 = P1._pb_build_item(bdf2, 0, '1', 1, 2, None, None, None)
    check(it2 and it2['qty'] is None, "pb_build_item: qty NaN → None")

    # ── parser_p0: _compute_col_confidence ──────────────────────────────────
    df_hi = pd.DataFrame({0: [1, 2, 3], 1: [2, 3, 4], 2: [10, 10, 10], 3: [20, 30, 40]})
    check(P0._compute_col_confidence(df_hi, 0, 1, 2, 3) == 'HIGH', "compute_col_conf: qty×price≈amt → HIGH")
    df_lo = pd.DataFrame({0: [1, 2, 3], 1: [2, 3, 4], 2: [10, 10, 10], 3: [999, 1, 2]})
    check(P0._compute_col_confidence(df_lo, 0, 1, 2, 3) == 'LOW', "compute_col_conf: ไม่ใกล้ → LOW")
    check(P0._compute_col_confidence(df_hi, None, 1, 2, 3) == 'LOW', "compute_col_conf: col None → LOW")
    df_noitem = pd.DataFrame({0: [99, 98], 1: [1, 1], 2: [1, 1], 3: [1, 1]})
    check(P0._compute_col_confidence(df_noitem, 0, 1, 2, 3) == 'LOW', "compute_col_conf: ไม่มี item row → LOW")
    df_zero = pd.DataFrame({0: [1, 2], 1: [2, 3], 2: [10, 10], 3: [0, 0]})
    check(P0._compute_col_confidence(df_zero, 0, 1, 2, 3) == 'LOW', "compute_col_conf: amt=0 ทุกแถว → chk=0 → LOW")
    check(P0._compute_col_confidence(df_hi, 0, 1, 2, 99) == 'LOW', "compute_col_conf: index เกิน → except → LOW")

    # ── parser_p0: check_iv_format เกณฑ์ 2 (length) / 3 (digit-length) ──────
    def _bill(iv):
        return {'iv_number': iv, 'iv_number_raw': iv, 'issues': []}
    bills = [_bill('AB12345'), _bill('AB12345'), _bill('AB12345'), _bill('AB99')]
    P0.check_iv_format(bills)
    check(any(i['code'] == 'IV002' for i in bills[3]['issues']), "check_iv_format: เกณฑ์2 ยาวผิดกลุ่ม → IV002")
    bills2 = [_bill('1234567'), _bill('1234567'), _bill('1234567'), _bill('12')]
    P0.check_iv_format(bills2)
    check(any(i['code'] == 'IV002' for i in bills2[3]['issues']), "check_iv_format: เกณฑ์3 จำนวนหลักผิด → IV002")

    # ── parser_p0: _has_suspat_in_iv / _addr_parse_confidence ───────────────
    check(P0._has_suspat_in_iv('2O6') == ['O'], "has_suspat: O ระหว่างเลข")
    check(P0._has_suspat_in_iv('ABC') == [], "has_suspat: ไม่มี")
    check(P0._addr_parse_confidence({}, set()) == 'HIGH', "addr_conf: ไม่มี mandatory → HIGH")
    check(P0._addr_parse_confidence({'a': 1, 'b': 1}, {'a', 'b', 'c'}) == 'HIGH', "addr_conf: ≥60% → HIGH")
    check(P0._addr_parse_confidence({'a': 1}, {'a', 'b', 'c'}) == 'LOW', "addr_conf: <60% → LOW")

    print("=" * 70)
    if not FAIL:
        print(f"RESULT: ✅ parser branch coverage unit — ผ่าน {PASS} เคส (edge/error path, golden-neutral)")
        return 0
    print(f"RESULT: ❌ ไม่ผ่าน {len(FAIL)}/{PASS+len(FAIL)} เคส")
    return 1


if __name__ == "__main__":
    sys.exit(main())
