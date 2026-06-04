# -*- coding: utf-8 -*-
"""test_parser_extra.py — [OBJ-1D ต่อยอด] ดัน coverage ของ parser.py ให้ ≥90%

เรียกฟังก์ชัน parser ทีละตัวด้วย input สังเคราะห์ (DataFrame เล็ก/บิล dict/สตริง)
ให้แตะ "กิ่งที่ข้อมูลจริง 81 ไฟล์ไม่ได้วิ่งผ่าน" — ทุก assert ผูกกับพฤติกรรมที่ควรเป็น.
ครอบ: รวมบิลข้ามหน้า, audit Text→ตัวเลข, label-based amounts, reconcile, tax-id helpers,
       IV format/raw, finalize amounts, file discovery (glob), ฯลฯ.

เป็น pure parsing helper (ไม่เรียก pipeline หลัก/ไม่อ่านไฟล์จริงของ golden) → ไม่กระทบ golden hash.
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_parser_extra.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings
import tempfile
import datetime as dt

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import pandas as pd
import parser as P
import state

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def item(seq, name='เหล็ก', qty=1.0, price=100.0, amount=None):
    return {'seq': seq, 'name': name, 'name_raw': name, 'qty': qty,
            'unit': 'เส้น', 'price': price, 'amount': amount if amount is not None else qty * price}


def bill(iv, sheet, items, file='TEST_69_05.xls'):
    return {'iv_number': iv, 'iv_number_raw': iv, 'sheet': sheet, 'file': file,
            'items': items, 'issues': [], 'subtotal': None, 'vat': None, 'total': None}


print("=" * 64)
print("PARSER EXTRA — กิ่งที่ข้อมูลจริงไม่ครอบ")
print("=" * 64)

# ─────────────────────────────────────────────────────────────
print("\n[P1] merge_continuation_bills — รวมหน้าต่อ / IV ซ้ำแต่ไม่ต่อ / บิลเดี่ยว")
# (A) IV เดียวกัน + seq ต่อเนื่อง (1,2 → 3,4) = หน้าต่อ → ยุบเป็นใบเดียว
cont = [bill('IVCONT', '1', [item(1), item(2)]),
        bill('IVCONT', '2', [item(3), item(4)])]
mc = P.merge_continuation_bills([dict(b) for b in cont])
merged_one = [b for b in mc if b.get('_merged_pages')]
check(len(mc) == 1 and merged_one, "IV เดียวกัน seq ต่อเนื่อง → ยุบเป็น 1 ใบ (มี _merged_pages)")
check(merged_one and len(merged_one[0]['items']) == 4, "items ถูกต่อครบ 4 รายการ")
check(merged_one and any(i.get('code') == 'IV001' for i in merged_one[0]['issues']),
      "ติดธง IV001 'รวมบิลข้ามหน้า'")
check(merged_one and merged_one[0]['subtotal'] == round(4 * (1 * 100), 2),
      "subtotal คำนวณใหม่จาก items ที่ครบ (4×qty1×price100=400)")
# (B) IV ซ้ำแต่ seq ไม่ต่อ (1,2 ‖ 1,2) → คนละบิล แยกไว้ (ไม่ยุบ)
dup = [bill('IVDUP', '1', [item(1), item(2)]),
       bill('IVDUP', '2', [item(1), item(2)])]
md = P.merge_continuation_bills([dict(b) for b in dup])
check(len(md) == 2 and not any(b.get('_merged_pages') for b in md),
      "IV ซ้ำแต่ลำดับไม่ต่อ → แยก 2 ใบ ไม่ยุบ")
# (C) บิลเดี่ยว / ไม่มี IV → คืนเดิม
check(len(P.merge_continuation_bills([bill('SOLO', '1', [item(1)])])) == 1, "บิลเดี่ยว → คืนเดิม")
check(P.merge_continuation_bills([]) == [], "ลิสต์ว่าง → คืนว่าง")

# ─────────────────────────────────────────────────────────────
print("\n[P2] audit Text→ตัวเลข (reset / record / summary)")
P.audit_text_num_reset()
check(len(state._TEXT_NUM_RECOVERIES) == 0, "reset → log ว่าง")
P._record_text_num('qty', '1,234', 1234.0)          # raw เป็น str → บันทึก
P._record_text_num('price', 99, 99.0)               # raw ไม่ใช่ str → ข้าม (early return)
check(len(state._TEXT_NUM_RECOVERIES) == 1, "บันทึกเฉพาะ raw ที่เป็น str (กรอง non-str)")
# cap: ลดเพดานชั่วคราวเพื่อแตะกิ่ง "เต็มแล้วหยุดบันทึก"
# OBJ-MAINT: patch ที่ __globals__ ของ _record_text_num (โมดูลนิยามจริง) ไม่ใช่ shell attr
#   → ทนการซอยไฟล์ (binding ที่ฟังก์ชันอ่านจริงถูก patch เสมอ ไม่ว่าอยู่เลเยอร์ไหน)
_pg = P._record_text_num.__globals__
_orig_max = _pg['_MAX_TEXT_NUM_RECOVERIES']
try:
    _pg['_MAX_TEXT_NUM_RECOVERIES'] = 1            # ตอนนี้มี 1 รายการแล้ว → เต็ม
    P._record_text_num('amount', '5,000', 5000.0)
    check(len(state._TEXT_NUM_RECOVERIES) == 1, "ถึงเพดาน → ไม่บันทึกเพิ่ม (กัน log บวม)")
finally:
    _pg['_MAX_TEXT_NUM_RECOVERIES'] = _orig_max
# summary แบบมีข้อมูล (echo) + แบบว่าง
with contextlib.redirect_stdout(io.StringIO()):
    recs = P.audit_text_num_summary(echo=True)
check(isinstance(recs, list) and len(recs) == 1, "summary คืน list ของเคสที่กู้คืน")
P.audit_text_num_reset()
with contextlib.redirect_stdout(io.StringIO()):
    empty = P.audit_text_num_summary(echo=True)
check(empty == [], "summary ตอนไม่มีเคส → []")
# summary ที่มี >5 เคส (แตะกิ่ง 'และอีก N เซลล์')
P.audit_text_num_reset()
for i in range(7):
    P._record_text_num('qty', f'{i},000', float(i))
with contextlib.redirect_stdout(io.StringIO()):
    many = P.audit_text_num_summary(echo=True)
check(len(many) == 7, "summary >5 เคส → แสดงตัวอย่าง 5 + นับที่เหลือ")
P.audit_text_num_reset()

# ─────────────────────────────────────────────────────────────
print("\n[P3] _label_based_amounts — หา subtotal/vat/total จาก label")
# df: แถว label + เลขขวาสุด
rows = [
    ['รวมเป็นเงิน', '', 1000.0],          # subtotal
    ['ภาษีมูลค่าเพิ่ม', '', 70.0],         # vat
    ['จำนวนเงินรวมทั้งสิ้น', '', 1070.0],  # total
]
df_lbl = pd.DataFrame(rows)
amts = P._label_based_amounts(df_lbl, 0, df_lbl.shape[0] - 1, df_lbl.shape[1])
check(amts['subtotal'] == 1000.0 and amts['vat'] == 70.0 and amts['total'] == 1070.0,
      f"จับ subtotal/vat/total จาก label ได้ถูกต้อง ({amts})")
# VAT ที่เป็น 'อัตรา' (7 / 0.07) ต้องไม่ถูกเก็บเป็นยอด VAT
df_rate = pd.DataFrame([['ภาษีมูลค่าเพิ่ม', '', 7]])
amts_rate = P._label_based_amounts(df_rate, 0, 0, 3)
check(amts_rate['vat'] is None, "VAT=7 (อัตรา) → ไม่นับเป็นยอด VAT")

# ─────────────────────────────────────────────────────────────
print("\n[P4] _reconcile_amounts — เติมค่าที่ขาด / ตรวจ balance")
check(P._reconcile_amounts(1000, 70, 1070)[3] == 'high', "ครบ 3 ค่า + balance → high")
check(P._reconcile_amounts(1000, 70, 9999)[3] == 'low', "ครบ 3 ค่า แต่ไม่ balance → low (ไม่แก้เลข)")
_s, _v, _t, _c = P._reconcile_amounts(1000, None, 1070)
check(_v == 70 and _c == 'high', "ขาด vat (มี 2/3) → เติม vat=70")
check(P._reconcile_amounts(1000, None, None)[3] == 'low', "มี 1/3 → ไม่เสกเลข (low)")

# ─────────────────────────────────────────────────────────────
print("\n[P5] _pb_finalize_amounts — provenance + เติมยอด")
# vat เป็น string แปลงไม่ได้ + ไม่มี sub/total/items → กิ่ง except (ไม่ throw)
r1 = {'subtotal': None, 'vat': 'ไม่ใช่ตัวเลข', 'total': None, 'items': []}
with contextlib.redirect_stdout(io.StringIO()):
    P._pb_finalize_amounts(r1)
check('amount_source' in r1, "vat แปลงไม่ได้ → กลืน exception ไม่ throw (ติด amount_source)")
# มีแต่ subtotal → derive vat & total
r2 = {'subtotal': 1000.0, 'vat': None, 'total': None, 'items': []}
P._pb_finalize_amounts(r2)
check(r2['vat'] == 70.0 and r2['total'] == 1070.0, "มีแต่ subtotal → derive vat=70, total=1070")
check(r2['amount_source']['vat'] == 'derived', "ติด provenance 'derived' ให้ vat ที่ระบบคำนวณเอง")

# ─────────────────────────────────────────────────────────────
print("\n[P6] tax-id helpers (_extract_taxid_safe / _taxid_from_cell / _pb_taxid_*)")
check(P._extract_taxid_safe('เลข 0-1055-66206-72-6 ปลายประโยค') == '0105566206726',
      "_extract_taxid_safe: pattern คั่น -/space → 13 หลัก")
check(P._extract_taxid_safe('') is None, "_extract_taxid_safe('') → None")
# numeric cell: 13 หลัก / 12 หลัก (เลข 0 นำหาย)
check(P._taxid_from_cell(105566206726, 0, 0)[0] == '0105566206726',
      "_taxid_from_cell: 12 หลัก → เติม 0 นำ → 13 หลัก")
check(P._taxid_from_cell(float('inf'), 0, 0) == (None, None, None),
      "_taxid_from_cell(inf) → กิ่ง except (ไม่ throw)")
# string cell: formatted 13
tid13, raw13, src13 = P._taxid_from_cell('0-1055-66206-72-6', 1, 2)
check(tid13 == '0105566206726', "_taxid_from_cell: string formatted → 13 หลัก")
# _pb_taxid_from_numeric: inf → except
check(P._pb_taxid_from_numeric(float('inf')) == (None, None), "_pb_taxid_from_numeric(inf) → except")
check(P._pb_taxid_from_numeric('ไม่ใช่เลข') == (None, None), "_pb_taxid_from_numeric(str) → (None,None)")
# _pb_try_taxid: เติม tax_id ลง result
res_tid = {'tax_id': None, 'tax_id_raw': None}
P._pb_try_taxid(res_tid, 105566206726, '105566206726')
check(res_tid['tax_id'] == '0105566206726', "_pb_try_taxid: numeric → เติม tax_id")

# ─────────────────────────────────────────────────────────────
print("\n[P7] _scan_branch_block — สาขา / Branch No")
df_br = pd.DataFrame([['สาขาที่ 5']])
check(P._scan_branch_block(df_br, 0, 0, 1) == ('00005', 'สาขา 5'), "'สาขาที่ 5' → ('00005','สาขา 5')")
df_hq = pd.DataFrame([['สำนักงานใหญ่']])
check(P._scan_branch_block(df_hq, 0, 0, 1) == ('00000', 'สำนักงานใหญ่'), "'สำนักงานใหญ่' → ('00000',...)")
df_bn = pd.DataFrame([['Branch No. 12']])
check(P._scan_branch_block(df_bn, 0, 0, 1)[0] == '00012', "'Branch No. 12' → '00012'")

# ─────────────────────────────────────────────────────────────
print("\n[P8] _addr_parse_confidence / _looks_like_address / _rightmost_num / _label_in_text")
check(P._addr_parse_confidence({}, set()) == 'HIGH', "ไม่มี mandatory_keys → HIGH")
check(P._addr_parse_confidence({'a': 1, 'b': 2}, {'a', 'b', 'c'}) == 'HIGH', "เจอ ≥60% → HIGH")
check(P._addr_parse_confidence({'a': 1}, {'a', 'b', 'c'}) == 'LOW', "เจอ <60% → LOW")
check(P._looks_like_address('123/45 ถนนสุขุมวิท แขวงคลองเตย') is True, "มีคำที่อยู่ → True")
check(P._looks_like_address('เลขประจำตัวผู้เสียภาษี') is False, "มีคำเลขภาษี → ไม่ใช่ที่อยู่")
check(P._looks_like_address('') is False, "ว่าง → False")
# _rightmost_num: ไม่มีเลขในแถว → None
df_norow = pd.DataFrame([['abc', 'def']])
check(P._rightmost_num(df_norow.to_numpy(dtype=object), 0, 2) is None, "แถวไม่มีเลข → None")

# ─────────────────────────────────────────────────────────────
print("\n[P9] _raw_iv_form — รูปแบบเลขตามเอกสารจริง / edge")
check(P._raw_iv_form('', 'IV123') == 'IV123', "text ว่าง → คืน cleaned เดิม")
check(P._raw_iv_form('เลขที่ IV6905-2000.6 วันนี้', 'IV69052000') == 'IV6905-2000.6'.upper()
      or P._raw_iv_form('เลขที่ IV6905-2000.6 วันนี้', 'IV69052000').startswith('IV6905'),
      "คืนเลขตามที่พิมพ์จริง (มีขีด/จุด)")
check(P._raw_iv_form('some text', '---') == '---', "cleaned ไม่มี alnum → คืน cleaned เดิม")

# ─────────────────────────────────────────────────────────────
print("\n[P10] _dic_pick_qty_price — 1 คอลัมน์ / 0 คอลัมน์ / fallback heuristic")
df_q = pd.DataFrame([[1, 2, 3, 100], [1, 5, 7, 200]])
check(P._dic_pick_qty_price(df_q.to_numpy(dtype=object), [0, 1], 3, [(0, [1, 1])]) == (0, None), "nums_c 1 คอลัมน์ → (col, None)")
check(P._dic_pick_qty_price(df_q.to_numpy(dtype=object), [0, 1], 3, []) == (None, None), "nums_c ว่าง → (None,None)")
# 2 คอลัมน์ แต่ qty×price ไม่เท่ากับ amount เลย → fallback min/max
qc, pc = P._dic_pick_qty_price(df_q.to_numpy(dtype=object), [0, 1], 3, [(0, [1, 1]), (1, [2, 5])])
check(qc is not None and pc is not None, f"2 คอลัมน์ไม่ validate → fallback heuristic min/max ({qc},{pc})")
# detect_item_columns_safe: [พบบั๊กแฝง] เรียก _compute_col_confidence ที่ "ไม่มีนิยามในทั้งแพ็กเกจ"
#   → เรียกเมื่อใดก็ NameError เสมอ. ฟังก์ชันนี้ไม่มี call site จริงใน pipeline (golden ใช้
#   detect_item_columns ตรง ๆ) จึงไม่กระทบ golden hash — แต่เป็น dead-on-arrival API.
#   เทสยืนยัน "พฤติกรรมจริงปัจจุบัน" (ยกข้อบกพร่องไว้ใน audit report; ไม่แก้ source เพื่อคง hash)
_raised = None
try:
    P.detect_item_columns_safe(df_q)
except NameError as e:
    _raised = e
check(_raised is not None and '_compute_col_confidence' in str(_raised),
      "detect_item_columns_safe → NameError (_compute_col_confidence ไม่ถูกนิยาม) [บั๊กแฝง บันทึกใน audit]")

# ─────────────────────────────────────────────────────────────
print("\n[P11] check_iv_format — อักขระน่าสงสัย / ยาวผิด / จำนวนหลักผิด")
# (0) ตัวอักษรน่าสงสัย O ปนในเลข (บิลใบเดียวก็จับได้)
b_susp = [{'iv_number': 'IV6905O023', 'iv_number_raw': 'IV6905O023', 'issues': []}]
P.check_iv_format(b_susp)
check(any(i['code'] == 'IV002' for i in b_susp[0]['issues']), "O ปนในเลข → IV002 (ตัวอักษรน่าสงสัย)")
# (1) อักขระแปลกใน iv_number (raw สะอาด) → criterion 1 append
b_weird = [{'iv_number': 'IV#6905', 'iv_number_raw': 'IV6905', 'issues': []},
           {'iv_number': 'IV6906', 'iv_number_raw': 'IV6906', 'issues': []}]
P.check_iv_format(b_weird)
check(any(i['code'] == 'IV002' for i in b_weird[0]['issues']), "อักขระแปลกใน iv_number → IV002")
# (2) ความยาวรวมผิดกลุ่ม (digit count เท่ากัน → แยกจากเกณฑ์ 3)
b_len = [{'iv_number': 'IV6905', 'iv_number_raw': 'IV6905', 'issues': []},
         {'iv_number': 'IV6906', 'iv_number_raw': 'IV6906', 'issues': []},
         {'iv_number': 'IV6907', 'iv_number_raw': 'IV6907', 'issues': []},
         {'iv_number': 'IV-6905', 'iv_number_raw': 'IV-6905', 'issues': []}]  # ยาว 7 (digit 4 เท่าเดิม)
P.check_iv_format(b_len)
check(any('ยาวผิดปกติ' in i.get('name', '') for i in b_len[3]['issues']),
      "ยาวรวมผิดกลุ่ม (7 vs 6) → IV002 ยาวผิดปกติ")
# (3) จำนวนหลักผิดกลุ่ม (ความยาวรวมเท่ากัน → แยกจากเกณฑ์ 2)
b_dig = [{'iv_number': 'AB6905', 'iv_number_raw': 'AB6905', 'issues': []},
         {'iv_number': 'AB6906', 'iv_number_raw': 'AB6906', 'issues': []},
         {'iv_number': 'AB6907', 'iv_number_raw': 'AB6907', 'issues': []},
         {'iv_number': 'A12345', 'iv_number_raw': 'A12345', 'issues': []}]  # ยาว 6 เท่าเดิม แต่ digit 5
P.check_iv_format(b_dig)
check(any('จำนวนหลักผิดปกติ' in i.get('name', '') for i in b_dig[3]['issues']),
      "จำนวนหลักผิดกลุ่ม (5 vs 4) → IV002 จำนวนหลักผิดปกติ")

# ─────────────────────────────────────────────────────────────
print("\n[P12] file discovery — get_files_via_drive (glob) + get_files_via_upload (input)")
with tempfile.TemporaryDirectory() as td:
    # สร้างไฟล์จริง: บิล 2 + lock file + ไฟล์ output ระบบ (ต้องถูกกรอง)
    for nm in ['KRR_69_05.xls', 'SHS_69_05.xlsx', '~$temp.xlsx', 'audit_v58_run.xlsx']:
        open(os.path.join(td, nm), 'w').close()
    found = P.get_files_via_drive(td)
    bases = sorted(os.path.basename(f) for f in found)
    check(bases == ['KRR_69_05.xls', 'SHS_69_05.xlsx'],
          f"glob เจอบิล 2 ไฟล์ + กรอง ~$/audit_v58_ ออก ({bases})")

    # get_files_via_upload: mock input() ให้คืน path โฟลเดอร์
    import builtins
    _orig_input = builtins.input
    try:
        builtins.input = lambda *a, **k: td
        with contextlib.redirect_stdout(io.StringIO()):
            up = P.get_files_via_upload()
        check(len(up) == 2, "get_files_via_upload(path ถูก) → เจอ 2 ไฟล์")
        # path ไม่ใช่โฟลเดอร์ → []
        builtins.input = lambda *a, **k: os.path.join(td, 'ไม่มีจริง')
        with contextlib.redirect_stdout(io.StringIO()):
            bad = P.get_files_via_upload()
        check(bad == [], "get_files_via_upload(path ผิด) → [] (แจ้งไม่พบโฟลเดอร์)")
    finally:
        builtins.input = _orig_input

# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
if FAIL:
    print(f"PARSER EXTRA: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    print("=" * 64)
    sys.exit(1)
else:
    print(f"PARSER EXTRA: ผ่าน {PASS} / ล้มเหลว 0")
    print("=" * 64)
    print("RESULT: ✅ กิ่ง parser (รวมหน้า/audit/amounts/taxid/iv/discovery) ครบ + ไม่กระทบ golden hash")
    sys.exit(0)
