# -*- coding: utf-8 -*-
"""
agents/report_agent.py — Report Agent (Python ปกติ, CRITICAL)

หน้าที่: สร้างไฟล์ Excel ผลตรวจ — เหมือนเดิม 100% (พิสูจน์ด้วย oracle/golden-master)
  ห่อฟังก์ชันเดิม:
    - LEAN  → build_clean_report(...)  (7 ชีต + dashboard)
    - FULL  → export_excel(...) + run_addon_pack(...)
  ไม่แตะ layout/ชีต/ตัวเลข — เป็น stage ปลายทางที่เขียนผลออก

หมายเหตุ (stability fix): ค่า default ของโฟลเดอร์รายงานในที่นี้ใช้ path ที่พกพาได้
  (os.getcwd()/audit_reports) แทน hardcoded Windows path เดิมในต้นฉบับ main()
  — เป็น "config" ไม่ใช่ logic → ไม่กระทบผลตรวจ (oracle จับ fingerprint ก่อนขั้น save)
"""
from __future__ import annotations

import os
from datetime import datetime

from . import core_access as core
from .base import Agent, AgentError
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status


def resolve_report_dir(options) -> str:
    """หาโฟลเดอร์ปลายทางแบบพกพา. ลำดับความสำคัญ:
       options['report_dir'] > env PUKPUI_REPORT_DIR > ./audit_reports
    """
    d = (options.get("report_dir")
         or os.environ.get("PUKPUI_REPORT_DIR")
         or os.path.join(os.getcwd(), "audit_reports"))
    return d


class ReportAgent(Agent):
    name = "report"
    description = "สร้าง Excel ผลตรวจ (เหมือนเดิม) — ห่อ build_clean_report/export_excel"
    critical = True   # สร้างรายงานไม่ได้ = งานไม่ส่งมอบ → หยุด

    def _run(self, ctx: PipelineContext) -> AgentResult:
        bills = ctx.bills or []
        if not bills:
            raise AgentError("ไม่มีบิลให้สร้างรายงาน")

        report_dir = resolve_report_dir(ctx.options)
        try:
            os.makedirs(report_dir, exist_ok=True)
        except Exception as e:
            # เขียนโฟลเดอร์ที่ขอไม่ได้ → ตกไปที่ cwd (เหมือนพฤติกรรม v8.4 เดิม) ไม่ล้มทั้งงาน
            report_dir = os.getcwd()

        # หมายเหตุ: cross-checks (DT004/DOC001) ถูกเรียกใน orchestrator core แล้ว (run-once)
        #   จึงไม่เรียกซ้ำที่นี่ — กันการเติม issue ซ้ำ (ซึ่งจะทำให้ Excel ไม่ byte-identical)
        fname = ctx.opt("report_name") or f"audit_v58_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        out = os.path.join(report_dir, fname)

        lean = bool(ctx.opt("lean", True))
        args = (bills, ctx.summary, ctx.iv_issues, ctx.typos, ctx.filename_issues, out)

        if lean:
            ok = core.core.build_clean_report(*args)
        else:
            ok = core.core.export_excel(*args)
            if ok:
                run_addon = core.get("run_addon_pack")
                if run_addon is not None:
                    try:
                        run_addon(bills, out)
                    except Exception as e:
                        # addon pack เป็น shoulder feature — พังไม่ควรล้มรายงานหลัก
                        pass

        if not ok or not os.path.isfile(out):
            raise AgentError(f"สร้างรายงานไม่สำเร็จ ({'LEAN' if lean else 'FULL'}) → {out}")

        ctx.report_path = out
        findings = [Finding(
            agent=self.name, code="REPORT-OK", severity=Severity.INFO.value,
            message=f"บันทึกรายงาน {'คลีน' if lean else 'เต็ม'} แล้ว",
            evidence={"path": os.path.abspath(out),
                      "size_bytes": os.path.getsize(out)})]
        summary = {
            "mode": "lean" if lean else "full",
            "path": os.path.abspath(out),
            "size_bytes": os.path.getsize(out),
            "bills": len(bills),
        }
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)
