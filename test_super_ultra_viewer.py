# -*- coding: utf-8 -*-
"""test_super_ultra_viewer.py — ยืนยัน 10 viewers + composer (ฟอร์แมต v9.2 "เหมือนคนเขียน")

ตรึง:
  • 10 viewers ครบ
  • FieldViewer ตัดสินตามเลน: fix/check → ข้อความ (ไม่มี emoji) , master → 'ไม่มี master ตรวจไม่ได้' ,
    note → ไม่ทำให้ช่องผิด (ยกขึ้นบรรทัดหมายเหตุ) , ไม่มี issue → ตรง
  • fix ชนะ check ชนะ master (ลำดับความสำคัญ)
  • [งาน D] ช่องรายการสินค้า: ITM010+ITM011 → ยุบเหลือ 'คำสินค้าผิด' ; ช่องวันที่: DOC001 → 'ลงวันที่ผิด'
  • [งาน D] DT001/DT002 = เลน NOTE → ช่องวันที่ยัง 'ตรง' แต่ขึ้นบรรทัด 'หมายเหตุ :' + บริษัทยังคลีนได้
  • [งาน C] บล็อกไม่มี emoji (❌/⚠️/📌) , ไม่ dump รายบิลใน .txt (ย้ายไป Excel) , ท้ายใช้ชื่อนิติบุคคลเต็ม
  • [A1] ไม่มี master / ผู้ขายไม่อยู่ใน master → ช่องตัวตนครบ 4 (ชื่อ/เลขภาษี/ที่อยู่/สาขา) = 'ตรวจไม่ได้'
    (แยกเหตุผล: ไม่มีใน master / ทะเบียนไม่มีข้อมูลช่องนี้ / อ่านจากบิลไม่ได้) + ไม่ขึ้น 'ตรงครับ ✅' หลอก
self-contained.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viewers import VIEWERS, CompanyViewer, TaxIdViewer, ItemViewer, DateViewer
import super_ultra_viewer as SUV

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


def _gi(*issues):
    """แปลง (code, detail) → group_issues format [(bill_key, issue)]."""
    return [("F.xls/1", {"code": c, "detail": d, "severity": "WARNING"}) for c, d in issues]


_check("มี 10 viewers", len(VIEWERS) == 10)

# CompanyViewer: ไม่มี issue → ตรง
_check("ไม่มี issue → 'ตรง'", CompanyViewer.verdict([])["status"] == "ตรง")

# CMP001 = ชื่อไม่ตรง master "ที่ตรวจเจอจริง" (master ต้องมีอยู่ถึงจะ fire)
#   v9.2 [FIX]: เดิมเลน MASTER → viewer โชว์ 'ไม่มี master ตรวจไม่ได้' ทั้งที่ฟ้องแล้ว (เคสแดง) ;
#   แก้เป็นเลน FIX → โชว์ความขัดแย้งจริง. 'ไม่มี master ตรวจไม่ได้' มาจาก build(master_present=False) เท่านั้น
v = CompanyViewer.verdict(_gi(("CMP001", "ในไฟล์ A | master B")))
_check("CMP001 (เจอจริง) → โชว์เป็น fix (ไม่ใช่ 'ไม่มี master')",
       v["mark"] == "fix" and "ไม่มี master" not in v["status"])

# [งาน C] fix lane (CMP005) → ข้อความ (ไม่มี emoji)
v = CompanyViewer.verdict(_gi(("CMP005", "ไม่มีจำกัด")))
_check("CMP005 (fix) → 'ชื่อบริษัทไม่ครบ' + ไม่มี emoji ❌",
       v["mark"] == "fix" and "ชื่อบริษัทไม่ครบ" in v["status"] and "❌" not in v["status"])

# fix ชนะ master (มีทั้ง CMP001 + CMP005)
v = CompanyViewer.verdict(_gi(("CMP001", "x | y"), ("CMP005", "ไม่มีจำกัด")))
_check("fix ชนะ master (mark=fix ไม่ใช่ 'ไม่มี master')", v["mark"] == "fix")

# TaxIdViewer: TAX003/TAX005 = ความขัดแย้งที่ "เทียบ master แล้วเจอจริง" (ไม่ใช่ 'ตรวจไม่ได้')
#   v9.2 [FIX]: เดิมจัดเลน MASTER → viewer โชว์ 'ไม่มี master ตรวจไม่ได้' ทั้งที่กฎฟ้องแล้ว (บั๊ก) ;
#   แก้เป็นเลน FIX → โชว์ความขัดแย้งจริง (เช่น 'เลขภาษีเป็นของบริษัทอื่นใน master')
v = TaxIdViewer.verdict(_gi(("TAX003", "เลขไม่ตรง")))
_check("TAX003 (เทียบ master เจอจริง) → โชว์เป็น fix (ไม่ใช่ 'ไม่มี master')", v["mark"] == "fix")
v5 = TaxIdViewer.verdict(_gi(("TAX005", "TaxID X เป็นของ 'A' — แต่ในบิลใช้ชื่อ 'B'")))
_check("TAX005 (เลขภาษีเป็นของบริษัทอื่น) → โชว์เป็น fix", v5["mark"] == "fix")

# [งาน D] ItemViewer: ITM010+ITM011 (typo จุดเดียว) → ยุบเหลือ label 'คำสินค้าผิด'
v = ItemViewer.verdict(_gi(("ITM010", '#3: "มั้วน" → "ม้วน"'), ("ITM011", '#3: "มั้วน" ใกล้เคียง')))
_check("ITM010+ITM011 ยุบเหลือ label 'คำสินค้าผิด' เดียว", set(v["fix"]) == {"คำสินค้าผิด"})

# [งาน D] ItemViewer: ITM015 → 'หน่วยสินค้าผิด' ; ITM002 → 'ลำดับรายการสินค้าผิด'
v = ItemViewer.verdict(_gi(("ITM015", '#1 "หิน 3/4" — ใช้หน่วย [คิว, ตัน]')))
_check("ITM015 → 'หน่วยสินค้าผิด'", set(v["fix"]) == {"หน่วยสินค้าผิด"})
v = ItemViewer.verdict(_gi(("ITM002", "ลำดับซ้ำ: [5]")))
_check("ITM002 → 'ลำดับรายการสินค้าผิด'", set(v["fix"]) == {"ลำดับรายการสินค้าผิด"})

# [งาน D] DateViewer: DOC001 → ช่องวันที่ = 'ลงวันที่ผิด'
v = DateViewer.verdict(_gi(("DOC001", "ชีต30 บิล31")))
_check("DOC001 → ช่องวันที่ = 'ลงวันที่ผิด' (fix)", v["mark"] == "fix" and "ลงวันที่ผิด" in v["status"])

# [งาน D] DateViewer: DOC001(fix) ชนะ DT001(note)
v = DateViewer.verdict(_gi(("DT001", "ไม่ตรงเดือน 12"), ("DOC001", "ชีต30 บิล31")))
_check("วันที่: DOC001(fix) ชนะ DT001(note)", v["mark"] == "fix" and "ลงวันที่ผิด" in v["status"])

# [งาน D] DT001 อย่างเดียว = NOTE → ไม่ทำให้ช่องวันที่ผิด (mark=ok) แต่เข้า note bucket
v = DateViewer.verdict(_gi(("DT001", "วันที่ 17/01 ไม่ตรงเดือน 12")))
_check("DT001 อย่างเดียว → ช่องวันที่ยัง 'ตรง' (mark=ok)",
       v["mark"] == "ok" and v["status"] == "ตรง")
_check("DT001 → เข้า note bucket 'เดือนในบิลไม่ตรง...'",
       any("เดือนในบิล" in x for x in v.get("note", [])))

# composer: บล็อกคลีน
clean_bill = {"file": "C.xls", "sheet": "1", "company": "บริษัท ทดสอบ จำกัด",
              "tax_id": "0", "branch": "สำนักงานใหญ่", "address": "x",
              "iv_number": "IV1", "iv_date": __import__("datetime").datetime(2026, 5, 1),
              "total": 1000.0, "vat": 65.0, "subtotal": 935.0, "items": [], "issues": []}
rows = SUV.build([clean_bill])
blk = SUV.render_block(1, rows[0])
_check("บล็อกคลีนมีหัว '69.05' (BE.MM)", "69.05" in blk)
_check("บล็อกคลีนจบ 'ตรงครับ ✅'", blk.strip().endswith("ตรงครับ"))
_check("บล็อกท้ายใช้ชื่อนิติบุคคลเต็ม 'บริษัท ทดสอบ จำกัด'", "บริษัท ทดสอบ จำกัด" in blk.strip().split("\n")[-1])
_check("บล็อกมีครบ 12 ช่อง (ยอด/บิล/10 field)",
       all(f in blk for f in ["ยอด :", "บิล :", "ชื่อบจ. :", "ที่อยู่ :",
                              "เลขที่ผู้เสียภาษี :", "สาขา/สนญ. :", "เลขที่ :",
                              "วันที่ :", "เลขที่ iv :", "รายการสินค้า :",
                              "ยอดหลัง Vat :", "ยอดก่อน vat :"]))

# composer: บล็อกมีปัญหา (typo) — [งาน C] ไม่มี emoji
bad_bill = dict(clean_bill)
bad_bill["issues"] = [{"code": "ITM010", "detail": '#2: "มั้วน" → "ม้วน"', "severity": "WARNING"}]
rows = SUV.build([bad_bill])
blk = SUV.render_block(1, rows[0])
_check("บล็อกปัญหา: รายการสินค้า 'ระบุจุด' (ลำดับที่ + คำว่า{คำผิดในบิล} + รีเช็คครับ) ไม่มี emoji",
       "ลำดับที่ 2" in blk and "คำว่ามั้วน" in blk and "รีเช็คครับ" in blk
       and "❌" not in blk and "⚠️" not in blk)
_check("บล็อกปัญหา: ท้ายใช้คำ 'รีเช็ค' (ไม่ใช่ 'แก้') + จบ 'ที่เหลือตรงครับผม'",
       "รีเช็ค" in blk and "จุดต้องแก้" not in blk
       and blk.strip().endswith("ที่เหลือตรงครับผม"))

# per-bill worklist (สำหรับ Excel): ระบุ ไฟล์/วันที่/ลำดับ + 'ของเดิม→ที่ควร'
fl = rows[0]["fixlist"]
_check("fixlist มี 1 จุด (รายการ #2)", len(fl) == 1 and fl[0]["seq"] == "2")
_check("fixlist บอกไฟล์/วันที่/ช่อง", fl[0]["file"] == "C.xls" and fl[0]["date"] == "01/05/2026"
       and fl[0]["field"] == "รายการสินค้า")
_check("fixlist detail มี 'ของเดิม→ที่ควร'", "มั้วน" in fl[0]["detail"] and "→" in fl[0]["detail"])

# [FIX] .txt ระบุจุดด้วย "รหัสนำหน้าไฟล์" (prefix) ไม่ใช่ชื่อไฟล์เต็ม + ไม่มี emoji 📌
_check("บล็อก .txt ระบุ prefix ('C') ไม่ใช่ชื่อไฟล์เต็ม ('C.xls'), ไม่มี 📌",
       "C วันที่" in blk and "C.xls" not in blk and "📌" not in blk)

# ITM010 + ITM011 จุดเดียวกัน → ยุบเหลือ 1 บรรทัดใน fixlist
bad2 = dict(clean_bill)
bad2["issues"] = [{"code": "ITM010", "detail": '#3: "เจียร์" → "เจียร" ใน "แผ่นเจียร์"', "severity": "WARNING"},
                  {"code": "ITM011", "detail": '#3: "เจียร์" ใกล้เคียง "เจียร" (~90%)', "severity": "WARNING"}]
rows2 = SUV.build([bad2])
fl2 = rows2[0]["fixlist"]
_check("ITM010+ITM011 จุดเดียว → fixlist เหลือ 1 บรรทัด", len(fl2) == 1)
_check("เลือก detail ที่มี 'ของเดิม→ที่ควร'", "→" in fl2[0]["detail"])

# ── [v9.2 งาน D] DT001 (NOTE) → บริษัทยังคลีน + มีบรรทัด 'หมายเหตุ :' + จบ 'ตรงครับ ✅' ──
note_bill = dict(clean_bill)
note_bill["file"] = "KRR_69_012.xls"
note_bill["issues"] = [{"code": "DT001", "detail": "วันที่ 17/01/2026 ไม่ตรงเดือน 12", "severity": "WARNING"}]
rows_nt = SUV.build([note_bill])
blk_nt = SUV.render_block(1, rows_nt[0])
_check("DT001 → บริษัทยังคลีน (ช่องวันที่ 'ตรง')",
       rows_nt[0]["clean"] and rows_nt[0]["verdicts"]["วันที่"]["status"] == "ตรง")
_check("DT001 → มีบรรทัด 'หมายเหตุ :' (ระบุไฟล์ KRR)", "หมายเหตุ :" in blk_nt and "KRR" in blk_nt)
_check("DT001 (clean+note) → ยังจบ 'ตรงครับ ✅'", blk_nt.strip().endswith("ตรงครับ"))

# ── [A1] master_present=False → ไม่มี master จริง: "ตรวจไม่ได้" ครอบทั้ง 4 ช่องตัวตน ──────────
#   v9.3 [FIX]: เดิม override เฉพาะ ชื่อบจ./เลขภาษี (ตกหล่นที่อยู่/สาขา → ขึ้น 'ตรง' หลอก) ;
#   A1 ครอบ ชื่อ/เลขภาษี/ที่อยู่/สาขา ครบ + แยกเหตุผล "ไม่มีใน master (ตรวจไม่ได้)".
rows_nm = SUV.build([clean_bill], master_present=False)
blk_nm = SUV.render_block(1, rows_nm[0])
_check("no-master: ชื่อบจ. → 'ไม่มีใน master (ตรวจไม่ได้)'",
       "ตรวจไม่ได้" in rows_nm[0]["verdicts"]["ชื่อบจ."]["status"]
       and "ไม่มีใน master" in rows_nm[0]["verdicts"]["ชื่อบจ."]["status"]
       and rows_nm[0]["verdicts"]["ชื่อบจ."]["mark"] == "master")
_check("no-master: เลขที่ผู้เสียภาษี → 'ตรวจไม่ได้'",
       "ตรวจไม่ได้" in rows_nm[0]["verdicts"]["เลขที่ผู้เสียภาษี"]["status"]
       and rows_nm[0]["verdicts"]["เลขที่ผู้เสียภาษี"]["mark"] == "master")
_check("no-master: ไม่พิมพ์ 'ตรงครับ ✅' หลอก", "ตรงครับ" not in blk_nm and "ตรงเท่าที่ตรวจได้" in blk_nm)
_check("no-master: ที่อยู่ ก็ 'ตรวจไม่ได้' ด้วย (A1 ครอบที่อยู่ — เลิกขึ้น 'ตรง' หลอก)",
       "ตรวจไม่ได้" in rows_nm[0]["verdicts"]["ที่อยู่"]["status"]
       and rows_nm[0]["verdicts"]["ที่อยู่"]["mark"] == "master")
_check("no-master: สาขา/สนญ. ก็ 'ตรวจไม่ได้' ด้วย (A1 ครอบสาขา)",
       "ตรวจไม่ได้" in rows_nm[0]["verdicts"]["สาขา/สนญ."]["status"]
       and rows_nm[0]["verdicts"]["สาขา/สนญ."]["mark"] == "master")
_check("no-master: footer ระบุช่องที่ตรวจไม่ได้ (รวมที่อยู่/สาขา ไม่ใช่แค่ชื่อ/เลขภาษี)",
       "ที่อยู่" in blk_nm and "สาขา" in blk_nm and "ไม่มี master เทียบ" in blk_nm)

# master_present=True (default) → คง 'ตรง' + 'ตรงครับ ✅' เหมือนเดิม (กัน regression)
rows_m = SUV.build([clean_bill], master_present=True)
blk_m = SUV.render_block(1, rows_m[0])
_check("has-master: ชื่อบจ. คง 'ตรง'", rows_m[0]["verdicts"]["ชื่อบจ."]["status"] == "ตรง")
_check("has-master: บล็อกคลีนยังจบ 'ตรงครับ ✅'", blk_m.strip().endswith("ตรงครับ"))

# error ที่ตรวจได้โดยไม่ต้องใช้ master (CMP005 ขาด 'จำกัด') ต้องยังโชว์แม้ master_present=False
bad_name = dict(clean_bill)
bad_name["issues"] = [{"code": "CMP005", "detail": "ไม่มีจำกัด", "severity": "WARNING"}]
rows_bn = SUV.build([bad_name], master_present=False)
_check("no-master: CMP005 (fix, ไม่พึ่ง master) ยังโชว์ (ไม่ถูกกลบเป็น 'ไม่มี master')",
       rows_bn[0]["verdicts"]["ชื่อบจ."]["mark"] == "fix")

# ── [UX 2026-06] รายการสินค้าหลายคำผิด: จัดกลุ่มต่อไฟล์ + footer pad '05/69' ──
def _typo_bill(fl, day, *typos):
    iss = [{"code": "ITM010", "detail": f'#{s}: "{w}" → "x"', "severity": "WARNING"} for s, w in typos]
    return {"file": fl, "sheet": "1", "company": "บริษัท ทดสอบ จำกัด", "tax_id": "0105556012345",
            "branch": "สำนักงานใหญ่", "address": "x", "iv_number": "IV1",
            "iv_date": __import__("datetime").datetime(2026, 5, day),
            "total": 1070.0, "vat": 70.0, "subtotal": 1000.0, "items": [], "issues": iss}
_rows_g = SUV.build([_typo_bill("TSH_69_05.xls", 6, (2, "เจียร์"), (5, "ปลายสว่าง")),
                     _typo_bill("TSH_69_05.xls", 14, (4, "ปี๊ป")),
                     _typo_bill("TKH_69_05.xls", 20, (3, "ม้วน"))])
_blk_g = SUV.render_block(1, _rows_g[0])
_item_line = [ln for ln in _blk_g.split("\n") if ln.startswith("รายการสินค้า :") or ln.startswith("TSH") or ln.startswith("TKH")]
_check("ไฟล์เดียวกัน (TSH) โชว์ prefix ครั้งเดียว (ไม่ซ้ำทุกคำผิด)", _blk_g.count("TSH วันที่") == 1)
_check("หลายคำผิดไฟล์เดียวกัน = คั่นด้วย ', ' (3 รายการ TSH ในบรรทัดเดียว)",
       "คำว่าเจียร์, วันที่" in _blk_g and "คำว่าปลายสว่าง" in _blk_g and "คำว่าปี๊ป" in _blk_g)
_check("แต่ละไฟล์โชว์ prefix ครั้งเดียว (TKH+TSH อย่างละ 1)",
       _blk_g.count("TKH วันที่") == 1 and _blk_g.count("TSH วันที่") == 1)
_check("คนละไฟล์ = ขึ้นบรรทัดใหม่ (ไฟล์ที่ 2 ตามลำดับ TKH<TSH = TSH นำหน้าบรรทัดใหม่)",
       any(ln.startswith("TSH วันที่") for ln in _blk_g.split("\n")))
_check("จบบรรทัดรายการด้วย 'รีเช็คครับ' ครั้งเดียว", _blk_g.count("รีเช็คครับ") == 1)
_check("footer เดือน pad ศูนย์ '05/69' (ไม่ใช่ '5/69')", "05/69" in _blk_g and " 5/69 " not in _blk_g)

# ── [Precision Council 2 ชั้น] ITM011 ก้ำกึ่ง → main 'ตรง' + บรรทัด "ตรวจตาเพิ่ม" + footer ตรงครับ ──
_soft_bill = dict(clean_bill)
_soft_bill["file"] = "TSH_69_05.xls"
_soft_bill["issues"] = [{"code": "ITM011", "detail": '#3: "เจียร" ใกล้เคียง (ตรวจสอบ) "เจียร์" (~90%)',
                         "severity": "WARNING"}]
_blk_s = SUV.render_block(1, SUV.build([_soft_bill])[0])
_check("soft (ITM011 ก้ำกึ่ง): ช่องรายการสินค้าในรีพอร์ตหลัก = 'ตรง'",
       "รายการสินค้า : ตรง" in _blk_s)
_check("soft: มีบรรทัด 'ตรวจตาเพิ่ม' ท้ายบล็อก (ไม่ทิ้ง/ไม่ซ่อน)",
       "ตรวจตาเพิ่ม (รายการสินค้า) :" in _blk_s and "ก้ำกึ่ง" in _blk_s and "เจียร" in _blk_s)
_check("soft: footer = 'ตรงครับ (มี N จุดให้ตรวจตาเพิ่ม)' (precision-first, ไม่ฟันธงส่งลูกค้า)",
       "ตรงครับ (มี 1 จุดให้ตรวจตาเพิ่ม)" in _blk_s)
# clear (ITM010 ชัด) ยังเข้ารีพอร์ตหลักเหมือนเดิม (ไม่ถูกดาวน์เป็น soft)
_clear_bill = dict(clean_bill)
_clear_bill["file"] = "TSH_69_05.xls"
_clear_bill["issues"] = [{"code": "ITM010", "detail": '#2: "มั้วน" → "ม้วน"', "severity": "WARNING"}]
_blk_c = SUV.render_block(1, SUV.build([_clear_bill])[0])
_check("clear (ITM010 ชัด): ยังขึ้นรีพอร์ตหลัก + footer รีเช็ค (ไม่ถูกยกไปตรวจตาเพิ่ม)",
       "คำว่ามั้วน" in _blk_c and "รีเช็ครายการสินค้าครับ" in _blk_c
       and "ตรวจตาเพิ่ม" not in _blk_c)

print("=" * 56)
if _fail == 0:
    print("RESULT: [PASS] 10 viewers + composer ทำงานถูก (ฟอร์แมตคน + เลน NOTE + คัดเลน + master_present)")
    sys.exit(0)
else:
    print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
    sys.exit(1)
