# -*- coding: utf-8 -*-
"""agents/vendor_report_ext.py — [F4 split] helper จัดฟอร์แมต field/ข้อความ (กลุ่ม B).
byte-identical: ย้ายมาจาก vendor_report.py เป๊ะ. infra ทั้งหมดมาจาก _base (รวมชื่อ
_underscore ผ่าน __all__ ของ base)."""
from __future__ import annotations

from .vendor_report_base import (   # [de-star P2] เดิม `import *` — explicit (23 ชื่อที่ _ext ใช้จริง)
    Counter, Dict, List, Optional, OrderedDict, Tuple, re,
    _MAX_DETAIL_PER_FIELD, _QUOTED_RE, _RECHECK_NAME, _base,
    _clean_human, _clean_tax, _ctx_prefix, _file_prefix, _find_master_entry, _full_company,
    _is_noise_issue, _item_by_seq, _match, _num, _seq_of, _vendor_key, _wrong_word,
)
from code_labels import MASTER_FIELD_SHORT  # [A1] ชื่อย่อช่องตัวตนสำหรับสรุปท้าย "ตรวจไม่ได้"


def _item_problem(b: dict, iss: dict) -> Tuple[Optional[int], str]:
    """คืน (seq, ปัญหาเป็นภาษาคน) ของ issue รายการสินค้า — สำนวนที่ลูกค้าต้องการ.
    typo → 'คำว่า {คำผิด}' ; เลขคณิต → 'จำนวน × ราคา ไม่ตรงกับยอด' ; อื่น → ข้อความที่ทำให้อ่านง่าย.
    """
    code = _base(iss.get("code", ""))
    detail = str(iss.get("detail") or iss.get("name") or "")
    seq = _seq_of(detail)
    it = _item_by_seq(b, seq)
    name = (it.get("name") if it else "") or ""

    # เลขคณิต: จำนวน×ราคา ≠ ยอด
    if code in ("ITM001",) or "≠ amount" in detail or "ไม่ตรงยอด" in detail:
        return seq, "จำนวน × ราคา ไม่ตรงกับยอด"

    # typo/คำสะกด: พยายามดึง "คำผิด" ออกมาตรง ๆ
    sug_m = _QUOTED_RE.search(detail)
    suggestion = sug_m.group(1) if sug_m else ""
    wrong = _wrong_word(name, suggestion) if suggestion else None
    if wrong:
        return seq, f"คำว่า {wrong}"
    # มี suggestion แต่ดึงคำผิดไม่ได้ → บอกคำที่ควรเป็น (ยังอ่านเป็นคนได้)
    if suggestion:
        return seq, f'น่าจะเป็น "{suggestion}"'
    # ไม่มี suggestion → ใช้ข้อความที่ตัดส่วนชื่อรายการ (ในวงเล็บท้าย) ออก ให้อ่านง่าย
    body = re.sub(r"^#\s*\d+\s*[:：]\s*", "", detail)         # ตัด '#N: '
    body = re.sub(r"\s*\([^)]*\)\s*$", "", body).strip()      # ตัด '(ชื่อรายการ…)' ท้าย
    return seq, (body or "ตรวจสอบรายการ")


# หน่วยที่ "ชัดเจน" สำหรับสินค้าบางชนิด — ถ้าบิลใช้หน่วยอื่นถือว่าผิดจริง (อนุญาตให้โชว์ในรายงาน)
#   (รายการ curated — ความเชื่อมั่นสูง, false-positive ต่ำ ; เพิ่มได้ตามที่ลูกค้าระบุ)
_DEFINITE_UNIT = (
    ("เพลท", "แผ่น", ("เส้น", "ท่อน", "อัน", "ตัว")),   # เหล็กเพลท → แผ่น (ไม่ใช่ เส้น)
)


def _definite_unit_phrase(b: dict, iss: dict) -> Optional[Tuple[int, str]]:
    """ถ้าเป็น ITM005 ที่เข้าข่าย 'หน่วยผิดชัดเจน' (เช่น เหล็กเพลท ใช้ เส้น) → คืน (seq, ปัญหา) ; ไม่งั้น None."""
    if _base(iss.get("code", "")) != "ITM005":
        return None
    detail = str(iss.get("detail") or "")
    seq = _seq_of(detail)
    it = _item_by_seq(b, seq)
    if not it:
        return None
    name = str(it.get("name") or "")
    unit = str(it.get("unit") or "").strip()
    for kw, correct, wrong_units in _DEFINITE_UNIT:
        if kw in name and (unit in wrong_units or (unit and unit != correct and unit not in (correct,))):
            # ดึง "คำสินค้า" ที่มี keyword (เช่น 'เหล็กเพลท')
            tok = next((w for w in name.split() if kw in w), kw)
            cur = unit or "(ไม่ระบุ)"
            return seq, f"คำว่า {tok} หน่วยควรเป็น {correct} ไม่ใช่ {cur}"
    return None


def _item_field_text(vbills: List[dict]) -> str:
    """สำนวนช่อง 'รายการสินค้า' ตามที่ลูกค้าต้องการ:
       'ไฟล์ STC วันที่ 11.05.2026 รายการสินค้า ลำดับที่ 2 คำว่า HAI UNION รีเช็คครับ'
    จัดกลุ่มตาม (prefix, วันที่) → ไล่ 'ลำดับที่ N {ปัญหา}' ; หลายกลุ่มคั่นด้วย ' ; '.
    ตัด noise (เดาหน่วย/เว้นวรรค/fuzzy) ออก ; แต่ 'หน่วยผิดชัดเจน' (เช่น เหล็กเพลท→แผ่น) ให้โชว์.
    """
    groups: "OrderedDict[str, list]" = OrderedDict()
    itm020_cnt: "OrderedDict[str, int]" = OrderedDict()   # [ADR-108/UX] file_prefix -> จำนวนบิล
    for b in vbills:
        ctx = _ctx_prefix(b)
        for iss in b.get("issues") or []:
            if not _match(iss.get("code", ""), ("ITM",)):
                continue
            if iss.get("code") == "ITM020":
                # [ADR-108/UX] ทั้งบิลไม่มีหน่วยสินค้า เกิดซ้ำหลายสิบบิล/ไฟล์ → ยุบเป็นสรุปต่อไฟล์
                #   (นับบิล) 1 บรรทัด/ไฟล์ ไม่ร่ายทีละบิล ; typo รายตัวคงชี้ทีละตัวด้านล่าง
                pre = _file_prefix(b)
                itm020_cnt[pre] = itm020_cnt.get(pre, 0) + 1
                continue
            if _is_noise_issue(iss):
                # ITM005 ส่วนใหญ่เป็น noise — ยกเว้น 'หน่วยผิดชัดเจน' (curated)
                du = _definite_unit_phrase(b, iss)
                if du is None:
                    continue
                seq, phrase = du
            else:
                seq, phrase = _item_problem(b, iss)
            entry = (seq if seq is not None else 0, phrase)
            lst = groups.setdefault(ctx, [])
            if entry not in lst:
                lst.append(entry)
    if not groups and not itm020_cnt:
        return "ตรง"
    parts = []
    for ctx, entries in groups.items():
        entries.sort(key=lambda e: (e[0], e[1]))
        items_txt = ", ".join(
            (f"รายการสินค้า ลำดับที่ {seq} {ph}" if seq else f"รายการสินค้า {ph}")
            for seq, ph in entries
        )
        parts.append(f"{ctx} {items_txt}")
    for pre, cnt in itm020_cnt.items():   # [ADR-108/UX] สรุป ITM020 ต่อไฟล์ (นับบิล)
        parts.append(f"ไฟล์ {pre}: {cnt} บิลไม่มีหน่วยสินค้าทั้งบิล (ช่องหน่วยว่างในต้นฉบับ)" if pre
                     else f"{cnt} บิลไม่มีหน่วยสินค้าทั้งบิล (ช่องหน่วยว่างในต้นฉบับ)")
    return " ; ".join(parts) + " รีเช็คครับ"


def _natural_field_text(vbills: List[dict], spec: Tuple[str, ...], with_date: bool = True) -> Tuple[bool, str]:
    """สำนวนฟิลด์ทั่วไป (สาขา/เลขที่/วันที่/IV/ยอด VAT) แบบภาษาคน:
       'ไฟล์ STC วันที่ 11.05.2026 {ปัญหา} ; ... รีเช็คครับ'  (ไม่มีคำนำหน้า 'ไม่ตรง —').
    with_date=False → ตัด 'วันที่ …' ออกจากบริบท (เช่นช่อง 'วันที่' ที่ detail พูดถึงวันที่อยู่แล้ว).
    คืน (ok, text). ok=True → 'ตรง'.
    """
    groups: "OrderedDict[str, list]" = OrderedDict()
    for b in vbills:
        ctx = _ctx_prefix(b, with_date=with_date)
        for iss in b.get("issues") or []:
            if not _match(iss.get("code", ""), spec):
                continue
            if _is_noise_issue(iss):
                continue
            body = re.sub(r"^#\s*\d+\s*[:：]\s*", "", str(iss.get("detail") or iss.get("name") or ""))
            body = _clean_human(body)
            if not body:
                continue
            lst = groups.setdefault(ctx, [])
            if body not in lst:
                lst.append(body)
    if not groups:
        return True, "ตรง"
    parts = []
    for ctx, bodies in groups.items():
        shown = bodies[:_MAX_DETAIL_PER_FIELD]
        extra = len(bodies) - len(shown)
        body = ", ".join(shown) + (f", และอีก {extra} รายการ" if extra > 0 else "")
        parts.append(f"{ctx} {body}")
    return False, " ; ".join(parts) + " รีเช็คครับ"


# ── ยอด (ก่อน VAT) + Diff ─────────────────────────────────────────────────────
def _fmt_baht(x: float) -> str:
    """รูปแบบเงินภาษาคน: จำนวนเต็มไม่โชว์ทศนิยม, ไม่งั้น 2 ตำแหน่ง."""
    return f"{x:,.0f}" if abs(x - round(x)) < 0.005 else f"{x:,.2f}"


def _pre_vat(b: dict) -> float:
    """ยอด 'ก่อน VAT' ของบิล แบบทนทาน.
    ปกติ subtotal = ก่อน VAT (subtotal + vat ≈ total). แต่บาง layout parser เก็บ 'ยอดรวม VAT'
    ใส่ช่อง subtotal (subtotal ≈ total ทั้งที่มี vat แยก) → ต้อง derive 'total − vat' ไม่งั้นยอดจะรวม VAT.
    """
    sub = _num(b.get("subtotal"))
    vat = _num(b.get("vat"))
    tot = _num(b.get("total"))
    if sub > 0 and tot > 0 and vat > 0:
        if abs((sub + vat) - tot) <= max(0.5, tot * 0.001):
            return sub                      # subtotal + vat = total → subtotal คือก่อน VAT (ถูก)
        if abs(sub - tot) <= 0.01:
            return tot - vat                # subtotal == total (รวม VAT ผิด) → derive ก่อน VAT
        return sub                          # อื่น ๆ เชื่อ subtotal
    if sub > 0:
        return sub
    if tot > 0 and vat > 0:
        return tot - vat
    return tot or sub


def _amount_line(vbills: List[dict]) -> str:
    """บรรทัด 'ยอด' — ผลรวม 'ก่อน VAT' (ทนทาน) + สถานะ.
    ตรง: 'ยอด : {รวมก่อน VAT} บาท ตรง'
    ไม่ตรง (ผลรวมรายการ ≠ ยอดก่อน VAT ในบางบิล): 'ยอด : ยอดเงินในบิลรวม {รวม} บาท ยอด Diff {ต่าง} บาท'
    """
    pre_sum = sum(_pre_vat(b) for b in vbills)
    # Diff ก่อน VAT = ผลรวม |ยอดก่อน VAT − ผลรวมรายการ| เฉพาะบิลที่ต่างเกิน 0.01 (= เลขในบิลผิดจริง)
    diff_total = 0.0
    has_gap = False
    for b in vbills:
        items_sum = sum(_num(it.get("amount")) for it in (b.get("items") or []))
        pre = _pre_vat(b)
        if items_sum and abs(items_sum - pre) > 0.01:
            diff_total += abs(items_sum - pre)
            has_gap = True
    if not has_gap:
        return f"ยอด : {_fmt_baht(pre_sum)} บาท ตรง"
    return f"ยอด : ยอดเงินในบิลรวม {_fmt_baht(pre_sum)} บาท ยอด Diff {_fmt_baht(diff_total)} บาท"


def _bill_count_line(vbills: List[dict]) -> str:
    """บรรทัด 'บิล' — นับเป็นบิล (รวมหน้าต่อแล้ว). ทักท้วงถ้าพบเลขที่ IV ซ้ำ."""
    ivs = [(b.get("iv_number") or "").strip() for b in vbills if (b.get("iv_number") or "").strip()]
    dup = [iv for iv, n in Counter(ivs).items() if n > 1]
    if dup:
        return f"บิล : {len(vbills)} บิล (พบเลขที่ IV ซ้ำ {len(dup)} เลข — รีเช็คครับ)"
    return f"บิล : {len(vbills)} บิล ตรง"


# ── หมายเหตุ: master vs บิล + จุดต่าง (ที่อยู่ / เลขภาษี) ────────────────────────
def _bill_values(vbills: List[dict], field: str) -> List[str]:
    """ค่าที่พบในบิล (ไม่ซ้ำ, คงลำดับ) สำหรับ field หนึ่ง."""
    out = OrderedDict()
    for b in vbills:
        v = (b.get(field) or "").strip()
        if v:
            out.setdefault(v, True)
    return list(out.keys())


def _token_diff(master_val: str, bill_val: str) -> str:
    """จุดต่างระดับคำ: คำที่อยู่ฝั่งหนึ่งแต่ไม่อยู่อีกฝั่ง (ภาษาคนอ่านง่าย)."""
    mt = [t for t in re.split(r"\s+", str(master_val or "")) if t]
    bt = [t for t in re.split(r"\s+", str(bill_val or "")) if t]
    only_m = [t for t in mt if t not in bt]
    only_b = [t for t in bt if t not in mt]
    parts = []
    if only_b:
        parts.append("ในบิลเกินมา: " + " ".join(only_b[:8]))
    if only_m:
        parts.append("ในบิลขาด: " + " ".join(only_m[:8]))
    return " / ".join(parts) if parts else "ต่างกันเล็กน้อย (ดูข้อความเต็ม)"


def _note_blocks(vbills: List[dict], master: Optional[dict], field_ok: Dict[str, bool]) -> List[str]:
    """สร้างบล็อก 'หมายเหตุ' โชว์ค่า master vs บิล + จุดต่าง เฉพาะ ที่อยู่/เลขภาษี ที่ไม่ตรง."""
    m = _find_master_entry(vbills, master)
    blocks: List[str] = []

    # ── ที่อยู่ ──
    if not field_ok.get("ที่อยู่", True):
        bill_addrs = _bill_values(vbills, "address")
        bill_addr = bill_addrs[0] if bill_addrs else "(ไม่พบที่อยู่ในบิล)"
        master_addr = (m.get("address") if m else "") or "(ยังไม่ได้ใส่ใน Master data)"
        blocks.append("ที่อยู่ที่ถูกต้อง (Master data) : " + master_addr)
        blocks.append("ที่อยู่ในบิล : " + bill_addr)
        if m and m.get("address"):
            blocks.append("จุดต่าง : " + _token_diff(master_addr, bill_addr))

    # ── เลขที่ผู้เสียภาษี ──
    if not field_ok.get("เลขที่ผู้เสียภาษี", True):
        bill_tax = _bill_values(vbills, "tax_id")
        bill_t = bill_tax[0] if bill_tax else "(ไม่พบในบิล)"
        master_t = (m.get("tax_id") if m else "") or "(ยังไม่ได้ใส่ใน Master data)"
        blocks.append("เลขที่ผู้เสียภาษีที่ถูกต้อง (Master data) : " + master_t)
        blocks.append("เลขที่ผู้เสียภาษีในบิล : " + bill_t)
        if m and m.get("tax_id"):
            blocks.append("จุดต่าง : " + ("เลขไม่ตรงกัน" if _clean_tax(master_t) != _clean_tax(bill_t) else "รูปแบบต่างกัน"))

    return blocks


def _summary_sentence(field_ok: "OrderedDict[str, bool]", has_notes: bool, uncheckable=()) -> str:
    """สรุปท้ายภาษาคน (ซอฟ):
       ตรงหมด + ตรวจได้ทุกช่อง       → 'ตรงครับ'
       ตรงหมด แต่บางช่องตัวตนตรวจไม่ได้ → 'ตรงเท่าที่ตรวจได้ (ช่อง .. ตรวจไม่ได้ — ไม่มี master เทียบ)'
       มีจุด + มีหมายเหตุ            → 'รีเช็ค{ฟิลด์}และแก้ไขตามหมายเหตุนะครับผม{หมายเหตุตรวจไม่ได้}'
       มีจุด ไม่มีหมายเหตุ           → 'รีเช็ค{ฟิลด์}ครับ{หมายเหตุตรวจไม่ได้} ที่เหลือตรงครับผม'
    [A1] 'ตรวจไม่ได้' = สถานะที่สาม (ไม่ใช่ error → ไม่เข้า 'รีเช็ค') — กันการพูดว่า 'ตรงครับ' หลอก.
    """
    bad = [_RECHECK_NAME.get(lbl, lbl) for lbl, ok in field_ok.items() if not ok]
    unck = [MASTER_FIELD_SHORT.get(lbl, _RECHECK_NAME.get(lbl, lbl)) for lbl in uncheckable]
    unck_note = (f" (ช่อง {'/'.join(unck)} ตรวจไม่ได้ — ไม่มี master เทียบ)") if unck else ""
    if not bad:
        return "ตรงครับ" if not unck else f"ตรงเท่าที่ตรวจได้{unck_note}"
    listed = ", ".join(bad)
    if has_notes:
        return f"รีเช็ค{listed}และแก้ไขตามหมายเหตุนะครับผม{unck_note}"
    return f"รีเช็ค{listed}ครับ{unck_note} ที่เหลือตรงครับผม"


def _group_by_vendor(bills: List[dict]) -> List[Tuple[str, List[dict]]]:
    """จัดกลุ่มบิลตาม "ผู้ขาย" (รวมทุกเดือน) → 1 รายงาน/ผู้ขาย ; งวดในหัวแสดงเป็นช่วงเดือน.
    เรียง deterministic ด้วยยอดก่อน VAT มาก→น้อย (เท่ากันตัดด้วยชื่อ/คีย์).
    """
    groups: "OrderedDict[str, List[dict]]" = OrderedDict()
    for b in bills or []:
        groups.setdefault(_vendor_key(b), []).append(b)

    def _sort_key(item):
        vkey, vb = item
        sub = sum(_num(b.get("subtotal")) for b in vb)
        return (-sub, _full_company(vb), vkey)

    return [(k, vb) for k, vb in sorted(groups.items(), key=_sort_key)]


# ── render ───────────────────────────────────────────────────────────────────
def _company_field(vbills: List[dict], master: Optional[dict]) -> Tuple[bool, str]:
    """ช่อง 'ชื่อบจ.' : 'ตรง' หรือ 'ไม่ตรง — ในบิล X / master Y' (สั้น ๆ ในบรรทัด)."""
    has_issue = any(
        _match(i.get("code", ""), ("CMP",)) and not _is_noise_issue(i)
        for b in vbills
        for i in (b.get("issues") or [])
    )
    if not has_issue:
        return True, "ตรง"
    bill_name = _full_company(vbills)
    m = _find_master_entry(vbills, master)
    mn = (m.get("name") if m else "") or "(ยังไม่ได้ใส่ใน Master data)"
    return False, f"ไม่ตรง — ในบิล {bill_name} / master {mn} รีเช็คครับ"




__all__ = [
    '_item_problem',
    '_DEFINITE_UNIT',
    '_definite_unit_phrase',
    '_item_field_text',
    '_natural_field_text',
    '_fmt_baht',
    '_pre_vat',
    '_amount_line',
    '_bill_count_line',
    '_bill_values',
    '_token_diff',
    '_note_blocks',
    '_summary_sentence',
    '_group_by_vendor',
    '_company_field',
]
