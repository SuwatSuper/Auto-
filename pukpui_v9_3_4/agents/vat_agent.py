# -*- coding: utf-8 -*-
"""
agents/vat_agent.py — VAT Agent (Python ปกติ, advisory)

หน้าที่ (เจ้าของโดเมน VAT):
  1. รวบรวม "ผลตรวจ VAT ที่เป็นทางการ" (issue code ขึ้นต้น VAT*) ที่ rule engine หลักแนบไว้
     → สรุปว่ากฎ VAT ตัวไหนยิงกี่บิล แยกระดับความรุนแรง
  2. ตรวจ VAT-specific false-clean: บิลที่ VAT ถูก "เดาเอง" (derived) แต่ไม่มี issue VAT เลย
     → ธงให้คนตรวจ (เพราะกฎ VAT001/002/003 อาจผ่านเพราะยอดถูกเติมให้ balance)

⚠️ ไม่รันกฎเองใหม่ และไม่ mutate bills — อ่าน b['issues'] ที่ pipeline หลักตรวจแล้ว
   (การรันกฎแยกจะเปลี่ยนลำดับ issue → กระทบ Excel byte-identical) → ใช้ผลทางการเท่านั้น
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal

from . import core_access as core
from ._shared import max_severity
from .base import Agent, bill_ref, issues_with_prefix
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status

_D = core._D


class VatAgent(Agent):
    name = "vat"
    description = "สรุปผลตรวจ VAT (ทางการ) + ธง false-clean เฉพาะ VAT"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        bills = ctx.bills or []
        findings = []
        code_counter = Counter()       # VATxxx -> จำนวนบิลที่ยิง
        sev_counter = Counter()        # severity -> count
        bills_with_vat_issue = 0
        n_false_clean = 0

        for b in bills:
            vat_issues = issues_with_prefix(b, "VAT")
            if vat_issues:
                bills_with_vat_issue += 1
                seen = set()
                for iss in vat_issues:
                    c = iss.get("code", "VAT?")
                    if c not in seen:        # นับ "บิลที่ยิงกฎนี้" ไม่ใช่จำนวน issue
                        code_counter[c] += 1
                        seen.add(c)
                    sev_counter[iss.get("severity", "INFO")] += 1
                # surface เป็น finding (สรุปต่อบิล) เพื่อให้โผล่ใน agent review/AI
                findings.append(Finding(
                    agent=self.name, code="VAT-ISSUE", severity=max_severity(vat_issues),
                    message="; ".join(f"{i.get('code')}: {i.get('detail','')[:60]}"
                                      for i in vat_issues[:3]),
                    evidence={"codes": sorted(seen), "count": len(vat_issues)},
                    **bill_ref(b)))

            # false-clean เฉพาะ VAT: vat เป็น derived แต่ไม่มี issue VAT
            src = b.get("amount_source") or {}
            if src.get("vat") == "derived" and not vat_issues:
                vat = _D(b.get("vat"))
                if vat is not None and abs(vat) > Decimal("1.00"):
                    n_false_clean += 1
                    findings.append(Finding(
                        agent=self.name, code="VAT-FALSECLEAN", severity=Severity.WARNING.value,
                        message="VAT ผ่านกฎทั้งหมด แต่ยอด VAT ระบบคำนวณเอง — ควรยืนยันยอดบนเอกสาร",
                        evidence={"vat": float(vat), "amount_source": dict(src)},
                        **bill_ref(b)))

        summary = {
            "bills": len(bills),
            "bills_with_vat_issue": bills_with_vat_issue,
            "vat_rule_hits": dict(code_counter),
            "vat_issue_severity": dict(sev_counter),
            "false_clean_candidates": n_false_clean,
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
