# -*- coding: utf-8 -*-
"""ultra_agent.py — "ตัวช่วยตรวจทาน-ยืนยันความจริง" (Ultra Agent) สำหรับ Company Summary.

แนวคิด (advisory ล้วน — ไม่แตะ engine/ผลตรวจ/golden hash):
  ระบบนี้ offline + deterministic → "ความฉลาด" = การ "ตรวจทานซ้ำด้วยหลักฐานอิสระ" แล้ว
  "ประสานสัญญาณจากหลายหน่วย" มาตัดสินว่า finding ที่กฎฟ้อง "จริงไหม" ไม่ใช่ AI สุ่ม/กล่องดำ.

แต่ละ finding ที่กฎฟ้อง Ultra Agent จะ:
  1) รวบหลักฐานอิสระ ("ประสานหน่วยภายใน"):
       • checksum ในบิลเอง 2 ตัว: (ก) subtotal+vat == total  (ข) vat == 7% ของ subtotal
       • re-derive เฉพาะเรื่อง (เลขภาษี mod-11, วันที่ในบิล, ความต่อเนื่องเลขเอกสาร)
       • เทียบบิล "พี่น้อง" ในชุดเดียวกัน (บริษัท×เดือน)
  2) ตรวจซ้ำ ("ไปตรวจงานอีกรอบ") แล้วนับสัญญาณ ยืนยัน(confirm)/ขัดแย้ง(contradict)/เป็นกลาง
  3) ตัดสิน verdict + ความมั่นใจ:
       • ยืนยัน(สูง)      = หลักฐานอิสระหนุน → ผิดจริง ต้องรีเช็ค
       • ควรตรวจซ้ำ(กลาง) = สัญญาณไม่พอ/ขัดแย้งกันเอง → ส่งคนตรวจซ้ำก่อนสรุป
       • น่าจะปกติ(ต่ำ)   = หลักฐานอิสระค้านการฟ้อง → น่าจะ false alarm
  4) สรุป Company Summary เวอร์ชัน "ตรวจทานแล้ว" (company_summary_ultra.txt) + เหตุผลว่าเกิดอะไรขึ้น

ผลผลิต: company_summary_ultra.txt (เวอร์ชันฉลาด อยู่ "ข้าง ๆ" ของเดิม — ไม่ทับของเดิม)
deterministic 100% (ไม่มี network/สุ่ม/เวลา) — รันซ้ำได้ผลเดิม.
"""
import warnings; warnings.filterwarnings("ignore")
import os
from config import audit_today  # [DET-FIX] injectable clock — pin ด้วย PUOPUY_AUDIT_DATE
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_labels import (F_NAME, F_TAX, F_DATE, F_IV, F_ITEM, F_PREVAT, F_POSTVAT,
                         field_of, lane_of, label_of)
import super_ultra_viewer as _suv

# ── ระดับ verdict ─────────────────────────────────────────────────────────────
V_CONFIRM = "ยืนยัน"          # หลักฐานอิสระหนุน → ผิดจริง ต้องรีเช็ค
V_RECHECK = "ควรตรวจซ้ำ"      # สัญญาณไม่พอ/ขัดแย้ง → ส่งคนตรวจซ้ำ
V_LIKELY_OK = "น่าจะปกติ"     # หลักฐานอิสระค้าน → น่าจะ false alarm
_CONF = {V_CONFIRM: "สูง", V_RECHECK: "ปานกลาง", V_LIKELY_OK: "ต่ำ"}
_ICON = {V_CONFIRM: "🔴", V_RECHECK: "🟡", V_LIKELY_OK: "🟢"}


# ── หลักฐานอิสระ #1: checksum ตัวเลขในบิล ────────────────────────────────────
def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def bill_checksums(b: dict) -> dict:
    """checksum อิสระในบิล: (ก) subtotal+vat==total  (ข) vat==7%×subtotal.
    คืน dict: arith_ok / vat_ok (None ถ้าข้อมูลไม่พอ) + ส่วนต่าง เพื่อใช้เป็นหลักฐาน."""
    sub, vat, tot = _num(b.get("subtotal")), _num(b.get("vat")), _num(b.get("total"))
    out = {"arith_ok": None, "vat_ok": None, "arith_diff": None, "vat_diff": None}
    if sub is not None and vat is not None and tot is not None:
        diff = abs((sub + vat) - tot)
        out["arith_diff"] = diff
        out["arith_ok"] = diff <= max(0.05, abs(tot) * 0.001)   # subtotal+vat == total
    if sub is not None and vat is not None and sub != 0:
        vdiff = abs(vat - sub * 0.07)
        out["vat_diff"] = vdiff
        out["vat_ok"] = vdiff <= max(0.10, abs(sub) * 0.005)    # vat = 7% ของ subtotal
    return out


# ── หลักฐานอิสระ #2: re-derive เลขภาษีไทย (mod-11) ───────────────────────────
def thai_tax_valid(tid: str):
    """ตรวจเลขประจำตัวผู้เสียภาษีไทย 13 หลักด้วย mod-11 (อิสระจากกฎ). คืน True/False/None."""
    s = "".join(ch for ch in str(tid or "") if ch.isdigit())
    if len(s) != 13:
        return None  # ไม่ใช่ 13 หลัก — ตรวจ checksum ไม่ได้ (ความยาวผิดเป็นเรื่องของกฎ)
    chk = sum(int(s[i]) * (13 - i) for i in range(12))
    return (11 - (chk % 11)) % 10 == int(s[12])


# ── ตรวจทานทีละ finding (ประสานหลักฐาน → verdict) ─────────────────────────────
# ── ระดับความน่าเชื่อของแต่ละรหัส — ครบทุกรหัส A-Z ในระบบ (59 รหัส) ──────────
# RELIABLE = เชิงโครงสร้าง/เลขคณิต/รูปแบบ/ซ้ำ/ตรรกะ ตรวจซ้ำได้แน่ → ยืนยันถ้าไม่มีหลักฐานค้าน
RELIABLE_CODES = {
    "ADDR001",                                          # ที่อยู่ไม่ครบ (ขาดส่วน)
    "BR001", "BR002",                                   # รหัสสาขาผิดรูปแบบ / ไม่ระบุสาขา
    "CMP002", "CMP005",                                 # คำนำหน้านิติบุคคลผิด / ขาด 'จำกัด'
    "DOC001", "DOC002", "DOC003", "DT004", "DT005", "DT006",   # ลงวันที่ผิด / เลขเอกสารซ้ำ / ไม่มีวันที่ / วันที่ไม่ถูกต้อง
    "ITM001", "ITM002", "ITM016", "ITM017", "ITM018",   # ยอดบรรทัด/ลำดับ/ซ้ำ/ติดลบ/จำนวน0
    "IV002", "IV003", "IV005", "IV006", "IV007",        # เลขใบกำกับผิดรูปแบบ/ซ้ำข้ามวัน/ไม่มีเลขที่/อย่างย่อ/[D1]เลขขยะ(absolute)
    "TAX001", "TAX002", "TAX006",                       # เลขภาษี ความยาว/อักษรปน/checksum
    # [ADR-190] สระอำแยกส่วน = ตรวจได้แน่นอนจาก byte ของเซลล์เอง (ไม่ต้องพึ่ง master/ฮิวริสติก)
    "CMP007", "ADDR011",
    "VAT001", "VAT002", "VAT003", "VAT005", "VAT007", "VAT009", "VAT012",  # ยอด/VAT เชิงเลขคณิต ; VAT012 = บาทอักษร↔ตัวเลข [ADR-122]
}
# FUZZY = ฮิวริสติก/คล้ายคลึง/อิงหน่วย-สเปก/ทบทวน → ให้คนยืนยันก่อน (ควรตรวจซ้ำ)
FUZZY_CODES = {
    "ADDR002", "ADDR004", "ADDR005", "ADDR006", "ADDR007", "ADDR010",   # สะกด/รูปแบบที่อยู่/ไปรษณีย์↔จังหวัด[B2]/↔อำเภอ[ADR-122]/จังหวัดปลอม[ADR-122]
    "BR003",                                            # สาขาไม่สม่ำเสมอในไฟล์
    "TAX008",                                           # [B1] เลขภาษีเดียวชื่อต่าง (cross-bill — ตรวจอิสระต่อบิลไม่ได้)
    "TAX009",                                           # [BS-3] ชื่อเดียวเลขภาษีต่าง (cross-bill — ตรวจอิสระต่อบิลไม่ได้)
    "CMP003",                                           # ใช้แบรนด์แทนชื่อนิติบุคคล
    "ITM003", "ITM004", "ITM005", "ITM006", "ITM007", "ITM008", "ITM009",
    "ITM010", "ITM011", "ITM012", "ITM013", "ITM014", "ITM015", "ITM019", "ITM020",  # ชื่อ/หน่วย/typo/ลำดับ(soft) — ITM019 = หน่วยสะกดผิด, ITM020 = ทั้งบิลไม่มีหน่วย (ตรวจเพิ่ม ให้คนรีเช็ค)
    "IV001", "IV004",                                   # prefix / ไล่เลขตามวัน
    "TAX004", "TAX007",                                 # OCR / ประเภทนิติบุคคล
    "VAT004", "VAT006", "VAT008", "VAT010", "VAT011",   # ปัดเศษ/รวมVAT/VATศูนย์/ไม่ได้ตรวจ/[BS-2]ใบมียอดแต่VAT=0(รีเช็ค)
}
# MASTER = เทียบ master เท่านั้น ตรวจอิสระ offline ไม่ได้ → ควรตรวจซ้ำ (+หมายเหตุ)
MASTER_CODES = {"ADDR003", "CMP001", "CMP004", "CMP006", "TAX003", "TAX005", "BR004"}  # +BR004 [B3] เทียบสาขากับ master
# NOTE = ข้อสังเกต (ไม่ใช่ finding ที่ต้องตัดสิน — ลงบรรทัดหมายเหตุของสรุปปกติ ไม่เข้า Ultra)
NOTE_CODES = {"DT001", "DT002", "DT003"}

# รหัสยอด/VAT ที่ใช้ checksum ยอดรวม/ผลรวมรายการเป็นหลักฐานอิสระ
_AMOUNT_CODES = {"ITM001", "VAT001", "VAT002", "VAT003", "VAT005", "VAT007", "VAT009", "AMT001"}


def _norm_name_key(s):
    import re as _re
    return _re.sub(r"\s+", "", str(s or ""))


def verify_finding(b: dict, code: str, detail: str, cs: dict, siblings: list) -> dict:
    """ตรวจซ้ำ finding หนึ่ง (ครบทุกรหัส): รวบหลักฐานอิสระ → ตั้ง corroborated/contradicted/
    line_only → ตัดสิน verdict (ยืนยัน/ควรตรวจซ้ำ/น่าจะปกติ). คืน dict รายละเอียด."""
    field = field_of(code)
    items = b.get("items") or []
    ev = []
    corroborated = False   # หลักฐานอิสระ "หนุน" การฟ้อง
    contradicted = False   # หลักฐานอิสระ "ค้าน" การฟ้อง
    line_only = False      # ปัญหาระดับบรรทัด แต่ยอดรวมถูก → ตรวจซ้ำเฉพาะบรรทัด

    # ── เลขภาษี ──
    if field == F_TAX:
        v = thai_tax_valid(b.get("tax_id"))
        raw = str(b.get("tax_id") or "")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if code == "TAX001":                       # ไม่ครบ 13 หลัก
            corroborated = len(digits) != 13
            contradicted = len(digits) == 13
            ev.append(f"นับหลักเลขภาษี = {len(digits)} (ต้อง 13)")
        elif code == "TAX002":                     # [A4] ไม่พบกลุ่มเลขภาษี 13 หลักที่ถูกต้อง (ตรงพฤติกรรม r_tax002)
            import re as _re
            _txt = str(b.get("tax_id_raw") or b.get("tax_id") or "")
            has13 = bool(_re.search(r'(?<!\d)(?:\d[\-\.\s]*){12}\d(?!\d)', _txt))
            corroborated = not has13
            contradicted = has13
            ev.append("พบกลุ่มเลข 13 หลักครบ" if has13 else "ไม่พบกลุ่มเลขภาษี 13 หลักที่ถูกต้อง")
        elif code == "TAX006":                     # checksum ไม่ผ่าน
            corroborated = v is False
            contradicted = v is True
            ev.append(f"คำนวณ mod-11 ซ้ำ: {'ผ่าน' if v else ('ไม่ผ่าน' if v is False else 'ไม่ครบ 13 หลัก')}")
        elif code == "TAX008":                     # [B1] เลขภาษีเดียวชื่อต่าง (cross-bill)
            ev.append("เลขภาษีเดียวถูกใช้กับชื่อบริษัทต่างกันข้ามบิล — ต้องดูภาพรวมข้ามบิล ตรวจอิสระต่อบิลไม่ได้")
        elif code in MASTER_CODES:                 # TAX003/TAX005 — อิง master
            ev.append("เลขภาษีถูกตามสูตร (mod-11 ผ่าน) แต่ติด master — ตรวจอิสระ offline ไม่ได้"
                      if v is True else "ต้องเทียบ master — ตรวจอิสระ offline ไม่ได้")
        else:                                      # TAX004/TAX007 — ฮิวริสติก
            ev.append("กฎฮิวริสติกเลขภาษี (OCR/ประเภทนิติบุคคล) — ให้คนยืนยัน")

    # ── ยอด/VAT (ใช้ checksum ยอดรวม/ผลรวมรายการเป็นหลักฐานอิสระ) ──
    elif code in _AMOUNT_CODES:
        sub = _num(b.get("subtotal"))
        item_sum = sum((_num(it.get("amount")) or 0) for it in items)
        if code == "VAT009":                       # ยอดก่อน VAT เป็นศูนย์/ไม่มี
            corroborated = (sub is None or sub == 0)
            contradicted = (sub is not None and sub != 0)
            ev.append("ยอดก่อน VAT เป็นศูนย์/ไม่มีจริง" if corroborated else f"ยอดก่อน VAT = {sub:,.2f} (ไม่ศูนย์)")
        elif code == "VAT002":                     # VAT 7% ไม่ตรง
            if cs.get("vat_ok") is False:
                corroborated = True; ev.append(f"VAT ≠ 7% ของ subtotal (ต่าง {cs.get('vat_diff'):.2f})")
            elif cs.get("vat_ok") is True:
                contradicted = True; ev.append("VAT = 7% ของ subtotal (checksum ผ่าน) → น่าจะ false alarm")
        elif code in ("VAT003", "VAT005", "VAT007"):   # ยอดรวม/ยอดเงิน/ส่วนลด — ใช้ arith
            if cs.get("arith_ok") is False:
                corroborated = True; ev.append(f"subtotal+vat ≠ total (ต่าง {cs.get('arith_diff'):.2f}) → ยอดผิดจริง")
            elif cs.get("arith_ok") is True:
                contradicted = True; ev.append("ยอดรวมลงตัว (subtotal+vat=total) → น่าจะ false alarm")
        elif code == "VAT001":                     # ผลรวมรายการ ≠ ยอดก่อน VAT
            if sub is not None and items:
                if abs(item_sum - sub) > max(0.05, abs(sub) * 0.001):
                    corroborated = True; ev.append(f"ผลรวมรายการ {item_sum:,.2f} ≠ ยอดก่อน VAT {sub:,.2f}")
                else:
                    contradicted = True; ev.append("ผลรวมรายการ = ยอดก่อน VAT (ตรวจซ้ำแล้วตรง)")
        elif code in ("ITM001", "AMT001"):         # จำนวน×ราคา ≠ ยอดบรรทัด / ยอดผิด
            bad_line = any(
                None not in (_num(it.get("qty")), _num(it.get("price")), _num(it.get("amount")))
                and abs((_num(it.get("qty")) or 0) * (_num(it.get("price")) or 0) - (_num(it.get("amount")) or 0))
                > max(0.05, abs(_num(it.get("amount")) or 0) * 0.001)
                for it in items)
            if bad_line:
                corroborated = True; ev.append("คำนวณซ้ำ: มีบรรทัด จำนวน×ราคา ≠ ยอดบรรทัดจริง")
            elif cs.get("arith_ok") is False:
                corroborated = True; ev.append("ยอดรวมบิลไม่ลงตัวด้วย (subtotal+vat ≠ total)")
            elif cs.get("arith_ok") is True:
                line_only = True; ev.append("ยอดรวมทั้งบิลลงตัว → ตรวจซ้ำเฉพาะบรรทัดที่กฎชี้")

    # ── วันที่ ──
    elif field == F_DATE:
        dstr = (b.get("iv_date_str") or "").strip()
        dt = b.get("iv_date")
        try:
            if dt and dstr and f"{dt.day:02d}" not in dstr and str(dt.day) not in dstr:
                corroborated = True; ev.append("วันที่ในระบบไม่ตรงกับข้อความวันที่ในบิล")
        except Exception:
            pass
        sib_date_issues = sum(1 for s in siblings
                              if any(field_of(i.get("code", "")) == F_DATE and
                                     lane_of(i.get("code", "")) in ("fix", "check")
                                     for i in s.get("issues", [])))
        if siblings and sib_date_issues <= max(1, len(siblings) // 5):
            corroborated = True
            ev.append(f"บิลพี่น้อง {len(siblings)} ใบ รูปแบบวันที่ปกติ (ใบนี้เป็นข้อยกเว้น)")

    # ── เลขที่/เลขใบกำกับ ซ้ำ (DOC003/IV003) — เทียบบิลพี่น้องในชุด ──
    elif code in ("DOC003", "IV003"):
        iv = (b.get("iv_number") or "").strip()
        same = sum(1 for s in siblings if (s.get("iv_number") or "").strip() == iv and iv)
        if same >= 1:
            corroborated = True; ev.append(f"พบเลขเดียวกัน {same + 1} ใบในชุด (ซ้ำจริง)")
        else:
            ev.append("ตรวจรูปแบบ/ความซ้ำตามกฎ")

    # ── รายการสินค้า (เชิงตรรกะ ตรวจซ้ำได้แน่) ──
    elif code == "ITM016":                         # รายการซ้ำ
        keys = [_norm_name_key(it.get("name")) for it in items if _norm_name_key(it.get("name"))]
        if len(keys) != len(set(keys)):
            corroborated = True; ev.append("คำนวณซ้ำ: มีชื่อรายการซ้ำในบิลจริง")
        else:
            ev.append("ตรวจรายการซ้ำตามกฎ")
    elif code == "ITM017":                         # จำนวน/ราคาติดลบ
        if any((_num(it.get("qty")) or 0) < 0 or (_num(it.get("price")) or 0) < 0 for it in items):
            corroborated = True; ev.append("คำนวณซ้ำ: พบจำนวน/ราคาติดลบจริง")
    elif code == "ITM018":                         # จำนวน=0 แต่มียอดเงิน
        if any(_num(it.get("qty")) == 0 and (_num(it.get("amount")) or 0) != 0 for it in items):
            corroborated = True; ev.append("คำนวณซ้ำ: พบจำนวน=0 แต่มียอดเงินจริง")
    elif code == "ITM002":                         # ลำดับรายการหาย
        seqs = [int(it.get("seq")) for it in items if str(it.get("seq")).isdigit()]
        if seqs and sorted(seqs) != list(range(min(seqs), max(seqs) + 1)):
            corroborated = True; ev.append("คำนวณซ้ำ: ลำดับรายการไม่ต่อเนื่องจริง")

    # ── ชื่อบริษัท / สาขา (เชิงโครงสร้าง ตรวจซ้ำได้) ──
    elif code == "CMP005":                         # ขาด 'จำกัด'
        nm = b.get("company") or ""
        if not any(k in nm for k in ("จำกัด", "มหาชน", "ห้างหุ้นส่วน", "หจก")):
            corroborated = True; ev.append("ชื่อไม่มีคำว่า 'จำกัด/มหาชน/ห้างหุ้นส่วน' จริง")
    elif code == "BR002":                          # ไม่ระบุสาขา
        if not (b.get("branch") or "").strip():
            corroborated = True; ev.append("ช่องสาขา/สนญ. ว่างจริง")

    # ── master-only (ตรวจอิสระ offline ไม่ได้) ──
    elif code in MASTER_CODES:
        ev.append("ต้องเทียบ master — ตรวจอิสระ offline ไม่ได้ (ให้คนยืนยัน)")

    if not ev:
        if code in FUZZY_CODES:
            ev.append("กฎฮิวริสติก/คล้ายคลึง/อิงสเปก → ให้คนยืนยันก่อนสรุป")
        elif code in RELIABLE_CODES:
            ev.append("ใช้สัญญาณเชิงโครงสร้างจากกฎ (เชื่อถือได้)")
        else:
            ev.append("ตรวจตามกฎ (ไม่มีหลักฐานอิสระเพิ่ม)")

    # ── ตัดสิน ──
    if contradicted:
        verdict = V_LIKELY_OK
    elif line_only:
        verdict = V_RECHECK
    elif code in FUZZY_CODES or code in MASTER_CODES:
        verdict = V_RECHECK
    elif corroborated or code in RELIABLE_CODES:
        verdict = V_CONFIRM
    else:
        verdict = V_RECHECK
    return {"field": field, "code": code, "label": label_of(code),
            "verdict": verdict, "confidence": _CONF[verdict], "reasoning": " ; ".join(ev)}


# ── ตรวจทานทั้งบริษัท (1 บล็อก summary) ───────────────────────────────────────
def verify_company(row: dict, gbills: list) -> dict:
    """ตรวจทานทั้งบริษัท×เดือน: checksum รวม + ตรวจทานทุก finding + สรุป verdict ภาพรวม."""
    n = len(gbills)
    cs_list = [bill_checksums(b) for b in gbills]
    arith_pass = sum(1 for c in cs_list if c["arith_ok"] is True)
    arith_chk = sum(1 for c in cs_list if c["arith_ok"] is not None)
    vat_pass = sum(1 for c in cs_list if c["vat_ok"] is True)
    vat_chk = sum(1 for c in cs_list if c["vat_ok"] is not None)

    # ตรวจทานทุก finding (lane fix/check) ของทุกบิลในกลุ่ม
    checks = []
    for b in gbills:
        cs = bill_checksums(b)
        sibs = [x for x in gbills if x is not b]
        for i in b.get("issues", []):
            code = i.get("code", "")
            if lane_of(code) in ("fix", "check"):
                r = verify_finding(b, code, i.get("detail", ""), cs, sibs)
                r["bill"] = b
                r["detail"] = i.get("detail", "")
                checks.append(r)

    n_confirm = sum(1 for c in checks if c["verdict"] == V_CONFIRM)
    n_recheck = sum(1 for c in checks if c["verdict"] == V_RECHECK)
    n_okish = sum(1 for c in checks if c["verdict"] == V_LIKELY_OK)

    # verdict ภาพรวม
    if n_confirm > 0:
        overall, rec = V_CONFIRM, "มีจุดผิดจริง — ต้องรีเช็ค/แก้ก่อนส่ง"
    elif n_recheck > 0:
        overall, rec = V_RECHECK, "ส่งให้คนตรวจซ้ำจุดที่ระบุก่อนสรุป"
    elif n_okish > 0:
        overall, rec = V_LIKELY_OK, "กฎฟ้องแต่หลักฐานอิสระค้าน — น่าจะส่งได้ (ยืนยันอีกชั้นได้)"
    else:
        overall, rec = "ผ่าน", "ทุกช่องผ่าน + ยอด checksum ครบ — พร้อมส่ง"

    return {"row": row, "n": n,
            "arith_pass": arith_pass, "arith_chk": arith_chk,
            "vat_pass": vat_pass, "vat_chk": vat_chk,
            "checks": checks, "n_confirm": n_confirm, "n_recheck": n_recheck,
            "n_okish": n_okish, "overall": overall, "recommend": rec}


def _ctx(b):
    """อ้างอิงบิล: 'ไฟล์ JRN เลขที่เอกสาร X วันที่ d.m.y'."""
    import re as _re
    pre = ""
    m = _re.match(r"\s*([A-Za-z]+)", os.path.basename(b.get("file", "") or ""))
    if m:
        pre = m.group(1).upper()
    iv = (b.get("iv_number_raw") or b.get("iv_number") or "").strip()  # [DISPLAY-FAITHFUL] เลขดิบตามใบ (มีขีด) ไม่ใช่ normalized
    dt = b.get("iv_date")
    # [A2-FIX] dt อาจเป็น string/ค่าแปลกที่ไม่มี .day → กัน AttributeError ทำสรุปล้ม
    d = f"{dt.day:02d}.{dt.month:02d}.{dt.year}" if hasattr(dt, "day") else ""
    parts = [f"ไฟล์ {pre}"] if pre else []
    if iv:
        parts.append(f"เลขที่เอกสาร {iv}")
    if d:
        parts.append(f"วันที่ {d}")
    return " ".join(parts) or "บิลนี้"


def render_ultra_block(idx: int, vc: dict) -> str:
    r = vc["row"]
    _mp = r["month"].split("/")
    hdr_month = f"{_mp[1]}.{int(_mp[0]):02d}" if len(_mp) == 2 and _mp[0].isdigit() else r["month"]
    # [A2-FIX] prevat อาจไม่ใช่ตัวเลข (เช่น '-'/'N/A') → กัน ValueError ทำสรุปล้ม
    try:
        amt = float(r.get("prevat") or 0)
    except (TypeError, ValueError):
        amt = 0.0
    amt_s = f"{amt:,.0f}" if amt.is_integer() else f"{amt:,.2f}"

    ov = vc["overall"]
    ov_icon = _ICON.get(ov, "✅")
    out = [f"{idx}.{r['short']} {hdr_month}  ·  {ov_icon} ภาพรวม: {ov}"]
    out.append(f"ยอด(ก่อน VAT) : {amt_s} บาท  ·  {vc['n']} บิล")
    # หลักฐานอิสระระดับชุด
    a_mark = "✅" if vc["arith_pass"] == vc["arith_chk"] and vc["arith_chk"] else "⚠️"
    v_mark = "✅" if vc["vat_pass"] == vc["vat_chk"] and vc["vat_chk"] else "⚠️"
    out.append(f"หลักฐานอิสระ (checksum บิล): {a_mark} ยอดลงตัว {vc['arith_pass']}/{vc['arith_chk']}"
               f"  ·  {v_mark} VAT 7% ถูก {vc['vat_pass']}/{vc['vat_chk']}")

    if vc["checks"]:
        out.append("🔎 จุดที่กฎฟ้อง → ผลตรวจทานซ้ำของ Ultra:")
        for c in vc["checks"]:
            ic = _ICON[c["verdict"]]
            out.append(f"  {ic} [{c['field']}] {_ctx(c['bill'])}")
            out.append(f"      กฎ: {c['code']} {c['label']}")
            out.append(f"      ตรวจซ้ำ: {c['reasoning']}")
            out.append(f"      → {c['verdict']} (มั่นใจ{c['confidence']})")
    else:
        out.append("🔎 ไม่มีจุดที่กฎฟ้อง — ตรวจทานแล้วสะอาด")

    out.append(f"📋 สรุป: ยืนยันผิด {vc['n_confirm']} · ควรตรวจซ้ำ {vc['n_recheck']} · "
               f"น่าจะปกติ {vc['n_okish']}  →  {vc['recommend']}")
    return "\n".join(out)


def build_ultra(bills, master_present=True, masters=None):
    """คืน list ของผลตรวจทานต่อบริษัท×เดือน (เรียงเหมือน super_ultra_viewer)."""
    rows = _suv.build(bills, master_present=master_present, masters=masters)
    # จับ bills กลับเข้ากลุ่มตาม key เดียวกับ build (เลขภาษี/ชื่อ-normalize, เดือน)
    from collections import defaultdict
    groups = defaultdict(list)
    for b in bills:
        ml, _ = _suv._month_label(b.get("iv_date"))
        tid = (b.get("tax_id") or "").strip()
        comp0 = b.get("company") or b.get("company_raw") or "ไม่ทราบชื่อ"
        groups[(tid or _suv._norm_company(comp0), ml)].append(b)
    # map row → gbills (จับด้วยเดือน + ชื่อที่โชว์ = most-common ของกลุ่ม)
    from collections import Counter
    key_by_disp = {}
    for k, gb in groups.items():
        disp = Counter((b.get("company") or b.get("company_raw") or "ไม่ทราบชื่อ") for b in gb).most_common(1)[0][0]
        key_by_disp[(disp, k[1])] = gb
    out = []
    for r in rows:
        gb = key_by_disp.get((r["company"], r["month"]), [])
        out.append(verify_company(r, gb))
    return out


def emit_ultra_summary(bills, outdir, master_present=True, masters=None):
    """เขียน company_summary_ultra.txt — เวอร์ชัน 'ตรวจทานแล้ว' (advisory, ข้างของเดิม).
    คืน path. ห่อกันล้มงานหลัก (advisory)."""
    from datetime import datetime
    vcs = build_ultra(bills, master_present=master_present, masters=masters)
    n_conf = sum(v["n_confirm"] for v in vcs)
    n_rech = sum(v["n_recheck"] for v in vcs)
    n_okish = sum(v["n_okish"] for v in vcs)
    n_clean = sum(1 for v in vcs if v["overall"] == "ผ่าน")
    # [ADR-181/REPORT-UNIT] เดิมหัวรีพอร์ตวาง 4 ตัวเลขต่อจาก "รวม N บริษัท/เดือน" ด้วย | เหมือนกันหมด
    #   แต่ n_clean = "จำนวนกลุ่ม" ส่วน n_conf/n_rech/n_okish = "จำนวนจุดที่ฟ้อง" → 44+9+457 = 510 ≫ 99
    #   ผู้อ่าน (บัญชี) เข้าใจว่าเป็นจำนวนบริษัททั้งหมด. แยกหน่วยให้ชัด + เพิ่มยอดกลุ่มที่ยังไม่ผ่าน.
    g_conf = sum(1 for v in vcs if v["n_confirm"] > 0)
    g_rech = sum(1 for v in vcs if v["n_confirm"] == 0 and v["n_recheck"] > 0)

    SEP = "─" * 31
    L = ["=" * 64,
         "Company Summary (ตรวจทานแล้วโดย Ultra Agent) — ยืนยันความจริงด้วยหลักฐานอิสระ",
         # [DET-FIX 2026-06-10] timestamp เดิมใช้ datetime.now() → รายงาน ultra ไม่นิ่งข้ามนาที
         #   (เทส 5 รอบ: เนื้อหา 878/879 บรรทัดตรงเป๊ะ ต่างแค่บรรทัดนี้). ใช้ injectable clock
         #   audit_today() (pin ได้ด้วย PUOPUY_AUDIT_DATE) แบบเดียวกับ audit core → deterministic.
         f"สร้างเมื่อ: {audit_today().strftime('%d/%m/%Y')}",
         f"นับเป็นบริษัท/เดือน (รวม {len(vcs)}) : พร้อมส่ง {n_clean}  |  มีจุดยืนยันผิด {g_conf}  |  "
         f"มีจุดควรตรวจซ้ำ {g_rech}",
         f"นับเป็นจุดที่ฟ้อง          : ยืนยันผิด {n_conf}  |  ควรตรวจซ้ำ {n_rech}  |  "
         f"น่าจะปกติ {n_okish}",
         "นิยาม: 🔴 ยืนยัน=ผิดจริง(หลักฐานหนุน) · 🟡 ควรตรวจซ้ำ=สัญญาณไม่พอ · 🟢 น่าจะปกติ=หลักฐานค้านการฟ้อง",
         "วิธีทำงาน: ตรวจ checksum บิล + คำนวณซ้ำ(เลขภาษี/วันที่) + เทียบบิลพี่น้อง → ตัดสินทีละจุด",
         "=" * 64]
    for i, vc in enumerate(vcs, 1):
        # [A2-FIX] บล็อกหนึ่งเรนเดอร์ไม่ได้ ต้องไม่ทำสรุปทั้งไฟล์หาย → degrade เป็นบรรทัดหมายเหตุ
        try:
            block = render_ultra_block(i, vc)
        except Exception as _e:
            block = f"(ข้ามบล็อกที่ {i} — เรนเดอร์ไม่ได้: {type(_e).__name__})"
        L += ["", SEP, block, SEP]

    path = os.path.join(outdir, "company_summary_ultra.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return path


def main():
    import glob
    import io
    import contextlib
    import importlib
    data = sys.argv[1] if len(sys.argv) > 1 else "."
    outdir = sys.argv[2] if len(sys.argv) > 2 else "."
    app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
    from golden_snapshot import MASTER
    files = sorted(glob.glob(os.path.join(data, "*.xls")) + glob.glob(os.path.join(data, "*.xlsx")))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        app.reset_run_state()
        bills, _ = app.parse_all_files(files)
        for b in bills:
            app.compute_bill_confidence(b)
        app.run_audit_core(bills, MASTER, isolate=True)
    p = emit_ultra_summary(bills, outdir, master_present=True)
    print(f"🤖 Ultra Agent → {os.path.abspath(p)}")


if __name__ == "__main__":
    main()
