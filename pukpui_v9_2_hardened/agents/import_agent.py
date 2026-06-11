# -*- coding: utf-8 -*-
"""
agents/import_agent.py — Import Agent (Python ปกติ, CRITICAL)

หน้าที่ (1 stage ชัดเจนในระบบเดิม): ค้นไฟล์ → parse เป็น "บิล" + filename_issues
  ห่อฟังก์ชันที่พิสูจน์แล้ว: get_files_via_drive / get_files_via_upload / parse_all_files
  ไม่แตะ logic การ parse แม้แต่บรรทัดเดียว — เพิ่มเฉพาะ:
    • validation ขาเข้า (โฟลเดอร์/ไฟล์มีจริง อ่านได้)
    • สรุปต่อไฟล์ (กี่บิล/ไฟล์) + ธงไฟล์ที่ parse ไม่ได้ → findings
    • error boundary (critical: ไม่มีบิล = หยุด pipeline อย่างชัดเจน)

ผลลัพธ์เขียนลง ctx.bills, ctx.filename_issues (orchestrator อ่านต่อ)
"""
from __future__ import annotations

import os
from collections import Counter

from . import core_access as core
from .base import Agent, AgentError
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status


class ImportAgent(Agent):
    name = "import"
    description = "ค้นไฟล์ + parse เป็นบิล (ห่อ parse_all_files เดิม)"
    critical = True   # ไม่มีบิล = ตรวจอะไรไม่ได้ → หยุด

    def _run(self, ctx: PipelineContext) -> AgentResult:
        file_list = list(ctx.file_list or [])

        # --- ถ้ายังไม่ได้ส่ง file_list มา ให้ค้นจาก source ที่ระบุใน options ---
        if not file_list:
            src = ctx.opt("source", "drive")
            folder = ctx.opt("folder", ".")
            if src == "upload":
                file_list = core.core.get_files_via_upload()
            else:
                if not os.path.isdir(folder):
                    raise AgentError(f"ไม่พบโฟลเดอร์: {folder!r}")
                file_list = core.core.get_files_via_drive(folder)
            ctx.file_list = file_list

        if not file_list:
            raise AgentError("ไม่พบไฟล์ .xls/.xlsx ให้ประมวลผล")

        # --- validation เบาๆ: คัดไฟล์ที่หาย/อ่านไม่ได้ออก + บันทึกเป็น finding ---
        readable, findings = [], []
        for f in file_list:
            if not os.path.isfile(f):
                findings.append(Finding(
                    agent=self.name, code="IMPORT-MISSING", severity=Severity.ERROR.value,
                    message="ไฟล์หายไป/ไม่ใช่ไฟล์", file=os.path.basename(str(f)),
                    evidence={"path": str(f)}))
                continue
            if os.path.getsize(f) == 0:
                findings.append(Finding(
                    agent=self.name, code="IMPORT-EMPTY", severity=Severity.WARNING.value,
                    message="ไฟล์ขนาด 0 ไบต์", file=os.path.basename(str(f)),
                    evidence={"path": str(f)}))
                continue
            readable.append(f)

        if not readable:
            raise AgentError("ไม่มีไฟล์ที่อ่านได้เลย (หาย/ว่างทั้งหมด)")

        # --- เรียกเครื่องยนต์เดิม (พฤติกรรม parse เหมือนเดิม 100%) ---
        bills, filename_issues = core.core.parse_all_files(readable)

        # --- compute_bill_confidence ต่อบิล (เหมือนที่ main() ทำ ก่อนขั้น rules) ---
        for b in bills:
            core.core.compute_bill_confidence(b)

        # เขียนลง context ให้ stage ถัดไปใช้
        ctx.bills = bills
        ctx.filename_issues = filename_issues

        # --- สรุปต่อไฟล์ + ธงไฟล์ที่ parse แล้วได้ 0 บิล (น่าสงสัย ควรเช็คมือ) ---
        per_file = Counter(str(b.get("file", "")) for b in bills)
        parsed_files = set(per_file)
        for f in readable:
            base = os.path.basename(f)
            if base not in parsed_files and f not in parsed_files:
                # ระบบเดิมเก็บ b['file'] เป็น basename — เทียบทั้งสองแบบกันพลาด
                if not any(os.path.basename(str(k)) == base for k in per_file):
                    findings.append(Finding(
                        agent=self.name, code="IMPORT-NOBILLS", severity=Severity.WARNING.value,
                        message="parse ไฟล์ได้ แต่ไม่พบบิลในไฟล์นี้ (ตรวจรูปแบบ/ชีต)",
                        file=base, evidence={"path": f}))

        summary = {
            "files_in": len(file_list),
            "files_readable": len(readable),
            "files_skipped": len(file_list) - len(readable),
            "bills": len(bills),
            "filename_issues": len(filename_issues),
            "bills_per_file_top": per_file.most_common(5),
        }
        status = Status.OK.value
        return AgentResult(self.name, status, summary=summary, findings=findings)
