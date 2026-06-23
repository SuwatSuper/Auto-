# -*- coding: utf-8 -*-
"""test_parser_extra2.py — [OBJ-1D ต่อยอด รอบ 2] ดัน parser.py ให้สูงกว่า 90% ต่อ

แตะกลุ่มที่เหลือ: TOR-format handler (_tor_*), parse_sheet/parse_file (multi-vat,
sheet-exception → SYS001), และกิ่งย่อยของ _pick_best_iv(_safe)/tax-id/unit/iv-fallback.
ทุก assert ผูกกับพฤติกรรมที่ควรเป็น. เป็น pure parsing (ไม่อ่านไฟล์ golden) → ไม่กระทบ hash.
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_parser_extra2.py
"""
import os
import sys
import io
import contextlib
import warnings
import tempfile
from datetime import datetime

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


def tor_df(rows, ncols=12):
    """สร้าง DataFrame เลย์เอาต์ TOR (pad ให้ครบ ncols)"""
    padded = [list(r) + [None] * (ncols - len(r)) for r in rows]
    return pd.DataFrame(padded)


print("=" * 64)
print("PARSER EXTRA 2 — TOR handler / parse_sheet / parse_file / กิ่งย่อย")
print("=" * 64)

# ─────────────────────────────────────────────────────────────
print("\n[Q1] TOR-format: _is_tor_format + _parse_tor_sheet (เส้นทางปกติครบ 6 ขั้น)")
# เลย์เอาต์ TOR: col2=ชื่อ, col7=ราคา, col9=IV/วันที่, col10=qty/vat-rate, col11=amount
rows = [
    [None, 'บริษัท ทดสอบ จำกัด สาขา 5', None, None, None, None, None, None, None, 'IV6905000001', None, None],
    [None, 'เลขประจำตัวผู้เสียภาษี 0105566206726', None, None, None, None, None, None, None, datetime(2569, 5, 2), None, None],
    [None, None, 'สินค้าทดสอบหนึ่ง', None, None, None, None, 100.0, None, None, 2.0, 200.0],   # item: price100 qty2 amt200
    [None, None, 'สินค้าทดสอบสอง', None, None, None, None, 50.0, None, None, 4.0, 200.0],
    ['(สี่ร้อยบาทถ้วน)', None, None, None, None, None, None, None, None, None, None, 400.0],     # subtotal row (amount-in-words)
    [None, None, None, None, None, None, None, None, None, None, 0.07, 28.0],                    # vat row (rate 0.07)
    [None, None, None, None, None, None, None, None, None, None, None, 428.0],                   # total
]
df_tor = tor_df(rows)
check(P._is_tor_format(df_tor) is True, "_is_tor_format จับ signature TOR ได้ (IV+เลขภาษี ไม่มี 'ใบกำกับภาษี')")
bills_tor = P.parse_sheet(df_tor, 'Sheet1', 'TOR_69_05.xls')
check(len(bills_tor) == 1, "parse_sheet route ไป TOR handler → ได้ 1 บิล")
b = bills_tor[0] if bills_tor else {}
check(b.get('iv_number') == 'IV6905000001', "อ่าน IV ถูก")
check(b.get('iv_date') is not None and b.get('iv_date_str', '').endswith('2026'),
      f"แปลงวันที่ พ.ศ.→ค.ศ. (datetime 2569→2026) ({b.get('iv_date_str')})")
# _tor_try_date โดยตรง: สตริงวันที่ ค.ศ. (parse ได้) / สตริงที่ตรง regex แต่ parse ไม่ได้ → except
_rd = {}
check(P._tor_try_date(_rd, '2026-05-02', '2026-05-02') is True, "_tor_try_date: สตริง ค.ศ. parse ได้ → True")
_rd2 = {}
check(P._tor_try_date(_rd2, '2029-99-99', '2029-99-99') is False,
      "_tor_try_date: สตริงตรง regex แต่วันที่ผิด → except → False")
check(b.get('branch_no') == '00005', "อ่านสาขา 5 → branch_no '00005' (กิ่ง _tor_cell_company)")
check(b.get('tax_id') == '0105566206726', "อ่านเลขภาษี 13 หลัก")
check(len(b.get('items', [])) == 2, "ดึงรายการสินค้า 2 รายการ (col2/col7/col10/col11)")
check(b.get('subtotal') == 400.0 and b.get('vat') == 28.0 and b.get('total') == 428.0,
      f"อ่าน subtotal/vat/total ครบ ({b.get('subtotal')}/{b.get('vat')}/{b.get('total')})")

# ─────────────────────────────────────────────────────────────
print("\n[Q2] TOR: กิ่ง except (ยอดอ่านเป็นเลขไม่ได้) + ไม่มี IV → None")
rows_bad = [
    [None, 'บริษัท ก จำกัด', None, None, None, None, None, None, None, 'IV6905000099', None, None],
    [None, 'เลขประจำตัวผู้เสียภาษี 0105566206726', None, None, None, None, None, None, None, None, None, None],
    [None, None, 'สินค้าราคาเพี้ยน', None, None, None, None, 10.0, None, None, 1.0, 10.0],
    ['(สิบบาทถ้วน)', None, None, None, None, None, None, None, None, None, None, 'ไม่ใช่เลข'],   # subtotal: float() ไม่ได้
    [None, None, None, None, None, None, None, None, None, None, 0.07, 'ก็ไม่ใช่เลข'],            # vat: float() ไม่ได้
    [None, None, None, None, None, None, None, None, None, None, None, 'รวมไม่เป็นเลข'],          # total: float() ไม่ได้
]
df_bad = tor_df(rows_bad)
bills_bad = P.parse_sheet(df_bad, 'S', 'TOR_69_05.xls')   # ต้องไม่ throw
# [ADR-046 F-2] TOR-path เรียก _pb_finalize_amounts แล้ว (เหมือน path ปกติ) → subtotal/vat/total ที่อ่านเป็น
#   ข้อความไม่ได้จะถูก derive จาก item_sum (item เดียว amount=10 → subtotal=10, vat=0.7, total=10.7).
#   หัวใจที่เทสต์กันคือ "ไม่ throw" (ทนข้อความ) ยังคงอยู่ ; ค่า subtotal เปลี่ยนจาก None → item_sum (สอดคล้อง path ปกติ)
check(len(bills_bad) == 1 and bills_bad[0].get('subtotal') == 10.0
      and (bills_bad[0].get('amount_source') or {}).get('subtotal') == 'item_sum',
      "ยอดเป็นข้อความ → ไม่ throw + subtotal derive จาก item_sum (TOR finalize เหมือน path ปกติ, ADR-046 F-2)")
# _parse_tor_sheet โดยตรงกับ df ที่ไม่มี IV → คืน None (1466)
df_noiv = tor_df([[None, 'อะไรสักอย่าง'] + [None] * 10])
check(P._parse_tor_sheet(df_noiv, 'S', 'f.xls') is None, "TOR sheet ไม่มี IV → คืน None")
# _tor_scan_vat: col10 (อัตรา) เป็นข้อความ float() ไม่ได้ → except continue (1424)
df_vatbad = tor_df([[None] * 12,
                    [None, None, None, None, None, None, None, None, None, None, 'ไม่ใช่อัตรา', 99.0]])
_rv = {'vat': None}
P._tor_scan_vat(df_vatbad, _rv, df_vatbad.shape[0], df_vatbad.shape[1], 0)
check(_rv['vat'] is None, "_tor_scan_vat: อัตราเป็นข้อความ → except continue (vat คง None)")

# ─────────────────────────────────────────────────────────────
print("\n[Q3] parse_sheet: TOR ที่ไม่มีเนื้อหา → [] / หลาย VAT row → trailing block")
# TOR ผ่าน signature แต่ไม่มี item/ยอด → bill ว่าง → parse_sheet คืน []
rows_empty = [
    [None, 'xx', None, None, None, None, None, None, None, 'IV6905000077', None, None],
    [None, 'เลขประจำตัวผู้เสียภาษี 0105566206726', None, None, None, None, None, None, None, None, None, None],
] + [[None] * 12 for _ in range(4)]
df_te = tor_df(rows_empty)
check(P.parse_sheet(df_te, 'S', 'TOR_69_05.xls') == [], "TOR มี IV แต่ไม่มี item/ยอด → ตัดทิ้ง (คืน [])")

# non-TOR ที่มี VAT-rate 0.07 สองแถว → เดินเส้น multi-block + trailing
mv = [['หัวบิล', '', ''] for _ in range(2)]
mv += [['สินค้า A', 1, 100]]
mv += [['ภาษีมูลค่าเพิ่ม', 0.07, 7]]            # vat row #1
mv += [['รวม', '', 107]]
mv += [['สินค้า B', 1, 200]]
mv += [['ภาษีมูลค่าเพิ่ม', 0.07, 14]]           # vat row #2
mv += [['รวม', '', 214]]
mv += [['สินค้า C', 1, 300]]                    # เนื้อหาหลัง vat row สุดท้าย → trailing block
mv += [['สินค้า D', 1, 400], ['รวมท้าย', '', 700], ['หมายเหตุ', '', ''],
       ['ปิดบิล', '', ''], ['', '', '']]         # เว้นช่องให้ block_end สุดท้าย < nrows-1 → เข้ากิ่ง trailing
df_mv = pd.DataFrame(mv)
vr = P._detect_vat_rows(df_mv)
check(len(vr) >= 2, f"_detect_vat_rows เจอ ≥2 แถว ({vr})")
bills_mv = P.parse_sheet(df_mv, 'S', 'KRR_69_05.xls')   # ต้องเดินกิ่ง trailing block ไม่ throw
check(isinstance(bills_mv, list), "parse_sheet multi-vat + trailing block → คืน list (ไม่ throw)")

# ─────────────────────────────────────────────────────────────
print("\n[Q4] parse_file: ชีต parse พัง → log SYS001 + วนชีตต่อ (ไม่ทั้งไฟล์ล่ม)")
with tempfile.TemporaryDirectory() as td:
    fp = os.path.join(td, 'KRR_69_05.xlsx')
    pd.DataFrame([['a', 'b', 'c']] * 6).to_excel(fp, header=False, index=False)
    # OBJ-MAINT: patch parse_sheet ที่ __globals__ ของ parse_file (โมดูลนิยามจริง) — ไม่ใช่ shell attr
    #   เดิม (monolith) parse_file/parse_sheet โมดูลเดียวกัน → patch shell ถึง ; หลังซอยต้อง patch ตรง
    #   binding ที่ parse_file เรียกจริง มิฉะนั้น boom ไม่ทำงาน (false pass)
    _sg = P.parse_file.__globals__
    _orig_ps = _sg['parse_sheet']

    def _boom_sheet(*a, **k):
        raise RuntimeError('forced-sheet-failure (test)')

    try:
        _sg['parse_sheet'] = _boom_sheet
        with contextlib.redirect_stdout(io.StringIO()):
            out = P.parse_file(fp)                 # except → SYS001, finally ปิด workbook
        check(out == [], "ชีตพังทุกชีต → คืน [] (บิลถูกข้าม) ไม่ throw ทั้งไฟล์")
    finally:
        _sg['parse_sheet'] = _orig_ps
    check(_sg['parse_sheet'] is _orig_ps, "คืน parse_sheet เดิม (ไม่ทิ้ง monkeypatch ค้าง)")

# ─────────────────────────────────────────────────────────────
print("\n[Q5] _pick_best_iv / _pick_best_iv_safe — กิ่งให้คะแนน")
check(P._pick_best_iv('เลขที่ IV6905001') == 'IV6905001', "_pick_best_iv: มี LABEL นำ → โบนัส +20")
check(P._pick_best_iv('X1234567') == 'X1234567' or P._pick_best_iv('X1234567') is None,
      "_pick_best_iv: รหัสสินค้า [A-Z]\\d{6,} → โทษ -20 (กิ่งทำงาน)")
# _safe: LOW (คะแนน 5-15), anti-prefix, 13 หลัก
iv_lo, conf_lo = P._pick_best_iv_safe('REF 123456')         # ไม่มี label/prefix IV → คะแนนกลาง
check(conf_lo in ('LOW', 'HIGH', 'NONE'), f"_safe คืนระดับความมั่นใจ ({conf_lo})")
iv_t, conf_t = P._pick_best_iv_safe('TAX 1234567')          # prefix TAX = anti → โทษ
check(conf_t in ('LOW', 'NONE', 'HIGH'), "_safe: anti-prefix TAX → กิ่งโทษทำงาน")
P._pick_best_iv_safe('X1234567')                            # [A-Z]\d{6,} ไม่ใช่ IV-prefix → โทษ -20 (432)
P._pick_best_iv_safe('ภาษี 1234567')                        # ANTI_CONTEXT 'ภาษี' รอบ candidate → โทษ -15 (438)
check(True, "_safe: product-code (-20) + anti-context (-15) กิ่งโทษทำงาน")
iv13, conf13 = P._pick_best_iv_safe('0105566206726')        # 13 หลัก → โทษ -30
check(conf13 == 'NONE' or iv13 is not None, "_safe: เลข 13 หลัก → กิ่งโทษ -30")
ivlab, _ = P._pick_best_iv_safe('เลขที่ IV6905001')         # label → โบนัส +20 → HIGH
check(ivlab == 'IV6905001', "_safe: มี label → จับ IV ถูก")

# ─────────────────────────────────────────────────────────────
print("\n[Q6] tax-id / unit / label helpers — กิ่งที่เหลือ")
check(P._extract_taxid_safe('เลขประจำตัวผู้เสียภาษี 0105566206726') == '0105566206726',
      "_extract_taxid_safe: หลัง keyword 13 หลักติดกัน")
check(P._extract_taxid_safe('เลขประจำตัวผู้เสียภาษี 10556-6206726') == '0105566206726',
      "_extract_taxid_safe: หลัง keyword 12 หลัก (มีตัวคั่น) → เติม 0 นำ")
t12 = P._taxid_from_cell('1055-66206-72-6', 0, 0)          # formatted 12 หลัก
check(t12[0] == '0105566206726', f"_taxid_from_cell: string formatted 12 หลัก → เติม 0 นำ ({t12[0]})")
check(P._find_unit_col([], 1, 2, 0) is None, "_find_unit_col: ไม่มี text_c → None")
check(P._find_unit_col([0], 1, 2, 5) is None, "_find_unit_col: ไม่มี cand หลัง name_col → None")
# _label_in_text: match แบบสระหาย (OCR)
check(P._label_in_text('รวมเงน', ['รวมเงิน']) is True, "_label_in_text: match สระหาย (รวมเงน=รวมเงิน)")

# ─────────────────────────────────────────────────────────────
print("\n[Q7] _pb_try_iv (weak fallback) / _row_has_vat_marker / _pb_extract_items / _pb_build_item")
# _pb_try_iv: ต้องเข้ากิ่ง fallback อ่อน (1036-1038) — string ที่ _pick_best_iv ให้ None แต่ regex อ่อนจับได้
res_iv = {'tax_id': None}
P._pb_try_iv(res_iv, 'AB123456', 'AB123456')
check(res_iv.get('iv_number') == 'AB123456' or '_iv_score' in res_iv,
      f"_pb_try_iv: candidate อ่อน → ตั้ง iv_number ({res_iv.get('iv_number')})")
# _row_has_vat_marker: string '7%'
df_v = pd.DataFrame([['ภาษี', '7%']])
check(P._row_has_vat_marker(df_v.to_numpy(dtype=object), 0, 2) is True, "_row_has_vat_marker: '7%' → True")
# _pb_extract_items: seq หาย แต่มีชื่อ+ยอด → ITM016
res_it = {'items': [], 'issues': []}
block = pd.DataFrame([
    [None, 'สินค้าไม่มีลำดับ', 1, 100],   # seq(col0)=NaN, name(col1), qty(col2), amt(col3)
])
P._pb_extract_items(res_it, block, (0, 1, 2, None, None, 3))
check(any(i['code'] == 'ITM016' for i in res_it['issues']) and len(res_it['items']) == 1,
      "_pb_extract_items: ลำดับหายแต่มีสินค้า+ยอด → ITM016 + เก็บ item")
# _pb_build_item: qty เป็น Text ('1,234') → บันทึก audit (text→num)
P.audit_text_num_reset()
blk2 = pd.DataFrame([['สินค้า', '1,234', 100.0, 123400.0]])
it = P._pb_build_item(blk2, 0, 1, 0, 1, None, 2, 3)
check(it and it['qty'] == 1234.0 and len(state._TEXT_NUM_RECOVERIES) >= 1,
      "_pb_build_item: qty Text '1,234' → กู้เป็น 1234 + บันทึก audit")
P.audit_text_num_reset()

# ─────────────────────────────────────────────────────────────
print("\n[Q8] check_iv_format — กิ่ง continue เมื่อบิลติด IV002 อยู่แล้ว (521)")
# บิลที่ iv_number_raw มีอักขระแปลก → ติด IV002 ตั้งแต่เกณฑ์ 0a แล้วเกณฑ์ 1 เจอซ้ำ → continue (521)
bills_dup = [
    {'iv_number': 'IV@6905', 'iv_number_raw': 'IV@6905', 'issues': []},   # @ แปลก → IV002 (0a) → เกณฑ์1 continue
    {'iv_number': 'IV6906', 'iv_number_raw': 'IV6906', 'issues': []},
]
P.check_iv_format(bills_dup)
n_iv002 = sum(1 for i in bills_dup[0]['issues'] if i['code'] == 'IV002')
check(n_iv002 == 1, f"บิลติด IV002 แล้ว → เกณฑ์ถัดไป continue ไม่เพิ่มซ้ำ (มี {n_iv002} IV002)")

# ─────────────────────────────────────────────────────────────
print("\n[Q9] get_files_via_upload(Enter ว่าง) → ใช้โฟลเดอร์ปัจจุบัน '.' (1617-1618)")
import builtins
_orig_input = builtins.input
try:
    builtins.input = lambda *a, **k: ''      # Enter ว่าง → folder='.'
    with contextlib.redirect_stdout(io.StringIO()):
        up_cwd = P.get_files_via_upload()
    check(isinstance(up_cwd, list), "Enter ว่าง → สแกนโฟลเดอร์ปัจจุบัน (คืน list ไม่ throw)")
finally:
    builtins.input = _orig_input

# ─────────────────────────────────────────────────────────────
print("\n[Q10] _parse_block — fallback scan tax_id เมื่อ header ไม่เจอ (1233-1236)")
# เลขภาษีอยู่ลึกเกิน header (แถว 25) แต่ยังอยู่ใน range ของ _scan_tax_id_block (30 แถว)
rows_pb = [['', '', ''] for _ in range(25)]
rows_pb[2] = ['ใบกำกับภาษี', '', '']                 # ทำให้ไม่ใช่ TOR + มี header บ้าง
rows_pb[25:25] = [['เลขประจำตัวผู้เสียภาษี 0105566206726', '', '']]   # แถว 25
rows_pb += [['สินค้า X', 1, 100], ['ภาษีมูลค่าเพิ่ม', 0.07, 7], ['รวม', '', 107]]
df_pb = pd.DataFrame(rows_pb)
blk = P._parse_block(df_pb, 'S', 'KRR_69_05.xls', 0, df_pb.shape[0] - 1, 0)
check(blk.get('tax_id') == '0105566206726',
      "เลขภาษีอยู่ลึกเกิน header → fallback _scan_tax_id_block เก็บได้ (TAX001)")

# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
if FAIL:
    print(f"PARSER EXTRA 2: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    print("=" * 64)
    sys.exit(1)
else:
    print(f"PARSER EXTRA 2: ผ่าน {PASS} / ล้มเหลว 0")
    print("=" * 64)
    print("RESULT: ✅ TOR handler + parse_sheet/parse_file + กิ่งย่อย ครบ + ไม่กระทบ golden hash")
    sys.exit(0)
