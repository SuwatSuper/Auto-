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
check(any(l == "บิล : 18 บิล" for l in lines), "บรรทัด 'บิล : 18 บิล' ถูกต้อง")

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
    fields.get("รายการสินค้า", "").startswith("ควรรีเช็ค"),
    f"รายการสินค้า (มี typo) = '{fields.get('รายการสินค้า')}'",
)
check(
    fields.get("เลขที่ผู้เสียภาษี") == "ตรง" and fields.get("ยอดหลัง Vat") == "ตรง",
    "ช่องที่ไม่มี issue = 'ตรง'",
)
# vendor เล็กทุก field ตรง
check(
    "รายการสินค้า : ตรง" in text2 and "ควรรีเช็ค" not in text2,
    "ผู้ขายที่สะอาด → ทุกช่อง 'ตรง'",
)

# [6] ครบ 10 ช่องตามผัง
check(all(f in fields for f in need_fields), "มีครบ 10 ช่องตามผัง")

# [7] บรรทัดท้าย = ชื่อเต็มบริษัท + งวด MM/YY
check(
    any(
        l.startswith("บริษัท จินไท่ คอนสตรัคชั่น จำกัด") and "05/69" in l for l in lines
    ),
    "บรรทัดท้าย = ชื่อเต็ม + งวด MM/YY",
)

# [8] ภาษาคน: ไม่มีโค้ดกฎ (เช่น ITM004/VAT002) หลุดในไฟล์
check(not re.search(r"[A-Z]{2,4}\d{3}", text1), "ไม่มีโค้ดกฎหลุด (ภาษาคนล้วน)")

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
