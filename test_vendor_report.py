# -*- coding: utf-8 -*-
"""test_vendor_report.py — ตรึงฟอร์แมต "รายงานลูกค้ารายผู้ขาย (.txt)" + พฤติกรรม agent

ครอบ: จัดกลุ่มผู้ขาย · map กฎ→ช่อง (ตรง/ไม่ตรง) · ฟอร์แมตหัว-ท้าย-งวด · ชื่อไฟล์ ·
       ภาษาคน (ไม่มีโค้ดกฎหลุด) · agent เขียนไฟล์ UTF-8 · ADVISORY (ไม่แตะ bills).

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_vendor_report.py
"""

import os
import sys
import io
import re
import copy
import tempfile
import datetime
import contextlib
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
from agents.vendor_report import build_vendor_reports, _short_name, _match
from agents.vendor_report_agent import VendorReportAgent
from agents.contracts import PipelineContext

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


D = datetime.date(2026, 5, 10)


def bill(
    iv, total, issues=None, comp="บริษัท จินไท่ คอนสตรัคชั่น จำกัด", tax="0105556789012"
):
    return {
        "file": "F.xlsx",
        "sheet": "1",
        "iv_number": iv,
        "iv_date": D,
        "company": comp,
        "tax_id": tax,
        "subtotal": total / 1.07,
        "vat": total - total / 1.07,
        "total": total,
        "items": [{"name": "เหล็ก", "qty": 1, "price": total, "amount": total}],
        "issues": issues or [],
    }


print("=" * 64)
print("VENDOR REPORT — ตรึงฟอร์แมต .txt รายผู้ขาย")
print("=" * 64)

# vendor ใหญ่: 18 บิล, 1 บิลมี typo รายการสินค้า (ITM004) ; vendor เล็ก: 3 บิล ทุก field ตรง
big = [bill(f"IV{i:03d}", 148889.0) for i in range(17)]
big.append(
    bill(
        "IV099",
        207006.0,
        issues=[{"code": "ITM004", "severity": "INFO", "name": "คำสะกด"}],
    )
)
small = [
    bill(f"B{i}", 50000.0, comp="บริษัท สมหวัง จำกัด", tax="0107000000017")
    for i in range(3)
]
bills = big + small

before = copy.deepcopy([b["issues"] for b in bills])
reps = build_vendor_reports(bills)

# [1] จำนวนไฟล์ = จำนวน vendor
check(len(reps) == 2, f"สร้าง 1 ไฟล์/ผู้ขาย (ได้ {len(reps)} ไฟล์ จาก 2 ผู้ขาย)")

# [2] เรียงยอดมาก→น้อย: จินไท่ (ยอดรวมสูงกว่า) มาก่อน + ชื่อไฟล์ {ลำดับ}.{ชื่อย่อ}.txt
fname1, text1 = reps[0]
fname2, text2 = reps[1]
check(fname1.startswith("1.") and fname1.endswith(".txt"), f"ชื่อไฟล์ที่ 1 = {fname1}")
check(fname2.startswith("2.") and "สมหวัง" in fname2, f"ชื่อไฟล์ที่ 2 = {fname2}")
check("จินไท่" in fname1, "ผู้ขายยอดสูงสุด (จินไท่) มาลำดับ 1")

# [3] หัวรายงาน: '{ลำดับ}.{ชื่อย่อ} {งวด}'  (งวด = พ.ศ. 2 หลัก = 69.05)
lines = text1.splitlines()
check(lines[0].strip("─") == "" and lines[0].startswith("─"), "บรรทัดแรก = เส้นคั่น")
check(
    lines[1].startswith("1.จินไท่ คอนสตรัคชั่น") and "69.05" in lines[1],
    f"หัว: '{lines[1]}'",
)

# [4] ยอด + จำนวนบิล
check(
    any(l.startswith("ยอด : ") and "บาท" in l for l in lines),
    "มีบรรทัด 'ยอด : ... บาท'",
)
check(any(l.startswith("บิล : 18 บิล") for l in lines), "บรรทัด 'บิล : 18 บิล ...' ถูกต้อง")
# [4b] ยอด = ผลรวม 'ก่อน VAT' (subtotal) ไม่ใช่ total — ข้อกำหนดสำคัญจากผู้ใช้
_sub_sum = sum(b["subtotal"] for b in big)
_amount_line = next((l for l in lines if l.startswith("ยอด : ")), "")
check(
    f"{_sub_sum:,.0f}" in _amount_line or f"{_sub_sum:,.2f}" in _amount_line,
    f"ยอด = ผลรวมก่อน VAT ({_sub_sum:,.2f}) ไม่ใช่ total : '{_amount_line}'",
)

# [5] field map: vendor ใหญ่มี typo → 'รายการสินค้า' ไม่ตรง (ภาษาคน) ; ที่เหลือ 'ตรง'
need_fields = [
    "ชื่อบจ.",
    "ที่อยู่",
    "เลขที่ผู้เสียภาษี",
    "สาขา/สนญ.",
    "เลขที่",
    "วันที่",
    "เลขที่ iv",
    "รายการสินค้า",
    "ยอดหลัง Vat",
    "ยอดก่อน vat",
]
fields = {}
for l in lines:
    if " : " in l:
        k, v = l.split(" : ", 1)
        if k in need_fields:
            fields[k] = v
check(
    fields.get("รายการสินค้า", "") != "ตรง"
    and "รีเช็ค" in fields.get("รายการสินค้า", ""),
    f"รายการสินค้า (มี typo) = '{fields.get('รายการสินค้า')}'",
)
# [A1] ไม่มี master → ช่องตัวตน (เลขภาษี) = 'ตรวจไม่ได้' (เลิกขึ้น 'ตรง' หลอก) ;
#   ช่องที่ไม่พึ่ง master (ยอดหลัง Vat) ที่ไม่มี issue = ยัง 'ตรง'
check(
    "ตรวจไม่ได้" in fields.get("เลขที่ผู้เสียภาษี", "") and fields.get("ยอดหลัง Vat") == "ตรง",
    "no-master: เลขภาษี = 'ตรวจไม่ได้' ; ยอดหลัง Vat (ไม่พึ่ง master) = 'ตรง'",
)
# vendor เล็กสะอาด (ไม่มี master): ช่องที่ไม่พึ่ง master 'ตรง' ; ไม่มี 'ไม่ตรง'/'รีเช็ค' ;
#   ช่องตัวตน = 'ตรวจไม่ได้' (สถานะที่สาม) ; ท้าย = 'ตรงเท่าที่ตรวจได้'
check(
    "รายการสินค้า : ตรง" in text2 and "ไม่ตรง" not in text2 and "รีเช็ค" not in text2
    and "ตรวจไม่ได้" in text2 and "ตรงเท่าที่ตรวจได้" in text2,
    "ผู้ขายสะอาด ไม่มี master → ช่องไม่พึ่ง master 'ตรง' + ช่องตัวตน 'ตรวจไม่ได้' + ท้าย 'ตรงเท่าที่ตรวจได้'",
)

# [6] ครบ 10 ช่องตามผัง
check(all(f in fields for f in need_fields), "มีครบ 10 ช่องตามผัง")

# [7] บรรทัดท้าย = ชื่อเต็มบริษัท + งวด MM/YY
check(
    any(
        l.startswith("บริษัท จินไท่ คอนสตรัคชั่น จำกัด") and "5/69" in l for l in lines
    ),
    "บรรทัดท้าย = ชื่อเต็ม + งวด M/YY",
)

# [8] ภาษาคน: ไม่มีโค้ดกฎ (เช่น ITM004/VAT002) หลุดในไฟล์
# โค้ดกฎจริง (CMP/ADDR/TAX/.../VAT + 3 หลัก) ต้องไม่หลุด ; ยกเว้น IV/SEQ ที่เป็น "เลขข้อมูล" (เลขเอกสาร) ไม่ใช่โค้ดกฎ
check(
    not re.search(r"\b(?:CMP|ADDR|TAX|BR|DOC|DT|ITM|VAT|SYS|DUP|FN)\d{3}\b", text1),
    "ไม่มีโค้ดกฎหลุด (ภาษาคนล้วน)",
)

# [9] _match: prefix vs exact
check(
    _match("VAT002", ("VAT002",)) and not _match("VAT001", ("VAT002",)),
    "_match แบบตรงตัว (VAT002) ถูกต้อง",
)
check(
    _match("TAX003", ("TAX",)) and _match("ITM017", ("ITM",)),
    "_match แบบ prefix (TAX/ITM) ถูกต้อง",
)

# [10] _short_name ตัดคำนำหน้า + 'จำกัด'
check(
    _short_name("บริษัท จินไท่ คอนสตรัคชั่น จำกัด") == "จินไท่ คอนสตรัคชั่น",
    "_short_name ตัด 'บริษัท'/'จำกัด'",
)

# [11] AGENT: เขียนไฟล์จริง UTF-8 + ADVISORY (ไม่แตะ issues)
tmp = tempfile.mkdtemp(prefix="vendor_rep_")
ctx = PipelineContext(
    bills=bills,
    options={
        "write_vendor_report": True,
        "vendor_report_dir": tmp,
        "write_report": False,
    },
)
with contextlib.redirect_stdout(io.StringIO()):
    res = VendorReportAgent().run(ctx)
check(
    res.status == "ok" and (res.summary or {}).get("files_written") == 2,
    f"agent เขียน 2 ไฟล์ (ได้ {(res.summary or {}).get('files_written')})",
)
written = sorted(os.listdir(tmp))
check(
    len(written) == 2 and all(f.endswith(".txt") for f in written),
    f"ไฟล์ .txt ในโฟลเดอร์: {written}",
)
if written:
    body = open(os.path.join(tmp, written[0]), encoding="utf-8-sig").read()
    check("จินไท่" in body or "สมหวัง" in body, "อ่านไฟล์ UTF-8 ได้ (ภาษาไทยถูก)")
check(
    [b["issues"] for b in bills] == before,
    "ADVISORY — issues ทุกบิลไม่เปลี่ยนหลังรัน agent",
)

# [12] โหมดพิสูจน์: write_vendor_report=False → ไม่เขียนไฟล์
tmp2 = tempfile.mkdtemp(prefix="vendor_rep2_")
ctx2 = PipelineContext(
    bills=bills, options={"write_vendor_report": False, "vendor_report_dir": tmp2}
)
with contextlib.redirect_stdout(io.StringIO()):
    res2 = VendorReportAgent().run(ctx2)
check(
    res2.status == "ok"
    and (res2.summary or {}).get("files_written") == 0
    and os.listdir(tmp2) == [],
    "write_vendor_report=False → ไม่เขียนไฟล์ (โหมดพิสูจน์)",
)

# ── [13] ฟีเจอร์ใหม่ v9.2: หมายเหตุ master, สรุปท้ายภาษาคน, ก่อน VAT, จัดกลุ่มทนเลขภาษีผิด ──
_MAS = {
    "เอ เอ เอ": {
        "name": "บริษัท เอ เอ เอ จำกัด",
        "tax_id": "0105500000017",
        "branch": "สำนักงานใหญ่",
        "address": "เลขที่ 100 ถนนสุขุมวิท แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110",
    }
}


def _mk(iv, sub, issues=None, addr=_MAS["เอ เอ เอ"]["address"], tax="0105500000017"):
    return {
        "file": "AAA_69_05.xls",
        "sheet": "1",
        "iv_number": iv,
        "iv_date": D,
        "iv_date_str": "10/05/2026",
        "company": "บริษัท เอ เอ เอ จำกัด",
        "tax_id": tax,
        "branch": "สำนักงานใหญ่",
        "branch_no": "00000",
        "address": addr,
        "subtotal": sub,
        "vat": round(sub * 0.07, 2),
        "total": round(sub * 1.07, 2),
        "items": [{"seq": 1, "name": "เหล็ก", "qty": 1, "unit": "เส้น", "price": sub, "amount": sub}],
        "issues": issues or [],
    }


# IV001 เลขภาษีผิด + ที่อยู่ผิด ; IV002 สะอาด — ต้องรวมเป็น "ผู้ขายเดียว 2 บิล"
aaa = [
    _mk(
        "IV001",
        1000.0,
        addr="เลขที่ 999 ถนนพระราม 4 แขวงคลองเตย เขตคลองเตย กรุงเทพมหานคร 10110",
        tax="0105500000099",
        issues=[
            {"code": "ADDR001", "category": "ที่อยู่", "name": "ที่อยู่", "detail": "ที่อยู่ไม่ตรงทะเบียน"},
            {"code": "TAX003", "category": "เลขภาษี", "name": "เลขภาษี", "detail": "ในไฟล์ 0105500000099 | master 0105500000017"},
        ],
    ),
    _mk("IV002", 2000.0),
]
aaa_reps = build_vendor_reports(aaa, None, _MAS)
check(len(aaa_reps) == 1, f"ผู้ขายเดียว (เลขภาษีผิด 1 บิล) → รวม 1 รายงาน (ได้ {len(aaa_reps)})")
atext = aaa_reps[0][1]
check("ยอด : 3,000 บาท ตรง" in atext, "ยอดก่อน VAT รวม 2 บิล = 3,000 (ไม่ใช่ total)")
check(any(l.startswith("บิล : 2 บิล") for l in atext.splitlines()), "นับเป็น 2 บิล")
check("หมายเหตุ :" in atext, "มีบล็อก 'หมายเหตุ :' เมื่อ ที่อยู่/เลขภาษี ไม่ตรง")
check(
    "ที่อยู่ที่ถูกต้อง (Master data) :" in atext and "ที่อยู่ในบิล :" in atext and "จุดต่าง :" in atext,
    "หมายเหตุที่อยู่: master vs บิล + จุดต่าง ครบ",
)
check(
    "เลขที่ผู้เสียภาษีที่ถูกต้อง (Master data) : 0105500000017" in atext
    and "เลขที่ผู้เสียภาษีในบิล : 0105500000099" in atext,
    "หมายเหตุเลขภาษี: master vs บิล ครบ",
)
check(
    "รีเช็ค" in atext.splitlines()[-3] or any("รีเช็ค" in l and "นะครับผม" in l for l in atext.splitlines()),
    "สรุปท้ายภาษาคน: 'รีเช็ค ... นะครับผม'",
)
check("ตามหมายเหตุ" in atext, "สรุปท้ายอ้างถึง 'หมายเหตุ' เมื่อมีบล็อกหมายเหตุ")

# ผู้ขายสะอาดล้วน → สรุปท้าย 'ตรงครับ' ไม่มีบล็อกหมายเหตุ
clean_reps = build_vendor_reports([_mk("IV010", 500.0), _mk("IV011", 700.0)], None, _MAS)
ctext = clean_reps[0][1]
check(ctext.rstrip().splitlines()[-2].endswith("ตรงครับ"), "ผู้ขายสะอาด → สรุปท้าย 'ตรงครับ'")
check("หมายเหตุ :" not in ctext, "ผู้ขายสะอาด → ไม่มีบล็อกหมายเหตุ")

# determinism: รัน 2 ครั้งได้ผลเท่ากันเป๊ะ
check(
    build_vendor_reports(aaa, None, _MAS) == build_vendor_reports(aaa, None, _MAS),
    "build_vendor_reports deterministic (รันซ้ำผลเท่ากัน)",
)

# ── [14] ตัวกรอง noise: ตัด soft/เชิงรูปแบบ คงคำผิดจริง ──
from agents.vendor_report import _is_noise_issue

check(_is_noise_issue({"code": "ITM005", "detail": "หน่วย=ชิ้น อาจไม่เหมาะ [soft]"}), "ITM005 (เดาหน่วย) = noise")
check(_is_noise_issue({"code": "ITM004", "detail": "#1: ไทย+อังกฤษ ติดกัน (ควรเว้นวรรค)"}), "ITM004 เว้นวรรค = noise")
check(_is_noise_issue({"code": "ITM004", "detail": "#2: อักขระแปลก ['NBSP']"}), "ITM004 อักขระแปลก = noise")
check(not _is_noise_issue({"code": "ITM004", "detail": 'น่าจะเป็น "THAI UNION" (สะกดตก T)'}), "คำผิดจริง (THAI UNION) = ไม่ใช่ noise")
check(not _is_noise_issue({"code": "VAT001", "detail": "ผลรวมรายการ ≠ subtotal"}), "VAT001 (ยอดผิด) = ไม่ใช่ noise")
check(not _is_noise_issue({"code": "ITM004", "detail": "แกลลอน (ขาด ล)"}), "คำสะกดตก (ขาด ล) = ไม่ใช่ noise")

# รายงานที่มีทั้ง noise + คำผิดจริง → โชว์เฉพาะคำผิดจริง
mixed = [
    _mk(
        "IV200",
        100.0,
        issues=[
            {"code": "ITM005", "category": "รายการสินค้า", "name": "หน่วย", "detail": "#1 หน่วย=ชิ้น อาจไม่เหมาะ [soft]"},
            {"code": "ITM004", "category": "รายการสินค้า", "name": "คำสะกด", "detail": "#2: ไทย+อังกฤษ ติดกัน (ควรเว้นวรรค)"},
            {"code": "ITM004", "category": "รายการสินค้า", "name": "คำสะกด", "detail": '#3: น่าจะเป็น "THAI UNION" (สะกดตก T)'},
        ],
    )
]
mtext = build_vendor_reports(mixed, None, _MAS)[0][1]
check('THAI UNION' in mtext, "รายงาน mixed: คงคำผิดจริง (THAI UNION)")
check("อาจไม่เหมาะ" not in mtext and "ติดกัน" not in mtext, "รายงาน mixed: ตัด noise (หน่วย/เว้นวรรค) ออก")

# ── [15] หัวเป็นช่วงเดือน (ผู้ขายข้ามเดือน) + สรุปท้ายซอฟ ──
def _mkm(iv, sub, mo, day):
    dd = datetime.date(2026, mo, day)
    return {
        "file": "JRN_69_0%d.xls" % mo, "sheet": "1", "iv_number": iv, "iv_date": dd,
        "iv_date_str": "%02d/%02d/2026" % (day, mo), "company": "บริษัท เอ เอ เอ จำกัด",
        "tax_id": "0105500000017", "branch": "สำนักงานใหญ่", "branch_no": "00000",
        "address": _MAS["เอ เอ เอ"]["address"], "subtotal": sub, "vat": round(sub * 0.07, 2),
        "total": round(sub * 1.07, 2), "items": [{"seq": 1, "name": "ทราย", "qty": 1, "unit": "คิว", "price": sub, "amount": sub}],
        "issues": [],
    }
span = build_vendor_reports([_mkm("M1", 100.0, 1, 5), _mkm("M2", 200.0, 2, 10)], None, _MAS)
stext = span[0][1]
check(stext.splitlines()[1].endswith("69.01-02"), f"หัวแสดงช่วงเดือน '69.01-02' (ได้ '{stext.splitlines()[1]}')")
check(stext.rstrip().splitlines()[-2].endswith("ตรงครับ"), "ผู้ขายสะอาดข้ามเดือน → ท้าย 'ตรงครับ'")
# สรุปท้ายซอฟ: มีจุด ไม่มีหมายเหตุ → 'ที่เหลือตรงครับผม'
dmm = _mkm("M3", 300.0, 5, 7)
dmm["issues"] = [{"code": "DT002", "category": "วันที่", "name": "วันที่", "detail": "ชีตลงวันที่ 7 แต่ลงวันที่ 18"}]
dtext = build_vendor_reports([dmm], None, _MAS)[0][1]
check("ที่เหลือตรงครับผม" in dtext, "สรุปท้ายซอฟ (ไม่มีหมายเหตุ): '...ที่เหลือตรงครับผม'")
check("1 จุดต้องแก้" not in dtext and "จุดที่ต้องแก้" not in dtext, "ไม่ใช้คำแข็ง 'จุดต้องแก้'")
check("ไฟล์ JRN" in dtext, "ช่องอ้างอิงด้วย 'ไฟล์ {prefix}'")

# ── [16] ยอด 'ก่อน VAT' ทนทาน + หน่วยผิดชัดเจน (เหล็กเพลท) ──
from agents.vendor_report import _pre_vat

# subtotal เก็บยอดรวม VAT ผิด (subtotal==total, มี vat) → ก่อน VAT = total − vat
b_badsub = {"subtotal": 107.0, "vat": 7.0, "total": 107.0, "items": [{"amount": 100.0}]}
check(abs(_pre_vat(b_badsub) - 100.0) < 0.01, f"_pre_vat: subtotal รวม VAT ผิด → 100 (ได้ {_pre_vat(b_badsub):.2f})")
# ปกติ subtotal+vat=total → ใช้ subtotal
b_ok = {"subtotal": 100.0, "vat": 7.0, "total": 107.0, "items": [{"amount": 100.0}]}
check(abs(_pre_vat(b_ok) - 100.0) < 0.01, "_pre_vat: ปกติ → subtotal (100)")
rep_bad = build_vendor_reports([{**_mk("IVx", 100.0), "subtotal": 107.0, "vat": 7.0, "total": 107.0,
                                 "items": [{"seq": 1, "name": "งาน", "qty": 1, "unit": "งาน", "price": 100.0, "amount": 100.0}]}], None, _MAS)[0][1]
check("ยอด : 100 บาท" in rep_bad, f"ยอดในรายงาน = ก่อน VAT (100) ไม่ใช่ 107 : '{[l for l in rep_bad.splitlines() if l.startswith('ยอด')][0]}'")

# เหล็กเพลท หน่วย=เส้น (ควร แผ่น) → ต้องโชว์ในรายการสินค้า
plate = [{**_mk("IVp", 1000.0),
          "items": [{"seq": 3, "name": "เหล็กเพลท หนา 10 มม.", "qty": 5, "unit": "เส้น", "price": 200.0, "amount": 1000.0}],
          "issues": [{"code": "ITM005", "category": "รายการสินค้า", "name": "หน่วย",
                      "detail": "#3 \"เหล็กเพลท หนา 10 มม.\" — หน่วย=เส้น อาจไม่เหมาะ (ปกติใช้ ['แผ่น']) [soft]"}]}]
ptext = build_vendor_reports(plate, None, _MAS)[0][1]
check("เหล็กเพลท" in ptext and "หน่วยควรเป็น แผ่น" in ptext, "เหล็กเพลท: โชว์ 'หน่วยควรเป็น แผ่น ไม่ใช่ เส้น'")
# ITM005 ปกติ (เต้ารับ/ชิ้น) ต้องยังถูกกรอง (ไม่ใช่ definite)
normal_unit = [{**_mk("IVn", 500.0),
                "items": [{"seq": 1, "name": "เต้ารับสามขา", "qty": 1, "unit": "ชิ้น", "price": 500.0, "amount": 500.0}],
                "issues": [{"code": "ITM005", "category": "รายการสินค้า", "name": "หน่วย",
                            "detail": "#1 \"เต้ารับสามขา\" — หน่วย=ชิ้น อาจไม่เหมาะ (ปกติใช้ ['ตัว']) [soft]"}]}]
ntext = build_vendor_reports(normal_unit, None, _MAS)[0][1]
check("รายการสินค้า : ตรง" in ntext, "ITM005 ทั่วไป (เต้ารับ/ชิ้น) → ยังกรองเป็น noise (ไม่โชว์)")

print("\n" + "=" * 64)
print(f"VENDOR REPORT: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ ฟอร์แมตรายงานลูกค้าตรึงครบ — advisory ไม่แตะผลหลัก")
sys.exit(0)
