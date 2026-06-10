# -*- coding: utf-8 -*-
"""super_ultra_viewer.py — ประกอบบล็อกสรุป "ต่อบริษัท × เดือน" ที่ก็อปวางได้เลย

ใช้ 10 viewers (viewers.py) ตัดสินแต่ละช่อง แล้วเรนเดอร์เป็นบล็อกตามฟอร์แมตที่ผู้ใช้ต้องการ:

    31. ซัน เหอ พลาสติก   เดือน 5/69
    ยอด : 5,990,004.06 บาท   ตรง
    บิล : 18 บิล   ตรง
    ชื่อบจ. : ตรง
    ...
    บริษัท ซัน เหอ พลาสติก จำกัด  05/69  ตรงครับ ✅

ออก 2 ไฟล์:
  • company_summary.txt  — บล็อกทุกบริษัท (ก็อปวางทีละบริษัทได้)
  • company_summary.xlsx — ตารางต่อบริษัท (1 แถว/บริษัท×เดือน) + ช่องสถานะ

ใช้:
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
      python3 super_ultra_viewer.py [DATA_DIR] [OUT_DIR]
advisory ล้วน — ไม่แตะ engine/ผลตรวจ/golden hash.
"""
import warnings; warnings.filterwarnings("ignore")
import os
import sys
import glob
import io
import re
import contextlib
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_labels import (FIELD_ORDER, F_NAME, F_ADDR, F_TAX, F_DATE, F_IV, F_ITEM,
                         F_PREVAT, F_POSTVAT,
                         field_of, lane_of, label_of, clean_detail, action_for,
                         NOTE, note_phrase, addr_summary, field_summary)
from viewers import VIEWERS
from puopuy_dates import _ivp_year2_to_ce, _ivp_year4_to_ce   # เดางวดจากเลขที่เอกสารเมื่อบิลไม่มีวันที่
import report_precision as _precision   # [Precision Council] ตัดสิน tier ต่อจุด (advisory → golden ไม่ขยับ)


# รหัส issue ที่ "ตัดออกจากสรุปลูกค้า (.txt)" — เป็นชั้นรายงานเท่านั้น ไม่กระทบ engine/golden
#   ITM015 = ใช้หน่วยปนกันในชุดเดียวกัน (เช่น หิน 3/4 คิว/ตัน) — ไม่ใช่ error ของบิล → ตัดทิ้ง
#   ITM018 = จำนวน=0 แต่มียอด — มักมาจากคอลัมน์ qty อ่านไม่ติด → ตัดทิ้ง
#   ITM016 = รายการซ้ำในบิล — ลูกค้าบอกว่าไม่เป็นไร ไม่ต้องขึ้น .txt "แต่ Excel ยังขึ้นเหมือนเดิม"
_HIDE_IN_SUMMARY = {"ITM015", "ITM018", "ITM016"}
_XLSX_ONLY = {"ITM016"}      # ไม่ขึ้น .txt แต่ยังเก็บลง Excel worklist


def _short_name(name: str) -> str:
    """ตัด 'บริษัท ' หน้า และ ' จำกัด' ท้าย → ชื่อสั้นสำหรับหัวบล็อก."""
    s = (name or "ไม่ทราบชื่อ").strip()
    for p in ("บริษัท ", "บจก. ", "บจก.", "ห้างหุ้นส่วนจำกัด ", "หจก. ", "หจก."):
        if s.startswith(p):
            s = s[len(p):]
            break
    for suf in (" จำกัด (มหาชน)", " จำกัด", " มหาชน"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    return s.strip() or "ไม่ทราบชื่อ"


def _period_from_iv(iv_number):
    """เดา (ปีพ.ศ. 2 หลัก, เดือน) จาก 'งวดที่ฝังในเลขที่เอกสาร' เช่น IV6905000850 → (69, 5).
    ใช้ตอนบิลอ่านวันที่ไม่ได้ — เลขที่เอกสารบอกเดือนอยู่แล้ว ไม่ต้องโยนไป 'ไม่ทราบเดือน'.
    คืน None เมื่ออ่านงวดไม่ชัด (กันเดามั่ว). ตรรกะตรงกับ detect_iv_period_mismatch."""
    if not iv_number:
        return None
    s = re.sub(r'[^0-9A-Za-z]', '', str(iv_number)).upper()
    m = re.match(r'^[A-Z]*(\d+)', s)
    if not m:
        return None
    lead = m.group(1)
    cy = mo = None
    if len(lead) >= 6:                       # ปี 4 หลัก + เดือน (เช่น 256805 / 202505)
        _cy, _ = _ivp_year4_to_ce(int(lead[:4])); _mo = int(lead[4:6])
        if _cy is not None and 1 <= _mo <= 12:
            cy, mo = _cy, _mo
    if cy is None and len(lead) >= 4:        # ปี 2 หลัก + เดือน (เช่น 6905 / 2505)
        _cy, _ = _ivp_year2_to_ce(int(lead[:2])); _mo = int(lead[2:4])
        if _cy is not None and 1 <= _mo <= 12:
            cy, mo = _cy, _mo
    if cy is None:
        return None
    be2 = ((cy + 543) if cy < 2500 else cy) % 100
    return be2, mo


def _month_label(dt, bill=None):
    if not dt:
        # ไม่มีวันที่ในบิล → ลองอ่านเดือนจาก 'เลขที่เอกสาร' (งวดฝังในเลข) ก่อนยอมแพ้เป็น 'ไม่ทราบเดือน'
        if bill is not None:
            p = _period_from_iv(bill.get("iv_number") or bill.get("iv_number_raw"))
            if p:
                be2, mo = p
                return f"{mo}/{be2:02d}", f"{mo:02d}/{be2:02d}"
        return "ไม่ทราบเดือน", "??/??"
    # [A3-FIX] กันปีที่เป็น พ.ศ. อยู่แล้ว (>2500) ถูก +543 ซ้ำ → label/คีย์กลุ่มเพี้ยน.
    #   ปกติ iv_date ถูก normalize เป็น ค.ศ. แล้ว → ผลเท่าเดิม (2026→69); guard นี้แค่กันเคสหลุด.
    be = dt.year + 543 if dt.year < 2500 else dt.year
    be2 = be % 100
    return f"{dt.month}/{be2:02d}", f"{dt.month:02d}/{be2:02d}"


# ── [v9.2 งาน D] บรรทัด "หมายเหตุ :" — ยกข้อสังเกตเลน NOTE (ลงวันที่ล่วงหน้า/เดือนไม่ตรงไฟล์) ──
def _file_prefix(fname: str) -> str:
    """ดึงรหัสผู้ขายหน้าไฟล์ (ตัวอักษรนำ) เช่น 'TSH 69.05.xls' → 'TSH'."""
    import re as _re
    m = _re.match(r"\s*([A-Za-z]+)", os.path.basename(fname or ""))
    return m.group(1).upper() if m else ""


def _fmt_dates(dates, cap=4) -> str:
    """รวมวันที่แบบสั้น (ตัดซ้ำแล้ว) ไม่เกิน cap ตัว; เกินบอก 'เป็นต้น'."""
    if not dates:
        return ""
    s = ", ".join(dates[:cap])
    if len(dates) > cap:
        s += " เป็นต้น"
    return s


def _note_line(code: str, rec: dict, ml2: str) -> str:
    """ประกอบข้อความหมายเหตุ 1 บรรทัด (อักษรพื้นฐาน ไม่มี emoji) จากรหัสเลน NOTE."""
    pre = "/".join(sorted(rec["prefixes"])) or "?"
    dates = _fmt_dates(rec["dates"])
    if code == "DT002":                       # ลงวันที่ล่วงหน้า — ระบุเดือนเอกสาร + วันที่
        s = f"ไฟล์ {pre} มีเอกสารเดือน {ml2} ลงวันที่ล่วงหน้า"
        return s + (f" วันที่ {dates}" if dates else "")
    if code == "DT001":                       # วันที่ในบิลไม่ตรงงวดที่ชื่อไฟล์ระบุ (เช่นไฟล์งวด 12 แต่บิลเดือนอื่น)
        s = f"ไฟล์ {pre} มีเอกสารลงวันที่ไม่ตรงงวดที่ชื่อไฟล์ระบุ"
        return s + (f" (วันที่ {dates})" if dates else "")
    s = f"ไฟล์ {pre} {note_phrase(code)}"
    return s + (f" (วันที่ {dates})" if dates else "")


def _norm_company(s: str) -> str:
    """normalize ชื่อบริษัทเป็น fallback group key (กันชื่อพิมพ์ต่างเล็กน้อย → split):
    รวบช่องว่างซ้ำ + ตัด 'จำกัด' ที่พิมพ์ซ้ำท้าย. ใช้ต่อเมื่อไม่มีเลขภาษี (เลขภาษีเป็น key หลัก)."""
    import re as _re
    s = _re.sub(r"\s+", " ", (s or "").strip())
    s = _re.sub(r"(\s*จำกัด)\s*จำกัด\s*$", r"\1", s)   # '... จำกัด จำกัด' → '... จำกัด'
    return s


def build(bills, master_present=True):
    from collections import Counter
    # ★ [FIX-CONSOLIDATE] จัดกลุ่มด้วย (เลขภาษี, เดือน) — เลขภาษี = canonical identity ของบริษัท
    #   กัน "บริษัทเดียว เดือนเดียว" ถูกแยกเป็นหลายบล็อกเพราะชื่อพิมพ์ต่าง ('จำกัด' เกิน/ขาด,
    #   เว้นวรรคไม่ตรง). ไม่มีเลขภาษี → fallback ชื่อ normalize. ชื่อที่โชว์ = ที่พบบ่อยสุดในกลุ่ม.
    groups = defaultdict(list)
    for b in bills:
        ml, _ = _month_label(b.get("iv_date"), b)
        tid = (b.get("tax_id") or "").strip()
        comp0 = b.get("company") or b.get("company_raw") or "ไม่ทราบชื่อ"
        groups[(tid or _norm_company(comp0), ml)].append(b)

    rows = []
    for _gkey, gbills in groups.items():
        ml = _gkey[1]
        comp = Counter(
            (b.get("company") or b.get("company_raw") or "ไม่ทราบชื่อ") for b in gbills
        ).most_common(1)[0][0]
        # ยอด/บิล
        total_sum = sum(float(b.get("total") or 0) for b in gbills)
        # [L3] subtotal==0 (จริง) ไม่ควรตกไป fallback — เดิมใช้ `or` ทำให้ 0 ถูกแทนด้วย total-vat
        prevat_sum = sum(
            (float(b["subtotal"]) if b.get("subtotal") is not None
             else (float(b.get("total") or 0) - float(b.get("vat") or 0)))
            for b in gbills)
        nbills = len(gbills)
        # รวม issue ทั้งกลุ่ม → (bill_key, issue)
        gi = []
        for b in gbills:
            bk = f"{b.get('file')}/{b.get('sheet')}"
            for i in b.get("issues", []):
                if i.get("code") in _HIDE_IN_SUMMARY:
                    continue
                gi.append((bk, i))
        # เดิน 10 viewers
        verdicts = {v.field: v.verdict(gi) for v in VIEWERS}
        # [v9.2 งาน A] ไม่มี master จริง → ช่องชื่อบจ./เลขภาษีที่ "ดูเหมือนตรง" ความจริงคือ "ตรวจไม่ได้".
        #   override เฉพาะช่องที่ยัง ok เท่านั้น — ห้ามกลบ error ที่ตรวจได้โดยไม่ต้องใช้ master
        #   (เช่น CMP005 ขาด 'จำกัด', TAX001 ไม่ครบ 13 หลัก) เพราะพวกนั้นยังต้องโชว์แม้ไม่มี master.
        if not master_present:
            for _f in (F_NAME, F_TAX):
                if verdicts[_f]["mark"] == "ok":
                    verdicts[_f]["status"] = "- ไม่มี master ตรวจไม่ได้"
                    verdicts[_f]["mark"] = "master"
        fix_fields = [f for f in FIELD_ORDER if verdicts[f]["mark"] == "fix"]
        check_fields = [f for f in FIELD_ORDER if verdicts[f]["mark"] == "check"]
        master_fields = [f for f in FIELD_ORDER if verdicts[f]["mark"] == "master"]
        clean = not fix_fields and not check_fields
        # รายการ "ต้องแก้รายบิล" — ระบุ ไฟล์/วันที่/ชีต/ลำดับที่/ประเภท/แก้ยังไง (ให้บัญชีเปิดถูกจุด)
        _raw = []
        xlsx_only = []   # โชว์เฉพาะใน Excel worklist (เช่น ITM016 รายการซ้ำ) — ไม่ขึ้น .txt
        for b in gbills:
            dt = b.get("iv_date")
            dts = dt.strftime("%d/%m/%Y") if dt else "?"
            for i in b.get("issues", []):
                code = i.get("code", "")
                ln = lane_of(code)
                if ln not in ("fix", "check"):
                    continue
                sm = re.match(r"\s*#(\d+)", i.get("detail", ""))
                _seq = sm.group(1) if sm else ""
                _iname = ""; _unit = ""
                if _seq.isdigit():
                    _items = b.get("items", []) or []
                    _ix = int(_seq) - 1
                    if 0 <= _ix < len(_items):
                        _iname = _items[_ix].get("name", "") or ""
                        _unit = _items[_ix].get("unit", "") or ""
                _entry = {
                    "file": b.get("file", ""), "sheet": str(b.get("sheet", "")),
                    "prefix": _file_prefix(b.get("file", "")),
                    "iv": b.get("iv_number", "") or "",
                    "iv_raw": b.get("iv_number_raw", "") or "",
                    "date": dts, "seq": _seq,
                    "item_name": _iname, "unit": _unit,
                    "field": field_of(code), "type": label_of(code),
                    "detail": clean_detail(code, i.get("detail", "")),
                    "action": action_for(field_of(code)),
                    "lane": ln, "code": code,
                }
                if code in _XLSX_ONLY:        # ITM016: Excel เท่านั้น
                    xlsx_only.append(_entry)
                elif code in _HIDE_IN_SUMMARY:  # ITM015/018: ตัดทิ้งทั้งคู่
                    continue
                else:
                    _raw.append(_entry)
        # ยุบหลายรหัสที่ชี้ "จุด+ประเภทเดียวกัน" (เช่น ITM010+ITM011 typo เดียว) → 1 บรรทัด
        #   เลือก detail ที่ดีสุด (มี 'ของเดิม→ที่ควร'); ยกเป็น fix ถ้ามีตัวใด fix
        _merged = {}
        for x in _raw:
            key = (x["file"], x["sheet"], x["date"], x["seq"], x["field"], x["type"])
            keep = _merged.get(key)
            if keep is None:
                _merged[key] = x
            else:
                if ("→" in x["detail"]) and ("→" not in keep["detail"]):
                    x["lane"] = "fix" if "fix" in (keep["lane"], x["lane"]) else x["lane"]
                    _merged[key] = x
                elif "fix" in (keep["lane"], x["lane"]):
                    keep["lane"] = "fix"
        fixlist = list(_merged.values())
        # [UX] รหัสไปรษณีย์: ADDR001 + ADDR005 ฟ้องเรื่องเดียวกัน → เหลือ 1 จุด/บิล (ไม่ขึ้นซ้ำ 2 บรรทัด)
        #   เก็บอันที่ข้อมูลมากกว่า (มี 'ทะเบียน') ; อื่น ๆ คงเดิม
        _zip_seen, _dedup = {}, []
        for x in fixlist:
            is_zip = (x["field"] == F_ADDR
                      and "ไปรษณีย์" in (x.get("detail", "") + x.get("type", "")))
            if not is_zip:
                _dedup.append(x); continue
            k = (x["file"], x["sheet"], x["date"])
            prev = _zip_seen.get(k)
            if prev is None:
                _zip_seen[k] = x; _dedup.append(x)
            elif "ทะเบียน" in x.get("detail", "") and "ทะเบียน" not in prev.get("detail", ""):
                _dedup[_dedup.index(prev)] = x; _zip_seen[k] = x
        fixlist = _dedup
        _ford = {f: n for n, f in enumerate(FIELD_ORDER)}
        fixlist.sort(key=lambda x: (_ford.get(x["field"], 99), x["file"], x["date"],
                                    int(x["seq"]) if x["seq"].isdigit() else 0))
        # [Precision Council] ลงคะแนน 10 ผู้ตรวจต่อจุด → tier 'clear'(รีพอร์ตหลัก)/'soft'(ตรวจตาเพิ่ม).
        #   advisory ล้วน — ไม่แตะ b['issues']/verdict/golden. ติด x['tier'] ให้ render_block ใช้.
        _bl = {(b.get("file", ""), str(b.get("sheet", ""))): b for b in gbills}
        _precision.annotate_tiers(fixlist, bill_lookup=_bl, master_present=master_present)
        # [v9.2 งาน D] เก็บข้อสังเกตเลน NOTE (ลงวันที่ล่วงหน้า/เดือนไม่ตรงไฟล์) แยกจาก error ช่อง
        #   → ยกขึ้นบรรทัด "หมายเหตุ :" ท้ายบล็อก (ไม่ทำให้ช่องวันที่ขึ้นผิด/ไม่ตัดสถานะคลีน)
        _, ml2 = (_month_label(gbills[0].get("iv_date"), gbills[0]) if gbills else ("", ""))
        notes_acc = {}
        for b in gbills:
            dt = b.get("iv_date")
            # [A3-FIX] guard ปี พ.ศ. ซ้ำ (เหมือน _month_label) — ปกติ ค.ศ. → ผลเท่าเดิม
            _be2 = ((dt.year + 543 if dt.year < 2500 else dt.year) % 100) if dt else 0
            dnote = f"{dt.day:02d}.{dt.month:02d}.{_be2:02d}" if dt else ""
            fpre = _file_prefix(b.get("file", ""))
            for i in b.get("issues", []):
                code = i.get("code", "")
                if lane_of(code) == NOTE:
                    rec = notes_acc.setdefault(code, {"prefixes": set(), "dates": []})
                    if fpre:
                        rec["prefixes"].add(fpre)
                    if dnote and dnote not in rec["dates"]:
                        rec["dates"].append(dnote)
        notes = [_note_line(code, rec, ml2) for code, rec in sorted(notes_acc.items())]
        try: import unit_detection_ext as _uxe; notes.extend(_uxe.company_unit_notes(gbills))  # [ADD-ON v9.2] หมายเหตุหน่วยระดับบริษัท (ปนไทย+อังกฤษ/หน่วยขาด) — advisory อ่าน gbills เท่านั้น
        except Exception: pass
        rows.append({
            "company": comp, "short": _short_name(comp), "month": ml,
            "total": total_sum, "prevat": prevat_sum, "nbills": nbills,
            "verdicts": verdicts, "fix": fix_fields, "check": check_fields,
            "master": master_fields, "clean": clean, "fixlist": fixlist,
            "master_present": master_present, "notes": notes,
            "xlsx_only": xlsx_only,
        })
    # เรียง: ต้องแก้ก่อน (มี fix), แล้วควรตรวจ, แล้วคลีน → ในกลุ่มเรียงชื่อ
    rows.sort(key=lambda r: (0 if r["fix"] else (1 if r["check"] else 2), r["company"], r["month"]))
    return rows

def _pinpoint_field(field, entries):
    """ประกอบข้อความ "ระบุจุด" ของช่องที่ต้องรีเช็ค: ไฟล์/เลขที่เอกสาร/วันที่/ลำดับ/ชื่อ/หน่วย
    ตามฟอร์แมตที่ผู้ใช้ต้องการ (ให้บัญชี/ลูกน้องลูกค้าเปิดไปแก้ถูกจุดได้เลย)."""
    if field in (F_ADDR, F_TAX): return field_summary(field, entries)   # [v9.2] ที่อยู่/เลขภาษี: สรุปสั้น + นับบิล (กันดัมพ์ซ้ำ)
    parts = []
    for fx in entries:
        d = (fx.get("date") or "").replace("/", ".")
        # ตัดส่วนซ้ำ "| สินค้า: ..." + ข้อความเดา "(คาดว่า...)" ออกให้สั้น
        extra = (fx.get("detail") or fx.get("type") or "").split("| สินค้า")[0]
        extra = re.sub(r"\s*\(คาดว่า[^)]*\)", "", extra).strip()
        if field == F_ITEM:
            # [UX] core ไม่ใส่ prefix(ไฟล์) — จัดกลุ่มต่อไฟล์ตอนรวมบรรทัด (ไฟล์เดียว=", " ; คนละไฟล์=บรรทัดใหม่)
            seg = (f"วันที่ {d} รายการสินค้า ลำดับที่ {fx['seq']}" if fx.get("seq")
                   else f"วันที่ {d}")   # ปัญหาระดับลำดับ/ทั้งบิล → ไม่มี 'ลำดับที่ ?'
            # โชว์ "คำว่า{คำที่พิมพ์ผิดในบิล}" = คำในเครื่องหมายคำพูด "ตัวแรก"
            #   (รูปแบบ 'แก้ "ผิด" → "ถูก"' และ '"ผิด" น่าจะเป็น "ถูก"' → คำแรก = คำผิดที่อยู่ในบิล)
            #   เพื่อให้คนเห็นแล้วรู้ทันทีว่าพิมพ์ผิดตรงไหน + เปิดไปแก้ได้
            _e = extra.replace("\u201c", '"').replace("\u201d", '"')
            _q = re.findall(r'"([^"]+)"', _e)
            if fx.get("seq") and _q:
                seg += f" คำว่า{_q[0]}"
            elif extra:
                seg += f" {extra}"
        elif field == F_DATE and fx.get("code") in ("DT005", "DT006"):
            # บิลไม่มีวันที่ / วันที่ไม่มีจริง — ไม่โชว์ "วันที่ ?" ; บอกตรง ๆ
            seg = f"ไฟล์ {fx.get('prefix','')}"
            if fx.get("iv"):
                seg += f" เลขที่เอกสาร {fx['iv']}"
            seg += " " + (extra if (fx.get("code") == "DT006" and extra) else "ไม่มีวันที่ในบิล ต้องเติมวันที่")
        elif field == F_DATE:
            seg = f"ไฟล์ {fx.get('prefix','')}"
            if fx.get("iv"):
                seg += f" เลขที่เอกสาร {fx['iv']}"
            seg += f" วันที่ {d}"
            # DOC001: "ชื่อชีตระบุวันที่ X แต่ข้างในบิล...Y" → สั้น "แต่ ชื่อชีตระบุวันที่ X"
            # DT004: "...เลขที่เอกสาร ... ฝังงวด NN/MM ..." → สั้น "แต่เลขที่เอกสารฝังงวด NN/MM"
            _m = re.search(r"ชื่อชีตระบุวันที่\s*([0-9./]+)", extra)
            _m2 = re.search(r"ฝังงวด\s*([0-9/]+)", extra)
            if _m:
                seg += f" แต่ ชื่อชีตระบุวันที่ {_m.group(1)}"
            elif _m2:
                seg += f" แต่เลขที่เอกสารฝังงวด {_m2.group(1)}"
            elif extra:
                seg += f" ({extra})"
        else:
            seg = f"ไฟล์ {fx.get('prefix','')}"
            if fx.get("code") == "IV002":
                # อักขระแปลกในเลขเอกสาร → สั้น+ภาษาคน: โชว์เลขเอกสารดิบ ให้เปิดไปดูเอง
                _raw = fx.get("iv_raw") or fx.get("iv") or ""
                seg += f" วันที่ {d} เลขที่เอกสาร {_raw}"
            else:
                if fx.get("iv"):
                    seg += f" เลขที่เอกสาร {fx['iv']}"
                seg += f" วันที่ {d}"
                if extra:
                    seg += f" {extra}"
        parts.append(re.sub(r" {2,}", " ", seg).strip())

    if field == F_ITEM:
        # จัดกลุ่มต่อไฟล์ (entries เรียงตาม file แล้วใน build): prefix โชว์ครั้งเดียวต่อไฟล์ ;
        #   หลายคำผิดไฟล์เดียวกัน = ", " บรรทัดเดียว ; คนละไฟล์ = ขึ้นบรรทัดใหม่ (อ่านแล้วรู้ว่าอีกไฟล์)
        lines, cur, _cur_pre = [], [], object()
        for fx, core in zip(entries, parts):
            pre = fx.get("prefix", "")
            if pre != _cur_pre:
                if cur:
                    lines.append(", ".join(cur))
                cur, _cur_pre = [], pre
                core = f"{pre} {core}" if pre else core
            cur.append(core)
        if cur:
            lines.append(", ".join(cur))
        return "\n".join(lines) + " รีเช็คครับ"

    return ", ".join(parts) + " รีเช็คครับ"


def render_block(n, r):
    from collections import defaultdict as _dd
    # เดือน: หัวบล็อกใช้ 'BE.MM' (เช่น 69.05), บรรทัดท้ายใช้ 'M/BE' (เช่น 5/69) ตามฟอร์แมตผู้ใช้
    _mp = r["month"].split("/")
    hdr_month = f"{_mp[1]}.{int(_mp[0]):02d}" if len(_mp) == 2 and _mp[0].isdigit() else r["month"]
    # [UX] ท้ายบล็อกใช้เดือนแบบ pad ศูนย์ '05/69' (ตาม docstring/ฟอร์แมตผู้ใช้) — เดิมหลุดเป็น '5/69'
    foot_month = f"{int(_mp[0]):02d}/{_mp[1]}" if len(_mp) == 2 and _mp[0].isdigit() else r["month"]

    by_field = _dd(list)
    for fx in r.get("fixlist", []):
        by_field[fx["field"]].append(fx)

    out = [f"{n}.{r['short']} {hdr_month}"]
    # ★ ยอด = ก่อน VAT เสมอ (แม้บางบิลเก็บยอดรวม VAT มาผิด — prevat คำนวณจาก subtotal/total-vat)
    amt = float(r.get("prevat") or 0)
    amt_s = f"{amt:,.0f}" if amt.is_integer() else f"{amt:,.2f}"
    out.append(f"ยอด : {amt_s} บาท ตรง")
    out.append(f"บิล : {r['nbills']} บิล ตรง")
    # [Precision Council 2 ชั้น] แยกจุดเป็น clear(รีพอร์ตหลัก)/soft(ตรวจตาเพิ่ม) ต่อช่อง
    clear_bf, soft_bf = _dd(list), _dd(list)
    for f, items in by_field.items():
        for e in items:
            (soft_bf if e.get("tier") == "soft" else clear_bf)[f].append(e)

    for f in FIELD_ORDER:
        if f in (F_PREVAT, F_POSTVAT):
            continue
        if f in clear_bf:                              # มีจุด 'ชัด' → ขึ้นรีพอร์ตหลัก
            out.append(f"{f} : {_pinpoint_field(f, clear_bf[f])}")
        elif f in by_field:                            # มีแต่ 'ก้ำกึ่ง' → ช่องหลักขึ้น 'ตรง' (ยกไปตรวจตาเพิ่ม)
            out.append(f"{f} : ตรง")
        else:
            out.append(f"{f} : {r['verdicts'][f]['status']}")
    out.append(f"ยอดหลัง Vat : {r['verdicts'][F_POSTVAT]['status']}")
    out.append(f"ยอดก่อน vat : {r['verdicts'][F_PREVAT]['status']}")
    # หมายเหตุ (ข้อสังเกตเลน NOTE) — ก่อนบรรทัดสรุปท้าย
    for note in r.get("notes", []):
        out.append(f"หมายเหตุ : {note}")
    # ชั้นที่ 2 — "ตรวจตาเพิ่ม" (จุดที่ council ยังไม่ยืนยันชัด ; ไม่ทิ้ง ไม่ซ่อน ขอตาคนยืนยัน)
    n_soft = 0
    for f in FIELD_ORDER:
        if f in soft_bf:
            n_soft += len(soft_bf[f])
            _soft = _pinpoint_field(f, soft_bf[f]).rsplit(" รีเช็คครับ", 1)[0]
            out.append(f"ตรวจตาเพิ่ม ({f}) : {_soft} — ก้ำกึ่ง ขอตาคนยืนยันครับ")
    # ★ บรรทัดสรุปท้าย — ใช้ปัญหาจาก verdict เดิม แต่ "ตัดช่องที่เหลือเฉพาะ soft" ออก (ยกไปตรวจตาเพิ่ม)
    #   → soft-only = ตรงสำหรับลูกค้า + มีจุดให้ตรวจตา ; ช่องที่ยังมีจุด 'ชัด' (หรือ verdict ที่ไม่มีใน worklist) คงเดิม
    soft_only_fields = {f for f in by_field if f not in clear_bf}
    footer_problems = [f for f in (r["fix"] + r["check"]) if f not in soft_only_fields]
    if not footer_problems:
        if r.get("master_present", True):
            base = f"{r['company']} {foot_month} ตรงครับ"
        else:
            base = f"{r['company']} {foot_month} ตรงเท่าที่ตรวจได้ (ไม่มี master เทียบชื่อ/เลขภาษี)"
        if n_soft:
            base += f" (มี {n_soft} จุดให้ตรวจตาเพิ่ม)"
        out.append(base)
    else:
        out.append(f"{r['company']} {foot_month} รีเช็ค{'/'.join(footer_problems)}ครับ ที่เหลือตรงครับผม")
    return "\n".join(out)


def write_txt(rows, path):
    from datetime import datetime
    nfix = sum(1 for r in rows if r["fix"])
    ncheck = sum(1 for r in rows if r["check"] and not r["fix"])
    nclean = sum(1 for r in rows if r["clean"])
    n_items = sum(len(r.get("fixlist", [])) for r in rows)

    L = []
    # หัวสั้น ๆ ภาษาคน ไม่มีเส้นคั่น/อักษรพิเศษ
    L.append("สรุปตรวจใบกำกับภาษี แยกต่อบริษัท (พร้อมส่งบัญชี)")
    L.append(f"รวม {len(rows)} บริษัท/เดือน  ตรง {nclean}  ต้องรีเช็ค {nfix + ncheck}")

    # 1 บริษัท×เดือน = 1 บล็อก คั่นด้วยบรรทัดว่าง (ไม่มีเส้น ─/=)
    n = 0
    for r in rows:
        n += 1
        L.append("")
        L.append(render_block(n, r))

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def write_xlsx(rows, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    wb = Workbook(); ws = wb.active; ws.title = "สรุปบริษัท"
    HF = PatternFill("solid", fgColor="1E40AF"); HFONT = Font(name="Arial", color="FFFFFF", bold=True)
    THIN = Side(style="thin", color="D1D5DB"); BD = Border(THIN, THIN, THIN, THIN)
    cols = ["#", "บริษัท", "เดือน", "ยอด (บาท)", "บิล"] + FIELD_ORDER + ["สรุป"]
    widths = [4, 30, 8, 16, 6] + [16] * len(FIELD_ORDER) + [40]
    for ci, (h, w) in enumerate(zip(cols, widths), 1):
        c = ws.cell(1, ci, h); c.fill = HF; c.font = HFONT; c.border = BD
        c.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        ws.column_dimensions[c.column_letter].width = w
    GREEN = PatternFill("solid", fgColor="DCFCE7"); RED = PatternFill("solid", fgColor="FEE2E2")
    YEL = PatternFill("solid", fgColor="FEF9C3"); GRAY = PatternFill("solid", fgColor="F3F4F6")
    for ri, r in enumerate(rows, 2):
        vals = [ri - 1, r["company"], r["month"], round(r["prevat"], 2), r["nbills"]]
        vals += [r["verdicts"][f]["status"] for f in FIELD_ORDER]
        summ = ("ตรงทั้งหมด ✅" if r["clean"]
                else f"ต้องตรวจ: {', '.join(r['fix'] + r['check'])}")
        if r.get("notes"):
            summ += "  | หมายเหตุ: " + " ; ".join(r["notes"])
        vals.append(summ)
        for ci, v in enumerate(vals, 1):
            c = ws.cell(ri, ci, v); c.font = Font(name="Arial", size=10)
            c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = BD
        for ci, f in enumerate(FIELD_ORDER, 6):
            m = r["verdicts"][f]["mark"]
            ws.cell(ri, ci).fill = (RED if m == "fix" else YEL if m == "check"
                                    else GRAY if m == "master" else GREEN)
        ws.cell(ri, len(cols)).fill = GREEN if r["clean"] else RED
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = f"A1:{ws.cell(1, len(cols)).column_letter}{len(rows)+1}"

    # ── ชีต 2: "ต้องแก้ รายบิล" — worklist บัญชี (ไฟล์/วันที่/ชีต/ลำดับ/แก้ยังไง) ──
    ws2 = wb.create_sheet("ต้องแก้ รายบิล")
    wcols = ["#", "ไฟล์", "วันที่", "ชีต", "ลำดับที่", "บริษัท", "ช่อง",
             "ประเภทปัญหา", "รายละเอียด / แก้ยังไง", "คำแนะนำ"]
    wwid = [4, 22, 12, 7, 9, 26, 16, 22, 46, 40]
    for ci, (h, w) in enumerate(zip(wcols, wwid), 1):
        c = ws2.cell(1, ci, h); c.fill = HF; c.font = HFONT; c.border = BD
        c.alignment = Alignment(horizontal="center", wrap_text=True, vertical="center")
        ws2.column_dimensions[c.column_letter].width = w
    wr = 2
    for r in rows:
        # fixlist (ขึ้นทั้ง .txt + Excel) + xlsx_only (เช่น ITM016 รายการซ้ำ — Excel เท่านั้น)
        for x in list(r.get("fixlist", [])) + list(r.get("xlsx_only", [])):
            seq = f"#{x['seq']}" if x["seq"] else "ทั้งบิล"
            vals = [wr - 1, x["file"], x["date"], x["sheet"], seq, r["company"],
                    x["field"], x["type"], x["detail"], x["action"]]
            for ci, v in enumerate(vals, 1):
                c = ws2.cell(wr, ci, v); c.font = Font(name="Arial", size=10)
                c.alignment = Alignment(wrap_text=True, vertical="top"); c.border = BD
            ws2.cell(wr, 8).fill = RED if x["lane"] == "fix" else YEL
            wr += 1
    ws2.freeze_panes = "A2"
    if wr > 2:
        ws2.auto_filter.ref = f"A1:{ws2.cell(1, len(wcols)).column_letter}{wr-1}"

    # ── ชีต 3: วิธีอ่าน (legend) ──
    ws3 = wb.create_sheet("วิธีอ่าน")
    ws3.column_dimensions["A"].width = 22; ws3.column_dimensions["B"].width = 70
    legend = [
        ("สี / สถานะ", "ความหมาย"),
        ("เขียว / ตรง", "ผ่าน ไม่มีปัญหา - พร้อมส่งบัญชี"),
        ("แดง", "ต้องแก้ก่อนส่ง (ช่องจะมีข้อความบอกปัญหา; ดูชีต 'ต้องแก้ รายบิล' ว่าแก้บิลไหน)"),
        ("เหลือง", "ควรตรวจด้วยตา (อาจไม่ผิด เช่น ราคา/หน่วยแปลก)"),
        ("เทา / ไม่มี master", "ไม่มีข้อมูล ภ.พ.20 มาเทียบ - ตรวจชื่อ/เลขภาษีเองไม่ได้"),
        ("หมายเหตุ", "ข้อสังเกต เช่น ลงวันที่ล่วงหน้า/เดือนไม่ตรงไฟล์ (ไม่ใช่ข้อผิดพลาดของช่อง)"),
        ("", ""),
        ("ชีต", "เนื้อหา"),
        ("สรุปบริษัท", "1 แถว/บริษัท×เดือน - ภาพรวมแต่ละช่อง"),
        ("ต้องแก้ รายบิล", "ทุกจุดที่ต้องแก้ - ระบุไฟล์/วันที่/ชีต/ลำดับ + แก้ยังไง"),
    ]
    for ri, (a, b) in enumerate(legend, 1):
        ca = ws3.cell(ri, 1, a); cb = ws3.cell(ri, 2, b)
        bold = ri == 1 or a in ("ชีต",)
        ca.font = Font(name="Arial", size=10, bold=bold); cb.font = Font(name="Arial", size=10, bold=bold)
        ca.alignment = Alignment(wrap_text=True, vertical="top")
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        if ri == 1 or a == "ชีต":
            ca.fill = HF; cb.fill = HF; ca.font = HFONT; cb.font = HFONT

    wb.save(path)


def emit_for_bills(bills, outdir, master_present=True):
    """ออกไฟล์สรุปจากบิลที่ parse แล้ว (ใช้ซ้ำหน่วยความจำ — ไม่ parse ใหม่). คืน (txt, xlsx).

    master_present: มี master จริงหรือไม่ — ถ้าไม่มี ช่องชื่อบจ./เลขภาษีจะขึ้น "ไม่มี master ตรวจไม่ได้".
    """
    rows = build(bills, master_present=master_present)
    os.makedirs(outdir, exist_ok=True)
    txt = os.path.join(outdir, "company_summary.txt")
    xlsx = os.path.join(outdir, "company_summary.xlsx")
    write_txt(rows, txt)
    write_xlsx(rows, xlsx)
    return txt, xlsx, rows


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    data = sys.argv[1] if len(sys.argv) > 1 else "/mnt/project"
    outdir = sys.argv[2] if len(sys.argv) > 2 else "/mnt/user-data/outputs"
    if not os.path.isdir(data):
        data = os.path.join("tests", "fixtures")
    from golden_snapshot import MASTER
    import importlib
    app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
    fl = sorted(glob.glob(os.path.join(data, "*.xls")) + glob.glob(os.path.join(data, "*.xlsx")))
    with contextlib.redirect_stdout(io.StringIO()):
        app.reset_run_state()
        bills, fi = app.parse_all_files(fl)
        for b in bills:
            app.compute_bill_confidence(b)
        app.run_audit_core(bills, MASTER, isolate=True)
    # หมายเหตุ: demo นี้ตรวจด้วยชุดทดสอบ (golden_snapshot.MASTER 1 บริษัท) ซึ่งไม่ใช่ master จริงของ
    #   บริษัทใน /mnt/project → ส่ง master_present=False ให้ช่องชื่อบจ./เลขภาษีขึ้น "ไม่มี master" ตามจริง
    #   (ไม่ขึ้น "ตรง" หลอก). บนเครื่องผู้ใช้ที่ใส่ master จริงแล้ว main() จะส่ง master_present=True.
    txt, xlsx, rows = emit_for_bills(bills, outdir, master_present=False)
    nfix = sum(1 for r in rows if r["fix"]); ncheck = sum(1 for r in rows if r["check"] and not r["fix"])
    nclean = sum(1 for r in rows if r["clean"])
    print(f"✅ {len(rows)} บริษัท×เดือน → ต้องแก้ {nfix} / ควรตรวจ {ncheck} / ตรง {nclean}")
    print(f"   {txt}")
    print(f"   {xlsx}")
    prob = next((r for r in rows if r["fix"]), None)
    clean = next((r for r in rows if r["clean"]), None)
    print("\n----- ตัวอย่างบล็อก (มีปัญหา) -----")
    if prob:
        print(render_block(1, prob))
    print("\n----- ตัวอย่างบล็อก (ตรง) -----")
    if clean:
        print(render_block(2, clean))


if __name__ == "__main__":
    main()
