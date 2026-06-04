# -*- coding: utf-8 -*-
"""
agents/taxid_agent.py — TaxID Agent (Python ปกติ, advisory)

หน้าที่ (เจ้าของโดเมนเลขภาษี):
  1. รวบรวมผลตรวจที่เป็นทางการ (code ขึ้นต้น TAX* / BR*) ที่ rule engine แนบไว้ → สรุป
  2. ตรวจ checksum mod-11 อย่างอิสระด้วย `_taxid_checksum_ok` เดิม → ยืนยันซ้ำกับกฎ TAX006
  3. cross-bill: เลขภาษี "เดียวกัน" ปรากฏใต้ชื่อบริษัทต่างกัน (สัญญาณผิดพลาด/ปลอม)
     — เป็นการตรวจข้ามบิลที่ pipeline ต่อบิลทำไม่ได้ → คุณค่าเพิ่มจริงของ agent

⚠️ ไม่ mutate bills, ไม่รันกฎใหม่ — อ่านผลทางการ + ใช้ primitive เดิม (clean_tax_id/checksum)
"""
from __future__ import annotations

from collections import Counter, defaultdict

from . import core_access as core
from ._shared import max_severity as _max_sev
from .base import Agent, bill_ref, issues_with_prefix
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status

clean_tax_id = core.clean_tax_id
checksum_ok = core._taxid_checksum_ok


class TaxIdAgent(Agent):
    name = "taxid"
    description = "สรุปผลตรวจเลขภาษี/สาขา + checksum อิสระ + เลขซ้ำข้ามบริษัท"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        bills = ctx.bills or []
        findings = []
        code_counter = Counter()
        bills_with_tax_issue = 0
        n_checksum_fail = 0

        # map: tax_id (13 หลักล้วน) -> set ของชื่อบริษัทที่ใช้เลขนี้
        id_to_companies = defaultdict(set)
        id_to_refs = defaultdict(list)

        for b in bills:
            tax_issues = issues_with_prefix(b, "TAX", "BR")
            if tax_issues:
                bills_with_tax_issue += 1
                seen = set()
                for iss in tax_issues:
                    c = iss.get("code", "TAX?")
                    if c not in seen:
                        code_counter[c] += 1
                        seen.add(c)
                findings.append(Finding(
                    agent=self.name, code="TAXID-ISSUE", severity=_max_sev(tax_issues),
                    message="; ".join(f"{i.get('code')}: {i.get('detail','')[:50]}"
                                      for i in tax_issues[:3]),
                    evidence={"codes": sorted(seen)}, **bill_ref(b)))

            # checksum อิสระ (ยืนยันซ้ำ TAX006)
            tid = clean_tax_id(b.get("tax_id"))
            if tid and len(tid) == 13 and tid.isdigit():
                if not checksum_ok(tid):
                    n_checksum_fail += 1
                    # ออก finding เฉพาะถ้ากฎหลักไม่ได้ยิง TAX006 (กันซ้ำซ้อน)
                    if not any(i.get("code") == "TAX006" for i in tax_issues):
                        findings.append(Finding(
                            agent=self.name, code="TAXID-CHECKSUM", severity=Severity.ERROR.value,
                            message=f"checksum เลขภาษีไม่ผ่าน (mod-11): {tid}",
                            evidence={"tax_id": tid}, **bill_ref(b)))
                comp = (b.get("company") or "").strip()
                id_to_companies[tid].add(comp)
                id_to_refs[tid].append(bill_ref(b))

        # cross-bill: เลขเดียว หลายชื่อบริษัท
        n_id_multi_company = 0
        for tid, companies in id_to_companies.items():
            distinct = {c for c in companies if c}
            if len(distinct) > 1:
                n_id_multi_company += 1
                ref = id_to_refs[tid][0]
                findings.append(Finding(
                    agent=self.name, code="TAXID-MULTICOMPANY", severity=Severity.WARNING.value,
                    message=f"เลขภาษี {tid} ใช้กับ {len(distinct)} ชื่อบริษัทต่างกัน",
                    evidence={"tax_id": tid, "companies": sorted(distinct)[:6],
                              "bill_count": len(id_to_refs[tid])}, **ref))

        summary = {
            "bills": len(bills),
            "bills_with_tax_issue": bills_with_tax_issue,
            "tax_rule_hits": dict(code_counter),
            "checksum_fail": n_checksum_fail,
            "unique_tax_ids": len(id_to_companies),
            "tax_id_multi_company": n_id_multi_company,
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
