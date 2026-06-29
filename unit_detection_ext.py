# -*- coding: utf-8 -*-
"""unit_detection_ext.py — ADD-ON ตรวจจับ "หน่วยสินค้า" เพิ่มเติม (ไม่กระทบ logic เดิม)

จุดประสงค์ (ตามที่ลูกค้าแจ้ง 4 อาการ):
  (1) หน่วยพื้นที่ 'ตรม.' (ตารางเมตร) ไม่ขึ้น/ไม่ถูกรู้จัก
        → เพิ่มตระกูลหน่วยพื้นที่ (ตรม./ตร.ม./ตารางเมตร/ตร.ว./sqm/m²) ให้ระบบรู้จัก
  (2) หน่วยที่ "ผิด" ขึ้นมาไม่ครบ (ที่ทำ Fuzzy)
        → ระบบเดิมตรวจ "ชื่อสินค้า" (ITM004/010/011) และตรวจ "ความเหมาะสมของหน่วย"
          (ITM005/006/015) แต่ "ไม่เคยสะกดตรวจช่องหน่วยเอง" → โมดูลนี้เติมการ
          spell-check ช่องหน่วยด้วย map ตรง + fuzzy (rapidfuzz) แบบมีกันชน false-positive
  (3) หน่วยไม่จับ: ปี๊ป / แกลอน / แกนลอน
        → เพิ่ม map รูปสะกดผิด→รูปมาตรฐาน (ปี๊ป→ปี๊บ, แกลอน/แกนลอน→แกลลอน ฯลฯ)
  (4) ไฟล์เดียวมีหน่วยทั้งไทย+อังกฤษปนกัน ไม่แจ้งเตือนในรายงาน Notepad
        → เพิ่มฟังก์ชันตรวจ "หน่วยปนภาษาในไฟล์เดียวกัน" สำหรับรายงาน Notepad (advisory)

หลักการออกแบบ (เพื่อ "ไม่กระทบระบบเดิม"):
  • เป็นโมดูล leaf อิสระ — พึ่งแค่ stdlib + rapidfuzz (มีกันถ้าไม่มี) ไม่ import core/rules กลับ
  • ทุกฟังก์ชัน pure / อ่านอย่างเดียว ไม่แก้บิล ไม่แตะ golden path
  • การ "ตรวจเพิ่ม" ผูกผ่านกฎใหม่ ITM019 (เปิด/ปิดได้) + ส่วนเสริมใน Notepad เท่านั้น
  • หน่วยมาตรฐานที่ถูกต้องอยู่ใน whitelist → ไม่ถูกฟ้องผิด (กัน false-positive)
"""
from __future__ import annotations

import re

# rapidfuzz เป็น dependency ของระบบอยู่แล้ว แต่กันไว้ถ้าสภาพแวดล้อมขาด → fuzzy degrade เงียบ
try:
    from rapidfuzz import fuzz as _fuzz
except Exception:  # pragma: no cover - ขึ้นกับ environment
    _fuzz = None


# ───────────────────────── ตระกูลหน่วย (canonical families) ─────────────────────────
# แต่ละตระกูล: key = รูปไทยมาตรฐาน, th = รูปไทยที่ยอมรับ, en = รูปอังกฤษที่ยอมรับ (ตัวพิมพ์เล็ก)
# ใช้สำหรับ (ก) จัดกลุ่มหน่วยพ้อง  (ข) ตรวจ "ไฟล์เดียวปนไทย+อังกฤษ"  (ค) whitelist กัน FP
_FAMILIES = [
    # — พื้นที่ (NEW: แก้อาการ 'ตรม. ไม่ขึ้น') —
    {'key': 'ตรม.', 'kind': 'area',
     'th': {'ตรม.', 'ตร.ม.', 'ตร.ม', 'ตรม', 'ตารางเมตร', 'ตาราเมตร'},
     'en': {'sqm', 'sq.m', 'sq.m.', 'sq m', 'm2', 'm²'}},
    {'key': 'ตร.ว.', 'kind': 'area',
     'th': {'ตร.ว.', 'ตร.ว', 'ตารางวา', 'ตารางวาฯ'},
     'en': {'sq.wa'}},
    {'key': 'ตร.ฟุต', 'kind': 'area',
     'th': {'ตร.ฟุต', 'ตารางฟุต'},
     'en': {'sqft', 'sq.ft', 'sq.ft.', 'ft2'}},
    # — ปริมาตร —
    {'key': 'ลบ.ม.', 'kind': 'volume',
     'th': {'ลบ.ม.', 'ลบ.ม', 'ลูกบาศก์เมตร', 'คิว', 'คิวฯ'},
     'en': {'cu.m', 'cu.m.', 'm3', 'cbm'}},
    {'key': 'ลิตร', 'kind': 'volume',
     'th': {'ลิตร', 'ล.'},
     'en': {'l', 'ltr', 'liter', 'litre'}},
    {'key': 'มล.', 'kind': 'volume',
     'th': {'มล.', 'ซีซี'},
     'en': {'ml', 'cc'}},
    # — ภาชนะ/ของเหลว (NEW typo: ปี๊ป / แกลอน / แกนลอน) —
    {'key': 'แกลลอน', 'kind': 'container',
     'th': {'แกลลอน'},
     'en': {'gallon', 'gal'}},
    {'key': 'ปี๊บ', 'kind': 'container',
     'th': {'ปี๊บ'},
     'en': set()},
    {'key': 'กระป๋อง', 'kind': 'container',
     'th': {'กระป๋อง'},
     'en': {'can'}},
    {'key': 'ถัง', 'kind': 'container',
     'th': {'ถัง'},
     'en': {'drum', 'bucket', 'pail', 'tank'}},
    # — น้ำหนัก —
    {'key': 'กก.', 'kind': 'weight',
     'th': {'กก.', 'กก', 'ก.ก.', 'กิโล', 'กิโลกรัม'},
     'en': {'kg', 'kgs', 'kgm', 'kilogram', 'kilograms'}},
    {'key': 'กรัม', 'kind': 'weight',
     'th': {'กรัม', 'ขีด'},
     'en': {'g', 'gram', 'grams', 'gm'}},
    {'key': 'ตัน', 'kind': 'weight',
     'th': {'ตัน'},
     'en': {'ton', 'tons', 'tonne'}},
    # — ความยาว —
    {'key': 'เมตร', 'kind': 'length',
     'th': {'เมตร', 'ม.'},
     'en': {'m', 'meter', 'metre', 'mtr'}},
    {'key': 'ซม.', 'kind': 'length',
     'th': {'ซม.', 'เซนติเมตร'},
     'en': {'cm'}},
    {'key': 'มม.', 'kind': 'length',
     'th': {'มม.', 'มิลลิเมตร'},
     'en': {'mm'}},
    {'key': 'นิ้ว', 'kind': 'length',
     'th': {'นิ้ว', 'หุน'},
     'en': {'inch', 'inches'}},
    # — นับชิ้น/ชุด —
    {'key': 'ชิ้น', 'kind': 'count',
     'th': {'ชิ้น'},
     'en': {'pcs', 'pcs.', 'pc', 'piece', 'pieces', 'ea', 'each'}},
    {'key': 'ชุด', 'kind': 'count',
     'th': {'ชุด', 'เซ็ต', 'เซต'},
     'en': {'set', 'sets'}},
    {'key': 'คู่', 'kind': 'count',
     'th': {'คู่'},
     'en': {'pair', 'pairs'}},
    {'key': 'แผ่น', 'kind': 'count',
     'th': {'แผ่น', 'ผืน', 'บาน'},
     'en': {'sheet', 'sheets'}},
    {'key': 'ม้วน', 'kind': 'count',
     'th': {'ม้วน', 'โรล'},
     'en': {'roll', 'rolls'}},
    {'key': 'หลอด', 'kind': 'count',
     'th': {'หลอด'},
     'en': {'tube', 'tubes'}},
    {'key': 'โหล', 'kind': 'count',
     'th': {'โหล'},
     'en': {'dozen', 'doz'}},
    # — บรรจุ/แพ็ค —
    {'key': 'กล่อง', 'kind': 'pack',
     'th': {'กล่อง', 'ลัง'},
     'en': {'box', 'boxes', 'ctn', 'carton', 'cartons'}},
    {'key': 'แพ็ค', 'kind': 'pack',
     'th': {'แพ็ค', 'แพ็ก', 'แพค'},
     'en': {'pack', 'packs', 'pkg', 'pk'}},
    {'key': 'ถุง', 'kind': 'pack',
     'th': {'ถุง', 'กระสอบ'},
     'en': {'bag', 'bags', 'sack', 'sacks'}},
]

# หน่วยไทยเดี่ยว ๆ ที่ "ถูกต้องอยู่แล้ว" — ใส่ใน whitelist กัน fuzzy ฟ้องผิด
# (หน่วยพวกนี้ไม่จำเป็นต้องมีตระกูลคู่อังกฤษ)
_EXTRA_VALID_TH = {
    'อัน', 'ตัว', 'ลูก', 'ก้อน', 'เส้น', 'ท่อน', 'แท่ง', 'ดอก', 'ใบ', 'ห่อ',
    'มัด', 'กำ', 'เล่ม', 'แผง', 'ตับ', 'พวง', 'ราย', 'รายการ', 'ครั้ง', 'งาน',
    'จุด', 'คัน', 'ต้น', 'ชั้น', 'หน้า', 'ระวาง', 'เที่ยว', 'พาเลท', 'พาเลต',
    'ขด', 'ก้าน', 'แกลลอน', 'ชุด', 'คู่', 'โหล', 'กระป๋อง', 'ถัง', 'ปี๊บ',
}
_EXTRA_VALID_EN = {
    'unit', 'units', 'no', 'no.', 'nos', 'lot', 'lots', 'job', 'item', 'items',
}

# ── ดัชนีค้นเร็ว: รูปสะกด(normalize)→ family ──
_VALID_TH = set(_EXTRA_VALID_TH)
_VALID_EN = set(_EXTRA_VALID_EN)
_SPELL_TO_FAMILY = {}     # normalized spelling -> family dict
for _fam in _FAMILIES:
    for _u in _fam['th']:
        _VALID_TH.add(_u)
        _SPELL_TO_FAMILY[_u] = _fam
    for _u in _fam['en']:
        _VALID_EN.add(_u)
        _SPELL_TO_FAMILY[_u] = _fam


# ───────── รูปสะกดผิด → รูปมาตรฐาน (FLAG: ฟ้องเป็นข้อสังเกตพร้อมคำแนะนำ) ─────────
# เป็นชุด "ตรงตัว" (deterministic) — ครอบเคสที่ลูกค้าแจ้ง + ญาติใกล้เคียงที่พบบ่อย
_TYPO_MAP = {
    # ภาชนะ (อาการ 3)
    'ปี๊ป': 'ปี๊บ', 'ปีบ': 'ปี๊บ', 'ปีป': 'ปี๊บ', 'ปิ๊บ': 'ปี๊บ', 'ปิ๊ป': 'ปี๊บ',
    'แกลอน': 'แกลลอน', 'แกนลอน': 'แกลลอน', 'แกลลอล': 'แกลลอน',
    'แกลล่อน': 'แกลลอน', 'แกลลั่น': 'แกลลอน', 'แกลลั้น': 'แกลลอน', 'แกนลอล': 'แกลลอน',
    'กระปอง': 'กระป๋อง', 'กะป๋อง': 'กระป๋อง', 'กระป้อง': 'กระป๋อง',
    # พื้นที่ (อาการ 1 — รูปเพี้ยน)
    'ตาราเมตร': 'ตรม.', 'ตารางเมตร์': 'ตรม.', 'ตร.เมตร': 'ตรม.',
    # น้ำหนัก/ปริมาตร ที่พบบ่อย
    'กิโลกัม': 'กิโลกรัม', 'กิโลกร้ม': 'กิโลกรัม', 'ลิตล': 'ลิตร', 'ลิต': 'ลิตร',
    # ม้วน/แผ่น
    'มั้วน': 'ม้วน', 'ม้วณ': 'ม้วน',
}

# เป้าหมายสำหรับ fuzzy fallback (รูปไทยมาตรฐานที่ "มักพิมพ์ผิด") — คุมขอบเขตกัน FP
_FUZZY_TARGETS = [
    'แกลลอน', 'ปี๊บ', 'กระป๋อง', 'ตรม.', 'ตารางเมตร', 'ลูกบาศก์เมตร',
    'กิโลกรัม', 'ลิตร', 'ม้วน', 'แผ่น', 'กล่อง', 'กระสอบ', 'ตะแกรง',
]
_FUZZY_MIN_LEN = 3        # หน่วยสั้น 1-2 ตัว (ม./ก./ล.) กำกวมเกินไป → ไม่ fuzzy
_FUZZY_THRESHOLD = 80     # rapidfuzz ratio ขั้นต่ำ (อนุรักษ์นิยม กัน false-positive)


# ───────────────────────────── helpers (pure) ─────────────────────────────
_TH_RE = re.compile(r'[ก-๛]')
_LATIN_RE = re.compile(r'[A-Za-z]')
# [ADR-105/P2] อักขระ "ความกว้างศูนย์/มองไม่เห็น" ที่ปนมากับค่าหน่วยจากไฟล์ Excel จริง
#   (ZWSP U+200B, ZWNJ U+200C, ZWJ U+200D, BOM U+FEFF) — ต้องตัดทิ้งก่อนเทียบ ไม่งั้น
#   'Set\u200c' ≠ 'Set' และ '\u200cUnit' ถูกจัดเป็นหน่วยอังกฤษปลอม. NBSP U+00A0 → ช่องว่างปกติ.
_ZERO_WIDTH = '\u200b\u200c\u200d\ufeff'
_ZW_RE = re.compile('[' + _ZERO_WIDTH + ']')


def _norm(u) -> str:
    """normalize หน่วยสำหรับ "เทียบ" — ตัดอักขระมองไม่เห็น/ช่องว่างหัวท้าย/ซ้อน, คงอักขระที่เห็นไว้.

    [ADR-105/P2] ตัดอักขระความกว้างศูนย์ (ZWSP/ZWNJ/ZWJ/BOM) + แปลง NBSP เป็นช่องว่างปกติ
      ก่อน collapse — เป็นขยะจากการ export Excel ที่ทำให้หน่วยเดียวกันเทียบไม่ตรง (เช่น 'Set‌').
    ไม่ทำลายข้อมูลที่ "มองเห็น" (ใช้ค่าเดิมตอนแสดงผล). คืน '' ถ้า None/ว่าง.
    """
    if u is None:
        return ''
    s = str(u)
    s = _ZW_RE.sub('', s)        # ตัดอักขระความกว้างศูนย์
    s = s.replace('\u00a0', ' ')  # NBSP → space
    s = s.strip()
    s = re.sub(r'\s+', ' ', s)
    return s


def _key(u) -> str:
    """คีย์เทียบ: normalize + lower (อังกฤษ) — ไทยไม่มี case จึงคงเดิม."""
    return _norm(u).lower()


def script_of(u) -> str:
    """จำแนกสคริปต์ของหน่วย → 'th' | 'en' | 'mixed' | 'other'."""
    s = _norm(u)
    if not s:
        return 'other'
    has_th = bool(_TH_RE.search(s))
    has_en = bool(_LATIN_RE.search(s))
    if has_th and has_en:
        return 'mixed'
    if has_th:
        return 'th'
    if has_en:
        return 'en'
    return 'other'


def _is_charged(it) -> bool:
    """รายการนี้ 'คิดเงินจริง' ไหม (มี amount หรือ qty ที่เป็นตัวเลข) — กันบรรทัดหัว/ว่าง.

    ใช้กรองตอนนับ 'หน่วยขาด' เพื่อไม่ฟ้องบรรทัดที่ไม่ใช่รายการสินค้าจริง.
    """
    if not it:
        return False
    for k in ('amount', 'qty', 'price'):
        v = it.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and v not in (0, 0.0):
            return True
        if isinstance(v, str) and v.strip() not in ('', '0'):
            return True
    return False


# [ADR-105/P2] โทเคนที่ "ไม่ใช่หน่วยจริง" — หัวคอลัมน์ที่หลุดเข้ามาเป็นค่าหน่วย (เช่น 'Unit'
#   ที่นำหน้าด้วย ZWNJ ใน STC_69_0512/TSH_69_0514, หรือ 'หน่วย'). หลัง _norm (ตัด ZW แล้ว)
#   ถ้าค่าหน่วยเท่ากับคำพวกนี้ → ถือว่า "ไม่มีหน่วย" (กันนับหน่วยปลอม + ทำให้หน่วยขาดถูกตรวจเจอ).
_NON_UNIT_TOKENS = frozenset({'unit', 'units', 'หน่วย', 'หน่วยนับ'})


def _is_real_unit(u) -> bool:
    """ค่าหน่วยนี้เป็น 'หน่วยจริง' ไหม — ไม่ว่าง และไม่ใช่หัวคอลัมน์ที่หลุดมา ('Unit'/'หน่วย')."""
    s = _norm(u)
    if not s:
        return False
    return s.lower().rstrip('.') not in _NON_UNIT_TOKENS


def is_known_unit(u) -> bool:
    """หน่วยนี้เป็นรูปมาตรฐาน/ยอมรับได้ไหม (อยู่ใน whitelist)."""
    k = _key(u)
    if not k:
        return False
    return k in _VALID_EN or _norm(u) in _VALID_TH


def family_of(u):
    """คืน family dict ของหน่วย (ถ้ารู้จัก) ไม่งั้น None.

    รองรับทั้งรูปไทย (เทียบตรง) และอังกฤษ (lower). เผื่อหน่วยมีข้อความห้อย
    เช่น 'kg.' / 'ชุด (set)' → ลองตัด/จับ token ด้วย.
    """
    if u is None:
        return None
    raw = _norm(u)
    low = raw.lower()
    if raw in _SPELL_TO_FAMILY:
        return _SPELL_TO_FAMILY[raw]
    if low in _SPELL_TO_FAMILY:
        return _SPELL_TO_FAMILY[low]
    # เผื่อมี '.' ห้อย เช่น 'kg.' 'pcs.'
    low2 = low.rstrip('.')
    if low2 in _SPELL_TO_FAMILY:
        return _SPELL_TO_FAMILY[low2]
    return None


def canonical_family_key(u):
    """คืน key ตระกูลของหน่วย (รูปไทยมาตรฐาน) — ใช้จัดกลุ่ม. ไม่รู้จัก → None."""
    fam = family_of(u)
    return fam['key'] if fam else None


def correct_unit(u):
    """ตรวจ 1 หน่วย → คืน dict ถ้าควรแก้ ไม่งั้น None.

    คืน: {'suggestion': รูปมาตรฐาน, 'method': 'map'|'fuzzy', 'score': int|None}
      - map   : ตรงกับชุดรูปสะกดผิดที่รู้จัก (มั่นใจสูง)
      - fuzzy : ใกล้เคียงรูปมาตรฐาน (rapidfuzz) เกินเกณฑ์ — กันด้วย whitelist + ความยาว
    หน่วยที่เป็นรูปมาตรฐานอยู่แล้ว → None (ไม่ฟ้อง).
    """
    raw = _norm(u)
    if not raw:
        return None

    # 1) ตรงชุดรูปสะกดผิดที่รู้จัก (deterministic, มั่นใจสูงสุด)
    if raw in _TYPO_MAP:
        return {'suggestion': _TYPO_MAP[raw], 'method': 'map', 'score': 100}
    low = raw.lower()
    if low in _TYPO_MAP:
        return {'suggestion': _TYPO_MAP[low], 'method': 'map', 'score': 100}

    # 2) เป็นหน่วยมาตรฐาน/ยอมรับได้แล้ว → ไม่ฟ้อง (กัน false-positive)
    if is_known_unit(raw):
        return None

    # 3) fuzzy fallback (เฉพาะหน่วยไทยยาวพอ + ไม่อยู่ whitelist) — เติม coverage
    if _fuzz is None:
        return None
    if script_of(raw) != 'th' or len(raw) < _FUZZY_MIN_LEN:
        return None
    best, best_score = None, 0
    for target in _FUZZY_TARGETS:
        sc = _fuzz.ratio(raw, target)
        if sc > best_score:
            best, best_score = target, sc
    if best and best != raw and best_score >= _FUZZY_THRESHOLD:
        return {'suggestion': best, 'method': 'fuzzy', 'score': int(best_score)}
    return None


# ─────────────────────── (อาการ 1) ดึง hint หน่วยพื้นที่จากชื่อ ───────────────────────
# ระบบเดิม (config.UNIT_HINT_PATTERNS) ไม่มี 'ตรม.' → เติม pattern พื้นที่แบบ add-on
_AREA_HINT_RE = re.compile(
    r'\d+(?:[.,]\d+)?\s*(?:ตร\.?ม\.?|ตรม\.?|ตารางเมตร|ตร\.?ว\.?|ตารางวา|ตารางฟุต|sq\.?\s*m|m2|m²)',
    re.IGNORECASE,
)


def extract_area_hint(name) -> str:
    """ถ้าชื่อสินค้ามี 'เลข+หน่วยพื้นที่' (เช่น 'กระเบื้อง 1.2 ตรม.') → คืน 'ตรม.' ไม่งั้น ''."""
    if not name:
        return ''
    return 'ตรม.' if _AREA_HINT_RE.search(str(name)) else ''


# ─────────────────────── (อาการ 2,3) ตรวจสะกดหน่วยรายบิล ───────────────────────
def detect_unit_typos(items):
    """สแกน items ของ "บิลเดียว" → คืน list[str] ข้อสังเกตหน่วยที่สะกดผิด/รูปไม่มาตรฐาน.

    เป็นช่องว่างที่ระบบเดิมไม่ครอบ: ITM004/010/011 ตรวจ "ชื่อ", ITM005/006/015
    ตรวจ "ความเหมาะสม/ความสม่ำเสมอของหน่วย" แต่ไม่มีกฎใด spell-check ช่องหน่วยเอง.
    """
    out = []
    for it in (items or []):
        unit = (it or {}).get('unit')
        if not _is_real_unit(unit):   # [ADR-105/P2] ข้ามหัวคอลัมน์หลุด/ว่าง
            continue
        res = correct_unit(unit)
        if not res:
            continue
        name = str((it or {}).get('name', '') or '')
        seq = (it or {}).get('seq', '?')
        if res['method'] == 'map':
            tag = 'สะกด/รูปไม่มาตรฐาน'
        else:
            tag = f"ใกล้เคียง ~{res['score']}%"
        out.append(
            f"#{seq} \"{name[:30]}\" — หน่วย \"{unit}\" {tag} "
            f"ควรเป็น \"{res['suggestion']}\""
        )
    return out


def detect_missing_units_in_bill(items):
    """flag 'หน่วยว่าง' ระดับบิล — เฉพาะเมื่อบิลเดียวกันมีรายการอื่น 'ที่มีหน่วยจริง' อยู่ด้วย.

    = สัญญาณ "หน่วยขาด/แหว่ง" ที่ noise ต่ำ (intra-bill inconsistency):
      ถ้าทั้งบิลไม่มีหน่วยเลย → ไม่ flag ที่นี่ (ปล่อยให้ ITM020 ระดับบิล + Notepad/บริษัทจับ).
    [ADR-105/P2] ใช้ _is_real_unit (ข้ามค่า 'Unit'/'หน่วย' ที่เป็นหัวคอลัมน์หลุด) + ข้อความตรง
      ข้อเท็จจริง: ช่องหน่วยใน "ต้นฉบับว่าง" — ไม่ใช่ระบบดึงมาไม่ครบ (พิสูจน์แล้ว source ไม่มีหน่วย).
    """
    items = items or []
    has_unit = any(_is_real_unit((it or {}).get('unit')) for it in items)
    if not has_unit:
        return []
    out = []
    for it in items:
        if (not _is_real_unit((it or {}).get('unit'))) and _is_charged(it):
            seq = (it or {}).get('seq', '?')
            name = str((it or {}).get('name', '') or '')
            out.append(f"#{seq} \"{name[:30]}\" — ไม่มีหน่วยสินค้า (ช่องหน่วยว่างในต้นฉบับ)")
    return out


def r_itm019(b, m, c):
    """[ADD-ON] ITM019 — ตรวจ "ช่องหน่วยสินค้า" ที่กฎเดิมไม่ครอบ:
       (ก) สะกดผิด/รูปไม่มาตรฐาน (ปี๊ป/แกลอน/แกนลอน/ตรม. ฯลฯ)
       (ข) หน่วยขาด/ดึงไม่ครบ ในบิลที่รายการอื่นมีหน่วย (intra-bill inconsistency)
    pure check ไม่มี side-effect (สอดคล้องสไตล์ r_itm0xx เดิม). คืน list[str].
    """
    items = (b or {}).get('items') or []
    return detect_unit_typos(items) + detect_missing_units_in_bill(items)


def detect_whole_bill_missing_units(items):
    """[ADR-106/P3 — ITM020] flag เมื่อ "ทั้งบิล" ไม่มีหน่วยจริงเลย แต่มีรายการคิดเงิน.

    เติมช่องว่างที่ ITM019 (intra-bill inconsistency) จงใจข้าม: ถ้า "ทุก" รายการไม่มีหน่วย
    ITM019 จะไม่ฟ้อง (ไม่มีรายการที่มีหน่วยให้เทียบ → has_unit=False → return []).
    เคสจริง: TOR_67_08.xlsx (ผ้า/ซิป มีจำนวน/ราคา/ยอด แต่ต้นฉบับไม่มีคอลัมน์หน่วยเลย).
    เจ้าของยืนยันต้องการให้ "ระบบบอก" เมื่อมีรายการสินค้าแต่ไม่มีหน่วย.
    คืน list[str] — สรุปราย "บิล" (หัวเดียว + รายการย่อ cap กันท่วม เช่น 107 รายการ).
    """
    items = items or []
    charged = [it for it in items if _is_charged(it)]
    if not charged:
        return []
    charged_no_unit = [it for it in charged if not _is_real_unit((it or {}).get('unit'))]
    if not charged_no_unit:
        return []
    # เงื่อนไข "ทั้งบิล" จริง = ไม่มีรายการคิดเงินใด "มีหน่วยจริง" เลย (ถ้ามี → intra-bill = ITM019)
    if any(_is_real_unit((it or {}).get('unit')) for it in charged):
        return []
    n = len(charged_no_unit)
    CAP = 5
    refs = []
    for it in charged_no_unit[:CAP]:
        seq = (it or {}).get('seq', '?')
        name = str((it or {}).get('name', '') or '')[:30]
        refs.append(f"#{seq} \"{name}\"")
    more = f" …(+{n - CAP} รายการ)" if n > CAP else ""
    return [f"ทั้งบิลไม่มีหน่วยสินค้า — {n} รายการคิดเงินไม่มีหน่วย (ช่องหน่วยว่างในต้นฉบับ): "
            + ", ".join(refs) + more]


def r_itm020(b, m, c):
    """[ADD-ON] ITM020 — "ทั้งบิลไม่มีหน่วยสินค้า": มีรายการคิดเงินแต่ไม่มีหน่วยเลยทั้งใบ.

    ช่องว่างที่ ITM019 (intra-bill) ข้าม — จับใบที่ "ทุกรายการ" ไม่มีหน่วย (เช่น TOR_67_08).
    pure check ไม่มี side-effect (สอดคล้องสไตล์ r_itm0xx เดิม). คืน list[str].
    """
    return detect_whole_bill_missing_units((b or {}).get('items') or [])


# ─────────────── (อาการใหม่) หมายเหตุระดับ "บริษัท" — ปนภาษา + หน่วยขาด ───────────────
def _company_key(b):
    """คีย์รวมบริษัท: เลขภาษี (canonical) → ไม่มีก็ใช้ชื่อ. ตรงแนวคิด super_ultra_viewer."""
    tid = str((b or {}).get('tax_id') or '').strip()
    if tid:
        return tid
    return _norm((b or {}).get('company') or (b or {}).get('company_raw') or '(ไม่ทราบบริษัท)')


def _unit_family_key(u):
    """คืน family-key ของหน่วย (รูปไทยมาตรฐาน เช่น 'เมตร','กก.','ชิ้น') ถ้ารู้จัก ไม่งั้น None.
    ใช้เทียบ "หน่วยเดียวกันเขียนต่างสคริปต์" (เมตร↔m, กก.↔kg) — อิสระจากสคริปต์."""
    s = _norm(u)
    if not s:
        return None
    fam = (_SPELL_TO_FAMILY.get(s)
           or _SPELL_TO_FAMILY.get(s.lower())
           or _SPELL_TO_FAMILY.get(s.rstrip('.'))
           or _SPELL_TO_FAMILY.get(s.rstrip('.').lower()))
    return fam['key'] if fam else None


def company_unit_notes(bills):
    """หมายเหตุระดับ "บริษัท" (list[str]) จากบิลของบริษัทเดียว (pre-grouped).

    ใช้ในบล็อกสรุปบริษัท (super_ultra_viewer "หมายเหตุ :") + Notepad:
      (ก) ปนไทย+อังกฤษ: บริษัทเขียน "หน่วยเดียวกัน" 2 สคริปต์ (เช่น เมตร/m, กก./kg) = inconsistency จริง
      (ข) หน่วยขาด/ดึงไม่ครบ: มีรายการคิดเงินที่ "ช่องหน่วยว่าง"

    [ADR-091] เดิม flag (ก) เมื่อ "หน่วยไทยใดๆ + หน่วยอังกฤษใดๆ" อยู่ด้วยกัน แม้คนละหน่วย
      → FP: 'PCS'(ชิ้น) + 'เมตร'(ยาว) ไม่ใช่ความขัดแย้ง. เจ้าของยืนยัน: ที่เป็นอังกฤษคือ "ชื่อสินค้า"
      ไม่ใช่หน่วย. แก้: flag เฉพาะเมื่อ family-key เดียวกันปรากฏทั้งสคริปต์ไทยและอังกฤษ.
    """
    blank = 0
    # [ADR-104/P1] "ปนภาษา" ต้องเป็น inconsistency "ภายในไฟล์เดียว" (ใบกำกับเดียว) ไม่ใช่
    #   aggregate ข้ามไฟล์ระดับบริษัท. เดิมรวมหน่วยทุกไฟล์ของบริษัท → FP: ผู้ขาย A ออกใบเป็น 'm',
    #   ผู้ขาย B ออกเป็น 'เมตร' (family เดียวกัน คนละไฟล์) → บริษัทถูกหาว่า "ปนภาษา" ทั้งที่แต่ละ
    #   ใบสคริปต์เดียวสม่ำเสมอ และบริษัทคุมไม่ได้ว่าผู้ขายแต่ละเจ้าเขียนหน่วยภาษาไหน. แก้:
    #   flag เฉพาะเมื่อ family เดียวกันปรากฏทั้งสคริปต์ไทยและอังกฤษ "ในไฟล์เดียวกัน".
    #   (เทสล็อกสังเคราะห์ 1 บิล = 1 ไฟล์ → พฤติกรรมเคส [A]-[D] คงเดิมเป๊ะ.)
    by_file = {}
    for b in (bills or []):
        fkey = (b or {}).get('file')
        slot = by_file.setdefault(fkey, {'th_fams': set(), 'en_fams': set()})
        for it in ((b or {}).get('items') or []):
            u = (it or {}).get('unit')
            if not u or not str(u).strip():
                if _is_charged(it):
                    blank += 1
                continue
            k = _unit_family_key(u)
            if not k:
                continue
            sc = script_of(u)
            if sc == 'th':
                slot['th_fams'].add(k)
            elif sc in ('en', 'mixed'):
                slot['en_fams'].add(k)
    # ปนภาษาจริง = อย่างน้อย 1 ไฟล์ ที่ family เดียวกันถูกเขียนทั้งสคริปต์ไทยและอังกฤษในไฟล์นั้น
    mixed_in_file = any(slot['th_fams'] & slot['en_fams'] for slot in by_file.values())
    notes = []
    if mixed_in_file:
        # [recheck] สั้น ภาษาคน — ไม่ list หน่วยทีละตัว (เจ้าของขอ "แค่นี้พอ จะได้ไม่งง")
        notes.append("หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษครับ")
    if blank:
        notes.append(f"หน่วยสินค้าบางรายการไม่มีหน่วย (ช่องหน่วยว่างในต้นฉบับ, {blank} รายการ)")
    return notes


def detect_company_unit_language_mix(bills):
    """จัดกลุ่มบิลทั้งหมดเป็นราย "บริษัท" → คืน list[dict] ของบริษัทที่มีหมายเหตุหน่วย.

    คืน: [{'company','tax_id','notes':[...], 'th':[...], 'en':[...], 'blank':int}]
    ใช้โดย Notepad (ภาพรวมทุกบริษัท).
    """
    groups = {}
    for b in (bills or []):
        groups.setdefault(_company_key(b), []).append(b)
    out = []
    for key, gbills in groups.items():
        notes = company_unit_notes(gbills)
        if not notes:
            continue
        th, en, blank = set(), set(), 0
        for b in gbills:
            for it in ((b or {}).get('items') or []):
                u = (it or {}).get('unit')
                if not _is_real_unit(u):   # [ADR-105/P2] หัวคอลัมน์หลุด/ว่าง = ไม่มีหน่วยจริง
                    if _is_charged(it):
                        blank += 1
                    continue
                sc = script_of(u)
                if sc == 'th':
                    th.add(_norm(u))
                elif sc in ('en', 'mixed'):
                    en.add(_norm(u))
        comp = (gbills[0].get('company') or gbills[0].get('company_raw') or key)
        out.append({'company': comp, 'tax_id': gbills[0].get('tax_id') or '',
                    'notes': notes, 'th': sorted(th), 'en': sorted(en), 'blank': blank})
    out.sort(key=lambda d: str(d['company']))
    return out


# ─────────────────── (อาการ 4) หน่วยปนไทย+อังกฤษในไฟล์เดียวกัน ───────────────────
def detect_file_unit_language_mix(bills):
    """ตรวจ "ไฟล์เดียวมีหน่วยทั้งไทย+อังกฤษ (ความหมายเดียวกัน)".

    คืน list[dict] เรียงตามชื่อไฟล์:
        {'file', 'mixed_families': [{'family','th','en'}...], 'th_units', 'en_units'}
    เกณฑ์หลัก (สัญญาณชัด): ตระกูลเดียวกันถูกเขียนทั้งรูปไทยและรูปอังกฤษในไฟล์เดียว
      (เช่น ใช้ทั้ง 'กก.' และ 'kg' หรือ 'ตรม.' และ 'sqm').
    """
    by_file = {}
    for b in (bills or []):
        fname = (b or {}).get('file') or '(ไม่ทราบไฟล์)'
        slot = by_file.setdefault(fname, {'th': set(), 'en': set(), 'fam_th': {}, 'fam_en': {}})
        for it in ((b or {}).get('items') or []):
            unit = (it or {}).get('unit')
            if not _is_real_unit(unit):   # [ADR-105/P2] ข้ามหัวคอลัมน์ที่หลุด
                continue
            sc = script_of(unit)
            disp = _norm(unit)
            fam = family_of(unit)
            if sc == 'th':
                slot['th'].add(disp)
                if fam:
                    slot['fam_th'].setdefault(fam['key'], set()).add(disp)
            elif sc in ('en', 'mixed'):
                slot['en'].add(disp)
                if fam:
                    slot['fam_en'].setdefault(fam['key'], set()).add(disp)

    out = []
    for fname in sorted(by_file):
        slot = by_file[fname]
        mixed = []
        for famkey in sorted(set(slot['fam_th']) & set(slot['fam_en'])):
            mixed.append({
                'family': famkey,
                'th': sorted(slot['fam_th'][famkey]),
                'en': sorted(slot['fam_en'][famkey]),
            })
        # รายงานเฉพาะไฟล์ที่ "มีตระกูลปนภาษา" (สัญญาณชัด ไม่รบกวน)
        if mixed:
            out.append({
                'file': fname,
                'mixed_families': mixed,
                'th_units': sorted(slot['th']),
                'en_units': sorted(slot['en']),
            })
    return out


def summarize_units_by_file(bills):
    """สรุป "หน่วยที่พบ + จำนวนครั้ง" ต่อไฟล์ (ให้ ตรม. และหน่วยอื่นปรากฏในรายงาน).

    คืน dict: {file: {unit: count}}  เรียงไฟล์ตามตัวอักษรเมื่อแสดง.
    """
    out = {}
    for b in (bills or []):
        fname = (b or {}).get('file') or '(ไม่ทราบไฟล์)'
        slot = out.setdefault(fname, {})
        for it in ((b or {}).get('items') or []):
            raw = (it or {}).get('unit')
            if not _is_real_unit(raw):   # [ADR-105/P2] ข้ามหัวคอลัมน์ที่หลุด ('Unit'/'หน่วย')
                continue
            unit = _norm(raw)
            slot[unit] = slot.get(unit, 0) + 1
    return out


def collect_unit_typos(bills):
    """รวมข้อสังเกตหน่วยสะกดผิดข้ามทุกบิล (สำหรับ Notepad) → list[str] '(file/sheet) ...'."""
    out = []
    for b in (bills or []):
        msgs = detect_unit_typos((b or {}).get('items') or [])
        if not msgs:
            continue
        ref = '/'.join(x for x in (str((b or {}).get('file') or ''),
                                   str((b or {}).get('sheet') or '')) if x)
        for msg in msgs:
            out.append(f"({ref}) {msg}" if ref else msg)
    return out


# ─────── (อาการ 5) หน่วย "วัด" ในชื่อ/สเปกสินค้า ปนไทย+อังกฤษ ราย "ไฟล์" (v9.3.4) ───────
# ผู้ใช้ขอ "จับจากหน่วยสินค้าจริง" แล้วขึ้นหมายเหตุในรีพอร์ตที่ส่งลูกค้า:
#   หน่วยวัด (มม./mm, ซม./cm, เมตร/m, นิ้ว/inch, กก./kg, ตรม./sqm) มักฝังในชื่อ/สเปกสินค้า
#   (ช่อง 'unit' เป็นหน่วยนับ เช่น ท่อน/แผ่น ที่เป็นไทยล้วน). เช่น SHS เขียนทั้ง '9 มม.' และ '9mm.'.
# เกณฑ์: ไฟล์มีหน่วยวัดทั้ง "รูปไทย" และ "รูปอังกฤษ" ที่ติดตัวเลข → หมายเหตุระดับไฟล์.
#   ตัด '"' (นิ้ว) ออก เพราะเป็นสัญลักษณ์สากล ไม่ใช่ "ภาษา" (กัน FP ที่ทุกไฟล์ติดเพราะขนาดท่อ 1/2").
_MEASURE_KINDS = {'length', 'area', 'volume', 'weight'}
_MEASURE_TH_KEYS = set()
_MEASURE_EN_KEYS = set()
for _fam in _FAMILIES:
    if _fam.get('kind') in _MEASURE_KINDS:
        for _u in _fam['th']:
            _k = _u.replace('.', '').replace(' ', '')
            if len(_k) >= 2:                 # กัน FP จาก token สั้น 1 ตัว (เช่น 'ม','ล') ติดเลขในรหัสสินค้า
                _MEASURE_TH_KEYS.add(_k)
        for _u in _fam['en']:
            _k = _u.replace('.', '').replace(' ', '').lower()
            if len(_k) >= 2:                 # กัน FP จาก 'm'/'g'/'l' ใน '9M2'/รหัสรุ่น
                _MEASURE_EN_KEYS.add(_k)
# token หน่วยที่ "ติดตัวเลข" (เช่น 9มม. / 9mm. / 240ซม. / 100 เมตร) — ทีละสคริปต์ (greedy ยาวสุดก่อน)
_NUM_UNIT_RE = re.compile(r'\d\s*([A-Za-z]{1,6}|[ก-๎]{1,7})\.?')


def _file_tag(fname):
    """ชื่อย่อไฟล์ (เช่น 'SHS' จาก 'SHS_69.04.xls') — ตัวอักษรนำหน้า basename."""
    base = str(fname or '').replace('\\', '/').rsplit('/', 1)[-1]
    m = re.match(r'([A-Za-z]+)', base)
    return m.group(1) if m else (base or '(ไม่ทราบไฟล์)')


def file_spec_unit_lang_notes(bills):
    """หมายเหตุระดับ "ไฟล์": หน่วยวัดของสินค้า (ฝังในชื่อ/สเปก) ปนทั้งไทยและอังกฤษ.

    คืน list[str] รวมไฟล์ที่ปนภาษาเป็นบรรทัดเดียว สั้น ภาษาคน เช่น
      "ไฟล์ SHS และ TSH หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษครับ"
    advisory ล้วน (อ่าน bills เท่านั้น ไม่ mutate / ไม่แตะ b['issues'] / golden hash ไม่ขยับ).
    """
    by_file = {}
    for b in (bills or []):
        fname = (b or {}).get('file') or '(ไม่ทราบไฟล์)'
        slot = by_file.setdefault(fname, {'th': set(), 'en': set()})
        for it in ((b or {}).get('items') or []):
            text = _norm((it or {}).get('name')) + ' ' + _norm((it or {}).get('unit'))
            for m in _NUM_UNIT_RE.finditer(text):
                tok = m.group(1)
                key = tok.replace('.', '').replace(' ', '').lower()
                if _LATIN_RE.search(tok):
                    if key in _MEASURE_EN_KEYS:
                        slot['en'].add(tok.lower())
                elif key in _MEASURE_TH_KEYS:
                    slot['th'].add(tok)
    # [recheck] รวมทุกไฟล์ที่ปนภาษาเป็น "บรรทัดเดียว" สั้น ภาษาคน (เจ้าของขอ ไม่ list หน่วย/ไม่แยกหลายบรรทัด)
    tags = []
    for fname in sorted(by_file):
        slot = by_file[fname]
        if slot['th'] and slot['en']:
            t = _file_tag(fname)
            if t not in tags:                       # dedupe + รักษาลำดับ sorted (เช่น SHS_69_05/SHS_69_06 → 'SHS' ครั้งเดียว)
                tags.append(t)
    if not tags:
        return []
    joined = ' และ '.join(tags)                     # 1 ไฟล์ → "SHS" ; หลายไฟล์ → "SHS และ TSH"
    return [f"ไฟล์ {joined} หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษครับ"]
