# -*- coding: utf-8 -*-
"""test_rules_extra.py — [OBJ-1D ต่อยอด] ดัน coverage ของ rules_engine.py ให้ ≥90%

แนวคิด (ต่างจาก test_rules_coverage.py ที่ขับ run_rules ทั้งชุด):
  เรียก "ฟังก์ชันกฎทีละตัว" ตรง ๆ ด้วย (b, m, c) ที่ออกแบบให้แตะ "กิ่งที่ฟ้องจริง"
  (fire branch) ของแต่ละกฎ แล้ว assert ว่าข้อความที่คืน "ถูกต้องตามเจตนา"
  → ไม่ใช่การปั๊ม coverage ด้วย test ขยะ: ทุก assert ผูกกับพฤติกรรมที่ควรเป็น.

ทั้งหมดเป็น pure check (อ่าน b → คืน list) — ไม่แตะผลหลัก/ไม่กระทบ golden hash.
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_rules_extra.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings
import datetime as dt
from types import SimpleNamespace

# ตรึงนาฬิกาตรวจให้ผลปีนิ่ง (r_dt003/r_dt004 อิง audit_today)
os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import state
import rules_engine as R

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def fires(out, label, must_contain=None):
    """กฎต้องฟ้อง (คืน list ไม่ว่าง) + (ทางเลือก) ข้อความต้องมี substring."""
    ok = bool(out)
    if ok and must_contain is not None:
        ok = any(must_contain in str(x) for x in out)
    check(ok, label + (f"  → {out}" if not ok else ""))


def silent(out, label):
    check(out == [] or out is None, label + (f"  (ควรเงียบ แต่ได้ {out})" if out else ""))


# ── master ที่มีฟิลด์ครบ (address_parts/address_full) สำหรับกฎ address ──
M = {
    'name': 'บริษัท ทดสอบ ระบบ จำกัด',
    'name_alt': '',
    'tax_id': '0105566206726',
    'branch': 'สำนักงานใหญ่',
    'address': 'เลขที่ 99 ถนนพระราม4 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    'address_full': 'เลขที่ 99 อาคารเอบีซี ชั้นที่ 10 ถนนพระราม4 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110',
    'address_parts': {
        'house_no': '99', 'moo': '', 'soi': 'สุขนิรันดร์', 'road': 'พระราม4',
        'subdistrict': 'คลองเตย', 'district': 'คลองเตย',
        'province': 'กรุงเทพมหานคร', 'zipcode': '10110',
    },
    'iv_prefix': 'IV',
}


def ctx(**over):
    c = {'sheet_name': '1', 'target_month': None, 'target_month_end': None,
         'all_masters': {'ทดสอบ': M}, 'unit_index': None,
         'all_bills_for_iv_check': []}
    c.update(over)
    return c


def item(seq, name, qty, unit, price, amount, name_raw=None):
    return {'seq': seq, 'name': name, 'name_raw': name_raw if name_raw is not None else name,
            'qty': qty, 'unit': unit, 'price': price, 'amount': amount}


# ════════════════════════════════════════════════════════════════════════════
print("=" * 64)
print("[CMP] กฎบริษัท")
print("=" * 64)

# r_cmp001: ชื่อต่างจาก master มาก → fuzzy fail (กิ่งฟ้อง)
fires(R.r_cmp001({'company': 'ห้างหุ้นส่วน เอ็กซ์วาย ซีโอ'}, M, ctx()),
      "CMP001 ชื่อไม่ตรง master → ฟ้อง (มี fuzzy%)", must_contain='fuzzy')
# r_cmp001: bill ไม่มีคีย์ 'company' → except → []
silent(R.r_cmp001({}, M, ctx()), "CMP001 bill ไม่มี company → except → เงียบ (ไม่ throw)")

# normalize_company_name + validate_company_prefix (helpers)
check(R.normalize_company_name('  บริษัท   เอ บี ซี  ') == 'บริษัท เอ บี ซี',
      "normalize_company_name ยุบช่องว่าง + trim")
check(R.validate_company_prefix('บริษัท เอ บี ซี จำกัด') is True,
      "validate_company_prefix รับคำนำหน้าถูก")
check(R.validate_company_prefix('โรงงาน เอ บี ซี') is False,
      "validate_company_prefix ปฏิเสธเมื่อไม่มีคำนำหน้า")

# r_cmp002: typo prefix
fires(R.r_cmp002({'company': 'บริษาท เอ บี ซี จำกัด'}, M, ctx()),
      "CMP002 typo prefix 'บริษาท' → ฟ้อง", must_contain='พิมพ์ผิด')

# r_cmp003: brand blacklist
fires(R.r_cmp003({'company': 'บริษัท Lotus ซัพพลาย จำกัด'}, M, ctx()),
      "CMP003 พบแบรนด์ Lotus → ฟ้อง", must_contain='Lotus')

# r_cmp004: เว้นวรรคต่าง (ชื่อเดียวกัน แต่ space count ต่าง)
b_sp = {'company': 'บริษัท ทดสอบ ระบบ จำกัด',
        'company_raw': 'บริษัท  ทดสอบ  ระบบ จำกัด'}  # double-space
fires(R.r_cmp004(b_sp, M, ctx()),
      "CMP004 เว้นวรรคไม่ตรง master → ฟ้อง", must_contain='ช่องว่าง')
# r_cmp004: ตัวอักษรต่างจริง (ไม่ใช่เว้นวรรค) → เงียบ (ปล่อย CMP001)
silent(R.r_cmp004({'company': 'บริษัท อื่น จำกัด', 'company_raw': 'บริษัท อื่น จำกัด'}, M, ctx()),
       "CMP004 ตัวอักษรต่างจริง → เงียบ (CMP001 รับผิดชอบ)")

# r_cmp005: บริษัท ต้องมี จำกัด / บมจ ต้องมี มหาชน / หจก ลงท้าย จำกัด
fires(R.r_cmp005({'company': 'บริษัท เอ บี ซี'}, M, ctx()),
      "CMP005 มี 'บริษัท' ไม่มี 'จำกัด' → ฟ้อง", must_contain='จำกัด')
fires(R.r_cmp005({'company': 'บมจ เอ บี ซี'}, M, ctx()),
      "CMP005 มี 'บมจ' ไม่มี 'มหาชน' → ฟ้อง", must_contain='มหาชน')
fires(R.r_cmp005({'company': 'หจก เอ บี ซี จำกัด'}, M, ctx()),
      "CMP005 'หจก' ลงท้าย 'จำกัด' เฉย ๆ → ฟ้อง")

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print("[ADDR] กฎที่อยู่")
print("=" * 64)

# r_addr001 (v9.2 SMART): บิลขาด anchor (แขวง/เขต) → ฟ้อง ERROR ระบุ field ที่ไม่ตรง
b_addr = {'address': 'เลขที่ 99 ถนนพระราม4 10110'}
out = R.r_addr001(b_addr, M, ctx())
fires(out, "ADDR001 บิลขาด anchor (แขวง/เขต) → ฟ้อง", must_contain='ไม่ตรงทะเบียน')
check(any('ไม่พบ' in str(x) for x in out), "ADDR001 ระบุ anchor field ที่ขาด (ไม่พบเขต/แขวง)")

# r_addr002: สะกดถนนผิดเล็กน้อย (fuzz 70-99)
b_typo = {'address': 'เลขที่ 99 ถนนพระราม5 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร'}
# ใช้ master road ที่คล้ายแต่ไม่ตรง
M2 = dict(M); M2['address_parts'] = dict(M['address_parts'], road='พระราม4')
fires(R.r_addr002({'address': 'ถนนสุขุมวิจ คลองเตย'},
                  {'address_parts': {'road': 'สุขุมวิท'}}, ctx()),
      "ADDR002 ถนนสะกดผิด (สุขุมวิจ~สุขุมวิท) → ฟ้อง", must_contain='สะกดผิด')

# r_addr003: ชั้น/อาคาร/ห้อง ต่างจาก master
b_floor = {'address': 'เลขที่ 99 ชั้นที่ 21 ห้องเลขที่ 5 ถนนพระราม4 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110'}
fires(R.r_addr003(b_floor, M, ctx()),
      "ADDR003 ชั้น/อาคาร/ห้อง ต่างจาก master → ฟ้อง")

# r_addr004: กรุงเทพ ใช้ ตำบล/อำเภอ (ผิด format)
fires(R.r_addr004({'address': 'เลขที่ 1 ตำบลในเมือง อำเภอเมือง กรุงเทพมหานคร 10100'}, M, ctx()),
      "ADDR004 กรุงเทพ ใช้ ตำบล/อำเภอ → ฟ้อง", must_contain='แขวง/เขต')
# ต่างจังหวัด ใช้ แขวง/เขต
fires(R.r_addr004({'address': 'เลขที่ 1 แขวงสุเทพ เขตเมือง จังหวัดเชียงใหม่ 50200'}, M, ctx()),
      "ADDR004 ต่างจังหวัด ใช้ แขวง/เขต → ฟ้อง", must_contain='ตำบล/อำเภอ')

# r_addr005: รหัสไปรษณีย์
silent(R.r_addr005({'address': 'เลขที่ 1 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110'}, M, ctx()),
       "ADDR005 รหัสกรุงเทพถูกต้อง → เงียบ")
fires(R.r_addr005({'address': 'เลขที่ 1 ถนนสุขุมวิท ไม่มีรหัส'}, M, ctx()),
      "ADDR005 ไม่มีรหัส 5 หลัก → ฟ้อง", must_contain='ไม่พบรหัส')
fires(R.r_addr005({'address': 'เลขที่ 1 เชียงใหม่ 09999'}, M, ctx()),
      "ADDR005 รหัสนอกช่วง (09999<10000) → ฟ้อง", must_contain='ไม่อยู่ในช่วง')
fires(R.r_addr005({'address': 'เลขที่ 1 กรุงเทพมหานคร 50200'}, M, ctx()),
      "ADDR005 รหัส 50200 ไม่ตรงกรุงเทพ → ฟ้อง", must_contain='ไม่ตรงกับกรุงเทพ')

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print("[TAX] กฎเลขภาษี")
print("=" * 64)

# r_tax002: tax_id_raw ไม่มีกลุ่ม 13 หลัก
fires(R.r_tax002({'tax_id_raw': 'เลขที่ 123'}, M, ctx()),
      "TAX002 raw ไม่มีเลข 13 หลัก → ฟ้อง", must_contain='ไม่พบเลขภาษี')

# r_tax003: เลขภาษีไม่ตรง master (อันตราย)
fires(R.r_tax003({'tax_id': '0999999999999', 'company': 'x'},
                 {'name': 'บริษัท ทดสอบ', 'tax_id': '0105566206726'}, ctx()),
      "TAX003 เลขภาษีไม่ตรง master → ฟ้อง (อันตราย)", must_contain='ไม่ตรง')

# r_tax005: TaxID เป็นของบริษัทอื่นใน master แต่บิลใช้ชื่ออื่น
mm_a = {'name': 'บริษัท เอ', 'tax_id': '0105566206726'}
mm_b = {'name': 'บริษัท บี', 'tax_id': '0999999999999'}
fires(R.r_tax005({'tax_id': '0105566206726', 'company': 'บริษัท บี'},
                 mm_b, ctx(all_masters={'a': mm_a, 'b': mm_b})),
      "TAX005 TaxID ของบริษัทอื่น แต่บิลใช้ชื่อผิด → ฟ้อง", must_contain='เป็นของ')

# r_tax006: checksum ไม่ผ่าน
fires(R.r_tax006({'tax_id': '1111111111111'}, M, ctx()),
      "TAX006 checksum ไม่ผ่าน → ฟ้อง", must_contain='checksum')

# r_tax007: ชื่อเป็นนิติบุคคล แต่เลขขึ้นต้น 1-8
fires(R.r_tax007({'tax_id': '1101700207221', 'company': 'บริษัท เอ บี ซี จำกัด'}, M, ctx()),
      "TAX007 นิติบุคคล แต่เลขขึ้นต้น 1 → ฟ้อง", must_contain='บุคคลธรรมดา')

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print("[IV/DATE] กฎเอกสาร/วันที่")
print("=" * 64)

# r_iv001: iv_number ไม่มีตัวอักษรนำหน้า → []
silent(R.r_iv001({'iv_number': '12345', 'file': 'f', 'tax_id': '0105566206726', 'company': 'x'},
                 M, ctx()),
       "IV001 IV ไม่มี prefix ตัวอักษร → เงียบ")
# r_iv001: prefix ต่างจาก dominant ของ vendor เดียวกันในไฟล์
sib = [
    {'iv_number': 'IV001', 'file': 'F', 'tax_id': '0105566206726', 'company': 'x'},
    {'iv_number': 'IV002', 'file': 'F', 'tax_id': '0105566206726', 'company': 'x'},
    {'iv_number': 'IV003', 'file': 'F', 'tax_id': '0105566206726', 'company': 'x'},
    {'iv_number': 'IV004', 'file': 'F', 'tax_id': '0105566206726', 'company': 'x'},
]
b_iv = {'iv_number': 'XX009', 'file': 'F', 'tax_id': '0105566206726', 'company': 'x'}
fires(R.r_iv001(b_iv, M, ctx(all_bills_for_iv_check=sib + [b_iv])),
      "IV001 prefix ต่างจากหลักของ vendor → ฟ้อง", must_contain='ต่างจาก prefix หลัก')

# r_dt001: เดือนไม่ตรง target_month
fires(R.r_dt001({'iv_date': dt.date(2025, 3, 10)}, M, ctx(target_month=5)),
      "DT001 เดือนไม่ตรง target → ฟ้อง", must_contain='ไม่ตรงเดือน')

# r_dt003: ปีพ.ศ. ผิดปกติแบบต่าง ๆ
fires(R.r_dt003({'iv_date': dt.date(2596, 1, 1)}, M, ctx()),
      "DT003 ปี 2596 = digit swap ของ 2569 → ฟ้อง", must_contain='digit swap')
fires(R.r_dt003({'iv_date': dt.date(2540, 1, 1)}, M, ctx()),
      "DT003 ปี 2540 เก่ามาก → ฟ้อง", must_contain='เก่ามาก')
fires(R.r_dt003({'iv_date': dt.date(2580, 1, 1)}, M, ctx()),
      "DT003 ปี 2580 เกินปีปัจจุบัน → ฟ้อง", must_contain='เกินปีปัจจุบัน')
fires(R.r_dt003({'iv_date': dt.date(2650, 1, 1)}, M, ctx()),
      "DT003 ปี 2650 > 2600 ผิดปกติ → ฟ้อง", must_contain='ผิดปกติ')
fires(R.r_dt003({'iv_date': dt.date(2400, 1, 1)}, M, ctx()),
      "DT003 ปี 2400 (2030<ปี<2500) คลุมเครือ → ฟ้อง", must_contain='คลุมเครือ')

# r_dt004: ปีนอกช่วง + วันที่ผิดรูป (ใช้ date-like object สำหรับ month/day ที่ date จริงสร้างไม่ได้)
fires(R.r_dt004({'iv_date': dt.date(2600, 1, 1)}, M, ctx()),
      "DT004 ปี ค.ศ. 2600 เกินช่วง → ฟ้อง", must_contain='เกินช่วงปกติ')
fires(R.r_dt004({'iv_date': dt.date(2000, 1, 1)}, M, ctx()),
      "DT004 ปี ค.ศ. 2000 ก่อน 2555 → ฟ้อง", must_contain='ก่อน')
fires(R.r_dt004({'iv_date': SimpleNamespace(year=2020, month=0, day=0)}, M, ctx()),
      "DT004 เดือน=0 และ วัน=0 (date-like) → ฟ้อง", must_contain='ผิดปกติ')
fires(R.r_dt004({'iv_date': SimpleNamespace(year=2020, month=1, day=40)}, M, ctx()),
      "DT004 วัน=40 > 31 (date-like) → ฟ้อง", must_contain='> 31')

# r_doc003: IV ซ้ำในไฟล์ (ผู้ขาย+เลข+วันที่ตรง)
d = dt.date(2025, 5, 15)
twin = {'iv_number': 'IV001', 'file': 'F', 'tax_id': '0105566206726', 'iv_date': d}
b_doc = {'iv_number': 'IV001', 'file': 'F', 'tax_id': '0105566206726', 'iv_date': d}
fires(R.r_doc003(b_doc, M, ctx(all_bills_for_iv_check=[twin, b_doc])),
      "DOC003 IV ซ้ำ (ผู้ขาย+เลข+วันเดียวกัน) → ฟ้อง", must_contain='ซ้ำ')
# r_doc003: iv_number ว่าง แต่มี all_bills → []
silent(R.r_doc003({'iv_number': '', 'file': 'F'}, M, ctx(all_bills_for_iv_check=[twin])),
       "DOC003 IV ว่าง → เงียบ")

# r_br003: บริษัทเดียวใช้ทั้งสนญ.+สาขา ในไฟล์
hq = {'tax_id': '0105566206726', 'branch_no': '00000', 'file': 'F'}
br = {'tax_id': '0105566206726', 'branch_no': '00001', 'file': 'F'}
fires(R.r_br003(hq, M, ctx(all_bills_for_iv_check=[hq, br])),
      "BR003 สนญ.+สาขา ปนในไฟล์ → ฟ้อง", must_contain='สำนักงานใหญ่')

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print("[ITM] กฎรายการสินค้า")
print("=" * 64)

# r_itm001: qty×price≠amount เกือบทั้งใบ (≥5, ≥60% พลาด) → สรุปคอลัมน์เพี้ยน
bad_items = [item(i, f'สินค้า{i}', 2, 'ชิ้น', 100, 999) for i in range(1, 7)]
fires(R.r_itm001({'items': bad_items}, M, ctx()),
      "ITM001 ผิดเกือบทั้งใบ → สรุปคอลัมน์เพี้ยน", must_contain='คอลัมน์')

# r_itm002: ลำดับซ้ำ + ฟันหลอ
fires(R.r_itm002({'items': [item(1, 'a', 1, 'x', 1, 1), item(1, 'b', 1, 'x', 1, 1),
                            item(3, 'c', 1, 'x', 1, 1)]}, M, ctx()),
      "ITM002 ลำดับซ้ำ/ฟันหลอ → ฟ้อง")

# r_itm013: ลำดับไม่เรียง + ไม่เริ่มที่ 1
fires(R.r_itm013({'items': [item(3, 'a', 1, 'x', 1, 1), item(2, 'b', 1, 'x', 1, 1)]}, M, ctx()),
      "ITM013 ลำดับไม่เรียง/ไม่เริ่ม 1 → ฟ้อง")

# r_itm014: gap ใหญ่ > 10
fires(R.r_itm014({'items': [item(1, 'a', 1, 'x', 1, 1), item(2, 'b', 1, 'x', 1, 1),
                            item(20, 'c', 1, 'x', 1, 1)]}, M, ctx()),
      "ITM014 gap ใหญ่ (#2→#20) → ฟ้อง", must_contain='gap')

# r_itm015: หน่วยต่างกลุ่มของชื่อเดียวกัน (unit_index)
idx = {'เหล็กเส้น': {'เส้น', 'กก.'}}
fires(R.r_itm015({'items': [item(1, 'เหล็กเส้น', 1, 'เส้น', 1, 1)]}, M, ctx(unit_index=idx)),
      "ITM015 ชื่อเดียวใช้หน่วยต่างกลุ่ม → ฟ้อง")

# r_itm017: ค่าติดลบในจำนวน/ราคา
fires(R.r_itm017({'items': [item(1, 'ของ', -5, 'ชิ้น', 100, -500)]}, M, ctx()),
      "ITM017 จำนวนติดลบ → ฟ้อง", must_contain='ติดลบ')
silent(R.r_itm017({'items': [item(1, 'ส่วนลดท้ายบิล', -5, 'ชิ้น', -100, 500)]}, M, ctx()),
       "ITM017 บรรทัดส่วนลดติดลบ → เงียบ (ตั้งใจติดลบ)")

# r_itm003: ชื่อคลุมเครือ
fires(R.r_itm003({'items': [item(1, 'ค่าบริการ', 1, '', 1, 1)]}, M, ctx()),
      "ITM003 ชื่อคลุมเครือ 'ค่าบริการ' → ฟ้อง", must_contain='คลุมเครือ')

# r_itm004: อักขระแปลก (zero-width) ใน name_raw
fires(R.r_itm004({'items': [item(1, 'เหล็ก', 1, 'x', 1, 1, name_raw='เหล็ก\u200bเส้น')]}, M, ctx()),
      "ITM004 อักขระล่องหนในชื่อ → ฟ้อง", must_contain='อักขระ')

# r_itm005: หน่วยไม่เหมาะกับประเภท (soft) — โคมไฟ ควร ชุด/โคม
fires(R.r_itm005({'items': [item(1, 'โคมไฟ LED', 1, 'กก.', 100, 100)]}, M, ctx()),
      "ITM005 โคมไฟ หน่วย กก. → soft mismatch", must_contain='soft')

# r_itm006: ในชื่อบอกหน่วย (แกลลอน) แต่ใช้หน่วยต่างกลุ่ม (เส้น)
fires(R.r_itm006({'items': [item(1, 'น้ำยาเคมี 5 แกลลอน', 1, 'เส้น', 100, 100)]}, M, ctx()),
      "ITM006 ชื่อระบุ 'แกลลอน' แต่หน่วย 'เส้น' → ฟ้อง", must_contain='แกลลอน')

# r_itm007: ชื่อสั้นเกินไป (1 ตัวอักษร, ไม่ใช่ spec/รหัส)
fires(R.r_itm007({'items': [item(1, 'X', 1, 'x', 1, 1)]}, M, ctx()),
      "ITM007 ชื่อสั้น 'X' → ฟ้อง", must_contain='สั้นเกินไป')

# r_itm008: ราคา outlier (ผ่าน gate ความเชื่อถือคอลัมน์)
oi = [item(i, f'ของ{i}', 1, 'ชิ้น', 100, 100) for i in range(1, 6)]
oi.append(item(6, 'ของแพง', 1, 'ชิ้น', 100000, 100000))
fires(R.r_itm008({'items': oi}, M, ctx()),
      "ITM008 ราคา/หน่วย outlier (1000×median) → ฟ้อง", must_contain='ผิดปกติ')

# r_itm009 + _build_product_whitelist + validate_product_word: ต้องมี PRODUCT_MASTER
_saved_pm = R.PRODUCT_MASTER
_saved_wl = state._PRODUCT_WHITELIST
try:
    R.PRODUCT_MASTER = {'เหล็กแท้': {'aliases': ['เหล็กเทียม']}}
    state._PRODUCT_WHITELIST = None  # บังคับ rebuild ให้แตะ loop PRODUCT_MASTER
    fires(R.r_itm009({'items': [item(1, 'เหล็กเทียมเกรดบี', 1, 'x', 1, 1)]}, M, ctx()),
          "ITM009 ใช้ alias → ควรใช้ชื่อ canonical", must_contain='alias')
    wl = R._build_product_whitelist()
    check('เหล็กแท้' in wl and 'เหล็กเทียม' in wl,
          "_build_product_whitelist รวม canonical+alias จาก PRODUCT_MASTER")
    state._PRODUCT_WHITELIST = wl
    check(R.validate_product_word('เหล็กแท้')['status'] == 'correct',
          "validate_product_word คำใน whitelist → correct")
    check(R.validate_product_word('  ')['status'] == 'unknown',
          "validate_product_word คำว่าง → unknown")
    check(R.validate_product_word('กก')['status'] == 'unknown',
          "validate_product_word คำสั้น (<min) → unknown")
    check(R.validate_product_word('ฮกุไม่มีจริงเลยนะ')['status'] == 'unknown',
          "validate_product_word คำไม่ใกล้เคียงอะไร → unknown")
finally:
    R.PRODUCT_MASTER = _saved_pm
    state._PRODUCT_WHITELIST = _saved_wl

# r_itm016: รายการซ้ำ (name+unit+price ตรง)
fires(R.r_itm016({'items': [item(1, 'เหล็ก', 2, 'เส้น', 100, 200),
                            item(2, 'เหล็ก', 2, 'เส้น', 100, 200)]}, M, ctx()),
      "ITM016 รายการซ้ำ → ฟ้อง", must_contain='ซ้ำ')

# r_itm018: หลายเคส
fires(R.r_itm018({'items': [item(1, 'a', 0, 'x', 10, 500)]}, M, ctx()),
      "ITM018 qty=0 แต่ amount≠0 → ฟ้อง", must_contain='qty=0')
fires(R.r_itm018({'items': [item(1, 'a', 5, 'x', 10, 0)]}, M, ctx()),
      "ITM018 qty>0 price>0 แต่ amount=0 → ฟ้อง", must_contain='amount=0')
fires(R.r_itm018({'items': [item(1, 'a', 99999, 'x', 10, 999990)]}, M, ctx()),
      "ITM018 qty=99999 กลมใหญ่ → ฟ้อง", must_contain='กลมใหญ่')
fires(R.r_itm018({'items': [item(1, 'a', 2, 'x', 100, 9999)]}, M, ctx()),
      "ITM018 qty×price≠amount (ไม่ใช่ส่วนลด) → ฟ้อง", must_contain='≠ amount')

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print("[VAT] กฎยอดเงิน")
print("=" * 64)

# r_vat004: ค่าไม่ใช่ตัวเลข → except (continue) ไม่ throw
silent(R.r_vat004({'subtotal': 'ไม่ใช่เลข', 'vat': None, 'total': None}, M, ctx()),
       "VAT004 subtotal ไม่ใช่ตัวเลข → ข้ามอย่างปลอดภัย")

# r_vat005: ติดลบ / total<subtotal / total=0
fires(R.r_vat005({'subtotal': -10.0, 'vat': None, 'total': None}, M, ctx()),
      "VAT005 subtotal ติดลบ → ฟ้อง", must_contain='ติดลบ')
fires(R.r_vat005({'subtotal': 100.0, 'vat': 7.0, 'total': 50.0}, M, ctx()),
      "VAT005 total<subtotal → ฟ้อง", must_contain='เป็นไปไม่ได้')
fires(R.r_vat005({'subtotal': 100.0, 'vat': 0.0, 'total': 0.0}, M, ctx()),
      "VAT005 total=0 ทั้งที่ subtotal>0 → ฟ้อง", must_contain='total=0')

# r_vat007: VAT คำนวณก่อนหักส่วนลด
its = [item(1, 'a', 1, 'x', 1000, 1000)]
fires(R.r_vat007({'subtotal': 900.0, 'vat': 70.0, 'total': 963.0, 'items': its}, M, ctx()),
      "VAT007 VAT คิดก่อนหักส่วนลด → ฟ้อง", must_contain='ส่วนลด')

# r_vat008: VAT=0 ทั้งที่ยอดสูง
fires(R.r_vat008({'vat': 0.0, 'total': 50000.0, 'subtotal': 46728.97,
                  'items': [item(1, 'a', 1, 'x', 1, 1)]}, M, ctx()),
      "VAT008 VAT=0 ยอด>10000 (sub≠total) → ฟ้อง", must_contain='VAT เป็น 0')
silent(R.r_vat008({'vat': 0.0, 'total': 50000.0, 'subtotal': 50000.0,
                   'items': [item(1, 'a', 1, 'x', 1, 1)]}, M, ctx()),
       "VAT008 VAT=0 แต่ sub≈total (ยกเว้นจริง) → เงียบ")

# r_vat009: ไม่มี subtotal (มี total) / subtotal=0
fires(R.r_vat009({'subtotal': None, 'total': 100.0,
                  'items': [item(1, 'a', 1, 'x', 1, 1)]}, M, ctx()),
      "VAT009 ไม่มี subtotal (มี total) → ฟ้อง", must_contain='ไม่มี subtotal')
fires(R.r_vat009({'subtotal': 0.0, 'total': 100.0,
                  'items': [item(1, 'a', 1, 'x', 1, 1)]}, M, ctx()),
      "VAT009 subtotal=0 ทั้งที่มีรายการ → ฟ้อง", must_contain='subtotal=0')
silent(R.r_vat009({'subtotal': 'x', 'total': 1.0,
                   'items': [item(1, 'a', 1, 'x', 1, 1)]}, M, ctx()),
       "VAT009 subtotal ไม่ใช่ตัวเลข → ข้ามอย่างปลอดภัย")

# r_vat010: ยอดที่ระบบ derive เอง (ไม่ได้อ่านจากเอกสาร)
fires(R.r_vat010({'amount_source': {'vat': 'derived', 'subtotal': 'parsed', 'total': 'item_sum'}}, M, ctx()),
      "VAT010 ยอด derived/item_sum → เตือนให้ตรวจตา", must_contain='เติมเอง')
silent(R.r_vat010({'amount_source': {'vat': 'parsed', 'subtotal': 'parsed', 'total': 'parsed'}}, M, ctx()),
       "VAT010 ทุกยอดอ่านจริง → เงียบ")

# ── load_product_master: ไฟล์ไม่มี → {} ──
check(isinstance(R.load_product_master(), dict),
      "load_product_master คืน dict เสมอ (ไฟล์ไม่มี → {})")

# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 64)
print(f"RULES EXTRA: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    print("รายการที่ล้ม:")
    for f in FAIL:
        print(f"  • {f}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ กิ่งฟ้องของกฎ r_* ถูกต้องตามเจตนา + ทนทาน")
sys.exit(0)
