# -*- coding: utf-8 -*-
"""test_typo_decisions_lock.py — ล็อก "การตัดสิน typo รายคำ" (ADR-084) + พฤติกรรม _kw_in_name (จุด ITM005)

ที่มา (business-reason):
  การตัดสิน typo กระจายอยู่หลายที่ (THAI_TYPO_PATTERNS / CONSTRUCTION_DICT / กฎหน่วย ITM019)
  ซึ่ง "ขัดกันเองได้" — เคยเกิดกับ 'ปี๊ป' (คอมเมนต์บอก whitelist แต่ ITM019 ยังฟ้อง).
  เทสนี้ตรึงการตัดสินรายคำที่ Tor อนุมัติ (ADR-084) ให้เป็น invariant ทดสอบได้ →
  ถ้าใครเผลอเปลี่ยน whitelist/pattern จะแดงทันที (ไม่ใช่รู้ตอน golden เพี้ยน).

  นอกจากนี้ตรึงพฤติกรรม `_kw_in_name` (root cause ITM005, ADR-085) ไว้เป็น characterization —
  เป็น "ตาข่ายนิรภัย" สำหรับการแก้ ITM005 ในอนาคต: ถ้าแก้ guard ตัวนี้ พฤติกรรมที่เปลี่ยน
  จะถูกจับโดยเทสนี้ (จงใจให้ผู้แก้เห็น before/after ชัด).

รันได้ทุกที่ — ไม่ต้องใช้ข้อมูลจริง. golden-neutral (เทสล้วน).
"""
import re
import sys

FAILS = []


def _check(cond, msg):
    mark = '✅' if cond else '❌'
    print(f'  {mark} {msg}')
    if not cond:
        FAILS.append(msg)


def _literal_core(rx):
    """ตัด regex metachar/lookaround หยาบ ๆ — ใช้เช็คว่าคำปรากฏใน pattern ไหม (เพียงพอสำหรับ literal)."""
    s = re.sub(r'\(\?[<!=][^)]*\)', '', rx)        # ตัด lookaround
    s = re.sub(r'\[[^\]]*\]', '', s)               # ตัด character class ทั้งก้อน (กัน false-overlap เช่น วาล์[^ว])
    s = re.sub(r'[\\^$.*+?{}()|]', '', s)
    return s.strip()


def main():
    from config_base import CONSTRUCTION_DICT, PYTHAINLP_WHITELIST, THAI_TYPO_PATTERNS
    from rules_engine_base import _kw_in_name

    pattern_cores = [_literal_core(rx) for rx, _ in THAI_TYPO_PATTERNS]

    print('=== [A] การตัดสิน typo รายคำ (ADR-084) ===')
    # คำที่ Tor อนุมัติ "ยกเว้น (whitelist)" → ต้องอยู่ใน CONSTRUCTION_DICT (fuzzy เลิกฟ้อง)
    for w in ('สวิตซ์', 'สวิตซ์ทางเดียว', 'สวิตซ์สองทาง', 'สวิตซ์สามทาง'):
        _check(w in CONSTRUCTION_DICT, f"'สวิตซ์' whitelisted: {w!r} อยู่ใน CONSTRUCTION_DICT")
    # [ADR-121] 'เจียร์' ต้อง "ไม่" เป็น typo-pattern target อีก (ลบแล้ว) + 'แผ่นเจียร์' อยู่ใน WHITELIST
    _check(not any('เจียร์' == core for core in pattern_cores),
           "'เจียร์' เลิกฟ้อง (ADR-121): ไม่เป็น typo-pattern target แล้ว")
    _check('แผ่นเจียร์' in PYTHAINLP_WHITELIST,
           "'แผ่นเจียร์' อยู่ใน PYTHAINLP_WHITELIST (ADR-121 — ITM011 fuzzy เลิกฟ้อง)")
    # [ADR-123 2026-06-28] เคลียร์คำก้ำกึ่ง — supersede ADR-084/090 สำหรับกลุ่ม B:
    #   เจ้าของหลัก "คำผิดในรายการสินค้า ต้องเป็นคำที่ผิดแน่ๆ เท่านั้น" → ทับศัพท์หลายรูปใช้จริง = เลิกฟ้อง.
    #   'พุ๊ก' (เดิม ADR-084 คงไว้) + 'อิฐบล็อค' (เดิม ADR-090 คงไว้ฟ้อง ITM011) → ย้ายเข้า whitelist.
    for w in ('พุ๊ก', 'พุ๊กเคมี', 'แกลอน', 'อิฐบล็อค', 'ตู้คอนซูเมอร์',
              'อะครีลิค', 'อีพ๊อกซี่', 'แป๊ป', 'แป็ป'):
        _check(w in PYTHAINLP_WHITELIST, f"'{w}' เลิกฟ้อง (ADR-123 กลุ่ม B): อยู่ใน PYTHAINLP_WHITELIST")
    # กลุ่ม B ต้อง "ไม่" เป็น typo-pattern target อีก (ลบ pattern ITM010/ITM004 แล้ว)
    for w in ('พุ๊ก', 'ครีลิ', 'อีพ๊อก'):
        _check(not any(w == core for core in pattern_cores),
               f"'{w}' ลบจาก typo-pattern แล้ว (ADR-123 กลุ่ม B)")
    # กลุ่ม A = typo จริง คงไว้ (รวม 'หล็กฉาก' ที่ ADR-123 เพิ่มเป็น ITM010 รีเช็ค)
    for w in ('มั้วน', 'แกนลอน', 'หล็กฉาก'):
        _check(any(w in core for core in pattern_cores), f"'{w}' typo จริง: ยังเป็น typo-pattern target")

    print()
    print('=== [B] consistency: คำใน dict (ถือว่าถูก) ต้องไม่เป็น literal typo-pattern target (กัน ปี๊ป-class) ===')
    contradictions = sorted(w for w in CONSTRUCTION_DICT if any(w == core for core in pattern_cores))
    _check(not contradictions, f"ไม่มีคำที่อยู่ทั้ง CONSTRUCTION_DICT และ typo-pattern (เจอ: {contradictions})")

    print()
    print('=== [C] characterization _kw_in_name (ITM005 sniper — ADR-087 lock) ===')
    # ADR-087 (F1): kw=='สี' + คำบอกสีล้วน = คำขยาย ไม่ใช่สินค้าสี → ITM005 ไม่คาดหน่วยแกลลอน.
    #   ตรึงทั้ง "ตัด FP" (สวิตช์/สายไฟ/สีล้วน → False) และ "recall คงเดิม" (สีจริง → True).
    #   ถ้าใครจะแก้ ITM005/_kw_in_name ต่อ ค่าเหล่านี้จะเปลี่ยน → ต้องอัปเทสนี้พร้อม ADR ใหม่.
    # --- ตัด false-positive (สินค้าไม่ใช่สี + คำบอกสี) → ต้องเป็น False ---
    _check(_kw_in_name('สี', 'BLสวิตซ์ทางเดียว 3 ปุ่ม สีดำ') is False,
           "[ADR-087 FIXED] 'สวิตช์...สีดำ' → False (เลิก FP หน่วยสี)")
    _check(_kw_in_name('สี', 'YAZAKI THW 1 x 2.5 สีน้ำตาล') is False,
           "[ADR-087] สายไฟ '...สีน้ำตาล' → False (เลิก FP)")
    _check(_kw_in_name('สี', 'กระเบื้องเคลือบบุผนัง สีเรียบ 8\"x8\"') is False,
           "[ADR-087] กระเบื้อง 'สีเรียบ' → False (เลิก FP)")
    _check(_kw_in_name('สี', 'สีน้ำเงิน') is False,
           "[ADR-087] 'สีน้ำเงิน' (สีล้วน) → False — token ยาวกั้นก่อน 'น้ำ'")
    # --- recall คงเดิม (สีจริง) → ต้องยังเป็น True ---
    _check(_kw_in_name('สี', 'สีรองพื้น TOA สีขาว') is True,
           "[recall] สีจริง 'สีรองพื้น' → True (ไม่หลุด)")
    _check(_kw_in_name('สี', 'สีน้ำ TOA 1 แกลลอน') is True,
           "[recall] 'สีน้ำ' (สีจริง) → True — จงใจไม่ใส่ 'น้ำ' ใน _SI_COLOR_ADJ")
    _check(_kw_in_name('สี', 'สีน้ำมันเบเยอร์ 1 แกลลอน') is True,
           "[recall] 'สีน้ำมัน' (สีจริง) → True")
    _check(_kw_in_name('สี', 'สีอะคริลิค 75ML') is True,
           "[recall] 'สีอะคริลิค' (สีจริง) → True")
    # --- guard เดิมไม่ถอย ---
    _check(_kw_in_name('สี', 'เหล็กสี่เหลี่ยม 50x50') is False,
           "'สี่' (สี+วรรณยุกต์) → False (กันถูก)")
    _check(_kw_in_name('สี', 'ลวดเชื่อมสีเงิน') is False,
           "'สี' กลางคำไม่มีช่องว่างนำ → False (กันถูก)")

    print()
    print('================================================================')
    if FAILS:
        print(f'RESULT: ❌ FAIL ({len(FAILS)} จุด) — การตัดสิน typo/พฤติกรรม guard เปลี่ยนไปจากที่ตรึงไว้')
        sys.exit(1)
    print('RESULT: ✅ PASS — typo decisions (ADR-084) + _kw_in_name characterization ตรงที่ล็อก')
    sys.exit(0)


if __name__ == '__main__':
    main()
