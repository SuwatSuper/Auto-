# -*- coding: utf-8 -*-
"""validators.py — cross-bill & sequence validators for ปุ้มปุ้ย 03 (module split pass 3).

Extracted VERBATIM. NO logic changed. IV sequence checks (_iv_check_*), invoice/date
sequence, product-typo detection, IV-period cross-checks (DT004/DOC001). These keep
their bill-mutation side-effects (IV003/IV004) exactly as before.

Imports a small parser/util surface from main (defined before ).
"""
import re
from collections import defaultdict, Counter
from rapidfuzz import fuzz
from config import CFG  # [F3] explicit (เดิม import *)
# [P-DAG พาส3a] นำเข้า dependency จาก "โมดูลต้นทางจริง" (leaf) แทนการวิ่งกลับ main
#   → ตัด circular dependency validators -> main (เดิมต้องพึ่งลำดับ import ภายใน main)
#   ปลอดภัยกว่าเดิม: import ได้แม้ validators ถูกโหลดเดี่ยว ๆ (parser/puopuy/* ไม่พึ่ง main)
from parser import _declared_period_from_filename
from puopuy_dates import _ivp_year2_to_ce, _ivp_year4_to_ce
from puopuy_core import clean_tax_id, normalize_text
from diagnostics import log_system_issue


# ============================================================
# 🔁 IDEMPOTENT APPEND (ADR-017) — cross-check ที่มี side-effect ต้อง "ปลอดภัยเมื่อเรียกซ้ำ"
#   เดิม cross-check (IV003/IV004/DT004/DOC001) append issue ลงบิลตรง ๆ → เรียกซ้ำ = ซ้ำ =
#   golden hash เพี้ยน (เคยตรึงด้วยวินัย "เรียกครั้งเดียว" + เทส tripwire). ตัวช่วยนี้ทำให้
#   "idempotent โดยโครงสร้าง": เติมเฉพาะ issue ที่ยังไม่มี (เทียบทั้ง dict).
#
#   byte-identical: เส้น golden เรียก cross-check ครั้งเดียว → ตอน append ไม่มี issue ตัวเดิมอยู่ก่อน
#   → เติมครบเหมือนเดิมทุกตัว (hash ไม่ขยับ — พิสูจน์ด้วย 269ddaed/f1ac8421/fff69fc6).
#   ไม่ชนกับ issue ของ \"กฎ\" ที่ใช้ code เดียวกัน (DT004/DOC001): name/detail ต่างกันเชิงโครงสร้าง
#   → dict ไม่มีทางเท่ากัน → ตัวช่วยนี้จึงดับเฉพาะ \"การ apply ซ้ำของ cross-check เดียวกัน\" เท่านั้น.
# ============================================================
def _append_issue_unique(b, issue):
    """เติม issue ลง b['issues'] เฉพาะเมื่อยังไม่มี dict ที่เท่ากันเป๊ะ (idempotent)."""
    bucket = b.setdefault('issues', [])
    if issue not in bucket:
        bucket.append(issue)



# ============================================================
# 🔍 CROSS-BILL
# ============================================================
# ============================================================
# 🔢 IV SEQUENCE SUB-CHECKS (decomposed from check_invoice_sequence, slice 3C)
#   logic/regex/severity เดิมทุกอย่าง — แยกเป็นฟังก์ชันชื่อชัด, คืน list[issue].
#   _iv_check_cross_day / _iv_check_ascending ยังคง side-effect เติม b['issues'] (IV003/IV004) เหมือนเดิม.
# ============================================================
def _iv_check_month_consistency(clean_bills):
    """[FIX-XBILL-MONTH] เดือนของบิล vs เสียงข้างมากในไฟล์ (ก๊อปชีตลืมแก้เดือน). คืน issues."""
    issues = []
    # === v5.9 [FIX-XBILL-MONTH]: ความสอดคล้องของ "เดือน" ภายในไฟล์เดียวกัน ===
    #   เคสก๊อปชีตแล้วลืมแก้เดือน: ชีตตั้งชื่อตามวัน (เช่น "6") → วันตรง แต่เดือนในบิลผิด
    #   การเทียบ sheet-vs-day เดิมจับไม่ได้ (เทียบแค่วัน) → เพิ่มเทียบเดือนกับเสียงข้างมากในไฟล์
    month_groups = defaultdict(list)
    for b in clean_bills:
        if not b.get('iv_date'):
            continue
        vendor = clean_tax_id(b.get('tax_id', '')) or normalize_text(b.get('company', '')).upper()
        month_groups[(b.get('file', ''), vendor)].append(b)
    for (file_key, vendor), grp in month_groups.items():
        if len(grp) < 3:
            continue   # ข้อมูลน้อยเกิน ตัดสินเสียงข้างมากไม่ได้
        yr_mo = [(b['iv_date'].year, b['iv_date'].month) for b in grp]
        common_ym, common_cnt = Counter(yr_mo).most_common(1)[0]
        if common_cnt < len(grp) * 0.6:
            continue   # ไม่มีเดือนหลักชัดเจน (อาจเป็นไฟล์คร่อมเดือนจริง) → ข้าม
        # v8.5 [FIX-XMONTH]: ถ้าชื่อไฟล์ "ประกาศช่วงเดือน" ชัดเจน (เช่น 69.03-04)
        #   → บิลที่เดือนอยู่ในช่วงที่ประกาศ ถือว่า "ถูกต้องตามไฟล์" ไม่ใช่ก๊อปลืมแก้ → ไม่ฟ้อง
        #   (ไฟล์เดือนเดียว/ชื่อไม่ระบุช่วง → declared_months=None → พฤติกรรมเดิมทุกประการ)
        decl_year, declared_months = _declared_period_from_filename(file_key)
        for b in grp:
            ym = (b['iv_date'].year, b['iv_date'].month)
            if ym != common_ym:
                # อยู่ในช่วงเดือนที่ชื่อไฟล์ประกาศไว้ (และปีตรง/ปีไม่ระบุ) → legit cross-month → ข้าม
                if declared_months and b['iv_date'].month in declared_months:
                    _bill_be = b['iv_date'].year + 543 if b['iv_date'].year < 2500 else b['iv_date'].year
                    if (decl_year is None) or (_bill_be == decl_year):
                        continue
                issues.append({
                    'type': 'บิลคนละเดือนกับไฟล์ (น่าจะก๊อปชีตลืมแก้วันที่)',
                    'severity': 'CRITICAL',
                    'iv': (b.get('iv_number_raw') or b.get('iv_number') or '-'),
                    'detail': f"[{file_key}/ชีต{b.get('sheet', '')}] "
                              f"บิลนี้ลงวันที่ {b['iv_date'].strftime('%d/%m/%Y')} (เดือน {ym[1]:02d}) "
                              f"แต่บิลส่วนใหญ่ในไฟล์เป็นเดือน {common_ym[1]:02d}/{common_ym[0]} "
                              f"({common_cnt}/{len(grp)} ใบ) — ตรวจว่าก๊อปชีตแล้วลืมแก้วันที่หรือไม่"
                })
    return issues


def _iv_check_sheet_day(clean_bills):
    """[Cross-check] sheet-day vs iv_date.day. คืน (issues, consistent_bills) — consistent_bills
    คือชุดบิลที่ผ่าน sheet-check แล้ว ใช้ต่อใน sequence-check (logic เดิม 100%)."""
    issues = []
    consistent_bills = []
    for b in clean_bills:
        # ไม่มี iv_date → ข้าม cross-check แต่ยังเข้า sequence ได้ถ้ามี IV
        if not b.get('iv_date'):
            if b.get('iv_number'): consistent_bills.append(b)
            continue

        # sheet ที่เป็นตัวเลข → ตีความเป็น day, ต้องตรงกับ iv_date.day
        sheet_raw = str(b.get('sheet','')).strip().lstrip('0').split('#')[0]
        if sheet_raw.isdigit():
            sheet_day = int(sheet_raw)
            if sheet_day != b['iv_date'].day:
                issues.append({'type':'IV วันที่ไม่สอดคล้อง','severity':'CRITICAL',
                              'iv':b.get('iv_number','-'),
                              'detail':f"[{b.get('file','')}/{b.get('sheet','')}] "
                                       f"sheet={sheet_day} vs iv_date.day={b['iv_date'].day} "
                                       f"(iv_date={b['iv_date'].strftime('%d/%m/%Y')})"})
                continue
        # sheet ไม่ใช่ตัวเลข (เช่น 'Sheet1','สรุป') → ข้าม sheet-check แต่เข้า sequence ได้
        if b.get('iv_number'):
            consistent_bills.append(b)
    return issues, consistent_bills


def _iv_check_sequence(consistent_bills):
    """[SEQ] group by (vendor, iv_date) — ตรวจซ้ำ/ถอยหลังภายในวันเดียวกัน. คืน issues."""
    issues = []
    # === Sequence check: group by (vendor, iv_date) ===
    groups = defaultdict(list)
    for b in consistent_bills:
        if not b.get('iv_date'): continue
        # ใช้ trailing digits ทั้งก้อนเป็น seq (ไม่แยก day/running)
        m_seq = re.search(r'(\d+)$', str(b['iv_number']))
        if not m_seq: continue

        vendor = clean_tax_id(b.get('tax_id','')) or normalize_text(b.get('company','')).upper()
        date_key = b['iv_date'].strftime('%Y-%m-%d')
        file_key = b.get('file','')
        groups[(file_key, vendor, date_key)].append({
            '_bill': b,
            '_seq': int(m_seq.group(1)),
            '_seq_len': len(m_seq.group(1)),   # [BUGFIX recheck #1] ความยาวสตริงดิบ (ก่อน int — กันศูนย์นำหาย)
            '_raw_iv': str(b['iv_number']),
        })

    for (file_key, vendor, date_key), group in groups.items():
        # v5.8L: IV กลุ่มยาวไม่เท่ากัน=format ต่าง→ไม่เทียบ. [BUGFIX recheck #1] ใช้ _seq_len สตริงดิบ (กัน '0100'/'0099'→3/2 หลัก ข้ามทั้งกลุ่ม)
        if len(set(e['_seq_len'] for e in group)) > 1:
            continue
        # 1) ตรวจซ้ำ (ไม่ขึ้นกับ order)
        seen = {}
        for entry in group:
            s = entry['_seq']
            if s in seen:
                # [P2-FIX-CONTEXT] เติม [file] ต้น detail — คนตรวจหาไฟล์เจอทันที (เดิมมีแต่ vendor/วันที่)
                issues.append({'type':'IV ซ้ำเลขท้าย','severity':'CRITICAL',
                              'iv':entry['_raw_iv'],
                              'detail':f"[{file_key}] vendor={vendor[:20]} วันที่={date_key} "
                                       f"— seq {s} ซ้ำกับ {seen[s]['_raw_iv']}"})
            else:
                seen[s] = entry

        # 2) ตรวจถอยหลัง (gap = ยอมรับได้, ไม่ flag)
        prev = None
        for entry in group:
            s = entry['_seq']
            if prev is not None and s < prev['_seq']:
                # [P2-FIX-CONTEXT] เติม [file] ต้น detail
                issues.append({'type':'IV ถอยหลัง','severity':'CRITICAL',
                              'iv':entry['_raw_iv'],
                              'detail':f"[{file_key}] vendor={vendor[:20]} วันที่={date_key} "
                                       f"— seq {s} < ก่อนหน้า {prev['_seq']} ({prev['_raw_iv']})"})
            prev = entry
    return issues


def _iv_check_cross_day(clean_bills):
    """[XBILL-DAY] เลขที่เดียวกันโผล่หลายวัน (IV003). side-effect: เติม b['issues']. คืน issues."""
    issues = []
    # === v5.9 [XBILL-DAY]: เลขที่เอกสารข้ามวัน (group by file+vendor+IV, คนละวัน) ===
    #   ใช้ clean_bills (ผ่าน source-dedup แล้ว) ไม่พึ่ง cross-check วันที่
    #   ข้ามบิลที่เป็น "รวมบิลข้ามหน้า" (มี _merged_pages) เพราะนั่นคือบิลเดียวที่ถูกยุบแล้ว
    iv_groups = defaultdict(list)
    for b in clean_bills:
        if not b.get('iv_number') or not b.get('iv_date'):
            continue
        if b.get('_merged_pages'):
            continue
        vendor = clean_tax_id(b.get('tax_id','')) or normalize_text(b.get('company','')).upper()
        iv_groups[(b.get('file',''), vendor, str(b['iv_number']).strip())].append(b)

    for (file_key, vendor, iv_no), grp in iv_groups.items():
        days = sorted(set(b['iv_date'].strftime('%d/%m/%Y') for b in grp))
        # (A) เลขที่เดียวกันโผล่หลายวัน = น่าจะลืมเปลี่ยนเลขเอกสาร
        if len(days) > 1:
            _detail = (f"[{file_key}] vendor={vendor[:20]} — เลขที่ {iv_no} "
                       f"ใช้ซ้ำใน {len(days)} วัน: {', '.join(days)} "
                       f"(น่าจะลืมเปลี่ยนเลขเอกสารตอนเปิดบิลใหม่)")
            issues.append({
                'type':'เลขที่เอกสารซ้ำข้ามวัน','severity':'CRITICAL',
                'iv':iv_no, 'detail':_detail})
            # ผูก issue เข้าบิลทุกใบในกลุ่ม → โผล่ใน Error Report/High Risk (โหมดคลีน)
            for b in grp:
                _append_issue_unique(b, {
                    'code':'IV003','severity':'CRITICAL','category':'เอกสาร',
                    'name':'เลขที่เอกสารซ้ำข้ามวัน',
                    'detail':f"เลขที่ {iv_no} ใช้ซ้ำใน {len(days)} วัน: {', '.join(days)} "
                             f"(น่าจะลืมเปลี่ยนเลขเอกสารตอนเปิดบิลใหม่)"})
    return issues


def _iv_check_ascending(clean_bills):
    """[XBILL-ASC] เลขท้ายต้องไม่ลดลงตามวัน (IV004). side-effect: เติม b['issues']. คืน issues."""
    issues = []
    # === v5.9 [XBILL-ASC]: เลขที่เอกสารไม่ไล่เรียงตามวัน (วันหลัง เลขต้องมากกว่าวันก่อน) ===
    #   group by file+vendor → เรียงตามวันที่ → เลขท้าย (trailing digits) ต้องไม่ลดลง
    asc_groups = defaultdict(list)
    for b in clean_bills:
        if not b.get('iv_number') or not b.get('iv_date'):
            continue
        if b.get('_merged_pages'):
            continue
        m_seq = re.search(r'(\d+)$', str(b['iv_number']))
        if not m_seq:
            continue
        vendor = clean_tax_id(b.get('tax_id','')) or normalize_text(b.get('company','')).upper()
        asc_groups[(b.get('file',''), vendor)].append(   # [BUGFIX recheck #1] +rawlen สตริงดิบใน tuple
            (b['iv_date'], int(m_seq.group(1)), str(b['iv_number']).strip(), b, len(m_seq.group(1))))

    for (file_key, vendor), entries in asc_groups.items():
        # ความยาวเลขท้ายต้องเท่ากัน — [BUGFIX recheck #1] ใช้ rawlen (สตริงดิบ) ไม่ใช่ len(str(int))
        if len({rawlen for *_, rawlen in entries}) > 1: continue
        entries.sort(key=lambda x: x[0])
        if len(entries) < 2:
            continue
        prev_d, prev_n, prev_iv, _prev_b, _ = entries[0]
        for d, n, iv, b, _ in entries[1:]:
            if d > prev_d and n < prev_n:
                _detail = (f"[{file_key}] vendor={vendor[:20]} — "
                           f"วันที่ {prev_d.strftime('%d/%m')} เลข {prev_n} "
                           f"แต่วันที่ {d.strftime('%d/%m')} เลข {n} (ลดลง ไม่ไล่ตามวัน)")
                issues.append({
                    'type':'เลขที่เอกสารไม่ไล่ตามวัน','severity':'WARNING',
                    'iv':f"{prev_iv} → {iv}", 'detail':_detail})
                # ผูก issue เข้าบิลใบที่เลขถอยหลัง → โผล่ใน Error Report (โหมดคลีน)
                _append_issue_unique(b, {
                    'code':'IV004','severity':'WARNING','category':'เอกสาร',
                    'name':'เลขที่เอกสารไม่ไล่ตามวัน',
                    'detail':f"วันก่อนหน้า {prev_d.strftime('%d/%m')} เลข {prev_n} ({prev_iv}) "
                             f"แต่ใบนี้ {d.strftime('%d/%m')} เลข {n} (เลขลดลง ไม่ไล่ตามวัน)"})
            prev_d, prev_n, prev_iv, _prev_b = d, n, iv, b
    return issues


def check_invoice_sequence(bills):
    """v5.8i: Flexible IV format — orchestrator (decomposed, slice 3C).
    ลำดับการตรวจ + ผลลัพธ์ (issues) เหมือนเดิม 100%:
      dedup → month-consistency → sheet-day(+build consistent) → sequence → cross-day → ascending.
    """
    issues = []

    # === Source dedup: กัน artifact จาก parse ซ้ำ (file,sheet,block) ===
    processed_sources = set()
    clean_bills = []
    for b in bills:
        src_key = (b.get('file',''), b.get('sheet',''), b.get('block_idx',0))
        if src_key in processed_sources: continue
        processed_sources.add(src_key)
        clean_bills.append(b)

    # ลำดับเดิม: month → sheet-day → sequence → cross-day → ascending
    issues += _iv_check_month_consistency(clean_bills)
    _sheet_issues, consistent_bills = _iv_check_sheet_day(clean_bills)
    issues += _sheet_issues
    issues += _iv_check_sequence(consistent_bills)
    issues += _iv_check_cross_day(clean_bills)
    issues += _iv_check_ascending(clean_bills)
    return issues


def check_iv_date_sequence(bills):
    """v5.8r: ตรวจ IV↔Date ถอยหลัง — เทียบ running เฉพาะภายในเดือนเดียวกัน
    running ส่วนใหญ่รีเซ็ตรายเดือน (เช่น CB-6904-0800 / CB-6905-0392)
    → เทียบข้ามเดือนไม่ได้ → group ด้วย (ไฟล์, ปี, เดือน) ของ iv_date
    """
    issues = []
    # group by (file, ปี, เดือน) — เทียบเฉพาะบิลในเดือนเดียวกัน
    by_group = defaultdict(list)
    for b in bills:
        if not b.get('iv_number') or not b.get('iv_date'): continue   # [BUGFIX recheck] .get() กัน KeyError
        digits = re.sub(r'[^\d]','',b['iv_number'])
        last_num = None
        if len(digits) >= 4:
            last_num = int(digits[-4:]) if len(digits) >= 8 else int(digits)
        if last_num is not None:
            month_key = (b['file'], b['iv_date'].year, b['iv_date'].month)
            by_group[month_key].append((b['iv_date'], last_num, b, len(digits)))   # [BUGFIX recheck #8] +จำนวนหลักดิบ
    for (file, yr, mo), entries in by_group.items():
        entries.sort(key=lambda x: x[0])
        if len(entries) < 2: continue
        if len({dl for *_, dl in entries}) > 1: continue   # [BUGFIX recheck #8] IV คนละจำนวนหลัก=คนละ format→ไม่เทียบ
        # guard: ในเดือนเดียวกันยังถอยบ่อย (>25%) = format แปลก → ข้าม
        nums = [n for _, n, _, _ in entries]
        backward = sum(1 for i in range(len(nums)-1) if nums[i] > nums[i+1])
        total_pairs = len(nums) - 1
        if total_pairs >= 3 and backward / total_pairs > 0.25:
            continue
        pd_, pn, pb, _ = entries[0]
        for d, n, b, _ in entries[1:]:
            if d > pd_ and n < pn:
                issues.append({'type':'IV↔Date ถอยหลัง','severity':'WARNING',
                              'iv':f"{pb['iv_number']} ↔ {b['iv_number']}",
                              'detail':f"[{file}] วันที่ {pd_.strftime('%d/%m')} IV={pn} | วันที่ {d.strftime('%d/%m')} IV={n}"})
            pd_, pn, pb = d, n, b
    return issues


def detect_iv_period_mismatch(iv_number, iv_date):
    """ตรวจว่า "งวดที่ฝังในเลขที่เอกสาร" ตรงกับวันที่ในบิลหรือไม่ (กันก๊อปชีตลืมแก้วันที่)

    คืน dict {'mismatch', 'iv_period', 'doc_period', 'basis'} เมื่ออ่านงวดจากเลขได้แน่ชัด
    คืน None เมื่ออ่านงวดไม่ได้ (→ ไม่ฟันธง ไม่ flag — ปลอดภัยกว่าการเดา)

    ลำดับการตีความ (เลือกอันแรกที่เข้าโครง): ปี4หลัก+เดือน → ปี2หลัก+เดือน → ปี4หลักอย่างเดียว
    """
    if not iv_number or not iv_date:
        return None
    s = re.sub(r'[^0-9A-Za-z]', '', str(iv_number)).upper()
    m = re.match(r'^[A-Z]*(\d+)', s)        # เลขชุดแรกหลังตัวอักษรนำ (ถ้ามี)
    if not m:
        return None
    lead = m.group(1)

    # งวดของบิล (แปลงเป็น ค.ศ. เพื่อเทียบฐานเดียวกัน)
    yr = iv_date.year
    doc_ce = yr - 543 if yr >= 2500 else yr
    doc_mm = iv_date.month

    cy = mo = basis = None
    # (a) ปี 4 หลัก + เดือน  (เช่น 202511 / 256811)
    if len(lead) >= 6:
        _cy, _basis = _ivp_year4_to_ce(int(lead[:4]))
        _mo = int(lead[4:6])
        if _cy is not None and 1 <= _mo <= 12:
            cy, mo, basis = _cy, _mo, _basis
    # (b) ปี 2 หลัก + เดือน  (เช่น 6811 / 2511 / 6904)
    if cy is None and len(lead) >= 4:
        _cy, _basis = _ivp_year2_to_ce(int(lead[:2]))
        _mo = int(lead[2:4])
        if _cy is not None and 1 <= _mo <= 12:
            cy, mo, basis = _cy, _mo, _basis
    # (c) ปี 4 หลักอย่างเดียว ไม่มีเดือน  (เช่น INV-2025-001)
    if cy is None and len(lead) >= 4:
        _cy, _basis = _ivp_year4_to_ce(int(lead[:4]))
        if _cy is not None:
            cy, mo, basis = _cy, None, _basis

    if cy is None:
        return None        # อ่านงวดจากเลขไม่ได้แบบมั่นใจ → ไม่ฟันธง

    mismatch = (cy != doc_ce) or (mo is not None and mo != doc_mm)

    # แสดงงวดทั้งสองฝั่งในฐานปีเดียวกับเลขเอกสาร (อ่านเทียบกันง่าย)
    iv_yr  = cy + 543 if basis == 'พ.ศ.' else cy
    doc_yr = doc_ce + 543 if basis == 'พ.ศ.' else doc_ce
    if mo is None:
        iv_period  = f"ปี {iv_yr}"
        doc_period = f"ปี {doc_yr}"
    else:
        iv_period  = f"{iv_yr % 100:02d}/{mo:02d}"
        doc_period = f"{doc_yr % 100:02d}/{doc_mm:02d}"
    return {'mismatch': mismatch, 'iv_period': iv_period,
            'doc_period': doc_period, 'basis': basis}


def check_product_typos(bills):
    names = set()
    for b in bills:
        for it in b['items']: names.add(it['name'])
    # [P0-FIX-DETERMINISM] tie-break ด้วยชื่อ (len, name) — กันผล typo สลับลำดับข้ามรอบ
    #   เดิม key=len อย่างเดียว: ชื่อยาวเท่ากันมี tie ที่ขึ้นกับ PYTHONHASHSEED (set iteration order)
    #   → รัน 2 ครั้งได้ลำดับ typo ต่างกัน ผิดสเปก "decisions must be repeatable in the records"
    #   เพิ่ม secondary key เป็นชื่อ → total order → deterministic 100% (เนื้อหา typo เท่าเดิมทุกคู่)
    nl = sorted(names, key=lambda s: (len(s), s))
    if len(nl) < 2: return []

    # v5.8 FIX: cap จำนวนชื่อ — กัน Colab หมดแรม/ค้างเงียบเมื่อรายการเยอะมาก
    # (cross-check ทั้งหมดเป็น O(n²) — ไฟล์ใหญ่หลายพันรายการจะทำ kernel ตาย)
    # v6.2: ย้ายค่า cap เข้า CFG (ค่าเริ่มต้น 3000 = พฤติกรรมเดิมเป๊ะ) และเปลี่ยน
    #       การ "ข้ามเงียบ" → log SYS002 ให้เห็น (กันรายงาน typo สะอาดลวงตา)
    # [P2-NOTE] อัลกอริทึม >500 ชื่อใช้ sliding-window (ลด O(n²) ลงแล้วบางส่วน ดูด้านล่าง)
    #   ถ้าชนเพดานบ่อย: เพิ่มไฟล์เป็นชุดย่อย (batch แยก) แล้วรวมรายงาน หรือปรับ CFG['MAX_TYPO_NAMES']
    #   ขึ้น — แต่ระวังเวลา/แรมโตแบบกำลังสอง (3000→1.5s, 5000→4s, 10000→อาจค้าง)
    MAX_TYPO_NAMES = int(CFG.get('MAX_TYPO_NAMES', 3000))
    if len(nl) > MAX_TYPO_NAMES:
        print(f'   ⚠️ ITM typo cross-check: ชื่อสินค้า unique {len(nl):,} ตัว '
              f'เกิน {MAX_TYPO_NAMES:,} — ข้ามการตรวจ typo ข้ามบิล (กันหมดแรม)')
        print(f'      💡 ทางออก: แบ่งไฟล์เป็นชุดย่อยแล้วรันทีละชุด หรือเพิ่ม '
              f'CFG["MAX_TYPO_NAMES"] (ระวังเวลา/แรมโตแบบกำลังสอง)')
        log_system_issue('SYS002', 'Typo Cross-Check Skipped',
                         f'ชื่อสินค้า unique {len(nl):,} เกินเพดาน {MAX_TYPO_NAMES:,} '
                         f'→ ข้ามการตรวจคำสะกดข้ามบิล (ปรับ CFG["MAX_TYPO_NAMES"] หรือแบ่ง batch)',
                         severity='WARNING', category='SYSTEM', echo=False)
        return []

    threshold = CFG['FUZZY_PRODUCT_THRESHOLD']
    typos = []
    seen_pairs = set()

    # v6.2 CPU: precompute number/spec sets ครั้งเดียวต่อชื่อ (เดิมรัน regex ซ้ำทุกคู่)
    #   ผลลัพธ์ "เหมือนเดิมเป๊ะ" — แค่ไม่ทำ regex ซ้ำบนชื่อเดิม ๆ ที่อยู่ในหลายคู่
    _spec_cache = {}
    def _spec_of(name):
        cached = _spec_cache.get(name)
        if cached is None:
            cached = (
                frozenset(re.findall(r'\d+(?:\.\d+)?', name)),
                frozenset(re.findall(r"\d+['\"x×]\d+", name)),
            )
            _spec_cache[name] = cached
        return cached

    def _is_spec_diff(a, b):
        na, sa = _spec_of(a)
        nb, sb = _spec_of(b)
        if na != nb: return True
        if sa != sb: return True
        return False

    try:
        from rapidfuzz import process
        if len(nl) <= 500:
            matrix = process.cdist(nl, nl, scorer=fuzz.ratio, score_cutoff=threshold)
            for i in range(len(nl)):
                for j in range(i+1, len(nl)):
                    score = matrix[i][j]
                    if not (threshold <= score < 100): continue
                    if _is_spec_diff(nl[i], nl[j]): continue
                    typos.append({'name1':nl[i],'name2':nl[j],'score':int(score)})
        else:
            for i, n1 in enumerate(nl):
                lo = max(0, int(len(n1) * 0.8))
                hi = int(len(n1) * 1.25) + 1
                start = i + 1
                while start < len(nl) and len(nl[start]) < lo: start += 1
                window = []
                for j in range(start, len(nl)):
                    if len(nl[j]) > hi: break
                    window.append(nl[j])
                if not window: continue
                matches = process.extract(n1, window, scorer=fuzz.ratio,
                                         score_cutoff=threshold, limit=5)
                for matched_name, score, _ in matches:
                    if score >= 100: continue
                    if _is_spec_diff(n1, matched_name): continue
                    pair = tuple(sorted([n1, matched_name]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        typos.append({'name1':pair[0],'name2':pair[1],'score':int(score)})
    except Exception as _e:
        print(f'⚠️ [product typo] primary path พลาด ใช้ fallback: {_e}')  # v5.9 FIX-1
        for i, n1 in enumerate(nl):
            for n2 in nl[i+1:]:
                if abs(len(n1) - len(n2)) > max(len(n1), len(n2)) * 0.3: continue
                score = fuzz.ratio(n1, n2)
                if not (threshold <= score < 100): continue
                if _is_spec_diff(n1, n2): continue
                typos.append({'name1':n1,'name2':n2,'score':int(score)})
    return typos


# ============================================================
# 🔗 CROSS-CHECKS (extracted from main, slice 2) — behavior 100% เดิม
#   logic/regex/เงื่อนไข ไม่เปลี่ยน; ย้ายออกมาเป็นฟังก์ชันชื่อชัด (seam ของชั้น validators)
# ============================================================
def apply_iv_period_crosscheck(all_bills):
    """[PATCH 1] DT004 — วันที่ในบิล vs งวดที่ฝังในเลขที่เอกสาร (Cross-Check).
    ย้ายจาก main() ตรง ๆ ไม่แก้ logic: detect_iv_period_mismatch() อ่านงวดจากเลขได้แน่ชัดจึงเทียบ.
    มี side-effect: เติม b['issues'] ใน place (เหมือนเดิม)."""
    for b in all_bills:
        if not b.get('iv_date') or not b.get('iv_number'): continue
        _ivp = detect_iv_period_mismatch(b['iv_number'], b['iv_date'])
        if _ivp and _ivp['mismatch']:
            _append_issue_unique(b, {
                'code': 'DT004', 'severity': 'ERROR', 'category': 'วันที่',
                'name': 'วันที่ขัดแย้งกับเลข IV',
                'detail': f"วันที่ในบิลเป็นงวด {_ivp['doc_period']} ({_ivp['basis']}) "
                          f"แต่เลขที่เอกสาร ({(b.get('iv_number_raw') or b.get('iv_number') or '-')}) "
                          f"ฝังงวด {_ivp['iv_period']} — ตรวจว่าก๊อปชีตแล้วลืมแก้วันที่หรือไม่"
            })


def apply_sheet_date_crosscheck(all_bills):
    """[PATCH 2] DOC001 — วันที่ในบิล vs ชื่อชีต (Day/Month Mismatch).
    ย้ายจาก main() ตรง ๆ ไม่แก้ logic/regex. มี side-effect: เติม b['issues'] ใน place."""
    for b in all_bills:
        if not b.get('iv_date') or not b.get('sheet'): continue
        # v5.9 FIX-6: ลบ import re ออกจากลูป (re ถูก import ไว้ที่บรรทัด 44 แล้ว)
        sheet_match = re.search(r'^(\d{1,2})\.(\d{1,2})', str(b['sheet']).strip())
        if sheet_match:
            sh_dd = int(sheet_match.group(1))
            sh_mm = int(sheet_match.group(2))
            doc_dd = b['iv_date'].day
            doc_mm = b['iv_date'].month
            if sh_dd != doc_dd or sh_mm != doc_mm:
                _append_issue_unique(b, {
                    'code': 'DOC001', 'severity': 'ERROR', 'category': 'เอกสาร',
                    'name': 'วันที่ไม่ตรงกับชื่อชีต',
                    'detail': f"ชื่อชีตระบุวันที่ {sh_dd:02d}/{sh_mm:02d} แต่ข้างในบิลระบุเป็นวันที่ {doc_dd:02d}/{doc_mm:02d} (คาดว่าก๊อปปี้ชีตแล้วลืมแก้วันที่)"
                })


def apply_missing_date_check(all_bills):
    """[DT005] บิลที่อ่านวันที่ไม่ได้/ไม่มีวันที่ = เอกสารไม่สมบูรณ์ → ฟ้องให้เติมวันที่.
    หมายเหตุ: เดือนถูกเดาจาก 'เลขที่เอกสาร' เพื่อจัดกลุ่มงวดแล้ว แต่ 'ตัววันที่' ในบิลยังหายอยู่
    จึงต้องเตือนคนตรวจ (ไม่ใช่ปล่อยผ่านเงียบ). side-effect: เติม b['issues'] (idempotent)."""
    for b in all_bills:
        if b.get('iv_date') or b.get('_bad_date'):   # _bad_date → ให้ DT006 จัดการ (เฉพาะเจาะจงกว่า)
            continue
        # บิลจริงเท่านั้น (มีเลขเอกสาร/รายการ/ยอด) — กันบิลเงา/ว่างถูกฟ้อง
        if not (b.get('iv_number') or b.get('items') or b.get('total')):
            continue
        _append_issue_unique(b, {
            'code': 'DT005', 'severity': 'ERROR', 'category': 'วันที่',
            'name': 'บิลไม่มีวันที่',
            'detail': 'อ่านวันที่ในบิลไม่ได้ (ไม่มีวันที่) — ต้องเติมวันที่ให้ครบ'
        })


def apply_abbrev_invoice_check(all_bills):
    """[IV006] ใบกำกับภาษี 'อย่างย่อ' → เครมภาษีซื้อไม่ได้ ต้องคัดออก (พบคำว่า 'อย่างย่อ' ในเอกสาร)."""
    for b in all_bills:
        if not b.get('_abbrev'):
            continue
        _append_issue_unique(b, {
            'code': 'IV006', 'severity': 'ERROR', 'category': 'เลขที่ IV',
            'name': 'ใบกำกับภาษีอย่างย่อ',
            'detail': 'เป็นใบกำกับภาษีอย่างย่อ เครมภาษีซื้อไม่ได้ ต้องใช้ใบกำกับเต็มรูป'
        })


def apply_bad_date_check(all_bills):
    """[DT006] วันที่ 'หน้าตาเป็นวันที่ แต่ไม่มีจริงในปฏิทิน' (31/04, 30/02) → parse ไม่ได้ เก็บที่ _bad_date → ฟ้องแก้."""
    for b in all_bills:
        bad = b.get('_bad_date')
        if not bad or b.get('iv_date'):
            continue
        _append_issue_unique(b, {
            'code': 'DT006', 'severity': 'ERROR', 'category': 'วันที่',
            'name': 'วันที่ไม่ถูกต้อง',
            'detail': f'วันที่ {bad} ไม่มีจริงในปฏิทิน ต้องแก้วันที่'
        })


def apply_missing_iv_check(all_bills):
    """[IV005] บิลที่มีรายการ/ยอด แต่ไม่มี 'เลขที่ใบกำกับ' = เอกสารไม่สมบูรณ์ → ฟ้องให้เติม.
    ใบกำกับภาษีต้องมีเลขที่เสมอ. side-effect: เติม b['issues'] (idempotent). คู่กับ DT005."""
    for b in all_bills:
        if (b.get('iv_number') or '').strip():
            continue
        # บิลจริงเท่านั้น (มีรายการ/ยอด) — กันบิลเงา/ว่างถูกฟ้อง
        if not (b.get('items') or b.get('total') or b.get('subtotal')):
            continue
        _append_issue_unique(b, {
            'code': 'IV005', 'severity': 'ERROR', 'category': 'เลขที่ IV',
            'name': 'บิลไม่มีเลขที่ใบกำกับ',
            'detail': 'อ่านเลขที่ใบกำกับไม่ได้ (ไม่มีเลขที่) — ต้องเติมเลขที่ใบกำกับ'
        })


# ============================================================
# [P-DAG พาส3f] check_filename_consistency + check_duplicate_items (ย้ายมาจาก main, verbatim)
# ============================================================

def check_filename_consistency(filename, bills, file_info):
    issues = []
    if not bills: return issues
    dates = [b.get('iv_date') for b in bills if b.get('iv_date')]   # [BUGFIX recheck] .get() กัน KeyError
    if not dates: return issues
    last_day = max(d.day for d in dates)
    if file_info.get('day') and file_info['day'] != last_day:
        issues.append({'file':filename,'type':'ชื่อไฟล์↔บิลสุดท้าย',
                      'detail':f"ระบุ {file_info['day']:02d} แต่บิลสุดท้าย {last_day}"})
    return issues


def check_duplicate_items(all_bills):
    """v5.8q PATCH 4B: ตรวจรายการสินค้าซ้ำเป๊ะ"""
    seen = defaultdict(list)
    for b in all_bills:
        for it in b.get('items', []):
            amt = it.get('amount')
            key = (
                b.get('file',''), str(b.get('sheet','')),
                b.get('iv_number') or '-', it.get('name',''),
                round(float(amt), 2) if isinstance(amt,(int,float)) else None,
            )
            seen[key].append(it.get('seq'))
    dups = []
    for (file, sheet, iv, name, amount), seqs in seen.items():
        if len(seqs) < 2: continue
        dups.append({'ไฟล์':file,'ชีต':sheet,'IV':iv,'รายการ':name[:40],
                     'ยอด':amount,'พบซ้ำ':len(seqs),'ลำดับ':seqs})
    return dups
