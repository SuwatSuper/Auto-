# -*- coding: utf-8 -*-
"""
agents/vendor_report_agent.py — VendorReportAgent (ส่งออก, advisory)

"ตัวกรองอัจฉริยะ" ที่อ่านผล audit ที่ตกผลึกแล้ว → สร้าง **รายงานลูกค้ารายผู้ขาย (.txt)**
ภาษาคนล้วน พร้อมก๊อปส่งลูกค้าได้เลย (1 ไฟล์ / 1 vendor) ใน reports/.

รันหลัง ReportAgent (Excel) → "คุยกับ" ผลของ ReportAgent: อ้างพาธ Excel (ctx.report_path)
ในสรุป เพื่อให้ NotepadAgent (ที่รันถัดไป) รวมเป็นบทสรุปงานเดียว.

⚠️ ADVISORY/READ-ONLY: อ่าน ctx อย่างเดียว, เขียน .txt แยกต่างหาก, **ไม่แตะ ctx.bills/Excel/golden**.
   ไม่ critical: พัง = pipeline ปกติ (เป็น output เสริม).

options:
  write_vendor_report : bool — เขียนไฟล์ไหม (ดีฟอลต์ = ตาม write_report ; โหมดพิสูจน์ปิด = ไม่เขียน)
  vendor_report_dir   : str  — โฟลเดอร์ปลายทาง (ดีฟอลต์ = report_dir เดียวกับ Excel)
  vendor_report_memo  : str  — ข้อความ "หมายเหตุ :" ต่อท้ายทุกไฟล์ (optional)
"""

from __future__ import annotations

import os
from typing import List, Optional

from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status


class VendorReportAgent(Agent):
    name = "vendor_report"
    description = "สร้างรายงานลูกค้ารายผู้ขาย (.txt ภาษาคน พร้อมส่ง) ข้าง Excel — advisory ไม่แตะผลหลัก"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        from .vendor_report import build_vendor_reports

        bills = ctx.bills or []
        reports = build_vendor_reports(
            bills,
            ctx.summary,
            ctx.master,
            memo=str(ctx.opt("vendor_report_memo", "") or ""),
        )

        do_write = bool(ctx.opt("write_vendor_report", ctx.opt("write_report", True)))
        out_dir = self._resolve_dir(ctx)

        written: List[str] = []
        err: Optional[str] = None
        if do_write and reports:
            try:
                os.makedirs(out_dir, exist_ok=True)
                for fname, text in reports:
                    path = os.path.join(out_dir, fname)
                    # UTF-8 BOM + CRLF → Notepad/Windows อ่านภาษาไทย+emoji ถูก ; ก๊อปส่งได้ทันที
                    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                        fh.write(text.replace("\n", "\r\n"))
                    written.append(path)
            except Exception as e:  # เขียนไม่ได้ก็ไม่ล้ม pipeline (advisory)
                err = f"{type(e).__name__}: {e}"

        # "คุยกับ" ReportAgent: อ้าง Excel ที่เพิ่งสร้าง เพื่อให้สรุปงานเป็นชุดเดียว
        excel = ctx.report_path
        if written:
            msg = f"สร้างรายงานลูกค้า {len(written)} ไฟล์ → {out_dir}/"
            if excel:
                msg += f" (ข้าง Excel: {os.path.basename(excel)})"
        elif not do_write:
            msg = f"เตรียมรายงานลูกค้า {len(reports)} ผู้ขาย (ไม่เขียนไฟล์: write_vendor_report=False)"
        elif err:
            msg = f"เตรียมรายงานลูกค้าได้ แต่เขียนไฟล์ไม่ได้: {err}"
        else:
            msg = "ไม่มีบิลให้สร้างรายงานลูกค้า"

        findings = [
            Finding(
                agent=self.name,
                code="VENDOR-REPORT",
                severity=Severity.INFO.value,
                message=msg,
                evidence={
                    "vendors": len(reports),
                    "files_written": len(written),
                    "dir": out_dir,
                    "excel": os.path.abspath(excel) if excel else None,
                },
            )
        ]
        summary = {
            "vendors": len(reports),
            "files_written": len(written),
            "dir": out_dir,
            "wrote_requested": do_write,
            "excel_report": os.path.abspath(excel) if excel else None,
            "files": [os.path.basename(p) for p in written],
        }
        if err:
            summary["write_error"] = err
        return AgentResult(
            self.name, Status.OK.value, summary=summary, findings=findings
        )

    # ---- โฟลเดอร์ปลายทาง: vendor_report_dir > report_dir > ข้าง Excel > audit_reports ----
    def _resolve_dir(self, ctx: PipelineContext) -> str:
        d = ctx.opt("vendor_report_dir") or ctx.opt("report_dir")
        if not d and ctx.report_path:
            d = os.path.dirname(ctx.report_path)
        if not d:
            try:
                from .report_agent import resolve_report_dir

                d = resolve_report_dir(ctx.options)
            except Exception:
                d = "."
        return d or "."
