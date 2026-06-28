# -*- coding: utf-8 -*-
"""code_labels.py — แปลง 56 รหัส → (field บล็อกบริษัท, คำภาษาคน, เลน)

ที่มา: อ่าน detail จริงจากบิลใน /mnt/project แล้วตั้งคำให้ "คนอ่านรู้เรื่องทันที"
  ❌ ไม่เอา: '#2: อังกฤษ+ไทยติดกัน (ควรเว้นวรรค) [soft]'
  ✅ เอา:    'ชื่อสินค้าควรเว้นวรรคอังกฤษ-ไทย'

3 ส่วน:
  FIELD[code]  → ช่องในบล็อกบริษัท (ชื่อบจ./ที่อยู่/เลขภาษี/สาขา/เลขที่/วันที่/เลขที่ iv/
                 รายการสินค้า/ยอดก่อน vat/ยอดหลัง vat)
  LABEL[code]  → คำภาษาคนสั้น ๆ
  LANE[code]   → 'fix'(ต้องแก้) | 'check'(ควรตรวจ) | 'review'(ข้อสังเกต) | 'master'(ไม่มี master ตรวจไม่ได้)

ใช้โดย viewers/composer — advisory ล้วน ไม่แตะ engine/golden.
"""
from __future__ import annotations

import re
from collections import OrderedDict

# ── ช่อง (field) ในบล็อกบริษัท ───────────────────────────────────────────────
F_NAME = "ชื่อบจ."
F_ADDR = "ที่อยู่"
F_TAX = "เลขที่ผู้เสียภาษี"
F_BRANCH = "สาขา/สนญ."
F_DOCNO = "เลขที่"
F_DATE = "วันที่"
F_IV = "เลขที่ iv"
F_ITEM = "รายการสินค้า"
F_PREVAT = "ยอดก่อน vat"
F_POSTVAT = "ยอดหลัง vat"

# ── เลน ──────────────────────────────────────────────────────────────────────
FIX = "fix"        # ผิดจริง ต้องแก้
CHECK = "check"    # ควรตรวจด้วยตา (อาจ convention/ราคาแปลก)
REVIEW = "review"  # ข้อสังเกต ไม่ใช่ must-fix
MASTER = "master"  # ต้องมี master ถึงตัดสินได้ (ตอนนี้ไม่มี → ตรวจไม่ได้)
NOTE = "note"      # [v9.2 งาน D] ข้อสังเกตเชิงหมายเหตุ (ลงวันที่ล่วงหน้า/เดือนไม่ตรงไฟล์) —
#                    ไม่ใช่ error ของช่อง → ไม่ทำให้ช่องนั้น "ผิด" แต่ยกขึ้นบรรทัด "หมายเหตุ :" แยกท้ายบล็อก

# ── ตารางหลัก: code → (field, label, lane) ───────────────────────────────────
MAP = {
    # บริษัท
    "CMP001": (F_NAME, "ชื่อบริษัทไม่ตรง master", FIX),
    "CMP002": (F_NAME, "คำนำหน้านิติบุคคลผิด", FIX),
    "CMP003": (F_NAME, "ใช้ชื่อแบรนด์แทนชื่อนิติบุคคล", FIX),
    "CMP004": (F_NAME, "เว้นวรรคชื่อบริษัทไม่ตรง master", CHECK),
    "CMP005": (F_NAME, "ชื่อบริษัทไม่ครบ (ขาด 'จำกัด')", FIX),
    "CMP006": (F_NAME, "ชื่อไม่ตรง 100% กับ ภ.พ.20", CHECK),
    # ที่อยู่
    "ADDR001": (F_ADDR, "ที่อยู่ไม่ครบ", FIX),
    "ADDR002": (F_ADDR, "ตัวสะกดถนน/แขวงผิด", CHECK),
    "ADDR003": (F_ADDR, "ชั้น/อาคาร/ห้อง ไม่ตรง master", CHECK),
    "ADDR004": (F_ADDR, "รูปแบบที่อยู่กรุงเทพ/ต่างจังหวัดผิด", CHECK),
    "ADDR005": (F_ADDR, "รหัสไปรษณีย์ผิด", CHECK),
    "ADDR006": (F_ADDR, "รหัสไปรษณีย์ไม่ตรงจังหวัด", CHECK),  # [B2] ไปรษณีย์↔จังหวัด ไม่สอดคล้อง
    "ADDR007": (F_ADDR, "รหัสไปรษณีย์ไม่ตรงอำเภอ/เขต", CHECK),  # [ADR-122] ไปรษณีย์↔อำเภอ ไม่สอดคล้อง
    "ADDR010": (F_ADDR, "จังหวัดไม่ใช่จังหวัดจริง", CHECK),     # [ADR-122] จังหวัดสะกดผิด/ปลอม
    # เลขภาษี
    "TAX001": (F_TAX, "เลขภาษีไม่ครบ 13 หลัก", FIX),
    "TAX002": (F_TAX, "ไม่พบเลขภาษี 13 หลักที่ถูกต้อง", FIX),  # [A4] label ให้ตรง r_tax002 (จับกลุ่มเลข 13 หลัก ไม่ใช่ตรวจ 'ตัวอักษรปน')
    "TAX003": (F_TAX, "เลขภาษีไม่ตรงกับบริษัท (master)", FIX),
    "TAX004": (F_TAX, "เลขภาษีน่าจะ OCR ผิด", CHECK),
    "TAX005": (F_TAX, "เลขภาษีเป็นของบริษัทอื่นใน master", FIX),
    "TAX006": (F_TAX, "เลขภาษี checksum ไม่ผ่าน", FIX),
    "TAX007": (F_TAX, "ประเภทนิติบุคคล (หลักแรก) ผิดปกติ", CHECK),
    "TAX008": (F_TAX, "เลขภาษีเดียวกันแต่ชื่อบริษัทต่างกัน", FIX),  # [B1] สัญญาณสวมเลข/ปลอม (cross-bill)
    "TAX009": (F_TAX, "ชื่อบริษัทเดียวกันใช้เลขภาษีต่างกัน", CHECK),  # [BS-3] ผู้ขายรายเดียวพิมพ์เลขภาษีผิดบางใบ (cross-bill) — เลขใดเลขหนึ่งน่าจะพิมพ์ผิด → ควรตรวจ
    # สาขา
    "BR001": (F_BRANCH, "รหัสสาขาผิดรูปแบบ", FIX),
    "BR002": (F_BRANCH, "ไม่ได้ระบุสาขา/สนญ.", FIX),
    "BR003": (F_BRANCH, "สาขาไม่สม่ำเสมอในไฟล์", CHECK),
    "BR004": (F_BRANCH, "สาขาไม่ตรงทะเบียน master", FIX),  # [B3] เทียบ branch กับ master
    # เอกสาร / วันที่
    "DOC001": (F_DATE, "ลงวันที่ผิด", FIX),
    "DOC002": (F_DATE, "ลงวันที่ผิด", FIX),
    "DOC003": (F_DOCNO, "เลขที่เอกสารซ้ำ (ใช้เลขเดียวกันหลายใบ)", FIX),
    "DT001": (F_DATE, "เดือนในบิลไม่ตรงงวดที่ชื่อไฟล์ระบุ", NOTE),
    "DT002": (F_DATE, "วันที่เป็นอนาคต", NOTE),
    "DT003": (F_DATE, "ปี พ.ศ./ค.ศ. ไม่ชัดเจน", NOTE),
    "DT004": (F_DATE, "ลงวันที่ผิด", FIX),
    "DT005": (F_DATE, "บิลไม่มีวันที่", FIX),
    "DT006": (F_DATE, "วันที่ไม่ถูกต้อง", FIX),
    # เลขที่ใบกำกับ
    "IV001": (F_IV, "prefix เลขใบกำกับไม่ตรง", REVIEW),
    "IV002": (F_IV, "เลขใบกำกับผิดรูปแบบ", FIX),
    "IV003": (F_IV, "เลขใบกำกับซ้ำข้ามวัน", FIX),
    "IV004": (F_IV, "เลขใบกำกับไม่ไล่ตามวัน", CHECK),
    "IV005": (F_IV, "บิลไม่มีเลขที่ใบกำกับ", FIX),
    "IV006": (F_IV, "ใบกำกับภาษีอย่างย่อ (เครมไม่ได้)", FIX),
    "IV007": (F_IV, "เลขใบกำกับไม่สมเหตุสมผล (เลขขยะ)", FIX),  # [D1] ศูนย์ล้วน/เศษยอดเงิน/placeholder
    # รายการสินค้า
    "ITM001": (F_ITEM, "จำนวน×ราคา ≠ ยอดรายการ", FIX),
    "ITM002": (F_ITEM, "ลำดับรายการสินค้าผิด", FIX),
    "ITM003": (F_ITEM, "ชื่อสินค้าคลุมเครือ", REVIEW),
    "ITM004": (F_ITEM, "มีอักขระล่องหน/รูปแบบแปลกในชื่อ", REVIEW),
    "ITM005": (F_ITEM, "หน่วยอาจไม่เหมาะกับสินค้า", REVIEW),
    "ITM006": (F_ITEM, "หน่วยสินค้าผิด", CHECK),
    "ITM007": (F_ITEM, "ชื่อสินค้าสั้นเกินไป", REVIEW),
    "ITM008": (F_ITEM, "ราคาต่อหน่วยผิดปกติ", CHECK),
    "ITM009": (F_ITEM, "ใช้ชื่อย่อ (alias) แทนชื่อเต็ม", REVIEW),
    "ITM010": (F_ITEM, "คำสินค้าผิด", FIX),
    "ITM011": (F_ITEM, "คำสินค้าผิด", FIX),
    "ITM012": (F_ITEM, "ชื่อสินค้าน่าจะพิมพ์คล้ายคำอื่น", REVIEW),
    "ITM013": (F_ITEM, "ลำดับรายการสินค้าผิด", CHECK),
    "ITM014": (F_ITEM, "ลำดับรายการสินค้าผิด", CHECK),
    "ITM015": (F_ITEM, "หน่วยสินค้าผิด", FIX),
    "ITM016": (F_ITEM, "รายการสินค้าซ้ำ", FIX),
    "ITM017": (F_ITEM, "จำนวน/ราคาติดลบ", FIX),
    "ITM018": (F_ITEM, "จำนวน=0 แต่มียอดเงิน", FIX),
    "ITM019": (F_ITEM, "หน่วยสะกดผิด/ขาดหาย", CHECK),
    "ITM020": (F_ITEM, "ทั้งบิลไม่มีหน่วยสินค้า", CHECK),
    # ยอดเงิน / VAT
    "VAT001": (F_PREVAT, "ผลรวมรายการ ≠ ยอดก่อน VAT", FIX),
    "VAT002": (F_POSTVAT, "VAT 7% คำนวณไม่ตรง", FIX),
    "VAT003": (F_POSTVAT, "ยอดรวมทั้งสิ้นไม่ตรง", FIX),
    "VAT004": (F_POSTVAT, "ปัดเศษยอดผิดปกติ", CHECK),
    "VAT005": (F_POSTVAT, "ยอดเงินผิดปกติ", FIX),
    "VAT006": (F_POSTVAT, "ราคารวม VAT แล้ว (VAT included)", REVIEW),
    "VAT007": (F_POSTVAT, "ส่วนลดไม่สอดคล้องยอด", FIX),
    "VAT008": (F_POSTVAT, "VAT เป็นศูนย์", REVIEW),
    "VAT011": (F_POSTVAT, "ใบมียอดแต่ VAT เป็นศูนย์ (ยกเว้นจริง/ลืมคิด?)", REVIEW),  # [BS-2] sub≈total → VAT008 เว้น ; VAT011 เก็บเป็นข้อสังเกต
    "VAT009": (F_PREVAT, "ยอดก่อน VAT เป็นศูนย์/ไม่มี", FIX),
    "VAT010": (F_POSTVAT, "VAT ไม่ได้ตรวจจริง", REVIEW),
    "VAT012": (F_POSTVAT, "ยอดตัวอักษรไม่ตรงกับตัวเลข", FIX),  # [ADR-122] บาทอักษร≠ตัวเลข (ปลอมแปลง)
}

# ── ลำดับ field ในบล็อกบริษัท (ตามฟอร์แมตที่ผู้ใช้ต้องการ) ───────────────────
FIELD_ORDER = [F_NAME, F_ADDR, F_TAX, F_BRANCH, F_DOCNO, F_DATE, F_IV, F_ITEM, F_POSTVAT, F_PREVAT]

# ── [A1] ช่อง "ตัวตน" ที่จะพูดว่า 'ตรง' ได้ ต้องเทียบ master จริงก่อน ──────────────
#   กลไก "เทียบเท่าเลน MASTER" แต่อยู่ระดับ **ช่อง** ไม่ใช่ระดับ **รหัส** — เพราะ
#   "กฎที่ฟ้องแล้ว = ตรวจแล้วจริง" (เช่น CMP001 ฟ้อง = เทียบ master แล้วไม่ตรง) ห้ามมีเลน MASTER
#   (test_report_consistency เป็น tripwire กันไว้). การ downgrade 'ตรง'→'ตรวจไม่ได้' จึงตัดสินที่
#   "ช่องตัวตนที่ยังไม่มี issue (mark=ok) แต่ไม่เคยเทียบ master จริง" — composer ใช้ชุดนี้รู้ว่า
#   ช่องไหนต้อง downgrade เมื่อผู้ขายรายนั้น "ไม่อยู่ใน master / ไม่มี master / master ไม่มีข้อมูลช่องนี้".
MASTER_DEPENDENT_FIELDS = (F_NAME, F_TAX, F_ADDR, F_BRANCH)

# เหตุผลย่อยของ "ตรวจไม่ได้" (แยกให้คนอ่านเข้าใจว่าทำไมยังไม่ใช่ 'ตรง') — ใช้ '-' นำ (อักษรพื้นฐาน
#   ตามมติ v9.2 งาน C ที่เลิก em-dash/emoji). ทุกข้อความมี '(ตรวจไม่ได้)' กำกับชัด.
UNCHECKABLE_NO_MASTER = "- ไม่มีใน master (ตรวจไม่ได้)"               # match_company ไม่เจอผู้ขายรายนี้
UNCHECKABLE_MASTER_NO_FIELD = "- ทะเบียนไม่มีข้อมูลช่องนี้ (ตรวจไม่ได้)"  # เจอผู้ขายแต่ master ไม่มี field นี้
UNCHECKABLE_BILL_UNREADABLE = "- อ่านจากบิลไม่ได้ (ตรวจไม่ได้)"        # บิลเอง parse field นี้ไม่ติด

# ชื่อย่อช่องตัวตนสำหรับบรรทัดสรุปท้ายบล็อก (footer) ให้กระชับ
MASTER_FIELD_SHORT = {F_NAME: "ชื่อบจ.", F_TAX: "เลขภาษี", F_ADDR: "ที่อยู่", F_BRANCH: "สาขา"}

# ── [A1] ช่องตัวตน → คีย์ "อ่านจากบิล" / คีย์ "อ้างอิงในทะเบียน(master)" (single source) ──────
#   ใช้ร่วมทุก composer (super_ultra_viewer + vendor_report) เพื่อตัดสิน honesty ให้สอดคล้องกัน.
_IDENTITY_BILL_KEYS = {
    F_NAME: ("company", "company_raw"),
    F_TAX: ("tax_id", "tax_id_raw"),
    F_ADDR: ("address",),
    F_BRANCH: ("branch", "branch_no"),
}
_IDENTITY_MASTER_KEYS = {
    F_NAME: ("name", "name_alt"),
    F_TAX: ("tax_id",),
    F_ADDR: ("address_parts", "address_full", "address"),
    F_BRANCH: ("branch", "branch_no"),
}


def bill_field_readable(field, bills) -> bool:
    """ช่องตัวตนนี้อ่านค่าจากบิลได้ไหม (มีอย่างน้อย 1 ใบในกลุ่มที่ค่าไม่ว่าง)."""
    for b in (bills or []):
        for k in _IDENTITY_BILL_KEYS.get(field, ()):
            if str((b or {}).get(k) or "").strip():
                return True
    return False


def master_has_field(field, entry) -> bool:
    """ทะเบียน (master entry) มีข้อมูลอ้างอิงของช่องตัวตนนี้ไหม (เช่น address_parts / branch)."""
    if not entry:
        return False
    for k in _IDENTITY_MASTER_KEYS.get(field, ()):
        if entry.get(k):
            return True
    return False


_NO_MASTER_KEY = "(ไม่พบใน master)"


def group_master_status(bills, master_present, masters):
    """คืน (matched, key, entry) ของกลุ่มผู้ขาย — honesty รายผู้ขาย/รายบิล (ใช้โดย super_ultra_viewer).

    ความน่าเชื่อถือ: สัญญาณรายบิล b['master_key'] (run_rules ตั้งจาก match_company) มาก่อน —
    ถ้าบิลไม่มี (เทส/ผู้เรียกปั้น bill เอง) ค่อย fallback ไป flag global master_present.
    masters (dict) ถ้าส่งมา → ใช้ดู "ทะเบียนมีข้อมูลช่องนี้ไหม" (เหตุผลย่อยที่ 2).
    """
    from collections import Counter
    keys = [b.get("master_key") for b in (bills or []) if b.get("master_key") is not None]
    if keys:
        matched = [k for k in keys if k and k != _NO_MASTER_KEY]
        if matched:
            g_key = Counter(matched).most_common(1)[0][0]
            return True, g_key, (masters or {}).get(g_key)
        return False, None, None
    return bool(master_present), None, None


def uncheckable_reason(field, bills, matched, entry):
    """เหตุผล "ตรวจไม่ได้" ของช่องตัวตน 1 ช่อง — คืนถ้อยคำ หรือ None ถ้า 'ตรง' จริง.

    'ตรง' จริง = อ่านค่าจากบิลได้ + ผู้ขายแมตช์ master + ทะเบียนมีข้อมูลช่องนี้ (เทียบแล้วไม่เจอ error).
    matched : ผู้ขายรายนี้เทียบ master ได้ไหม (composer แต่ละตัวคำนวณเองจาก master_key/หา entry).
    entry   : master record ของผู้ขาย (None ถ้าไม่รู้/ไม่ส่ง → ข้ามการเช็ค "ทะเบียนมี field ไหม").
    """
    if not bill_field_readable(field, bills):
        return UNCHECKABLE_BILL_UNREADABLE          # บิลเองอ่านช่องนี้ไม่ติด
    if not matched:
        return UNCHECKABLE_NO_MASTER                # ผู้ขายไม่อยู่ใน master (รวมกรณีไม่มี master เลย)
    if entry is not None and not master_has_field(field, entry):
        return UNCHECKABLE_MASTER_NO_FIELD          # เจอผู้ขายแต่ทะเบียนไม่มีข้อมูลช่องนี้
    return None                                     # เทียบ master จริงแล้ว → 'ตรง'


def apply_identity_honesty(verdicts, bills, master_present, masters=None):
    """[A1] downgrade ช่องตัวตน (mark=ok) ที่ "ไม่เคยเทียบ master จริง" → 'ตรวจไม่ได้' (mutate verdicts).

    เรียกหลังเดิน viewers — override เฉพาะ mark=ok (ไม่กลบ error ที่ไม่พึ่ง master เช่น CMP005/TAX001).
    """
    matched, _key, entry = group_master_status(bills, master_present, masters)
    for f in MASTER_DEPENDENT_FIELDS:
        v = verdicts.get(f)
        if not v or v.get("mark") != "ok":
            continue
        reason = uncheckable_reason(f, bills, matched, entry)
        if reason is not None:
            v["status"] = reason
            v["mark"] = "master"

_DEFAULT = (F_ITEM, "พบข้อสังเกต", CHECK)


def field_of(code: str) -> str:
    return MAP.get(code, _DEFAULT)[0]


def label_of(code: str) -> str:
    return MAP.get(code, _DEFAULT)[1]


def lane_of(code: str) -> str:
    return MAP.get(code, _DEFAULT)[2]


# ── [v9.2 งาน D] ถ้อยคำสำหรับบรรทัด "หมายเหตุ :" (เลน NOTE) ───────────────────
#   ไม่ใช่ error ของช่อง — เป็นข้อสังเกตเชิงบริบทที่ผู้ใช้อนุญาตให้ยกขึ้นหมายเหตุ
NOTE_PHRASE = {
    "DT001": "วันที่ในบิลไม่ตรงงวดที่ชื่อไฟล์ระบุ",
    "DT002": "ลงวันที่ล่วงหน้า",
    "DT003": "ปี พ.ศ./ค.ศ. ไม่ชัดเจน",
}


def note_phrase(code: str) -> str:
    """ถ้อยคำหมายเหตุของรหัสเลน NOTE (เช่น DT002 → 'ลงวันที่ล่วงหน้า')."""
    return NOTE_PHRASE.get(code, label_of(code))


def short_detail(code: str, detail: str) -> str:
    """ดึง 'ส่วนเสริมสั้น' จาก detail ให้คนเห็นบริบท (ไม่ใช่ jargon ยาว).

    เช่น ITM010 '#2: "มั้วน" → "ม้วน" ...' → '#2 มั้วน→ม้วน' ; ITM018 '#1: qty=0 ...' → '#1 จำนวน 0'.
    """
    d = detail or ""
    seq = ""
    m = re.match(r"\s*#(\d+)", d)
    if m:
        seq = f"#{m.group(1)}"
    m2 = re.search(r'"([^"]+)"\s*→\s*"([^"]+)"', d)
    if m2:
        return f"{seq} {m2.group(1)}→{m2.group(2)}".strip()
    if "qty=0" in d:
        return f"{seq} จำนวน 0".strip()
    if "ซ้ำ" in d:
        return seq or "ซ้ำ"
    return seq


# ── คำแนะนำ "ต้องทำอะไร" ต่อช่อง (ให้คน/บัญชีลงมือแก้ได้ทันที) ────────────────
ACTION_BY_FIELD = {
    F_NAME:    "เปิดไฟล์ต้นฉบับ แก้ชื่อนิติบุคคลให้ตรง ภ.พ.20 (คำนำหน้า/‘จำกัด’/เว้นวรรค)",
    F_ADDR:    "ตรวจที่อยู่ในใบกำกับให้ตรงทะเบียน (เลขที่/แขวง/เขต/ไปรษณีย์)",
    F_TAX:     "ตรวจเลขผู้เสียภาษี 13 หลักให้ครบและถูกต้อง",
    F_BRANCH:  "ระบุ ‘สำนักงานใหญ่’ หรือเลขสาขา 5 หลักให้ชัดเจน",
    F_DOCNO:   "แก้เลขที่เอกสารที่ซ้ำ/ผิดรูปแบบ (อย่าใช้เลขซ้ำหลายใบ)",
    F_DATE:    "แก้วันที่ในบิลให้ตรงกับชื่อชีต/งวดที่ระบุ (ระวังก๊อปชีตแล้วลืมแก้)",
    F_IV:      "แก้เลขใบกำกับให้ถูกรูปแบบและไล่ลำดับตามวันที่",
    F_ITEM:    "เปิดไฟล์ต้นฉบับ แก้ชื่อ/หน่วย/จำนวนของรายการที่ระบุ",
    F_PREVAT:  "ตรวจผลรวมรายการ = ยอดก่อน VAT",
    F_POSTVAT: "ตรวจ VAT 7% และยอดรวมทั้งสิ้นให้ถูกต้อง",
}


def action_for(field: str) -> str:
    return ACTION_BY_FIELD.get(field, "ตรวจสอบความถูกต้องของช่องนี้")


def field_of_issue(issue: dict) -> str:
    return field_of(issue.get("code", ""))


def human_issue(issue: dict) -> str:
    """issue → 'คำภาษาคน (บริบทสั้น)' เช่น 'ชื่อสินค้าสะกดผิด (#3 มั้วน→ม้วน)'."""
    code = issue.get("code", "")
    lab = label_of(code)
    sd = short_detail(code, issue.get("detail", ""))
    return f"{lab} ({sd})" if sd else lab


def clean_detail(code: str, detail: str) -> str:
    """แปลง detail ดิบ → ข้อความที่บัญชีอ่านแล้วลงมือแก้ได้ทันที (ของเดิม→ที่ควร / สินค้า / หน่วย).

    ดึงจากรูปแบบ detail จริงของแต่ละรหัส (ตรวจกับข้อมูลจริงใน /mnt/project แล้ว).
    """
    d = (detail or "").strip()
    d_nohdr = re.sub(r"^\s*#\d+[:\s]*", "", d)            # ตัด '#N:' หน้าออก (ลำดับแยกคอลัมน์แล้ว)
    if code == "CMP004":                                   # เว้นวรรคชื่อบริษัท: ย่อเหลือจำนวนช่อง (เลิกโชว์สตริง ␣ ยาว ๆ)
        m = re.search(r"ไฟล์มี\s*(\d+)\s*ช่องว่าง\s*/\s*master\s*มี\s*(\d+)", d)
        return (f"เว้นวรรคชื่อบริษัทไม่ตรง master (ไฟล์ {m.group(1)} ช่อง / master {m.group(2)} ช่อง)"
                if m else "เว้นวรรคชื่อบริษัทไม่ตรง master")
    if code == "TAX005":                                   # เลขภาษีเป็นของบริษัทอื่น: บอกเจ้าของจริง vs ชื่อในบิล
        mo = re.search(r"เป็นของ\s*'([^']*)'", d)
        mn = re.search(r"ใช้ชื่อ\s*'([^']*)'", d)
        mt = re.search(r"TaxID\s*(\d+)", d)
        if mo and mn:
            tx = f"{mt.group(1)} " if mt else ""
            return f'เลขภาษี {tx}เป็นของ "{mo.group(1)}" แต่บิลใช้ชื่อ "{mn.group(1)}"'
        return d_nohdr
    if code == "CMP006":                                   # ชื่อไม่ตรง 100%: ย่อเหลือ บิล vs ภ.พ.20
        mb = re.search(r"บิล='([^']*)'", d)
        mm = re.search(r"ภ\.พ\.20='([^']*)'", d)
        if mb and mm:
            return f'ชื่อในบิล "{mb.group(1)}" ไม่ตรง ภ.พ.20 "{mm.group(1)}"'
        return d_nohdr
    if code == "ITM019":                                   # หน่วยสะกดผิด/ขาด: ย่อเหลือสินค้า + หน่วย→ที่ควร
        mp = re.search(r'"([^"]+)"', d)
        prod = mp.group(1).strip() if mp else ""
        if "ไม่มีหน่วย" in d:
            return (f"สินค้า: {prod} | ไม่มีหน่วยสินค้า (ช่องหน่วยว่างในต้นฉบับ)" if prod else "ไม่มีหน่วยสินค้า (ช่องหน่วยว่างในต้นฉบับ)")
        mu = re.search(r'หน่วย\s*"([^"]+)".*?ควรเป็น\s*"([^"]+)"', d)
        if mu:
            # [recheck] เก็บรูป 'ควรเป็น' ไว้ใน "ราย detail ภายใน" (council/viewer ใช้จำแนก typo↔หน่วยขาด) —
            #   การแสดงผลต่อผู้ใช้ตัด 'ควรเป็น' ออกที่ชั้น render (super_ultra_viewer) ให้เหลือ 'หน่วย X'
            return (f"สินค้า: {prod} | " if prod else "") + f'หน่วย "{mu.group(1)}" ควรเป็น "{mu.group(2)}"'
        return d_nohdr
    if code == "ITM010":                                   # สะกดผิด: ของเดิม→ที่ควร + ชื่อสินค้า
        mxy = re.search(r'"([^"]+)"\s*→\s*"([^"]+)"', d)
        mp = re.search(r'ใน\s*"([^"]+)"', d)
        xy = f'แก้ "{mxy.group(1)}" → "{mxy.group(2)}"' if mxy else d_nohdr
        return xy + (f' | สินค้า: {mp.group(1).strip()}' if mp else "")
    if code == "ITM011":
        m = re.search(r'"([^"]+)"\s*ใกล้เคียง\s*"([^"]+)"', d)
        return f'"{m.group(1)}" น่าจะเป็น "{m.group(2)}" (สะกดผิด)' if m else d_nohdr
    if code in ("ITM005", "ITM006"):                       # หน่วยไม่เหมาะ: สินค้า + หน่วยปัจจุบัน→ควรใช้
        mp = re.search(r'"([^"]+)"', d)
        mu = re.search(r'หน่วย=([^\s]+)', d)
        ms = re.search(r'\[([^\]]+)\]', d)
        prod = mp.group(1).strip() if mp else "?"
        cur = mu.group(1) if mu else "?"
        sug = ms.group(1).replace("'", "").replace('"', "") if ms else ""
        return f'สินค้า: {prod} | หน่วยปัจจุบัน "{cur}"' + (f' ควรใช้ {sug}' if sug else "")
    if code == "ITM015":
        mp = re.search(r'"([^"]+)"', d)
        ms = re.search(r'\[([^\]]+)\]', d)
        prod = mp.group(1).strip() if mp else "?"
        units = ms.group(1).replace("'", "").replace('"', "") if ms else ""
        return f'สินค้า: {prod} | ใช้หน่วยปนกัน: {units}'
    if code == "ITM018":
        m = re.search(r'amount=([\d,\.]+)', d)
        return f'จำนวน=0 แต่มียอด {m.group(1)} บาท' if m else d_nohdr
    if code == "ITM016":
        m = re.search(r'#(\d+)\s*และ\s*#(\d+)', d)
        return f'รายการซ้ำ: #{m.group(1)} กับ #{m.group(2)}' if m else d_nohdr
    if code == "ITM002":                                   # running ลำดับรายการสินค้า: ซ้ำ / ขาด
        m = re.search(r'\[([^\]]+)\]', d)
        nums = re.sub(r'\s*,\s*', ' และ ', m.group(1).strip()) if m else ""
        if "ซ้ำ" in d:
            return f"ลำดับที่ {nums} ซ้ำกัน" if nums else "มีลำดับสินค้าซ้ำกัน"
        if "รายการ" in d:                                  # รูปแบบ ">10 รายการ" (ขาดเยอะ)
            return "ลำดับสินค้าขาดหลายรายการ"
        return f"ขาดลำดับที่ {nums}" if nums else "ลำดับสินค้าขาดหายไป"
    if code == "ITM013":                                   # ลำดับไม่เรียง / ไม่เริ่มที่ 1
        if "ไม่เริ่มที่ 1" in d:
            return "ลำดับสินค้าไม่ได้เริ่มที่ 1"
        return "ลำดับสินค้าไม่เรียงกัน"
    if code == "ITM014":                                   # gap ลำดับใหญ่ผิดปกติ
        return "ลำดับสินค้าเว้นช่วงผิดปกติ"
    if code == "ADDR002":                                  # สะกดที่อยู่ผิด (จังหวัด/ถนน/แขวง/เขต)
        mlbl = re.match(r'\s*(\S+?)\s*อาจสะกดผิด', d)       # ตัดเลข % ทศนิยมยาว ๆ ออก → ภาษาคน
        mw = re.search(r"อาจสะกดผิด:\s*'([^']+)'", d)
        mr = re.search(r"ควรเป็น\s*'([^']+)'", d)
        if mlbl and mw and mr:
            return f"ลงชื่อ{mlbl.group(1)}ผิด บิลลง {mw.group(1)} ที่ถูก {mr.group(1)}"
        return d_nohdr
    if code == "IV005":                                    # บิลไม่มีเลขที่ใบกำกับ
        return "ไม่มีเลขที่ใบกำกับ ต้องเติมเลขที่"
    if code == "ADDR005":                                  # รหัสไปรษณีย์
        return "รหัสไปรษณีย์ไม่ครบ"
    if code == "ADDR001":                                  # ที่อยู่ไม่ครบ/ไม่ตรงทะเบียน
        body = re.sub(r'^ที่อยู่ไม่ตรงทะเบียน[:：]\s*', '', d_nohdr)
        if "ไปรษณีย์" in body and ";" not in body:         # ปัญหาเดียว = รหัสไปรษณีย์ → คำสั้น
            mz = re.search(r'(\d{5})', body)
            return f"รหัสไปรษณีย์ไม่ครบ (ทะเบียน {mz.group(1)})" if mz else "รหัสไปรษณีย์ไม่ครบ"
        return d_nohdr
    if code == "ITM007":
        m = re.search(r"'([^']+)'", d)
        return f'ชื่อสินค้าสั้น: {m.group(1)}' if m else d_nohdr
    return d_nohdr


# ── [v9.2] สรุป "ที่อยู่" แบบสั้น: บอกเฉพาะ field ที่ผิด + จำนวนบิล (ตามที่ลูกค้าเลือก) ──
def _addr_bad_fields(detail: str):
    """ดึง 'ชื่อ field ที่ไม่ตรง' จาก detail ของ ADDR (ตัดค่า บิล/ทะเบียน ออก).

    detail จริง: 'ที่อยู่ไม่ตรงทะเบียน: รหัสไปรษณีย์ไม่ตรง (บิล: .. / ทะเบียน: ..); เขต/อำเภอไม่ตรง (..); ...'
    → คืน ['รหัสไปรษณีย์','เขต-อำเภอ', ...] (แทน '/' ในชื่อ field ด้วย '-' กันชนกับตัวคั่น).
    """
    d = re.sub(r"^.*?ทะเบียน:\s*", "", detail or "")     # ตัดวลีนำ 'ที่อยู่ไม่ตรงทะเบียน:'
    out = []
    for chunk in d.split(";"):
        # รองรับทุกรูป: '<field>ไม่ตรง' / 'ไม่พบ<field> (' / '<field>ต่าง' / 'ทะเบียนมี<field> '
        m = (re.match(r"\s*(.+?)\s*ไม่ตรง", chunk) or
             re.search(r"ไม่พบ(.+?)\s*\(", chunk) or
             re.match(r"\s*(.+?)\s*ต่าง\b", chunk) or
             re.search(r"ทะเบียนมี(.+?)\s", chunk))
        if m:
            lbl = m.group(1).strip().replace("/", "-")
            if lbl and lbl not in out and len(lbl) <= 18:
                out.append(lbl)
    return out


def _entry_prefix(fx) -> str:
    """[C1] ชื่อไฟล์ (prefix) ของบิลที่ผิด — ใช้ key 'prefix' ที่ composer ใส่มา ; ถ้าไม่มี derive จาก 'file'
    (ตัดส่วนหลัง _ / เว้นวรรค / . ตัวแรก เหมือน _file_prefix ของ composer)."""
    p = (fx.get("prefix") or "").strip()
    if p:
        return p
    f = (fx.get("file") or "").strip()
    return re.split(r"[ _.]", f, 1)[0] if f else ""


def addr_summary(entries) -> str:
    """[C1] รวม ADDR ของช่อง 'ที่อยู่' → ระบุ "ไฟล์" + field ที่ผิด + จำนวนบิล (บัญชีเปิดไปแก้ถูกจุด):
       'ไฟล์ {prefix} <field ผิด> ไม่ตรง (N บิล) รีเช็คครับ' ; หลายไฟล์ → 'ไฟล์ A .. (n), ไฟล์ B .. (m)'.
    เดิมคืนแค่ '(N บิล)' ลอย ๆ ไม่มีไฟล์ → เปิดไม่ถูกจุด.
    """
    groups = OrderedDict()
    for fx in (entries or []):
        pre = _entry_prefix(fx)
        g = groups.setdefault(pre, {"fields": [], "bills": set()})
        g["bills"].add((fx.get("file", ""), fx.get("sheet", ""), fx.get("date", "")))
        for lbl in _addr_bad_fields(fx.get("detail", "") or fx.get("type", "")):
            if lbl not in g["fields"]:
                g["fields"].append(lbl)
    parts = []
    for pre, g in groups.items():
        flds = "/".join(g["fields"]) if g["fields"] else "ที่อยู่"
        head = f"ไฟล์ {pre} " if pre else ""
        parts.append(f"{head}{flds} ไม่ตรง ({len(g['bills'])} บิล)")
    return (", ".join(parts) if parts else "ที่อยู่ ไม่ตรง (0 บิล)") + " รีเช็คครับ"


def field_summary(field, entries) -> str:
    """[C1] สรุปช่องแบบสั้น + ระบุไฟล์ (กันดัมพ์ซ้ำทุกบรรทัด แต่บอกไฟล์ให้เปิดถูกจุด):
       • ที่อยู่ → addr_summary (field ที่ผิด + ไฟล์ + จำนวนบิล)
       • อื่น ๆ (เช่น เลขภาษีเป็นของบริษัทอื่น) → 'ไฟล์ {prefix} {detail ยุบซ้ำ} (N บิล)' ต่อไฟล์
    """
    if field == F_ADDR:
        return addr_summary(entries)
    groups = OrderedDict()
    for fx in (entries or []):
        pre = _entry_prefix(fx)
        g = groups.setdefault(pre, {"details": [], "bills": set()})
        g["bills"].add((fx.get("file", ""), fx.get("sheet", ""), fx.get("date", "")))
        d = (fx.get("detail") or fx.get("type") or "").strip()
        if d and d not in g["details"]:
            g["details"].append(d)
    parts = []
    for pre, g in groups.items():
        body = " ; ".join(g["details"]) if g["details"] else "ไม่ตรง"
        head = f"ไฟล์ {pre} " if pre else ""
        parts.append(f"{head}{body} ({len(g['bills'])} บิล)")
    return (", ".join(parts) if parts else "ไม่ตรง (0 บิล)") + " รีเช็คครับ"
