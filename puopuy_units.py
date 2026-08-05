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
    # [ADR-184/UNIT-EN] เพิ่มหน่วยนับ "ชิ้น" ฝั่งอังกฤษเข้ากลุ่มเดียวกับ เส้น/ท่อน/อัน.
    #   เหตุผลเชิงประจักษ์: ITM015 บน corpus จริงฟ้อง 254 จุด — 154 จุด (61%) คือคู่
    #   ['Pcs.','ท่อน'] / ['Pcs.','เส้น'] / ['PCS.','เส้น'] ซึ่งเป็น "หน่วยเดียวกันเขียนคนละภาษา"
    #   บนใบเดียวกันของผู้ขายเหล็ก (RB6-SR24, DB10-SD40, H-beam …) = false positive ล้วน.
    #   ผู้ใช้สั่งชัด: ผิดจริงต้องแจ้ง / ไม่ผิดต้องไม่กวน → ยุบเป็นกลุ่มเดียวกันที่ต้นเหตุ
    #   แทนการซ่อนปลายทาง (ของเดิมใช้ _HIDE_IN_SUMMARY ซ่อน = รีพอร์ตขึ้น "ตรง" หลอก).
    {'เส้น', 'ท่อน', 'อัน', 'ชิ้น', 'pcs', 'pcs.', 'pc', 'pc.', 'piece', 'pieces', 'ea', 'each'},
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
    # [ADR-184/UNIT-EN] หน่วยฝั่งอังกฤษบนใบจริงเขียนได้หลายตัวพิมพ์ ('Pcs.', 'PCS.', 'pcs')
    #   → เทียบซ้ำแบบ case-insensitive เฉพาะเมื่อ exact-match พลาด. ลำดับนี้สำคัญ:
    #   หน่วยไทยไม่มีแนวคิดตัวพิมพ์ → เส้นทางเดิมของภาษาไทยเหมือนเดิมเป๊ะ (golden-neutral).
    _sl = s.lower()
    if _sl in _UNIT_CANON_MAP:
        return _UNIT_CANON_MAP[_sl]
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


# ── [ADR-122] VAT012 — แปลง "ยอดเงินเป็นตัวอักษรไทย (บาทตัวอักษร)" → Decimal ─────────────────
#   ใช้เทียบกับยอดตัวเลข (กันแก้เลขแต่ลืมแก้ตัวอักษร = ช่องปลอมแปลง). conservative สุด:
#   แปลงไม่สะอาด/มีเศษคำแปลก → คืน None (กฎ VAT012 จะ "เงียบ" ไม่ฟ้อง → ไม่มี false-positive).
_THAI_DIGIT = {'ศูนย์': 0, 'หนึ่ง': 1, 'สอง': 2, 'สาม': 3, 'สี่': 4, 'ห้า': 5,
               'หก': 6, 'เจ็ด': 7, 'แปด': 8, 'เก้า': 9, 'เอ็ด': 1, 'ยี่': 2}
_THAI_SCALE = {'สิบ': 10, 'ร้อย': 100, 'พัน': 1000, 'หมื่น': 10000, 'แสน': 100000}
# longest-first เพื่อ tokenize ถูก (ยี่ ต้องลองก่อน, เอ็ด ก่อน เ-)
_THAI_NUM_TOKENS = sorted(list(_THAI_DIGIT) + list(_THAI_SCALE) + ['ล้าน'], key=len, reverse=True)


def _thai_words_to_int(s: Any) -> "int | None":
    """แปลง 'คำเลขไทย' → int. คืน None ถ้ามี 'เศษที่ไม่ใช่คำเลข' (กัน mis-parse ชื่อสินค้า/ของแปลก)."""
    if s is None:
        return None
    s = str(s).strip()
    s = re.sub(r'[\s\(\)\-,\.]', '', s)        # ตัด whitespace/วงเล็บ/จุลภาค/จุด
    if not s:
        return None
    result = 0      # ผลรวมก้อนล้านที่ commit แล้ว
    current = 0     # ก้อนปัจจุบัน (< ล้าน)
    last_digit = 0  # หลักหน่วยที่ค้างรอ scale
    seen = False
    i, n = 0, len(s)
    while i < n:
        for tok in _THAI_NUM_TOKENS:
            if s.startswith(tok, i):
                seen = True
                if tok == 'ล้าน':
                    current += last_digit
                    if current == 0:           # 'ล้าน' ต้องมีค่านำหน้า — ไม่งั้นผิดรูป
                        return None
                    result += current * 1000000
                    current = 0; last_digit = 0
                elif tok in _THAI_SCALE:
                    d = last_digit if last_digit else 1   # 'สิบ' เดี่ยว = 1×10
                    current += d * _THAI_SCALE[tok]
                    last_digit = 0
                else:                          # digit word
                    last_digit = _THAI_DIGIT[tok]
                i += len(tok)
                break
        else:
            return None                        # เจออักขระที่ไม่ใช่คำเลข → ไม่สะอาด → ยอมแพ้ (เงียบ)
    if not seen:
        return None
    current += last_digit
    return result + current


def baht_text_to_decimal(s: Any) -> "Decimal | None":
    """แปลง 'บาทตัวอักษร' (เช่น 'หกหมื่นแปดพันสี่ร้อยแปดสิบบาทถ้วน') → Decimal(68480.00).
    รองรับสตางค์ ('...บาทห้าสิบสตางค์' → .50) + 'ถ้วน' (=.00). คืน None ถ้าแปลงไม่สะอาด/ไม่มี 'บาท'.
    """
    if not s:
        return None
    s = str(s).strip()
    if 'บาท' not in s:
        return None                            # ต้องมี 'บาท' จึงมั่นใจว่าเป็นยอดเงิน (กัน mis-parse)
    baht_part, _, rest = s.partition('บาท')
    baht = _thai_words_to_int(baht_part)
    if baht is None:
        return None
    satang: int = 0
    rest = rest.replace('ถ้วน', '').strip()
    if 'สตางค์' in rest:
        sat_part = rest.split('สตางค์')[0]
        sat_val = _thai_words_to_int(sat_part)
        if sat_val is None or not (0 <= sat_val <= 99):
            return None
        satang = sat_val
        rest = ''                              # ใช้ส่วน สตางค์ แล้ว
    elif rest:
        # มีเศษหลัง 'บาท' ที่ไม่ใช่ 'ถ้วน'/'สตางค์' → ไม่สะอาด → เงียบ
        return None
    try:
        return Decimal(baht) + (Decimal(satang) / Decimal(100))
    except (InvalidOperation, ValueError):
        return None
