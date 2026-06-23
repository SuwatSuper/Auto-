# -*- coding: utf-8 -*-
"""
agents/synthesis_agent.py — SynthesisAgent (Tier-3 capstone, mesh consumer + Local LLM)

ตำแหน่งในลำดับชั้น (Hybrid Hierarchical + Mesh):
    Tier-1 (review อิสระ)  : formula / vat / wht / taxid     → publish findings เข้า mesh
    Tier-2 (correlation)   : crosscheck / confidence          → อ่าน mesh, เติมสัญญาณสังเคราะห์
    Tier-2.5 (triage)      : ai_review                          → จัด priority "รายบิล" + อธิบาย
    Tier-3 (synthesis) นี้ : synthesis                          → สรุป "ภาพรวมทั้งงานตรวจ" ★

ความต่างจาก ai_review (กันทำงานซ้ำ):
  - ai_review : มองทีละบิล — "บิลไหนควรดูก่อน + เพราะอะไร"
  - synthesis : มองทั้งชุดงาน — "ภาพรวมความเสี่ยงเป็นอย่างไร, รูปแบบปัญหาที่พบบ่อย,
                บริษัท/ไฟล์ใดน่ากังวลเชิงระบบ, ผู้บริหาร/หัวหน้าทีมควรโฟกัสอะไร"
  → นี่คือ 'สังเคราะห์ขั้นสุดท้าย' ตามที่ออกแบบ: รวมผลของทุก agent ใน mesh เป็นบทสรุปเดียว

ทำไมทำให้ "ฉลาดขึ้น":
  อ่าน mesh ที่ "ตกผลึกแล้ว" (รวม cross-confirm + confidence score ของ Tier-2) →
  เห็นว่าปัญหากระจุกที่ไหน, ชนิดใดเด่น, มีบิลที่หลายผู้ตรวจเห็นตรงกันกี่ใบ →
  ยกระดับจาก "รายการ findings" เป็น "ข้อสรุปเชิงบริหารที่ลงมือต่อได้"

⚠️ ADVISORY ONLY — ไม่แตะ ctx.bills/ผลตรวจหลัก. ผลอยู่ใน findings (AI-SYNTH-*) เท่านั้น.
   ไม่มี LLM / ต่อไม่ได้ → ยัง synthesize เชิงสถิติแบบ deterministic ได้ (degrade graceful).
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Dict, List

from ._shared import parse_llm_json
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status
from .llm_provider import make_provider


_SYSTEM_PROMPT = (
    "คุณคือหัวหน้าทีมผู้สอบบัญชี (audit lead) ภาษาไทย. ทีมของคุณ (เครื่องมืออัตโนมัติหลายตัว) "
    "ตรวจเอกสารชุดหนึ่งเสร็จแล้ว และส่ง 'สถิติภาพรวม' ของสิ่งที่พบมาให้คุณ. "
    "หน้าที่ของคุณคือเขียน 'บทสรุปเชิงบริหาร' สั้น กระชับ ให้หัวหน้างานเข้าใจภาพรวมความเสี่ยง "
    "และตัดสินใจได้ว่าควรทุ่มกำลังตรวจที่จุดใดก่อน\n\n"
    "ข้อห้ามเด็ดขาด:\n"
    "- ห้ามคำนวณยอดเงินใหม่ หรือตัดสินว่าบิลใด 'ผ่าน/ไม่ผ่าน' แทนกฎของระบบ\n"
    "- ห้ามแต่งตัวเลข/ข้อเท็จจริงที่ไม่มีใน input ที่ให้มา\n"
    "- ให้ได้เพียง 'บทสรุปเชิงตรวจทาน' ที่มนุษย์เป็นผู้ตัดสินใจสุดท้าย\n\n"
    "ตอบกลับเป็น JSON เท่านั้น ตาม schema:\n"
    '{"headline":"พาดหัว 1 ประโยค","overview":"ภาพรวม 2-4 ประโยค",'
    '"themes":["รูปแบบปัญหาที่พบบ่อย ..."],"focus":["จุดที่ควรตรวจก่อน ..."]}'
)


def _parse_llm_json(text: str) -> dict:
    """แกะ JSON จากคำตอบ LLM (คง raw text เป็น overview ถ้าแกะไม่ได้ — พฤติกรรมเดิม)."""
    return parse_llm_json(text, raw_fallback_key="overview")


def _build_overview(ctx: PipelineContext) -> Dict:
    """สังเคราะห์ 'ข้อมูลสถิติภาพรวม' จาก mesh (deterministic) — ใช้เป็น input ให้ LLM
    และเป็น fallback summary ถ้าไม่มี LLM. ตัวเลขทั้งหมดมาจาก findings ใน mesh เท่านั้น.
    """
    mesh = ctx.mesh
    overview: Dict = {
        "total_bills": len(ctx.bills or []),
        "total_findings": 0,
        "severity": {},
        "by_agent": {},
        "top_codes": [],
        "corroborated": [],   # บิลที่หลายผู้ตรวจอิสระเห็นตรงกัน
    }
    if mesh is None:
        return overview

    all_f: List[Finding] = mesh.all()
    overview["total_findings"] = len(all_f)

    # นับตามความรุนแรง
    sev_count = Counter(f.severity for f in all_f)
    overview["severity"] = {s: sev_count.get(s, 0)
                            for s in (Severity.CRITICAL.value, Severity.ERROR.value,
                                      Severity.WARNING.value, Severity.INFO.value)}

    # นับตาม agent (เรียงตามตัวอักษร — deterministic)
    by_agent = Counter(f.agent for f in all_f)
    overview["by_agent"] = {a: by_agent[a] for a in sorted(by_agent)}

    # code ที่พบบ่อยสุด (รูปแบบปัญหา) — เรียง (จำนวนมาก→น้อย, code ตามตัวอักษร)
    code_count = Counter(f.code for f in all_f)
    overview["top_codes"] = [
        {"code": c, "count": n}
        for c, n in sorted(code_count.items(), key=lambda x: (-x[1], x[0]))[:10]
    ]

    # cross-agent corroboration (หัวใจ mesh): บิลที่ >=2 agent ธงตรงกัน
    try:
        corr = mesh.correlate_by_bill(min_agents=2)
        overview["corroborated"] = [
            {"file": r["file"], "sheet": r["sheet"], "iv": r["iv"],
             "n_agents": r["n_agents"], "agents": r["agents"],
             "max_severity": r["max_severity"]}
            for r in corr[:15]
        ]
    except Exception:
        overview["corroborated"] = []

    return overview


class SynthesisAgent(Agent):
    name = "synthesis"
    description = "สังเคราะห์ภาพรวมทั้งงานตรวจจาก mesh (executive summary) — Local LLM + fallback สถิติ"
    critical = False   # advisory — ไม่มี LLM/พัง = pipeline ปกติ

    def _run(self, ctx: PipelineContext) -> AgentResult:
        overview = _build_overview(ctx)

        # ---------- กรณีปิด AI: สังเคราะห์เชิงสถิติแบบ deterministic ----------
        if not ctx.opt("enable_ai", False):
            return self._statistical_synthesis(ctx, overview,
                                               reason="ปิดใช้งาน AI (enable_ai=False) — ใช้สรุปสถิติแทน")

        provider = make_provider(ctx.options)
        if not provider.available():
            return self._statistical_synthesis(ctx, overview,
                                               reason="ต่อ Local LLM ไม่ได้ — ใช้สรุปสถิติแทน (degrade graceful)",
                                               provider=provider.info())

        # ---------- กรณีมี LLM: ให้สังเคราะห์เป็นบทสรุปเชิงบริหาร ----------
        user_prompt = (
            "นี่คือสถิติภาพรวมของผลตรวจเอกสารทั้งชุด (JSON) ที่ทีมเครื่องมือสรุปมา. "
            "ช่วยเขียนบทสรุปเชิงบริหารตาม schema ที่กำหนด:\n\n"
            + json.dumps(overview, ensure_ascii=False, indent=0)
        )
        # LLM call อาจล้มชั่วคราวแม้ probe ผ่าน → ตกไปใช้สรุปสถิติ (degrade graceful) ไม่ใช่ ERROR
        try:
            raw = provider.chat(_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            return self._statistical_synthesis(
                ctx, overview,
                reason=f"เรียก Local LLM ไม่สำเร็จ ({type(e).__name__}) — ใช้สรุปสถิติแทน",
                provider=provider.info())
        parsed = _parse_llm_json(raw)

        findings: List[Finding] = []
        headline = str(parsed.get("headline", "")).strip()[:300]
        body = str(parsed.get("overview", "")).strip()[:1200]
        if headline or body:
            findings.append(Finding(
                agent=self.name, code="AI-SYNTH-OVERVIEW", severity=Severity.INFO.value,
                message=(headline + (" — " if headline and body else "") + body)[:1400],
                evidence={"provider": provider.info(),
                          "stats": {"bills": overview["total_bills"],
                                    "findings": overview["total_findings"],
                                    "severity": overview["severity"]}}))

        for theme in (parsed.get("themes") or [])[:8]:
            if isinstance(theme, str) and theme.strip():
                findings.append(Finding(
                    agent=self.name, code="AI-SYNTH-THEME", severity=Severity.INFO.value,
                    message=theme.strip()[:300]))

        for foc in (parsed.get("focus") or [])[:8]:
            if isinstance(foc, str) and foc.strip():
                findings.append(Finding(
                    agent=self.name, code="AI-SYNTH-FOCUS", severity=Severity.WARNING.value,
                    message=foc.strip()[:300]))

        if not findings:
            # LLM ตอบแต่แกะไม่ได้ → ยังให้สรุปสถิติเป็นหลักประกัน
            return self._statistical_synthesis(ctx, overview,
                                               reason="LLM ตอบแต่แกะ JSON ไม่ได้ — ใช้สรุปสถิติแทน",
                                               provider=provider.info())

        summary = {
            "mode": "llm",
            "provider": provider.info(),
            "bills": overview["total_bills"],
            "findings_in_mesh": overview["total_findings"],
            "corroborated_bills": len(overview["corroborated"]),
            "themes": sum(1 for f in findings if f.code == "AI-SYNTH-THEME"),
            "focus": sum(1 for f in findings if f.code == "AI-SYNTH-FOCUS"),
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)

    # ---------- fallback: บทสรุปเชิงสถิติ (ไม่มี LLM ก็ยังมีประโยชน์) ----------
    def _statistical_synthesis(self, ctx: PipelineContext, overview: Dict,
                               reason: str, provider: dict = None) -> AgentResult:
        findings: List[Finding] = []
        sev = overview["severity"]
        n_corr = len(overview["corroborated"])

        # บทสรุปภาพรวมแบบ deterministic
        parts = [
            f"ตรวจ {overview['total_bills']} บิล พบข้อสังเกตรวม {overview['total_findings']} รายการ",
        ]
        sev_bits = [f"{k} {v}" for k, v in sev.items() if v]
        if sev_bits:
            parts.append("(" + ", ".join(sev_bits) + ")")
        if n_corr:
            parts.append(f"; มี {n_corr} บิลที่ผู้ตรวจหลายตัวเห็นตรงกัน (ควรดูก่อน)")
        findings.append(Finding(
            agent=self.name, code="AI-SYNTH-OVERVIEW", severity=Severity.INFO.value,
            message=" ".join(parts)[:1400],
            evidence={"severity": sev, "by_agent": overview["by_agent"],
                      "top_codes": overview["top_codes"]}))

        # รูปแบบปัญหาเด่น (จาก top_codes) → theme เชิงสถิติ
        for tc in overview["top_codes"][:5]:
            findings.append(Finding(
                agent=self.name, code="AI-SYNTH-THEME", severity=Severity.INFO.value,
                message=f"รูปแบบที่พบบ่อย: {tc['code']} ({tc['count']} ครั้ง)",
                evidence={"code": tc["code"], "count": tc["count"]}))

        # บิล cross-validated → focus (เชิง mesh: หลายผู้ตรวจเห็นตรงกัน)
        for c in overview["corroborated"][:8]:
            findings.append(Finding(
                agent=self.name, code="AI-SYNTH-FOCUS", severity=Severity.WARNING.value,
                message=(f"บิลนี้ถูกธงโดย {c['n_agents']} ผู้ตรวจ "
                         f"({', '.join(c['agents'])}) — ระดับสูงสุด {c['max_severity']}"),
                file=c["file"], sheet=c["sheet"], iv=c["iv"],
                evidence={"agents": c["agents"], "max_severity": c["max_severity"]}))

        summary = {
            "mode": "statistical",
            "reason": reason,
            "bills": overview["total_bills"],
            "findings_in_mesh": overview["total_findings"],
            "corroborated_bills": n_corr,
        }
        if provider:
            summary["provider"] = provider
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
