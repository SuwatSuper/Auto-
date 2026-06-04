# -*- coding: utf-8 -*-
"""
agents/verification_lenses.py — "คลังผู้ตรวจเชิงกลไก" (Inspection Bank) ของ VerificationAgent

แยกจาก verification_agent.py เพื่อ maintainability (แต่ละไฟล์ ≲600 บรรทัด, ไม่มี circular import):
  • ที่นี่ = เลนส์ตรวจอิสระทั้งหมด (ฟังก์ชันบริสุทธิ์) + ทะเบียน INSPECTION_LENSES + ตัวสร้างดัชนีข้ามบิล
  • verification_agent.py = Supervisor (รวมโหวต → consensus) ที่ import คลังนี้

หลักการ (ย่อ — ดูเต็มใน verification_agent.py):
  PRECISION-FIRST: เลนส์ "งดออกเสียง (0)" เมื่อข้อมูลไม่พอ/ไม่เกี่ยว ห้ามเดา.
  กฎโดเมนล็อก: VAT = round(subtotal×0.07,2) เป๊ะ (L8, ห้าม band).
  OFFLINE/ADVISORY: อ่านอย่างเดียว ไม่มี network; L6 (LLM) งดออกเสียงเมื่อ offline → deterministic.
  เพิ่มผู้ตรวจ = ต่อ Lens(...) ใน INSPECTION_LENSES + unit test + รัน pin test (gated).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Callable, Dict, List, Tuple

from . import core_access as core
from ._shared import parse_llm_json

_D = core._D

# กลุ่มกฎ "แม่นสูง" (เลขคณิต/โครงสร้าง — ดีเทอร์มินิสติก, false-positive ต่ำ)
_HIGH_PRECISION = {
    "VAT001",
    "VAT002",
    "VAT003",
    "VAT005",
    "VAT007",
    "VAT009",
    "TAX001",
    "TAX002",
    "ITM001",
    "ITM017",
}
# กลุ่มกฎ "heuristic" (fuzzy/NLP/OCR/แนะนำ — false-positive สูงกว่า)
_HEURISTIC = {
    "ITM003",
    "ITM004",
    "ITM010",
    "ITM011",
    "ITM012",
    "TAX004",
    "ADDR002",
}
# เลนส์ที่เกี่ยวกับ "ยอดเงิน" (กลุ่มเลขคณิตออกเสียงเฉพาะ issue กลุ่มนี้)
_MONEY_PREFIXES = ("VAT", "ITM001", "ITM017", "ITM018")

# กฎโดเมนล็อก: VAT 7% เป๊ะ + ค่ายอมรับปัดเศษ (นักบัญชีปรับได้ที่จุดเดียวนี้)
_VAT_RATE = Decimal("0.07")
_VAT_ROUND_TOL = Decimal("0.01")  # ตรงถึงสตางค์ = "เป๊ะภายในปัดเศษ"
_MONEY_TOL = Decimal("0.01")  # ค่ายอมรับเลขคณิตยอด (qty×price, Σ, chain)
_ROUND_BAHT = Decimal("0.5")  # ส่วนต่าง ≤ 0.50 = อธิบายได้ด้วยปัดเศษ


def _is_money_issue(code: str) -> bool:
    return any(code.startswith(p) for p in _MONEY_PREFIXES)


def _q2(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ──────────────────────────────────────────────────────────────────────────
# Lens framework — "คลังผู้ตรวจเชิงกลไก" (ขยายจำนวนผู้ตรวจได้โดยไม่แตะ supervisor)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class LensInput:
    """ข้อมูลที่เลนส์ตรวจ 1 ตัวมองเห็น (อ่านอย่างเดียว).
    index/master = ดัชนีข้ามบิล + ทะเบียนบริษัท (เติมครั้งเดียวใน _run, เลนส์อ่านอย่างเดียว).
    """

    bill: dict
    issue: dict
    code: str
    sev: str
    peers: List[dict]  # บิลพี่น้องในไฟล์เดียวกัน
    llm: object = None  # provider หรือ None (offline/ปิด)
    index: Dict = field(default_factory=dict)
    master: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Lens:
    """ผู้ตรวจ 1 คน: id (key ใน votes), dimension (ความเชี่ยวชาญ — ใช้ในรายงาน),
    fn (ฟังก์ชันบริสุทธิ์: LensInput -> (vote, reason))."""

    id: str
    dimension: str
    fn: Callable[[LensInput], Tuple[int, str]]


# ===========================================================================
# เลนส์ฐาน (v9.1) L1–L6
# ===========================================================================
def lens_recompute(x: LensInput) -> Tuple[int, str]:
    """L1: คำนวณยอดใหม่จากต้นทางอย่างอิสระ (เฉพาะ issue กลุ่มยอดเงิน)."""
    b, code = x.bill, x.code
    tol = _MONEY_TOL
    try:
        if code.startswith("VAT001"):
            items = [_D(i.get("amount")) for i in (b.get("items") or [])]
            items = [d for d in items if d is not None]
            sub = _D(b.get("subtotal"))
            if not items or sub is None:
                return 0, ""
            diff = abs(sum(items, Decimal("0")) - sub)
            return (
                (1, f"recompute: Σรายการต่าง subtotal {float(diff):,.2f}")
                if diff > tol
                else (-1, "recompute: Σรายการ=subtotal (ไม่ต่างจริง)")
            )
        if code.startswith("VAT002"):
            sub, vat = _D(b.get("subtotal")), _D(b.get("vat"))
            if sub is None or vat is None or abs(vat) <= Decimal("1"):
                return 0, ""
            exp = sub * Decimal("0.07")
            return (
                (1, "recompute: vat ไม่ใกล้ 7%")
                if abs(exp - vat) > Decimal("1")
                else (-1, "recompute: vat ≈ 7% (ไม่ต่างจริง)")
            )
        if code.startswith("VAT003"):
            sub, vat, tot = (
                _D(b.get("subtotal")),
                _D(b.get("vat")) or Decimal("0"),
                _D(b.get("total")),
            )
            if sub is None or tot is None:
                return 0, ""
            return (
                (1, "recompute: sub+vat ≠ total")
                if abs((sub + vat) - tot) > Decimal("1")
                else (-1, "recompute: sub+vat = total (ไม่ต่างจริง)")
            )
        if code.startswith("ITM001"):
            bad = 0
            for it in b.get("items") or []:
                q, p, a = _D(it.get("qty")), _D(it.get("price")), _D(it.get("amount"))
                if None in (q, p, a):
                    continue
                if abs(q * p - a) > tol:
                    bad += 1
            return (
                (1, f"recompute: {bad} รายการ qty×price≠amount")
                if bad
                else (-1, "recompute: ทุกรายการ qty×price=amount")
            )
        if code.startswith("VAT005") or code.startswith("ITM017"):
            vals = [_D(b.get(k)) for k in ("subtotal", "vat", "total")]
            neg = any(v is not None and v < 0 for v in vals)
            return (1, "recompute: พบยอดติดลบจริง") if neg else (0, "")
    except Exception:
        return 0, ""
    return 0, ""


def lens_provenance(x: LensInput) -> Tuple[int, str]:
    """L2: ยอด derived (ระบบเดา) ลดความมั่นใจว่าเป็น error เอกสาร / parsed เพิ่มความมั่นใจ."""
    b, code = x.bill, x.code
    if not _is_money_issue(code):
        return 0, ""
    src = b.get("amount_source") or {}
    derived = [k for k in ("subtotal", "vat", "total") if src.get(k) == "derived"]
    if derived:
        return (
            -1,
            f"ยอด {','.join(derived)} เป็นค่าที่ระบบเดาเอง (derived) — อาจไม่ใช่ error เอกสาร",
        )
    if src and all(
        src.get(k) == "parsed" for k in ("subtotal", "vat", "total") if k in src
    ):
        return 1, "ยอดอ่านจากเอกสารโดยตรง (parsed) — น่าเชื่อว่าเป็นค่าจริงในใบ"
    return 0, ""


def lens_confidence(x: LensInput) -> Tuple[int, str]:
    """L3: ความเชื่อมั่นการ parse ของทั้งบิล."""
    pc = str(x.bill.get("parse_confidence", "")).upper()
    if pc == "HIGH":
        return 1, "parse confidence HIGH"
    if pc == "LOW":
        return -1, "parse confidence LOW — ทั้งบิลอ่านมาไม่นิ่ง อาจเป็น artifact"
    return 0, ""


def lens_peer(x: LensInput) -> Tuple[int, str]:
    """L4: โดดเดี่ยวในไฟล์ = anomaly เด่น / พบทั่วไป = อาจเป็นควิร์กของชุด."""
    b, code, peers = x.bill, x.code, x.peers
    others = [p for p in peers if p is not b]
    if not others:
        return 0, ""
    share = sum(
        1
        for p in others
        if any(str(i.get("code", "")) == code for i in (p.get("issues") or []))
    )
    frac = share / len(others)
    if frac < 0.5:
        return (
            1,
            f"โดดเดี่ยวในไฟล์ ({share}/{len(others)} บิลพี่น้องมี {code}) — anomaly เด่น",
        )
    return 0, f"พบทั่วไปในไฟล์ ({share}/{len(others)}) — อาจเป็นรูปแบบ/ควิร์กของชุดนี้"


def lens_ruleclass(x: LensInput) -> Tuple[int, str]:
    """L5: กฎกลุ่มแม่นสูง vs heuristic."""
    base = x.code.split("-")[0]
    if base in _HIGH_PRECISION:
        return 1, f"กฎ {base} กลุ่มแม่นสูง (เลขคณิต/โครงสร้าง)"
    if base in _HEURISTIC:
        return (
            -1,
            f"กฎ {base} กลุ่ม heuristic (fuzzy/NLP/OCR) — โน้มเอียง false-positive",
        )
    return 0, ""


_LLM_SYSTEM = (
    "คุณคือผู้ช่วยตรวจสอบใบกำกับภาษีไทย ทำหน้าที่ 'ผู้ตรวจซ้ำ' ของระบบ audit. "
    "ระบบเจอ Error หนึ่งจุดบนบิล หน้าที่คุณคือประเมินว่า Error นี้ 'น่าจะเป็นปัญหาจริง' "
    "หรือ 'น่าจะเป็น false positive (เช่นจากการอ่านไฟล์ผิด/ปัดเศษ)'. "
    'ตอบเป็น JSON เท่านั้น: {"verdict":"confirm|refute|uncertain","reason":"สั้นๆ"}'
)


def lens_llm(x: LensInput) -> Tuple[int, str]:
    """L6: เลนส์ภาษา (Local LLM, opt-in). offline/probe ไม่ติด → งดออกเสียง (deterministic)."""
    if x.llm is None:
        return 0, ""
    b, iss, code = x.bill, x.issue, x.code
    try:
        user = (
            f"Error code: {code} ({iss.get('name','')})\n"
            f"รายละเอียด: {str(iss.get('detail',''))[:200]}\n"
            f"subtotal={b.get('subtotal')} vat={b.get('vat')} total={b.get('total')} "
            f"จำนวนรายการ={len(b.get('items') or [])} "
            f"parse_confidence={b.get('parse_confidence')}"
        )
        raw = x.llm.chat(_LLM_SYSTEM, user)
        obj = parse_llm_json(raw)
        verdict = str(obj.get("verdict", "")).lower().strip()
        reason = str(obj.get("reason", ""))[:80]
        if verdict == "confirm":
            return 1, f"LLM: ยืนยันเป็นปัญหาจริง — {reason}"
        if verdict == "refute":
            return -1, f"LLM: น่าจะ false positive — {reason}"
        return 0, (f"LLM: ไม่ชัด — {reason}" if reason else "")
    except Exception:
        return 0, ""


# ===========================================================================
# เลนส์เพิ่ม — ยอดเงิน/เลขคณิต (L7, L8, L11, L12, L13, L14, L15, L16)
# ===========================================================================
def lens_rounding_explains(x: LensInput) -> Tuple[int, str]:
    """L7: ส่วนต่างเล็ก ≤ 0.50 บาท = ปัดเศษสตางค์ → ค้าน (เฉพาะ refute)."""
    b, code = x.bill, x.code
    if not _is_money_issue(code):
        return 0, ""
    try:
        sub, vat, tot = _D(b.get("subtotal")), _D(b.get("vat")), _D(b.get("total"))
        gap = None
        if code.startswith("VAT003") and sub is not None and tot is not None:
            gap = abs((sub + (vat or Decimal("0"))) - tot)
        elif code.startswith("VAT001") and sub is not None:
            items = [_D(i.get("amount")) for i in (b.get("items") or [])]
            items = [d for d in items if d is not None]
            if items:
                gap = abs(sum(items, Decimal("0")) - sub)
        elif code.startswith("VAT002") and sub is not None and vat is not None:
            gap = abs(_q2(sub * _VAT_RATE) - vat)
        if gap is None:
            return 0, ""
        if Decimal("0") < gap <= _ROUND_BAHT:
            return (
                -1,
                f"ส่วนต่างเพียง {float(gap):.2f} บาท — อธิบายได้ด้วยปัดเศษสตางค์ (น่าจะไม่ใช่ error)",
            )
        return 0, ""
    except Exception:
        return 0, ""


def lens_vat_7pct_exact(x: LensInput) -> Tuple[int, str]:
    """L8: กฎโดเมนล็อก — vat ต้อง = round(subtotal×0.07,2). เป๊ะภายในปัดเศษ → ค้าน,
    เบี่ยงเกินปัดเศษ → ยืนยัน. (ห้ามใช้ band) งดออกเสียงถ้าไม่คิด VAT (อาจ exempt)."""
    if not x.code.startswith("VAT002"):
        return 0, ""
    try:
        sub, vat = _D(x.bill.get("subtotal")), _D(x.bill.get("vat"))
        if sub is None or vat is None or sub <= 0 or abs(vat) <= Decimal("1"):
            return 0, ""  # ไม่มียอด / vat ดูเป็น rate หรือ 0 (อาจ exempt) → งดออกเสียง
        expected = _q2(sub * _VAT_RATE)
        diff = abs(vat - expected)
        if diff <= _VAT_ROUND_TOL:
            return (
                -1,
                f"vat={float(vat):,.2f} = 7% เป๊ะ (คาด {float(expected):,.2f}) — น่าจะไม่ใช่ error",
            )
        return (
            1,
            f"vat={float(vat):,.2f} เบี่ยงจาก 7% (คาด {float(expected):,.2f}, ต่าง {float(diff):,.2f}) — ยืนยันผิด",
        )
    except Exception:
        return 0, ""


def lens_amount_completeness(x: LensInput) -> Tuple[int, str]:
    """L11: ยอดที่จำเป็นอ่านไม่ได้ (None) → error อาจมาจากข้อมูลไม่ครบ (ค้าน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    missing = [k for k in ("subtotal", "vat", "total") if _D(x.bill.get(k)) is None]
    if missing:
        return (
            -1,
            f"ยอด {','.join(missing)} อ่านไม่ได้ (ว่าง) — error อาจมาจากข้อมูลไม่ครบ",
        )
    return 0, ""


def lens_money_triple(x: LensInput) -> Tuple[int, str]:
    """L12: ความสอดคล้องของสามยอด round(sub)+round(vat) vs round(total) (มุมองค์รวม)."""
    if not _is_money_issue(x.code):
        return 0, ""
    b = x.bill
    sub, vat, tot = _D(b.get("subtotal")), _D(b.get("vat")), _D(b.get("total"))
    if sub is None or tot is None:
        return 0, ""
    v = vat if vat is not None else Decimal("0")
    diff = abs(_q2(sub) + _q2(v) - _q2(tot))
    if diff <= _MONEY_TOL:
        return -1, "สามยอดสอดคล้อง (sub+vat=total) — โครงยอดไม่ขัดกัน"
    if diff > _ROUND_BAHT:
        return (
            1,
            f"สามยอดไม่สอดคล้อง (ต่าง {float(diff):,.2f}) — ยืนยันความผิดปกติของยอด",
        )
    return 0, ""


def lens_line_sum_amount(x: LensInput) -> Tuple[int, str]:
    """L13: Σ(items.amount) เทียบ subtotal (มุมรายการ → corroborate)."""
    if not _is_money_issue(x.code):
        return 0, ""
    b = x.bill
    sub = _D(b.get("subtotal"))
    amts = [_D(i.get("amount")) for i in (b.get("items") or [])]
    amts = [a for a in amts if a is not None]
    if sub is None or not amts:
        return 0, ""
    diff = abs(sum(amts, Decimal("0")) - sub)
    if diff <= _MONEY_TOL:
        return -1, "Σ ยอดรายการ = subtotal — รายการประกอบยอดครบ"
    if diff > _ROUND_BAHT:
        return 1, f"Σ ยอดรายการ ≠ subtotal (ต่าง {float(diff):,.2f})"
    return 0, ""


def lens_line_qty_price(x: LensInput) -> Tuple[int, str]:
    """L14: Σ(qty×price) เทียบ subtotal (อิสระจาก L13 ที่ใช้ amount)."""
    if not _is_money_issue(x.code):
        return 0, ""
    b = x.bill
    sub = _D(b.get("subtotal"))
    if sub is None:
        return 0, ""
    tot = Decimal("0")
    n = 0
    for it in b.get("items") or []:
        q, p = _D(it.get("qty")), _D(it.get("price"))
        if q is None or p is None:
            continue
        tot += q * p
        n += 1
    if n == 0:
        return 0, ""
    diff = abs(tot - sub)
    if diff <= _MONEY_TOL:
        return -1, "Σ(qty×price) = subtotal — ราคา×จำนวนประกอบยอดได้"
    if diff > _ROUND_BAHT:
        return 1, f"Σ(qty×price) ≠ subtotal (ต่าง {float(diff):,.2f})"
    return 0, ""


def lens_negative_sanity(x: LensInput) -> Tuple[int, str]:
    """L15: ยอด sub/vat/total ติดลบ = ผิดปกติจริง (ยืนยัน) — เฉพาะ issue ยอดเงิน."""
    if not _is_money_issue(x.code):
        return 0, ""
    b = x.bill
    negs = [
        k
        for k in ("subtotal", "vat", "total")
        if (_D(b.get(k)) is not None and _D(b.get(k)) < 0)
    ]
    if negs:
        return 1, f"ยอด {','.join(negs)} ติดลบ — ผิดปกติชัดเจน"
    return 0, ""


def lens_magnitude_outlier(x: LensInput) -> Tuple[int, str]:
    """L16: total เทียบบิลพี่น้องในไฟล์ (≥3 ใบ, std>0). |z|>3 ยืนยัน / |z|<1 ค้าน."""
    if not _is_money_issue(x.code):
        return 0, ""
    b = x.bill
    tot = _D(b.get("total"))
    if tot is None:
        return 0, ""
    vals = []
    for p in x.peers:
        if p is b:
            continue
        t = _D(p.get("total"))
        if t is not None:
            vals.append(float(t))
    if len(vals) < 3:
        return 0, ""
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = var**0.5
    if std <= 0:
        return 0, ""
    z = abs(float(tot) - mean) / std
    if z > 3:
        return 1, f"ยอดรวมห่างค่ากลางของไฟล์ {z:.1f}σ — outlier ชัด"
    if z < 1:
        return -1, f"ยอดรวมอยู่ในช่วงปกติของไฟล์ ({z:.1f}σ)"
    return 0, ""


# ===========================================================================
# เลนส์เพิ่ม — เลขภาษี/เอกสาร/ข้ามบิล (L9, L10, L17, L18, L19, L20, L21, L22)
# ===========================================================================
def lens_taxid_checksum(x: LensInput) -> Tuple[int, str]:
    """L9: ใช้ checksum mod11 ของ engine (ไม่เขียนใหม่ → ไม่ดริฟต์)."""
    if not x.code.startswith("TAX"):
        return 0, ""
    try:
        tid = core.clean_tax_id(x.bill.get("tax_id"))
    except Exception:
        return 0, ""
    s = "" if tid is None else str(tid)
    if len(s) != 13 or not s.isdigit():
        return 0, ""
    try:
        if core._taxid_checksum_ok(s):
            return -1, "checksum เลขภาษี (mod11) ถูกต้อง — เลขโครงสร้างสมเหตุผล"
        return 1, "checksum เลขภาษี (mod11) ไม่ผ่าน — ยืนยันเลขน่าจะพิมพ์ผิด/ปลอม"
    except Exception:
        return 0, ""


def lens_taxid_format(x: LensInput) -> Tuple[int, str]:
    """L10: โครงสร้างเลขภาษี 13 หลักล้วน."""
    if not x.code.startswith("TAX"):
        return 0, ""
    try:
        tid = core.clean_tax_id(x.bill.get("tax_id"))
    except Exception:
        return 0, ""
    if tid is None or str(tid) == "":
        return 0, ""
    s = str(tid)
    if len(s) == 13 and s.isdigit():
        return -1, "เลขภาษีเป็นตัวเลข 13 หลักครบ (รูปแบบถูก)"
    return 1, f"เลขภาษีผิดรูปแบบ: '{s}' ({len(s)} อักขระ) — ยืนยันปัญหาเชิงรูปแบบ"


def lens_taxid_crosscompany(x: LensInput) -> Tuple[int, str]:
    """L17: เลขภาษีเดียวกันโผล่ภายใต้ 'ชื่อบริษัทต่างกัน' ข้ามทั้งชุด → ยืนยัน (index)."""
    if not x.code.startswith("TAX"):
        return 0, ""
    try:
        tid = core.clean_tax_id(x.bill.get("tax_id"))
    except Exception:
        return 0, ""
    s = "" if tid is None else str(tid)
    if len(s) != 13:
        return 0, ""
    companies = x.index.get("taxid_companies", {}).get(s, set())
    if len(companies) >= 2:
        return (
            1,
            f"เลขภาษี {s} พบใน {len(companies)} ชื่อบริษัทต่างกัน — น่าสงสัยว่าใช้ผิด/ปลอม",
        )
    return 0, ""


def lens_duplicate_signature(x: LensInput) -> Tuple[int, str]:
    """L18: (tax_id,total) ซ้ำกับบิลอื่น ≥1 ใบ → ยืนยันความน่าสงสัยว่าออกซ้ำ (index)."""
    b = x.bill
    try:
        tid = core.clean_tax_id(b.get("tax_id"))
    except Exception:
        tid = None
    tot = _D(b.get("total"))
    if tid is None or tot is None or str(tid) == "":
        return 0, ""
    sig = (str(tid), str(_q2(tot)))
    cnt = x.index.get("sig_taxid_total", {}).get(sig, 0)
    if cnt >= 2:
        return 1, f"ยอดรวม {float(tot):,.2f} + เลขภาษีเดียวกัน พบ {cnt} ใบ — อาจออกซ้ำ"
    return 0, ""


def lens_period_match(x: LensInput) -> Tuple[int, str]:
    """L19: วันที่ในใบ (iv_date) อยู่ในงวดของไฟล์ (file_info year/month) ไหม.
    งดออกเสียงถ้าไฟล์ไม่ระบุงวด (เช่น fixture)."""
    b = x.bill
    fi = b.get("file_info") or {}
    yr, mo = fi.get("year"), fi.get("month")
    dt = b.get("iv_date")
    if yr is None or dt is None or not hasattr(dt, "year"):
        return 0, ""
    if dt.year != yr:
        return 1, f"ปีในใบ ({dt.year}) ไม่ตรงงวดไฟล์ ({yr})"
    if mo is not None and hasattr(dt, "month") and dt.month != mo:
        return 1, f"เดือนในใบ ({dt.month}) ไม่ตรงงวดไฟล์ ({mo})"
    return -1, "วันที่ในใบตรงงวดของไฟล์"


def lens_doc_completeness(x: LensInput) -> Tuple[int, str]:
    """L20: เอกสารหลัก (company/tax_id/iv_number/iv_date) อ่านได้ไม่ครบ → error อาจเป็น artifact."""
    b = x.bill
    missing = []
    if not (b.get("company") or "").strip():
        missing.append("ชื่อบริษัท")
    try:
        tid = core.clean_tax_id(b.get("tax_id"))
    except Exception:
        tid = None
    if not tid:
        missing.append("เลขภาษี")
    if not (str(b.get("iv_number") or "")).strip():
        missing.append("เลขที่ใบกำกับ")
    if b.get("iv_date") is None:
        missing.append("วันที่")
    if len(missing) >= 2:
        return (
            -1,
            f"เอกสารอ่านได้ไม่ครบ (ขาด {', '.join(missing)}) — error อาจเป็น artifact การอ่าน",
        )
    return 0, ""


def lens_master_known(x: LensInput) -> Tuple[int, str]:
    """L21: เลขภาษี/บริษัท อยู่ในทะเบียน master (ภ.พ.20 local) → ผู้ขายรู้จัก (ลดความน่าจะผิด)."""
    if not (x.code.startswith("TAX") or x.code.startswith("ADDR")):
        return 0, ""
    master = x.master or {}
    if not master:
        return 0, ""
    try:
        tid = core.clean_tax_id(x.bill.get("tax_id"))
    except Exception:
        tid = None
    known_ids = x.index.get("master_taxids")
    if known_ids is None:
        known_ids = set()
    if tid and str(tid) in known_ids:
        return -1, "เลขภาษีตรงทะเบียน master (ผู้ขายรู้จัก) — ลดความน่าจะเป็น error"
    return 0, ""


def lens_iv_prefix_match(x: LensInput) -> Tuple[int, str]:
    """L22: เลขที่ใบกำกับขึ้นต้นตรง iv_prefix ของบริษัทในทะเบียน master ไหม (เฉพาะ issue IV/SEQ)."""
    base = x.code.split("-")[0]
    if not (base.startswith("IV") or base.startswith("SEQ")):
        return 0, ""
    master = x.master or {}
    iv = str(x.bill.get("iv_number") or "").strip()
    if not master or not iv:
        return 0, ""
    prefixes = x.index.get("master_iv_prefixes") or set()
    if not prefixes:
        return 0, ""
    if any(iv.startswith(p) for p in prefixes if p):
        return -1, "เลขที่ใบกำกับขึ้นต้นตรง prefix ของบริษัทในทะเบียน"
    return 1, f"เลขที่ใบกำกับ '{iv}' ไม่ขึ้นต้นด้วย prefix ที่ลงทะเบียนไว้"


# ===========================================================================
# เลนส์เพิ่ม (v9.2) — ยอด/รายการ/ข้ามบิล มุมใหม่ (L23–L30)
#   ทุกตัว PRECISION-FIRST: งดออกเสียง (0) เมื่อข้อมูลไม่พอ/ไม่เกี่ยว ; self-contained
#   (ใช้เฉพาะ field ของบิล + helper เดิม + ดัชนีข้ามบิล) ; deterministic, ไม่มี network.
# ===========================================================================
def lens_vat_zero_exempt(x: LensInput) -> Tuple[int, str]:
    """L23: issue กลุ่มยอดเงินที่ vat==0 ทั้งที่ subtotal>0 → อาจยกเว้น/นอกระบบ VAT (ค้าน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    sub, vat = _D(x.bill.get("subtotal")), _D(x.bill.get("vat"))
    if sub is None or vat is None:
        return 0, ""
    if sub > 0 and vat == 0:
        return (
            -1,
            "VAT=0 ทั้งที่มียอดก่อนภาษี — อาจเป็นสินค้ายกเว้น/นอกระบบ VAT (อาจไม่ใช่ error)",
        )
    return 0, ""


def lens_item_count_sanity(x: LensInput) -> Tuple[int, str]:
    """L24: issue ยอดเงินแต่ไม่มีรายการสินค้าเลย ทั้งที่มี subtotal>0 → รายการอาจ parse ไม่ได้ (ค้าน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    sub = _D(x.bill.get("subtotal"))
    items = x.bill.get("items") or []
    if sub is not None and sub > 0 and len(items) == 0:
        return (
            -1,
            "ไม่มีรายการสินค้าให้ตรวจ แต่มี subtotal — รายการอาจอ่านไม่ได้ (artifact การ parse)",
        )
    return 0, ""


def lens_line_amount_negative(x: LensInput) -> Tuple[int, str]:
    """L25: รายการสินค้าใดมียอด (amount) ติดลบ บน issue ยอดเงิน → ผิดปกติเชิงรายการ (ยืนยัน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    n = 0
    for it in x.bill.get("items") or []:
        a = _D(it.get("amount"))
        if a is not None and a < 0:
            n += 1
    if n:
        return 1, f"พบ {n} รายการยอดติดลบ — ผิดปกติเชิงรายการ (ยืนยันความผิดปกติของยอด)"
    return 0, ""


def lens_duplicate_line_in_bill(x: LensInput) -> Tuple[int, str]:
    """L26: รายการ (ชื่อ+ยอด) ซ้ำกันภายในบิลเดียว ≥2 ครั้ง → น่าสงสัยคีย์ข้อมูลซ้ำ (ยืนยัน)."""
    seen: Dict[Tuple[str, str], int] = {}
    for it in x.bill.get("items") or []:
        name = str(it.get("name", "")).strip()
        a = _D(it.get("amount"))
        if not name or a is None:
            continue
        key = (name, str(_q2(a)))
        seen[key] = seen.get(key, 0) + 1
    dup = sum(1 for c in seen.values() if c >= 2)
    if dup:
        return 1, f"พบ {dup} รายการที่ (ชื่อ+ยอด) ซ้ำในบิลเดียว — น่าสงสัยคีย์ข้อมูลซ้ำ"
    return 0, ""


def lens_company_multi_taxid(x: LensInput) -> Tuple[int, str]:
    """L27: ชื่อบริษัทเดียวกันผูกกับเลขภาษี ≥2 เลขข้ามทั้งชุด → ปนข้อมูล (ยืนยัน, เฉพาะ TAX). (index)"""
    if not x.code.startswith("TAX"):
        return 0, ""
    comp = (x.bill.get("company") or "").strip()
    if not comp:
        return 0, ""
    tids = x.index.get("company_taxids", {}).get(comp, set())
    if len(tids) >= 2:
        return (
            1,
            f"ชื่อบริษัท '{comp[:20]}' ผูกกับ {len(tids)} เลขภาษีต่างกัน — น่าสงสัยข้อมูลปน/พิมพ์ผิด",
        )
    return 0, ""


def lens_total_lt_subtotal(x: LensInput) -> Tuple[int, str]:
    """L28: ยอดรวม < ยอดก่อนภาษี (subtotal>0) → เป็นไปไม่ได้ถ้า VAT≥0 (ยืนยัน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    sub, tot = _D(x.bill.get("subtotal")), _D(x.bill.get("total"))
    if sub is None or tot is None or sub <= 0:
        return 0, ""
    if tot < sub:
        return (
            1,
            f"ยอดรวม {float(tot):,.2f} < ยอดก่อนภาษี {float(sub):,.2f} — เป็นไปไม่ได้ถ้า VAT≥0",
        )
    return 0, ""


def lens_decimal_scale_error(x: LensInput) -> Tuple[int, str]:
    """L29: total/subtotal ≈ 10 หรือ 100 เท่า → อาจพิมพ์ทศนิยมผิดตำแหน่ง (ยืนยัน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    sub, tot = _D(x.bill.get("subtotal")), _D(x.bill.get("total"))
    if sub is None or tot is None or sub <= 0 or tot <= 0:
        return 0, ""
    ratio = float(tot) / float(sub) if tot >= sub else float(sub) / float(tot)
    for scale in (10.0, 100.0):
        if abs(ratio - scale) <= scale * 0.01:
            return (
                1,
                f"อัตราส่วนยอด ≈ {int(scale)} เท่า — อาจพิมพ์ทศนิยมผิดตำแหน่ง (decimal slip)",
            )
    return 0, ""


def lens_vat_present_no_base(x: LensInput) -> Tuple[int, str]:
    """L30: มี VAT (|vat|>1) แต่ subtotal หาย/เป็น 0 → VAT ลอยไม่มียอดฐาน (ยืนยัน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    sub, vat = _D(x.bill.get("subtotal")), _D(x.bill.get("vat"))
    if vat is None or abs(vat) <= Decimal("1"):
        return 0, ""
    if sub is None or sub == 0:
        return (
            1,
            "มี VAT แต่ไม่มียอดฐาน (subtotal หาย/เป็น 0) — VAT ลอย ผิดโครงสร้างยอด",
        )
    return 0, ""


# ===========================================================================
# เลนส์เพิ่ม (v9.2b) — เวลา/งวด/รายการ มิติที่ยังบอด (L31–L34)
#   reuse domain logic จาก core (audit_today / detect_iv_period_mismatch) → ไม่ดริฟต์
# ===========================================================================
def lens_future_date(x: LensInput) -> Tuple[int, str]:
    """L31: วันที่ในใบเป็น "อนาคต" เทียบวันตรวจ (audit_today) → ผิดปกติชัด (ยืนยัน).
    deterministic: audit_today เคารพ PUOPUY_AUDIT_DATE. งดออกเสียงถ้าไม่มีวันที่/อ่านวันตรวจไม่ได้.
    """
    dt = x.bill.get("iv_date")
    if dt is None or not hasattr(dt, "year"):
        return 0, ""
    today_fn = core.get("audit_today")
    if today_fn is None:
        return 0, ""
    try:
        today = today_fn()
        d = dt.date() if hasattr(dt, "date") else dt
        if d > today:
            return (
                1,
                f"วันที่ในใบ {d.isoformat()} เป็นอนาคต (เทียบวันตรวจ {today.isoformat()}) — ผิดปกติ",
            )
    except Exception:
        return 0, ""
    return 0, ""


def lens_iv_period_conflict(x: LensInput) -> Tuple[int, str]:
    """L32: งวดที่ฝังในเลขที่เอกสารขัดกับวันที่ในบิล (reuse detect_iv_period_mismatch).
    เฉพาะ issue กลุ่มเอกสาร/วันที่ (IV/DT/DOC/SEQ). mismatch → ยืนยัน, ตรงงวด → ค้าน."""
    base = x.code.split("-")[0]
    if not (
        base.startswith("IV")
        or base.startswith("DT")
        or base.startswith("DOC")
        or base.startswith("SEQ")
    ):
        return 0, ""
    fn = core.get("detect_iv_period_mismatch")
    if fn is None:
        return 0, ""
    iv, dt = x.bill.get("iv_number"), x.bill.get("iv_date")
    if not iv or dt is None:
        return 0, ""
    try:
        res = fn(iv, dt)
    except Exception:
        return 0, ""
    if not res:
        return 0, ""
    if res.get("mismatch"):
        return (
            1,
            f"งวดในเลขเอกสาร ({res.get('iv_period')}) ขัดวันที่ในบิล ({res.get('doc_period')}) — ยืนยัน",
        )
    return -1, "งวดในเลขเอกสารตรงวันที่ในบิล — โครงสร้างเลข/วันที่สอดคล้อง"


def lens_qty_negative(x: LensInput) -> Tuple[int, str]:
    """L33: รายการสินค้าใดมีจำนวน (qty) ติดลบ บน issue ยอดเงิน → ผิดปกติเชิงรายการ (ยืนยัน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    n = 0
    for it in x.bill.get("items") or []:
        q = _D(it.get("qty"))
        if q is not None and q < 0:
            n += 1
    if n:
        return 1, f"พบ {n} รายการจำนวน (qty) ติดลบ — ผิดปกติเชิงรายการ"
    return 0, ""


def lens_subtotal_zero_with_items(x: LensInput) -> Tuple[int, str]:
    """L34: subtotal หาย/เป็น 0 แต่ Σ(ยอดรายการ) > 0 → subtotal น่าจะ parse ไม่ได้ (ยืนยัน)."""
    if not _is_money_issue(x.code):
        return 0, ""
    sub = _D(x.bill.get("subtotal"))
    if sub is not None and sub != 0:
        return 0, ""
    amts = [_D(i.get("amount")) for i in (x.bill.get("items") or [])]
    s = sum((a for a in amts if a is not None), Decimal("0"))
    if s > 0:
        return (
            1,
            f"subtotal หาย/เป็น 0 แต่ยอดรวมรายการ = {float(s):,.2f} — subtotal น่าจะอ่านไม่ได้",
        )
    return 0, ""


# ──────────────────────────────────────────────────────────────────────────
# คลังผู้ตรวจ (INSPECTION BANK) — ลำดับนี้กำหนดลำดับ reasons ที่แสดง
#   ★ เพิ่มผู้ตรวจ = ต่อ Lens(...) + unit test + รัน pin test (gated). supervisor ไม่ต้องแก้.
# ──────────────────────────────────────────────────────────────────────────
INSPECTION_LENSES: Tuple[Lens, ...] = (
    # ── ฐาน (v9.1) ──
    Lens("L1_recompute", "arithmetic", lens_recompute),
    Lens("L2_provenance", "provenance", lens_provenance),
    Lens("L3_confidence", "parse_trust", lens_confidence),
    Lens("L4_peer", "peer_consistency", lens_peer),
    Lens("L5_ruleclass", "rule_precision", lens_ruleclass),
    Lens("L6_llm", "language_model", lens_llm),
    # ── ยอดเงิน/เลขคณิต ──
    Lens("L7_rounding", "rounding_artifact", lens_rounding_explains),
    Lens("L8_vat_7pct", "vat_7pct_exact", lens_vat_7pct_exact),
    Lens("L11_amt_complete", "amount_completeness", lens_amount_completeness),
    Lens("L12_money_triple", "money_triple", lens_money_triple),
    Lens("L13_line_sum", "line_sum_amount", lens_line_sum_amount),
    Lens("L14_qty_price", "line_qty_price", lens_line_qty_price),
    Lens("L15_negative", "negative_sanity", lens_negative_sanity),
    Lens("L16_magnitude", "magnitude_outlier", lens_magnitude_outlier),
    # ── เลขภาษี/เอกสาร/ข้ามบิล ──
    Lens("L9_taxid_sum", "taxid_checksum", lens_taxid_checksum),
    Lens("L10_taxid_fmt", "taxid_format", lens_taxid_format),
    Lens("L17_taxid_xco", "taxid_crosscompany", lens_taxid_crosscompany),
    Lens("L18_dup_sig", "duplicate_signature", lens_duplicate_signature),
    Lens("L19_period", "period_match", lens_period_match),
    Lens("L20_doc_complete", "doc_completeness", lens_doc_completeness),
    Lens("L21_master", "master_known", lens_master_known),
    Lens("L22_iv_prefix", "iv_prefix_match", lens_iv_prefix_match),
    # ── เพิ่ม v9.2: ยอด/รายการ/ข้ามบิล มุมใหม่ ──
    Lens("L23_vat_zero", "vat_zero_exempt", lens_vat_zero_exempt),
    Lens("L24_item_count", "item_count_sanity", lens_item_count_sanity),
    Lens("L25_line_neg", "line_amount_negative", lens_line_amount_negative),
    Lens("L26_dup_line", "duplicate_line_in_bill", lens_duplicate_line_in_bill),
    Lens("L27_co_xtaxid", "company_multi_taxid", lens_company_multi_taxid),
    Lens("L28_total_lt_sub", "total_lt_subtotal", lens_total_lt_subtotal),
    Lens("L29_dec_scale", "decimal_scale_error", lens_decimal_scale_error),
    Lens("L30_vat_nobase", "vat_present_no_base", lens_vat_present_no_base),
    # ── เพิ่ม v9.2b: เวลา/งวด/รายการ มิติที่ยังบอด ──
    Lens("L31_future_date", "future_date", lens_future_date),
    Lens("L32_iv_period", "iv_period_conflict", lens_iv_period_conflict),
    Lens("L33_qty_neg", "qty_negative", lens_qty_negative),
    Lens("L34_sub_zero", "subtotal_zero_with_items", lens_subtotal_zero_with_items),
)


def lens_roster() -> List[Dict[str, str]]:
    """รายชื่อผู้ตรวจในคลัง (id + dimension) — ให้ report/notepad โชว์ 'ทีมตรวจ' ได้."""
    return [{"id": ln.id, "dimension": ln.dimension} for ln in INSPECTION_LENSES]


def _build_cross_index(bills: List[dict], master: Dict) -> Dict:
    """สร้างดัชนีข้ามบิล + ทะเบียน master 'ครั้งเดียว' (deterministic) ให้เลนส์อ่าน."""
    taxid_companies: Dict[str, set] = defaultdict(set)
    company_taxids: Dict[str, set] = defaultdict(set)  # L27: ชื่อบริษัท → เซ็ตเลขภาษี
    sig: Counter = Counter()
    for b in bills:
        try:
            tid = core.clean_tax_id(b.get("tax_id"))
        except Exception:
            tid = None
        s = "" if tid is None else str(tid)
        comp = (b.get("company") or "").strip()
        if len(s) == 13 and comp:
            taxid_companies[s].add(comp)
            company_taxids[comp].add(s)
        tot = _D(b.get("total"))
        if s and len(s) == 13 and tot is not None:
            sig[(s, str(_q2(tot)))] += 1

    master_taxids = set()
    master_iv_prefixes = set()
    for rec in (master or {}).values():
        if isinstance(rec, dict):
            try:
                mt = core.clean_tax_id(rec.get("tax_id"))
            except Exception:
                mt = None
            if mt:
                master_taxids.add(str(mt))
            pre = str(rec.get("iv_prefix") or "").strip()
            if pre:
                master_iv_prefixes.add(pre)
    return {
        "taxid_companies": {k: set(v) for k, v in taxid_companies.items()},
        "company_taxids": {k: set(v) for k, v in company_taxids.items()},
        "sig_taxid_total": dict(sig),
        "master_taxids": master_taxids,
        "master_iv_prefixes": master_iv_prefixes,
    }
