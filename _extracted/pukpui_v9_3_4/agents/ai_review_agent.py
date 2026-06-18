# -*- coding: utf-8 -*-
"""
agents/ai_review_agent.py — AI Review Agent (Local LLM, advisory เท่านั้น)

หน้าที่: เป็น "ผู้ตรวจคนที่สอง" ที่ใช้ Local LLM ช่วย *จัดลำดับความสำคัญ + อธิบาย*
  รายการที่ agent ฝั่ง Python ธงไว้ (formula/vat/wht/taxid) + บิลที่ความเชื่อมั่นต่ำ
  เพื่อชี้ให้ "คน" ไปตรวจจุดเสี่ยงสูงก่อน

⚠️ สัญญาเหล็ก (ทำให้ผล Excel เหมือนเดิม + ปลอดภัย):
  1. ADVISORY ONLY — ไม่แก้ ctx.bills, ไม่แก้ผลตรวจ, ไม่แตะ Excel หลัก
     ผลของ LLM ออกเป็น findings (AI-*) และไฟล์ review แยกต่างหากเท่านั้น
  2. LLM "ห้ามคำนวณยอด/ตัดสินผ่าน-ไม่ผ่านแทนกฎ" — ทำได้แค่ triage/อธิบาย
  3. degrade graceful — ถ้าไม่มี LLM (probe ไม่ผ่าน) → status=skipped, pipeline ปกติ
  4. output ของ LLM = ข้อความที่ไม่เชื่อถือ (untrusted) → parse แบบกันพัง, เก็บเป็น "หมายเหตุ"
  5. prompt ถูกจำกัดขนาด (เฉพาะรายการที่ถูกธง ไม่ dump ทุกบิล)
"""
from __future__ import annotations

import json

from ._shared import SEV_RANK as _RANK, parse_llm_json
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status
from .llm_provider import make_provider

_SYSTEM_PROMPT = (
    "คุณคือผู้ช่วยผู้สอบบัญชี (audit assistant) ภาษาไทย หน้าที่ของคุณคือ "
    "ช่วย 'จัดลำดับความสำคัญ' และ 'อธิบายสั้น ๆ' ของรายการที่ระบบตรวจสอบอัตโนมัติ "
    "ได้ธงไว้แล้ว เพื่อให้ผู้สอบบัญชีที่เป็นมนุษย์ไปตรวจจุดเสี่ยงสูงก่อน\n\n"
    "ข้อห้ามเด็ดขาด:\n"
    "- ห้ามคำนวณยอดเงินใหม่ หรือสรุปว่าบิลใด 'ผ่าน/ไม่ผ่าน' แทนกฎของระบบ\n"
    "- ห้ามแต่งข้อมูลที่ไม่มีใน input\n"
    "- คุณให้ได้เพียง 'คำแนะนำเชิงตรวจทาน' ที่มนุษย์เป็นผู้ตัดสินใจสุดท้าย\n\n"
    "ตอบกลับเป็น JSON เท่านั้น ตาม schema:\n"
    '{"summary":"...","prioritized":[{"file":"..","iv":"..","why":"..",'
    '"severity":"CRITICAL|ERROR|WARNING|INFO","recommended_action":".."}]}'
)


def _collect_candidates(ctx: PipelineContext, max_items: int) -> list:
    """รวบรวมรายการที่ควรให้ LLM ช่วย triage — อ่านจาก **mesh** (data plane) เป็นหลัก.

    ลำดับความสำคัญ (ทำให้ AI สังเคราะห์ขั้นสุดท้ายได้ฉลาดขึ้น):
      1) CROSS-CONFIRM / CONF-SCORE จาก Tier-2 (cross-validated) — มาก่อนเสมอ
      2) findings ของ Tier-1 (formula/vat/wht/taxid)
      3) บิลความเชื่อมั่นต่ำจาก parser
    ถ้าไม่มี mesh (รันนอก orchestrator) → fallback อ่าน ctx.results แบบเดิม (ไม่พัง).
    """
    cands = []
    mesh = ctx.mesh

    if mesh is not None:
        # 1) สัญญาณสังเคราะห์จาก Tier-2 ก่อน (mesh correlation) — สำคัญสุด
        for f in mesh.by_code_prefix("CROSS-CONFIRM", "CONF-SCORE"):
            cands.append({
                "source": f.agent, "code": f.code, "severity": f.severity,
                "file": f.file, "sheet": f.sheet, "iv": f.iv,
                "message": f.message,
                "cross_validated": True,
            })
        # 2) Tier-1 reviewers
        for f in mesh.by_agent("formula", "vat", "wht", "taxid"):
            if f.severity == Severity.INFO.value and f.code in ("FORMULA-DERIVED",):
                continue
            cands.append({
                "source": f.agent, "code": f.code, "severity": f.severity,
                "file": f.file, "sheet": f.sheet, "iv": f.iv,
                "message": f.message,
            })
    else:
        # fallback (ไม่มี mesh): พฤติกรรมเดิม — อ่าน ctx.results
        for name in ("formula", "vat", "wht", "taxid"):
            res = ctx.results.get(name)
            if not res:
                continue
            for f in res.findings:
                if f.severity == Severity.INFO.value and f.code in ("FORMULA-DERIVED",):
                    continue
                cands.append({
                    "source": name, "code": f.code, "severity": f.severity,
                    "file": f.file, "sheet": f.sheet, "iv": f.iv,
                    "message": f.message,
                })

    # 3) บิลความเชื่อมั่นต่ำ (parser อ่านไม่ชัด) — ต้องตาคนช่วย
    for b in (ctx.bills or []):
        conf = b.get("amount_confidence")
        if conf == "low":
            cands.append({
                "source": "confidence", "code": "LOW-CONF", "severity": "WARNING",
                "file": str(b.get("file", "")), "sheet": str(b.get("sheet", "")),
                "iv": str(b.get("iv_number") or "-"),
                "message": "ความเชื่อมั่นของยอดต่ำ (parser อ่านไม่ชัด)",
            })

    # จัดลำดับ: cross_validated ก่อน, แล้ว CRITICAL > ERROR > WARNING > INFO, แล้วตัดที่ max_items
    cands.sort(key=lambda c: (c.get("cross_validated", False),
                              _RANK.get(c.get("severity"), 0)), reverse=True)
    return cands[:max_items]


def _parse_llm_json(text: str) -> dict:
    """แกะ JSON จากคำตอบ LLM (คง raw text เป็น summary ถ้าแกะไม่ได้ — พฤติกรรมเดิม)."""
    return parse_llm_json(text, raw_fallback_key="summary")


class AiReviewAgent(Agent):
    name = "ai_review"
    description = "Local LLM ช่วย triage/อธิบายรายการที่ถูกธง (advisory เท่านั้น)"
    critical = False   # advisory — ไม่มี LLM/พัง = pipeline ปกติ

    def _run(self, ctx: PipelineContext) -> AgentResult:
        if not ctx.opt("enable_ai", False):
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "ปิดใช้งาน (enable_ai=False)"})

        provider = make_provider(ctx.options)
        if not provider.available():
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "ต่อ Local LLM ไม่ได้ (degrade graceful)",
                                        "provider": provider.info()})

        max_items = int(ctx.opt("ai_max_items", 60))
        candidates = _collect_candidates(ctx, max_items)
        if not candidates:
            return AgentResult(self.name, Status.OK.value,
                               summary={"reason": "ไม่มีรายการที่ต้อง triage",
                                        "provider": provider.info()})

        user_prompt = (
            "ต่อไปนี้คือรายการที่ระบบตรวจสอบอัตโนมัติได้ธงไว้ (JSON). "
            "ช่วยจัดลำดับความสำคัญและอธิบายสั้น ๆ ว่าผู้สอบบัญชีควรดูอะไรก่อน:\n\n"
            + json.dumps(candidates, ensure_ascii=False, indent=0)
        )

        # LLM call เป็น I/O ที่อาจล้มชั่วคราว (timeout/เน็ตหลุด) แม้ available() ผ่านแล้ว.
        # advisory → ล้ม = degrade เป็น SKIPPED (ไม่ใช่ ERROR ที่จะทำ SuperAgent มองว่าระบบพัง).
        try:
            raw = provider.chat(_SYSTEM_PROMPT, user_prompt)
        except Exception as e:
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": f"เรียก Local LLM ไม่สำเร็จ (degrade graceful): "
                                                  f"{type(e).__name__}: {str(e)[:120]}",
                                        "provider": provider.info()})
        parsed = _parse_llm_json(raw)

        findings = []
        summary_text = str(parsed.get("summary", ""))[:1000]
        if summary_text:
            findings.append(Finding(
                agent=self.name, code="AI-SUMMARY", severity=Severity.INFO.value,
                message=summary_text, evidence={"provider": provider.info()}))

        for item in (parsed.get("prioritized") or [])[:max_items]:
            if not isinstance(item, dict):
                continue
            sev = str(item.get("severity", "INFO")).upper()
            if sev not in ("CRITICAL", "ERROR", "WARNING", "INFO"):
                sev = "INFO"
            findings.append(Finding(
                agent=self.name, code="AI-TRIAGE", severity=sev,
                message=str(item.get("why", ""))[:300],
                file=str(item.get("file", "")), iv=str(item.get("iv", "-")),
                evidence={"recommended_action": str(item.get("recommended_action", ""))[:200]}))

        summary = {
            "provider": provider.info(),
            "candidates_sent": len(candidates),
            "triage_items": max(0, len(findings) - (1 if summary_text else 0)),
            "raw_chars": len(raw or ""),
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
