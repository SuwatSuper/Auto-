# -*- coding: utf-8 -*-
"""
puopuy_ingest.py — Adapter/Normalization Layer (v9.2, ADR-016) — DECISION GATE "ทาง A"

ชั้นคั่นระหว่าง raw parse กับ validation/aggregation — **module ใหม่ ไม่แตะ engine 4 ตัว**
(parser/rules_engine/validators/puopuy_units) → golden hash ของ engine คงเดิม.

ให้ "checksum ที่ใบกำกับมีอยู่แล้วแต่ระบบยังไม่ใช้":
  1) thai_words_to_number  — แปลง "ยอดตัวอักษรไทย" → ตัวเลข (redundant encoding ของยอดรวม)
  2) normalize_vat_rate    — รองรับ VAT ทั้ง 0.07 (สัดส่วน) และ 7 (เปอร์เซ็นต์เต็ม แบบ SBT)
  3) reconcile_totals      — เทียบ 3 ทาง: net(เลข)=words(สะกด) · grand=net+vat · subtotal=Σ line_item
  4) classify_row          — จำแนกแถว: line_item/subtotal/words_total/vat/grand_total/header/blank
  5) ingest_bill           — ห่อผล → ออก finding เดียว "ยอดไม่ reconcile" + ตั้ง needs_human_review

ปรัชญา: **fail loud** — ไม่มั่นใจ/อ่านไม่ออก → ตั้ง flag ให้คนตรวจ ไม่เดามั่ว. deterministic, offline.

หมายเหตุ: SEED template registry (จากหลักฐาน 773 sheets) เป็น "จุดตั้งต้น" — ต้อง validate กับ
ไฟล์จริง 81/103 ก่อนใช้ production (ดู TEMPLATE_REGISTRY ด้านล่าง).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional

# ── คำเลขไทย ────────────────────────────────────────────────────────────────
_TH_DIGIT = {
    "ศูนย์": 0,
    "หนึ่ง": 1,
    "เอ็ด": 1,
    "สอง": 2,
    "ยี่": 2,
    "สาม": 3,
    "สี่": 4,
    "ห้า": 5,
    "หก": 6,
    "เจ็ด": 7,
    "แปด": 8,
    "เก้า": 9,
}
_TH_PLACE = {"สิบ": 10, "ร้อย": 100, "พัน": 1000, "หมื่น": 10000, "แสน": 100000}
_TH_MILLION = "ล้าน"
# เรียงยาว→สั้น เพื่อ match longest-first (กัน 'สิบ' ชน 'สิบเอ็ด' ฯลฯ)
_TH_TOKENS = sorted(
    list(_TH_DIGIT) + list(_TH_PLACE) + [_TH_MILLION], key=len, reverse=True
)
_Q2 = Decimal("0.01")


def _tokenize_thai_num(s: str) -> Optional[List[str]]:
    """ตัดสตริงเลขไทย (ไม่มีช่องว่าง) เป็น token. เจออักขระแปลก → None (อ่านไม่ออก = fail loud)."""
    toks: List[str] = []
    i, n = 0, len(s)
    while i < n:
        for w in _TH_TOKENS:
            if s.startswith(w, i):
                toks.append(w)
                i += len(w)
                break
        else:
            return None  # มีอักขระที่ไม่ใช่คำเลขไทย → อ่านไม่ออก
    return toks


def _fold_thai_int(toks: List[str]) -> int:
    """รวม token (ไม่มีจุดทศนิยม) → จำนวนเต็ม. รองรับ สิบ..แสน + ล้าน (กลุ่มละ 10^6)."""
    result = 0
    group = 0
    digit = 0
    for t in toks:
        if t in _TH_DIGIT:
            digit = _TH_DIGIT[t]
        elif t in _TH_PLACE:
            group += (digit or 1) * _TH_PLACE[t]
            digit = 0
        elif t == _TH_MILLION:
            group += digit
            result = (result + group) * 1_000_000
            group = digit = 0
    return result + group + digit


def thai_words_to_number(text: str) -> Optional[Decimal]:
    """แปลง 'ยอดตัวอักษรไทย' → Decimal. คืน None ถ้าไม่ใช่/อ่านไม่ออก (fail loud, ไม่เดา).

    รองรับ: หลัก/สิบ/ร้อย/พัน/หมื่น/แสน/ล้าน, เอ็ด, ยี่สิบ, 'บาท…สตางค์', 'ถ้วน', วงเล็บ (…) แบบ TOR.
    """
    if not text:
        return None
    s = str(text).strip()
    s = re.sub(r"[()]", "", s)  # TOR: ตัดวงเล็บครอบ
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^(จำนวนเงิน|ตัวอักษร|รวมเงิน|รวมทั้งสิ้น)", "", s)
    if "บาท" not in s:
        return None  # ไม่มี 'บาท' = ไม่ใช่ยอดตัวอักษร
    baht_part, _, rest = s.partition("บาท")
    # สตางค์
    satang = 0
    if "ถ้วน" in rest:
        satang = 0
    elif "สตางค์" in rest:
        sat_words = rest.partition("สตางค์")[0]
        st = _tokenize_thai_num(sat_words)
        if st is None:
            return None
        satang = _fold_thai_int(st)
    if not baht_part:
        return None
    bt = _tokenize_thai_num(baht_part)
    if bt is None:
        return None
    baht = _fold_thai_int(bt)
    if not (0 <= satang <= 99):
        return None
    return (Decimal(baht) + Decimal(satang) / Decimal(100)).quantize(_Q2)


# ── VAT normalize (0.07 หรือ 7) ───────────────────────────────────────────────
def normalize_vat_rate(raw) -> Optional[Decimal]:
    """normalize อัตรา VAT → สัดส่วน (เช่น 0.07). รองรับ 0.07 (สัดส่วน) และ 7 (เปอร์เซ็นต์เต็ม).
    คืน None ถ้าอ่านไม่ออก. ค่าที่เข้าได้: 0.07 → 0.07 · 7 → 0.07 · 7.0 → 0.07 · '7%' → 0.07.
    """
    if raw is None:
        return None
    try:
        v = Decimal(str(raw).replace("%", "").replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None
    if v == 0:
        return Decimal("0")
    if v < 1:  # 0.07 = สัดส่วนอยู่แล้ว
        return v
    return v / Decimal(100)  # 7 → 0.07 (เปอร์เซ็นต์เต็ม)


def _D(x) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        return Decimal(str(x).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


# ── 3-way reconciliation ──────────────────────────────────────────────────────
RECONCILE_OK = "OK"
RECONCILE_MISMATCH = "MISMATCH"
_TOL = Decimal(
    "1.00"
)  # ผ่อนปรนปัดเศษ/floating-point noise (เช่น VAT=2691.5000000000005)


def reconcile_totals(
    net: Optional[Decimal],
    vat: Optional[Decimal],
    grand: Optional[Decimal],
    words_total: Optional[Decimal] = None,
    line_sum: Optional[Decimal] = None,
    vat_rate: Optional[Decimal] = None,
    tol: Decimal = _TOL,
) -> Dict:
    """เทียบยอด 3 ทาง (เท่าที่มีข้อมูล). คืน {status, checks[], details}.

    checks ที่ทำ (ข้ามอันที่ข้อมูลไม่พอ):
      • grand == net + vat
      • words_total == grand (ยอดตัวอักษร = ยอดรวม) หรือ == net (บางใบสะกดยอดก่อนภาษี)
      • line_sum == net (Σ line item = ยอดก่อนภาษี)
      • vat == net * vat_rate (ถ้ามี rate)
    """
    checks: List[Dict] = []

    def _chk(name, a, b):
        if a is None or b is None:
            return
        ok = abs(a - b) <= tol
        checks.append(
            {
                "check": name,
                "ok": ok,
                "left": float(a),
                "right": float(b),
                "diff": float(abs(a - b)),
            }
        )

    _chk(
        "grand=net+vat",
        grand,
        (net + vat) if (net is not None and vat is not None) else None,
    )
    if words_total is not None:
        # ยอดตัวอักษรควรตรงกับ grand (พบบ่อยสุด) — ถ้าไม่ ลองเทียบ net
        wt_ok_grand = grand is not None and abs(words_total - grand) <= tol
        wt_ok_net = net is not None and abs(words_total - net) <= tol
        ref, refname = (grand, "grand") if (grand is not None) else (net, "net")
        checks.append(
            {
                "check": f"words=={refname}",
                "ok": bool(wt_ok_grand or wt_ok_net),
                "left": float(words_total),
                "right": float(ref) if ref is not None else None,
                "diff": float(abs(words_total - ref)) if ref is not None else None,
            }
        )
    _chk("line_sum=net", line_sum, net)
    if vat_rate is not None and net is not None and vat is not None and vat_rate > 0:
        _chk("vat=net*rate", vat, (net * vat_rate).quantize(_Q2))

    done = [c for c in checks if c["right"] is not None]
    status = (
        RECONCILE_OK
        if (done and all(c["ok"] for c in done))
        else (RECONCILE_MISMATCH if done else "INSUFFICIENT")
    )
    failed = [c["check"] for c in done if not c["ok"]]
    return {"status": status, "checks": checks, "failed": failed}


# ── Row classification ────────────────────────────────────────────────────────
_VAT_MARK = re.compile(r"ภาษีมูลค่าเพิ่ม|ภ\.?พ\.?|\bvat\b", re.IGNORECASE)
_GRAND_MARK = re.compile(
    r"รวมทั้งสิ้น|ยอดสุทธิ|จำนวนเงินรวม|grand\s*total|net\s*total", re.IGNORECASE
)
_SUB_MARK = re.compile(
    r"รวมเป็นเงิน|ยอดรวมก่อน|รวมก่อนภาษี|มูลค่าสินค้า|sub\s*total", re.IGNORECASE
)


def classify_row(cells: List, seq_col: Optional[int] = None) -> str:
    """จำแนกชนิดแถวจากเนื้อหา cell — generic (ไม่ผูก template เดียว).
    คืน: 'words_total' / 'vat' / 'grand_total' / 'subtotal' / 'line_item' / 'blank'."""
    vals = [("" if v is None else str(v)).strip() for v in (cells or [])]
    joined = " ".join(vals)
    if not joined.strip():
        return "blank"
    # ยอดตัวอักษร = มี 'บาท' + ลงท้ายกลุ่มสตางค์/ถ้วน และแปลงเป็นเลขได้
    if "บาท" in joined and ("ถ้วน" in joined or "สตางค์" in joined):
        if thai_words_to_number(joined) is not None:
            return "words_total"
    if _GRAND_MARK.search(joined):
        return "grand_total"
    if _VAT_MARK.search(joined):
        return "vat"
    if _SUB_MARK.search(joined):
        return "subtotal"
    # line_item = มีเลขลำดับใน seq_col (ถ้าระบุ) หรือมีตัวเลขยอด + ข้อความชื่อ
    if seq_col is not None and seq_col < len(vals):
        sv = vals[seq_col].replace(".0", "")
        if sv.isdigit() and 1 <= int(sv) <= 50:
            return "line_item"
    return "line_item" if any(re.search(r"\d", v) for v in vals) else "blank"


# ── SEED template registry (จากหลักฐาน 773 sheets — ต้อง validate กับไฟล์จริง) ──
# ⚠️ SEED เท่านั้น: column index จากตาราง 2.1 ของ audit — ห้ามถือว่าครบ/ถูก 100%
#    ก่อนใช้ production ต้องสแกน 81/103 ไฟล์ยืนยัน + ขยาย (Phase 2 บนไฟล์จริง)
TEMPLATE_REGISTRY: Dict[str, Dict] = {
    "TKH": {
        "seq": 0,
        "desc": 1,
        "qty": 12,
        "price": 13,
        "unit": 11,
        "amount": 17,
        "words_col": 0,
        "vat_kind": "ratio",
    },  # 0.07
    "SEI": {
        "seq": 1,
        "desc": 2,
        "qty": 15,
        "price": 16,
        "unit": 17,
        "amount": 20,
        "words_col": 1,
        "vat_kind": "ratio",
    },
    "TOR": {
        "seq": None,
        "desc": 2,
        "qty": 7,
        "price": 9,
        "amount": 11,
        "words_col": 0,
        "words_paren": True,
        "vat_kind": "ratio",
    },
    "SBT": {
        "seq": 0,
        "desc": 1,
        "qty": 10,
        "price": 12,
        "unit": 11,
        "amount": 13,
        "words_col": 2,
        "vat_kind": "percent_int",
    },  # VAT = 7
}


# ── ingest envelope (fail loud) ───────────────────────────────────────────────
def ingest_bill(bill: Dict, tol: Decimal = _TOL) -> Dict:
    """ห่อผล reconcile ของ 1 บิล → ตั้ง needs_human_review เมื่อยอดไม่ reconcile/ข้อมูลไม่พอ.

    อ่าน field มาตรฐานจากบิลที่ parse แล้ว: subtotal/vat/total + (ออปชัน) words_total/items/vat_rate.
    ไม่แก้บิล (อ่านอย่างเดียว) — คืน dict สรุปเพื่อให้ชั้นบนตัดสินใจ. **ไม่ออก finding 'ลืมเลขลำดับ'**.
    """
    net = _D(bill.get("subtotal"))
    vat = _D(bill.get("vat"))
    grand = _D(bill.get("total"))
    words_total = None
    wt_raw = bill.get("words_total") or bill.get("amount_in_words")
    if wt_raw:
        words_total = thai_words_to_number(wt_raw)
    line_sum = None
    items = bill.get("items") or []
    amts = [_D(i.get("amount")) for i in items]
    amts = [a for a in amts if a is not None]
    if amts:
        line_sum = sum(amts, Decimal("0"))
    vat_rate = (
        normalize_vat_rate(bill.get("vat_rate"))
        if bill.get("vat_rate") is not None
        else None
    )

    rec = reconcile_totals(net, vat, grand, words_total, line_sum, vat_rate, tol=tol)
    needs_review = rec["status"] != RECONCILE_OK
    reason = ""
    if rec["status"] == RECONCILE_MISMATCH:
        reason = "ยอดไม่ reconcile: " + ", ".join(rec["failed"])
    elif rec["status"] == "INSUFFICIENT":
        reason = "ข้อมูลยอดไม่พอ reconcile (อ่านยอด/ยอดตัวอักษรไม่ได้)"
    return {
        "needs_human_review": needs_review,
        "reconcile_status": rec["status"],
        "reason": reason,
        "checks": rec["checks"],
        "parsed": {
            "net": float(net) if net is not None else None,
            "vat": float(vat) if vat is not None else None,
            "grand": float(grand) if grand is not None else None,
            "words_total": float(words_total) if words_total is not None else None,
            "line_sum": float(line_sum) if line_sum is not None else None,
        },
    }
