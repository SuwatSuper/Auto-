# -*- coding: utf-8 -*-
"""test_bs1_taxid_fullwidth.py — [BS-1/ADR-114] เลขภาษี full-width ０-９ → อารบิก

ช่องโหว่: clean_tax_id แปลงเลขไทย ๐-๙ ได้ แต่เลข full-width ０-９ (U+FF10–FF19)
ถูก re.sub([^0-9]) (ASCII) ตัดทิ้ง → คืน '' → ระบบขึ้น "ไม่พบเลขภาษี" หลอก + checksum/
เทียบทะเบียน/TAX005/008 ทำไม่ได้. (เจอบ่อยตอน copy เลขจาก PDF/ระบบบางตัว.)

ตรึง: full-width → เลขถูก ; เลขไทย/ASCII ไม่ regress ; อักขระไม่ใช่เลข → '' (ไม่ false-positive).
self-contained: ไม่พึ่ง corpus. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from puopuy_core import clean_tax_id, _taxid_checksum_ok

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


FW = "０１０５５４０００１２３４"   # full-width 13 หลัก
TH = "๐๑๐๕๕๔๐๐๐๑๒๓๔"        # เลขไทย 13 หลัก
AS = "0105540001234"           # ASCII 13 หลัก

# 1) ฟ้อง/กู้เคสผิด: full-width → อารบิกถูกต้อง 13 หลัก (เดิม = '')
_check("full-width ０-９ → '0105540001234' (เดิมคืน '')", clean_tax_id(FW) == AS)
_check("full-width ได้ 13 หลักครบ (ไม่หาย)", len(clean_tax_id(FW)) == 13)

# 2) ไม่ regress: เลขไทย + ASCII ยังถูกเหมือนเดิม
_check("เลขไทย ๐-๙ → ถูกเหมือนเดิม (ADR-074 ไม่พัง)", clean_tax_id(TH) == AS)
_check("ASCII → ถูกเหมือนเดิม", clean_tax_id(AS) == AS)

# 3) ผสม full-width + ASCII + เลขไทย → รวมเป็นอารบิกถูก
_check("ผสม fw+ascii → ถูก", clean_tax_id("0105５４0001234") == AS)
_check("ผสม label + dash + full-width → ถูก", clean_tax_id("เลขภาษี ０１０５-５４０-００１２３４") == AS)

# 4) เงียบเคสถูก/ปกติ (ไม่สร้าง false-positive): อักขระไม่ใช่เลข → ''
_check("ตัวอักษรล้วน → '' (ไม่คว้าเป็นเลข)", clean_tax_id("ABCDEF") == "")
_check("ว่าง/None → ''", clean_tax_id("") == "" and clean_tax_id(None) == "")

# 5) idempotent
_check("idempotent: clean(clean(fw)) == clean(fw)", clean_tax_id(clean_tax_id(FW)) == AS)

# 6) downstream: full-width tax ที่ผ่าน checksum ได้ → checksum ทำงานบนค่าที่กู้มา
#    (ใช้เลข checksum-valid จริง 0994000165510 แบบ full-width)
FW_CKSUM = "".join(chr(ord('０') + int(d)) for d in "0994000165510")
_check("checksum ทำงานบน full-width ที่กู้มาแล้ว (valid)", _taxid_checksum_ok(clean_tax_id(FW_CKSUM)))

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] BS-1 full-width ０-９ แปลงถูก + ไม่ regress เลขไทย/ASCII")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
