# -*- coding: utf-8 -*-
"""test_verification_lenses_unit.py — unit test ราย "ผู้ตรวจ" (lens) ในคลัง

ทดสอบแต่ละเลนส์ "อย่างโดดเดี่ยว" (เรียก fn ตรง ๆ) ครอบ +1/0/-1 + เคสขอบ (ข้อมูลว่าง/ไม่เกี่ยว).
รองรับ OBJ-TEST (coverage) + ทำให้เพิ่มผู้ตรวจใหม่ได้อย่างมั่นใจ.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_verification_lenses_unit.py
"""

import os, sys, io, datetime, contextlib, warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
from agents.verification_lenses import (
    LensInput,
    _build_cross_index,
    lens_vat_7pct_exact,
    lens_rounding_explains,
    lens_amount_completeness,
    lens_money_triple,
    lens_line_sum_amount,
    lens_line_qty_price,
    lens_negative_sanity,
    lens_magnitude_outlier,
    lens_taxid_checksum,
    lens_taxid_format,
    lens_taxid_crosscompany,
    lens_duplicate_signature,
    lens_period_match,
    lens_doc_completeness,
    lens_master_known,
    lens_iv_prefix_match,
    lens_vat_zero_exempt,
    lens_item_count_sanity,
    lens_line_amount_negative,
    lens_duplicate_line_in_bill,
    lens_company_multi_taxid,
    lens_total_lt_subtotal,
    lens_decimal_scale_error,
    lens_vat_present_no_base,
)

PASS, FAIL = 0, []


def vote(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def X(code, idx=None, master=None, peers=None, **bill):
    return LensInput(
        bill=bill,
        issue={"code": code},
        code=code,
        sev="ERROR",
        peers=peers or [],
        llm=None,
        index=idx or {},
        master=master or {},
    )


print("=" * 64)
print("LENS UNIT — ผู้ตรวจราย lens (30 ผู้ตรวจ)")
print("=" * 64)

print("\n[L8 vat_7pct_exact] กฎโดเมนล็อก round(sub×0.07,2) — ห้าม band")
vote(
    lens_vat_7pct_exact(X("VAT002", subtotal=1000.0, vat=70.0))[0] == -1,
    "vat 70 (7%เป๊ะ) → -1",
)
vote(
    lens_vat_7pct_exact(X("VAT002", subtotal=1000.0, vat=75.0))[0] == 1,
    "vat 75 (เกินปัดเศษ) → +1",
)
vote(
    lens_vat_7pct_exact(X("VAT002", subtotal=1234.0, vat=86.38))[0] == -1,
    "vat=round(86.38)เป๊ะ → -1",
)
vote(
    lens_vat_7pct_exact(X("VAT002", subtotal=1000.0, vat=0.0))[0] == 0,
    "vat 0 (อาจ exempt) → 0",
)
vote(
    lens_vat_7pct_exact(X("VAT001", subtotal=1000.0, vat=70.0))[0] == 0,
    "ไม่ใช่ VAT002 → 0",
)

print("\n[L7 rounding_explains] refute ส่วนต่าง ≤ 0.50")
vote(
    lens_rounding_explains(X("VAT003", subtotal=1000.0, vat=70.0, total=1070.30))[0]
    == -1,
    "gap 0.30 → -1",
)
vote(
    lens_rounding_explains(X("VAT003", subtotal=1000.0, vat=70.0, total=1075.0))[0]
    == 0,
    "gap 5 → 0",
)
vote(
    lens_rounding_explains(X("TAX001", subtotal=1.0, vat=1.0, total=99.0))[0] == 0,
    "ไม่ใช่ money → 0",
)

print("\n[L11 amount_completeness]")
vote(
    lens_amount_completeness(X("VAT003", subtotal=1000.0, vat=None, total=1070.0))[0]
    == -1,
    "vat ว่าง → -1",
)
vote(
    lens_amount_completeness(X("VAT003", subtotal=1000.0, vat=70.0, total=1070.0))[0]
    == 0,
    "ครบ → 0",
)

print("\n[L12 money_triple]")
vote(
    lens_money_triple(X("VAT001", subtotal=1000.0, vat=70.0, total=1070.0))[0] == -1,
    "sub+vat=total → -1",
)
vote(
    lens_money_triple(X("VAT001", subtotal=1000.0, vat=70.0, total=1200.0))[0] == 1,
    "ไม่สอดคล้อง → +1",
)
vote(
    lens_money_triple(X("TAX001", subtotal=1000.0, vat=70.0, total=1070.0))[0] == 0,
    "ไม่ใช่ money → 0",
)

print("\n[L13 line_sum_amount] / [L14 line_qty_price]")
items_ok = [
    {"qty": 2.0, "price": 100.0, "amount": 200.0},
    {"qty": 1.0, "price": 800.0, "amount": 800.0},
]
vote(
    lens_line_sum_amount(X("VAT001", subtotal=1000.0, items=items_ok))[0] == -1,
    "Σamount=sub → -1",
)
vote(
    lens_line_sum_amount(X("VAT001", subtotal=999.0, items=items_ok))[0] == 1,
    "Σamount≠sub → +1",
)
vote(
    lens_line_qty_price(X("VAT001", subtotal=1000.0, items=items_ok))[0] == -1,
    "Σ(q×p)=sub → -1",
)
vote(
    lens_line_qty_price(X("VAT001", subtotal=500.0, items=items_ok))[0] == 1,
    "Σ(q×p)≠sub → +1",
)
vote(
    lens_line_sum_amount(X("VAT001", subtotal=1000.0, items=[]))[0] == 0,
    "ไม่มีรายการ → 0",
)

print("\n[L15 negative_sanity]")
vote(
    lens_negative_sanity(X("ITM017", subtotal=-500.0, vat=-35.0, total=-535.0))[0] == 1,
    "ยอดติดลบ → +1",
)
vote(
    lens_negative_sanity(X("ITM017", subtotal=500.0, vat=35.0, total=535.0))[0] == 0,
    "ยอดบวก → 0",
)

print("\n[L16 magnitude_outlier] ต้องมีพี่น้อง ≥3")
peers = [{"total": 100.0}, {"total": 105.0}, {"total": 95.0}, {"total": 102.0}]
vote(
    lens_magnitude_outlier(X("VAT001", total=100000.0, peers=peers))[0] == 1,
    "outlier 100000 → +1",
)
vote(
    lens_magnitude_outlier(X("VAT001", total=101.0, peers=peers))[0] == -1,
    "ในช่วงปกติ → -1",
)
vote(
    lens_magnitude_outlier(X("VAT001", total=100000.0, peers=[{"total": 1.0}]))[0] == 0,
    "พี่น้อง <3 → 0",
)

print("\n[L9 taxid_checksum] / [L10 taxid_format]")
vote(
    lens_taxid_checksum(X("TAX001", tax_id="0105000000012"))[0] == -1,
    "checksum ผ่าน → -1",
)
vote(
    lens_taxid_checksum(X("TAX006", tax_id="1111111111111"))[0] == 1,
    "checksum ไม่ผ่าน → +1",
)
vote(lens_taxid_checksum(X("TAX001", tax_id="123"))[0] == 0, "ไม่ใช่ 13 หลัก → 0")
vote(
    lens_taxid_format(X("TAX001", tax_id="0105000000012"))[0] == -1, "13 หลักล้วน → -1"
)
vote(lens_taxid_format(X("TAX001", tax_id="12345"))[0] == 1, "5 หลัก → +1")
vote(lens_taxid_format(X("TAX001"))[0] == 0, "ไม่มีเลข → 0")

print("\n[L17 taxid_crosscompany] / [L18 duplicate_signature] (index ข้ามบิล)")
xbills = [
    {"tax_id": "0105000000012", "company": "บ.หนึ่ง", "total": 1070.0},
    {"tax_id": "0105000000012", "company": "บ.สอง", "total": 1070.0},
]
idx = _build_cross_index(xbills, {})
vote(
    lens_taxid_crosscompany(X("TAX002", idx=idx, tax_id="0105000000012"))[0] == 1,
    "เลขเดียว 2 บริษัท → +1",
)
vote(
    lens_taxid_crosscompany(
        X("TAX002", idx=_build_cross_index([xbills[0]], {}), tax_id="0105000000012")
    )[0]
    == 0,
    "บริษัทเดียว → 0",
)
vote(
    lens_duplicate_signature(
        X("TAX002", idx=idx, tax_id="0105000000012", total=1070.0)
    )[0]
    == 1,
    "ยอด+เลขซ้ำ → +1",
)
vote(
    lens_duplicate_signature(X("TAX002", idx=idx, tax_id="0105000000012", total=999.0))[
        0
    ]
    == 0,
    "ยอดไม่ซ้ำ → 0",
)

print("\n[L19 period_match]")
fi = {"year": 2025, "month": 1}
vote(
    lens_period_match(X("IV001", file_info=fi, iv_date=datetime.datetime(2025, 1, 15)))[
        0
    ]
    == -1,
    "ตรงงวด → -1",
)
vote(
    lens_period_match(
        X("IV001", file_info=fi, iv_date=datetime.datetime(2024, 12, 15))
    )[0]
    == 1,
    "ผิดปี → +1",
)
vote(
    lens_period_match(
        X("IV001", file_info={"year": None}, iv_date=datetime.datetime(2025, 1, 1))
    )[0]
    == 0,
    "ไฟล์ไม่ระบุงวด → 0",
)

print("\n[L20 doc_completeness]")
vote(
    lens_doc_completeness(X("VAT001", company="", iv_number=""))[0] == -1,
    "ขาด ≥2 ฟิลด์ → -1",
)
vote(
    lens_doc_completeness(
        X(
            "VAT001",
            company="บ.ก",
            tax_id="0105000000012",
            iv_number="IV1",
            iv_date=datetime.datetime(2025, 1, 1),
        )
    )[0]
    == 0,
    "ครบ → 0",
)

print("\n[L21 master_known] / [L22 iv_prefix_match]")
M = {"k": {"tax_id": "0105000000012", "iv_prefix": "IV"}}
midx = _build_cross_index([], M)
vote(
    lens_master_known(X("TAX001", idx=midx, master=M, tax_id="0105000000012"))[0] == -1,
    "อยู่ใน master → -1",
)
vote(
    lens_master_known(X("TAX001", idx=midx, master=M, tax_id="9999999999999"))[0] == 0,
    "ไม่อยู่ใน master → 0",
)
vote(
    lens_iv_prefix_match(X("IV001", idx=midx, master=M, iv_number="IV6801"))[0] == -1,
    "prefix ตรง → -1",
)
vote(
    lens_iv_prefix_match(X("IV001", idx=midx, master=M, iv_number="XX001"))[0] == 1,
    "prefix ไม่ตรง → +1",
)

print("\n[L23 vat_zero_exempt] vat=0 ทั้งที่มี subtotal>0 → ค้าน")
vote(
    lens_vat_zero_exempt(X("VAT002", subtotal=1000.0, vat=0.0))[0] == -1,
    "vat 0 + sub>0 → -1",
)
vote(
    lens_vat_zero_exempt(X("VAT002", subtotal=1000.0, vat=70.0))[0] == 0,
    "vat 70 → 0",
)
vote(
    lens_vat_zero_exempt(X("TAX001", subtotal=1000.0, vat=0.0))[0] == 0,
    "ไม่ใช่ money → 0",
)

print("\n[L24 item_count_sanity] ไม่มีรายการแต่มี subtotal → ค้าน")
vote(
    lens_item_count_sanity(X("VAT001", subtotal=1000.0, items=[]))[0] == -1,
    "0 รายการ + sub>0 → -1",
)
vote(
    lens_item_count_sanity(X("VAT001", subtotal=1000.0, items=[{"amount": 1000.0}]))[0]
    == 0,
    "มีรายการ → 0",
)

print("\n[L25 line_amount_negative] รายการยอดติดลบ → ยืนยัน")
vote(
    lens_line_amount_negative(X("ITM017", items=[{"amount": -500.0}]))[0] == 1,
    "amount ติดลบ → +1",
)
vote(
    lens_line_amount_negative(X("VAT001", items=[{"amount": 500.0}]))[0] == 0,
    "amount บวก → 0",
)

print("\n[L26 duplicate_line_in_bill] รายการ (ชื่อ+ยอด) ซ้ำในบิล → ยืนยัน")
dup_items = [
    {"name": "เหล็กเส้น", "amount": 100.0},
    {"name": "เหล็กเส้น", "amount": 100.0},
]
vote(
    lens_duplicate_line_in_bill(X("VAT001", items=dup_items))[0] == 1,
    "ชื่อ+ยอดซ้ำ → +1",
)
vote(
    lens_duplicate_line_in_bill(
        X("VAT001", items=[{"name": "a", "amount": 1.0}, {"name": "b", "amount": 2.0}])
    )[0]
    == 0,
    "ไม่ซ้ำ → 0",
)

print("\n[L27 company_multi_taxid] (index) บริษัทเดียว 2 เลขภาษี → ยืนยัน")
co_bills = [
    {"tax_id": "0105000000012", "company": "บ.เดียวกัน", "total": 1.0},
    {"tax_id": "0107000000017", "company": "บ.เดียวกัน", "total": 2.0},
]
cidx = _build_cross_index(co_bills, {})
vote(
    lens_company_multi_taxid(X("TAX002", idx=cidx, company="บ.เดียวกัน"))[0] == 1,
    "บริษัทเดียว 2 เลขภาษี → +1",
)
vote(
    lens_company_multi_taxid(
        X("TAX002", idx=_build_cross_index([co_bills[0]], {}), company="บ.เดียวกัน")
    )[0]
    == 0,
    "บริษัทเดียว 1 เลขภาษี → 0",
)
vote(
    lens_company_multi_taxid(X("VAT001", idx=cidx, company="บ.เดียวกัน"))[0] == 0,
    "ไม่ใช่ TAX → 0",
)

print("\n[L28 total_lt_subtotal] ยอดรวม < ยอดก่อนภาษี → ยืนยัน")
vote(
    lens_total_lt_subtotal(X("VAT003", subtotal=1000.0, total=900.0))[0] == 1,
    "total<sub → +1",
)
vote(
    lens_total_lt_subtotal(X("VAT003", subtotal=1000.0, total=1070.0))[0] == 0,
    "total>sub → 0",
)
vote(
    lens_total_lt_subtotal(X("ITM017", subtotal=-500.0, total=-535.0))[0] == 0,
    "subtotal ติดลบ (guard) → 0",
)

print("\n[L29 decimal_scale_error] อัตราส่วน ≈ 10/100 เท่า → ยืนยัน")
vote(
    lens_decimal_scale_error(X("VAT003", subtotal=100.0, total=1000.0))[0] == 1,
    "total≈10×sub → +1",
)
vote(
    lens_decimal_scale_error(X("VAT003", subtotal=1000.0, total=1070.0))[0] == 0,
    "อัตราส่วนปกติ → 0",
)

print("\n[L30 vat_present_no_base] มี VAT แต่ไม่มี subtotal → ยืนยัน")
vote(
    lens_vat_present_no_base(X("VAT002", subtotal=None, vat=70.0))[0] == 1,
    "vat 70 + ไม่มี sub → +1",
)
vote(
    lens_vat_present_no_base(X("VAT002", subtotal=1000.0, vat=70.0))[0] == 0,
    "มี sub → 0",
)
vote(
    lens_vat_present_no_base(X("VAT002", subtotal=None, vat=0.0))[0] == 0,
    "vat≈0 → 0",
)

print("\n" + "=" * 64)
print(f"LENS UNIT: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ ทุกผู้ตรวจผ่านครบ (+1/0/-1) + เคสขอบ")
sys.exit(0)
