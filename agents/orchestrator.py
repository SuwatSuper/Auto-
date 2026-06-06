# -*- coding: utf-8 -*-
"""
agents/orchestrator.py — ตัวควบคุมสายการผลิต (DAG runner)

หัวใจของสถาปัตยกรรม multi-agent: ร้อยทุก agent เข้าด้วยกันตามลำดับที่ถูกต้อง
โดย "ผลตรวจที่เป็นทางการ" (ตัวที่ออก Excel) ยังวิ่งผ่าน **เครื่องยนต์เดิมชุดเดียว**
ในลำดับเป๊ะตามที่พิสูจน์แล้ว (golden_master / main) → จึง byte-identical พิสูจน์ได้

ลำดับ DAG:
  reset_run_state
    └─ [1] ImportAgent (critical)            ค้นไฟล์ + parse → ctx.bills, ctx.filename_issues
         └─ _run_audit_core(ctx)             ⭐ ลำดับศักดิ์สิทธิ์ (รันครั้งเดียว, ห้ามแตะ)
              dup → rules → iv_seq+iv_date → typos → summary → crosschecks
         ├─ [2] FormulaAgent (review)        ตรวจซ้ำเชิงเลขคณิตอย่างอิสระ (read-only)
         ├─ [3] VatAgent     (review)        อ่านผล VAT* + ชี้ false-clean (read-only)
         ├─ [4] WhtAgent     (review)        ห่อ addon ภงด.53 เดิม (read-only)
         ├─ [5] TaxIdAgent   (review)        checksum อิสระ + ซ้ำข้ามบริษัท (read-only)
         ├─ [6] AiReviewAgent (Local LLM)    triage/อธิบาย — advisory ล้วน (read-only)
         └─ [7] ReportAgent  (critical)      เขียน Excel (เหมือนเดิม)

กฎ error-boundary:
  - agent critical พัง  → โยน AgentError ขึ้นมา = หยุดทั้ง pipeline (มี state ค้างให้ debug)
  - agent ไม่ critical พัง → base.Agent.run() จับไว้ คืน status=error, **pipeline ไปต่อ**
    (สะท้อนปรัชญา P1-FIX-ISOLATION: ส่วนเสริมพังต้องไม่ล้มงานหลัก)

⭐ ทำไม _run_audit_core ต้องอยู่ "ที่เดียว ครั้งเดียว":
   ผลตรวจหลักถูก fingerprint ด้วย SHA256 (golden_master). ถ้า run_all_rules หรือ
   crosscheck ถูกเรียกซ้ำ/สลับลำดับ → issue ซ้ำ/เรียงใหม่ → hash เปลี่ยน → ไม่เหมือนเดิม
   ดังนั้น agent ฝั่ง review ทุกตัว "อ่านอย่างเดียว" ไม่รันกฎเอง
"""
from __future__ import annotations

from typing import Callable, List, Optional

from . import core_access as core
from .ai_review_agent import AiReviewAgent
from .base import Agent, AgentError
from .confidence_agent import ConfidenceAgent
from .contracts import AgentResult, PipelineContext, Status
from .crosscheck_agent import CrossCheckAgent
from .formula_agent import FormulaAgent
from .import_agent import ImportAgent
from .mesh import FindingsMesh
from .notepad_agent import NotepadAgent
from .report_agent import ReportAgent
from .super_agent import SuperAgent
from .synthesis_agent import SynthesisAgent
from .taxid_agent import TaxIdAgent
from .vat_agent import VatAgent
from .vendor_report_agent import VendorReportAgent
from .verification_agent import VerificationAgent
from .wht_agent import WhtAgent


# ---------------------------------------------------------------------------
# ⭐ ลำดับศักดิ์สิทธิ์ — ก๊อปจาก main() (บรรทัด ~4782–4844) และ golden_master.py เป๊ะ
#    ห้ามแก้ลำดับ / ห้ามเรียกซ้ำ ที่อื่น  (ทุกบรรทัดมีผลต่อ fingerprint)
# ---------------------------------------------------------------------------
def _run_audit_core(ctx: PipelineContext) -> None:
    """รันชุดกฎ/ตรวจสอบหลัก "ครั้งเดียว" ในลำดับที่พิสูจน์แล้ว แล้วเขียนผลลง ctx.

    ⭐ v9.1 DECOUPLE: ลำดับนี้ "ไม่ก๊อปซ้ำ" อีกต่อไป — delegate ไปที่ core.run_audit_core()
    ซึ่งเป็น *แหล่งความจริงเดียว* ที่ main() และ golden_master ก็เรียกตัวเดียวกัน
    → engine == agent == golden รับประกันด้วยโครงสร้าง (ไม่ใช่ด้วยการก๊อปแล้วหวังว่าจะตรง).

    เทียบ main()/golden_master (ลำดับเดียวกันทุกบรรทัด, โค้ดอยู่ที่เดียว):
        check_duplicate_items → run_all_rules → check_invoice_sequence + check_iv_date_sequence
        → check_product_typos → summarize_by_company → apply_iv_period_crosscheck
        → apply_sheet_date_crosscheck

    isolate=True: ได้ error-isolation (P1-FIX-ISOLATION) เท่ากับเส้น engine — เดิมเส้น agent
    ไม่มี try/except ตรงนี้ ทำให้ข้อมูลเสียทำ pipeline ล้มทั้งเส้น (engine กลับ degrade ได้).
    บนข้อมูล golden ทุกขั้นไม่โยน → ผล/hash เท่าเดิมเป๊ะ (= baseline.json._sha256).
    """
    result = core.core.run_audit_core(ctx.bills, ctx.master, isolate=True)
    ctx.dup_items = result['dup_items']
    ctx.iv_seq = result['iv_seq']
    ctx.iv_date = result['iv_date']
    ctx.iv_issues = result['iv_issues']      # ← = iv_seq + iv_date (ค่าที่ Report ใช้)
    ctx.typos = result['typos']
    ctx.summary = result['summary']


class Orchestrator:
    """ตัวรัน pipeline แบบ agent. ใช้ลำดับคงที่ + error-boundary ตาม critical flag."""

    def __init__(self, logger: Optional[Callable[[str], None]] = None):
        # logger เบาๆ (callable รับ str). default = เงียบ
        self._log = logger or (lambda msg: None)
        self.logger = logger

    # ---- รายชื่อ agent ฝั่ง review (รันหลัง core, ลำดับนี้คงที่เพื่อผล findings เสถียร) ----
    def _review_agents(self) -> List[Agent]:
        # Tier-1: ผู้ตรวจอิสระ (อ่าน ctx.bills/issue หลัก ออก findings ของตัวเอง)
        return [
            FormulaAgent(self.logger),
            VatAgent(self.logger),
            WhtAgent(self.logger),
            TaxIdAgent(self.logger),
        ]

    def _tier2_agents(self) -> List[Agent]:
        """Tier-2: ผู้สังเคราะห์ (อ่าน mesh ที่ Tier-1 โพสต์ไว้ → correlation/score).
        ลำดับคงที่: crosscheck (cross-confirm ข้าม agent) → confidence (คะแนนรวม) →
        verification (ยืนยัน Error ของ engine แต่ละตัวด้วย 5 เลนส์ → consensus per-Error).
        ทั้งหมด advisory — ไม่แตะ ctx.bills/ผลตรวจหลัก (golden hash คงเดิม).
        """
        return [
            CrossCheckAgent(self.logger),
            ConfidenceAgent(self.logger),
            VerificationAgent(self.logger),
        ]

    def run(self, ctx: PipelineContext) -> PipelineContext:
        """รัน pipeline เต็ม. คืน ctx เดิม (มี ctx.results ครบทุก agent ที่รันถึง).

        ยกเว้น critical agent ล้ม → โยน AgentError (ตั้งใจหยุด) โดย ctx ยังถือ state เท่าที่ทำได้
        """
        # 0) รีเซ็ต cache ที่ใช้ร่วม (ตรงกับ golden_master/main ที่เรียกก่อนเริ่ม) — กันรัฐตกค้าง
        core.core.reset_run_state()

        # 0.5) ตั้ง mesh (data plane) ถ้ายังไม่มี — agent ทุกตัว publish/อ่าน findings ผ่านที่นี่
        if ctx.mesh is None:
            ctx.mesh = FindingsMesh()

        # 1) Import (critical) — ไม่มีบิล = หยุด
        self._dispatch(ImportAgent(self.logger), ctx)

        # ⭐ core audit "ครั้งเดียว" — นี่คือผลที่จะกลายเป็น Excel (byte-identical)
        self._log("[core] run_audit_core (rules + sequence + crosscheck) …")
        _run_audit_core(ctx)
        self._log(f"[core] done: bills={len(ctx.bills)} "
                  f"iv_seq={len(ctx.iv_seq)} iv_date={len(ctx.iv_date)} "
                  f"typos={len(ctx.typos)} companies={len(ctx.summary)} "
                  f"dup={len(ctx.dup_items)}")

        # 2) – 8) ทุก agent "หลัง core" (review → tier2 → ai → synthesis → super → report → notepad)
        #     แยกเป็นเมธอดเดียว: ให้ run() (เส้นเต็ม) และ run_advisory() (เส้น advisory-only ที่เรียก
        #     จาก main() ของ monolith หลังเขียน Excel) ใช้ "ลำดับเดียวกันที่เดียว" — กัน drift.
        self._run_post_core_agents(ctx, allow_report=True)

        return ctx

    # ---- ลำดับ agent หลัง core (แหล่งความจริงเดียว ใช้ร่วม run / run_advisory) ----
    def _run_post_core_agents(self, ctx: PipelineContext, *, allow_report: bool) -> None:
        """รัน agent ทุกตัว 'หลัง core audit' ตามลำดับคงที่.

        allow_report=True  : เส้นเต็ม (run()) — เขียน Excel ตาม ctx.options['write_report'] (เดิมเป๊ะ)
        allow_report=False : เส้น advisory-only (run_advisory()) — *ไม่* เขียน Excel
                             (ผู้เรียก เช่น main() ของ monolith เขียนไฟล์ผลลัพธ์หลักไปแล้ว)

        ⚠️ สำหรับ allow_report=True ลำดับต้องเท่าเดิมทุกบรรทัด (run_agents.py พิสูจน์ byte-identical).
        """
        # 2–5) Tier-1 review agents (ไม่ critical — พังตัวใดตัวหนึ่ง pipeline ไปต่อ)
        #      findings ถูก publish เข้า mesh อัตโนมัติผ่าน ctx.record()
        for agent in self._review_agents():
            self._dispatch(agent, ctx)

        # 5.5) Tier-2 mesh consumers (crosscheck → confidence → verification)
        for agent in self._tier2_agents():
            self._dispatch(agent, ctx)

        # 6) AI Review (Local LLM, ไม่ critical) — อ่าน mesh ทั้งหมดแล้ว triage/อธิบายให้คน
        self._dispatch(AiReviewAgent(self.logger), ctx)

        # 6.5) Tier-3 Synthesis (capstone) — สรุปภาพรวมจาก mesh ที่ตกผลึก (รัน *หลัง* ai_review)
        self._dispatch(SynthesisAgent(self.logger), ctx)

        # 6.9) Tier-4 SuperAgent (meta-supervisor) — QA สายการผลิต + รวมทุก tier (รัน *หลัง* synthesis)
        self._dispatch(SuperAgent(self.logger), ctx)

        # 7) Report (critical) — เขียน Excel เหมือนเดิม. เส้น advisory ข้าม (Excel เขียนที่อื่นแล้ว)
        if allow_report:
            if ctx.opt("write_report", True):
                self._dispatch(ReportAgent(self.logger), ctx)
            else:
                self._log("[report] ข้าม (write_report=False) — โหมดพิสูจน์/วิเคราะห์เท่านั้น")

        # 7.5) VendorReport (advisory) — รายงานลูกค้ารายผู้ขาย .txt ข้าง Excel (output เพิ่ม, ไม่ทับ Excel)
        #      รันหลัง Report เพื่ออ้างพาธ Excel (ctx.report_path) ในสรุป. ไม่แตะ bills.
        self._dispatch(VendorReportAgent(self.logger), ctx)

        # 8) Notepad (advisory, ท้ายสุด) — สรุปการทำงานทุก agent + super เป็น .txt. ไม่แตะ bills.
        self._dispatch(NotepadAgent(self.logger), ctx)

    def run_advisory(self, ctx: PipelineContext) -> PipelineContext:
        """รัน 'เฉพาะชั้น advisory' บน ctx ที่ผ่าน parse + audit core มาแล้ว.

        ใช้โดย main() ของ monolith *หลังเขียน Excel เสร็จ* เพื่อออกไฟล์รายงานการทำงานของ agent (.txt):
          ★ ไม่ parse ใหม่ (reuse ctx.bills ที่มีอยู่)  → เพอร์ฟอร์แมนซ์ parse ไม่เสีย
          ★ ไม่ rerun rules/crosscheck                  → ไม่เกิด issue ซ้ำ, golden hash คงเดิม
          ★ ไม่เขียน Excel                               → ไฟล์ผลลัพธ์หลักไม่ถูกแตะ
        เงื่อนไข: ctx ต้องมี bills (+ summary/iv_*/typos/dup_items) เติมมาแล้ว. agent ชั้น advisory
        เป็น read-only ต่อ bills (พิสูจน์เชิงโครงสร้าง) → ปลอดภัยแม้ bills ถูกตรวจมาแล้ว.
        *ไม่* เรียก reset_run_state เพื่อไม่รบกวน state ของ monolith ที่กำลังรันอยู่.
        """
        if ctx.mesh is None:
            ctx.mesh = FindingsMesh()
        self._run_post_core_agents(ctx, allow_report=False)
        return ctx

    # ---- helper: รัน 1 agent + บันทึกผล + บังคับ error-boundary ----
    def _dispatch(self, agent: Agent, ctx: PipelineContext) -> AgentResult:
        try:
            result = agent.run(ctx)
        except AgentError as e:
            # critical agent สั่งหยุด — บันทึก "ผลของจริง" (มี traceback เต็มจาก base.run) ถ้ามี
            #   [C1-FIX] เดิมสร้างผลบางๆ ทับ → เสีย traceback ในจุดสำคัญที่สุด. fallback ถ้าไม่มี.
            res = getattr(e, "result", None) or AgentResult(
                agent.name, Status.ERROR.value,
                error=f"{agent.name} (critical) หยุด pipeline")
            ctx.record(res)
            raise
        ctx.record(result)
        return result


# ---------------------------------------------------------------------------
# convenience: สร้าง ctx + รัน ในฟังก์ชันเดียว (ใช้โดย run_agents.py / harness)
# ---------------------------------------------------------------------------
def run_pipeline(master: dict,
                 file_list: Optional[List[str]] = None,
                 options: Optional[dict] = None,
                 logger: Optional[Callable[[str], None]] = None) -> PipelineContext:
    """ทางลัด: ประกอบ PipelineContext แล้วรัน Orchestrator. คืน ctx ที่รันเสร็จ."""
    ctx = PipelineContext(
        master=master or {},
        file_list=list(file_list or []),
        options=dict(options or {}),
    )
    return Orchestrator(logger=logger).run(ctx)


def run_pipeline_advisory(ctx: PipelineContext,
                          logger: Optional[Callable[[str], None]] = None) -> PipelineContext:
    """ทางลัด: รัน 'เฉพาะชั้น advisory' บน ctx ที่เตรียมมาแล้ว (parse + audit core เสร็จ).

    ใช้โดย main() ของ monolith เพื่อออกไฟล์ 'รายงานการทำงานของ agent' (.txt) ข้าง Excel
    โดยไม่ parse ซ้ำ / ไม่ rerun rules / ไม่เขียน Excel → ไม่กระทบผลตรวจหลัก (golden hash คงเดิม).
    คืน ctx เดิมที่มี ctx.results ครบทุก agent ชั้น advisory (รวม notepad ที่เขียนไฟล์แล้ว).
    """
    return Orchestrator(logger=logger).run_advisory(ctx)
