# -*- coding: utf-8 -*-
"""test_adr125_addrline_houseno.py — [ADR-125] กู้ "บ้านเลขที่หาย" จากที่อยู่ 2 บรรทัด

อาการจริง (KNT/CETI, KNT_69_05.xls ทั้ง 8 ชีต):
  ที่อยู่บิลแยก 2 บรรทัดในเซลล์ติดกัน —
    บรรทัด 1: "3/182 หมู่บ้าน กลางเมือง Urbanion ซอย ศรีนครินทร์ 46/1 (ปราโมทย์)"  ← มีบ้านเลขที่
    บรรทัด 2: "แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250"                          ← มี anchor แข็ง
  เดิม _pb_try_address_line รับเฉพาะบรรทัดที่มี anchor แข็ง (เลขที่ \\d+/ตำบล/แขวง/หมู่ที่ \\d+
  หรือ เขต/อำเภอ/จังหวัด/กรุงเทพ) → บรรทัด 1 (เลขเปล่า ไม่มี label 'เลขที่' + 'หมู่บ้าน' + 'ซอย')
  ตกทุก branch → ถูกทิ้งทั้งบรรทัด → b['address'] เหลือแค่บรรทัด 2 → house_no = None →
  ADDR001 ฟ้อง "ไม่พบเลขที่ (ทะเบียน: 3/182)" หลอก ทั้งที่เลขที่ตรงเป๊ะ.

แก้ (ADR-125): เพิ่ม branch รับบรรทัดต่อเนื่องที่ "ขึ้นต้นด้วยบ้านเลขที่ (^\\d+(/\\d+)*)
  + มีคำพักอาศัย (ซอย/ตรอก/ถนน/หมู่บ้าน/หมู่ที่/อาคาร) + len<200".
  guard "ขึ้นต้นด้วยเลข" จงใจกันบรรทัดสินค้า (เช่น 'สีทาถนน...'/'ขิงซอย') ที่ไม่ได้ขึ้นต้นด้วยเลข.
  corpus blast = 0 บิล → golden-neutral (พิสูจน์ด้วย regression_full = 23b315e8).

ครอบ 4 ด้าน:
  (1) บรรทัด KNT ถูกเก็บแล้ว (กู้บ่กลับ)
  (2) guard: บรรทัดสินค้า/วันที่/เลขภาษี ไม่หลุดเข้า address (กัน over-collect)
  (3) end-to-end ชั้น collector→join→extract: house_no = '3/182'
  (4) characterization "ก่อนแก้" (เฉพาะบรรทัด 2) → house_no = None (ยืนยันต้นตอบั๊ก)

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_adr125_addrline_houseno.py
"""
import os, sys, io, contextlib, warnings, importlib
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
from parser_p1 import _pb_try_address_line
from rules_engine_rules_a import _addr_parse_smart

PASS, FAIL = 0, []
def check(c, l):
    global PASS
    if c: PASS += 1; print(f"  ✅ {l}")
    else: FAIL.append(l); print(f"  ❌ {l}")

def _collect(line):
    """รัน collector จริงต่อ 1 บรรทัด → คืน list ที่เก็บได้ (เลียนแบบ _pb_scan_header ต่อเซลล์)"""
    acc = []; _pb_try_address_line(acc, line); return acc

KNT_L1 = "3/182 หมู่บ้าน กลางเมือง Urbanion ซอย ศรีนครินทร์ 46/1 (ปราโมทย์)"
KNT_L2 = "แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250"

print("=" * 64)
print("ADR-125 — กู้บ้านเลขที่หายจากที่อยู่ 2 บรรทัด (KNT/CETI)")
print("=" * 64)

# ── (1) บรรทัด KNT (บ้านเลขที่เปล่า + ซอย/หมู่บ้าน) ต้องถูกเก็บ ─────────────────
print("\n[1] บรรทัดบ้านเลขที่ (เลขเปล่า+ซอย/หมู่บ้าน) ถูกเก็บ")
check(KNT_L1 in _collect(KNT_L1), f"เก็บ ← {KNT_L1[:40]!r}…")
check(KNT_L2 in _collect(KNT_L2), f"เก็บ ← {KNT_L2!r} (anchor แข็งเดิมยังเก็บ)")
# รูปแบบอื่นที่ควรเก็บด้วย (เลขเปล่าขึ้นต้น + คำพักอาศัย)
for ln in ["99/1 ถนนสุขุมวิท ตึกเอ", "121/5 หมู่ที่ 3 ซอยข้าง", "5 อาคารพหลโยธินเพลส"]:
    check(ln in _collect(ln), f"เก็บ ← {ln!r}")

# ── (2) guard: บรรทัดที่ "ไม่ใช่ที่อยู่" ต้องไม่ถูกเก็บ (กัน over-collect → golden เพี้ยน) ──
print("\n[2] guard — บรรทัดสินค้า/วันที่/เลขภาษี ไม่หลุดเข้า address")
neg = [
    "สีทาถนน TOA สะท้อนแสง #717 สีขาว 3ลิตร",   # ขึ้นต้น 'สี' (ไม่ใช่เลข) → ไม่เก็บ
    "ขิงซอย",                                    # ขึ้นต้น 'ขิง' → ไม่เก็บ
    "2/5/69",                                     # วันที่ (ไม่มีคำพักอาศัย) → ไม่เก็บ
    "0-1055-67105-93-1",                          # เลขภาษี (ไม่มีคำพักอาศัย) → ไม่เก็บ
    "3 ท่อ PVC สีฟ้า",                            # สินค้าเลขนำ แต่ไม่มีคำพักอาศัย → ไม่เก็บ
    "บริษัท ทดสอบ จำกัด ซอย 1",                   # ขึ้นต้น 'บริษัท' → ตัดทิ้งตั้งแต่ guard แรก
]
for ln in neg:
    check(_collect(ln) == [], f"ไม่เก็บ ← {ln[:38]!r}")

# ── (3) end-to-end: collector→join→extract → house_no = '3/182' ────────────────
print("\n[3] end-to-end (collector→join→extract)")
acc = []
for ln in (KNT_L1, KNT_L2):          # เลียน _pb_scan_header สแกน 2 เซลล์ตามลำดับ
    _pb_try_address_line(acc, ln)
addr = " ".join(acc)
hn = _addr_parse_smart(addr).get("house_no")
check("3/182" in addr, f"address ประกอบครบ มี '3/182'  → {addr[:46]!r}…")
check(hn == "3/182", f"house_no = '3/182' (ตรงทะเบียน → ADDR001 ไม่ฟ้อง)  ได้ {hn!r}")

# ── (4) characterization "ก่อนแก้": เฉพาะบรรทัด 2 → house_no = None (ต้นตอบั๊ก) ──
print("\n[4] characterization ต้นตอบั๊ก — ที่อยู่ขาดบรรทัด 1")
hn_broken = _addr_parse_smart(KNT_L2).get("house_no")
check(hn_broken is None, f"ที่อยู่เฉพาะบรรทัดล่าง → house_no = None (= อาการ 'ไม่พบเลขที่')  ได้ {hn_broken!r}")

print("\n" + "=" * 64)
if FAIL:
    print(f"❌ FAIL {len(FAIL)} / {PASS + len(FAIL)}")
    for f in FAIL: print("   -", f)
    sys.exit(1)
print(f"✅ PASS ทั้งหมด {PASS} เคส — ADR-125 ล็อกแล้ว")
