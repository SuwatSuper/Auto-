# -*- coding: utf-8 -*-
"""test_master_key_branch_adr151.py — [ADR-151] คีย์ master แยกตามสาขา (อนุมัติโดย Tor)

บั๊กที่แก้ (master_io BUG-1, อนุมัติแล้ว): เดิม input_master_data ตั้งคีย์จาก "ชื่อบริษัทล้วน" →
HQ + สาขา ชื่อเดียวกันชนกัน 1 คีย์ → master เก็บได้ record เดียว/บริษัท → _pick_branch_record
(disambiguate HQ/สาขา ของ tax-join ADR-146) ใช้จริงผ่านเมนูกรอกไม่ได้.

แก้: คีย์แยกตามสาขา (_master_key) + branch_no normalize (BUG-2) → HQ + หลายสาขาอยู่ร่วมกันได้
→ tax-join disambiguate สาขาทำงานจริงครบวง. golden-NEUTRAL (input_master_data ไม่อยู่เส้น corpus/golden).

รัน: python3 test_master_key_branch_adr151.py   (exit 0 = ผ่าน)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from master import _company_key_base, _normalize_branch_no, _master_key
from puopuy_core import clean_tax_id
from core_utils import parse_address_input
from rules_engine_base import match_company

_FAIL = 0


def check(cond, label):
    global _FAIL
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _FAIL += 1


print("\n[A] _company_key_base — ตัด prefix/suffix นิติบุคคล")
check(_company_key_base('บริษัท เอบีซี จำกัด') == 'เอบีซี', "บริษัท…จำกัด → เอบีซี")
check(_company_key_base('หจก. วัชราวุธ เอ็นจิเนียริ่ง') == 'วัชราวุธ เอ็นจิเนียริ่ง', "หจก. → ตัด prefix")
check(_company_key_base('บมจ. ปตท จำกัด (มหาชน)') == 'ปตท', "บมจ + (มหาชน) → ปตท")

print("\n[B] _normalize_branch_no — รหัสสาขา 5 หลัก")
check(_normalize_branch_no('สำนักงานใหญ่') == '00000', "สำนักงานใหญ่ → 00000")
check(_normalize_branch_no('สาขา 00001') == '00001', "สาขา 00001 → 00001")
check(_normalize_branch_no('สาขาที่ 5') == '00005', "สาขาที่ 5 → 00005 (เลขที่ใดก็ได้)")
check(_normalize_branch_no('สาขาที่ 5 กรุงเทพ') == '00005', "สาขาที่ 5 กรุงเทพ → 00005 (BUG-2: ไม่ใช่เลขท้าย)")
check(_normalize_branch_no('สาขากรุงเทพ') == '', "สาขากรุงเทพ (ไม่มีเลข) → ''")
# กับดัก F1: 'สาขาสำนักพระโขนง' มี substring 'สำนัก' แต่ไม่ใช่ HQ
check(_normalize_branch_no('สาขาสำนักพระโขนง') == '', "สาขาสำนักพระโขนง → '' (ไม่ใช่ HQ — เต็มคำ)")

print("\n[C] _master_key — แยกคีย์ตามสาขา")
check(_master_key('เอบีซี', '00000', 'สำนักงานใหญ่') == 'เอบีซี', "HQ → key_base สะอาด (backward-compatible)")
check(_master_key('เอบีซี', '00001', 'สาขา 00001') == 'เอบีซี (สาขา 00001)', "สาขามีเลข → suffixed")
check(_master_key('เอบีซี', '', 'สาขากรุงเทพ') == 'เอบีซี (สาขากรุงเทพ)', "สาขาไม่มีเลข → label")
check(_master_key('เอบีซี', '', '') == 'เอบีซี', "ไม่มีข้อมูลสาขา → key_base (HQ)")
# คีย์แยกกันจริง: HQ ≠ สาขา (เดิมชนกัน)
keys = {_master_key('เอบีซี', _normalize_branch_no(b), b)
        for b in ['สำนักงานใหญ่', 'สาขา 00001', 'สาขา 00002']}
check(len(keys) == 3, f"BUG-1: HQ + 2 สาขา → 3 คีย์ต่างกัน (เดิมชนเป็น 1) — ได้ {len(keys)}")


def _mk_record(name, tax, branch, addr):
    """จำลองการสร้าง record ของ input_master_data ผ่าน helper ชุดเดียวกัน."""
    kb = _company_key_base(name)
    bn = _normalize_branch_no(branch)
    key = _master_key(kb, bn, branch)
    return key, {'name': name, 'name_alt': name, 'tax_id': clean_tax_id(tax),
                 'branch': branch, 'branch_no': bn, 'iv_prefix': 'IV',
                 'address_full': addr, 'address_parts': parse_address_input(addr)}


print("\n[D] end-to-end: master หลายสาขา → tax-join disambiguate ได้จริง (ADR-146 ครบวง)")
TAX = '0105540001230'
MASTER = {}
for br, ad in [('สำนักงานใหญ่', 'เลขที่ 1 ถนนเอ แขวงบี เขตซี กรุงเทพมหานคร 10110'),
               ('สาขา 00001', 'เลขที่ 2 ถนนดี ตำบลอี อำเภอเอฟ จังหวัดชลบุรี 20000'),
               ('สาขา 00002', 'เลขที่ 3 ถนนจี ตำบลเอช อำเภอไอ จังหวัดระยอง 21000')]:
    k, r = _mk_record('บริษัท เอบีซี จำกัด', TAX, br, ad)
    MASTER[k] = r
check(len(MASTER) == 3, f"D1 master เก็บ HQ + 2 สาขา ครบ (เดิมได้ 1) — ได้ {len(MASTER)}")
# tax-join + disambiguate ตามสาขาของบิล
_, m_hq, _ = match_company('บริษัท เอบีซี จำกัด', MASTER, bill_tax_id=TAX, bill_branch_no='00000')
check(m_hq is not None and m_hq['branch_no'] == '00000', "D2 บิล HQ → record สำนักงานใหญ่")
_, m_b1, _ = match_company('บริษัท เอบีซี จำกัด', MASTER, bill_tax_id=TAX, bill_branch_no='00001')
check(m_b1 is not None and m_b1['branch_no'] == '00001', "D3 บิลสาขา 1 → record สาขา 00001")
_, m_b2, _ = match_company('บริษัท เอบีซี จำกัด', MASTER, bill_tax_id=TAX, bill_branch_no='00002')
check(m_b2 is not None and m_b2['branch_no'] == '00002', "D4 บิลสาขา 2 → record สาขา 00002")
# คนละ address ต่อสาขา → ที่อยู่ของ record ที่ join ตรงสาขา (พิสูจน์ disambiguation ส่งผลจริง)
check(m_b1['address_full'] != m_hq['address_full'], "D5 แต่ละสาขามี address ของตัวเอง (join ถูกตัว)")

print("\n" + "=" * 64)
if _FAIL == 0:
    print("RESULT: ✅ branch-aware master key (ADR-151) — HQ+สาขาอยู่ร่วมกัน, tax-join disambiguate ครบวง")
    sys.exit(0)
print(f"RESULT: ❌ {_FAIL} ข้อไม่ผ่าน")
sys.exit(1)
