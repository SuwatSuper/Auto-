# -*- coding: utf-8 -*-
"""
agents/_shared.py — ตัวช่วยกลาง (pure) ที่ agent หลายตัวใช้ร่วมกัน

ทำไมต้องมีไฟล์นี้ (P-DEDUP):
  ก่อนหน้านี้โค้ดชุดเดียวกันถูก "ก๊อปวาง" กระจายหลายไฟล์ จนเสี่ยง drift:
    • _parse_llm_json()        — เหมือนกันเป๊ะใน ai_review / synthesis / super
    • _SEV_RANK (3/2/1/0)      — ซ้ำใน vat / taxid / super / notepad_report (+ inline ใน mesh, ai_review)
    • _max_sev()               — เหมือนกันใน vat / taxid
    • bill key "file|sheet|iv" — เขียนเองซ้ำใน confidence / super / mesh
  ถ้าแก้บั๊กในสำเนาเดียวแล้วลืมอีกสำเนา → พฤติกรรมเพี้ยนเงียบ. รวมไว้จุดเดียว = แก้ที่เดียว.

⚠️ โมดูลนี้ "บริสุทธิ์": import เฉพาะ stdlib + .contracts (ไม่แตะ core_access/เครื่องยนต์)
   → import ได้แม้ไม่มี engine, ไม่กระทบ byte-identical (อยู่ชั้น advisory ล้วน).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

# ลำดับความรุนแรงมาตรฐานของทั้งระบบ (ใช้จัดอันดับ/หา max) — แหล่งความจริงเดียว
SEV_RANK: Dict[str, int] = {"CRITICAL": 3, "ERROR": 2, "WARNING": 1, "INFO": 0}

__all__ = ["SEV_RANK", "max_severity", "bill_key", "parse_llm_json"]


def max_severity(issues, key=None) -> str:
    """คืน severity สูงสุดจาก list ของ issue/finding (ค่าเริ่มต้น 'INFO' ถ้าว่าง).

    Args:
        issues: iterable ของ dict (มีคีย์ 'severity') หรือ object (มี .severity)
        key:    ฟังก์ชันดึง severity จากแต่ละ item (ดีฟอลต์: รองรับทั้ง dict และ object)
    """
    if key is None:
        def key(it):
            if isinstance(it, dict):
                return it.get("severity", "INFO")
            return getattr(it, "severity", "INFO")
    best = "INFO"
    best_rank = SEV_RANK.get(best, 0)
    for it in issues or []:
        s = key(it) or "INFO"
        r = SEV_RANK.get(s, 0)
        if r > best_rank:
            best, best_rank = s, r
    return best


def bill_key(file: str, sheet: str, iv: str) -> str:
    """กุญแจอ้างอิงบิลมาตรฐาน (file|sheet|iv) — ใช้ทุกที่ที่ correlate ข้าม agent.

    ⚠️ อย่า reconstruct (file,sheet,iv) ด้วยการ split คีย์นี้กลับ — ถ้า field มี '|'
       จะแยกผิด. ให้เก็บ tuple ต้นฉบับไว้ต่างหากแล้วใช้ key นี้เป็น index เท่านั้น.
    """
    return f"{file}|{sheet}|{iv}"


def parse_llm_json(text: str, raw_fallback_key: Optional[str] = None) -> Dict[str, Any]:
    """แกะ JSON จากคำตอบ LLM แบบกันพัง (LLM อาจห่อด้วย ```json หรือมีข้อความนำ/ตาม).

    ลำดับการพยายาม:
      1) ตัด code fence แล้ว json.loads ทั้งก้อน
      2) จับ {...} ก้อนแรกที่ครอบคลุมแล้ว json.loads
      3) แกะไม่ได้เลย → ถ้ามี raw_fallback_key คืน {key: text[:500]} เพื่อคง "เนื้อความดิบ"
         (พฤติกรรมเดิมของ ai_review/synthesis), ไม่งั้นคืน {}.

    คืน dict เสมอ (ผู้เรียกใช้ .get() ต่อได้ปลอดภัย — ไม่ต้องกลัว None).
    """
    if not text:
        return {}
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            pass
    if raw_fallback_key:
        return {raw_fallback_key: t[:500]}
    return {}
