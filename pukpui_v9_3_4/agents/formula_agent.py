# -*- coding: utf-8 -*-
"""
agents/formula_agent.py — Formula Agent (Python ปกติ, advisory)

หน้าที่: ตรวจ "ความสัมพันธ์ของยอดเงิน" อย่างเป็นอิสระ (independent recomputation)
  - sum(items) ≈ subtotal ?
  - subtotal × 7% ≈ vat ?
  - subtotal + vat ≈ total ?
  - ยอดที่ระบบ "เดาเอง" (provenance = derived) มีกี่บิล → ธงให้คนตรวจยอดบนเอกสารจริง

⚠️ READ-ONLY: ไม่แก้ b['subtotal']/b['vat']/b['total'] หรือ b['issues'] เลย
   → ผลตรวจหลัก/Excel เหมือนเดิม. ค่าที่ตรวจได้ไปอยู่ใน findings เท่านั้น

ทำไมจึง "แม่นขึ้น": นี่คือผู้ตรวจคนที่สอง (second opinion) ที่อ่านยอดแบบไม่ขึ้นกับ
parser — ช่วยจับเคสที่ยอดถูก "เติมให้ balance อัตโนมัติ" จนกฎ VAT มองว่าผ่าน (false-clean)
ซึ่งเป็นความเสี่ยงที่ระบบเดิมระบุไว้เองใน v9 (กฎ VAT010 ที่ถูกปิด)
"""
from __future__ import annotations

from decimal import Decimal

from . import core_access as core
from .base import Agent, bill_ref
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status

_D = core._D
_vat_tol = core._vat_tolerance
_SEVEN_PCT = Decimal("0.07")


def _num(b, key):
    return _D(b.get(key))


class FormulaAgent(Agent):
    name = "formula"
    description = "ตรวจความสัมพันธ์ยอดเงินอิสระ (sum/VAT/total) + provenance"
    critical = False   # advisory — พังแล้ว pipeline ไปต่อได้

    def _run(self, ctx: PipelineContext) -> AgentResult:
        bills = ctx.bills or []
        findings = []
        n_items_mismatch = n_vat_mismatch = n_total_mismatch = 0
        n_derived_sub = n_derived_vat = n_derived_total = 0
        n_checked = 0

        for b in bills:
            ref = bill_ref(b)
            src = b.get("amount_source") or {}
            if src.get("subtotal") == "derived":
                n_derived_sub += 1
            if src.get("vat") == "derived":
                n_derived_vat += 1
            if src.get("total") == "derived":
                n_derived_total += 1

            sub = _num(b, "subtotal")
            vat = _num(b, "vat")
            tot = _num(b, "total")

            # (1) ผลรวมรายการ ≈ subtotal
            items = b.get("items") or []
            item_vals = [_D(i.get("amount")) for i in items if i.get("amount") is not None]
            if item_vals and sub is not None:
                n_checked += 1
                s = sum(item_vals, Decimal("0"))
                diff = abs(s - sub)
                if diff > _vat_tol(sub):
                    n_items_mismatch += 1
                    findings.append(Finding(
                        agent=self.name, code="FORMULA-ITEMSUM", severity=Severity.WARNING.value,
                        message=f"ผลรวมรายการ {s:,.2f} ≠ subtotal {sub:,.2f} (ต่าง {diff:,.2f})",
                        evidence={"item_sum": float(s), "subtotal": float(sub),
                                  "diff": float(diff)}, **ref))

            # (2) subtotal × 7% ≈ vat  (ข้าม vat ที่เป็น rate ≤ 1.0 เหมือนกฎ VAT002)
            if sub is not None and vat is not None and abs(vat) > Decimal("1.00"):
                expected = (sub * _SEVEN_PCT).quantize(Decimal("0.01"))
                if abs(expected - vat) >= Decimal("1.00"):
                    n_vat_mismatch += 1
                    findings.append(Finding(
                        agent=self.name, code="FORMULA-VAT7", severity=Severity.WARNING.value,
                        message=f"VAT ควร ~{expected:,.2f} แต่ได้ {vat:,.2f}",
                        evidence={"subtotal": float(sub), "vat": float(vat),
                                  "expected_vat": float(expected)}, **ref))

            # (3) subtotal + vat ≈ total
            if sub is not None and tot is not None:
                v = vat if vat is not None else Decimal("0")
                expected_total = (sub + v).quantize(Decimal("0.01"))
                if abs(expected_total - tot) >= Decimal("1.00"):
                    n_total_mismatch += 1
                    findings.append(Finding(
                        agent=self.name, code="FORMULA-TOTAL", severity=Severity.WARNING.value,
                        message=f"subtotal+VAT ควร {expected_total:,.2f} แต่ total {tot:,.2f}",
                        evidence={"subtotal": float(sub), "vat": float(v),
                                  "total": float(tot), "expected_total": float(expected_total)},
                        **ref))

            # (4) ธง false-clean: ยอดสำคัญถูก derive (ไม่ได้อ่านจากเอกสารจริง)
            if src.get("subtotal") == "derived" or src.get("vat") == "derived":
                findings.append(Finding(
                    agent=self.name, code="FORMULA-DERIVED", severity=Severity.INFO.value,
                    message="ยอด subtotal/VAT บางส่วนระบบคำนวณเอง (ไม่ได้อ่านจากเอกสาร) — ควรตรวจยอดจริง",
                    evidence={"amount_source": dict(src),
                              "amount_confidence": b.get("amount_confidence")}, **ref))

        summary = {
            "bills": len(bills),
            "checked": n_checked,
            "itemsum_mismatch": n_items_mismatch,
            "vat7_mismatch": n_vat_mismatch,
            "total_mismatch": n_total_mismatch,
            "derived_subtotal": n_derived_sub,
            "derived_vat": n_derived_vat,
            "derived_total": n_derived_total,
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
