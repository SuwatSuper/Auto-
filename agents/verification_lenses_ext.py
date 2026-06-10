# -*- coding: utf-8 -*-
"""agents/verification_lenses_ext.py — [F4 split] เลนส์กลุ่ม B (byte-identical extract)
ย้ายฟังก์ชัน lens_* ชุดหลังมาจาก verification_lenses.py เพื่อให้แต่ละไฟล์ ≤600 LOC.
infra ทั้งหมดมาจาก _base (รวมชื่อ _underscore ผ่าน __all__ ของ base)."""
from __future__ import annotations
from .verification_lenses_base import (   # [de-star P2] เดิม `import *` — explicit (10 ชื่อที่ _ext ใช้จริง; _ext.__all__ ไม่ re-export base)
    Decimal, Dict, LensInput, Tuple,
    _D, _MONEY_TOL, _ROUND_BAHT, _is_money_issue, _q2, core,
)

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
    # [M5] file_info.year เก็บเป็น พ.ศ. (parser_p0a: 2500+y / y+543) แต่ iv_date.year เป็น ค.ศ.
    #   เดิมเทียบตรง ๆ → 2026 != 2569 จริงเสมอ → โหวต "ไม่ตรงปี" เกือบทุกบิล. normalize ก่อนเทียบ.
    ce_yr = yr - 543 if yr > 2400 else yr
    if dt.year != ce_yr:
        return 1, f"ปีในใบ ({dt.year}) ไม่ตรงงวดไฟล์ ({ce_yr})"
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

__all__ = [
    'lens_amount_completeness',
    'lens_money_triple',
    'lens_line_sum_amount',
    'lens_line_qty_price',
    'lens_negative_sanity',
    'lens_magnitude_outlier',
    'lens_taxid_checksum',
    'lens_taxid_format',
    'lens_taxid_crosscompany',
    'lens_duplicate_signature',
    'lens_period_match',
    'lens_doc_completeness',
    'lens_master_known',
    'lens_iv_prefix_match',
    'lens_vat_zero_exempt',
    'lens_item_count_sanity',
    'lens_line_amount_negative',
    'lens_duplicate_line_in_bill',
    'lens_company_multi_taxid',
    'lens_total_lt_subtotal',
    'lens_decimal_scale_error',
    'lens_vat_present_no_base',
    'lens_future_date',
    'lens_iv_period_conflict',
    'lens_qty_negative',
    'lens_subtotal_zero_with_items',
]
