# -*- coding: utf-8 -*-
"""
agents/vendor_report.py — "รายงานลูกค้า" รายผู้ขาย (.txt) ภาษาคน พร้อมก๊อปส่งได้เลย

ฟีเจอร์ (additive): สร้าง .txt แยกทีละ vendor (1 ไฟล์ / 1 ผู้ขาย / แยกตามงวดเดือน) เป็น
  **output อีกอันข้าง Excel** — อ่านผล audit ที่ตกผลึกแล้ว (bills + issues + master)
  แล้ว map เข้า "ฟอร์มภาษาคน": field ไหนไม่มีปัญหา = "ตรง" ; มีปัญหา = อธิบายสั้น ๆ
  แบบคนพูด (อ้างไฟล์/ลำดับรายการ/หน่วย/วันที่ — ไม่มีศัพท์เทคนิค/โค้ดกฎ).

⚠️ ADVISORY/READ-ONLY: ไม่แตะ ctx.bills/ผลตรวจหลัก/Excel → ไม่กระทบ golden hash.
   โมดูลนี้ = ตรรกะจัดฟอร์แมตล้วน (pure, deterministic) ; การเขียนไฟล์อยู่ที่ VendorReportAgent.

ฟอร์แมต (ตามที่ผู้ใช้กำหนดในเอกสารตัวอย่าง):
  ─────────────
  {ลำดับ}.{ชื่อย่อ} {งวด YY.MM}
  ยอด : {รวมยอดก่อน VAT} บาท ตรง         ← ย้ำ: ก่อน VAT (ผลรวม subtotal ทุกบิลในงวด)
        (ถ้าไม่ตรง → "ยอดเงินในบิลรวม X บาท ยอด Diff Y บาท")
  บิล : {n} บิล ตรง                       ← นับเป็น "บิล" (รวมหน้าต่อแล้ว) ไม่ใช่ "ใบ/ชีต"
  ชื่อบจ. : ตรง / ไม่ตรง ...
  ที่อยู่ : ตรง / ไม่ตรง (ดูหมายเหตุท้าย)
  เลขที่ผู้เสียภาษี : ตรง / ไม่ตรง (ดูหมายเหตุท้าย)
  สาขา/สนญ. : ...
  เลขที่ : ...        วันที่ : ...      เลขที่ iv : ...      รายการสินค้า : ...
  ยอดหลัง Vat : ...   ยอดก่อน vat : ...
  {ชื่อเต็มบริษัท} {งวด MM/YY} {สรุปท้ายภาษาคน: "ตรงครับ" / "รีเช็ค ... และหมายเหตุนะครับผม"}
  หมายเหตุ : (เฉพาะเมื่อที่อยู่/เลขภาษีไม่ตรง — โชว์ master vs บิล + จุดต่าง ; + memo ถ้ามี)
  ─────────────
"""

from __future__ import annotations

from .vendor_report_base import (   # [de-star P2] เดิม `import *` — explicit (13 ชื่อใช้จริง; DIVIDER re-export ผ่าน __all__)
    DIVIDER, Dict, FIELD_LAYOUT, List, Optional, OrderedDict, Tuple,
    _find_master_entry, _full_company, _is_noise_issue, _match, _period,
    _safe_filename, _short_name,
)
from code_labels import MASTER_DEPENDENT_FIELDS, uncheckable_reason  # [A1] honesty 'ตรง'=เทียบ master จริง
from .vendor_report_ext import (   # [de-star P2] เดิม `import *` — explicit (8 helper ใช้จริง + _pre_vat re-export ให้เทส)
    _amount_line, _bill_count_line, _company_field, _group_by_vendor,
    _item_field_text, _natural_field_text, _note_blocks, _summary_sentence,
    _pre_vat,  # noqa: F401  re-export — test_vendor_report.py import ตรง (ไม่ใช้ภายในไฟล์นี้)
)


def _render_one(
    idx: int,
    vbills: List[dict],
    *,
    master: Optional[dict] = None,
    head_note: str = "",
    foot_note: str = "",
    memo: str = "",
) -> str:
    full = _full_company(vbills)
    short = _short_name(full)
    p_head, p_foot = _period(vbills)

    head = f"{idx}.{short}"
    if p_head:
        head += f" {p_head}"
    if head_note:
        head += f" {head_note}"

    lines: List[str] = [DIVIDER, head.rstrip()]
    lines.append(_amount_line(vbills))
    lines.append(_bill_count_line(vbills))

    field_ok: "OrderedDict[str, bool]" = OrderedDict()
    # ฟิลด์ที่อ้างอิง "หมายเหตุท้าย" (โชว์ค่า master vs บิล) — บรรทัดบนสั้น ๆ
    NOTE_FIELDS = {"ที่อยู่", "เลขที่ผู้เสียภาษี"}
    # [A1] honesty: ตัดสิน "เทียบ master ได้จริงไหม" ทีละผู้ขาย (หา record จากเลขภาษี/ชื่อ) — ใช้กับช่องตัวตน
    _ventry = _find_master_entry(vbills, master)
    _vmatched = _ventry is not None
    uncheckable: List[str] = []
    for label, spec in FIELD_LAYOUT:
        if label == "ชื่อบจ.":
            ok, text = _company_field(vbills, master)
        elif label in NOTE_FIELDS:
            has_issue = any(
                _match(i.get("code", ""), spec) and not _is_noise_issue(i)
                for b in vbills
                for i in (b.get("issues") or [])
            )
            ok = not has_issue
            text = "ตรง" if ok else "ไม่ตรง (ดูหมายเหตุท้าย)"
        elif label == "รายการสินค้า":
            text = _item_field_text(vbills)
            ok = text == "ตรง"
        elif label == "วันที่":
            ok, text = _natural_field_text(vbills, spec, with_date=True)
        else:
            ok, text = _natural_field_text(vbills, spec)
        # [A1] ช่องตัวตนที่ "ไม่มี issue (ดูเหมือนตรง)" แต่ไม่เคยเทียบ master จริง → 'ตรวจไม่ได้'
        #   (เลิกขึ้น 'ตรง' หลอก). 'ตรวจไม่ได้' เป็นสถานะที่สาม — ok คงเป็น True (ไม่เข้า 'รีเช็ค').
        if ok and label in MASTER_DEPENDENT_FIELDS:
            reason = uncheckable_reason(label, vbills, _vmatched, _ventry)
            if reason is not None:
                text = reason
                uncheckable.append(label)
        field_ok[label] = ok
        lines.append(f"{label} : {text}")

    notes = _note_blocks(vbills, master, field_ok)

    foot = full
    if p_foot:
        foot += f" {p_foot}"
    summary = _summary_sentence(field_ok, has_notes=bool(notes), uncheckable=uncheckable)
    foot += f" {summary}"
    if foot_note:
        foot += f" {foot_note}"
    lines.append(foot.rstrip())

    if notes or memo:
        lines.append("หมายเหตุ :")
        for nb in notes:
            lines.append("  " + nb)
        if memo:
            lines.append("  " + memo)

    lines.append(DIVIDER)
    return "\n".join(lines)


def build_vendor_reports(
    bills: List[dict],
    summary: Optional[list] = None,
    master: Optional[dict] = None,
    *,
    memo: str = "",
) -> List[Tuple[str, str]]:
    """สร้างรายงานลูกค้า .txt รายผู้ขาย (แยกงวดเดือน). คืน list ของ (filename, text) เรียง deterministic.

    filename = '{ลำดับ}.{ชื่อย่อ}.txt'  (ลำดับเริ่ม 1, เรียงยอดก่อน VAT มาก→น้อย).
    """
    out: List[Tuple[str, str]] = []
    for idx, (_key, vbills) in enumerate(_group_by_vendor(bills), start=1):
        text = _render_one(idx, vbills, master=master, memo=memo)
        base = f"{idx}.{_safe_filename(_short_name(_full_company(vbills)))}"
        # [L12] ลบ seen_fname ที่ไม่เคยถูกใช้ (idx นำหน้าทำให้ชื่อไม่ชนอยู่แล้ว)
        fname = f"{base}.txt"
        out.append((fname, text))
    return out


__all__ = ['DIVIDER', 'build_vendor_reports']
