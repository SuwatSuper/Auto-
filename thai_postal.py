# -*- coding: utf-8 -*-
"""thai_postal.py — [B2] ตาราง prefix รหัสไปรษณีย์ (2 หลักแรก) → จังหวัด ของไทย (data-driven)

ที่มา (verifiable, ไม่เดาจากความจำ): derive จากชุดข้อมูล geography ของไทย
  (thailand-geography-data/thailand-geography-json — รหัสไปรษณีย์จริง 7,436 ตำบล/แขวง)
  → 'จังหวัด → เซ็ต prefix 2 หลักที่ถูกต้อง' ครบ 77 จังหวัด. เป็น dict แก้ไข/เพิ่มได้ง่าย.

ใช้โดย r_addr006: ตรวจ 'รหัสไปรษณีย์ ↔ จังหวัด ไม่สอดคล้อง' โดยไม่พึ่ง master.
หมายเหตุสำคัญ (กัน false positive):
  • บาง prefix ครอบหลายจังหวัด (10 = กรุงเทพ+สมุทรปราการ ; 13 = อยุธยา+ลพบุรี ฯลฯ)
  • บางจังหวัดมีหลาย prefix (เชียงใหม่ = 50,58 ; นครราชสีมา = 30,36 ; ลพบุรี = 13,15,18 ฯลฯ)
  → จึง map เป็น 'จังหวัด → เซ็ต prefix' แล้วฟ้องเฉพาะเมื่อ "ไม่มีไปรษณีย์ใดในที่อยู่ตรงจังหวัดเลย".
  • กรุงเทพฯ เว้นไว้ — ADDR005 ตรวจช่วง 10000–10999 อยู่แล้ว (กันฟ้องซ้ำ).
"""
from __future__ import annotations
import re

# จังหวัด (ไทย) → tuple ของ prefix 2 หลักแรกของรหัสไปรษณีย์ที่ถูกต้อง (เรียงคงที่ = deterministic)
PROVINCE_POSTAL_PREFIXES = {
    'กระบี่': ('80', '81',),
    'กรุงเทพมหานคร': ('10',),
    'กาญจนบุรี': ('70', '71',),
    'กาฬสินธุ์': ('46',),
    'กำแพงเพชร': ('62',),
    'ขอนแก่น': ('40',),
    'จันทบุรี': ('22',),
    'ฉะเชิงเทรา': ('24',),
    'ชลบุรี': ('20',),
    'ชัยนาท': ('17',),
    'ชัยภูมิ': ('36',),
    'ชุมพร': ('86',),
    'ตรัง': ('92',),
    'ตราด': ('23',),
    'ตาก': ('63',),
    'นครนายก': ('26',),
    'นครปฐม': ('73',),
    'นครพนม': ('48',),
    'นครราชสีมา': ('30', '36',),
    'นครศรีธรรมราช': ('80',),
    'นครสวรรค์': ('60',),
    'นนทบุรี': ('11',),
    'นราธิวาส': ('96',),
    'น่าน': ('55',),
    'บึงกาฬ': ('38',),
    'บุรีรัมย์': ('31',),
    'ปทุมธานี': ('12',),
    'ประจวบคีรีขันธ์': ('77',),
    'ปราจีนบุรี': ('25',),
    'ปัตตานี': ('94',),
    'พระนครศรีอยุธยา': ('13',),
    'พะเยา': ('56',),
    'พังงา': ('82', '83',),
    'พัทลุง': ('93',),
    'พิจิตร': ('66',),
    'พิษณุโลก': ('65',),
    'ภูเก็ต': ('83',),
    'มหาสารคาม': ('44',),
    'มุกดาหาร': ('49',),
    'ยะลา': ('95',),
    'ยโสธร': ('35',),
    'ระนอง': ('85',),
    'ระยอง': ('21', '22',),
    'ราชบุรี': ('70',),
    'ร้อยเอ็ด': ('45',),
    'ลพบุรี': ('13', '15', '18',),
    'ลำปาง': ('52',),
    'ลำพูน': ('51',),
    'ศรีสะเกษ': ('33',),
    'สกลนคร': ('47',),
    'สงขลา': ('90',),
    'สตูล': ('91',),
    'สมุทรปราการ': ('10',),
    'สมุทรสงคราม': ('75',),
    'สมุทรสาคร': ('74',),
    'สระบุรี': ('18',),
    'สระแก้ว': ('27',),
    'สิงห์บุรี': ('16',),
    'สุพรรณบุรี': ('72',),
    'สุราษฎร์ธานี': ('84',),
    'สุรินทร์': ('32',),
    'สุโขทัย': ('64',),
    'หนองคาย': ('43',),
    'หนองบัวลำภู': ('39',),
    'อำนาจเจริญ': ('37',),
    'อุดรธานี': ('41',),
    'อุตรดิตถ์': ('53',),
    'อุทัยธานี': ('61',),
    'อุบลราชธานี': ('34',),
    'อ่างทอง': ('14',),
    'เชียงราย': ('57',),
    'เชียงใหม่': ('50', '58',),
    'เพชรบุรี': ('76',),
    'เพชรบูรณ์': ('67',),
    'เลย': ('42',),
    'แพร่': ('54',),
    'แม่ฮ่องสอน': ('58',),
}


# กรุงเทพฯ: ADDR005 ดูแลช่วง BKK แล้ว → ADDR006 เว้น (กันทับซ้อน)
_ADDR006_SKIP_PROVINCES = frozenset({'กรุงเทพมหานคร'})
_BKK_HINTS = ('กรุงเทพ', 'กทม')
_ZIP_RE = re.compile(r'(?<!\d)(\d{5})(?!\d)')
# [ADR-143/TN-02] เลขไทย ๐-๙ → อารบิก ก่อนจับ/เทียบรหัสไปรษณีย์. `\d` ของ Python เป็น Unicode จับ
#   '๘๓๐๐๐' ได้ แต่ `z[:2] in valid_pref` เทียบ '๘๓' กับ '83' (ASCII) ไม่ตรง → ADDR006/007 ฟ้อง FP
#   บนรหัสที่ "ถูกแต่เขียนเลขไทย". corpus = เลขอารบิกล้วน (0 เลขไทยในที่อยู่) → translate เป็น no-op → golden-neutral.
_THAI_DIGITS = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')

# [ADR-110] อักขระไทยที่ "ต่อคำ" (พยัญชนะ ก-ฮ + สระ/วรรณยุกต์) — ใช้ตรวจ word-boundary ของชื่อจังหวัด
#   กัน substring false-positive: ชื่อจังหวัดสั้น (เลย/ตาก/น่าน/ตรัง/ตราด/แพร่) ที่บังเอิญเป็นส่วนของคำอื่น
#   (เช่น "เลยกว่า"→เลย, "ตากสิน"→ตาก, "น่านฟ้า"→น่าน). ไทยไม่มีเว้นวรรค → ใช้ "อักขระข้างเคียง
#   ไม่ใช่ตัวต่อคำ" เป็นขอบ. ครอบคลุม U+0E01–0E2E (พยัญชนะ), 0E30–0E3A (สระล่าง/หลัง), 0E40–0E4E (สระหน้า/มาร์ก).
_THAI_WORD_CHAR = re.compile(r'[ก-ฮะ-ฺเ-๎]')
# คำนำหน้าจังหวัดที่มัก "ติดกัน" ไม่มีเว้นวรรค (จังหวัดเลย / จ.เลย) → ถือว่าขอบหน้า OK แม้ตามด้วยอักขระไทย
_PROV_INDICATORS = ('จังหวัด', 'จ.')


def _province_word_match(pv, addr):
    """[ADR-110] True ถ้า pv ปรากฏใน addr แบบ 'เป็นคำ' (มีขอบ ไม่ใช่ substring กลางคำอื่น).

    ขอบหน้า OK เมื่อ: อยู่ต้นสตริง / อักขระหน้าไม่ใช่ตัวต่อคำไทย / นำหน้าด้วย 'จังหวัด'|'จ.'.
    ขอบหลัง OK เมื่อ: อยู่ท้ายสตริง / อักขระหลังไม่ใช่ตัวต่อคำไทย (เว้นวรรค/ตัวเลข/เครื่องหมาย).
    conservative: ถ้าทุก occurrence อยู่กลางคำอื่น → ถือว่าไม่พบ (false-negative ดีกว่า false-positive).
    """
    start = 0
    n = len(addr)
    while True:
        i = addr.find(pv, start)
        if i < 0:
            return False
        j = i + len(pv)
        before_ok = (i == 0) or (not _THAI_WORD_CHAR.match(addr[i - 1])) \
            or any(addr[:i].endswith(p) for p in _PROV_INDICATORS)
        after_ok = (j >= n) or (not _THAI_WORD_CHAR.match(addr[j]))
        if before_ok and after_ok:
            return True
        start = i + 1


def province_in_address(addr):
    """คืนชื่อจังหวัดเดียวที่พบในที่อยู่ ; None ถ้าไม่พบ หรือพบหลายจังหวัด (กำกวม → conservative).

    [ADR-110] จับแบบ word-boundary (ดู _province_word_match) ไม่ใช่ substring ดิบ — กัน false-positive
    ชื่อจังหวัดสั้นที่เป็นส่วนของคำอื่น. golden-neutral บน corpus (ADDR006 ฟ้อง 0× ทั้งก่อน/หลัง — พิสูจน์ golden_master).
    """
    if not addr:
        return None
    found = [pv for pv in PROVINCE_POSTAL_PREFIXES if _province_word_match(pv, addr)]
    return found[0] if len(found) == 1 else None


def postal_province_mismatch(addr):
    """ตรวจ 'รหัสไปรษณีย์ ↔ จังหวัด' ไม่สอดคล้อง (ไม่พึ่ง master).

    คืน (province, postal, prefix) เมื่อ "ขัดกันชัด" = ในที่อยู่ระบุจังหวัด X แต่ไม่มีรหัสไปรษณีย์
    5 หลักใด ๆ ที่ prefix ตรงจังหวัด X เลย. คืน None (เงียบ) เมื่อ:
      - ดึงจังหวัดไม่ได้/กำกวม  - ไม่พบไปรษณีย์ 5 หลัก  - เป็นกรุงเทพฯ/มีคำว่า กรุงเทพ-กทม (ADDR005 ดูแล)
      - มีไปรษณีย์อย่างน้อยหนึ่งตัวที่ prefix ตรงจังหวัด (สอดคล้อง)
    conservative: false-negative ดีกว่า false-positive.
    """
    if not addr:
        return None
    province = province_in_address(addr)
    if province is None or province in _ADDR006_SKIP_PROVINCES:
        return None
    if any(h in addr for h in _BKK_HINTS):
        return None
    zips = _ZIP_RE.findall(addr.translate(_THAI_DIGITS))   # [ADR-143/TN-02] เลขไทย→อารบิก ก่อนจับรหัส
    if not zips:
        return None
    valid = PROVINCE_POSTAL_PREFIXES.get(province, ())
    if any(z[:2] in valid for z in zips):
        return None
    return (province, zips[0], zips[0][:2])


# ── [ADR-122] ADDR010 — จังหวัดที่ระบุในที่อยู่ "ไม่ใช่ 1 ใน 77 จังหวัดจริง" (สะกดผิด/ปลอม) ──
# ตัวย่อ/ชื่อไม่เป็นทางการที่ "ถูกต้อง" (ไม่ใช่ typo) — กัน false-positive
_PROVINCE_ALIASES = frozenset({
    'กรุงเทพ', 'กรุงเทพฯ', 'กทม', 'กทม.', 'กรุงเทพมหานครฯ',
    'อยุธยา', 'ศรีอยุธยา', 'บางกอก',
})
# token จับชื่อจังหวัดหลังคำนำหน้า 'จังหวัด'/'จ.' (Thai run ยาว 2-20 ตัว)
_PROV_TOKEN_RE = re.compile(r'(?:จังหวัด|จ\.)\s*([ก-๙]{2,20})')


def invalid_province_in_address(addr):
    """ตรวจว่าที่อยู่ระบุ 'จังหวัด X' ที่ X ไม่ใช่จังหวัดจริง (สะกดผิด/ปลอม) — ไม่พึ่ง master.

    คืน (token, suggestion|None) เมื่อพบจังหวัดที่ไม่ถูกต้อง ; None (เงียบ) เมื่อ:
      - ที่อยู่มีจังหวัดจริงอยู่แล้ว (province_in_address เจอ word-boundary)  → ถูก
      - ดึง token 'จังหวัด X' ไม่ได้ / X สั้น < 3 ตัว                        → ข้อมูลไม่พอ
      - X เป็นตัวย่อ/ชื่อไม่เป็นทางการที่ยอมรับได้ (กรุงเทพ/อยุธยา ฯลฯ)       → ถูก
      - X เป็น prefix/ส่วนของจังหวัดจริง หรือจังหวัดจริงเป็น prefix ของ X     → ถูก (ตัดท้ายเกิน)
    conservative (false-negative ดีกว่า false-positive): ฟ้องเฉพาะกรณีชัด.
    """
    if not isinstance(addr, str):          # [ADR-122 hardening] กันครัชเมื่อ addr เป็น non-str (int/list/None)
        addr = '' if addr is None else str(addr)
    if not addr:
        return None
    # มีจังหวัดจริงในที่อยู่ (word-boundary) → ถูกต้อง ไม่ต้องตรวจ
    if province_in_address(addr) is not None:
        return None
    m = _PROV_TOKEN_RE.search(addr)
    if not m:
        return None
    tok = m.group(1).strip()
    if len(tok) < 3 or tok in _PROVINCE_ALIASES:
        return None
    # ยอมรับถ้า token "ตรง/ใกล้ชิด" จังหวัดจริง — แต่กัน 'จังหวัด+คำเกิน' (เช่น สุโขทัยธานี = สุโขทัย+ธานี)
    for pv in PROVINCE_POSTAL_PREFIXES:
        if tok == pv:
            return None
        if tok.startswith(pv) and len(tok) - len(pv) <= 1:   # จังหวัด + วรรณยุกต์/ฯ (เชียงใหม่ฯ) → ถูก
            return None
        if pv.startswith(tok) and len(pv) - len(tok) <= 2:   # จังหวัดถูกตัดท้ายเล็กน้อย → conservative ถือว่าถูก
            return None
    for al in _PROVINCE_ALIASES:
        if tok == al or (tok.startswith(al) and len(tok) - len(al) <= 1):
            return None
    # X ไม่ตรงจังหวัดจริงเลย → หา "ใกล้เคียงสุด" (typo) เพื่อแนะนำ
    try:
        from rapidfuzz import process, fuzz
        best = process.extractOne(tok, list(PROVINCE_POSTAL_PREFIXES.keys()),
                                  scorer=fuzz.ratio, score_cutoff=70)
        suggestion = best[0] if best else None
    except Exception:
        suggestion = None
    return (tok, suggestion)


# ── [ADR-122] ADDR007 — รหัสไปรษณีย์ ↔ อำเภอ/เขต ไม่สอดคล้อง (เสริม ADDR006 ระดับจังหวัด) ──
_DISTRICT_TOKEN_RE = re.compile(r'(?:อำเภอ|อ\.|เขต|ข\.)\s*([ก-๙]{2,25})')


def district_postal_mismatch(addr):
    """ตรวจ 'รหัสไปรษณีย์ ↔ อำเภอ/เขต' ไม่สอดคล้อง — ไม่พึ่ง master. conservative สุด (กัน FP).

    คืน (district_token, postal, ชื่ออำเภอที่รหัสนี้เป็นจริง) เฉพาะเมื่อ "มั่นใจว่าผิดอำเภอ" =
      - ดึงจังหวัด (word-boundary) + อำเภอ (อำเภอ/อ./เขต/ข.) + รหัสไปรษณีย์ที่ prefix ตรงจังหวัด ได้ครบ
      - (จังหวัด, อำเภอ) อยู่ในตาราง DISTRICT_POSTAL  และรหัสนั้น "ไม่อยู่ในชุดของอำเภอนั้น"
      - แต่รหัสนั้น "อยู่ในอำเภออื่นของจังหวัดเดียวกัน" (= รหัสจริงแต่คนละอำเภอ → ผิดชัด)
    คืน None ทุกกรณีอื่น (ดึงไม่ครบ / อำเภอไม่รู้จัก / รหัสไม่อยู่ในจังหวัดเลย → ปล่อย ADDR006/typo).
    """
    if not isinstance(addr, str):          # [ADR-122 hardening] กันครัชเมื่อ addr เป็น non-str
        addr = '' if addr is None else str(addr)
    if not addr:
        return None
    province = province_in_address(addr)
    # [ADR-140] dead-guard fix: เดิม `if None or in SKIP: if None: return` → กรุงเทพฯ (ใน SKIP) ตกผ่าน
    #   ไม่เคยถูกเว้นจริง (ขัด intent ที่ว่า ADDR005 ดูแลโซน กทม.แล้ว). คืน None ทั้ง None และ SKIP-province.
    if province is None or province in _ADDR006_SKIP_PROVINCES:
        return None
    try:
        from thai_district import DISTRICT_POSTAL
    except Exception:
        return None
    dz = DISTRICT_POSTAL.get(province)
    if not dz:
        return None
    zips = _ZIP_RE.findall(addr.translate(_THAI_DIGITS))   # [ADR-143/TN-02] เลขไทย→อารบิก ก่อนจับรหัส
    valid_pref = PROVINCE_POSTAL_PREFIXES.get(province, ())
    prov_zips = [z for z in zips if z[:2] in valid_pref]
    if len(prov_zips) != 1:                       # ไม่มี/หลายรหัสจังหวัด → กำกวม → เงียบ
        return None
    zip5 = prov_zips[0]
    m = _DISTRICT_TOKEN_RE.search(addr)
    if not m:
        return None
    tok = m.group(1).strip()
    if len(tok) < 2:
        return None
    # จับคู่ token อำเภอกับอำเภอจริง (exact ก่อน ; ไม่งั้น prefix ที่ "ไม่กำกวม" = มีตัวเดียว)
    matched = None
    if tok in dz:
        matched = tok
    else:
        cands = [d for d in dz if d.startswith(tok) or tok.startswith(d)]
        if len(cands) == 1:
            matched = cands[0]
    if matched is None:                           # อำเภอไม่รู้จัก/กำกวม → เงียบ
        return None
    if zip5 in dz[matched]:                        # รหัสตรงอำเภอ → ถูก
        return None
    # รหัสนี้เป็นของ "อำเภออื่น" ในจังหวัดเดียวกันไหม → มั่นใจว่าผิดอำเภอ
    others = [d for d, zs in dz.items() if d != matched and zip5 in zs]
    if not others:                                # รหัสไม่อยู่อำเภอใดเลย (P.O.box/typo) → เงียบ (กัน FP)
        return None
    return (tok, zip5, others[0])
