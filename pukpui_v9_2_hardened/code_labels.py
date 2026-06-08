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
    "CMP001": (F_NAME, "ชื่อบริษัทไม่ตรง master", MASTER),
    "CMP002": (F_NAME, "คำนำหน้านิติบุคคลผิด", FIX),
    "CMP003": (F_NAME, "ใช้ชื่อแบรนด์แทนชื่อนิติบุคคล", FIX),
    "CMP004": (F_NAME, "เว้นวรรคชื่อบริษัทไม่ตรง master", REVIEW),
    "CMP005": (F_NAME, "ชื่อบริษัทไม่ครบ (ขาด 'จำกัด')", FIX),
    # ที่อยู่
    "ADDR001": (F_ADDR, "ที่อยู่ไม่ครบ", FIX),
    "ADDR002": (F_ADDR, "ตัวสะกดถนน/แขวงผิด", CHECK),
    "ADDR003": (F_ADDR, "ชั้น/อาคาร/ห้อง ไม่ตรง master", MASTER),
    "ADDR004": (F_ADDR, "รูปแบบที่อยู่กรุงเทพ/ต่างจังหวัดผิด", CHECK),
    "ADDR005": (F_ADDR, "รหัสไปรษณีย์ผิด", CHECK),
    # เลขภาษี
    "TAX001": (F_TAX, "เลขภาษีไม่ครบ 13 หลัก", FIX),
    "TAX002": (F_TAX, "เลขภาษีมีตัวอักษรปน", FIX),
    "TAX003": (F_TAX, "เลขภาษีไม่ตรงกับบริษัท (master)", MASTER),
    "TAX004": (F_TAX, "เลขภาษีน่าจะ OCR ผิด", CHECK),
    "TAX005": (F_TAX, "เลขภาษีไม่พบใน master", MASTER),
    "TAX006": (F_TAX, "เลขภาษี checksum ไม่ผ่าน", FIX),
    "TAX007": (F_TAX, "ประเภทนิติบุคคล (หลักแรก) ผิดปกติ", CHECK),
    # สาขา
    "BR001": (F_BRANCH, "รหัสสาขาผิดรูปแบบ", FIX),
    "BR002": (F_BRANCH, "ไม่ได้ระบุสาขา/สนญ.", FIX),
    "BR003": (F_BRANCH, "สาขาไม่สม่ำเสมอในไฟล์", CHECK),
    # เอกสาร / วันที่
    "DOC001": (F_DATE, "ลงวันที่ผิด", FIX),
    "DOC002": (F_DATE, "ลงวันที่ผิด", FIX),
    "DOC003": (F_DOCNO, "เลขที่เอกสารซ้ำ (ใช้เลขเดียวกันหลายใบ)", FIX),
    "DT001": (F_DATE, "เดือนในบิลไม่ตรงงวดที่ชื่อไฟล์ระบุ", NOTE),
    "DT002": (F_DATE, "วันที่เป็นอนาคต", NOTE),
    "DT003": (F_DATE, "ปี พ.ศ./ค.ศ. ไม่ชัดเจน", NOTE),
    "DT004": (F_DATE, "ลงวันที่ผิด", FIX),
    "DT005": (F_DATE, "บิลไม่มีวันที่", FIX),
    # เลขที่ใบกำกับ
    "IV001": (F_IV, "prefix เลขใบกำกับไม่ตรง", REVIEW),
    "IV002": (F_IV, "เลขใบกำกับผิดรูปแบบ", FIX),
    "IV003": (F_IV, "เลขใบกำกับซ้ำข้ามวัน", FIX),
    "IV004": (F_IV, "เลขใบกำกับไม่ไล่ตามวัน", CHECK),
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
    # ยอดเงิน / VAT
    "VAT001": (F_PREVAT, "ผลรวมรายการ ≠ ยอดก่อน VAT", FIX),
    "VAT002": (F_POSTVAT, "VAT 7% คำนวณไม่ตรง", FIX),
    "VAT003": (F_POSTVAT, "ยอดรวมทั้งสิ้นไม่ตรง", FIX),
    "VAT004": (F_POSTVAT, "ปัดเศษยอดผิดปกติ", CHECK),
    "VAT005": (F_POSTVAT, "ยอดเงินผิดปกติ", FIX),
    "VAT006": (F_POSTVAT, "ราคารวม VAT แล้ว (VAT included)", REVIEW),
    "VAT007": (F_POSTVAT, "ส่วนลดไม่สอดคล้องยอด", FIX),
    "VAT008": (F_POSTVAT, "VAT เป็นศูนย์", REVIEW),
    "VAT009": (F_PREVAT, "ยอดก่อน VAT เป็นศูนย์/ไม่มี", FIX),
    "VAT010": (F_POSTVAT, "VAT ไม่ได้ตรวจจริง", REVIEW),
}

# ── ลำดับ field ในบล็อกบริษัท (ตามฟอร์แมตที่ผู้ใช้ต้องการ) ───────────────────
FIELD_ORDER = [F_NAME, F_ADDR, F_TAX, F_BRANCH, F_DOCNO, F_DATE, F_IV, F_ITEM, F_POSTVAT, F_PREVAT]

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
