# -*- coding: utf-8 -*-
"""
agents/super_agent.py — SuperAgent (Tier-4 "ผู้กำกับระบบ" / meta-supervisor capstone)

ตำแหน่งในลำดับชั้น (Hybrid Hierarchical + Mesh):
    Tier-1  review อิสระ     : formula / vat / wht / taxid     → publish findings เข้า mesh
    Tier-2  correlation/score: crosscheck / confidence          → cross-confirm + คะแนนความเชื่อมั่น/บิล
    Tier-2.5 triage          : ai_review                          → จัด priority รายบิล + อธิบาย
    Tier-3  synthesis        : synthesis                          → บทสรุปเชิงบริหารของ "เนื้อหา audit"
    Tier-4  SUPER นี้ ★       : super (meta-supervisor)            → กำกับ "ตัวระบบเอง"

ทำไมต้องมี SuperAgent (และทำไมไม่ซ้ำกับ synthesis):
  • synthesis ตอบว่า "เนื้อหา audit ภาพรวมเป็นอย่างไร" (เพื่อหัวหน้าทีมตรวจ)
  • super ตอบว่า "ระบบตรวจทำงานดีแค่ไหน + ถ้าจะลงมือ ควรเริ่มบิลไหนก่อน (ลำดับเดียว รวมทุก tier) +
    มีสัญญาณที่ tier ต่าง ๆ ขัดแย้ง/ชี้เพิ่มตรงไหนบ้าง" (เพื่อผู้กำกับงาน/ผู้ส่งมอบ)

หน้าที่หลัก 4 อย่าง (ทั้งหมด deterministic — ทำซ้ำได้ ตามรอยได้):
  1) Pipeline QA      — ตรวจสุขภาพสายการผลิต: agent ครบไหม, ตัวใด error/skipped, AI ตกโหมด fallback ไหม
  2) Unified priority — รวมสัญญาณทุก tier (severity + จำนวนผู้ตรวจอิสระ + คะแนน confidence + AI เห็นพ้อง)
                        เป็น "คะแนนลำดับเดียว/บิล" แล้วจัดอันดับ top-N "ควรตรวจก่อน"
  3) Divergence       — จับจุดที่ tier ไม่ตรงกัน: บิลที่ AI ชี้แต่ไม่มีผู้ตรวจ deterministic ธง (สัญญาณใหม่)
  4) System verdict   — สรุปคำตัดสินเชิงระบบ 1 ย่อหน้า + (ทางเลือก) บทสรุปภาษาคนจาก Local LLM

⚠️ ADVISORY ONLY — อ่าน ctx.results / ctx.mesh / ctx.bills อย่างเดียว, **ไม่แตะ ctx.bills/ผลตรวจหลัก**.
   ผลของ super อยู่ใน findings (SUPER-*) + AgentResult.summary เท่านั้น → ReportAgent ไม่อ่าน mesh
   จึง Excel ยัง byte-identical (พิสูจน์ได้ด้วย golden_master/verify_golden).
   ไม่ critical: พัง/ไม่มี LLM = pipeline ปกติ (degrade graceful).
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Optional

from ._shared import SEV_RANK as _SEV_RANK, bill_key as _bkey, parse_llm_json
from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status
from .llm_provider import make_provider

# น้ำหนักความรุนแรงเฉพาะของ super (สเกลคนละชุดกับ ConfidenceAgent โดยตั้งใจ — ใช้รวมคะแนนข้าม tier)
_SEV_WEIGHT = {"CRITICAL": 40, "ERROR": 25, "WARNING": 12, "INFO": 4}

# ผู้ตรวจอิสระชั้นต้น (การธงพร้อมกันหลายตัว = หลักฐานข้ามมุมมอง)
_TIER1 = ("formula", "vat", "wht", "taxid")
# agent ที่คาดว่าจะรันครบในสายการผลิตเต็ม (ใช้ตรวจ QA ว่าขาดตัวใด)
_EXPECTED = ("import", "formula", "vat", "wht", "taxid",
             "crosscheck", "confidence", "ai_review", "synthesis")
# meta agent ที่ "ไม่นับเป็นหลักฐานต้นทาง" ตอนรวมคะแนน (กัน double-count/feedback loop)
_META = ("confidence", "crosscheck", "synthesis", "super")


def _parse_llm_json(text: str) -> dict:
    """แกะ JSON จากคำตอบ LLM แบบกันพัง (super ไม่คง raw text — ต้องการเฉพาะ schema)."""
    return parse_llm_json(text)


class SuperAgent(Agent):
    name = "super"
    description = ("ผู้กำกับระบบ (meta-supervisor): QA สายการผลิต + รวมสัญญาณทุก tier เป็น"
                   "ลำดับปฏิบัติเดียว + จับสัญญาณขัดแย้งข้าม tier (advisory, ไม่แตะผลหลัก)")
    critical = False   # advisory capstone — พัง/ไม่มี LLM = pipeline ปกติ

    # ---------------------------------------------------------------- run
    def _run(self, ctx: PipelineContext) -> AgentResult:
        mesh = ctx.mesh
        if mesh is None:
            return AgentResult(self.name, Status.SKIPPED.value,
                               summary={"reason": "ไม่มี mesh (รันนอก orchestrator) — super ทำงานไม่ได้"})

        findings: List[Finding] = []

        # 1) ---------- Pipeline QA (สุขภาพระบบ) ----------
        health = self._assess_pipeline(ctx)
        if health["errored"]:
            findings.append(Finding(
                agent=self.name, code="SUPER-QA", severity=Severity.ERROR.value,
                message=("ระบบทำงานไม่ครบ: agent ที่ล้ม = "
                         + ", ".join(health["errored"])
                         + " (ผลส่วนนี้อาจขาด — โปรดตรวจ log)"),
                evidence={"errored": health["errored"], "missing": health["missing"],
                          "statuses": health["statuses"]}))
        else:
            findings.append(Finding(
                agent=self.name, code="SUPER-QA", severity=Severity.INFO.value,
                message=(f"สายการผลิตทำงานครบ {health['ok']}/{health['expected']} agent หลัก"
                         + (f"; AI โหมด fallback: {', '.join(health['ai_fallback'])}"
                            if health["ai_fallback"] else "; AI ทำงานเต็มรูปแบบหรือปิดไว้")),
                evidence={"statuses": health["statuses"],
                          "ai_fallback": health["ai_fallback"]}))

        # 2) ---------- Unified priority (รวมสัญญาณทุก tier → ลำดับเดียว) ----------
        ranked, agg = self._unified_priority(ctx)
        top_n = int(ctx.opt("super_top_n", 10))
        top = ranked[:top_n]
        for r in top:
            sev = (Severity.CRITICAL.value if r["priority"] >= 80 else
                   Severity.ERROR.value if r["priority"] >= 55 else
                   Severity.WARNING.value)
            findings.append(Finding(
                agent=self.name, code="SUPER-PRIORITY", severity=sev,
                message=(f"ลำดับตรวจ {r['rank']}: คะแนนรวม {r['priority']}/100 "
                         f"— ผู้ตรวจอิสระ {r['n_tier1']} ตัว"
                         + (f", confidence {r['conf']}" if r["conf"] is not None else "")
                         + (", AI เห็นพ้อง" if r["ai"] else "")
                         + (", cross-confirmed" if r["cross"] else "")),
                file=r["file"], sheet=r["sheet"], iv=r["iv"],
                evidence={"priority_score": r["priority"], "breakdown": r["breakdown"],
                          "tier1_agents": r["tier1_agents"], "codes": r["codes"],
                          "max_severity": r["max_sev"]}))

        # 3) ---------- Divergence / novelty (สัญญาณที่ tier ไม่ตรงกัน) ----------
        for r in agg["ai_only"][: int(ctx.opt("super_novel_n", 10))]:
            findings.append(Finding(
                agent=self.name, code="SUPER-NOVEL", severity=Severity.INFO.value,
                message=("AI สังเกตบิลนี้เพิ่มเติม แต่ไม่มีผู้ตรวจ deterministic ธง "
                         "— อาจเป็นสัญญาณใหม่หรือ false positive ของ AI โปรดใช้วิจารณญาณ"),
                file=r["file"], sheet=r["sheet"], iv=r["iv"],
                evidence={"ai_codes": r["codes"]}))

        # 4) ---------- System verdict (คำตัดสินเชิงระบบ) ----------
        verdict_text = self._verdict_text(health, ranked, agg)
        findings.append(Finding(
            agent=self.name, code="SUPER-VERDICT", severity=Severity.INFO.value,
            message=verdict_text,
            evidence={"high_priority": sum(1 for r in ranked if r["priority"] >= 55),
                      "cross_confirmed": agg["n_cross"], "ai_only": len(agg["ai_only"]),
                      "mesh_stats": mesh.stats()}))

        summary: Dict = {
            "mode": "deterministic",
            "pipeline_ok": not health["errored"],
            "agents_ok": health["ok"], "agents_expected": health["expected"],
            "agents_errored": health["errored"], "agents_missing": health["missing"],
            "ai_fallback": health["ai_fallback"],
            "bills_ranked": len(ranked),
            "high_priority_bills": sum(1 for r in ranked if r["priority"] >= 55),
            "cross_confirmed_bills": agg["n_cross"],
            "ai_only_bills": len(agg["ai_only"]),
            "top_priorities": [
                {"rank": r["rank"], "file": r["file"], "sheet": r["sheet"],
                 "iv": r["iv"], "priority": r["priority"]} for r in top
            ],
            "verdict": verdict_text,
        }

        # 5) ---------- (ทางเลือก) บทสรุปภาษาคนจาก Local LLM — degrade graceful ----------
        if ctx.opt("enable_ai", False):
            brief = self._llm_brief(ctx, summary)
            if brief:
                summary["mode"] = "llm"
                summary["provider"] = brief["provider"]
                findings.append(Finding(
                    agent=self.name, code="SUPER-BRIEF", severity=Severity.INFO.value,
                    message=brief["text"][:1400],
                    evidence={"provider": brief["provider"]}))

        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)

    # ---------------------------------------------------------------- QA
    def _assess_pipeline(self, ctx: PipelineContext) -> Dict:
        """ตรวจสุขภาพสายการผลิตจาก ctx.results (ไม่แตะอะไร)."""
        statuses = {name: r.status for name, r in ctx.results.items()}
        errored = sorted(n for n, s in statuses.items() if s == Status.ERROR.value)
        present = set(statuses.keys())
        missing = sorted(a for a in _EXPECTED if a not in present)
        ok = sum(1 for a in _EXPECTED if statuses.get(a) == Status.OK.value)

        # AI ตกโหมด fallback (statistical) ไหม — อ่านจาก summary ของ synthesis/ai_review
        ai_fallback: List[str] = []
        for nm in ("synthesis", "ai_review"):
            r = ctx.results.get(nm)
            if r is not None:
                mode = str((r.summary or {}).get("mode", ""))
                if mode and mode != "llm":
                    ai_fallback.append(nm)
        return {"statuses": statuses, "errored": errored, "missing": missing,
                "ok": ok, "expected": len(_EXPECTED), "ai_fallback": sorted(ai_fallback)}

    # ------------------------------------------------------ unified priority
    def _unified_priority(self, ctx: PipelineContext):
        """รวมสัญญาณทุก tier ต่อบิลเป็น 'คะแนนลำดับเดียว' (โปร่งใส ตามรอยได้).

        คะแนนดิบ/บิล =
            severity_weight(max ของหลักฐานต้นทาง)            # ความรุนแรง
          + (n_tier1 - 1) * 8   ถ้า n_tier1 >= 2              # ผู้ตรวจอิสระเห็นพ้อง
          + confidence_risk_score * 0.4                       # คะแนน Tier-2 (cross-aware แล้ว)
          + 8  ถ้า AI ก็ธงบิลนี้ด้วย                          # AI เห็นพ้อง
        แล้ว normalize → 0..100 (เชิงอันดับภายในรอบนี้ เหมือน ConfidenceAgent)
        """
        mesh = ctx.mesh
        per_agents: Dict[str, set] = defaultdict(set)
        per_codes: Dict[str, set] = defaultdict(set)
        per_maxsev: Dict[str, str] = {}
        per_conf: Dict[str, Optional[float]] = {}
        ref: Dict[str, tuple] = {}

        for f in mesh.all():
            k = _bkey(f.file, f.sheet, f.iv)
            ref.setdefault(k, (f.file, f.sheet, f.iv))
            per_agents[k].add(f.agent)
            per_codes[k].add(f.code)
            # max severity เฉพาะหลักฐาน "ต้นทาง" (ไม่ใช่ meta) — กันยกระดับด้วยผลของตัวเอง
            if f.agent not in _META:
                cur = per_maxsev.get(k, "INFO")
                if _SEV_RANK.get(f.severity, 0) > _SEV_RANK.get(cur, 0):
                    per_maxsev[k] = f.severity
            # ดึงคะแนน confidence (ถ้ามี)
            if f.agent == "confidence" and f.code == "CONF-SCORE":
                per_conf[k] = float(f.evidence.get("risk_score", 0) or 0)

        rows = []
        for k, agents in per_agents.items():
            tier1 = sorted(agents & set(_TIER1))
            n_tier1 = len(tier1)
            ai = "ai_review" in agents
            cross = "crosscheck" in agents
            conf = per_conf.get(k)
            max_sev = per_maxsev.get(k, "INFO")

            raw = _SEV_WEIGHT.get(max_sev, 4)
            if n_tier1 >= 2:
                raw += (n_tier1 - 1) * 8
            if conf is not None:
                raw += conf * 0.4
            if ai:
                raw += 8

            rows.append({
                "key": k, "file": ref[k][0], "sheet": ref[k][1], "iv": ref[k][2],
                "raw": raw, "n_tier1": n_tier1, "tier1_agents": tier1,
                "ai": ai, "cross": cross, "conf": conf,
                "max_sev": max_sev, "codes": sorted(per_codes[k]),
            })

        # ตัดบิลที่ไม่มีสัญญาณต้นทางเลย (เฉพาะ meta โผล่) ออกจากการจัดอันดับ
        rows = [r for r in rows if r["n_tier1"] > 0 or r["ai"] or (r["conf"] or 0) > 0]

        max_raw = max((r["raw"] for r in rows), default=1.0) or 1.0
        for r in rows:
            r["priority"] = round(r["raw"] / max_raw * 100, 1)
            r["breakdown"] = {
                "sev_weight": _SEV_WEIGHT.get(r["max_sev"], 4),
                "tier1_bonus": (r["n_tier1"] - 1) * 8 if r["n_tier1"] >= 2 else 0,
                "confidence_part": round((r["conf"] or 0) * 0.4, 1),
                "ai_bonus": 8 if r["ai"] else 0,
                "raw": round(r["raw"], 1), "max_raw": round(max_raw, 1),
            }
        # เรียง deterministic: คะแนนสูงก่อน, แล้ว severity, แล้ว bill key
        rows.sort(key=lambda r: (-r["priority"], -_SEV_RANK.get(r["max_sev"], 0), r["key"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i

        # มุมมองเสริม: บิลที่ AI ชี้แต่ไม่มี Tier-1 ธง (สัญญาณใหม่) + จำนวน cross-confirmed
        ai_only = sorted(
            [{"file": r["file"], "sheet": r["sheet"], "iv": r["iv"], "codes": list(r["codes"])}
             for r in rows if r["ai"] and r["n_tier1"] == 0],
            key=lambda d: (d["file"], d["sheet"], d["iv"]))
        n_cross = sum(1 for r in rows if r["cross"])

        return rows, {"ai_only": ai_only, "n_cross": n_cross}

    # ---------------------------------------------------------- verdict text
    def _verdict_text(self, health: Dict, ranked: List[Dict], agg: Dict) -> str:
        hp = sum(1 for r in ranked if r["priority"] >= 55)
        parts = []
        if health["errored"]:
            parts.append(f"⚠️ ระบบไม่ครบ ({len(health['errored'])} agent ล้ม)")
        else:
            parts.append(f"ระบบทำงานครบ {health['ok']}/{health['expected']} agent")
        parts.append(f"จัดอันดับ {len(ranked)} บิลที่มีสัญญาณ")
        if hp:
            parts.append(f"พบ {hp} บิลควรตรวจก่อน (คะแนน ≥ 55)")
        if agg["n_cross"]:
            parts.append(f"{agg['n_cross']} บิล cross-confirmed")
        if agg["ai_only"]:
            parts.append(f"{len(agg['ai_only'])} บิลที่ AI ชี้เพิ่ม (ไม่มีผู้ตรวจ deterministic ธง)")
        if health["ai_fallback"]:
            parts.append(f"หมายเหตุ: AI โหมด fallback ({', '.join(health['ai_fallback'])})")
        return " · ".join(parts)

    # ------------------------------------------------------------- LLM brief
    def _llm_brief(self, ctx: PipelineContext, summary: Dict) -> Optional[Dict]:
        """บทสรุปเชิงปฏิบัติการระดับระบบจาก Local LLM (ทางเลือก). คืน None ถ้าต่อไม่ได้/แกะไม่ได้.

        ขอบเขตต่างจาก synthesis: เน้น 'คำแนะนำเชิงระบบ/ลำดับการลงมือ' ไม่ใช่สรุปเนื้อหา audit ซ้ำ.
        """
        provider = make_provider(ctx.options)
        if not provider.available():
            return None
        sys_prompt = (
            "คุณคือผู้กำกับงานตรวจสอบ (audit supervisor) ภาษาไทย. ระบบตรวจอัตโนมัติหลายตัวทำงานเสร็จ "
            "และส่ง 'สรุปเชิงระบบ' (JSON) มาให้: สุขภาพสายการผลิต + บิลที่ควรตรวจก่อน + สัญญาณที่ AI ชี้เพิ่ม. "
            "เขียน 'คำแนะนำเชิงปฏิบัติการ' สั้นมาก (2-4 ประโยค) ว่าทีมมนุษย์ควรลงมือกับงานชุดนี้อย่างไร "
            "(เริ่มจากอะไร, ระวังอะไร). ห้ามคำนวณยอด/ตัดสินผ่าน-ไม่ผ่านแทนระบบ, ห้ามแต่งตัวเลขนอก input. "
            'ตอบ JSON เท่านั้น: {"recommendation":"..."}'
        )
        payload = {
            "pipeline_ok": summary["pipeline_ok"],
            "agents_errored": summary["agents_errored"],
            "ai_fallback": summary["ai_fallback"],
            "high_priority_bills": summary["high_priority_bills"],
            "cross_confirmed_bills": summary["cross_confirmed_bills"],
            "ai_only_bills": summary["ai_only_bills"],
            "top_priorities": summary["top_priorities"][:5],
        }
        try:
            raw = provider.chat(sys_prompt, json.dumps(payload, ensure_ascii=False, indent=0))
        except Exception:
            return None      # LLM ล้มชั่วคราว → ข้ามบทสรุป LLM (super ยังคืนผล deterministic ครบ)
        parsed = _parse_llm_json(raw)
        rec = str(parsed.get("recommendation", "")).strip()
        if not rec:
            return None
        return {"text": rec, "provider": provider.info()}
