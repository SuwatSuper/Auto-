# -*- coding: utf-8 -*-
"""
agents/confidence_agent.py — ConfidenceAgent (Tier-2, mesh consumer)

ตำแหน่ง: รันหลัง Tier-1 + CrossCheck (อ่าน mesh ที่สะสม findings ครบแล้ว).
หน้าที่: ให้ "คะแนนความเชื่อมั่นรวม" ต่อบิล โดยถ่วงน้ำหนักหลักฐานจากหลายแหล่งใน mesh
        + ความเชื่อมั่นจาก parser (amount_confidence) → จัดอันดับว่าบิลใด "น่ากังวลสุด".

ทำไมทำให้ "ฉลาดขึ้น":
  เดิมแต่ละ finding แยกกัน คนต้องรวมหัวเอง. ConfidenceAgent สังเคราะห์เป็น 'คะแนนเดียว/บิล'
  ที่เทียบกันได้ → จัดลำดับงานตรวจได้ทันที. คะแนนนี้ยังเป็น input ให้ AI สังเคราะห์ขั้นสุดท้าย.

สูตรคะแนน (โปร่งใส ตามรอยได้ — ไม่ใช่กล่องดำ):
  risk = Σ severity_weight(finding)  +  bonus ตามจำนวน agent อิสระที่ธง  +  low-parser-confidence
  แล้ว normalize เป็น 0..100 (เชิงอันดับ ไม่ใช่ความน่าจะเป็นเชิงสถิติ).

⚠️ ADVISORY ONLY — ไม่แตะ ctx.bills/ผลตรวจหลัก. คะแนนอยู่ใน finding (CONF-SCORE) เท่านั้น.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict

import mesh_contract

from ._shared import bill_key as _bkey
from ._shared import TIER1 as _TIER1   # [B6-FIX] แหล่งความจริงเดียว (เดิมก๊อปซ้ำ 4 ไฟล์)
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status

_SEV_WEIGHT = {"CRITICAL": 10, "ERROR": 6, "WARNING": 3, "INFO": 1}


class ConfidenceAgent(Agent):
    name = "confidence"
    description = "ให้คะแนนความเชื่อมั่นรวมต่อบิลจากหลักฐานทั้ง mesh (จัดอันดับงานตรวจ)"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        mesh = ctx.mesh
        if mesh is None:
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "ไม่มี mesh (รันนอก orchestrator)"})

        # P2: สุขภาพสัญญาผู้ผลิต Tier-1 (ไม่ออก finding ซ้ำ — crosscheck ยกธงแล้ว;
        #     บันทึกในสรุปเพื่อให้ "ตีความคะแนน" ได้ว่าคะแนนต่ำเพราะหลักฐานหายหรือบิลสะอาด)
        _contract = mesh_contract.verify_producers(ctx.results, mesh, _TIER1)

        # parser confidence ต่อบิล (file|sheet|iv → 'low' ?) เพื่อบวกน้ำหนัก
        low_conf_bills = set()
        for b in (ctx.bills or []):
            if b.get("amount_confidence") == "low":
                # [A-M1 2026-06-20] ต้อง key ด้วย iv_number_raw ก่อน (เหมือน bill_ref/f.iv ที่ mesh ใช้)
                #   เดิมใช้ iv_number (normalize ตัด '-') → ไม่ตรงกับ f.iv (raw เช่น 'IV6801-0001') →
                #   โบนัส low-confidence (+3) "ไม่เคยถูกบวก" กับบิลใด ๆ ที่ raw≠normalize (= สัญญาณตาย).
                k = _bkey(b.get("file", ""), b.get("sheet", ""),
                          b.get("iv_number_raw") or b.get("iv_number") or "-")
                low_conf_bills.add(k)

        # รวมหลักฐานต่อบิลจาก mesh (ไม่นับ finding ของ confidence เอง กัน feedback loop)
        per_bill_raw: Dict[str, float] = defaultdict(float)
        per_bill_agents: Dict[str, set] = defaultdict(set)
        per_bill_codes: Dict[str, set] = defaultdict(set)
        per_bill_ref: Dict[str, tuple] = {}    # key -> (file,sheet,iv) ต้นฉบับ (กัน split เพี้ยน)
        for f in mesh.all():
            if f.agent == self.name:
                continue
            bkey = _bkey(f.file, f.sheet, f.iv)
            per_bill_raw[bkey] += _SEV_WEIGHT.get(f.severity, 1)
            per_bill_agents[bkey].add(f.agent)
            per_bill_codes[bkey].add(f.code)
            per_bill_ref.setdefault(bkey, (f.file, f.sheet, f.iv))

        # บวกน้ำหนัก: จำนวน Tier-1 อิสระที่ธง (ยิ่งหลาย = ยิ่งมั่นใจ) + parser low-conf
        for bkey in list(per_bill_raw.keys()):
            n_tier1 = len(per_bill_agents[bkey] & set(_TIER1))
            if n_tier1 >= 2:
                per_bill_raw[bkey] += (n_tier1 - 1) * 4   # โบนัส cross-validation
            if bkey in low_conf_bills:
                per_bill_raw[bkey] += 3

        if not per_bill_raw:
            return AgentResult(self.name, Status.OK.value,
                               summary={"reason": "ไม่มีหลักฐานใน mesh ให้ให้คะแนน",
                                        "scored_bills": 0,
                                        "tier1_contract": mesh_contract.summary_dict(_contract)})

        # normalize → 0..100 (เชิงอันดับ): หารด้วย max แล้วคูณ 100
        max_raw = max(per_bill_raw.values()) or 1.0
        # ออก finding เฉพาะบิลที่คะแนนเด่น (ตัด noise) — ใช้ threshold ปรับได้
        top_pct = float(ctx.opt("confidence_min_score", 40))  # 0..100

        scored = []
        for bkey, raw in per_bill_raw.items():
            score = round(raw / max_raw * 100, 1)
            scored.append((score, bkey, raw))
        # เรียงคะแนนสูง→ต่ำ, แล้ว bkey (deterministic)
        scored.sort(key=lambda x: (-x[0], x[1]))

        findings = []
        for score, bkey, raw in scored:
            if score < top_pct:
                continue
            file, sheet, iv = per_bill_ref.get(bkey, (bkey, "", ""))
            agents = sorted(per_bill_agents[bkey])
            sev = (Severity.CRITICAL.value if score >= 80 else
                   Severity.ERROR.value if score >= 60 else
                   Severity.WARNING.value)
            findings.append(Finding(
                agent=self.name, code="CONF-SCORE", severity=sev,
                message=(f"คะแนนความเชื่อมั่นความเสี่ยง {score}/100 "
                         f"(หลักฐานจาก {len(agents)} แหล่ง: {', '.join(agents)})"),
                file=file, sheet=sheet, iv=iv,
                evidence={
                    "risk_score": score,
                    "raw_weight": round(raw, 1),
                    "agents": agents,
                    "codes": sorted(per_bill_codes[bkey]),
                }))

        summary = {
            "scored_bills": len(per_bill_raw),
            "flagged_bills": len(findings),
            "max_raw_weight": round(max_raw, 1),
            "min_score_threshold": top_pct,
            "tier1_contract": mesh_contract.summary_dict(_contract),
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
