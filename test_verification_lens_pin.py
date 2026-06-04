# -*- coding: utf-8 -*-
"""test_verification_lens_pin.py — ตรึง (pin) ผลของ "คลังเลนส์ 30 ผู้ตรวจ"

ช่องโหว่ที่อุด: golden_master ตรึงเฉพาะผลตรวจหลัก ไม่ครอบ findings (votes/verdict) ของ agent.
ไฟล์นี้ = regression ของชั้น advisory: ตรึง roster + votes/score/verdict ต่อบิลออกแบบ.

บิลออกแบบครอบเลนส์สำคัญ:
  A=VAT001 จริง · C/C2=TAX001(ไม่มีเลข) · B/B2=ITM004 heuristic
  D=VAT002 7%เป๊ะ(FP) · E=VAT003 gap0.30(FP) · F=TAX006 checksumผิด · G=TAX001 เลขถูก+ข้ามบริษัท+ซ้ำ
  H/I=เลขภาษีเดียวกันต่างบริษัท+ยอดซ้ำ · J=ยอดติดลบ
★ เพิ่ม/ลบผู้ตรวจ: รันไฟล์นี้ดู diff → ตรวจว่าเปลี่ยน "เฉพาะที่ควร" → อัปเดต EXPECT/ROSTER + บันทึกเหตุผล

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_verification_lens_pin.py
"""

import os, sys, io, copy, datetime, contextlib, warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
from agents.contracts import PipelineContext
from agents.verification_agent import VerificationAgent, INSPECTION_LENSES, lens_roster

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def iss(c, s, n):
    return {"code": c, "severity": s, "category": "t", "name": n, "detail": ""}


P = {"subtotal": "parsed", "vat": "parsed", "total": "parsed"}
DV = {"subtotal": "derived", "vat": "derived", "total": "derived"}
DT = datetime.datetime(2025, 1, 15)


def mk(
    f, sh, iv, sub, vat, tot, src, pc, items, issues, tax=None, comp=None, date=None
):
    b = {
        "file": f,
        "sheet": sh,
        "iv_number": iv,
        "subtotal": sub,
        "vat": vat,
        "total": tot,
        "amount_source": src,
        "parse_confidence": pc,
        "items": items,
        "issues": issues,
    }
    if tax is not None:
        b["tax_id"] = tax
    if comp is not None:
        b["company"] = comp
    if date is not None:
        b["iv_date"] = date
    return b


bills = [
    mk(
        "F1.xlsx",
        "1",
        "IVA",
        1000.0,
        70.0,
        1070.0,
        P,
        "HIGH",
        [{"qty": 5.0, "price": 100.0, "amount": 500.0}],
        [iss("VAT001", "CRITICAL", "Sum=PreVAT")],
    ),
    mk(
        "F1.xlsx",
        "2",
        "IVC",
        1000.0,
        70.0,
        1070.0,
        P,
        "MID",
        [{"qty": 10.0, "price": 100.0, "amount": 1000.0}],
        [iss("TAX001", "CRITICAL", "เลขภาษี 13 หลัก")],
    ),
    mk(
        "F1.xlsx",
        "3",
        "IVC2",
        1000.0,
        70.0,
        1070.0,
        P,
        "MID",
        [{"qty": 10.0, "price": 100.0, "amount": 1000.0}],
        [iss("TAX001", "CRITICAL", "เลขภาษี 13 หลัก")],
    ),
    mk(
        "F2.xlsx",
        "1",
        "IVB",
        1000.0,
        70.0,
        1070.0,
        DV,
        "LOW",
        [{"name": "เหล้กเส้น", "qty": 10.0, "price": 100.0, "amount": 1000.0}],
        [iss("ITM004", "INFO", "คำสะกด")],
    ),
    mk(
        "F2.xlsx",
        "2",
        "IVB2",
        1000.0,
        70.0,
        1070.0,
        DV,
        "LOW",
        [{"name": "เหล้กเส้น", "qty": 10.0, "price": 100.0, "amount": 1000.0}],
        [iss("ITM004", "INFO", "คำสะกด")],
    ),
    mk(
        "F3.xlsx",
        "1",
        "IVD",
        1000.0,
        70.0,
        1070.0,
        P,
        "HIGH",
        [{"qty": 1.0, "price": 1000.0, "amount": 1000.0}],
        [iss("VAT002", "ERROR", "VAT ไม่ตรง 7%")],
        comp="ก",
        date=DT,
    ),
    mk(
        "F4.xlsx",
        "1",
        "IVE",
        1000.0,
        70.0,
        1070.30,
        P,
        "MID",
        [{"qty": 1.0, "price": 1000.0, "amount": 1000.0}],
        [iss("VAT003", "ERROR", "sub+vat≠total")],
        comp="ข",
        date=DT,
    ),
    mk(
        "F5.xlsx",
        "1",
        "IVF",
        1000.0,
        70.0,
        1070.0,
        P,
        "HIGH",
        [{"qty": 1.0, "price": 1000.0, "amount": 1000.0}],
        [iss("TAX006", "ERROR", "checksum mod11")],
        tax="1111111111111",
        comp="ค",
        date=DT,
    ),
    mk(
        "F6.xlsx",
        "1",
        "IVG",
        1000.0,
        70.0,
        1070.0,
        P,
        "MID",
        [{"qty": 1.0, "price": 1000.0, "amount": 1000.0}],
        [iss("TAX001", "CRITICAL", "เลขภาษี 13 หลัก")],
        tax="0105000000012",
        comp="ง",
        date=DT,
    ),
    mk(
        "F7.xlsx",
        "1",
        "IVH",
        1000.0,
        70.0,
        1070.0,
        P,
        "HIGH",
        [{"qty": 1.0, "price": 1000.0, "amount": 1000.0}],
        [iss("TAX002", "CRITICAL", "เลขภาษีซ้ำ")],
        tax="0105000000012",
        comp="หจก หนึ่ง",
        date=DT,
    ),
    mk(
        "F7.xlsx",
        "2",
        "IVI",
        1000.0,
        70.0,
        1070.0,
        P,
        "HIGH",
        [{"qty": 1.0, "price": 1000.0, "amount": 1000.0}],
        [iss("TAX002", "CRITICAL", "เลขภาษีซ้ำ")],
        tax="0105000000012",
        comp="หจก สอง",
        date=DT,
    ),
    mk(
        "F8.xlsx",
        "1",
        "IVJ",
        -500.0,
        -35.0,
        -535.0,
        P,
        "HIGH",
        [{"qty": 1.0, "price": -500.0, "amount": -500.0}],
        [iss("ITM017", "ERROR", "ยอดติดลบ")],
        comp="จ",
        date=DT,
    ),
]
MASTER = {
    "ง": {"name": "บ.ง", "tax_id": "0105000000012", "branch": "สนญ", "iv_prefix": "IV"}
}

ROSTER_EXPECT = [
    {"id": "L1_recompute", "dimension": "arithmetic"},
    {"id": "L2_provenance", "dimension": "provenance"},
    {"id": "L3_confidence", "dimension": "parse_trust"},
    {"id": "L4_peer", "dimension": "peer_consistency"},
    {"id": "L5_ruleclass", "dimension": "rule_precision"},
    {"id": "L6_llm", "dimension": "language_model"},
    {"id": "L7_rounding", "dimension": "rounding_artifact"},
    {"id": "L8_vat_7pct", "dimension": "vat_7pct_exact"},
    {"id": "L11_amt_complete", "dimension": "amount_completeness"},
    {"id": "L12_money_triple", "dimension": "money_triple"},
    {"id": "L13_line_sum", "dimension": "line_sum_amount"},
    {"id": "L14_qty_price", "dimension": "line_qty_price"},
    {"id": "L15_negative", "dimension": "negative_sanity"},
    {"id": "L16_magnitude", "dimension": "magnitude_outlier"},
    {"id": "L9_taxid_sum", "dimension": "taxid_checksum"},
    {"id": "L10_taxid_fmt", "dimension": "taxid_format"},
    {"id": "L17_taxid_xco", "dimension": "taxid_crosscompany"},
    {"id": "L18_dup_sig", "dimension": "duplicate_signature"},
    {"id": "L19_period", "dimension": "period_match"},
    {"id": "L20_doc_complete", "dimension": "doc_completeness"},
    {"id": "L21_master", "dimension": "master_known"},
    {"id": "L22_iv_prefix", "dimension": "iv_prefix_match"},
    {"id": "L23_vat_zero", "dimension": "vat_zero_exempt"},
    {"id": "L24_item_count", "dimension": "item_count_sanity"},
    {"id": "L25_line_neg", "dimension": "line_amount_negative"},
    {"id": "L26_dup_line", "dimension": "duplicate_line_in_bill"},
    {"id": "L27_co_xtaxid", "dimension": "company_multi_taxid"},
    {"id": "L28_total_lt_sub", "dimension": "total_lt_subtotal"},
    {"id": "L29_dec_scale", "dimension": "decimal_scale_error"},
    {"id": "L30_vat_nobase", "dimension": "vat_present_no_base"},
]
_KEYS = [r["id"] for r in ROSTER_EXPECT]


def V(**nz):
    d = {k: 0 for k in _KEYS}
    d.update(nz)
    return d


EXPECT = {
    "IVA": (
        "CONFIRMED",
        5,
        V(
            L1_recompute=1,
            L2_provenance=1,
            L3_confidence=1,
            L4_peer=1,
            L5_ruleclass=1,
            L12_money_triple=-1,
            L13_line_sum=1,
            L14_qty_price=1,
            L20_doc_complete=-1,
        ),
    ),
    "IVC": ("NEEDS_REVIEW", 0, V(L5_ruleclass=1, L20_doc_complete=-1)),
    "IVC2": ("NEEDS_REVIEW", 0, V(L5_ruleclass=1, L20_doc_complete=-1)),
    "IVB": (
        "LIKELY_FALSE_POSITIVE",
        -3,
        V(L3_confidence=-1, L5_ruleclass=-1, L20_doc_complete=-1),
    ),
    "IVB2": (
        "LIKELY_FALSE_POSITIVE",
        -3,
        V(L3_confidence=-1, L5_ruleclass=-1, L20_doc_complete=-1),
    ),
    "IVD": (
        "LIKELY_FALSE_POSITIVE",
        -2,
        V(
            L1_recompute=-1,
            L2_provenance=1,
            L3_confidence=1,
            L5_ruleclass=1,
            L8_vat_7pct=-1,
            L12_money_triple=-1,
            L13_line_sum=-1,
            L14_qty_price=-1,
        ),
    ),
    "IVE": (
        "LIKELY_FALSE_POSITIVE",
        -2,
        V(
            L1_recompute=-1,
            L2_provenance=1,
            L5_ruleclass=1,
            L7_rounding=-1,
            L13_line_sum=-1,
            L14_qty_price=-1,
        ),
    ),
    "IVF": ("NEEDS_REVIEW", 1, V(L3_confidence=1, L9_taxid_sum=1, L10_taxid_fmt=-1)),
    "IVG": (
        "NEEDS_REVIEW",
        0,
        V(
            L5_ruleclass=1,
            L9_taxid_sum=-1,
            L10_taxid_fmt=-1,
            L17_taxid_xco=1,
            L18_dup_sig=1,
            L21_master=-1,
        ),
    ),
    "IVH": (
        "NEEDS_REVIEW",
        1,
        V(
            L3_confidence=1,
            L5_ruleclass=1,
            L9_taxid_sum=-1,
            L10_taxid_fmt=-1,
            L17_taxid_xco=1,
            L18_dup_sig=1,
            L21_master=-1,
        ),
    ),
    "IVI": (
        "NEEDS_REVIEW",
        1,
        V(
            L3_confidence=1,
            L5_ruleclass=1,
            L9_taxid_sum=-1,
            L10_taxid_fmt=-1,
            L17_taxid_xco=1,
            L18_dup_sig=1,
            L21_master=-1,
        ),
    ),
    "IVJ": (
        "CONFIRMED",
        3,
        V(
            L1_recompute=1,
            L2_provenance=1,
            L3_confidence=1,
            L5_ruleclass=1,
            L12_money_triple=-1,
            L13_line_sum=-1,
            L14_qty_price=-1,
            L15_negative=1,
            L25_line_neg=1,  # v9.2: รายการ amount ติดลบ → corroborate (score 2→3, ยัง CONFIRMED)
        ),
    ),
}

print("=" * 64)
print("VERIFICATION LENS PIN — ตรึงคลังเลนส์ 30 ผู้ตรวจ")
print("=" * 64)
before = copy.deepcopy([b["issues"] for b in bills])
ctx = PipelineContext(
    bills=bills,
    master=MASTER,
    options={"verify_severities": ("CRITICAL", "ERROR", "WARNING", "INFO")},
)
with contextlib.redirect_stdout(io.StringIO()):
    res = VerificationAgent().run(ctx)

print(f"\n[1] roster = {len(INSPECTION_LENSES)} ผู้ตรวจ ตามที่ตรึง")
check(
    lens_roster() == ROSTER_EXPECT,
    "roster ตรง (ต่าง = เพิ่ม/ลบเลนส์ → อัปเดต EXPECT/ROSTER)",
)

print("\n[2] votes/score/verdict ต่อบิล ตรงกับที่ตรึง")
by_iv = {f.iv: f for f in res.findings}
for iv, (vd, sc, vv) in EXPECT.items():
    f = by_iv.get(iv)
    ok = (
        f is not None
        and f.evidence.get("verdict") == vd
        and f.evidence.get("score") == sc
        and f.evidence.get("votes") == vv
    )
    msg = f"{iv}: {vd} (score {sc:+d})"
    if not ok and f is not None:
        gv = f.evidence.get("votes", {})
        diff = {k: gv.get(k) for k in vv if vv.get(k) != gv.get(k)}
        msg += f"  [ได้ score {f.evidence.get('score')}, verdict {f.evidence.get('verdict')}, diff {diff}]"
    check(ok, msg)

print("\n[3] ADVISORY — b['issues'] ไม่เปลี่ยนหลังรัน")
check([b["issues"] for b in bills] == before, "issues ทุกบิลเหมือนเดิมเป๊ะ")

print("\n" + "=" * 64)
print(f"LENS PIN: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ คลังเลนส์ 30 ผู้ตรวจตรึงครบ + advisory")
sys.exit(0)
