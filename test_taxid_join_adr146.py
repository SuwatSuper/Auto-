# -*- coding: utf-8 -*-
"""test_taxid_join_adr146.py — [ADR-146/147] พิสูจน์ join master ด้วย tax_id (เลข 13 หลักเอกลักษณ์)

บริบท: เดิม match_company join ด้วย "ชื่อบริษัท fuzzy" เท่านั้น (rules_engine_base) → บิลที่ชื่อ
เพี้ยน/ย่อ/อังกฤษ/typo (score < FUZZY_NAME_THRESHOLD=75) ไม่ match → กฎตัวตน ~24 ข้าม "ทั้งบิล
เงียบ ๆ" (false-negative) ทั้งที่ tax_id ตรง. ADR-146 เปลี่ยนเป็น tax_id-primary + คง name fallback.

เทสนี้เป็น "ตาข่ายนิรภัย" ของเส้นทางที่ Tor กำลังจะเปิดใช้ (เติม master จริง):
  A) เคส FN เดิม (66.7 / 10.5) ต้อง match ได้ด้วย tax_id (score 100, แหล่ง=tax_id)
  B) name fallback ยังทำงาน (tax_id ไม่อยู่ใน master / บิลไม่มี tax_id) — กัน regression
  C) golden-NEUTRAL: master ว่าง → ตก fallback ชื่อเดิมเป๊ะ (None, None, 0)
  D) disambiguate สาขา (HQ vs สาขา N) เมื่อหลาย record แชร์ tax_id เดียว
  E) ทนทาน: record non-dict / tax_id ขาด/เพี้ยน / เลขมี dash/space/ไทย/full-width ไม่ครัช
  F) integration run_rules: บิลชื่อ typo + tax ตรง → กฎตัวตน "รันจริง" (ไม่ข้ามเงียบ) ;
     anti-fraud TAX005 ยังฟ้องเคสสวมเลข (tax ของคนอื่น + ชื่อคนละเจ้า) — join ไม่กลบกฎ

รัน: python3 test_taxid_join_adr200.py   (exit 0 = ผ่าน)
"""
import os
import sys
import io
import contextlib
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine_base import match_company
from rules_engine import run_rules
from core_utils import parse_address_input

_FAIL = 0


def check(cond, label):
    global _FAIL
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _FAIL += 1


# master keyed by name-derived key (เหมือน production input_master_data) — record มี tax_id 13 หลัก
MASTER = {
    'เอบีซี เอ็นจิเนียริ่ง แอนด์ คอนสตรัคชั่น': {
        'name': 'บริษัท เอบีซี เอ็นจิเนียริ่ง แอนด์ คอนสตรัคชั่น จำกัด',
        'name_alt': 'เอบีซี เอ็นจิเนียริ่ง',
        'tax_id': '0105563333333', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        'address_full': 'เลขที่ 88 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    },
}
TID = '0105563333333'

print("\n[A] เคส FN เดิม → match ได้ด้วย tax_id (score 100)")
# A1: ชื่อไทยเพี้ยน (วิศวกรรม แทน เอ็นจิเนียริ่ง) — เดิม 66.7 ไม่ match
k, m, s = match_company('บริษัท เอบีซี วิศวกรรม จำกัด', MASTER, bill_tax_id=TID)
check(m is not None and s == 100, f"A1 ชื่อไทยเพี้ยน + tax ตรง → match (score={s})")
check(m is not None and m.get('tax_id') == TID, "A1 record ที่คืน = เจ้าของ tax จริง")
# A2: ชื่ออังกฤษ — เดิม 10.5 ไม่ match
k2, m2, s2 = match_company('ABC Engineering and Construction Co.,Ltd.', MASTER, bill_tax_id=TID)
check(m2 is not None and s2 == 100, f"A2 ชื่ออังกฤษ + tax ตรง → match (score={s2})")
# A3: เลขภาษีมี dash/space (รูปแบบ ภ.พ.20) → normalize แล้ว match
k3, m3, s3 = match_company('X', MASTER, bill_tax_id='0-1055-63333-33-3')
check(m3 is not None and s3 == 100, "A3 tax มี dash → clean_tax_id แล้ว match")
# A4: เลขไทย ๐-๙
k4, m4, s4 = match_company('X', MASTER, bill_tax_id='๐๑๐๕๕๖๓๓๓๓๓๓๓')
check(m4 is not None and s4 == 100, "A4 tax เลขไทย → translate แล้ว match")

print("\n[B] name fallback ยังทำงาน (กัน regression)")
# B1: tax_id ไม่อยู่ใน master → ตก fallback ชื่อ (ชื่อเพี้ยน → ไม่ match เหมือนเดิม)
kb, mb, sb = match_company('บริษัท เอบีซี วิศวกรรม จำกัด', MASTER, bill_tax_id='0999999999999')
check(mb is None, "B1 tax ไม่อยู่ใน master + ชื่อเพี้ยน → ไม่ match (fallback ชื่อเดิม)")
# B2: บิลไม่มี tax_id → name-only ; ชื่อตรง substring → match
kb2, mb2, sb2 = match_company('บริษัท เอบีซี เอ็นจิเนียริ่ง แอนด์ คอนสตรัคชั่น จำกัด', MASTER, bill_tax_id=None)
check(mb2 is not None and sb2 == 100, "B2 ไม่มี tax_id + ชื่อตรง → name fallback match")
# B3: บิลไม่มี tax_id + ชื่อเพี้ยน → ไม่ match (พฤติกรรมเดิมเป๊ะ)
kb3, mb3, sb3 = match_company('บริษัท เอบีซี วิศวกรรม จำกัด', MASTER, bill_tax_id='')
check(mb3 is None and abs(sb3 - 66.66666666666667) < 1e-6,
      f"B3 ไม่มี tax_id + ชื่อเพี้ยน → ไม่ match, score เดิม ({sb3:.1f})")
# B4: signature backward-compatible (เรียกแบบเดิม 2 args ได้)
kb4, mb4, sb4 = match_company('บริษัท เอบีซี เอ็นจิเนียริ่ง แอนด์ คอนสตรัคชั่น จำกัด', MASTER)
check(mb4 is not None, "B4 เรียก 2-args (เดิม) ยังได้ — backward compatible")

print("\n[C] golden-NEUTRAL: master ว่าง → ผลเดิมเป๊ะ")
check(match_company('บริษัท เอบีซี จำกัด', {}, bill_tax_id=TID) == (None, None, 0),
      "C1 master ว่าง + มี tax → (None, None, 0) เหมือนเดิม")
check(match_company('', {}, bill_tax_id=TID) == (None, None, 0),
      "C2 ชื่อว่าง + master ว่าง → (None, None, 0)")

print("\n[D] disambiguate สาขา (หลาย record แชร์ tax เดียว)")
MULTI = {
    'เอ็กซ์ สนญ': {'name': 'บริษัท เอ็กซ์ จำกัด', 'tax_id': '0105556000010',
                   'branch': 'สำนักงานใหญ่', 'branch_no': '00000'},
    'เอ็กซ์ สาขา1': {'name': 'บริษัท เอ็กซ์ จำกัด', 'tax_id': '0105556000010',
                     'branch': 'สาขา 00001', 'branch_no': '00001'},
}
kd, md, sd = match_company('บริษัท เอ็กซ์ จำกัด', MULTI, bill_tax_id='0105556000010', bill_branch_no='00001')
check(md is not None and md.get('branch_no') == '00001', "D1 บิลสาขา 00001 → เลือก record สาขา 00001")
kd2, md2, sd2 = match_company('บริษัท เอ็กซ์ จำกัด', MULTI, bill_tax_id='0105556000010', bill_branch_no='00000')
check(md2 is not None and md2.get('branch_no') == '00000', "D2 บิล HQ → เลือก record สำนักงานใหญ่")
kd3, md3, sd3 = match_company('บริษัท เอ็กซ์ จำกัด', MULTI, bill_tax_id='0105556000010', bill_branch_no='')
check(md3 is not None and md3.get('branch_no') == '00000', "D3 บิลไม่ระบุสาขา → default สำนักงานใหญ่")
kd4, md4, sd4 = match_company('บริษัท เอ็กซ์ จำกัด', MULTI, bill_tax_id='0105556000010', bill_branch_no='00099')
check(md4 is not None, "D4 บิลสาขาไม่ตรงใคร → ยัง match (ไม่ครัช) เลือก HQ")
# [ADR-150 F1] HQ tie-break: record สาขาที่ descriptor มีคำ 'สำนัก' ต้องไม่แย่ง record 00000 จริง
HQTIE = {'A สาขาสำนัก': {'tax_id': '0105556000010', 'branch': 'สาขาสำนักพระโขนง', 'branch_no': '00021'},
         'B สนญ': {'tax_id': '0105556000010', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000'}}
_kf, md5, _sf = match_company('co', HQTIE, bill_tax_id='0105556000010', bill_branch_no='')
check(md5 is not None and md5.get('branch_no') == '00000',
      "D5 [F1] บิลไม่ระบุสาขา → เลือก 00000 จริง ไม่ใช่ 'สาขาสำนัก...' (กัน BR004 FP)")
# [ADR-150 CRASH-1] หลาย record แชร์ tax + master key คนละ type → sort ไม่ครัช
try:
    match_company('co', {1: {'tax_id': '0105556000010', 'branch_no': '1'},
                         'a': {'tax_id': '0105556000010', 'branch_no': '2'}},
                  bill_tax_id='0105556000010', bill_branch_no='00099')
    check(True, "D6 [CRASH-1] master key คนละ type (int+str) → sort ไม่ครัช")
except Exception as e:
    check(False, f"D6 [CRASH-1] ครัช: {e!r}")

print("\n[E] ทนทาน — input เพี้ยน/ขาด ไม่ครัช")
BAD = {
    'ok': {'name': 'บริษัท โอเค จำกัด', 'tax_id': '0105556000027', 'branch_no': '00000'},
    'broken': 'ไม่ใช่ dict',                                   # record non-dict
    'no_tax': {'name': 'บริษัท ไม่มีเลข จำกัด'},                  # tax_id ขาด
    'blank_tax': {'name': 'บริษัท เลขว่าง จำกัด', 'tax_id': ''},  # tax_id ว่าง
    'short_tax': {'name': 'บริษัท เลขสั้น จำกัด', 'tax_id': '123'},  # tax_id ไม่ครบ 13
}
try:
    ke, me, se = match_company('บริษัท โอเค จำกัด', BAD, bill_tax_id='0105556000027')
    check(me is not None and me.get('tax_id') == '0105556000027', "E1 ข้าม record เพี้ยน, match ตัวที่ดี")
except Exception as e:
    check(False, f"E1 ครัช: {e!r}")
try:
    # tax ของ record ที่ tax_id ขาด → ไม่ index → ตก fallback ชื่อ
    ke2, me2, se2 = match_company('บริษัท ไม่มีเลข จำกัด', BAD, bill_tax_id='0000000000000')
    check(me2 is not None, "E2 tax ไม่อยู่ใน index → fallback ชื่อ match record tax-less")
except Exception as e:
    check(False, f"E2 ครัช: {e!r}")
try:
    check(match_company(None, {}, bill_tax_id=None) == (None, None, 0), "E3 None/None ไม่ครัช")
    match_company('x', None, bill_tax_id='0105556000027')   # master=None
    check(True, "E4 master=None ไม่ครัช")
except Exception as e:
    check(False, f"E3/E4 ครัช: {e!r}")

print("\n[F] integration run_rules — กฎตัวตน 'รันจริง' ไม่ข้ามเงียบ + anti-fraud คง")
_MADDR = 'เลขที่ 5/32 ซอยศรีนครินทร์ 46/1 แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250'
IMASTER = {
    'ฉี อัน คอนสตรัคชั่น': {
        'name': 'บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด', 'name_alt': 'ฉี อัน คอนสตรัคชั่น',
        'tax_id': '0105566206726', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        'address': _MADDR, 'address_full': _MADDR, 'address_parts': parse_address_input(_MADDR),
    },
}


def _bill(company, tax_id, address, branch_no='00000'):
    return {'company': company, 'company_raw': company, 'tax_id': tax_id, 'tax_id_raw': tax_id,
            'branch': 'สำนักงานใหญ่', 'branch_no': branch_no, 'iv_number': 'IV1', 'iv_number_raw': 'IV1',
            'iv_date': datetime.date(2025, 5, 15), 'iv_date_str': '15/05/2025',
            'address': address, 'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
            'sheet': '1', 'file': 'TST.xls', 'block_idx': 0, 'issues': [],
            'items': [{'seq': 1, 'name': 'เหล็ก', 'name_raw': 'เหล็ก', 'qty': 1.0,
                       'unit': 'เส้น', 'price': 1.0, 'amount': 1.0}]}


def _codes(b):
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(b, IMASTER, {'month': 5, 'month_end': None, 'year': 2025},
                  unit_index={}, all_bills_ref=[b])
    return {i['code'] for i in b['issues']}, b.get('master_key')

# F1: บิลชื่อ typo (ฉี→ชี) + tax ตรง + ที่อยู่ "ผิดจาก master" → เดิมข้ามเงียบ (ชื่อ fuzzy ไม่ถึง)
#     ใหม่: tax-join → ADDR001 เทียบที่อยู่ "รันจริง" และฟ้อง (ตรวจได้ ไม่ใช่ 'ตรง' หลอก)
typo = _bill('บริษัท ชี อัน คอนสตรัคชั่น กรุ๊ป จำกัด', '0105566206726',
             'เลขที่ 999 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110')
cc, mk = _codes(typo)
check(mk and mk != '(ไม่พบใน master)', f"F1 บิลชื่อ typo + tax ตรง → match master (key={mk})")
check('ADDR001' in cc, "F1 ADDR001 รันจริง (ที่อยู่ต่าง master ถูกฟ้อง — ไม่ข้ามเงียบ)")

# F2: บิลเป็นเจ้าของจริง (ชื่อ+tax+address ตรง) → ไม่มี FP ตัวตน
ok = _bill('บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด', '0105566206726',
           'เลขที่ 5/32 ซอยศรีนครินทร์ 46/1 เขตประเวศ กรุงเทพมหานคร 10250')
cc2, mk2 = _codes(ok)
check('TAX005' not in cc2 and 'CMP001' not in cc2, "F2 เจ้าของจริง → ไม่มี TAX005/CMP001 FP")

# F3: สวมเลข — tax ของ ฉีอัน แต่ชื่อ 'เจ.อาร์.' (คนละเจ้า) → anti-fraud ต้องฟ้อง (join ไม่กลบกฎ)
spoof = _bill('บริษัท เจ.อาร์. (ประเทศไทย) จำกัด', '0105566206726',
              'เลขที่ 5/32 ซอยศรีนครินทร์ 46/1 เขตประเวศ กรุงเทพมหานคร 10250')
cc3, mk3 = _codes(spoof)
check('TAX005' in cc3, "F3 สวมเลข (tax คนอื่น + ชื่อคนละเจ้า) → TAX005 ฟ้อง (anti-fraud คง)")
check('CMP001' in cc3, "F3 ชื่อไม่ตรงเจ้าของ tax → CMP001 ฟ้องด้วย (join ไม่กลบกฎ)")

print("\n" + "=" * 64)
if _FAIL == 0:
    print("RESULT: ✅ tax_id-primary join (ADR-146/147) — FN เดิม match ได้, fallback คง, golden-neutral")
    sys.exit(0)
print(f"RESULT: ❌ {_FAIL} ข้อไม่ผ่าน")
sys.exit(1)
