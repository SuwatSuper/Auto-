# -*- coding: utf-8 -*-
"""
agents/crosscheck_agent.py — CrossCheckAgent (Tier-2, mesh consumer)

ตำแหน่งในลำดับชั้น: รัน**หลัง** Tier-1 (formula/vat/wht/taxid) เพราะอ่านผลของพวกนั้นผ่าน mesh.
หน้าที่: หา "บิลที่ถูกหลาย agent ธงพร้อมกัน" = สัญญาณ cross-validated ความเชื่อมั่นสูง
        แล้วออก finding สรุป (CROSS-CONFIRM) ชี้ให้คนตรวจจุดที่ 'หลายมุมมองตรงกัน' ก่อน

ทำไมทำให้ "แม่นขึ้น":
  agent เดี่ยวธงเยอะ → คนตรวจล้น ไม่รู้เริ่มตรงไหน. แต่ถ้า VAT + Formula + TaxID
  ชี้บิลใบเดียวกัน → โอกาสเป็นปัญหาจริงสูงกว่ามาก (ลด false positive ในชั้นคำแนะนำ).
  นี่คือพลังของ mesh: รวมหลักฐานข้าม agent โดยไม่มีใครรันกฎซ้ำ.

⚠️ ADVISORY ONLY — อ่าน mesh อย่างเดียว, ไม่แตะ ctx.bills/ผลตรวจหลัก → Excel เหมือนเดิม.
   ไม่ critical (พัง = ข้าม, pipeline ปกติ).
"""
from __future__ import annotations

import mesh_contract

from ._shared import TIER1 as _TIER1   # [B6-FIX] แหล่งความจริงเดียว (เดิมก๊อปซ้ำ 4 ไฟล์)
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status

# Tier-1 ที่ถือว่าเป็น "ผู้ตรวจอิสระ" — การธงพร้อมกันจาก >=2 ใน set นี้ = สัญญาณแรง


class CrossCheckAgent(Agent):
    name = "crosscheck"
    description = "รวมผล Tier-1 ผ่าน mesh — ชี้บิลที่หลาย agent ธงพร้อมกัน (cross-validated)"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        mesh = ctx.mesh
        if mesh is None:
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "ไม่มี mesh (รันนอก orchestrator)"})

        # ── P2: ตรวจสัญญาผู้ผลิต Tier-1 ก่อนเชื่อผล correlation ──────────────
        #   ถ้าผู้ตรวจอิสระตัวใด "ไม่ได้รัน/ล้ม" → cross-confirm ที่ได้จะต่ำกว่าจริง (หลักฐานหาย).
        #   ยกธง MESH-CONTRACT (ERROR, ระดับ pipeline) ที่นี่ "ครั้งเดียว" (crosscheck = ผู้บริโภคตัวแรก).
        contract = mesh_contract.verify_producers(ctx.results, mesh, _TIER1)

        min_agents = int(ctx.opt("crosscheck_min_agents", 2))
        rows = mesh.correlate_by_bill(min_agents=min_agents)

        # สนใจเฉพาะการยืนยันข้ามจาก Tier-1 ผู้ตรวจอิสระ (ไม่นับ ai/confidence/crosscheck เอง)
        findings = []
        if not contract["ok"]:
            findings.append(Finding(
                agent=self.name, code="MESH-CONTRACT", severity=Severity.ERROR.value,
                message=mesh_contract.violation_message(contract),
                file="", sheet="", iv="",      # pipeline-level (ไม่ผูกบิลใบใด)
                evidence=mesh_contract.summary_dict(contract)))

        confirmed = 0
        for r in rows:
            tier1_agents = [a for a in r["agents"] if a in _TIER1]
            if len(tier1_agents) < min_agents:
                continue
            confirmed += 1
            # severity ของ cross-confirm = ยกตาม max ของหลักฐาน แต่ไม่ต่ำกว่า WARNING
            sev = r["max_severity"]
            if sev == Severity.INFO.value:
                sev = Severity.WARNING.value
            findings.append(Finding(
                agent=self.name, code="CROSS-CONFIRM", severity=sev,
                message=(f"บิลนี้ถูกธงโดย {len(tier1_agents)} ผู้ตรวจอิสระพร้อมกัน "
                         f"({', '.join(tier1_agents)}) — ความเชื่อมั่นสูง ควรตรวจก่อน"),
                file=r["file"], sheet=r["sheet"], iv=r["iv"],
                evidence={
                    "agents": tier1_agents,
                    "n_tier1_agents": len(tier1_agents),
                    "codes": r["codes"],
                    "max_severity": r["max_severity"],
                }))

        summary = {
            "min_agents": min_agents,
            "bills_cross_confirmed": confirmed,
            "mesh_total_findings": mesh.count(),
            "tier1_considered": list(_TIER1),
            "tier1_contract": mesh_contract.summary_dict(contract),
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
