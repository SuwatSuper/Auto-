# -*- coding: utf-8 -*-
"""mesh_contract.py — สัญญา "ผู้ผลิตข้อมูลครบ" ของ data plane (FindingsMesh)

ปัญหาที่แก้ (P2):
  Tier-2 (crosscheck/confidence) "อ่าน mesh แบบ implicit" — ถ้า Tier-1 ตัวใด **isolated-fail**
  มันจะ publish น้อยลง/ไม่ publish โดย pipeline ยังไปต่อ (error boundary). ผลคือ correlate_by_bill
  และคะแนน confidence "เพี้ยนเงียบ" (น้อยลงเพราะหลักฐานหาย ไม่ใช่เพราะบิลสะอาด) โดยไม่มีใครรู้.

วิธี: ตรวจว่า "ผู้ผลิตชั้น Tier-1 ที่คาดไว้" รันครบและสถานะ ok จริงไหม ก่อนเชื่อผล Tier-2.
  ใช้ 2 สัญญาณรวมกัน (ตามที่ออกแบบไว้):
    • ctx.results[name].status  — รันถึงและสำเร็จไหม (ของจริงที่บอก "พัง/ข้าม/ไม่รัน")
    • mesh.agents_seen()        — โพสต์เข้ากระดานหรือยัง (รองรับเคส "รัน ok แต่ไม่เจออะไร")

  จำแนก:
    missing  = คาดไว้ แต่ไม่อยู่ใน results (ไม่ได้รันเลย)        → ละเมิดสัญญา
    errored  = อยู่ใน results แต่ status == 'error'             → ละเมิดสัญญา
    skipped  = status == 'skipped' (ตั้งใจข้าม)                  → เตือน (ไม่นับละเมิดเข้ม)
    ran_ok   = status == 'ok'
    silent   = ran_ok แต่ไม่อยู่ใน agents_seen() (รันแล้วแต่ 0 finding) → INFO เท่านั้น (ถูกต้องได้)
    violations = missing + errored  ← เคสอันตรายที่ทำ Tier-2 เพี้ยนเงียบ

โมดูลนี้ "บริสุทธิ์" (ไม่ import config/agents/หนัก) → import จากที่ไหนก็ได้ ไม่ผูกลำดับ.
ผลเป็น advisory ล้วน — ไม่แตะ ctx.bills/ผลตรวจหลัก → ไม่กระทบ golden hash.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ผู้ผลิตชั้น Tier-1 ที่คาดว่าต้องครบ (ตรงกับ orchestrator._review_agents / crosscheck._TIER1)
DEFAULT_TIER1: Tuple[str, ...] = ("formula", "vat", "wht", "taxid")

# สถานะมาตรฐาน (ตรงกับ agents.contracts.Status — เก็บเป็น literal เพื่อไม่ผูก import)
_ST_OK = "ok"
_ST_ERROR = "error"
_ST_SKIPPED = "skipped"


def _status_of(result: Any) -> Optional[str]:
    """อ่าน .status จาก AgentResult แบบทนทาน (None = ไม่มีผล)."""
    if result is None:
        return None
    return getattr(result, "status", None)


def verify_producers(results: Dict[str, Any],
                     mesh: Any,
                     expected: Tuple[str, ...] = DEFAULT_TIER1) -> Dict[str, Any]:
    """ตรวจสัญญาผู้ผลิต. คืน dict (ตามรอยได้ทุกหมวด).

    Args:
        results : ctx.results (name -> AgentResult)
        mesh    : ctx.mesh (มี agents_seen()) — None ได้ (จะถือว่า seen=[])
        expected: รายชื่อผู้ผลิต Tier-1 ที่คาดว่าต้องครบ
    """
    expected = tuple(expected)
    results = results or {}
    try:
        seen = list(mesh.agents_seen()) if mesh is not None else []
    except Exception:
        seen = []
    seen_set = set(seen)

    missing: List[str] = []
    errored: List[str] = []
    skipped: List[str] = []
    ran_ok: List[str] = []
    for name in expected:
        if name not in results:
            missing.append(name)
            continue
        st = _status_of(results.get(name))
        if st == _ST_ERROR:
            errored.append(name)
        elif st == _ST_SKIPPED:
            skipped.append(name)
        elif st == _ST_OK:
            ran_ok.append(name)
        else:
            # สถานะแปลก/ไม่รู้จัก → ถือว่าไม่ปลอดภัย (นับเป็น errored)
            errored.append(name)

    # รัน ok แต่ไม่โพสต์อะไรเข้า mesh — ถูกต้องได้ (บิลสะอาด) → INFO เท่านั้น
    silent = [n for n in ran_ok if n not in seen_set]
    violations = missing + errored

    return {
        "ok": not violations,
        "expected": list(expected),
        "seen": sorted(seen_set & set(expected)),   # เฉพาะที่เกี่ยวกับ Tier-1
        "missing": missing,
        "errored": errored,
        "skipped": skipped,
        "ran_ok": ran_ok,
        "silent": silent,
        "violations": violations,
    }


def summary_dict(report: Dict[str, Any]) -> Dict[str, Any]:
    """ย่อรายงานสำหรับใส่ AgentResult.summary (กระชับ ตามรอยได้)."""
    return {
        "ok": report["ok"],
        "expected": report["expected"],
        "missing": report["missing"],
        "errored": report["errored"],
        "skipped": report["skipped"],
        "silent": report["silent"],
    }


def violation_message(report: Dict[str, Any]) -> str:
    """ข้อความ (ภาษาคน) อธิบายการละเมิดสัญญา — ใช้เป็น message ของ Finding."""
    parts: List[str] = []
    if report["missing"]:
        parts.append("ไม่ได้รัน: " + ", ".join(report["missing"]))
    if report["errored"]:
        parts.append("ล้มเหลว: " + ", ".join(report["errored"]))
    detail = " | ".join(parts) if parts else "—"
    return ("สัญญา mesh ไม่ครบ: ผู้ตรวจชั้น Tier-1 บางตัวไม่ส่งผลเข้ากระดานกลาง "
            f"({detail}) → ผลสังเคราะห์ของ Tier-2 (cross-confirm/คะแนนความเชื่อมั่น) "
            "อาจต่ำกว่าจริงเพราะหลักฐานหาย ไม่ใช่เพราะบิลสะอาด — โปรดตรวจ log ของ agent ที่ล้ม")
