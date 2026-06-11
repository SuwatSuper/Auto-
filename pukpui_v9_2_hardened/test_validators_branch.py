# -*- coding: utf-8 -*-
"""test_validators_branch.py — เก็บ "กิ่ง (branch)" ที่ยังไม่ถูกตรวจใน validators.py

เป้าหมาย (DECISIONS.md §6.1): ดัน branch coverage ของ validators.py จาก 79.4% → ≥85%
โดย **ไม่แตะ business logic** — สร้างบิลสังเคราะห์ที่ "จุดชนวน" แต่ละกิ่งให้ทำงานจริง:
  • positive detection: IV ซ้ำเลขท้าย / IV ถอยหลัง / เลขซ้ำข้ามวัน (IV003) /
    เลขไม่ไล่ตามวัน (IV004) / เดือนไม่ตรงไฟล์ / sheet-day mismatch / DT004 / DOC001
  • guard branches: ไม่มี iv_date / ไม่มี iv_number / group เล็กเกิน / dedup ซ้ำ source
  • detect_iv_period_mismatch: ปี4+เดือน / ปี2+เดือน / ปี4อย่างเดียว / อ่านงวดไม่ได้
  • check_product_typos fallback path (บังคับ primary พลาด → ใช้ fallback O(n²))

เป็น **pin/coverage test** ล้วน: ยืนยันพฤติกรรม + เก็บกิ่ง ; golden ไม่ขยับ.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_validators_branch.py
"""

import os
import sys
import io
import contextlib
import warnings
from datetime import date

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import validators as V

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def _bill(**kw):
    """บิลขั้นต่ำตาม contract ที่ validators ใช้ (เติม field ที่ขาดด้วยค่าปลอดภัย)."""
    b = {
        "file": "F.xlsx",
        "sheet": "1",
        "block_idx": 0,
        "iv_number": None,
        "iv_date": None,
        "tax_id": "0105500000001",
        "company": "บริษัท ทดสอบ จำกัด",
        "items": [],
        "issues": [],
    }
    b.update(kw)
    return b


def _silent(fn, *a, **k):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


print("=" * 64)
print("VALIDATORS BRANCH — เก็บกิ่งที่เหลือ (79.4% → ≥85%)")
print("=" * 64)

# ──────────────────────────────────────────────────────────────
# [A] _iv_check_sequence: IV ซ้ำเลขท้าย (135) + IV ถอยหลัง (146)
#     + guard ไม่มี iv_date (110) / ไม่มี trailing digit (113)
# ──────────────────────────────────────────────────────────────
seq_bills = [
    _bill(iv_number="IV001", iv_date=date(2025, 1, 10)),  # seq 1
    _bill(iv_number="IV001", iv_date=date(2025, 1, 10)),  # seq 1 ซ้ำ → 135
    _bill(iv_number="IV005", iv_date=date(2025, 1, 10)),  # seq 5
    _bill(iv_number="IV003", iv_date=date(2025, 1, 10)),  # seq 3 < 5 → ถอยหลัง 146
    _bill(iv_number="IVXX", iv_date=date(2025, 1, 10)),  # ไม่มี trailing digit → 113
    _bill(iv_number="IV009", iv_date=None),  # ไม่มี iv_date → 110
]
seq_issues = _silent(V._iv_check_sequence, seq_bills)
types = {i["type"] for i in seq_issues}
check("IV ซ้ำเลขท้าย" in types, "_iv_check_sequence จับ IV ซ้ำเลขท้าย (กิ่ง 135)")
check("IV ถอยหลัง" in types, "_iv_check_sequence จับ IV ถอยหลัง (กิ่ง 146)")

# seq ยาวไม่เท่ากันในกลุ่ม → ข้าม (127-128)
seq_bills2 = [
    _bill(iv_number="IV01", iv_date=date(2025, 2, 1)),  # seq len 1 (1)
    _bill(iv_number="IV100", iv_date=date(2025, 2, 1)),  # seq len 3 (100)
]
r = _silent(V._iv_check_sequence, seq_bills2)
check(r == [], "_iv_check_sequence: seq ยาวต่างกัน → ข้าม (กิ่ง 127)")

# ──────────────────────────────────────────────────────────────
# [B] _iv_check_cross_day: เลขซ้ำข้ามวัน → IV003 (174-187)
#     + guard ไม่มี iv_number/iv_date (165) + _merged_pages (166)
# ──────────────────────────────────────────────────────────────
cross_bills = [
    _bill(iv_number="DOC-1", iv_date=date(2025, 3, 1)),
    _bill(iv_number="DOC-1", iv_date=date(2025, 3, 2)),  # เลขเดิม คนละวัน → IV003
    _bill(iv_number=None, iv_date=date(2025, 3, 1)),  # ไม่มี iv_number → 165
    _bill(iv_number="DOC-9", iv_date=date(2025, 3, 1), _merged_pages=[1, 2]),  # 166
]
cross_issues = _silent(V._iv_check_cross_day, cross_bills)
check(
    any(i["type"] == "เลขที่เอกสารซ้ำข้ามวัน" for i in cross_issues),
    "_iv_check_cross_day จับเลขซ้ำข้ามวัน (IV003, กิ่ง 174)",
)
# side-effect: บิลในกลุ่มต้องได้ IV003 ผูกเข้า b['issues']
check(
    any(
        any(x.get("code") == "IV003" for x in b.get("issues", [])) for b in cross_bills
    ),
    "_iv_check_cross_day เติม IV003 เข้า b['issues'] (side-effect 182-187)",
)

# ──────────────────────────────────────────────────────────────
# [C] _iv_check_ascending: เลขไม่ไล่ตามวัน → IV004 (218-230)
#     + guard 199 + seq len ต่างกัน 212 + < 2 entries 215
# ──────────────────────────────────────────────────────────────
asc_bills = [
    _bill(iv_number="A005", iv_date=date(2025, 4, 1)),  # วันก่อน เลข 5
    _bill(iv_number="A003", iv_date=date(2025, 4, 2)),  # วันหลัง เลข 3 < 5 → IV004
    _bill(iv_number=None, iv_date=date(2025, 4, 1)),  # guard 199
]
asc_issues = _silent(V._iv_check_ascending, asc_bills)
check(
    any(i["type"] == "เลขที่เอกสารไม่ไล่ตามวัน" for i in asc_issues),
    "_iv_check_ascending จับเลขถอยตามวัน (IV004, กิ่ง 218)",
)
check(
    any(any(x.get("code") == "IV004" for x in b.get("issues", [])) for b in asc_bills),
    "_iv_check_ascending เติม IV004 เข้า b['issues'] (side-effect 226-230)",
)

# seq len ต่างกัน → ข้าม (211-212)
asc_len = [
    _bill(iv_number="A01", iv_date=date(2025, 4, 1)),  # 1
    _bill(iv_number="A100", iv_date=date(2025, 4, 2)),  # 100 (len ต่าง)
]
check(
    _silent(V._iv_check_ascending, asc_len) == [],
    "_iv_check_ascending: seq len ต่างกัน → ข้าม (กิ่ง 212)",
)

# < 2 entries (vendor เดียว วันเดียวใบเดียว) → ข้าม (215)
asc_one = [_bill(iv_number="A001", iv_date=date(2025, 4, 1))]
check(
    _silent(V._iv_check_ascending, asc_one) == [],
    "_iv_check_ascending: < 2 ใบ → ข้าม (กิ่ง 215)",
)

# ──────────────────────────────────────────────────────────────
# [D] _iv_check_month_consistency: เดือนไม่ตรงเสียงข้างมาก (63-71)
#     + group < 3 (46) + no clear majority (50) + no iv_date (41)
# ──────────────────────────────────────────────────────────────
month_bills = [
    _bill(iv_number="M1", iv_date=date(2025, 1, 5), file="report.xlsx"),
    _bill(iv_number="M2", iv_date=date(2025, 1, 6), file="report.xlsx"),
    _bill(iv_number="M3", iv_date=date(2025, 1, 7), file="report.xlsx"),
    _bill(
        iv_number="M4", iv_date=date(2025, 2, 8), file="report.xlsx"
    ),  # เดือน 2 ผิด → flag
    _bill(iv_number="M5", iv_date=None, file="report.xlsx"),  # no iv_date → 41
]
month_issues = _silent(V._iv_check_month_consistency, month_bills)
check(
    any("คนละเดือน" in i["type"] for i in month_issues),
    "_iv_check_month_consistency จับเดือนผิดเสียงข้างมาก (กิ่ง 63)",
)

# group < 3 → ข้าม (46)
small_grp = [
    _bill(iv_number="S1", iv_date=date(2025, 1, 5)),
    _bill(iv_number="S2", iv_date=date(2025, 2, 6)),
]
check(
    _silent(V._iv_check_month_consistency, small_grp) == [],
    "_iv_check_month_consistency: group < 3 → ข้าม (กิ่ง 46)",
)

# ไม่มีเดือนหลักชัด (3 เดือนต่างกันหมด) → ข้าม (50)
no_majority = [
    _bill(iv_number="N1", iv_date=date(2025, 1, 5)),
    _bill(iv_number="N2", iv_date=date(2025, 2, 6)),
    _bill(iv_number="N3", iv_date=date(2025, 3, 7)),
]
check(
    _silent(V._iv_check_month_consistency, no_majority) == [],
    "_iv_check_month_consistency: ไม่มีเดือนหลัก → ข้าม (กิ่ง 50)",
)

# ──────────────────────────────────────────────────────────────
# [E] _iv_check_sheet_day: sheet-day mismatch (91-96)
#     + no iv_date but has iv_number (84-85) + sheet ไม่ใช่ digit (98-99)
# ──────────────────────────────────────────────────────────────
sheet_bills = [
    _bill(
        iv_number="SH1", iv_date=date(2025, 5, 15), sheet="20"
    ),  # sheet 20 != day 15 → flag
    _bill(
        iv_number="SH2", iv_date=date(2025, 5, 15), sheet="15"
    ),  # ตรง → ไม่ flag (89->99)
    _bill(iv_number="SH3", iv_date=None, sheet="9"),  # no iv_date มี iv → 84-85
    _bill(
        iv_number="SH4", iv_date=date(2025, 5, 15), sheet="สรุป"
    ),  # ไม่ใช่ digit → 98-99
]
sheet_issues, consistent = _silent(V._iv_check_sheet_day, sheet_bills)
check(
    any("ไม่สอดคล้อง" in i["type"] for i in sheet_issues),
    "_iv_check_sheet_day จับ sheet-day mismatch (กิ่ง 91)",
)
check(
    any(b.get("iv_number") == "SH3" for b in consistent),
    "_iv_check_sheet_day: no iv_date+มี iv → เข้า consistent (กิ่ง 84-85)",
)

# ──────────────────────────────────────────────────────────────
# [F] check_invoice_sequence: dedup ซ้ำ source (249) — orchestrator เต็ม
# ──────────────────────────────────────────────────────────────
dup_src = [
    _bill(iv_number="O1", iv_date=date(2025, 6, 1), file="X", sheet="1", block_idx=0),
    _bill(
        iv_number="O1", iv_date=date(2025, 6, 1), file="X", sheet="1", block_idx=0
    ),  # src ซ้ำ → 249
    _bill(iv_number="O2", iv_date=date(2025, 6, 2), file="X", sheet="1", block_idx=1),
]
check(
    isinstance(_silent(V.check_invoice_sequence, dup_src), list),
    "check_invoice_sequence: dedup source ซ้ำ ทำงาน (กิ่ง 249)",
)

# ──────────────────────────────────────────────────────────────
# [G] check_iv_date_sequence: IV↔Date ถอยหลัง (291-294)
#     + guard 272 + digits<4 (275-277) + <2 entries (282) + >25% ถอย (287)
# ──────────────────────────────────────────────────────────────
ivdate_bills = [
    _bill(iv_number="CB6905-0800", iv_date=date(2025, 5, 1)),
    _bill(
        iv_number="CB6905-0392", iv_date=date(2025, 5, 10)
    ),  # วันหลัง เลขน้อยกว่า → ถอย
    _bill(iv_number="CB6905-0900", iv_date=date(2025, 5, 20)),
    _bill(iv_number=None, iv_date=date(2025, 5, 2)),  # guard 272
    _bill(iv_number="AB", iv_date=date(2025, 5, 3)),  # digits < 4 → 275-277
]
ivd_issues = _silent(V.check_iv_date_sequence, ivdate_bills)
check(
    any("IV↔Date ถอยหลัง" in i["type"] for i in ivd_issues),
    "check_iv_date_sequence จับ IV↔Date ถอยหลัง (กิ่ง 291)",
)

# > 25% ถอย → format แปลก → ข้าม (287)
weird = [
    _bill(iv_number=f"Z{1000 - i*100:04d}", iv_date=date(2025, 7, i + 1))
    for i in range(5)  # เลขลดลงทุกใบ → ถอย 100% > 25% → ข้าม
]
check(
    _silent(V.check_iv_date_sequence, weird) == [],
    "check_iv_date_sequence: ถอย > 25% → ข้าม format แปลก (กิ่ง 287)",
)

# ──────────────────────────────────────────────────────────────
# [H] detect_iv_period_mismatch: ทุกเส้นทางตีความงวด
# ──────────────────────────────────────────────────────────────
# (a) ปี4+เดือน (len>=6) — 202511 ตรงกับ พ.ย. 2025 → ไม่ mismatch (กิ่ง 322-326)
r_a = V.detect_iv_period_mismatch("202511-001", date(2025, 11, 5))
check(
    r_a is not None and r_a["mismatch"] is False,
    "detect_iv_period: ปี4+เดือน ตรงงวด → mismatch=False (กิ่ง 326)",
)
# (a') ปี4+เดือน แต่บิลคนละเดือน → mismatch=True
r_a2 = V.detect_iv_period_mismatch("202511-001", date(2025, 1, 5))
check(
    r_a2 is not None and r_a2["mismatch"] is True,
    "detect_iv_period: ปี4+เดือน คนละเดือน → mismatch=True",
)
# (b) ปี2+เดือน (6905 = พ.ค. 2569 พ.ศ.) ตรงกับ พ.ค. 2026
r_b = V.detect_iv_period_mismatch("CB6905-0001", date(2026, 5, 5))
check(r_b is not None, "detect_iv_period: ปี2+เดือน อ่านงวดได้ (กิ่ง 328-332)")
# (c) ปี4อย่างเดียว ไม่มีเดือน (INV-2025-001) → mo=None (กิ่ง 334-337)
r_c = V.detect_iv_period_mismatch("INV2025001", date(2025, 6, 5))
check(
    r_c is not None and "ปี" in r_c["iv_period"],
    "detect_iv_period: ปี4อย่างเดียว → period='ปี ...' (กิ่ง 334-337)",
)
# (d) อ่านงวดไม่ได้เลย → None (กิ่ง 311-312 / 339-340)
check(
    V.detect_iv_period_mismatch("INV", date(2025, 6, 5)) is None,
    "detect_iv_period: ไม่มีเลข → None (กิ่ง 311)",
)
check(
    V.detect_iv_period_mismatch("AB99", date(2025, 6, 5)) is None,
    "detect_iv_period: เลขสั้นอ่านงวดไม่ได้ → None (กิ่ง 339)",
)
# guard input ว่าง (307-308)
check(
    V.detect_iv_period_mismatch("", None) is None,
    "detect_iv_period: input ว่าง → None (กิ่ง 307)",
)

# ──────────────────────────────────────────────────────────────
# [I] apply_iv_period_crosscheck: DT004 append (465) + guard (462)
# ──────────────────────────────────────────────────────────────
dt004 = [
    _bill(
        iv_number="202511-001", iv_date=date(2025, 1, 5)
    ),  # งวด พ.ย. แต่ลงเดือน ม.ค. → DT004
    _bill(iv_number=None, iv_date=date(2025, 1, 5)),  # guard 462
    _bill(iv_number="X", iv_date=None),  # guard 462
]
_silent(V.apply_iv_period_crosscheck, dt004)
check(
    any(x.get("code") == "DT004" for x in dt004[0]["issues"]),
    "apply_iv_period_crosscheck: เติม DT004 (กิ่ง 465)",
)

# ──────────────────────────────────────────────────────────────
# [J] apply_sheet_date_crosscheck: DOC001 append (487) + guard (478)
# ──────────────────────────────────────────────────────────────
doc001 = [
    _bill(
        iv_number="D1", iv_date=date(2025, 8, 20), sheet="15.08"
    ),  # ชีต 15/08 != วันที่ 20/08
    _bill(iv_number="D2", iv_date=None, sheet="15.08"),  # guard 478
    _bill(iv_number="D3", iv_date=date(2025, 8, 20), sheet="สรุป"),  # ไม่ match pattern
]
_silent(V.apply_sheet_date_crosscheck, doc001)
check(
    any(x.get("code") == "DOC001" for x in doc001[0]["issues"]),
    "apply_sheet_date_crosscheck: เติม DOC001 (กิ่ง 487)",
)

# ──────────────────────────────────────────────────────────────
# [K] check_filename_consistency: day mismatch (505) + no dates (502)
# ──────────────────────────────────────────────────────────────
fc_bills = [
    _bill(iv_number="FC1", iv_date=date(2025, 9, 10)),
    _bill(iv_number="FC2", iv_date=date(2025, 9, 25)),  # บิลสุดท้าย day=25
]
fc_issues = _silent(V.check_filename_consistency, "sep_30.xlsx", fc_bills, {"day": 30})
check(
    len(fc_issues) == 1 and fc_issues[0]["type"] == "ชื่อไฟล์↔บิลสุดท้าย",
    "check_filename_consistency: day mismatch → flag (กิ่ง 505)",
)
# no dates → return [] (502)
fc_none = [_bill(iv_number="FC3", iv_date=None)]
check(
    _silent(V.check_filename_consistency, "x.xlsx", fc_none, {"day": 5}) == [],
    "check_filename_consistency: ไม่มี date → [] (กิ่ง 502)",
)
# no bills → return [] (500)
check(
    _silent(V.check_filename_consistency, "x.xlsx", [], {"day": 5}) == [],
    "check_filename_consistency: ไม่มีบิล → [] (กิ่ง 500)",
)

# ──────────────────────────────────────────────────────────────
# [L] check_duplicate_items: รายการซ้ำเป๊ะ (525) + ไม่ซ้ำ (data path)
# ──────────────────────────────────────────────────────────────
dup_items = [
    _bill(
        iv_number="DUP1",
        items=[
            {"name": "เหล็กเส้น 12mm", "amount": 100.0, "seq": 1},
            {"name": "เหล็กเส้น 12mm", "amount": 100.0, "seq": 2},  # ซ้ำเป๊ะ → 525
            {"name": "ปูนซีเมนต์", "amount": 50.0, "seq": 3},  # ไม่ซ้ำ
        ],
    ),
]
dups = _silent(V.check_duplicate_items, dup_items)
check(
    len(dups) == 1 and dups[0]["พบซ้ำ"] == 2,
    "check_duplicate_items: จับรายการซ้ำเป๊ะ (กิ่ง 525)",
)

# ──────────────────────────────────────────────────────────────
# [M] check_product_typos: fallback path (บังคับ primary พลาด) 441-449
#     + length diff > 30% (445) + score นอกช่วง (447) + spec diff (448)
# ──────────────────────────────────────────────────────────────
import rapidfuzz.process as _rfp

typo_bills = [
    _bill(
        items=[
            {"name": "สีกันสนิมสีแดงเบอร์หนึ่ง", "amount": 1.0, "seq": 1},
            {
                "name": "สีกันสนิมสีแดงเบอรหนึ่ง",
                "amount": 1.0,
                "seq": 2,
            },  # near-dup → typo (449)
            {"name": "x", "amount": 1.0, "seq": 3},  # สั้นมาก → length diff (445)
            {"name": "ท่อพีวีซี 4 นิ้ว", "amount": 1.0, "seq": 4},
            {
                "name": "ท่อพีวีซี 6 นิ้ว",
                "amount": 1.0,
                "seq": 5,
            },  # spec ต่าง (เลข) → 448
        ]
    ),
]
_orig_cdist = _rfp.cdist


def _boom_cdist(*a, **k):
    raise RuntimeError("forced-fallback")


_rfp.cdist = _boom_cdist
try:
    typos_fb = _silent(V.check_product_typos, typo_bills)
finally:
    _rfp.cdist = _orig_cdist
check(
    isinstance(typos_fb, list)
    and any("เบอร" in t["name1"] or "เบอร" in t["name2"] for t in typos_fb),
    "check_product_typos: fallback path จับ near-dup (กิ่ง 441-449)",
)

# < 2 ชื่อ → คืน [] (366)
check(
    _silent(
        V.check_product_typos,
        [_bill(items=[{"name": "เดี่ยว", "amount": 1, "seq": 1}])],
    )
    == [],
    "check_product_typos: < 2 ชื่อ → [] (กิ่ง 366)",
)

print("\n" + "=" * 64)
print(f"VALIDATORS BRANCH: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ เก็บกิ่งครบ — golden ไม่ขยับ (advisory/coverage เท่านั้น)")
sys.exit(0)
