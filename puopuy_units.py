# -*- coding: utf-8 -*-
"""puopuy_units.py — LEAF UTILITY LAYER (unit + Decimal helpers)

⚠️ RECONSTRUCTED MODULE (v9-rebuild 2026-06)
   ต้นฉบับเดิมหายจากแพ็กเกจที่ส่งมอบ (ไม่อยู่ใน ZIP / ไม่มีใน .pyc / ไม่มีสำเนาในโค้ด).
   ไฟล์นี้สร้างขึ้นใหม่จาก "หลักฐานที่ยังเหลือ" เพื่อให้ระบบกลับมารันได้:
     • extract_unit_hint  ← ใช้ข้อมูลจริง UNIT_HINT_PATTERNS จาก config.py  (FAITHFUL)
     • _unit_canon        ← ใช้ synonym groups ชุดเดียวกับ rules_engine.r_itm005 (FAITHFUL)
     • _D                 ← contract มาตรฐาน (None/blank/unparseable → None)        (FAITHFUL)
     • _vat_tolerance     ← [OBJ-1A 2026-06] คืนสู่ "สูตรเดิมที่มีหลักฐานว่าพิสูจน์แล้ว"  (RESTORED ✓)
   ทุกค่าที่เป็น APPROX ทำเครื่องหมายไว้ — ถ้าเจอต้นฉบับใน source control ให้ diff ทับได้ทันที.
   _vat_tolerance ไม่ใช่ APPROX แล้ว: เปลี่ยนกลับเป็นสูตรเดิม 0.5 + |sub|/100000 อย่างตั้งใจ
   (เหตุผล/หลักฐาน/ค่าเก่า-ใหม่ ดูบล็อกเหนือ _vat_tolerance + REBUILD_STATUS_TH.md ข้อ OBJ-1A).

ตำแหน่งใน DAG:  config/state → [puopuy_units] → parser/rules → main  (leaf; พึ่ง config ได้, ไม่มี cycle)
"""
from __future__ import annotations

from typing import Any

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# config เป็น base ของ DAG (ไม่ import puopuy_units กลับ → ไม่มี circular)
from config import UNIT_HINT_PATTERNS


# ───────────────────────── Decimal helper (FAITHFUL) ─────────────────────────
def _D(x: Any) -> Decimal | None:
    """แปลงเป็น Decimal; None/ว่าง/แปลงไม่ได้ → None.

    Contract สรุปจาก call sites (rules_engine.r_vat001/002/003, formula/vat agents):
      - รับ None ได้ (formula_agent: _D(b.get(key)))
      - รับ float/int/Decimal/str ที่มี comma/฿/ช่องว่างล่องหน
      - คืน None เมื่อแปลงไม่ได้ (ผู้เรียกเช็ค `if x is None`)
      - bool ไม่ใช่ตัวเลขเชิงบัญชี → None (กัน True==1 หลุด)
    """
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, Decimal):
        return x if x.is_finite() else None   # [BUGFIX recheck #4] กัน Decimal('inf'/'nan')
    if isinstance(x, (int, float)):
        try:
            d = Decimal(str(x))
        except (InvalidOperation, ValueError):
            return None
        return d if d.is_finite() else None   # [BUGFIX recheck #4] กัน float inf/nan
    s = str(x).strip()
    if not s:
        return None
    # ล้างสัญลักษณ์เงิน/คั่นหลัก/อักขระล่องหน ก่อนแปลง
    s = (s.replace(',', '').replace('฿', '')
           .replace('\xa0', '').replace('\u200b', '').replace('\ufeff', '').strip())
    if not s:
        return None
    # [L2] เลขติดลบรูปแบบบัญชี '(1234.56)' → -1234.56 (เดิมคืน None ทิ้งค่าเงียบ).
    #   เฉพาะ '(ตัวเลขล้วน)' เท่านั้น — ข้อความอื่นในวงเล็บยังคืน None ตามเดิม → golden-neutral บน corpus.
    _neg = False
    if len(s) >= 3 and s[0] == '(' and s[-1] == ')':
        _inner = s[1:-1].strip()
        if re.fullmatch(r'\d+(?:\.\d+)?', _inner):
            s, _neg = _inner, True
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if _neg:
        d = -d
    return d if d.is_finite() else None   # [BUGFIX recheck #4] กัน "nan"/"inf" (is_finite). หมายเหตุ: ค่ามหึมา-finite (เช่น 1e999) ผ่านที่นี่โดยตั้งใจ — ถูกกันตอน quantize ใน _money_q (H1/ADR-038)


# ───────────── VAT tolerance (RESTORED — สูตรเดิมที่มีหลักฐานว่าพิสูจน์แล้ว) ─────────────
# ใช้เฉพาะใน r_vat001: เทียบ Σ(amount รายการ) กับ subtotal.
#
# [OBJ-1A · 2026-06 · การเปลี่ยน business logic อย่างตั้งใจ]
#   เดิมโมดูลนี้ "เดา" สูตรขึ้นใหม่ (นึกว่าต้นฉบับหาย) แล้วตั้งหลวมเกินไป:
#       ค่าเก่า (reconstructed / APPROX) : max(1.00, 0.005·|subtotal|)
#       ค่าใหม่ (restored / documented)   : 0.5 + |subtotal|/100000
#   สูตรเก่าหลวมกว่า 83–484 เท่า (ยิ่งบิลใหญ่ยิ่งหลวม) = false-negative landmine:
#   บิลยอดสูงที่ผลรวมรายการ ≠ subtotal จะถูกปล่อยผ่านเงียบ ไม่ฟ้อง VAT001.
#   ตัวอย่าง: subtotal 1,530,236 — สูตรเก่าปล่อยส่วนต่างได้ถึง 7,651 บาท, สูตรใหม่ปล่อยแค่ 15.80 บาท.
#
#   หลักฐานเชิงประจักษ์ (ข้อมูลจริง 81 ไฟล์ / 631 บิลที่เข้าเกณฑ์):
#       • ทุกบิลกระทบยอดตรงระดับ ≤ 1e-10 บาท → VAT001 ฟ้อง 0 ใบ "ทั้งสองสูตร"
#       • จึงพิสูจน์แล้วว่า golden hash ไม่ขยับ (ยังเป็น ec61907f…) — ไม่ต้อง regenerate baseline
#       • ค่าถูกตรึงด้วย test_pinned_logic.py (ถ้าใครแก้สูตรเงียบ ๆ ภายหลัง = เทสล้มทันที)
#
#   None / แปลงไม่ได้ → คืนฐาน 0.5 (พจน์ |sub|/100000 = 0).
# ───────────── อัตรา VAT (แหล่งความจริงเดียวของ "7%") ─────────────
# [OBJ-CONSISTENCY 2026-06] เดิมเลข Decimal('0.07') ถูกฮาร์ดโค้ดซ้ำในหลายไฟล์
#   (rules_engine_rules_b/c, parser_p0a/p2 และ agent อีก 2 ไฟล์มี _SEVEN_PCT/_VAT_RATE ของตัวเอง).
#   ตั้งค่ากลางที่ leaf money-math นี้ (parser + rules_engine import จากที่นี่ตรง ๆ) → ถ้าวันหนึ่ง
#   อัตราเปลี่ยน แก้จุดเดียว. ค่า = Decimal('0.07') เป๊ะ → golden hash ไม่ขยับ (พิสูจน์ด้วยชุดเทส).
VAT_RATE = Decimal('0.07')              # อัตราภาษีมูลค่าเพิ่ม 7% (สูตร: VAT = _money_q(subtotal × VAT_RATE))


def _money_q(x: Any) -> float | None:
    """[F-1 · OBJ-CONSISTENCY] ปัดเงินเป็น 2 ตำแหน่ง (สตางค์) แบบ ROUND_HALF_UP — แหล่งความจริงเดียว.
    คืน float (คงชนิดที่เก็บ). None/แปลงไม่ได้ → None.

    เหตุผล: เดิมจุดเติม/derive ยอดใช้ round(x,2) ของ Python = banker's rounding (half-to-even)
      ขัดกับกฎของระบบ "เงินทุกค่าใช้ Decimal+ROUND_HALF_UP". ที่ขอบครึ่งสตางค์ (.xx5) ผลต่าง 0.01
      (เช่น SHS_68_117 ช.7: round(8742.125,2)=8742.12 แต่ HALF_UP=8742.13). _money_q รวมการปัด
      ไว้จุดเดียวให้ทั้งระบบปัดแบบเดียวกัน (เหมือน path VAT-จาก-subtotal ที่ทำถูกอยู่แล้ว)."""
    d = _D(x)
    if d is None:
        return None
    # [H1/ADR-038] กัน Decimal.quantize ระเบิด InvalidOperation เมื่อค่ามหึมา (เกิน context 28 หลัก
    #   เช่น 1e30 จากเซลล์ผิดเพี้ยน). เดิม raise หลุดผ่าน call site ที่ไม่ห่อ (parser_p2:113/129,
    #   parser_p0a:126, _reconcile_amounts) → parse_file ดักระดับชีต → "บิลทั้งชีตหายเงียบ".
    #   คืน None แทน (สอดคล้องสัญญา _D: แปลงเป็นเงินไม่ได้ → None). ยอดจริง ≤ ~1.6e8 → เหมือนเดิม (golden ไม่ขยับ).
    try:
        return float(d.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


_VAT_TOL_BASE = Decimal('0.5')          # ฐานคงที่ (บาท)
_VAT_TOL_DIVISOR = Decimal('100000')    # +1 บาท ต่อ subtotal ทุก 100,000 บาท


def _vat_tolerance(sub: Any) -> Decimal:
    """เกณฑ์ยอมรับส่วนต่างของผลรวมรายการ vs subtotal (คืน Decimal).

    สูตร (RESTORED): 0.5 + |subtotal|/100000.
    subtotal None / แปลงไม่ได้ → คืนฐาน 0.5.
    """
    d = _D(sub)
    if d is None:
        return _VAT_TOL_BASE
    return _VAT_TOL_BASE + abs(d) / _VAT_TOL_DIVISOR


# ───────────── unit canonicalization (FAITHFUL — ชุดเดียวกับ r_itm005) ─────────────
# คัดลอกจาก rules_engine.r_itm005 (UNIT_SYNONYMS) — เป็นข้อมูลต้นฉบับที่ยังรอด.
_UNIT_SYNONYMS = [
    {'แกลลอน', 'กระป๋อง', 'ถัง', 'ปี๊บ', 'กล.'},
    {'ลิตร', 'มล.', 'ล.', 'cc'},
    {'กก.', 'กิโล', 'กิโลกรัม', 'ก.ก.', 'kg'},
    {'แผ่น', 'ผืน', 'บาน'},
    {'ม้วน', 'โรล', 'roll'},
    {'ชุด', 'เซ็ต', 'set', 'คู่'},
    {'เส้น', 'ท่อน', 'อัน'},
    {'ก้อน', 'ลูก', 'ตัว'},
    {'ถุง', 'กระสอบ', 'แพ็ค', 'พาเลท', 'กล่อง', 'ลัง'},
]
# canonical representative = ตัวแรกตามลำดับอักษร (deterministic) ของกลุ่มที่ match
_UNIT_CANON_MAP = {}
for _grp in _UNIT_SYNONYMS:
    _rep = sorted(_grp)[0]
    for _u in _grp:
        _UNIT_CANON_MAP[_u] = _rep


def _unit_canon(u: Any) -> str:
    """ยุบหน่วยพ้องความหมายเป็นตัวแทนกลุ่ม (deterministic).

    ใช้ใน rules_engine.r_itm006/r_itm015 เพื่อ "ฟ้องเฉพาะหน่วยที่ต่างกลุ่มจริง".
    ถ้าไม่อยู่กลุ่มไหน → คืนค่าที่ strip แล้ว (ตัวมันเอง).
    """
    if not u:
        return ''
    s = str(u).strip()
    if s in _UNIT_CANON_MAP:
        return _UNIT_CANON_MAP[s]
    # เผื่อหน่วยมีข้อความห้อย (เช่น 'กก. (โดยประมาณ)') → จับด้วย substring
    for token, rep in _UNIT_CANON_MAP.items():
        if token in s:
            return rep
    return s


# ──────────── unit hint จากชื่อสินค้า (FAITHFUL — ใช้ regex จริงจาก config) ────────────
_UNIT_HINT_COMPILED = [(re.compile(pat), hint) for pat, hint in UNIT_HINT_PATTERNS]


def extract_unit_hint(name: Any) -> str:
    """ดึง 'หน่วยที่บอกใบ้ในชื่อสินค้า' จากรูปแบบ เลข+หน่วย (เช่น '5 ลิตร' → 'ลิตร').

    ใช้ UNIT_HINT_PATTERNS จาก config.py (ข้อมูลต้นฉบับ). คืนหน่วยของ pattern แรกที่เจอ,
    ไม่เจอ → '' . (rules_engine.r_itm006 ตีความ hint ที่เป็น spec แยกเองภายหลัง)
    """
    if not name:
        return ''
    s = str(name)
    for rx, hint in _UNIT_HINT_COMPILED:
        if rx.search(s):
            return hint
    return ''
