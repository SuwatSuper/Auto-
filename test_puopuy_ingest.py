# -*- coding: utf-8 -*-
"""test_puopuy_ingest.py — ตรึง Adapter Layer (ADR-016): Thai-words/VAT/reconcile/classify

ครอบเคสตามเอกสาร PROMPT (ข้อ 5 ความครอบคลุม) — deterministic, offline, ไม่ต้องมีไฟล์จริง:
  • Thai-words→number: หลัก/สิบ/ร้อย/พัน/หมื่น/แสน/ล้าน + เอ็ด + ยี่สิบ + บาท/สตางค์/ถ้วน + วงเล็บ TOR
  • VAT normalize: 0.07 (สัดส่วน) และ 7 (เปอร์เซ็นต์เต็ม แบบ SBT) + float noise
  • reconcile 3 ทาง: ตรง→OK ; ขัด→MISMATCH ระบุจุด ; over-sum (ITM008-b) จับได้
  • classify_row: words_total ไม่ถูกมองเป็น line_item (แก้ราก ITM01)
  • ingest_bill: ยอดไม่ reconcile → needs_human_review (fail loud) ไม่ออก 'ลืมเลขลำดับ'

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_puopuy_ingest.py
"""

import os
import sys
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
import puopuy_ingest as I

PASS, FAIL = 0, []


def check(c, label):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def D(x):
    return Decimal(str(x))


print("=" * 64)
print("PUOPUY INGEST (ADR-016) — adapter layer (Thai-words/VAT/reconcile)")
print("=" * 64)

print("\n[1] thai_words_to_number")
cases = {
    "หนึ่งร้อยยี่สิบสามบาทห้าสิบสตางค์": "123.50",
    "สิบล้านบาทถ้วน": "10000000.00",
    "สองล้านหกแสนแปดพันหกบาทยี่สิบห้าสตางค์": "2608006.25",
    "ยี่สิบเอ็ดบาทถ้วน": "21.00",
    "เก้าร้อยเก้าสิบเก้าบาทเก้าสิบเก้าสตางค์": "999.99",
    "หนึ่งพันบาทถ้วน": "1000.00",
    "(หนึ่งหมื่นบาทถ้วน)": "10000.00",  # TOR วงเล็บ
    "จำนวนเงินห้าสิบบาทถ้วน": "50.00",  # มี label นำ
}
for words, expect in cases.items():
    got = I.thai_words_to_number(words)
    check(got == D(expect), f"'{words[:30]}' → {expect} (ได้ {got})")
# ไม่ใช่ยอดตัวอักษร → None (fail loud)
check(
    I.thai_words_to_number("เหล็กเส้น 12 มม.") is None, "ข้อความสินค้า → None (ไม่เดา)"
)
check(I.thai_words_to_number("") is None, "ว่าง → None")

print("\n[2] normalize_vat_rate (0.07 และ 7)")
check(I.normalize_vat_rate("0.07") == D("0.07"), "0.07 (สัดส่วน) → 0.07")
check(I.normalize_vat_rate(7) == D("0.07"), "7 (เปอร์เซ็นต์เต็ม SBT) → 0.07")
check(I.normalize_vat_rate("7%") == D("0.07"), "'7%' → 0.07")
check(I.normalize_vat_rate(0) == D("0"), "0 (ยกเว้น) → 0")
check(I.normalize_vat_rate("x") is None, "อ่านไม่ออก → None")

print("\n[3] reconcile_totals — ตรง/ขัด/over-sum")
# ตรง: net 1000 + vat 70 = grand 1070 ; words=1070 ; line_sum=1000
r_ok = I.reconcile_totals(
    D("1000"),
    D("70"),
    D("1070"),
    words_total=D("1070"),
    line_sum=D("1000"),
    vat_rate=D("0.07"),
)
check(r_ok["status"] == I.RECONCILE_OK, f"ทุกยอดตรง → OK (failed={r_ok['failed']})")

# float noise: vat 2691.5000000000005 ภายใน tol → ยังผ่าน
r_noise = I.reconcile_totals(D("38450"), D("2691.5000000000005"), D("41141.5"))
check(
    r_noise["status"] == I.RECONCILE_OK,
    "float noise (2691.5000000000005) → ยังผ่าน (tol)",
)

# ITM008-b: grand บวกเกิน (10,266,200 แต่จริง 10,000,000) → MISMATCH ชี้ grand=net+vat
r_over = I.reconcile_totals(
    D("9345794.39"), D("654205.61"), D("10266200"), line_sum=D("9345794.39")
)
check(
    r_over["status"] == I.RECONCILE_MISMATCH and "grand=net+vat" in r_over["failed"],
    "over-sum (grand เกิน) → MISMATCH ชี้ grand=net+vat",
)

# คนละเขต words: words=9999 แต่ grand=1070 → MISMATCH
r_w = I.reconcile_totals(D("1000"), D("70"), D("1070"), words_total=D("9999"))
check(r_w["status"] == I.RECONCILE_MISMATCH, "ยอดตัวอักษรไม่ตรงยอดรวม → MISMATCH")

# ข้อมูลไม่พอ
check(
    I.reconcile_totals(None, None, None)["status"] == "INSUFFICIENT",
    "ไม่มีข้อมูล → INSUFFICIENT",
)

print("\n[4] classify_row — words_total ไม่เป็น line_item (ราก ITM01)")
check(
    I.classify_row(["", "สองล้านหกแสนแปดพันหกบาทยี่สิบห้าสตางค์", "", ""])
    == "words_total",
    "แถวยอดตัวอักษร → 'words_total' (ไม่ใช่ line_item)",
)
check(
    I.classify_row(["1", "เหล็กเส้น 12มม.", "10", "58", "580"], seq_col=0)
    == "line_item",
    "แถวสินค้ามี seq → 'line_item'",
)
check(I.classify_row(["", "ภาษีมูลค่าเพิ่ม 7%", "", "70"]) == "vat", "แถว VAT → 'vat'")
check(
    I.classify_row(["", "รวมทั้งสิ้น", "", "1070"]) == "grand_total",
    "แถวยอดรวม → 'grand_total'",
)
check(I.classify_row(["", "", "", ""]) == "blank", "แถวว่าง → 'blank'")

print("\n[5] ingest_bill — fail loud (needs_human_review)")
b_ok = {
    "subtotal": 1000,
    "vat": 70,
    "total": 1070,
    "amount_in_words": "หนึ่งพันเจ็ดสิบบาทถ้วน",
    "items": [{"amount": 600}, {"amount": 400}],
}
out_ok = I.ingest_bill(b_ok)
check(
    out_ok["needs_human_review"] is False and out_ok["reconcile_status"] == "OK",
    f"บิลสอดคล้อง → ไม่ flag (status={out_ok['reconcile_status']})",
)

b_bad = {
    "subtotal": 9345794.39,
    "vat": 654205.61,
    "total": 10266200,
    "items": [{"amount": 9345794.39}],
}
out_bad = I.ingest_bill(b_bad)
check(
    out_bad["needs_human_review"] is True and "reconcile" in out_bad["reason"],
    f"บิลยอดเกิน → needs_human_review + reason ('{out_bad['reason'][:40]}')",
)
check(
    "ลืมเลขลำดับ" not in out_bad["reason"],
    "ไม่ออก finding 'ลืมเลขลำดับ' กับยอดที่ไม่ reconcile",
)

print("\n[6] TEMPLATE_REGISTRY seed (4 template)")
check(set(I.TEMPLATE_REGISTRY) == {"TKH", "SEI", "TOR", "SBT"}, "มี seed 4 template")
check(I.TEMPLATE_REGISTRY["TOR"]["seq"] is None, "TOR ไม่มีคอลัมน์เลขลำดับ (seq=None)")
check(
    I.TEMPLATE_REGISTRY["SBT"]["vat_kind"] == "percent_int", "SBT VAT = percent_int (7)"
)

print("\n" + "=" * 64)
print(f"PUOPUY INGEST: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ adapter layer ทำงานครบ — golden ไม่ขยับ (module ใหม่ ไม่แตะ engine)")
sys.exit(0)
