# -*- coding: utf-8 -*-
"""
agents/notepad_agent.py — NotepadAgent (ส่งออก, advisory)

เขียน "รายงานสรุปการทำงานของทุก agent + super" เป็นไฟล์ .txt (เปิดด้วย Notepad ได้ทันที).
รันท้ายสุดของสายการผลิต (หลัง report) เพื่อให้เห็นผลครบทุก agent.

⚠️ ADVISORY ONLY — อ่าน ctx อย่างเดียว, เขียนไฟล์ .txt แยกต่างหาก, **ไม่แตะ ctx.bills/ผลตรวจหลัก**
   → ไม่กระทบ byte-identical (ReportAgent ไม่อ่าน mesh; snapshot คิดจาก bills/summary เท่านั้น).
   ไม่ critical: พัง = pipeline ปกติ.

options:
  write_note : bool  — เขียนไฟล์ไหม (ดีฟอลต์ = ตาม write_report; โหมดพิสูจน์ปิด report = ปิด note ด้วย)
  note_path  : str   — พาธไฟล์ที่ต้องการ (ถ้าไม่ระบุ จะวางข้าง Excel หรือโฟลเดอร์ปัจจุบัน)
  report_dir : str   — โฟลเดอร์ผลลัพธ์ (ใช้ร่วมกับ ReportAgent)
"""
from __future__ import annotations

import os
from typing import Optional

from .base import Agent
from .contracts import AgentResult, Finding, PipelineContext, Severity, Status


class NotepadAgent(Agent):
    name = "notepad"
    description = "สรุปการทำงานของทุก agent + super เป็นไฟล์ .txt (Notepad) — advisory"
    critical = False

    def _run(self, ctx: PipelineContext) -> AgentResult:
        from .notepad_report import render
        text = render(ctx)

        # เขียนไฟล์ไหม: ดีฟอลต์ตาม write_report (โหมดพิสูจน์ write_report=False → ไม่เขียน)
        do_write = bool(ctx.opt("write_note", ctx.opt("write_report", True)))

        path: Optional[str] = None
        err: Optional[str] = None
        if do_write:
            path = self._resolve_path(ctx)
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                # UTF-8 BOM + CRLF → Notepad (รวมรุ่นเก่า) แสดงภาษาไทยถูกต้อง
                with open(path, "w", encoding="utf-8-sig", newline="") as fh:
                    fh.write(text.replace("\n", "\r\n"))
            except Exception as e:           # เขียนไม่ได้ก็ไม่ล้ม pipeline (advisory)
                err = f"{type(e).__name__}: {e}"
                path = None

        msg = (f"สร้างรายงาน Notepad → {path}" if path
               else ("สร้างรายงาน (ไม่เขียนไฟล์: write_note=False)" if not do_write
                     else f"สร้างรายงานแต่เขียนไฟล์ไม่ได้: {err}"))
        findings = [Finding(agent=self.name, code="NOTE-REPORT",
                            severity=Severity.INFO.value, message=msg,
                            evidence={"written": bool(path), "chars": len(text)})]
        summary = {"written": bool(path), "path": path, "chars": len(text),
                   "wrote_requested": do_write}
        if err:
            summary["write_error"] = err
        return AgentResult(self.name, Status.OK.value, summary=summary, findings=findings)

    # ---- เลือกพาธไฟล์: note_path > report_dir > ข้าง Excel > โฟลเดอร์ปัจจุบัน ----
    def _resolve_path(self, ctx: PipelineContext) -> str:
        p = ctx.opt("note_path")
        if p:
            return p
        d = ctx.opt("report_dir")
        if not d and ctx.report_path:
            d = os.path.dirname(ctx.report_path)
        if not d:
            try:
                from .report_agent import resolve_report_dir
                d = resolve_report_dir(ctx.options)
            except Exception:
                d = "."
        return os.path.join(d or ".", "agent_report.txt")
