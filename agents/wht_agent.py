# -*- coding: utf-8 -*-
"""
agents/wht_agent.py — WHT Agent (Python ปกติ, advisory)

หน้าที่: ตรวจบิลที่น่าจะต้องหัก ณ ที่จ่าย 3% (ภงด.53) แต่ไม่เห็นการหัก
  ห่อฟังก์ชันเดิม `addon_check_withholding` (analytics.py) — logic เดิม 100%
  เดิมฟังก์ชันนี้เป็น add-on อยู่แล้ว (อ่านบิล ไม่แก้บิล) → ปลอดภัยโดยธรรมชาติ

ที่ agent เพิ่มให้: สัญญา/error-boundary/สรุป + แปลง candidate → Finding มาตรฐาน
ค่า rate/threshold/keywords มาจาก ADDON_CFG เดิมใน config.py (ไม่ตั้งใหม่)
"""
from __future__ import annotations

from . import core_access as core
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status


class WhtAgent(Agent):
    name = "wht"
    description = "ตรวจ ภงด.53 (หัก ณ ที่จ่าย 3%) — ห่อ addon_check_withholding เดิม"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        bills = ctx.bills or []

        fn = core.get("addon_check_withholding")
        if fn is None:
            # ฟังก์ชันเดิมไม่อยู่ (เช่น analytics.py ถูกตัด) → ข้ามอย่างชัดเจน ไม่พัง
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "addon_check_withholding ไม่พบใน core"})

        candidates = fn(bills) or []

        findings = []
        total_expected = 0.0
        for c in candidates:
            exp = float(c.get("expected_wht_3pct") or 0)
            total_expected += exp
            findings.append(Finding(
                agent=self.name, code="WHT-CANDIDATE",
                severity=c.get("severity", Severity.WARNING.value),
                message=c.get("note", "ตรวจ ภงด.53"),
                file=str(c.get("file", "")), sheet=str(c.get("sheet", "")),
                iv=str(c.get("iv", "-")),
                evidence={
                    "company": c.get("company", ""),
                    "service_subtotal": c.get("service_subtotal"),
                    "expected_wht_3pct": exp,
                    "service_items": c.get("service_items", ""),
                }))

        summary = {
            "bills": len(bills),
            "wht_candidates": len(candidates),
            "expected_wht_total": round(total_expected, 2),
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
