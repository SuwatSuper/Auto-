# -*- coding: utf-8 -*-
"""test_fix_tnt_trio.py — ตรึง 3 fix จากเคสจริง TNT/เถ้าแก่เนี้ย 11.06.69

BUG-1: master.parse_master_blob — ภ.พ.20 layout 'เลขภาษี<TAB>เลขสาขา'
BUG-2: vendor_report — provenance diagnostics (TAX001 fallback/IV001 merge) ไม่รั่วเข้า .txt
BUG-3: parser_p2._sheet_name_looks_like_bill — SYS003 จับชีต 'N (2)' ครบ
"""
import sys

_results = []
def check(cond, msg):
    _results.append((bool(cond), msg))
    print(f"  {'✅' if cond else '❌'} {msg}")

print("=" * 64)
print("FIX TNT TRIO — ตรึงการแก้ 3 บั๊กเคสจริง 11.06.69")
print("=" * 64)

# ── BUG-1 : parse_master_blob ──────────────────────────────────────────────
from master import parse_master_blob

blob_tnt = ("0-2055-55015-71-1\t00001\t\n"
            " บริษัท เถ้าแก่เนี้ย จำกัด   /  บริษัทเถ้าแก่เนี้ย จำกัด \n"
            "อาคาร - ห้องเลขที่ - ชั้นที่ - หมู่บ้าน - เลขที่ 9/16 หมู่ที่ 1 ถนน - \n"
            "ตำบลหนองซ้ำซาก อำเภอบ้านบึง จังหวัดชลบุรี 20170")
r = parse_master_blob(blob_tnt)
check(r["tax_id"] == "0205555015711", f"BUG-1: ภ.พ.20 TAB-layout → tax_id 13 หลักถูก (ได้ {r['tax_id']!r})")
check("00001" in r["branch"], f"BUG-1: สาขา 00001 ถูกจับ (ได้ {r['branch']!r})")

r2 = parse_master_blob("เลขประจำตัวผู้เสียภาษี 0-1055-66206-72-6 สำนักงานใหญ่ "
                       "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด เลขที่ 5/32 "
                       "ซอย ศรีนครินทร์ 46/1 เขตประเวศ กรุงเทพมหานคร 10250")
check(r2["tax_id"] == "0105566206726" and r2["branch"] == "สำนักงานใหญ่",
      "BUG-1 regression: explicit สำนักงานใหญ่ ยังถูก")

r3 = parse_master_blob("0-1055-66206-72-6 สาขา 00003 บริษัท X จำกัด เลขที่ 1 แขวง ก กรุงเทพ 10110")
check("00003" in r3["branch"], "BUG-1 regression: explicit 'สาขา N' ยังถูก")

r4 = parse_master_blob("0-1055-66206-72-6 บริษัท X จำกัด เลขที่ 9/16 ตำบล ย จังหวัดชลบุรี 20170")
check(r4["branch"] == "สำนักงานใหญ่" and "20170" not in r4["branch"],
      "BUG-1 guard: รหัสไปรษณีย์ปลายที่อยู่ ไม่ถูกจับเป็นสาขา")

r5 = parse_master_blob("0105566206726 00000 บริษัท Z จำกัด เลขที่ 1 แขวง ก กรุงเทพ 10110")
check(r5["branch"] == "สำนักงานใหญ่", "BUG-1 guard: เลขโดด 00000 = สำนักงานใหญ่")

# ── BUG-2 : vendor_report provenance filter ────────────────────────────────
from agents.vendor_report_base import _is_noise_issue
from agents.vendor_report import build_vendor_reports

check(_is_noise_issue({"code": "TAX001", "severity": "INFO", "name": "fallback scan",
                       "detail": "เจอเลขภาษีจาก pure 13-digit [r9,c6]"}) is True,
      "BUG-2: TAX001 fallback scan = noise (กรองออก)")
check(_is_noise_issue({"code": "TAX001", "severity": "INFO", "name": "auto-fix 12→13",
                       "detail": "เลขภาษี 12 หลัก เพิ่ม 0 นำหน้าให้แล้ว"}) is True,
      "BUG-2: TAX001 auto-fix = noise (กรองออก)")
check(_is_noise_issue({"code": "IV001", "severity": "INFO", "name": "รวมบิลข้ามหน้า",
                       "detail": "บิล X รวมจาก 2 ชีต: 18, 18 (2)"}) is True,
      "BUG-2: IV001 merge = noise (กรองออก)")
check(_is_noise_issue({"code": "ITM004", "severity": "INFO", "name": "คำสะกด"}) is False,
      "BUG-2 contract: ITM004 คำสะกด (ข้อสังเกตเนื้อหา) ยังโชว์ (ไม่ใช่ noise)")
check(_is_noise_issue({"code": "TAX003", "severity": "ERROR", "name": "เลขภาษีไม่ตรง master",
                       "detail": "ไม่ตรง: บิล 111 / ทะเบียน 222"}) is False,
      "BUG-2 contract: ERROR จริงยังโชว์")

_bill = {
    "file": "TNT_69_05.xls", "sheet": "6",
    "company": "บริษัท เถ้าแก่เนี้ย จำกัด", "tax_id": "0205555015711",
    "branch": "สาขา 1", "branch_no": "00001",
    "iv_number": "05137", "iv_date_str": "06/05/2026",
    "subtotal": 1486140.0, "vat": 104029.8, "total": 1590169.8,
    "items": [{"seq": 1, "name": "แผ่นทำความสะอาด", "qty": 3000,
               "price": 495.38, "amount": 1486140.0}],
    "issues": [{"code": "TAX001", "severity": "INFO", "category": "เลขภาษี",
                "name": "fallback scan",
                "detail": "เจอเลขภาษีจาก pure 13-digit [r9,c6]"}],
}
_, _text = build_vendor_reports([_bill])[0]
check("pure 13-digit" not in _text and "[r9,c6]" not in _text,
      "BUG-2 e2e: รายงาน .txt ไม่มี tag debug 'pure 13-digit'/'[r9,c6]'")

# ── BUG-3 : SYS003 sheet pattern ───────────────────────────────────────────
from parser_p2 import _sheet_name_looks_like_bill as _slb

for s in ("18", "5", "5.1", "22.2", "18 (2)", "5.1 (2)", "20 (2)", "18#2", "018", "05"):
    check(_slb(s) is True, f"BUG-3: ชื่อชีต {s!r} = bill-sheet")
for s in ("", "Sheet1", "สรุป", "cover", "18 อื่นๆ", "a1"):
    check(_slb(s) is False, f"BUG-3: ชื่อชีต {s!r} ≠ bill-sheet")

# ── สรุป ──────────────────────────────────────────────────────────────────
_fail = [m for ok, m in _results if not ok]
print("=" * 64)
print(f"FIX TNT TRIO: ผ่าน {len(_results) - len(_fail)} / ล้มเหลว {len(_fail)}")
print("=" * 64)
if _fail:
    for m in _fail:
        print(f"  • {m}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ ตรึง 3 fix ครบ — เคส TNT/เถ้าแก่เนี้ย ปิดสนิท")
