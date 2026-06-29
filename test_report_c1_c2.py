# -*- coding: utf-8 -*-
"""test_report_c1_c2.py — [C1+C2] รายงานลูกค้า: ระบุไฟล์ + หน่วยสะกดผิดขึ้นช่องรายการสินค้า

ไม่พึ่ง corpus จริง. ตรึง:
  C1 — ช่อง 'ที่อยู่'/'เลขที่ผู้เสียภาษี' ในรายงานต้อง "บอกไฟล์ (prefix)" ไม่ใช่แค่ '(N บิล)' ลอย ๆ
       (หลายไฟล์ → ไล่ทุกไฟล์)
  C2 — ITM019 'หน่วยสะกดผิด' (มี mapping ผิด→ถูกชัด) → ขึ้นช่อง 'รายการสินค้า' (เหมือน typo ITM010/011) ;
       ITM019 'หน่วยขาด/ดึงไม่ได้' → คงอยู่ 'ตรวจตาเพิ่ม' (soft) ไม่ promote (กัน false positive)

advisory ล้วน — audit golden ไม่ขยับ. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from code_labels import addr_summary, field_summary, F_TAX
import super_ultra_viewer as SUV

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


# ── C1: addr_summary / field_summary ต้องมี "ไฟล์ {prefix}" ────────────────────
_ADET = ("ที่อยู่ไม่ตรงทะเบียน: รหัสไปรษณีย์ไม่ตรง (บิล: 10540 / ทะเบียน: 10280); "
         "เขต/อำเภอไม่ตรง (บิล: บางพลี / ทะเบียน: เมือง)")
one = addr_summary([{"prefix": "JRN", "file": "JRN_69_05.xls", "sheet": "1", "date": "a", "detail": _ADET}])
_check("C1 addr ไฟล์เดียว → ขึ้นต้น 'ไฟล์ JRN'", one.startswith("ไฟล์ JRN"))
_check("C1 addr ระบุ field ผิด + นับบิล", "รหัสไปรษณีย์" in one and "(1 บิล)" in one and one.endswith("รีเช็คครับ"))

multi = addr_summary([
    {"prefix": "JRN", "file": "JRN_69_05.xls", "sheet": "1", "date": "a", "detail": _ADET},
    {"prefix": "JRN", "file": "JRN_69_05.xls", "sheet": "2", "date": "b", "detail": _ADET},
    {"prefix": "KRR", "file": "KRR_69_05.xls", "sheet": "1", "date": "c", "detail": _ADET},
])
_check("C1 addr หลายไฟล์ → ไล่ทุกไฟล์ (JRN + KRR)", "ไฟล์ JRN" in multi and "ไฟล์ KRR" in multi)
_check("C1 addr หลายไฟล์ → นับบิลแยกต่อไฟล์ (JRN 2 / KRR 1)", "(2 บิล)" in multi and "(1 บิล)" in multi)

tax = field_summary(F_TAX, [{"prefix": "TNT", "file": "TNT_69_01.xls", "sheet": "1", "date": "d",
                             "detail": 'เลขภาษี เป็นของ "ฉี อัน" แต่บิลใช้ชื่อ "เจ.อาร์."'}])
_check("C1 เลขภาษี → ขึ้นต้น 'ไฟล์ TNT'", tax.startswith("ไฟล์ TNT") and "(1 บิล)" in tax)

# derive prefix จาก 'file' เมื่อไม่มี key 'prefix' (เทสเก่า/ผู้เรียกที่ไม่ใส่ prefix)
deriv = addr_summary([{"file": "TKH", "sheet": "1", "date": "x", "detail": _ADET}])
_check("C1 derive prefix จาก file ('TKH') เมื่อไม่มี key prefix", deriv.startswith("ไฟล์ TKH"))


# ── C2: ITM019 หน่วยสะกดผิด vs หน่วยขาด ────────────────────────────────────────
def _base():
    return {"file": "STC_69_05.xls", "sheet": "1", "company": "บริษัท ทดสอบ จำกัด", "tax_id": "0",
            "branch": "สำนักงานใหญ่", "address": "x", "iv_number": "IV1",
            "iv_date": datetime.datetime(2026, 5, 11), "total": 1070.0, "vat": 70.0, "subtotal": 1000.0,
            "items": [{"seq": 2, "name": "ทินเนอร์", "unit": "แกลอน"}]}


b_spell = _base()
b_spell["issues"] = [{"code": "ITM019", "detail": '#2: "ทินเนอร์" — หน่วย "แกลอน" ควรเป็น "แกลลอน"',
                      "severity": "WARNING"}]
blk_sp = SUV.render_block(1, SUV.build([b_spell])[0])
_item_line = next((ln for ln in blk_sp.split("\n") if ln.startswith("รายการสินค้า :")), "")
_check("C2 หน่วยสะกดผิด → ขึ้นช่อง 'รายการสินค้า' (ไม่ใช่ 'ตรง')", _item_line != "รายการสินค้า : ตรง")
# [recheck] หน่วยทำเหมือนรายการสินค้า: โชว์ 'หน่วย แกลอน' ให้รีเช็ค (ไม่ระบุ "ควรเป็น")
_check("C2 หน่วยสะกดผิด → โชว์ 'หน่วย แกลอน' (แบบเดียวกับรายการสินค้า)",
       'หน่วย แกลอน' in blk_sp)
_check("C2 หน่วยสะกดผิด → ไม่มีรูป 'ควรเป็น' แบบเดิม", 'ควรเป็น' not in blk_sp)
_check("C2 หน่วยสะกดผิด → ระบุไฟล์ STC + ลำดับที่ 2", "STC" in _item_line and "ลำดับที่ 2" in _item_line)
_check("C2 หน่วยสะกดผิด → footer 'รีเช็ครายการสินค้า' (ไม่ตกไป soft)", "รีเช็ครายการสินค้า" in blk_sp)
_check("C2 หน่วยสะกดผิด → ไม่ตกบรรทัด 'ตรวจตาเพิ่ม'", "ตรวจตาเพิ่ม" not in blk_sp)

b_miss = _base()
b_miss["items"] = [{"seq": 3, "name": "ปูน", "unit": ""}]
b_miss["issues"] = [{"code": "ITM019", "detail": '#3: "ปูน" — ไม่มีหน่วยสินค้า (ดึงมาไม่ครบ)',
                     "severity": "WARNING"}]
blk_ms = SUV.render_block(1, SUV.build([b_miss])[0])
_check("C2 หน่วยขาด → ช่องรายการสินค้าหลัก = 'ตรง' (ไม่ promote)",
       "รายการสินค้า : ตรง" in blk_ms)
_check("C2 หน่วยขาด → คงอยู่บรรทัด 'ตรวจตาเพิ่ม' (soft)",
       "ตรวจตาเพิ่ม (รายการสินค้า)" in blk_ms and "ไม่มีหน่วย" in blk_ms)

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] C1 รายงานระบุไฟล์ + C2 หน่วยสะกดผิดขึ้นช่องรายการสินค้า (หน่วยขาดคง soft)")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
