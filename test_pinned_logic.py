# -*- coding: utf-8 -*-
"""test_pinned_logic.py — ตรึง (pin) พฤติกรรมของ 3 จุดที่กู้คืนแบบ ⚠ APPROX

ทำไม (P1): REBUILD_STATUS ระบุว่า 3 จุดนี้ "ต้นฉบับไม่ทราบค่า" จึงสร้างใหม่แบบโปร่งใส.
ปัญหา: ถ้าใครเผลอแก้ "น้ำหนัก/เกณฑ์/รูปแบบ" ภายหลัง → ผลเงียบๆ เพี้ยน โดยไม่มีเทสจับ.
เทสนี้ **ฝังค่าที่ตรวจวัดจริงไว้เป็น literal** (ไม่คำนวณซ้ำจากโมดูล) → ถ้าพฤติกรรมขยับ = ล้มทันที.

ครอบ 3 จุด APPROX:
  1) puopuy_units._vat_tolerance       — RESTORED 0.5 + |subtotal|/100000; None/abs/comma/ขยะ, บิลใหญ่, ชนิด Decimal
  2) analytics.compute_bill_confidence — น้ำหนักหักคะแนนแต่ละชนิด + clamp [0,1] + เส้น exception→LOW
  3) analytics.summarize_by_company    — รูปแบบ field period (พ.ศ. 2 หลัก.เดือน), เรียง/ไม่ซ้ำ/'-'/ยอดเป็นตัวเลข

ไม่ต้องใช้ข้อมูลจริง (เร็ว → ใส่ CI ได้):
    PYTHONHASHSEED=0 python3 test_pinned_logic.py
exit 0 = ตรึงผ่าน, 1 = พฤติกรรมขยับจากที่ตรึงไว้
"""
import os
import sys
import datetime as dt
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

import analytics
import puopuy_units as U
from config import CONF_TIERS

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def eq(label, got, want):
    check(got == want, f"{label}  (ได้ {got!r}, ตรึงไว้ {want!r})")


# ════════════════════════════════════════════════════════════════════════════
print("=" * 64)
print("PINNED LOGIC — ตรึงพฤติกรรม 3 จุด APPROX (กันการเพี้ยนเงียบ)")
print("=" * 64)

# ── 0) ค่าคงที่ที่ผูกกับนโยบาย (ถ้าขยับ ผลตรวจหน้าตา/logic เปลี่ยน) ──────────────
print("\n[0] ค่าคงที่ฐาน (CONF_TIERS)")
eq("CONF_TIERS.HIGH_MIN", CONF_TIERS["HIGH_MIN"], 0.9)
eq("CONF_TIERS.MID_MIN", CONF_TIERS["MID_MIN"], 0.7)

# ── 1) _vat_tolerance (RESTORED: 0.5 + |subtotal|/100000) ─────────────────────
#    [OBJ-1A · 2026-06] เปลี่ยนจากสูตร reconstructed max(1.00, 0.5%·sub) กลับเป็น
#    "สูตรเดิมที่มีหลักฐานว่าพิสูจน์แล้ว" อย่างตั้งใจ. ค่าด้านล่างคือค่าจริงของสูตรใหม่
#    (วัดจากโมดูล) — ถ้าใครแก้สูตรเงียบ ๆ ภายหลัง = เทสนี้ล้มทันที.
print("\n[1] _vat_tolerance — RESTORED 0.5 + |subtotal|/100000")
eq("None → ฐาน 0.5", U._vat_tolerance(None), Decimal("0.5"))
eq("10000 → 0.5 + 0.1 = 0.6", U._vat_tolerance(10000), Decimal("0.6"))
eq("100 → 0.5 + 0.001 = 0.501", U._vat_tolerance(100), Decimal("0.501"))
eq("200 → 0.5 + 0.002 = 0.502", U._vat_tolerance(200), Decimal("0.502"))
eq("200.01 → 0.5 + 0.0020001", U._vat_tolerance(Decimal("200.01")), Decimal("0.5020001"))
eq("ค่าติดลบ ใช้ abs (-2000 → 0.52)", U._vat_tolerance(-2000), Decimal("0.52"))
eq("สตริงมี comma '1,234.50' → 0.512345", U._vat_tolerance("1,234.50"), Decimal("0.512345"))
eq("ขยะ 'abc' → ฐาน 0.5", U._vat_tolerance("abc"), Decimal("0.5"))
eq("'0' → ฐาน 0.5", U._vat_tolerance("0"), Decimal("0.5"))
# บิลใหญ่: ยืนยันว่าสูตรใหม่เข้มกว่ามาก (สูตรเก่าจะปล่อยถึง ~7,651)
eq("subtotal 1,530,236 → 15.8023572", U._vat_tolerance(Decimal("1530235.72")), Decimal("15.8023572"))
check(isinstance(U._vat_tolerance(10000), Decimal), "คืนชนิด Decimal เสมอ (ไม่ใช่ float)")
# constants ของสูตรใหม่ (ถ้าแก้ ต้องตั้งใจ + อัป baseline ถ้าจำเป็น)
eq("_VAT_TOL_BASE", U._VAT_TOL_BASE, Decimal("0.5"))
eq("_VAT_TOL_DIVISOR", U._VAT_TOL_DIVISOR, Decimal("100000"))

# ── 2) compute_bill_confidence (น้ำหนักหักคะแนน + clamp + exception→LOW) ──────
print("\n[2] compute_bill_confidence — น้ำหนัก/คะแนน/tier ที่ตรึงไว้")

# น้ำหนักแต่ละชนิด (literal) — ถ้าใครแก้ค่าพวกนี้ จะถูกจับทันที
eq("_W_NO_TAXID", analytics._W_NO_TAXID, 0.15)
eq("_W_BAD_TAXID", analytics._W_BAD_TAXID, 0.10)
eq("_W_NO_IV", analytics._W_NO_IV, 0.15)
eq("_W_NO_DATE", analytics._W_NO_DATE, 0.10)
eq("_W_NO_ITEMS", analytics._W_NO_ITEMS, 0.20)
eq("_W_MISSING_AMT (ต่อช่อง)", analytics._W_MISSING_AMT, 0.08)
eq("_W_AMOUNT_LOW", analytics._W_AMOUNT_LOW, 0.15)
eq("_W_VAT_INCONSISTENT", analytics._W_VAT_INCONSISTENT, 0.10)

_CLEAN = dict(tax_id="0105000000012", iv_number="IV1", iv_date=dt.date(2025, 1, 1),
              items=[{"name": "x", "unit": "ชิ้น", "amount": 100}],
              subtotal=100.0, vat=7.0, total=107.0, amount_confidence="ok")


def score_of(overrides):
    b = dict(_CLEAN)
    b.update(overrides)
    analytics.compute_bill_confidence(b)
    return b["parse_confidence_score"], b["parse_confidence"], b["parse_confidence_reasons"]


s, t, r = score_of({})
check((s, t, r) == (1.0, "HIGH", []), f"บิลสะอาด → score 1.0 / HIGH / ไม่มีเหตุผล (ได้ {s}/{t}/{len(r)} เหตุผล)")

s, t, r = score_of(dict(tax_id="", iv_number="", iv_date=None, items=[],
                        subtotal=None, vat=None, total=None, amount_confidence=""))
check((s, t) == (0.16, "LOW") and len(r) == 5,
      f"บิลว่างเปล่า → 0.16 / LOW / 5 เหตุผล (ได้ {s}/{t}/{len(r)})")

s, t, r = score_of(dict(tax_id=""))
check((s, t) == (0.85, "MID"), f"ขาดเลขภาษีอย่างเดียว → 0.85 / MID (ได้ {s}/{t})")

s, t, r = score_of(dict(tax_id="0000000000000"))
check((s, t) == (0.9, "HIGH"), f"เลขภาษี checksum ไม่ผ่าน → 0.90 / HIGH (ได้ {s}/{t})")

s, t, r = score_of(dict(vat=None, total=None))
check((s, t) == (0.84, "MID"), f"ขาดยอด 2 ช่อง → 0.84 / MID (ได้ {s}/{t})")

s, t, r = score_of(dict(amount_confidence="LOW"))
check((s, t) == (0.85, "MID"), f"parser amount_confidence=LOW → 0.85 / MID (ได้ {s}/{t})")

s, t, r = score_of(dict(subtotal=100.0, vat=50.0, total=150.0))
check((s, t) == (0.9, "HIGH"), f"VAT ไม่ใกล้ 7% → 0.90 / HIGH (ได้ {s}/{t})")

# clamp ขอบล่าง: หักแทบทุกอย่าง → คะแนนต่ำสุด (โมเดลปัจจุบันหักได้ ≤ 0.99 → ต่ำสุด 0.01)
s, t, r = score_of(dict(tax_id="", iv_number="", iv_date=None, items=[],
                        subtotal=None, vat=None, total=None, amount_confidence="LOW"))
check(s == 0.01 and 0.0 <= s <= 1.0 and t == "LOW",
      f"หักเกือบทุกข้อ → 0.01 / LOW และอยู่ในช่วง [0,1] (ได้ {s}/{t})")

# เส้น exception → LOW (ปลอดภัยเสมอ ไม่ crash): ป้อน items เป็นชนิดที่ทำให้ภายในพัง
bad = {"items": 12345, "tax_id": 999}  # .get/iter ผิดชนิด → except → LOW
analytics.compute_bill_confidence(bad)
check(bad.get("parse_confidence") in ("HIGH", "MID", "LOW"),
      "อินพุตเพี้ยน → ไม่ throw (มี try ครอบ)")

# ── 3) summarize_by_company + _period_label (รูปแบบ period) ──────────────────
print("\n[3] _period_label + summarize_by_company — รูปแบบ period")
eq("_period_label(2025-11-05) = '68.11'", analytics._period_label(dt.date(2025, 11, 5)), "68.11")
eq("_period_label(2025-01-01) = '68.01'", analytics._period_label(dt.date(2025, 1, 1)), "68.01")
eq("_period_label(2025-02-28) = '68.02'", analytics._period_label(dt.date(2025, 2, 28)), "68.02")
eq("_period_label(None) = '-'", analytics._period_label(None), "-")

bills = [
    dict(master_key="ACME", iv_date=dt.date(2025, 1, 5), subtotal=100, vat=7, total=107),
    dict(master_key="ACME", iv_date=dt.date(2025, 2, 9), subtotal=None, vat=None, total=None),
    dict(master_key=None, iv_date=None, subtotal=50, vat=3.5, total=53.5),
]
out = analytics.summarize_by_company(bills)
by_key = {g["key"]: g for g in out}

check(set(by_key) == {"ACME", "(ไม่พบใน master)"},
      f"จัดกลุ่มด้วย master_key + บัคเก็ต fallback (ได้ {sorted(by_key)})")
g = by_key["ACME"]
eq("ACME.period (2 งวด เรียง+join ', ')", g["period"], "68.01, 68.02")
eq("ACME.bill_count", g["bill_count"], 2)
eq("ACME.subtotal (None→0, รวม)", g["subtotal"], 100.0)
eq("ACME.vat", g["vat"], 7.0)
eq("ACME.total", g["total"], 107.0)
check(isinstance(g["subtotal"], (int, float)) and not isinstance(g["subtotal"], bool),
      "subtotal เป็นตัวเลขเสมอ (ranking sort ด้วย -subtotal ได้)")
gf = by_key["(ไม่พบใน master)"]
eq("บิลไม่มีวันที่ → period '-'", gf["period"], "-")
eq("fallback key subtotal", gf["subtotal"], 50.0)

# ── 4) audit_today() — นาฬิกาที่ฉีดได้ (กันผลตรวจขยับตามเวลา / reproducible) ──
print("\n[4] audit_today — clock ที่ฉีดได้ (env PUOPUY_AUDIT_DATE)")
import os as _os
import datetime as _dt2
from config import audit_today
import rules_engine as _R

_old = _os.environ.get("PUOPUY_AUDIT_DATE")
try:
    _os.environ["PUOPUY_AUDIT_DATE"] = "2025-03-15"
    eq("pin → ใช้วันที่ที่กำหนด", audit_today(), _dt2.date(2025, 3, 15))
    _os.environ["PUOPUY_AUDIT_DATE"] = "ไม่ใช่วันที่"
    check(isinstance(audit_today(), _dt2.date), "pin รูปแบบผิด → fallback เวลาจริง (ไม่ crash)")

    # กฎ r_dt002 (future date) ต้อง 'นิ่ง' ตาม pin — พิสูจน์ว่า reproducible จริง
    _bill = {"iv_date": _dt2.datetime(2025, 6, 1)}
    _os.environ["PUOPUY_AUDIT_DATE"] = "2025-01-01"
    check(bool(_R.r_dt002(_bill, {}, {})), "r_dt002: pin ก่อนวันบิล → ฟ้อง future (deterministic)")
    _os.environ["PUOPUY_AUDIT_DATE"] = "2025-12-31"
    check(not _R.r_dt002(_bill, {}, {}), "r_dt002: pin หลังวันบิล → ไม่ฟ้อง (deterministic)")
finally:
    if _old is None:
        _os.environ.pop("PUOPUY_AUDIT_DATE", None)
    else:
        _os.environ["PUOPUY_AUDIT_DATE"] = _old

# ── สรุป ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"PINNED: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for f in FAIL:
        print(f"  ❌ {f}")
    print("\n⚠️ พฤติกรรมขยับจากที่ตรึงไว้. ถ้า 'ตั้งใจแก้' (เช่นเจอต้นฉบับ) ให้ปรับค่าที่ตรึง")
    print("   ในไฟล์นี้ + สร้าง baseline.json ใหม่ + รัน regression_full ยืนยัน.")
    sys.exit(1)
print("RESULT: ✅ ตรึงครบ — 3 จุด APPROX ยังให้ค่าตรงตามที่บันทึกไว้")
sys.exit(0)
