# -*- coding: utf-8 -*-
"""
agents/vendor_report.py — "รายงานลูกค้า" รายผู้ขาย (.txt) ภาษาคน พร้อมก๊อปส่งได้เลย

ฟีเจอร์เพิ่ม (additive): สร้าง .txt แยกทีละ vendor เป็น **output อีกอันข้าง Excel**
  — อ่านผล audit ที่รันเสร็จแล้ว (bills + issues) map เข้า "ฟอร์มภาษาคน" ที่ field ไหนผ่าน = "ตรง"
  ไม่ผ่าน = อธิบายสั้น ๆ ภาษาคน (ไม่มีศัพท์เทคนิค/โค้ดกฎ).

⚠️ ADVISORY/READ-ONLY: ไม่แตะ ctx.bills/ผลตรวจหลัก/Excel → ไม่กระทบ golden hash.
   โมดูลนี้ = ตรรกะการจัดฟอร์แมตล้วน (pure) ; การเขียนไฟล์อยู่ที่ VendorReportAgent.

ฟอร์แมต (ตามที่ผู้ใช้กำหนด):
  ─────────────
  {ลำดับ}.{ชื่อย่อ} {งวด} {หมายเหตุหัว?}
  ยอด : {รวมยอด} บาท
  บิล : {n} บิล
  ชื่อบจ. : ตรง / ...
  ... (10 ช่อง map จากกฎ) ...
  {ชื่อเต็มบริษัท} {งวด} {สรุปท้าย?}
  หมายเหตุ : {memo?}
  ─────────────
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from . import core_access as core

DIVIDER = "─" * 31

# ── ผังช่อง (label, โค้ดกฎที่เกี่ยวข้อง) — map ผลกฎ → ช่องภาษาคน ──────────────
#   ค่าใน tuple: ถ้าลงท้ายด้วยตัวเลข = จับ "ตรงตัว" (เช่น VAT002) ; ไม่งั้น = จับ prefix (เช่น TAX → TAX001..)
FIELD_LAYOUT: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("ชื่อบจ.", ("CMP",)),
    ("ที่อยู่", ("ADDR",)),
    ("เลขที่ผู้เสียภาษี", ("TAX",)),
    ("สาขา/สนญ.", ("BR",)),
    ("เลขที่", ("DOC002", "DOC003")),
    ("วันที่", ("DOC001", "DT")),
    ("เลขที่ iv", ("IV", "SEQ")),
    ("รายการสินค้า", ("ITM",)),
    ("ยอดหลัง Vat", ("VAT002", "VAT003", "VAT004", "VAT007")),
    ("ยอดก่อน vat", ("VAT001", "VAT005", "VAT006", "VAT008", "VAT009")),
)

# prefix นิติบุคคล/คำนำหน้า ที่ตัดออกตอนทำ "ชื่อย่อ"
_NAME_PREFIXES = (
    "บริษัท",
    "ห้างหุ้นส่วนจำกัด",
    "ห้างหุ้นส่วนสามัญ",
    "บจก.",
    "บมจ.",
    "หจก.",
    "ร้าน",
    "กิจการร่วมค้า",
)
_CODE_RE = re.compile(
    r"\b[A-Z]{2,4}\d{2,3}\b"
)  # โค้ดกฎ เช่น VAT002 — ตัดออกจากข้อความคน
_FNAME_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]+')  # อักขระต้องห้ามในชื่อไฟล์


# ── helpers ──────────────────────────────────────────────────────────────────
def _num(x) -> float:
    """แปลงค่าเป็น float อย่างทน (None/ขยะ → 0.0) ผ่าน _D ของ core."""
    try:
        d = core._D(x)
        return float(d) if d is not None else 0.0
    except Exception:
        return 0.0


def _base(code: str) -> str:
    return str(code or "").split("-")[0].strip().upper()


def _match(code: str, spec: Tuple[str, ...]) -> bool:
    """code เข้ากับช่องนี้ไหม. spec ที่ลงท้ายตัวเลข = ตรงตัว ; ไม่งั้น = prefix."""
    b = _base(code)
    if not b:
        return False
    for s in spec:
        if s and s[-1].isdigit():
            if b == s:
                return True
        elif b.startswith(s):
            return True
    return False


def _vendor_key(b: dict) -> str:
    """กุญแจจัดกลุ่มผู้ขาย: เลขภาษี 13 หลัก (ถ้ามี) ไม่งั้นชื่อบริษัท."""
    try:
        tid = core.clean_tax_id(b.get("tax_id"))
    except Exception:
        tid = None
    if tid and len(str(tid)) == 13:
        return str(tid)
    comp = (b.get("company") or "").strip()
    return comp or "(ไม่ระบุผู้ขาย)"


def _short_name(company: str) -> str:
    """ชื่อย่อสำหรับหัวรายงาน/ชื่อไฟล์: ตัดคำนำหน้านิติบุคคล + 'จำกัด' + วงเล็บท้าย."""
    s = (company or "").strip()
    for p in sorted(_NAME_PREFIXES, key=len, reverse=True):
        if s.startswith(p):
            s = s[len(p) :].strip()
            break
    s = re.sub(r"\s*\(.*?\)\s*$", "", s)  # ตัด (สำนักงานใหญ่) ฯลฯ ท้าย
    s = re.sub(r"จำกัด\s*$", "", s).strip()
    return s or (company or "ผู้ขาย").strip()


def _safe_filename(s: str) -> str:
    return _FNAME_BAD.sub("", (s or "")).strip().replace(" ", "")[:60] or "vendor"


def _clean_human(text: str) -> str:
    """ทำข้อความให้เป็น 'ภาษาคน': ตัดโค้ดกฎออก + ยุบช่องว่าง."""
    t = _CODE_RE.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", t).strip(" :-")


def _period(vbills: List[dict]) -> Tuple[str, str]:
    """งวดบัญชีที่พบบ่อยสุด → ('YY.MM' สำหรับหัว, 'MM/YY' สำหรับท้าย). พ.ศ. 2 หลัก."""
    yms: List[Tuple[int, int]] = []
    for b in vbills:
        d = b.get("iv_date")
        if d is not None and hasattr(d, "year") and hasattr(d, "month"):
            be = d.year + 543 if d.year < 2500 else d.year
            yms.append((be % 100, d.month))
    if not yms:
        return "", ""
    (yy, mm), _ = Counter(yms).most_common(1)[0]
    return f"{yy:02d}.{mm:02d}", f"{mm:02d}/{yy:02d}"


def _full_company(vbills: List[dict]) -> str:
    names = [
        (b.get("company") or "").strip()
        for b in vbills
        if (b.get("company") or "").strip()
    ]
    if not names:
        return "(ไม่ระบุชื่อบริษัท)"
    return Counter(names).most_common(1)[0][0]


def _field_status(vbills: List[dict], spec: Tuple[str, ...]) -> str:
    """คืน 'ตรง' ถ้าไม่มี issue ในช่องนี้ ; ไม่งั้นอธิบายสั้น ๆ ภาษาคน (ไม่มีโค้ด)."""
    affected = 0
    for b in vbills:
        if any(_match(iss.get("code", ""), spec) for iss in (b.get("issues") or [])):
            affected += 1
    if affected == 0:
        return "ตรง"
    return f"ควรรีเช็ค {affected} บิลครับ"


def _group_by_vendor(bills: List[dict]) -> List[Tuple[str, List[dict]]]:
    """จัดกลุ่มบิลตามผู้ขาย แล้วเรียง deterministic ด้วยยอดรวมมาก→น้อย (เท่ากันตัดด้วยชื่อ)."""
    groups: Dict[str, List[dict]] = {}
    for b in bills or []:
        groups.setdefault(_vendor_key(b), []).append(b)

    def _sort_key(item):
        key, vb = item
        total = sum(_num(b.get("total")) for b in vb)
        return (-total, _full_company(vb), key)

    return sorted(groups.items(), key=_sort_key)


# ── render ───────────────────────────────────────────────────────────────────
def _render_one(
    idx: int,
    vbills: List[dict],
    *,
    head_note: str = "",
    foot_note: str = "",
    memo: str = "",
) -> str:
    full = _full_company(vbills)
    short = _short_name(full)
    p_head, p_foot = _period(vbills)
    total_sum = sum(_num(b.get("total")) for b in vbills)

    head = f"{idx}.{short}"
    if p_head:
        head += f" {p_head}"
    if head_note:
        head += f" {head_note}"

    lines: List[str] = [DIVIDER, head.rstrip()]
    lines.append(f"ยอด : {total_sum:,.2f} บาท")
    lines.append(f"บิล : {len(vbills)} บิล")
    for label, spec in FIELD_LAYOUT:
        lines.append(f"{label} : {_field_status(vbills, spec)}")

    foot = full
    if p_foot:
        foot += f" {p_foot}"
    if foot_note:
        foot += f" {foot_note}"
    lines.append(foot.rstrip())
    if memo:
        lines.append(f"หมายเหตุ : {memo}")
    lines.append(DIVIDER)
    return "\n".join(lines)


def build_vendor_reports(
    bills: List[dict],
    summary: Optional[list] = None,
    master: Optional[dict] = None,
    *,
    memo: str = "",
) -> List[Tuple[str, str]]:
    """สร้างรายงานลูกค้า .txt รายผู้ขาย. คืน list ของ (filename, text) เรียง deterministic.

    filename = '{ลำดับ}.{ชื่อย่อ}.txt'  (ลำดับเริ่ม 1, เรียงยอดมาก→น้อย).
    """
    out: List[Tuple[str, str]] = []
    for idx, (_key, vbills) in enumerate(_group_by_vendor(bills), start=1):
        text = _render_one(idx, vbills, memo=memo)
        fname = f"{idx}.{_safe_filename(_short_name(_full_company(vbills)))}.txt"
        out.append((fname, text))
    return out
