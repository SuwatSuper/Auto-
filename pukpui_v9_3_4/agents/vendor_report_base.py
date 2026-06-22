# -*- coding: utf-8 -*-
"""agents/vendor_report_base.py — [F4 split] infra + helper ฐานของรายงานผู้ขาย
(imports + ค่าคงที่ + helper ระดับล่าง: name/tax/period/context/seq/typo). byte-identical:
ย้ายมาจาก vendor_report.py เป๊ะ. __all__ ครอบชื่อ _underscore + ชื่อ import เพื่อให้
`from .vendor_report_base import *` ปลายทาง (ext/main) เห็นครบเหมือน scope เดิม."""
from __future__ import annotations

import re
from collections import Counter, OrderedDict
from typing import Dict, List, Optional, Tuple

from . import core_access as core

DIVIDER = "─" * 31

# ── ผังช่อง (label, โค้ดกฎที่เกี่ยวข้อง) — map ผลกฎ → ช่องภาษาคน ──────────────
#   ค่าใน tuple: ถ้าลงท้ายด้วยตัวเลข = จับ "ตรงตัว" (เช่น VAT002) ; ไม่งั้น = จับ prefix (เช่น TAX → TAX001..)
FIELD_LAYOUT: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("ชื่อบจ.", ("CMP",)),
    ("ที่อยู่", ("ADDR",)),
    ("เลขที่ผู้เสียภาษี", ("TAX",)),
    ("สาขา/สนญ.", ("BR",)),
    ("เลขที่", ("DOC002", "DOC003")),
    ("วันที่", ("DOC001", "DT")),
    ("เลขที่ iv", ("IV", "SEQ")),
    ("รายการสินค้า", ("ITM",)),
    ("ยอดหลัง Vat", ("VAT002", "VAT003", "VAT004", "VAT007")),
    ("ยอดก่อน vat", ("VAT001", "VAT005", "VAT006", "VAT008", "VAT009")),
)

# ชื่อย่อสำหรับ "สรุปท้าย" (รีเช็ค ...) ของแต่ละช่อง
_RECHECK_NAME: Dict[str, str] = {
    "ชื่อบจ.": "ชื่อบริษัท",
    "ที่อยู่": "ที่อยู่",
    "เลขที่ผู้เสียภาษี": "เลขผู้เสียภาษี",
    "สาขา/สนญ.": "สาขา",
    "เลขที่": "เลขที่เอกสาร",
    "วันที่": "วันที่",
    "เลขที่ iv": "เลขที่ IV",
    "รายการสินค้า": "รายการสินค้า",
    "ยอดหลัง Vat": "ยอดหลัง VAT",
    "ยอดก่อน vat": "ยอดก่อน VAT",
}

# prefix นิติบุคคล/คำนำหน้า ที่ตัดออกตอนทำ "ชื่อย่อ"
_NAME_PREFIXES = (
    "บริษัท",
    "ห้างหุ้นส่วนจำกัด",
    "ห้างหุ้นส่วนสามัญ",
    "บจก.",
    "บมจ.",
    "หจก.",
    "ร้าน",
    "กิจการร่วมค้า",
)
_CODE_RE = re.compile(r"\b[A-Z]{2,4}\d{2,3}\b")  # โค้ดกฎ เช่น VAT002 — ตัดออกจากข้อความคน
_FNAME_BAD = re.compile(r'[\\/:*?"<>|\r\n\t]+')  # อักขระต้องห้ามในชื่อไฟล์
_MAX_DETAIL_PER_FIELD = 3  # โชว์รายละเอียดต่อช่องไม่เกินนี้ (ที่เหลือยุบเป็น "และอีก N")


# ── helpers พื้นฐาน ───────────────────────────────────────────────────────────
def _num(x) -> float:
    """แปลงค่าเป็น float อย่างทน (None/ขยะ → 0.0) ผ่าน _D ของ core."""
    try:
        d = core._D(x)
        return float(d) if d is not None else 0.0
    except Exception:
        return 0.0


def _base(code: str) -> str:
    return str(code or "").split("-")[0].strip().upper()


def _match(code: str, spec: Tuple[str, ...]) -> bool:
    """code เข้ากับช่องนี้ไหม. spec ที่ลงท้ายตัวเลข = ตรงตัว ; ไม่งั้น = prefix."""
    b = _base(code)
    if not b:
        return False
    for s in spec:
        if s and s[-1].isdigit():
            if b == s:
                return True
        elif b.startswith(s):
            return True
    return False


def _clean_tax(x) -> str:
    try:
        t = core.clean_tax_id(x)
    except Exception:
        t = None
    return str(t) if t else ""


def _vendor_key(b: dict) -> str:
    """กุญแจจัดกลุ่มผู้ขาย = ชื่อบริษัท (normalize).

    [เหตุผล] เดิมใช้ 'เลขภาษี' เป็นคีย์ → บิลของผู้ขายเดียวกันที่ "เลขภาษีพิมพ์ผิด" บางใบ
      จะถูกแยกออกเป็นคนละรายงาน ทั้งที่เป็นผู้ขายเดียวกัน (และเลขภาษีผิดคือสิ่งที่เรากำลังจะรายงาน).
      ชื่อบริษัทเสถียรกว่า → ใช้ชื่อ (normalize) เป็นคีย์ ; ถ้าไม่มีชื่อค่อย fallback เลขภาษี.
    """
    name = _norm_name(b.get("company") or "")
    if name:
        return "n:" + name
    tid = _clean_tax(b.get("tax_id"))
    if tid:
        return "t:" + tid
    return "(ไม่ระบุผู้ขาย)"


def _short_name(company: str) -> str:
    """ชื่อย่อสำหรับหัวรายงาน/ชื่อไฟล์: ตัดคำนำหน้านิติบุคคล + 'จำกัด' + วงเล็บท้าย."""
    s = (company or "").strip()
    for p in sorted(_NAME_PREFIXES, key=len, reverse=True):
        if s.startswith(p):
            s = s[len(p):].strip()
            break
    s = re.sub(r"\s*\(.*?\)\s*$", "", s)  # ตัด (สำนักงานใหญ่) ฯลฯ ท้าย
    s = re.sub(r"จำกัด\s*$", "", s).strip()
    return s or (company or "ผู้ขาย").strip()


def _norm_name(s: str) -> str:
    """normalize ชื่อบริษัทสำหรับ 'จับคู่ master': ตัดคำนำหน้า/จำกัด/วงเล็บ/ช่องว่าง แล้ว lower."""
    return re.sub(r"\s+", "", _short_name(s or "")).lower()


def _safe_filename(s: str) -> str:
    return _FNAME_BAD.sub("", (s or "")).strip().replace(" ", "")[:60] or "vendor"


def _clean_human(text: str) -> str:
    """ทำข้อความให้เป็น 'ภาษาคน': ตัดโค้ดกฎออก + ยุบช่องว่าง."""
    t = _CODE_RE.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", t).strip(" :-")


def _be_period(d) -> Optional[Tuple[int, int]]:
    """คืน (ปีพ.ศ. 2 หลัก, เดือน) จากวันที่ ; None ถ้าไม่มี."""
    if d is not None and hasattr(d, "year") and hasattr(d, "month"):
        be = d.year + 543 if d.year < 2500 else d.year
        return (be % 100, d.month)
    return None


def _period(vbills: List[dict]) -> Tuple[str, str]:
    """งวดของรายงาน (รวมทุกเดือนของผู้ขาย) → ('หัว', 'ท้าย'). พ.ศ. 2 หลัก.

    เดือนเดียว  → หัว 'YY.MM'        ท้าย 'M/YY'
    หลายเดือน   → หัว 'YY.MMmin-MMmax' ท้าย 'Mmax/YY'  (เช่น '69.01-02' / '2/69')
    ข้ามปี      → หัว 'YYmin.MMmin-YYmax.MMmax'
    """
    yms = sorted({p for p in (_be_period(b.get("iv_date")) for b in vbills) if p})
    if not yms:
        return "", ""
    (yy0, mm0), (yy1, mm1) = yms[0], yms[-1]
    if yms[0] == yms[-1]:
        return f"{yy0:02d}.{mm0:02d}", f"{mm0}/{yy0:02d}"
    if yy0 == yy1:
        return f"{yy0:02d}.{mm0:02d}-{mm1:02d}", f"{mm1}/{yy1:02d}"
    return f"{yy0:02d}.{mm0:02d}-{yy1:02d}.{mm1:02d}", f"{mm1}/{yy1:02d}"


def _full_company(vbills: List[dict]) -> str:
    names = [(b.get("company") or "").strip() for b in vbills if (b.get("company") or "").strip()]
    if not names:
        return "(ไม่ระบุชื่อบริษัท)"
    return Counter(names).most_common(1)[0][0]


def _bill_label(b: dict) -> str:
    """ป้ายอ้างอิงบิลแบบคนอ่าน: 'ไฟล์ X' + (วันที่ ถ้ามี).
    หมายเหตุ: ไม่ใส่เลข IV ในป้าย (เอกสารอ้างไฟล์/วันที่/ลำดับรายการ — และเลข IV รูปแบบ
      เช่น IV099 จะดูเหมือน 'โค้ด') ; ถ้า rule detail อ้างเลขเอกสารเองก็ยังโชว์ตามจริง.
    """
    f = (b.get("file") or "").strip()
    parts = []
    if f:
        parts.append(f"ไฟล์ {f}")
    ds = (b.get("iv_date_str") or "").strip()
    if ds:
        parts.append(f"วันที่ {ds}")
    return " ".join(parts) if parts else "บิลนี้"


# ── จับคู่ master ─────────────────────────────────────────────────────────────
def _find_master_entry(vbills: List[dict], master: Optional[dict]) -> Optional[dict]:
    """หา record master ของผู้ขายนี้ (เทียบเลขภาษีก่อน แล้วค่อยชื่อ) — ทนи master ว่าง/พัง."""
    if not master or not isinstance(master, dict):
        return None
    # 1) เลขภาษี (แม่นสุด) — ใช้เลขที่พบบ่อยสุดในกลุ่ม (ทนบิลเดียวที่เลขผิด)
    taxes = [t for t in (_clean_tax(b.get("tax_id")) for b in vbills) if t]
    vtax = Counter(taxes).most_common(1)[0][0] if taxes else ""
    if vtax:
        for m in master.values():
            if isinstance(m, dict) and _clean_tax(m.get("tax_id")) == vtax:
                return m
    # 2) ชื่อ (normalize)
    vname = _norm_name(_full_company(vbills))
    if vname:
        for m in master.values():
            if isinstance(m, dict) and _norm_name(m.get("name", "")) == vname:
                return m
    return None


# ── ตัวกรอง "noise" ออกจากรายงานลูกค้า ─────────────────────────────────────────
#   รายงานต้องชี้ "ของที่ต้องแก้จริง" เท่านั้น. ข้อสังเกตเชิงรูปแบบ (เว้นวรรคไทย-อังกฤษ,
#   เดาหน่วย "อาจไม่เหมาะ") + การเดาคำผิดด้วย fuzzy พจนานุกรม (X ใกล้เคียง Y ~96%) เชื่อถือ
#   ไม่ได้กับศัพท์เทคนิค/ทับศัพท์ → ตัดออก. *เฉพาะใน .txt ลูกค้า (advisory) — กฎ engine ครบ ไม่กระทบ golden.*
_NOISE_MARKERS = (
    "ติดกัน",
    "ควรเว้นวรรค",
    "ควรมีช่องว่าง",
    "อักขระแปลก",
    "space ซ้อน",
    "NBSP",
    "อาจไม่เหมาะ",     # ITM005 เดาหน่วย
    "[soft]",
    "ใกล้เคียง",        # fuzzy พจนานุกรม (ไม่แน่นอนกับศัพท์เทคนิค)
    "อาจสะกดผิด",       # fuzzy พจนานุกรม
    "(~",               # คะแนน fuzzy เช่น (~96%)
)
# คำผิด "ชัดเจน/กำหนดเอง" (deterministic) → คงไว้เสมอ : pattern ที่เราเขียนเองมี "น่าจะ"/"ขาด "
_SIGNAL_MARKERS = ("น่าจะ", "ขาด ")

# [BUG-2 FIX 11.06.69] diagnostics "ที่มา/การกระทำของ parser" — เล่าว่าระบบทำอะไรสำเร็จ
#   (สแกนเจอที่ไหน / auto-fix อะไร / merge อะไร) ไม่ใช่บิลผิดอะไร → ห้ามรั่วเข้า .txt ลูกค้า.
#   เคสจริง TNT: TAX001 detail='เจอเลขภาษีจาก pure 13-digit [r9,c6]' โผล่ช่องเลขภาษีเป็น
#   "รีเช็ค" ทั้งที่ extraction สำเร็จ ไม่มีปัญหา. จับด้วย marker ใน detail/name —
#   ไม่ใช้ severity ล้วน เพราะ ITM004 'คำสะกด' ก็ INFO แต่เป็นข้อสังเกตเนื้อหา (เทสล็อกให้โชว์).
_PROVENANCE_MARKERS = (
    "เจอเลขภาษีจาก",      # TAX001 fallback scan — มีพิกัด cell ภายใน [rN,cN]
    "fallback scan",       # TAX001 name
    "auto-fix",            # TAX001 name 12→13
    "เพิ่ม 0 นำหน้า",      # TAX001 detail 12→13
    "รวมบิลข้ามหน้า",      # IV001 name — merge หน้าต่อสำเร็จ
    "รวมจาก",              # IV001 detail 'รวมจาก N ชีต'
)


def _is_noise_issue(iss: dict) -> bool:
    """True = ข้อสังเกตเชิงรูปแบบ/soft/เดา ที่ไม่ควรขึ้นในรายงานลูกค้า (ไม่ใช่ error ที่ต้องแก้)."""
    base = _base(iss.get("code", ""))
    detail = str(iss.get("detail") or iss.get("name") or "")
    name = str(iss.get("name") or "")
    # [BUG-2 FIX 11.06.69] provenance diagnostic ของ parser → ไม่ใช่ปัญหา user
    #   (เช็คทั้ง detail และ name — TAX001 name='fallback scan' detail='เจอเลขภาษีจาก ...')
    if any(pm in detail or pm in name for pm in _PROVENANCE_MARKERS):
        return True
    if base == "ITM005":  # เดาหน่วย — soft เสมอ
        return True
    if any(nz in detail for nz in _NOISE_MARKERS):  # fuzzy/รูปแบบ → noise (เช็คก่อน)
        return True
    return False


# ── helper: prefix ไฟล์ / วันที่จุด / ดึงคำผิด ─────────────────────────────────
def _file_prefix(b: dict) -> str:
    """ตัด prefix ไฟล์แบบสั้น: 'STC_69_05.xls' → 'STC' (ตัดที่ _ / ช่องว่าง / จุดแรก)."""
    f = (b.get("file") or "").strip()
    if not f:
        return ""
    return re.split(r"[_\s.]", f, 1)[0] or f


def _date_dots(b: dict) -> str:
    """วันที่แบบจุด: '11/05/2026' → '11.05.2026'."""
    ds = (b.get("iv_date_str") or "").strip()
    return ds.replace("/", ".") if ds else ""


def _ctx_prefix(b: dict, with_date: bool = True) -> str:
    """หัวประโยคอ้างอิงบิลแบบคน: 'ไฟล์ STC วันที่ 11.05.2026' (prefix + วันที่จุด).
    with_date=False → 'ไฟล์ STC' (ใช้กับช่อง 'วันที่' ที่ไม่ต้องการวันที่ซ้ำ).
    """
    pre = _file_prefix(b)
    d = _date_dots(b)
    head = f"ไฟล์ {pre}" if pre else ""
    if with_date and d:
        head = f"{head} วันที่ {d}".strip()
    return head or (f"วันที่ {d}" if d else "บิลนี้")


_SEQ_RE = re.compile(r"#\s*(\d+)")
_QUOTED_RE = re.compile(r'["“]([^"”]+)["”]')


def _seq_of(detail: str) -> Optional[int]:
    m = _SEQ_RE.search(str(detail or ""))
    return int(m.group(1)) if m else None


def _item_by_seq(b: dict, seq: Optional[int]) -> Optional[dict]:
    if seq is None:
        return None
    for it in b.get("items") or []:
        try:
            if int(it.get("seq")) == seq:
                return it
        except (TypeError, ValueError):
            continue
    return None


def _wrong_word(item_name: str, suggestion: str) -> Optional[str]:
    """หา 'คำที่สะกดผิด' ในชื่อรายการ โดยเทียบกับคำที่ถูก (suggestion) — คืน run ของคำที่ใกล้สุด.
    เช่น suggestion='THAI UNION', name='HAI UNION สายไฟ...' → 'HAI UNION'.
    """
    name = str(item_name or "")
    sug = str(suggestion or "").strip()
    if not name or not sug:
        return None
    try:
        from rapidfuzz import fuzz
    except Exception:
        return None
    words = name.split()
    k = max(1, len(sug.split()))
    best, best_score = None, 0.0
    for i in range(0, max(1, len(words) - k + 1)):
        cand = " ".join(words[i:i + k])
        sc = fuzz.ratio(cand.upper(), sug.upper())
        if sc > best_score:
            best, best_score = cand, sc
    # ใกล้แต่ไม่เท่ากับคำที่ถูก = คำผิด
    if best and best_score >= 60 and best.strip().upper() != sug.upper():
        return best.strip()
    return None




__all__ = [
    're',
    'Counter',
    'OrderedDict',
    'Dict',
    'List',
    'Optional',
    'Tuple',
    'core',
    'DIVIDER',
    'FIELD_LAYOUT',
    '_RECHECK_NAME',
    '_NAME_PREFIXES',
    '_CODE_RE',
    '_FNAME_BAD',
    '_MAX_DETAIL_PER_FIELD',
    '_num',
    '_base',
    '_match',
    '_clean_tax',
    '_vendor_key',
    '_short_name',
    '_norm_name',
    '_safe_filename',
    '_clean_human',
    '_be_period',
    '_period',
    '_full_company',
    '_bill_label',
    '_find_master_entry',
    '_NOISE_MARKERS',
    '_SIGNAL_MARKERS',
    '_is_noise_issue',
    '_file_prefix',
    '_date_dots',
    '_ctx_prefix',
    '_SEQ_RE',
    '_QUOTED_RE',
    '_seq_of',
    '_item_by_seq',
    '_wrong_word',
]
