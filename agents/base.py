# -*- coding: utf-8 -*-
"""
agents/base.py — คลาสฐานของ agent ทุกตัว

ทำไมต้องมีฐานร่วม (แทนที่จะให้แต่ละ agent เขียน try/except เอง):
  1. Error boundary สม่ำเสมอ  — agent พังต้องไม่ล้มทั้ง pipeline (สำหรับ agent ที่ไม่ critical)
                                  สะท้อนปรัชญา P1-FIX-ISOLATION ของระบบเดิม (validators แยก try/except)
  2. จับเวลา/observability      — รู้ทุกครั้งว่า agent ไหนช้า/พัง โดยไม่ต้องเดา
  3. สัญญา (contract) เดียวกัน  — ทุก agent คืน AgentResult เสมอ (orchestrator จัดการแบบ uniform)

critical=True  → agent นี้พัง = หยุด pipeline (เช่น Import ไม่มีบิล, Report เขียนไฟล์ไม่ได้)
critical=False → agent นี้พัง = log + ไปต่อ (review/AI เป็น advisory ทิ้งได้)
"""
from __future__ import annotations

import traceback
from abc import ABC, abstractmethod
from typing import List

from .contracts import AgentResult, PipelineContext, Status, _Timer


class AgentError(Exception):
    """error ที่ critical agent โยนเพื่อสั่งหยุด pipeline อย่างชัดเจน (ตั้งใจ ไม่ใช่บั๊ก).

    [C1-FIX] พก `result` (AgentResult ที่มี traceback เต็ม) ไว้ด้วย — เดิม run() สร้างผล error
    ละเอียดแล้วถูกทิ้งตอน raise, orchestrator จึงบันทึกผลบางๆ ไร้ traceback ในจุดที่สำคัญที่สุด
    (critical crash). ผูก result ไว้ให้ผู้จับบันทึกของจริงได้.
    """
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result


class Agent(ABC):
    """คลาสฐาน. subclass implement `_run(ctx) -> AgentResult` เท่านั้น.

    การห่อ error/เวลา/log ทำที่ `run()` (ห้าม override) เพื่อให้พฤติกรรมสม่ำเสมอทั้งระบบ.
    """

    #: ชื่อ agent (ใช้เป็น key ใน ctx.results และในรายงาน) — subclass ต้องตั้ง
    name: str = "agent"
    #: คำอธิบายสั้นๆ ว่า agent นี้ทำอะไร
    description: str = ""
    #: True = พังแล้วหยุด pipeline / False = พังแล้วไปต่อ
    critical: bool = False

    def __init__(self, logger=None):
        # logger เป็น optional — ถ้าไม่ส่งมาใช้ print เบาๆ (ไม่ผูกกับ logging framework ใด)
        self._log = logger or (lambda msg: None)

    # ---- public, ห้าม override: ห่อ error-boundary + timing + log ----
    def run(self, ctx: PipelineContext) -> AgentResult:
        timer = _Timer()
        try:
            with timer:
                result = self._run(ctx)
            if result is None:  # กัน subclass ลืม return
                result = AgentResult(self.name, Status.OK.value)
            result.duration_s = timer.elapsed
            self._log(f"[{self.name}] {result.status} "
                      f"({len(result.findings)} findings, {result.duration_s:.3f}s)")
            return result
        except AgentError as e:
            # critical agent สั่งหยุดเอง — ปล่อยขึ้นไปให้ orchestrator ตัดสินใจ
            self._log(f"[{self.name}] CRITICAL STOP: {e}")
            raise
        except Exception as e:
            elapsed = getattr(timer, "elapsed", 0.0)
            tb = traceback.format_exc(limit=4)
            self._log(f"[{self.name}] ERROR (isolated): {type(e).__name__}: {e}")
            res = AgentResult(
                name=self.name, status=Status.ERROR.value,
                error=f"{type(e).__name__}: {e}\n{tb}", duration_s=elapsed,
            )
            if self.critical:
                # critical แต่ดันโยน exception ธรรมดา → แปลงเป็น AgentError เพื่อหยุดอย่างชัดเจน
                #   [C1-FIX] แนบ res (มี traceback เต็ม) ไปด้วย เพื่อให้ orchestrator บันทึกของจริง
                raise AgentError(f"{self.name} (critical) ล้มเหลว: {e}", result=res) from e
            return res

    @abstractmethod
    def _run(self, ctx: PipelineContext) -> AgentResult:
        """โค้ดจริงของ agent. คืน AgentResult. ห้ามจับ exception เองถ้าไม่จำเป็น
        (ปล่อยให้ base จับ เพื่อความสม่ำเสมอ)."""
        raise NotImplementedError


# ---------- helper ที่ agent review ใช้บ่อย ----------

def bill_ref(b: dict) -> dict:
    """ดึง pointer มาตรฐานของบิล (file/sheet/iv) สำหรับใส่ใน Finding."""
    return {
        "file": str(b.get("file", "")),
        "sheet": str(b.get("sheet", "")),
        "iv": str(b.get("iv_number") or "-"),
    }


def issues_with_prefix(b: dict, *prefixes: str) -> List[dict]:
    """คืน issue (ที่ระบบหลักตรวจแล้ว) ของบิลที่ code ขึ้นต้นด้วย prefix ที่ระบุ.

    ใช้ให้ domain agent (VAT/TaxID) อ่านผล "ที่เป็นทางการ" จาก pipeline หลัก
    แทนการรันกฎเองใหม่ (ซึ่งจะเปลี่ยนลำดับ → กระทบ byte-identical).
    """
    out = []
    for iss in (b.get("issues") or []):
        code = str(iss.get("code", ""))
        if any(code.startswith(p) for p in prefixes):
            out.append(iss)
    return out
