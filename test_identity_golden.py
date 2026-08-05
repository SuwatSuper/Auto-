# -*- coding: utf-8 -*-
"""test_identity_golden.py — [ADR-148] identity-golden: ตาข่ายนิรภัยกฎ "ตรวจตัวตน" ~9 ข้อ

ปัญหา (🟡 ข้อ 2 ใน PROMPT_FIX_MASTER_JOIN): main golden (`23b315e8`) คำนวณด้วย
`golden_snapshot.MASTER = {}` (ว่าง) → กฎตัวตนที่พึ่ง master (CMP001/004/006, ADDR001/002/003,
TAX003/005, BR004) **dormant 100% บน corpus** → ถ้าโค้ดแก้ทำกฎพังเงียบ golden จับไม่ได้.
นี่คือกฎชุดที่ Tor กำลังจะ "เปิดใช้จริง" ด้วย master จริง → ต้องมีตาข่ายแยก.

แนวคิด (golden แยก ไม่แตะ main golden):
  (ก) master ทดสอบเล็ก fixed (สังเคราะห์ — ไม่มี PII, ไม่อยู่ใน corpus)
  (ข) บิลสังเคราะห์ 8 ใบ ครอบสถานการณ์ตัวตน (ตรง/typo/เลขผิด/สวมเลข/ที่อยู่ผิด/สาขาผิด/สาขาถูก/ไม่รู้จัก)
  (ค) เอาต์พุตกฎตัวตนที่คาดหวัง **pin เป็น literal** — ผ่านเมื่อตรงเป๊ะ (ทั้งฟ้องและเงียบ)
ทดสอบทั้งกับ tax_id-primary join (ADR-146) — disambiguate สาขา + anti-fraud + honesty.

main golden ไม่กระทบ (golden_snapshot.MASTER ยังว่าง). รัน: python3 test_identity_golden.py (exit 0=ผ่าน)
"""
import os
import sys
import io
import contextlib
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rules_engine import run_rules
from core_utils import parse_address_input

_FAIL = 0


def check(cond, label):
    global _FAIL
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _FAIL += 1


# ── (ก) master ทดสอบ fixed (สังเคราะห์ · tax_id checksum ถูกต้องทั้งหมด → ไม่ noise TAX006) ──
_A_ADDR = 'เลขที่ 12/34 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110'
_B_ADDR = 'เลขที่ 99 หมู่ 5 ถนนมิตรภาพ ตำบลในเมือง อำเภอเมือง จังหวัดนครราชสีมา 30000'
_B1_ADDR = 'เลขที่ 5 หมู่ 1 ตำบลปากช่อง อำเภอปากช่อง จังหวัดนครราชสีมา 30130'

MASTER = {
    'อัลฟ่า เทรดดิ้ง': {
        'name': 'บริษัท อัลฟ่า เทรดดิ้ง จำกัด', 'name_alt': 'อัลฟ่า เทรดดิ้ง',
        'tax_id': '0105540001230', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        'address_full': _A_ADDR, 'address_parts': parse_address_input(_A_ADDR),
    },
    # เบต้า มี 2 record แชร์ tax เดียว (สนญ + สาขา 1) → ทดสอบ disambiguate ของ tax-join (ADR-146)
    'เบต้า สนญ': {
        'name': 'บริษัท เบต้า คอนสตรัคชั่น จำกัด', 'name_alt': 'เบต้า คอนสตรัคชั่น',
        'tax_id': '0105550005670', 'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
        'address_full': _B_ADDR, 'address_parts': parse_address_input(_B_ADDR),
    },
    'เบต้า สาขา1': {
        'name': 'บริษัท เบต้า คอนสตรัคชั่น จำกัด', 'name_alt': 'เบต้า คอนสตรัคชั่น',
        'tax_id': '0105550005670', 'branch': 'สาขา 00001', 'branch_no': '00001',
        'address_full': _B1_ADDR, 'address_parts': parse_address_input(_B1_ADDR),
    },
}


def _bill(co, tax, addr, bno='00000', br='สำนักงานใหญ่'):
    """บิลสังเคราะห์ — VAT/ยอด consistent (item Σ = subtotal, vat 7%) → กฎที่ไม่ใช่ตัวตนเงียบหมด."""
    return {'company': co, 'company_raw': co, 'tax_id': tax, 'tax_id_raw': tax,
            'branch': br, 'branch_no': bno, 'iv_number': 'IV6805001', 'iv_number_raw': 'IV6805001',
            'iv_date': datetime.date(2025, 5, 15), 'iv_date_str': '15/05/2025', 'address': addr,
            'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0, 'sheet': '1', 'file': 'IDG.xls',
            'block_idx': 0, 'issues': [],
            'items': [{'seq': 1, 'name': 'บริการรับเหมา', 'name_raw': 'บริการรับเหมา',
                       'qty': 10.0, 'unit': 'ชิ้น', 'price': 100.0, 'amount': 1000.0}]}


# ── (ข) 8 สถานการณ์ตัวตน ──────────────────────────────────────────────────────
BILLS = {
    'alpha_ok':              _bill('บริษัท อัลฟ่า เทรดดิ้ง จำกัด', '0105540001230', _A_ADDR),
    'alpha_nametypo':        _bill('บริษัท อัลฟา เทรดดิ้ง จำกัด', '0105540001230', _A_ADDR),  # อัลฟ่า→อัลฟา
    'alpha_wrongtax':        _bill('บริษัท อัลฟ่า เทรดดิ้ง จำกัด', '0105570001114', _A_ADDR),  # tax ไม่อยู่ใน master
    'spoof_taxid':           _bill('บริษัท แกมม่า โลจิสติกส์ จำกัด', '0105540001230', _A_ADDR),  # ใช้ tax ของอัลฟ่า
    'alpha_addrwrong':       _bill('บริษัท อัลฟ่า เทรดดิ้ง จำกัด', '0105540001230',
                                   'เลขที่ 777 ถนนพระราม 4 แขวงสีลม เขตบางรัก กรุงเทพมหานคร 10500'),
    'beta_branch_mismatch':  _bill('บริษัท เบต้า คอนสตรัคชั่น จำกัด', '0105550005670', _B_ADDR,
                                   bno='00005', br='สาขา 00005'),  # บิลอ้างสาขา 5 (ทะเบียนมีแค่ สนญ/สาขา1)
    'beta_branch1_ok':       _bill('บริษัท เบต้า คอนสตรัคชั่น จำกัด', '0105550005670', _B1_ADDR,
                                   bno='00001', br='สาขา 00001'),  # ตรงสาขา 1 (disambiguate ถูก)
    'unknown_vendor':        _bill('บริษัท ซีตา อันโนน จำกัด', '0105560009996',
                                   'เลขที่ 1 ถนนเทสต์ แขวงทดสอบ เขตทดสอบ กรุงเทพมหานคร 10000'),
}

# ── (ค) เอาต์พุต pin เป็น literal: (set รหัสที่ฟ้องทั้งบิล, master_key) ──────────────
#   pin "ครบทุกรหัส" (ไม่เฉพาะตัวตน) — บิล VAT-consistent → รหัสที่เหลือต้องเป็นตัวตนล้วน.
#   ถ้าโค้ดแก้ทำกฎตัวตนเพี้ยน (ฟ้องเกิน/หาย) → ด่านนี้แดงทันที.
EXPECTED = {
    'alpha_ok':             (set(),                       'อัลฟ่า เทรดดิ้ง'),     # ตรงทุกช่อง → เงียบ
    'alpha_nametypo':       ({'CMP006'},                  'อัลฟ่า เทรดดิ้ง'),     # ชื่อไม่ตรง 100%
    'alpha_wrongtax':       ({'TAX003'},                  'อัลฟ่า เทรดดิ้ง'),     # เลขภาษีไม่ตรงทะเบียน
    'spoof_taxid':          ({'CMP001', 'TAX005'},        'อัลฟ่า เทรดดิ้ง'),     # สวมเลข: ชื่อคนละเจ้า
    'alpha_addrwrong':      ({'ADDR001', 'ADDR003'},      'อัลฟ่า เทรดดิ้ง'),     # ที่อยู่ผิดทะเบียน
    'beta_branch_mismatch': ({'BR004'},                   'เบต้า สนญ'),          # สาขาในบิลไม่ตรงทะเบียน
    'beta_branch1_ok':      (set(),                       'เบต้า สาขา1'),         # ตรงสาขา 1 (disambiguate)
    'unknown_vendor':       (set(),                       '(ไม่พบใน master)'),    # honesty: ไม่อ้างตัวตนมั่ว
}


def _run(b):
    with contextlib.redirect_stdout(io.StringIO()):
        run_rules(b, MASTER, {'month': 5, 'month_end': None, 'year': 2025},
                  unit_index={}, all_bills_ref=[b])
    return {i['code'] for i in b['issues']}, b.get('master_key'), {i['code']: i['detail'] for i in b['issues']}


print("\n[identity-golden] pin เอาต์พุตกฎตัวตน 8 สถานการณ์ (master ทดสอบ fixed)")
for name, b in BILLS.items():
    got_codes, got_key, details = _run(b)
    exp_codes, exp_key = EXPECTED[name]
    check(got_codes == exp_codes, f"{name:22s} รหัส={sorted(got_codes)} (คาด {sorted(exp_codes)})")
    check(got_key == exp_key, f"{name:22s} master_key={got_key!r} (คาด {exp_key!r})")

print("\n[anti-fraud detail] ข้อความกฎสวมเลข/เลขผิด ต้องสื่อความถูก")
_, _, d_spoof = _run(BILLS['spoof_taxid'])
check('เป็นของ' in d_spoof.get('TAX005', '') and 'แต่ในบิลใช้ชื่อ' in d_spoof.get('TAX005', ''),
      "TAX005 ระบุเจ้าของจริง + ชื่อในบิล")
_, _, d_wt = _run(BILLS['alpha_wrongtax'])
check('ไม่ตรง' in d_wt.get('TAX003', ''), "TAX003 ระบุเลขภาษีไม่ตรงทะเบียน")
_, _, d_br = _run(BILLS['beta_branch_mismatch'])
check('สาขา' in d_br.get('BR004', '') and 'ทะเบียน' in d_br.get('BR004', ''),
      "BR004 ระบุสาขาในบิล vs ทะเบียน")

print("\n[main-golden untouched] golden_snapshot.MASTER ยังว่าง (กฎตัวตน dormant บน corpus)")
import golden_snapshot
check(golden_snapshot.MASTER == {}, "golden_snapshot.MASTER == {} (main golden 23b315e8 ไม่กระทบ)")

print("\n" + "=" * 64)
if _FAIL == 0:
    print("RESULT: ✅ identity-golden — กฎตัวตน 9 ข้อมีตาข่าย pin ครบ (ตรง/typo/เลขผิด/สวมเลข/ที่อยู่/สาขา/honesty)")
    sys.exit(0)
print(f"RESULT: ❌ {_FAIL} ข้อไม่ผ่าน")
sys.exit(1)
