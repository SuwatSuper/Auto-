# -*- coding: utf-8 -*-
"""test_adr193_itm001_zero_line.py — [ADR-193] ITM001: 'ศูนย์' ไม่ใช่ 'ค่าหาย'

บั๊ก (สูง, false-clean): r_itm001 คัดบรรทัดด้วยความจริงเชิงตรรกะ
    if not (it['qty'] and it['price'] and it['amount']): continue
ใน Python `0`/`0.0` เป็น falsy เท่ากับ `None` → บรรทัดที่ค่าใดค่าหนึ่งอ่านได้เป็น **ศูนย์จริง**
ถูกจัดเป็น "ข้อมูลหาย" แล้วข้ามเงียบ ทั้งที่ 0 คือค่าที่อ่านได้และต้องตรวจ.

ผลจริงที่พิสูจน์แล้ว (oracle_itm_matrix.py): บรรทัด qty=5 price=0 amount=500
  · ITM001 ข้าม (price=0 falsy)
  · ITM018 ข้ามด้วย (ทุกสาขาที่เทียบ qty×price ต้องการ price_f > 0)
  → หลุดทั้งสองกฎ = false-clean (ยอด 500 บาทไม่ถูกตรวจสอบเลย แต่รีพอร์ตขึ้น 'ตรง')

แก้: คัดด้วย `is None` (= ค่าหายจริง) แทนความจริงเชิงตรรกะ — ขอบเขต 1 บรรทัดใน r_itm001.
corpus จริง 0 บรรทัดที่มีศูนย์ (oracle_zero_lines.py: real_cases 0/80, fixtures 0/3)
→ no-op บนข้อมูลจริง → golden-NEUTRAL.

เทสนี้ล็อกทั้งสองทาง: เคสบวก (ต้องฟ้อง) + เคสลบ (ห้ามฟ้องเกิน).
รันได้ทุกที่ (ไม่ต้องมี corpus).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rules_engine as RE

FAILS = []

CTX = {'sheet_name': '1', 'target_month': None, 'target_month_end': None,
       'all_masters': {}, 'unit_index': None, 'all_bills_for_iv_check': [],
       'xbill_tax_index': {}, 'xbill_file_index': {}, 'xbill_iv_index': {}}


def _check(cond, msg):
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        FAILS.append(msg)


def _bill(items):
    return {'file': 't.xls', 'sheet': 's', 'block_idx': 0,
            'company': 'บริษัท ทดสอบ จำกัด', 'company_raw': 'บริษัท ทดสอบ จำกัด',
            'tax_id': '0105551234567', 'tax_id_raw': '0105551234567',
            'branch': 'สำนักงานใหญ่', 'branch_no': '00000',
            'address': '', 'address_raw': '',
            'iv_number': 'IV1', 'iv_number_raw': 'IV1',
            'iv_date': None, 'iv_date_str': '',
            'subtotal': None, 'vat': None, 'total': None,
            'items': items, 'issues': []}


def _item(qty, price, amount, discount=None, seq=1):
    return {'seq': seq, 'name': 'ท่อพีวีซี', 'name_raw': 'ท่อพีวีซี', 'qty': qty,
            'unit': 'เส้น', 'price': price, 'amount': amount, 'discount': discount}


def _itm001(items):
    return RE.RULES['ITM001']['check'](_bill(items), None, CTX) or []


def _any_rule(items):
    """รหัสกฎ ITM*/VAT* ที่ฟ้องบิลนี้ — ใช้พิสูจน์ว่า 'ไม่มีกฎไหนจับเลย'"""
    b = _bill(items)
    out = []
    for code, rule in RE.RULES.items():
        if not code.startswith(('ITM', 'VAT')) or not rule.get('enabled'):
            continue
        try:
            if rule['check'](b, None, CTX):
                out.append(code)
        except Exception:
            out.append('SYS-' + code)
    return out


print("=" * 68)
print("ADR-193 — ITM001: ศูนย์ต้องถูกตรวจ ไม่ใช่ถูกมองว่าเป็นค่าหาย")
print("=" * 68)

# ── เคสบวก: ผิดจริง ต้องฟ้อง ─────────────────────────────────────
print("\n[บวก] บรรทัดที่ผิดจริง — ITM001 ต้องฟ้อง")
_check(bool(_itm001([_item(5, 0, 500.0)])),
       "price=0 แต่ amount=500 (qty×price=0) → ต้องฟ้อง")
_check(bool(_itm001([_item(5, 100, 0.0)])),
       "amount=0 แต่ qty×price=500 → ต้องฟ้อง")
_check(bool(_itm001([_item(0, 100, 500.0)])),
       "qty=0 แต่ amount=500 → ต้องฟ้อง")

# เคสหลุดสองกฎ (ต้นเหตุที่ทำให้เป็น false-clean จริง)
_check(bool(_any_rule([_item(5, 0, 500.0)])),
       "price=0/amount=500 ต้องมีอย่างน้อย 1 กฎจับ (เดิมหลุดทั้ง ITM001+ITM018)")

# ── เคสลบ: ถูกต้องอยู่แล้ว ห้ามฟ้อง (กันแก้เกิน) ──────────────────
print("\n[ลบ] บรรทัดที่ถูกต้อง — ห้ามฟ้อง")
_check(not _itm001([_item(5, 100, 500.0)]),
       "5×100=500 ตรง → เงียบ")
_check(not _itm001([_item(0, 0, 0.0)]),
       "ศูนย์ทั้งบรรทัด (0×0=0) → เงียบ ไม่ใช่ false positive")
_check(not _itm001([_item(0, 100, 0.0)]),
       "qty=0 amount=0 (0×100=0) → เงียบ")
_check(not _itm001([_item(5, 0, 0.0)]),
       "price=0 amount=0 (5×0=0) → เงียบ")
_check(not _itm001([_item(5, 100, 450.0, discount=0.10)]),
       "ส่วนลด 10% พิสูจน์ได้จากเซลล์ → ยอดลงตัว → เงียบ (ADR-189 ไม่ถอย)")

# ── ค่าหายจริง (None) ต้องยังข้ามเหมือนเดิม ──────────────────────
print("\n[ลบ] ค่าหายจริง (None) — ต้องข้ามเหมือนเดิม ห้ามเดา")
_check(not _itm001([_item(None, 100, 500.0)]), "qty=None → ข้าม")
_check(not _itm001([_item(5, None, 500.0)]), "price=None → ข้าม")
_check(not _itm001([_item(5, 100, None)]), "amount=None → ข้าม")

# ── ADR-189 ไม่ถอย: ไม่มีเซลล์ส่วนลด = ต้องฟ้องเสมอ ───────────────
print("\n[บวก] ADR-189 ไม่ถอย — ไม่มีส่วนลดในเอกสารต้องฟ้องทุกช่วง %")
_check(bool(_itm001([_item(5, 100, 450.0)])), "ต่ำกว่า 10% ไม่มี discount → ฟ้อง")
_check(bool(_itm001([_item(5, 100, 300.0)])), "ต่ำกว่า 40% ไม่มี discount → ฟ้อง")

print("\n" + "=" * 68)
if FAILS:
    print(f"RESULT: ❌ {len(FAILS)} ข้อไม่ผ่าน")
    for f in FAILS:
        print("   -", f)
    sys.exit(1)
print("RESULT: ✅ ผ่านทั้งหมด — ITM001 ตรวจศูนย์ได้ และไม่ฟ้องเกิน")
sys.exit(0)
