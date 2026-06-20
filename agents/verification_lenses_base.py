# -*- coding: utf-8 -*-
"""agents/verification_lenses_base.py — [F4 split] infra ร่วมของคลังเลนส์
(imports + ค่าคงที่โดเมน + _is_money_issue/_q2 + LensInput/Lens). byte-identical:
ย้ายมาจาก verification_lenses.py เป๊ะ. __all__ ครอบชื่อ _underscore เพื่อให้
`from ..._base import *` ปลายทาง (ext/main) เห็นครบเหมือน scope เดิม."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Callable, Dict, List, Tuple

from . import core_access as core
from ._shared import parse_llm_json

_D = core._D

# กลุ่มกฎ "แม่นสูง" (เลขคณิต/โครงสร้าง — ดีเทอร์มินิสติก, false-positive ต่ำ)
_HIGH_PRECISION = {
    "VAT001",
    "VAT002",
    "VAT003",
    "VAT005",
    "VAT007",
    "VAT009",
    "TAX001",
    "TAX002",
    "ITM001",
    "ITM017",
}
# กลุ่มกฎ "heuristic" (fuzzy/NLP/OCR/แนะนำ — false-positive สูงกว่า)
_HEURISTIC = {
    "ITM003",
    "ITM004",
    "ITM010",
    "ITM011",
    "ITM012",
    "TAX004",
    "ADDR002",
}
# เลนส์ที่เกี่ยวกับ "ยอดเงิน" (กลุ่มเลขคณิตออกเสียงเฉพาะ issue กลุ่มนี้)
_MONEY_PREFIXES = ("VAT", "ITM001", "ITM017", "ITM018")

# กฎโดเมนล็อก: VAT 7% เป๊ะ + ค่ายอมรับปัดเศษ (นักบัญชีปรับได้ที่จุดเดียวนี้)
_VAT_RATE = Decimal("0.07")
_VAT_ROUND_TOL = Decimal("0.01")  # ตรงถึงสตางค์ = "เป๊ะภายในปัดเศษ"
_MONEY_TOL = Decimal("0.01")  # ค่ายอมรับเลขคณิตยอด (qty×price, Σ, chain)
_ROUND_BAHT = Decimal("0.5")  # ส่วนต่าง ≤ 0.50 = อธิบายได้ด้วยปัดเศษ


def _is_money_issue(code: str) -> bool:
    return any(code.startswith(p) for p in _MONEY_PREFIXES)


def _q2(d: Decimal) -> Decimal:
    # [A-C1 2026-06-20] ห่อ quantize กัน InvalidOperation เมื่อยอดมหึมา (เกิน Decimal context 28 หลัก
    #   เช่น _D('1e30')). เดิม raise หลุดถึง _build_cross_index (รันครั้งเดียวก่อน loop เลนส์) → VerificationAgent
    #   ทั้งตัว error → ทิ้งผลโหวตของ "ทุกบิล" รวมบิลสะอาด (findings=0). engine ฮาร์ดเดนจุดนี้แล้ว (ADR-038);
    #   เลนส์เป็น sibling ที่ตกหล่น. คืนค่าเดิม (ไม่ปัด) เมื่อปัดไม่ได้ — เลนส์เปรียบเทียบด้วย tolerance อยู่แล้ว.
    try:
        return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return d


# ──────────────────────────────────────────────────────────────────────────
# Lens framework — "คลังผู้ตรวจเชิงกลไก" (ขยายจำนวนผู้ตรวจได้โดยไม่แตะ supervisor)
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class LensInput:
    """ข้อมูลที่เลนส์ตรวจ 1 ตัวมองเห็น (อ่านอย่างเดียว).
    index/master = ดัชนีข้ามบิล + ทะเบียนบริษัท (เติมครั้งเดียวใน _run, เลนส์อ่านอย่างเดียว).
    """

    bill: dict
    issue: dict
    code: str
    sev: str
    peers: List[dict]  # บิลพี่น้องในไฟล์เดียวกัน
    llm: object = None  # provider หรือ None (offline/ปิด)
    index: Dict = field(default_factory=dict)
    master: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class Lens:
    """ผู้ตรวจ 1 คน: id (key ใน votes), dimension (ความเชี่ยวชาญ — ใช้ในรายงาน),
    fn (ฟังก์ชันบริสุทธิ์: LensInput -> (vote, reason))."""

    id: str
    dimension: str
    fn: Callable[[LensInput], Tuple[int, str]]

__all__ = [
    'Counter',
    'defaultdict',
    'dataclass',
    'field',
    'Decimal',
    'ROUND_HALF_UP',
    'Callable',
    'Dict',
    'List',
    'Tuple',
    'core',
    'parse_llm_json',
    '_D',
    '_HIGH_PRECISION',
    '_HEURISTIC',
    '_MONEY_PREFIXES',
    '_VAT_RATE',
    '_VAT_ROUND_TOL',
    '_MONEY_TOL',
    '_ROUND_BAHT',
    '_is_money_issue',
    '_q2',
    'LensInput',
    'Lens',
]
