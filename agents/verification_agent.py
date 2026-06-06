# -*- coding: utf-8 -*-
"""
agents/verification_agent.py — VerificationAgent (Tier-2 "ยืนยัน Error ก่อนฟันธง")

Supervisor ของ "ทีมผู้ตรวจเชิงกลไก": รันทุกเลนส์ใน INSPECTION_LENSES (agents/verification_lenses.py)
ต่อ Error แต่ละตัว แล้วรวมโหวตเป็น consensus verdict:
    score ≥ +2 → CONFIRMED   |   score ≤ -1 → LIKELY_FALSE_POSITIVE   |   อื่น ๆ → NEEDS_REVIEW

★ PRECISION-FIRST · กฎโดเมนล็อก VAT=round(sub×0.07,2) (L8) · OFFLINE-ONLY · ADVISORY:
  ทุกเลนส์อ่านอย่างเดียว ไม่แตะ b['issues']/ผลหลัก, ไม่มี network. L6 (LLM) opt-in + offline→งดออกเสียง
  → CI/pin deterministic. ผลอยู่ใน findings (VERIFY-*) + summary → golden hash เหมือนเดิม
  (regression_full: engine==agent==baseline ; ชั้น advisory ตรึงด้วย pin test). ไม่ critical.

หมายเหตุ: crosscheck = หา "หลาย agent ธงบิลเดียวกัน" ; verification (ตัวนี้) = verify
  "Error แต่ละตัวของ engine" ด้วยคลังเลนส์ → consensus per-Error.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Tuple

from .base import Agent, bill_ref
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status
from .llm_provider import make_provider
from .verification_lenses import (
    INSPECTION_LENSES,
    LensInput,
    _build_cross_index,
    lens_roster,
)

# re-export (backward-compat: เครื่องมือ/เทสเดิมที่ import จาก verification_agent ยังใช้ได้)
__all__ = ["VerificationAgent", "INSPECTION_LENSES", "LensInput", "lens_roster"]


class VerificationAgent(Agent):

    name = "verification"
    description = (
        "ยืนยัน Error ของ engine ด้วยคลังเลนส์อิสระ → consensus ต่อ Error "
        "(confirmed / needs-review / likely-false-positive) — advisory ไม่แตะผลหลัก"
    )
    critical = False

    # ---------------------------------------------------------------- run
    def _run(self, ctx: PipelineContext) -> AgentResult:
        bills = ctx.bills or []
        scope = tuple(ctx.opt("verify_severities", ("CRITICAL", "ERROR")))

        # L6 (LLM lens) — opt-in + offline-safe (default ปิด → งดออกเสียง → deterministic/CI)
        self._llm = None
        self._llm_info = {
            "used": False,
            "reason": "ปิด (default) — deterministic เลนส์เท่านั้น",
        }
        if ctx.opt("verify_use_llm", False):
            try:
                prov = make_provider(ctx.options)
                if prov.available():
                    self._llm = prov
                    self._llm_info = {"used": True, "provider": prov.info()}
                else:
                    self._llm_info = {
                        "used": False,
                        "reason": "เปิดไว้แต่ probe LLM ไม่ติด (offline) → งดออกเสียง",
                        "provider": prov.info(),
                    }
            except Exception as _e:
                self._llm_info = {
                    "used": False,
                    "reason": f"สร้าง provider ไม่ได้: {type(_e).__name__}",
                }

        # index บิลพี่น้องตามไฟล์ (L4/L16) — deterministic
        by_file: Dict[str, List[dict]] = defaultdict(list)
        for b in bills:
            by_file[str(b.get("file", ""))].append(b)
        # ดัชนีข้ามบิล + ทะเบียน master (L17/L18/L21/L22) — สร้างครั้งเดียว
        cross = _build_cross_index(bills, ctx.master or {})

        findings: List[Finding] = []
        n_total = n_confirmed = n_review = n_falsepos = 0
        lens_agree: Dict[str, int] = defaultdict(int)

        for b in bills:
            ref = bill_ref(b)
            peers = by_file.get(str(b.get("file", "")), [])
            for iss in b.get("issues") or []:
                sev = str(iss.get("severity", "INFO"))
                if sev not in scope:
                    continue
                code = str(iss.get("code", ""))
                votes, reasons = self._vote(
                    b, iss, code, sev, peers, cross, ctx.master or {}
                )
                for ln, v in votes.items():
                    if v > 0:
                        lens_agree[ln] += 1
                score = sum(votes.values())
                n_voted = sum(1 for v in votes.values() if v != 0)

                if score >= 2:
                    verdict, vcode, vsev = "CONFIRMED", "VERIFY-CONFIRMED", sev
                    n_confirmed += 1
                elif score <= -1:
                    verdict, vcode, vsev = (
                        "LIKELY_FALSE_POSITIVE",
                        "VERIFY-FALSEPOS",
                        Severity.INFO.value,
                    )
                    n_falsepos += 1
                else:
                    verdict, vcode, vsev = "NEEDS_REVIEW", "VERIFY-REVIEW", sev
                    n_review += 1
                n_total += 1

                findings.append(
                    Finding(
                        agent=self.name,
                        code=vcode,
                        severity=vsev,
                        message=(
                            f"[{code}] {iss.get('name', '')} → consensus: {verdict} "
                            f"(คะแนน {score:+d} จาก {n_voted} เลนส์ที่ออกเสียง) — "
                            + "; ".join(reasons[:3])
                        ),
                        file=ref["file"],
                        sheet=ref["sheet"],
                        iv=ref["iv"],
                        evidence={
                            "engine_code": code,
                            "engine_severity": sev,
                            "verdict": verdict,
                            "score": score,
                            "votes": dict(votes),
                            "reasons": reasons,
                        },
                    )
                )

        summary = {
            "scope_severities": list(scope),
            "errors_verified": n_total,
            "confirmed": n_confirmed,
            "needs_review": n_review,
            "likely_false_positive": n_falsepos,
            "lens_confirm_counts": dict(lens_agree),
            "lens_roster": lens_roster(),
            "inspectors": len(INSPECTION_LENSES),
            "llm_lens": self._llm_info,
            "note": "advisory — ไม่แก้ b['issues']; ผลตรวจหลัก/hash เหมือนเดิม",
        }
        return AgentResult(
            self.name, Status.OK.value, summary=summary, findings=findings
        )

    # ---------------------------------------------------------------- lenses
    def _vote(
        self, b, iss, code, sev, peers, cross, master
    ) -> Tuple[Dict[str, int], List[str]]:
        """รันทุกเลนส์ในคลัง (ตามลำดับ INSPECTION_LENSES). คืน (votes, reasons)."""
        x = LensInput(
            bill=b,
            issue=iss,
            code=code,
            sev=sev,
            peers=peers,
            llm=self._llm,
            index=cross,
            master=master,
        )
        votes: Dict[str, int] = {}
        reasons: List[str] = []
        for ln in INSPECTION_LENSES:
            v, r = ln.fn(x)
            votes[ln.id] = v
            if r:
                reasons.append(r)
        return votes, reasons
