# -*- coding: utf-8 -*-
"""issue_consolidator.py — ชั้นสรุป (consolidation) ที่ "Agent ควรทำ" แต่เดิมไม่ได้ทำ

ปัญหาที่แก้ (ตามที่ผู้ใช้ชี้):
  บิลเดียว รายการเดียว เลขที่เดียว แต่ engine เด้งหลายรหัสที่ "ชี้ปัญหาเดียวกัน" เช่น
  รายการ #2 เด้ง ITM004(สะกด) + ITM005(หน่วย) + ITM010(typo) + ITM011(fuzzy) + ITM015(หน่วยต่าง)
  = 5 บรรทัดในชีต Error ทั้งที่เป็น "ปัญหาชื่อ/หน่วยของรายการ #2" อันเดียว.
  ถ้าไม่ยุบ คนต้องมานั่งสรุปเอง → ช้า/ตกหล่น.

ทำอะไร (advisory · pure · อ่านอย่างเดียว — ไม่แตะ engine/ผลตรวจ/golden hash):
  • จัดกลุ่ม issue ของแต่ละบิลตาม "จุด" (spot):
      - รหัสตระกูล ITM  → จับเลขรายการจาก detail "#N:" → กลุ่มต่อ "รายการ #N"
      - รหัสอื่น        → กลุ่มต่อ "หมวด" ระดับบิล (บริษัท/เลขภาษี/ยอดเงิน/วันที่/เอกสาร/ที่อยู่/สาขา/IV)
  • ยุบหลายรหัสในจุดเดียวกันให้เหลือ 1 "ข้อสรุป" พร้อม: หมวด, รหัสที่เกี่ยว, สรุปสั้น,
    ความรุนแรงสูงสุด, และป้ายช่วยคัด (master-dependent / review-only / ต้องแก้).
  • จัด "หมวดรหัสที่สอดคล้องกัน" ให้อัตโนมัติ → คนเห็น "ปัญหาจริงกี่เรื่อง" ไม่ใช่ "กี่รหัส".

ผลตรวจดิบ (bill['issues']) ไม่ถูกแตะ — ทุกรหัสยังอยู่ครบ (recall ไม่หาย) แค่ "นำเสนอแบบยุบ".
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

# ลำดับความรุนแรง (ตรงกับทั้งระบบ)
_SEV_RANK = {"CRITICAL": 3, "ERROR": 2, "WARNING": 1, "INFO": 0}

# ── หมวดตามตระกูลรหัส (prefix) — "รหัสไหนสอดคล้องกัน" ────────────────────────
#   (ป้ายหมวด, คำอธิบายกลาง ๆ ของหมวด)
CODE_FAMILY = {
    "CMP":  ("บริษัท/นิติบุคคล", "ชื่อ/คำนำหน้า/เว้นวรรค/แบรนด์"),
    "TAX":  ("เลขผู้เสียภาษี",   "13 หลัก/ตัวเลขล้วน/ตรงบริษัท/checksum"),
    "ADDR": ("ที่อยู่",          "ครบถ้วน/สะกด/ตรง master/ไปรษณีย์"),
    "BR":   ("สาขา",            "รหัส/การระบุสาขา"),
    "DOC":  ("เอกสาร",          "วันที่↔ชีต / เลขที่ซ้ำในไฟล์"),
    "IV":   ("เลขที่ใบกำกับ",    "prefix/ลำดับ/ซ้ำ/ถอยหลัง"),
    "DT":   ("วันที่",           "เดือน target/อนาคต/พ.ศ.-ค.ศ./นอกช่วง"),
    "ITM":  ("รายการสินค้า",     "ชื่อ/หน่วย/จำนวน/ราคา/ลำดับ/ซ้ำ"),
    "VAT":  ("ยอดเงิน/ภาษี",     "ผลรวม/VAT 7%/total/ส่วนลด"),
    "SYS":  ("ระบบ",            "กฎ/parse ทำงานผิดพลาด"),
}

# รหัสที่ "ขึ้นกับ master-data" — ถ้า master ไม่ครบจะ false positive (คัดออกก่อนได้)
# [ADR-111] ถอด CMP005 ออก — r_cmp005 ตรวจ "โครงสร้างชื่อ" ล้วน ('บริษัท'→ต้องมี 'จำกัด' ฯลฯ)
#   ไม่อ่าน master เลย → จัดเป็น MASTER_DEPENDENT ผิด ทำให้ must-fix เชิงโครงสร้างถูกกลบลงเลน "ขึ้นกับ master".
#   golden/report-neutral บน corpus (CMP005 ฟ้อง 0×). ดู INVARIANTS/DECISIONS.md §ADR-111.
MASTER_DEPENDENT = {"CMP001", "CMP003", "CMP004", "TAX003", "TAX005", "ADDR003"}

# รหัสเลน "ข้อสังเกต" (review) — ไม่ใช่ must-fix
# [ADR-059] เลิก hardcode → derive จาก code_labels.MAP (source of truth เดียวกับ viewer)
#   ปัญหาเดิม: REVIEW_ONLY hardcoded 11 รหัส → ตกหล่นรหัสเลน check/note (CMP006/DT001/DT002/
#     IV004/ITM019/…) ทำให้ spot ที่เป็น "ข้อสังเกตล้วน" ถูกจัดผิดเป็น "ต้องแก้" ใน consolidated report
#     (lane logic หลุดจาก MAP action-tier — desync ที่ ADR-054/M6 เคยตามแก้ทีละรหัสแบบ manual).
#   ใหม่: REVIEW_ONLY = {รหัสที่ MAP lane ∈ soft} ∪ config.REVIEW_CODES
#     soft lane = check/review/note/master (ทุกเลนที่ "ไม่ใช่ fix")
#     ∪ config.REVIEW_CODES → คง ITM015 (MAP=fix แต่ ADR-051/054 จัดเป็น review: หน่วยซ้ำชื่อเดียว
#       เช่น ทราย=[คิว,ตัน] = ผู้ขายขายหลายหน่วย ไม่ใช่ error) ไม่ให้ถอยกลับเป็น must-fix.
#   ผล: must-fix แท้ = (MAP=fix ลบ config.REVIEW_CODES = 38 รหัส รวม DOC001) ยังเป็น "ต้องแก้" ครบ
#       (zero false-soft). advisory layer — golden hash ไม่ขยับ (issue_consolidator อ่านอย่างเดียว).
#   หมายเหตุ: คง MAP[ITM015]='fix' ไว้ (viewer/company_summary ใช้ → เปลี่ยนจะกระทบ golden-safe
#     อีกพื้นผิว) — sync ที่ชั้นนี้ด้วย ∪ config.REVIEW_CODES แทน. ดู INVARIANTS/DECISIONS.md §ADR-059
_REVIEW_SOFT_LANES = frozenset({"check", "review", "note", "master"})
try:
    from code_labels import MAP as _CODE_LABEL_MAP
    _MAP_SOFT = frozenset(
        code for code, _meta in _CODE_LABEL_MAP.items()
        if isinstance(_meta, (tuple, list)) and len(_meta) > 2 and _meta[2] in _REVIEW_SOFT_LANES
    )
except Exception:                                   # pragma: no cover — defensive (longevity)
    _MAP_SOFT = frozenset()
try:
    from config import REVIEW_CODES as _CFG_REVIEW_CODES
except Exception:                                   # pragma: no cover
    _CFG_REVIEW_CODES = frozenset()
# fallback (เผื่อ import ทั้งคู่ล้ม) = ชุด hardcoded เดิมที่พิสูจน์แล้ว — กันรายงานพังเฉย ๆ
_REVIEW_ONLY_FALLBACK = frozenset({"ITM003", "ITM004", "ITM005", "ITM007", "ITM009",
                                   "ITM012", "ITM015", "IV001", "VAT006", "VAT008", "VAT010"})
REVIEW_ONLY = (_MAP_SOFT | frozenset(_CFG_REVIEW_CODES)) or _REVIEW_ONLY_FALLBACK

# กลุ่มย่อยของ ITM → ใช้สรุปว่า "รายการนี้มีปัญหาด้านไหน" (รหัสที่สอดคล้องกัน)
_ITM_ASPECT = {
    "ชื่อ/สะกด":   {"ITM003", "ITM004", "ITM007", "ITM010", "ITM011", "ITM012"},
    "หน่วย":       {"ITM005", "ITM006", "ITM015", "ITM019", "ITM020"},  # [ADR-111] ITM019/020 เป็นเรื่องหน่วย
    "จำนวน/ราคา":  {"ITM001", "ITM008", "ITM017", "ITM018"},
    "ลำดับ":       {"ITM002", "ITM013", "ITM014"},
    "ซ้ำ":         {"ITM016"},
    "alias":       {"ITM009"},
}


def _family(code: str) -> str:
    m = re.match(r"[A-Z]+", code or "")
    return m.group(0) if m else "?"


def _item_spot(detail: str):
    """ดึงเลขรายการจาก detail ITM ('#N: ...') → 'รายการ #N' ; ไม่มี → None."""
    m = re.match(r"\s*#(\d+)", detail or "")
    return f"รายการ #{m.group(1)}" if m else None


def _itm_aspects(codes) -> list:
    """รหัส ITM ในกลุ่ม → ด้านที่มีปัญหา (เช่น ['ชื่อ/สะกด','หน่วย'])."""
    asp = []
    for name, group in _ITM_ASPECT.items():
        if codes & group:
            asp.append(name)
    return asp or ["รายการ"]


def consolidate_bill(bill: dict) -> list:
    """ยุบ issue ของ 1 บิลเป็นข้อสรุปต่อ 'จุด' (spot). คืน list ของ consolidated finding."""
    groups = defaultdict(lambda: {"codes": set(), "names": [], "sevs": set(), "details": []})
    for iss in bill.get("issues", []):
        code = iss.get("code", "?")
        fam = _family(code)
        if fam == "ITM":
            spot = _item_spot(iss.get("detail", "")) or "รายการ (รวม)"
        else:
            spot = "ทั้งบิล"
        g = groups[(fam, spot)]
        g["codes"].add(code)
        nm = iss.get("name")
        if nm and nm not in g["names"]:
            g["names"].append(nm)
        g["sevs"].add(iss.get("severity", "INFO"))
        g["details"].append(iss.get("detail", ""))

    out = []
    for (fam, spot), g in groups.items():
        cat, _ = CODE_FAMILY.get(fam, (fam, ""))
        codes = g["codes"]
        max_sev = max(g["sevs"], key=lambda s: _SEV_RANK.get(s, 0))
        # สรุปสั้น
        if fam == "ITM":
            summary = f"{cat} {spot}: " + " + ".join(_itm_aspects(codes))
        else:
            summary = f"{cat}: " + " + ".join(g["names"][:3])
        # ป้ายช่วยคัด
        if codes & MASTER_DEPENDENT:
            bucket = "ขึ้นกับ master"
        elif codes <= REVIEW_ONLY:
            bucket = "ข้อสังเกต (review)"
        else:
            bucket = "ต้องแก้"
        out.append({
            "file": bill.get("file", ""),
            "sheet": str(bill.get("sheet", "")),
            "iv": bill.get("iv_number") or bill.get("iv_number_raw") or "-",
            "spot": spot,
            "category": cat,
            "summary": summary,
            "codes": ",".join(sorted(codes)),
            "n_codes": len(codes),
            "max_severity": max_sev,
            "bucket": bucket,
            "example": (g["details"][0] or "")[:120],
        })
    # เรียง: ต้องแก้ก่อน → severity สูงก่อน → ตามไฟล์/ชีต/จุด
    _bucket_rank = {"ต้องแก้": 0, "ขึ้นกับ master": 1, "ข้อสังเกต (review)": 2}
    out.sort(key=lambda r: (_bucket_rank.get(r["bucket"], 3),
                            -_SEV_RANK.get(r["max_severity"], 0),
                            r["file"], r["sheet"], r["spot"]))
    return out


def consolidate_all(all_bills: list) -> list:
    """ยุบทั้งชุด → list ของ consolidated finding (ทุกบิล)."""
    findings = []
    for b in all_bills:
        findings.extend(consolidate_bill(b))
    return findings


def summary_stats(all_bills: list) -> dict:
    """สถิติ before/after + แยกหมวด + แยก bucket — ใช้โชว์ว่า 'ปัญหาจริงกี่เรื่อง'."""
    raw = sum(len(b.get("issues", [])) for b in all_bills)
    findings = consolidate_all(all_bills)
    by_cat = Counter(f["category"] for f in findings)
    by_bucket = Counter(f["bucket"] for f in findings)
    fix_only = [f for f in findings if f["bucket"] == "ต้องแก้"]
    bills_fix = len({(f["file"], f["sheet"], f["iv"]) for f in fix_only})
    return {
        "raw_issues": raw,
        "consolidated_findings": len(findings),
        "fix_findings": len(fix_only),
        "bills_with_fix": bills_fix,
        "by_category": dict(by_cat.most_common()),
        "by_bucket": dict(by_bucket),
    }
