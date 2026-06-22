# -*- coding: utf-8 -*-
"""test_verification_agent.py — [feature] VerificationAgent (5 เลนส์ + consensus per-Error)

พิสูจน์:
  (1) consensus verdict ถูกต้องตามเคสที่ออกแบบ (CONFIRMED / NEEDS_REVIEW / LIKELY_FALSE_POSITIVE)
  (2) ADVISORY — รัน agent แล้ว b['issues'] ของทุกบิล "ไม่เปลี่ยน" (deep-equal ก่อน/หลัง)
  (3) ไม่ throw + คืน AgentResult OK + ออก finding VERIFY-* ครบ

ไม่ต้องใช้ข้อมูลจริง → เร็ว ใส่ CI ได้:
    PYTHONHASHSEED=0 python3 test_verification_agent.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import copy
import contextlib
import warnings

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')  # ให้ sys.path/โมดูลพร้อม

from agents.contracts import PipelineContext
from agents.verification_agent import VerificationAgent

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def issue(code, sev, name):
    return {"code": code, "severity": sev, "category": "test", "name": name, "detail": ""}


# ── บิลออกแบบให้ consensus ออกมาตามที่คาด ──
# A: CONFIRMED — VAT001 จริง (Σ500≠sub1000) + parsed + HIGH + โดดเดี่ยว + high-precision
billA = {
    "file": "F1.xlsx", "sheet": "1", "iv_number": "IVA",
    "subtotal": 1000.0, "vat": 70.0, "total": 1070.0,
    "amount_source": {"subtotal": "parsed", "vat": "parsed", "total": "parsed"},
    "parse_confidence": "HIGH",
    "items": [{"seq": 1, "name": "x", "qty": 5.0, "price": 100.0, "amount": 500.0}],
    "issues": [issue("VAT001", "CRITICAL", "Sum=PreVAT")],
}
# C: NEEDS_REVIEW — TAX001 + MID + โดดเดี่ยว + high-precision (L4+1, L5+1 = +2... ปรับ MID→0)
#    score = 0(L1)+0(L2)+0(L3 MID)+1(L4 โดดเดี่ยว)+1(L5 high) = +2 → CONFIRMED
#    เพื่อให้เป็น NEEDS_REVIEW ให้ใช้บิลที่ "พบทั่วไป" (L4=0) → score=+1
billC = {
    "file": "F1.xlsx", "sheet": "2", "iv_number": "IVC",
    "subtotal": 1000.0, "vat": 70.0, "total": 1070.0,
    "amount_source": {"subtotal": "parsed", "vat": "parsed", "total": "parsed"},
    "parse_confidence": "MID",
    "items": [{"seq": 1, "name": "x", "qty": 10.0, "price": 100.0, "amount": 1000.0}],
    "issues": [issue("TAX001", "CRITICAL", "เลขภาษี 13 หลัก")],
}
billC2 = {  # peer ของ C ที่มี TAX001 เหมือนกัน → ทำให้ L4(C)=0 (พบทั่วไป)
    "file": "F1.xlsx", "sheet": "3", "iv_number": "IVC2",
    "subtotal": 1000.0, "vat": 70.0, "total": 1070.0,
    "amount_source": {"subtotal": "parsed", "vat": "parsed", "total": "parsed"},
    "parse_confidence": "MID",
    "items": [{"seq": 1, "name": "x", "qty": 10.0, "price": 100.0, "amount": 1000.0}],
    "issues": [issue("TAX001", "CRITICAL", "เลขภาษี 13 หลัก")],
}
# B: LIKELY_FALSE_POSITIVE — ITM004 (typo heuristic) + LOW + พบทั่วไป
#    score = 0+0-1(L3 LOW)+0(L4 พบทั่วไป)-1(L5 heuristic) = -2 → FALSEPOS
billB = {
    "file": "F2.xlsx", "sheet": "1", "iv_number": "IVB",
    "subtotal": 1000.0, "vat": 70.0, "total": 1070.0,
    "amount_source": {"subtotal": "derived", "vat": "derived", "total": "derived"},
    "parse_confidence": "LOW",
    "items": [{"seq": 1, "name": "เหล้กเส้น", "qty": 10.0, "price": 100.0, "amount": 1000.0}],
    "issues": [issue("ITM004", "INFO", "คำสะกด pattern")],
}
billB2 = {  # peer ของ B ที่มี ITM004 เหมือนกัน → L4(B)=0
    "file": "F2.xlsx", "sheet": "2", "iv_number": "IVB2",
    "subtotal": 1000.0, "vat": 70.0, "total": 1070.0,
    "amount_source": {"subtotal": "derived", "vat": "derived", "total": "derived"},
    "parse_confidence": "LOW",
    "items": [{"seq": 1, "name": "เหล้กเส้น", "qty": 10.0, "price": 100.0, "amount": 1000.0}],
    "issues": [issue("ITM004", "INFO", "คำสะกด pattern")],
}

bills = [billA, billC, billC2, billB, billB2]

print("=" * 64)
print("VERIFICATION AGENT — 5 เลนส์ + consensus per-Error")
print("=" * 64)

# snapshot ของ issues ก่อนรัน (พิสูจน์ advisory)
before = copy.deepcopy([b["issues"] for b in bills])

ctx = PipelineContext(
    bills=bills,
    options={"verify_severities": ("CRITICAL", "ERROR", "WARNING", "INFO")},
)
agent = VerificationAgent()
with contextlib.redirect_stdout(io.StringIO()):
    res = agent.run(ctx)

print("\n[1] ไม่ throw + คืนผล OK")
check(res is not None and res.status == "ok", "VerificationAgent คืน status=ok")
check(len(res.findings) == 5, f"ออก finding ครบ 5 Error (ได้ {len(res.findings)})")

print("\n[2] consensus verdict ตรงตามที่ออกแบบ")
verdict_by_iv = {f.iv: f.evidence.get("verdict") for f in res.findings}
score_by_iv = {f.iv: f.evidence.get("score") for f in res.findings}
print("     verdicts:", verdict_by_iv)
print("     scores  :", score_by_iv)
check(verdict_by_iv.get("IVA") == "CONFIRMED", "A (VAT001 จริง+parsed+HIGH+โดดเดี่ยว) → CONFIRMED")
check(verdict_by_iv.get("IVC") == "NEEDS_REVIEW", "C (TAX001+MID+พบทั่วไป) → NEEDS_REVIEW")
check(verdict_by_iv.get("IVB") == "LIKELY_FALSE_POSITIVE",
      "B (ITM004 heuristic+LOW+derived) → LIKELY_FALSE_POSITIVE")

print("\n[3] ADVISORY — b['issues'] ไม่เปลี่ยนหลังรัน agent")
after = [b["issues"] for b in bills]
check(after == before, "issues ของทุกบิลเหมือนเดิมเป๊ะ (agent ไม่ mutate ผลหลัก)")

print("\n[4] summary metrics")
print("     ", res.summary)
check(res.summary.get("errors_verified") == 5, "นับ Error ที่ verify = 5")
check(res.summary.get("confirmed", 0) >= 1 and res.summary.get("likely_false_positive", 0) >= 1,
      "มีทั้ง confirmed และ likely-false-positive")

print("\n" + "=" * 64)
print(f"VERIFICATION: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for f in FAIL:
        print(f"  • {f}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ consensus per-Error ถูกต้อง + advisory (ไม่แตะผลหลัก)")
sys.exit(0)
