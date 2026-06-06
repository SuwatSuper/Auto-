# -*- coding: utf-8 -*-
"""
agents/contracts.py — โครงสร้างข้อมูลกลางที่ทุก agent ใช้ร่วมกัน (immutable-by-convention)

หลักการออกแบบ:
  - PipelineContext   : "สายพานข้อมูล" เส้นเดียวที่ไหลผ่านทุก agent ตามลำดับ DAG
                        orchestrator เป็นผู้ "เขียน" ฟิลด์ผลลัพธ์ลง context, agent อ่าน/เติม findings
  - AgentResult       : ผลลัพธ์มาตรฐานของ agent ทุกตัว (status + summary + findings + เวลา + error)
  - Finding           : ข้อสังเกต "เชิงคำแนะนำ" (advisory) 1 รายการ — ไม่ใช่คำตัดสินที่ไปแก้ Excel

⚠️ กฎเหล็ก: agent ฝั่ง review (Formula/VAT/WHT/TaxID/AI) **ห้าม mutate** bills/ผลตรวจหลัก
   จึงไม่กระทบ Excel byte-identical. ผลของมันไปอยู่ใน findings เท่านั้น (อ่านได้, ตามรอยได้, ทิ้งได้)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Status(str, Enum):
    """สถานะมาตรฐานของผล agent (เป็น str ด้วย เพื่อ serialize ลง JSON ได้ตรงๆ)."""
    OK = "ok"            # ทำงานครบ
    SKIPPED = "skipped"  # ข้ามโดยตั้งใจ (เช่น ปิดใช้งาน / ไม่มีข้อมูลให้ทำ / ไม่มี LLM)
    ERROR = "error"      # พังกลางคัน (ถูก error-boundary จับไว้ — pipeline ไปต่อได้ถ้า agent นี้ไม่ critical)


class Severity(str, Enum):
    """ระดับความสำคัญของ finding — สอดคล้องกับระบบเดิม (CRITICAL/ERROR/WARNING/INFO)."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass
class Finding:
    """ข้อสังเกตเชิงคำแนะนำ 1 รายการ (advisory). ไม่เปลี่ยนผลตรวจหลัก.

    เก็บ pointer กลับไปยังบิล (file/sheet/iv) เสมอ เพื่อให้คนตรวจไล่กลับได้
    """
    agent: str                       # agent ที่ออก finding นี้
    code: str                        # รหัสภายใน agent (เช่น FORMULA-X, VATX, AIX)
    severity: str = Severity.INFO.value
    message: str = ""                # ข้อความสรุปสั้นๆ (ภาษาคน)
    file: str = ""
    sheet: str = ""
    iv: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)  # ตัวเลข/บริบทประกอบ (ตามรอยได้)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent, "code": self.code, "severity": self.severity,
            "message": self.message, "file": self.file, "sheet": self.sheet,
            "iv": self.iv, "evidence": dict(self.evidence),
        }


@dataclass
class AgentResult:
    """ผลลัพธ์มาตรฐานของ agent ทุกตัว."""
    name: str
    status: str = Status.OK.value
    summary: Dict[str, Any] = field(default_factory=dict)   # metrics เชิงตัวเลข/สรุป
    findings: List[Finding] = field(default_factory=list)    # advisory list
    error: Optional[str] = None                              # ข้อความ error (ถ้า status=error)
    duration_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "status": self.status, "summary": dict(self.summary),
            "findings": [f.to_dict() for f in self.findings],
            "error": self.error, "duration_s": round(self.duration_s, 4),
        }


@dataclass
class PipelineContext:
    """สายพานข้อมูลเส้นเดียวที่ไหลผ่านทุก agent.

    ผู้เขียนฟิลด์ผลลัพธ์ (bills, summary, ...) = orchestrator (core audit step).
    agent review อ่านจากที่นี่และเติม results[name] เท่านั้น — ไม่แก้ของเดิม.
    """
    # ---------- inputs (กำหนดตอนเริ่ม) ----------
    master: Dict[str, Any] = field(default_factory=dict)
    file_list: List[str] = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)   # flags: report_dir, lean, enable_ai, ...

    # ---------- audit state (orchestrator เป็นผู้เติม ตามลำดับ pipeline) ----------
    bills: List[Dict[str, Any]] = field(default_factory=list)
    filename_issues: List[Any] = field(default_factory=list)
    # iv_issues = iv_seq + iv_date (รวม) — เป็นค่าที่ Report ใช้ (ตรงกับ main() เป๊ะ)
    iv_issues: List[Any] = field(default_factory=list)
    # เก็บแยกไว้ด้วย เพื่อพิสูจน์ byte-identical (golden_master เก็บ iv_seq/iv_date คนละช่อง)
    iv_seq: List[Any] = field(default_factory=list)
    iv_date: List[Any] = field(default_factory=list)
    typos: List[Any] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    dup_items: List[Any] = field(default_factory=list)
    report_path: Optional[str] = None

    # ---------- per-agent results (สะสมระหว่างรัน) ----------
    results: Dict[str, AgentResult] = field(default_factory=dict)

    # ---------- mesh (data plane): กระดานกลางสำหรับ findings ข้าม agent ----------
    #   ตั้งค่าโดย orchestrator ตอนเริ่ม (FindingsMesh). agent อ่าน peer ผ่านที่นี่แทน ad-hoc.
    #   เก็บเป็น Any เพื่อเลี่ยง import วน (mesh.py import contracts อยู่แล้ว)
    mesh: Optional[Any] = None

    # ---------- helpers ----------
    def record(self, result: AgentResult) -> None:
        """บันทึกผล agent ลง results และ (ถ้ามี mesh) publish findings เข้ากระดานกลางอัตโนมัติ.

        การ publish อัตโนมัติตรงนี้ทำให้ orchestrator ไม่ต้องสั่ง publish เอง และรับประกันว่า
        ลำดับ publish = ลำดับ record (ดีเทอร์มินิสติกตาม control plane).
        """
        self.results[result.name] = result
        if self.mesh is not None and result.findings:
            try:
                self.mesh.publish(result.findings)
            except Exception as _e:
                # mesh ต้องไม่ทำให้ pipeline ล้ม (advisory plane) — แต่ "ไม่กลืนเงียบ":
                # log ที่ stderr เพื่อให้บั๊กการ publish ถูกมองเห็น (เดิม pass เฉยๆ = ซ่อนปัญหา)
                import sys as _sys
                _sys.stderr.write(
                    f"[mesh] publish ล้มเหลวสำหรับ agent '{result.name}' "
                    f"({type(_e).__name__}: {_e}) — ข้าม findings ชุดนี้ (pipeline ไปต่อ)\n")

    def all_findings(self) -> List[Finding]:
        out: List[Finding] = []
        for r in self.results.values():
            out.extend(r.findings)
        return out

    def opt(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)


class _Timer:
    """context manager จับเวลา (ใช้ภายใน base.Agent)."""
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self.t0
        return False
