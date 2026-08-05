# -*- coding: utf-8 -*-
"""report_precision.py — Precision Council (ด่านสุดท้ายของ "รีพอร์ตพร้อมส่งลูกค้า")

ทำไมมี: รีพอร์ตสรุปต่อบริษัท (super_ultra_viewer) คือฉบับที่ "ส่งตรงลูกค้า" — ผิดไม่ได้.
  ของเดิมมี verification 34 lenses + ConfidenceAgent + ultra_agent อยู่แล้ว แต่ยังไม่มี
  "สภาตรวจซ้ำเฉพาะรีพอร์ตลูกค้า" ที่รวมทุกเสียงต่อ "จุดที่จะรายงาน" แล้วตัดสินว่า
  **ชัดพอจะใส่รีพอร์ตหลักไหม** (โดยเฉพาะ fuzzy typo ที่ต้อง "ผิดแบบชัด").

โมเดล (ตามที่ผู้ใช้เลือก — 2 ชั้น): สภา 10 ผู้ตรวจ deterministic ลงคะแนนต่อจุด
  → tier 'clear' (เข้ารีพอร์ตหลัก, พร้อมส่ง) หรือ 'soft' (ยกไปบรรทัด "ตรวจตาเพิ่ม" ท้ายบล็อก —
  ไม่ทิ้ง ไม่ซ่อน แต่บอกว่า "ยังก้ำกึ่ง ขอตาคนยืนยัน").

⚠️ ADVISORY/READ-ONLY: ไม่แตะ b['issues']/ผลตรวจหลัก → audit golden (35b2f7c8) ไม่ขยับ.
   ไม่มี ML/training — เป็น rule-based โปร่งใส ("เทรน" = คาลิเบรต threshold ด้วยเทสเคสจริง).
   reuse ตรรกะ core (_taxid_checksum_ok, ฯลฯ) → ไม่ดริฟต์จากเครื่องตรวจหลัก.
"""
from __future__ import annotations

import re

try:                                            # reuse core (ไม่เขียนใหม่ → ไม่ดริฟต์)
    from puopuy_core import _taxid_checksum_ok, clean_tax_id
except Exception:                               # standalone-safe (เทส/CI ที่ไม่โหลด engine)
    def _taxid_checksum_ok(digits):  # type: ignore
        return False
    def clean_tax_id(s):             # type: ignore
        return re.sub(r"\D", "", str(s or ""))

CLEAR, SOFT = "clear", "soft"
CONFIRM, RECHECK, ABSTAIN = "CONFIRM", "RECHECK", "ABSTAIN"

# [REP-M3 2026-06-20] อักขระควบคุมที่ openpyxl ปฏิเสธ — sanitize ก่อนเขียนเซลล์ของ company_summary.xlsx
#   (วาง helper ที่นี่ ไม่ใช่ super_ultra_viewer เพื่อคงไฟล์นั้นไว้ ≤600 LOC ตาม invariant F4)
_XLS_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
def _xls_safe(v):
    """ตัดอักขระควบคุมก่อนเขียนเซลล์ — กัน IllegalCharacterError ทำ advisory xlsx หลุดทั้งไฟล์.
    [ADR-176] + กันสตริงขึ้นต้น '=' กลายเป็นสูตร (formula injection) — corpus ปัจจุบัน 0 เคส = zero-impact."""
    if isinstance(v, str):
        v = _XLS_ILLEGAL.sub("", v)
        return "'" + v if v.startswith('=') else v
    return v

# รหัสที่ "โครงสร้างชัด ตรวจซ้ำได้แน่" → ค่าเริ่มต้นเอนไป clear เมื่อไม่มีผู้ตรวจค้าน
#   ADDR002 = สะกดที่อยู่ผิด (เทียบทะเบียน) → ที่อยู่ต้องตรงทะเบียน = ต้องแก้จริง
#   DOC001 = ชื่อชีต(=วันที่) ไม่ตรงวันที่ในบิล → 'ชื่อชีตกับวันที่ต้องตรงกัน' = สัญญาณเชื่อถือได้ → รีเช็คชัด
#   ── ลำดับความเชื่อถือของความสอดคล้องวันที่ (ตามที่ผู้ใช้กำหนด) ──
#     ชื่อชีต↔วันที่ (DOC001) = เชื่อได้/ต้องตรง → clear(รีเช็ค)
#     เลขที่เอกสาร↔วันที่ (DT004) = แล้วแต่บริษัท ไม่ชัวร์ → soft(ตรวจตาเพิ่ม) [ไม่อยู่ใน set นี้]
#     ชื่อไฟล์↔งวด (DT001) = อ้างอิงคร่าว → NOTE(หมายเหตุ)
_STRUCTURAL = {"ITM002", "ITM013", "ITM014", "CMP005", "IV002", "IV004", "TAX006", "ADDR002",
               "DT005", "IV005", "DOC001", "DT006", "IV006"}
# field ที่พึ่ง master (ไม่มี master = ยืนยันไม่ได้ → soft)
_MASTER_DEPENDENT_CODES = {"CMP001", "CMP004", "TAX003", "TAX005", "ADDR001", "ADDR003"}


def _point_key(e):
    return (e.get("file"), e.get("date"), e.get("seq"))


# ──────────────────────────────────────────────────────────────────────────
# 10 ผู้ตรวจ — แต่ละตัวคืน (verdict, reason). ABSTAIN = "ไม่เกี่ยวกับจุดนี้"
# ──────────────────────────────────────────────────────────────────────────
def a_typo_severity(e, bill, ctx):
    """1. fuzzy typo ต้อง 'ผิดชัด' — ITM010 (มีคำถูกเทียบ deterministic) = ชัด → CONFIRM.

    [ADR-098] ITM011 (fuzzy พจนานุกรม) → RECHECK เสมอ (เลิก auto-CONFIRM 'fuzzy มั่นใจสูง').
      เหตุผล: fuzzy ไม่แน่นอนกับศัพท์ช่าง/เทคนิค และการ "แบ่งคำ" พลาดทำให้เกิด false positive
      เช่น 'ข้อต่อ...ชุบสังกะสี' → segmenter ตัดเป็น 'ชุ|บสังกะสี' → ฟ้อง 'บสังกะสี' ใกล้ 'สังกะสี'
      ทั้งที่คำจริง 'ชุบสังกะสี' สะกดถูก. ⇒ ยกไป 'ตรวจตาเพิ่ม' เมื่อยืนเดี่ยว ; ถ้า co-located
      กับ ITM010 หรือมี ≥2 รหัสหนุน (consensus) สภายก clear เอง (typo จริงยังโชว์ผ่าน ITM010).
      ผล: ช่อง 'รายการสินค้า' หลักจะ 'รีเช็ค' เฉพาะคำผิดที่ยืนยันชัด (ITM010) เท่านั้น —
      ตรงกับ vendor_report ที่กรอง fuzzy เป็น noise อยู่แล้ว (รีพอร์ตสองฉบับสอดคล้องกัน)."""
    code = e.get("code", "")
    if code == "ITM010":
        return CONFIRM, "typo ชัด (ITM010 มีคำถูกเทียบ)"
    if code == "ITM011":
        return RECHECK, "fuzzy พจนานุกรม — ยกไปตรวจตาเพิ่ม (กัน FP ศัพท์ช่าง/แบ่งคำพลาด)"
    return ABSTAIN, ""


def a_unit_sanity(e, bill, ctx):
    """2. หน่วยผิดชัด (เช่น เหล็กเพลท/แผ่น ใช้หน่วย 'เส้น') — ITM015 ผ่าน guard เข้มแล้ว.
    [C2] ITM019 หน่วยสะกดผิด: ถ้ามี mapping ผิด→ถูกชัด ('หน่วย "X" ควรเป็น "Y"') = typo จริง → CONFIRM
    (ขึ้นช่อง 'รายการสินค้า' เหมือน ITM010/011) ; ถ้าเป็น 'หน่วยขาด/ดึงไม่ได้' = ก้ำกึ่ง → ABSTAIN (คง soft)."""
    if e.get("code") == "ITM015":
        return CONFIRM, "หน่วยไม่เข้ากับชนิดสินค้า (ITM015 guard เข้ม)"
    if e.get("code") == "ITM019":
        d = e.get("detail") or ""
        if re.search(r'หน่วย\s*"[^"]+"\s*ควรเป็น\s*"[^"]+"', d):
            return CONFIRM, "หน่วยสะกดผิด (มีคำที่ถูกชัด) — เทียบเท่า typo รายการสินค้า"
        return ABSTAIN, ""        # หน่วยขาด/ดึงไม่ได้ → ก้ำกึ่ง (soft)
    return ABSTAIN, ""


def a_taxid_checksum(e, bill, ctx):
    """3. เลขภาษีผิด — ตรวจซ้ำด้วย checksum/ความยาว 13 หลัก จากบิลจริง."""
    if e.get("field") != "เลขที่ผู้เสียภาษี" and not (e.get("code", "").startswith("TAX")):
        return ABSTAIN, ""
    tid = clean_tax_id(bill.get("tax_id", "") if bill else "")
    if tid and (len(tid) != 13 or not _taxid_checksum_ok(tid)):
        return CONFIRM, "เลขภาษี checksum/ความยาวไม่ผ่าน (ยืนยันซ้ำ)"
    # v9.2: TAX003/TAX005 = "ผลเทียบ master โดยตรง" (master_echo ยืนยันแล้ว) → ไม่ recheck ซ้ำให้ตกเป็น soft
    if e.get("code") in ("TAX003", "TAX005"):
        return ABSTAIN, ""
    return RECHECK, "เลขภาษีต้องเทียบ master เพิ่ม"


def a_name_spacing(e, bill, ctx):
    """4. ชื่อบริษัท — ขาด 'จำกัด' (CMP005) = โครงสร้างชัด ; เว้นวรรค/ชื่อต่าง master = ก้ำกึ่ง."""
    code = e.get("code", "")
    if code == "CMP005":
        return CONFIRM, "ชื่อนิติบุคคลไม่ครบ 'จำกัด' (โครงสร้างชัด)"
    if code in ("CMP004", "CMP001"):
        return RECHECK, "ชื่อ/เว้นวรรคต่าง master — ขอตาคนยืนยัน"
    return ABSTAIN, ""


def a_seq_gap(e, bill, ctx):
    """5. ลำดับรายการหาย/ซ้ำ — ITM002/013/014 ตรวจจากเลขลำดับ (ชัด)."""
    if e.get("code") in ("ITM002", "ITM013", "ITM014"):
        return CONFIRM, "ลำดับรายการสินค้าผิด/หาย (ตรวจจากเลขลำดับ)"
    return ABSTAIN, ""


def a_amount_presence(e, bill, ctx):
    """6. ยอดเงินรายการหาย — สัญญาณจาก detail ('ยอด...หาย/ไม่มี/0')."""
    d = (e.get("detail") or "") + " " + (e.get("type") or "")
    if re.search(r"ยอด.*(หาย|ไม่มี|ขาด)|ไม่มียอด|amount.*missing", d):
        return CONFIRM, "ยอดเงินรายการหาย (ตรวจจากข้อความ)"
    return ABSTAIN, ""


def a_subtotal_reconcile(e, bill, ctx):
    """7. ยอดรวมรายการไม่ reconcile — Σ(qty×price) เทียบ subtotal เกิน tol."""
    if not bill or e.get("field") not in ("ยอดก่อน vat", "ยอดหลัง Vat", "รายการสินค้า"):
        return ABSTAIN, ""
    items = bill.get("items") or []
    sub = bill.get("subtotal")
    if not items or not isinstance(sub, (int, float)) or sub <= 0:
        return ABSTAIN, ""
    s = 0.0
    for it in items:
        q, p = it.get("qty"), it.get("price")
        if isinstance(q, (int, float)) and isinstance(p, (int, float)):
            s += q * p
    if s > 0 and abs(s - sub) / max(abs(sub), 1) > 0.02:
        return CONFIRM, f"Σรายการ {s:,.2f} ≠ subtotal {sub:,.2f} (>2%)"
    return ABSTAIN, ""


def a_empty_items(e, bill, ctx):
    """8. ไม่มีรายการสินค้าแต่มียอด — parse artifact ที่ต้องเตือนชัด."""
    if not bill:
        return ABSTAIN, ""
    items = bill.get("items") or []
    tot = bill.get("total") or bill.get("subtotal") or 0
    if not items and isinstance(tot, (int, float)) and tot > 0 and e.get("field") == "รายการสินค้า":
        return CONFIRM, "ไม่มีรายการสินค้าแต่มียอดเงิน (parse artifact)"
    return ABSTAIN, ""


def a_cross_consensus(e, bill, ctx):
    """9. หลายรหัสชี้จุดเดียวกัน (≥2 code ที่ file/date/seq เดียว) = หลักฐานหนุนกัน → มั่นใจขึ้น."""
    if len(ctx.get("sibling_codes", set())) >= 2:
        return CONFIRM, f"{len(ctx['sibling_codes'])} รหัสชี้จุดเดียวกัน (consensus)"
    return ABSTAIN, ""


def a_master_echo(e, bill, ctx):
    """10. ยืนยันกับ master — ถ้าจุดนี้พึ่ง master แต่ไม่มี master = ยืนยันไม่ได้ → ก้ำกึ่ง."""
    if e.get("code") in _MASTER_DEPENDENT_CODES:
        if ctx.get("master_present", True):
            return CONFIRM, "เทียบ master ได้ (ยืนยัน)"
        return RECHECK, "ไม่มี master เทียบ — ยืนยันเองไม่ได้"
    return ABSTAIN, ""


COUNCIL = [
    ("typo", a_typo_severity), ("unit", a_unit_sanity), ("taxid", a_taxid_checksum),
    ("name", a_name_spacing), ("seq", a_seq_gap), ("amount", a_amount_presence),
    ("reconcile", a_subtotal_reconcile), ("empty_items", a_empty_items),
    ("consensus", a_cross_consensus), ("master_echo", a_master_echo),
]
if len(COUNCIL) != 10:  # [F-4] เดิม assert (หายภายใต้ python -O) → raise ชัดเจน คงการตรวจ invariant เสมอ
    raise RuntimeError(f"COUNCIL ต้องมี 10 ตัว (พบ {len(COUNCIL)}) — โครงสร้างเพี้ยน")


def council_review(entry, bill=None, fixlist=(), master_present=True):
    """ลงคะแนนสภา 10 ผู้ตรวจต่อ 1 จุด → tier ('clear'|'soft') + เหตุผล.

    กติกาตัดสิน (precision-first สำหรับรีพอร์ตลูกค้า):
      • มี CONFIRM และไม่มี RECHECK            → clear
      • มี CONFIRM และมี RECHECK ปนกัน         → clear เฉพาะถ้า consensus ยืนยัน, ไม่งั้น soft
      • ไม่มี CONFIRM (มีแต่ RECHECK/ABSTAIN)   → soft
      • ไม่มีผู้ตรวจเกี่ยวเลย → ใช้ความชัดของรหัส (_STRUCTURAL=clear, อื่น=soft)
    """
    sib = {e.get("code") for e in (fixlist or [entry]) if _point_key(e) == _point_key(entry)}
    ctx = {"sibling_codes": sib, "master_present": master_present}
    votes = {}
    for name, fn in COUNCIL:
        v, why = fn(entry, bill or {}, ctx)
        votes[name] = {"verdict": v, "why": why}
    confirms = [n for n, r in votes.items() if r["verdict"] == CONFIRM]
    rechecks = [n for n, r in votes.items() if r["verdict"] == RECHECK]

    if confirms and not rechecks:
        tier = CLEAR
    elif confirms and rechecks:
        tier = CLEAR if "consensus" in confirms else SOFT
    # [ADR-145/RPT-03] ลบ `elif confirms: tier = CLEAR` (unreachable — confirms truthy ถูกจับโดย 2 branch
    #   บนเสมอ: (T,F)→branch1, (T,T)→branch2). else ครอบ (F,F)+(F,T) ตามเดิม → behavior identical.
    else:
        # ไม่มีผู้ตรวจ CONFIRM
        if not confirms and not rechecks:
            tier = CLEAR if entry.get("code") in _STRUCTURAL else SOFT
        else:
            tier = SOFT
    return {
        "tier": tier,
        "confirm": sorted(confirms),
        "recheck": sorted(rechecks),
        "reason": "; ".join(votes[n]["why"] for n in confirms) or
                  "; ".join(votes[n]["why"] for n in rechecks) or "ไม่มีผู้ตรวจยืนยัน",
        "votes": votes,
    }


def annotate_tiers(fixlist, bill_lookup=None, master_present=True):
    """ติด entry['tier'] + entry['council'] ให้ทุกจุดใน fixlist (in-place) แล้วคืน fixlist."""
    bl = bill_lookup or {}
    for e in fixlist:
        bill = bl.get((e.get("file", ""), e.get("sheet", ""))) if bl else None
        res = council_review(e, bill=bill, fixlist=fixlist, master_present=master_present)
        e["tier"] = res["tier"]
        e["council"] = res
    return fixlist
