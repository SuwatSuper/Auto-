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
from .verification_lenses_base import (   # [de-star P2] เดิม `import *` — explicit (= __all__ ของ _base เป๊ะ; re-export ครบ)
    Counter, defaultdict, dataclass, field, Decimal, ROUND_HALF_UP,
    Callable, Dict, List, Tuple, core, parse_llm_json,
    _D, _HIGH_PRECISION, _HEURISTIC, _MONEY_PREFIXES, _VAT_RATE,
    _VAT_ROUND_TOL, _MONEY_TOL, _ROUND_BAHT, _is_money_issue, _q2,
    LensInput, Lens,
)
from .verification_lenses_ext import (   # [de-star P2] เดิม `import *` — explicit (= __all__ ของ _ext เป๊ะ; เลนส์กลุ่ม B re-export ให้ registry/เทส)
    lens_amount_completeness, lens_money_triple, lens_line_sum_amount,
    lens_line_qty_price, lens_negative_sanity, lens_magnitude_outlier,
    lens_taxid_checksum, lens_taxid_format, lens_taxid_crosscompany,
    lens_duplicate_signature, lens_period_match, lens_doc_completeness,
    lens_master_known, lens_iv_prefix_match, lens_vat_zero_exempt,
    lens_item_count_sanity, lens_line_amount_negative, lens_duplicate_line_in_bill,
    lens_company_multi_taxid, lens_total_lt_subtotal, lens_decimal_scale_error,
    lens_vat_present_no_base, lens_future_date, lens_iv_period_conflict,
    lens_qty_negative, lens_subtotal_zero_with_items,
)

# ── [de-star P2] public re-export surface ของ hub นี้ ──
#   เดิม `import *` 2 ตัวบัง surface ไว้ implicit + ทำ F405 ทุก use-site. ตอน de-star
#   เป็น explicit (= __all__ ของ _base/_ext เป๊ะ) → `__all__` นี้ = สิ่งที่ re-export ออก
#   (infra จาก _base + เลนส์กลุ่ม B จาก _ext + เลนส์/ทะเบียนที่นิยามในไฟล์นี้เอง)
#   ทำให้ (1) consumer (verification_agent/เทส) เห็นชื่อครบเหมือนเดิม (2) ดับ F401 เทียม
__all__ = [
    # infra re-export (จาก _base — คงพฤติกรรม star เดิม)
    "Counter", "defaultdict", "dataclass", "field", "Decimal", "ROUND_HALF_UP",
    "Callable", "Dict", "List", "Tuple", "core", "parse_llm_json",
    "_D", "_HIGH_PRECISION", "_HEURISTIC", "_MONEY_PREFIXES", "_VAT_RATE",
    "_VAT_ROUND_TOL", "_MONEY_TOL", "_ROUND_BAHT", "_is_money_issue", "_q2",
    "LensInput", "Lens",
    # เลนส์กลุ่ม B (จาก _ext)
    "lens_amount_completeness", "lens_money_triple", "lens_line_sum_amount",
    "lens_line_qty_price", "lens_negative_sanity", "lens_magnitude_outlier",
    "lens_taxid_checksum", "lens_taxid_format", "lens_taxid_crosscompany",
    "lens_duplicate_signature", "lens_period_match", "lens_doc_completeness",
    "lens_master_known", "lens_iv_prefix_match", "lens_vat_zero_exempt",
    "lens_item_count_sanity", "lens_line_amount_negative", "lens_duplicate_line_in_bill",
    "lens_company_multi_taxid", "lens_total_lt_subtotal", "lens_decimal_scale_error",
    "lens_vat_present_no_base", "lens_future_date", "lens_iv_period_conflict",
    "lens_qty_negative", "lens_subtotal_zero_with_items",
    # เลนส์/ทะเบียน/ตัวช่วย ที่นิยามในไฟล์นี้เอง
    "lens_recompute", "lens_provenance", "lens_confidence", "lens_peer",
    "lens_ruleclass", "lens_llm", "lens_rounding_explains", "lens_vat_7pct_exact",
    "lens_roster", "_build_cross_index", "INSPECTION_LENSES",
]


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
            sub, vat, tot = (_D(b.get("subtotal")), _D(b.get("vat")), _D(b.get("total")))
            # [A4-FIX] เดิม `_D(vat) or Decimal("0")` ปน "vat=0 จริง" กับ "vat อ่านไม่ออก (None)"
            #   → ถ้า vat อ่านไม่ออกจะถูกตีเป็น 0 แล้วอาจสร้าง/ซ่อน 'sub+vat≠total' ผิด.
            #   precision-first: ข้อมูลไม่ครบ → abstain (ไม่โหวต).
            if sub is None or tot is None or vat is None:
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
