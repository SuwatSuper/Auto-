# -*- coding: utf-8 -*-
"""
agents/mesh.py — FindingsMesh: กระดานกลาง (blackboard) ของสถาปัตยกรรม Hybrid Hierarchical + Mesh

บทบาทใน 2 ระนาบ (two-plane architecture):
  • Control plane  = orchestrator (ลำดับชั้น/ดีเทอร์มินิสติก) — ตัดสินว่า "ใครรันเมื่อไหร่"
  • Data plane     = FindingsMesh (ตาข่าย/แนวราบ) — ตัดสินว่า "ใครเห็นผลของใคร"

ทำไมต้องมี mesh แยกจาก ctx.results:
  เดิม agent อ่านผลเพื่อนผ่าน ctx.results.get(name).findings แบบ ad-hoc (ฮาร์ดโค้ดชื่อ)
  → เปราะ (พิมพ์ชื่อผิด = เงียบ), ไม่มี query แบบ by-bill/by-severity/by-code,
    ไม่มี dedup/provenance, ขยายยาก. mesh ให้ API กลางที่:
      - publish(findings)              : agent โพสต์ผลเข้ากระดาน
      - by_agent / by_severity / by_code / by_bill / since(seq)  : query หลายมุม
      - correlate_by_bill()            : จับบิลที่ "หลาย agent สงสัยพร้อมกัน" (หัวใจของ mesh)
  โดย **ขนเฉพาะ Finding (advisory)** — ไม่แตะ ctx.bills/ผลทางการ → Excel ยัง byte-identical

immutable-by-convention: ผู้บริโภคไม่ควรแก้ Finding ที่ดึงไป (อ่านอย่างเดียว)
deterministic: ลำดับ publish ถูกกำหนดโดย orchestrator (hierarchical) → query ผลคงที่
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from ._shared import SEV_RANK as _RANK, bill_key
from .contracts import Finding


def _bill_key(f: Finding) -> str:
    """กุญแจอ้างอิงบิลของ finding (file|sheet|iv) — ใช้จับ cross-agent correlation."""
    return bill_key(f.file, f.sheet, f.iv)


class FindingsMesh:
    """กระดานกลางสำหรับ findings เชิงคำแนะนำ (advisory) ที่ทุก agent โพสต์/อ่านได้.

    ไม่ผูกกับ orchestrator: ส่งเข้าไปใน PipelineContext ให้ agent ทุกตัวใช้ร่วม.
    ทุก method query คืน **list ใหม่** (ไม่คืน internal list ตรง ๆ) เพื่อกันการแก้ข้าม agent.
    """

    def __init__(self) -> None:
        self._findings: List[Finding] = []          # ลำดับ publish (deterministic by orchestrator)
        self._by_agent: Dict[str, List[Finding]] = defaultdict(list)
        self._by_bill: Dict[str, List[Finding]] = defaultdict(list)
        # key -> (file, sheet, iv) ต้นฉบับ — เก็บไว้แทนการ split คีย์กลับ (กัน field มี '|' แล้วเพี้ยน)
        self._bill_ref: Dict[str, tuple] = {}

    # ---------- publish (producer side) ----------
    def publish(self, findings: List[Finding]) -> int:
        """โพสต์ findings เข้า mesh. คืนจำนวนที่รับเข้า.

        ปลอดภัยเสมอ: ตัวที่ไม่ใช่ Finding จะถูกข้าม (ไม่ throw) เพื่อไม่ให้ agent ตัวเดียวล้ม mesh.
        """
        n = 0
        for f in (findings or []):
            if not isinstance(f, Finding):
                continue
            self._findings.append(f)
            self._by_agent[f.agent].append(f)
            k = _bill_key(f)
            self._by_bill[k].append(f)
            self._bill_ref.setdefault(k, (f.file, f.sheet, f.iv))
            n += 1
        return n

    # ---------- query (consumer side) — คืน list ใหม่เสมอ ----------
    def all(self) -> List[Finding]:
        """ทุก finding ตามลำดับ publish."""
        return list(self._findings)

    def by_agent(self, *names: str) -> List[Finding]:
        """findings ของ agent ที่ระบุ (หลายชื่อได้)."""
        out: List[Finding] = []
        for nm in names:
            out.extend(self._by_agent.get(nm, []))
        return out

    def by_severity(self, *severities: str) -> List[Finding]:
        """findings ที่ severity ตรงกับที่ระบุ (เช่น 'CRITICAL','ERROR')."""
        sev = set(severities)
        return [f for f in self._findings if f.severity in sev]

    def by_code(self, *codes: str) -> List[Finding]:
        """findings ตาม code ภายใน agent (เช่น 'VATX','FORMULA-MISMATCH')."""
        cs = set(codes)
        return [f for f in self._findings if f.code in cs]

    def by_code_prefix(self, *prefixes: str) -> List[Finding]:
        """findings ที่ code ขึ้นต้นด้วย prefix (เช่น 'AI-','VAT')."""
        return [f for f in self._findings
                if any(f.code.startswith(p) for p in prefixes)]

    def by_bill(self, file: str, sheet: str, iv: str) -> List[Finding]:
        """findings ทั้งหมดที่ชี้ไปยังบิลใบเดียวกัน (file/sheet/iv)."""
        return list(self._by_bill.get(bill_key(file, sheet, iv), []))

    def since(self, seq: int) -> List[Finding]:
        """findings ตั้งแต่ index `seq` เป็นต้นไป (ให้ agent อ่าน 'ของใหม่หลังจุดหนึ่ง')."""
        if seq < 0:
            seq = 0
        return self._findings[seq:]

    def count(self) -> int:
        """จำนวน finding ปัจจุบันใน mesh (ใช้เป็น cursor ให้ since())."""
        return len(self._findings)

    def agents_seen(self) -> List[str]:
        """รายชื่อ agent ที่เคยโพสต์เข้า mesh (เรียงตามตัวอักษร — เสถียร)."""
        return sorted(self._by_agent.keys())

    # ---------- correlation (หัวใจของ mesh: รวมมุมมองข้าม agent) ----------
    def correlate_by_bill(self, min_agents: int = 2) -> List[Dict]:
        """จับบิลที่ถูก ">= min_agents ตัว" ธงพร้อมกัน → สัญญาณความเชื่อมั่นสูง.

        คืน list ของ dict (เรียงจากจำนวน agent มาก→น้อย แล้วตาม bill key — deterministic):
            {
              "file","sheet","iv",
              "agents":   [ชื่อ agent ที่ธงบิลนี้ (เรียง)],
              "n_agents": k,
              "codes":    [code ที่เกี่ยว (เรียง)],
              "max_severity": "CRITICAL|ERROR|WARNING|INFO",
              "findings": [Finding ...]   # ดิบ เผื่อ consumer ใช้ต่อ
            }
        ใช้โดย CrossCheckAgent/ConfidenceAgent เพื่อยก/ลดความสำคัญแบบ cross-validated.
        """
        rows: List[Dict] = []
        for bkey, fs in self._by_bill.items():
            agents = sorted({f.agent for f in fs})
            if len(agents) < min_agents:
                continue
            file, sheet, iv = self._bill_ref.get(bkey, (bkey, "", ""))
            codes = sorted({f.code for f in fs})
            max_sev = max((f.severity for f in fs), key=lambda s: _RANK.get(s, 0))
            rows.append({
                "file": file, "sheet": sheet, "iv": iv,
                "agents": agents, "n_agents": len(agents),
                "codes": codes, "max_severity": max_sev,
                "findings": list(fs),
            })
        # เรียง deterministic: agent มากก่อน, แล้ว severity สูงก่อน, แล้ว bill key
        rows.sort(key=lambda r: (-r["n_agents"], -_RANK.get(r["max_severity"], 0),
                                 r["file"], r["sheet"], r["iv"]))
        return rows

    def stats(self) -> Dict[str, int]:
        """สรุปเชิงตัวเลขของ mesh (ใส่ลง summary ได้)."""
        by_sev: Dict[str, int] = defaultdict(int)
        for f in self._findings:
            by_sev[f.severity] += 1
        return {
            "total": len(self._findings),
            "agents": len(self._by_agent),
            "bills_touched": len(self._by_bill),
            **{f"sev_{k}": v for k, v in by_sev.items()},
        }
