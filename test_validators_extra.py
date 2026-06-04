# -*- coding: utf-8 -*-
"""test_validators_extra.py — [OBJ-1D ต่อยอด] ดัน coverage ของ validators.py ให้ ≥90%

แตะ "กิ่งที่เหลือ" ของตัวตรวจลำดับ/วันที่/งวด/typo โดยเรียก sub-checker ตรง ๆ
ด้วยบิลที่ออกแบบให้เข้าทางที่ test_validators.py เดิมยังไม่ครอบ:
  • _iv_check_month_consistency : กดเงียบเดือนนอกกลุ่มเมื่อชื่อไฟล์ "ประกาศช่วงเดือน" (60-62)
  • _iv_check_sheet_day         : sheet เป็นเลข แต่ ≠ iv_date.day → ฟ้อง + ไม่เข้า sequence (92-97)
  • _iv_check_sequence          : เลขท้ายยาวไม่เท่ากัน → ข้าม (128) ; เลขถอยหลังในวันเดียวกัน (148)
  • _iv_check_cross_day         : ข้ามบิล _merged_pages (167) ; เลขที่เดียวกันข้ามวัน → IV003 (175-183)
  • _iv_check_ascending         : ข้ามบิล _merged_pages (201) ; IV ไม่มีเลขท้าย → ข้าม (204)
  • check_iv_date_sequence      : IV↔Date ถอยหลังในเดือนเดียวกัน (292)
  • detect_iv_period_mismatch   : งวด "ปี4หลักล้วน" ไม่มีเดือน (335-337,347-349) ; อ่านงวดไม่ได้→None (340)
  • check_product_typos         : ชนเพดาน MAX_TYPO_NAMES → SYS002 (377-385) ; primary พลาด→fallback (441-449)

ทุก assert ผูกกับ "พฤติกรรมที่ควรเป็น" (ไม่ใช่ปั๊ม coverage). เป็น pure check บนสำเนาบิล
→ ไม่แตะผลหลัก/ไม่กระทบ golden hash.
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_validators_extra.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""
import os
import sys
import io
import contextlib
import warnings
import datetime as dt

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
warnings.filterwarnings('ignore')

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

import validators as V

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


def has_type(issues, needle):
    return any(needle in str(i.get('type', '')) for i in issues)


def has_code(bill, code):
    return any(i.get('code') == code for i in bill.get('issues', []))


VENDOR_TAX = '0105566206726'


def mkb(iv, year, month, day, file='TEST_69_05.xls', sheet=None,
        items=None, merged=False):
    """บิลควบคุมได้: ปี ค.ศ./เดือน/วัน, ชื่อไฟล์, sheet, _merged_pages, items."""
    b = {
        'iv_number': iv, 'iv_number_raw': iv,
        'iv_date': dt.date(year, month, day) if day else None,
        'company': 'บริษัท ก จำกัด', 'tax_id': VENDOR_TAX,
        'sheet': sheet if sheet is not None else str(day or 1),
        'file': file, 'block_idx': 0,
        'subtotal': 1000.0, 'vat': 70.0, 'total': 1070.0,
        'items': items or [{'seq': 1, 'name': 'เหล็ก', 'name_raw': 'เหล็ก',
                            'qty': 1.0, 'unit': 'เส้น', 'price': 1000.0, 'amount': 1000.0}],
        'issues': [],
    }
    if merged:
        b['_merged_pages'] = [1, 2]
    return b


print("=" * 64)
print("VALIDATORS EXTRA — กิ่งที่เหลือของ IV/date/period/typo")
print("=" * 64)

# ─────────────────────────────────────────────────────────────
print("\n[V1] _iv_check_month_consistency — ชื่อไฟล์ประกาศช่วงเดือน → กดเงียบเดือนนอกกลุ่ม (60-62)")
# ไฟล์ KRR_69_03-04 ประกาศช่วงเดือน {3,4} ปี 2569(BE). บิลปี 2026(CE)=2569(BE) ตรงปี
#   3 ใบเดือน 3 (เสียงข้างมาก) + 1 ใบเดือน 4 (อยู่ในช่วงที่ประกาศ) → ใบเดือน 4 ต้อง "ไม่ถูกฟ้อง"
decl_file = 'KRR_69_03-04.xls'
decl_bills = [mkb('IV01', 2026, 3, 1, file=decl_file, sheet='1'),
              mkb('IV02', 2026, 3, 2, file=decl_file, sheet='2'),
              mkb('IV03', 2026, 3, 3, file=decl_file, sheet='3'),
              mkb('IV04', 2026, 4, 4, file=decl_file, sheet='4')]  # เดือน 4 อยู่ในช่วงประกาศ
res = V._iv_check_month_consistency([dict(b) for b in decl_bills])
check(not has_type(res, 'คนละเดือน'),
      f"เดือน 4 ที่อยู่ในช่วงประกาศ {{3,4}} → ไม่ฟ้อง (suppress)  (ได้ {len(res)} issue)")
# คอนทราสต์: ไฟล์ไม่ประกาศช่วง (เดือนเดียว) → ใบเดือน 4 กลายเป็น outlier ต้องฟ้อง (พิสูจน์ว่า suppress ไม่ใช่ vacuous)
plain_bills = [mkb('IV01', 2026, 3, 1, file='KRR_69_03.xls', sheet='1'),
               mkb('IV02', 2026, 3, 2, file='KRR_69_03.xls', sheet='2'),
               mkb('IV03', 2026, 3, 3, file='KRR_69_03.xls', sheet='3'),
               mkb('IV04', 2026, 4, 4, file='KRR_69_03.xls', sheet='4')]
res2 = V._iv_check_month_consistency([dict(b) for b in plain_bills])
check(has_type(res2, 'คนละเดือน'),
      "ไฟล์ไม่ประกาศช่วง → ใบเดือน 4 เป็น outlier ต้องฟ้อง (suppress มีผลจริง ไม่ vacuous)")

# ─────────────────────────────────────────────────────────────
print("\n[V2] _iv_check_sheet_day — sheet เป็นเลขแต่ ≠ iv_date.day → ฟ้อง + ไม่เข้า sequence (92-97)")
sd_bill = mkb('IV6805020', 2025, 5, 20, sheet='15')  # ชีต 15 แต่วันที่ 20
issues_sd, consistent = V._iv_check_sheet_day([dict(sd_bill)])
check(has_type(issues_sd, 'ไม่สอดคล้อง'), "sheet 15 vs day 20 → ฟ้อง 'IV วันที่ไม่สอดคล้อง'")
check(len(consistent) == 0, "บิลที่ sheet ไม่ตรง → ไม่ถูกส่งต่อเข้า sequence (continue)")
# คอนทราสต์: sheet ตรงวัน → ไม่ฟ้อง + เข้า sequence
ok_bill = mkb('IV6805020', 2025, 5, 20, sheet='20')
iss_ok, cons_ok = V._iv_check_sheet_day([dict(ok_bill)])
check(not iss_ok and len(cons_ok) == 1, "sheet 20 == day 20 → ไม่ฟ้อง + เข้า sequence")

# ─────────────────────────────────────────────────────────────
print("\n[V3] _iv_check_sequence — เลขท้ายยาวไม่เท่ากันในวันเดียวกัน → ข้ามการเทียบ (128)")
# วันเดียวกัน vendor เดียวกัน: ลงท้าย '5' (seq=5,len1) กับ '12' (seq=12,len2) → seq_lengths={1,2} → ข้าม
mixlen = [mkb('IV-A5', 2025, 5, 10, sheet='Sheet1'),
          mkb('IV-B12', 2025, 5, 10, sheet='Sheet1')]
res3 = V._iv_check_sequence([dict(b) for b in mixlen])
check(not has_type(res3, 'ซ้ำ') and not has_type(res3, 'ถอยหลัง'),
      f"เลขท้ายยาวต่างกัน (1 vs 2 หลัก) → ไม่เทียบลำดับ (ได้ {len(res3)} issue)")

print("\n[V4] _iv_check_sequence — เลขถอยหลังในวันเดียวกัน (เลขท้ายยาวเท่ากัน) → ฟ้อง (148)")
# วันเดียวกัน: ใบแรกลงท้าย '05'(5) ใบหลัง '03'(3) → 3<5 = ถอยหลัง
desc = [mkb('IV-X05', 2025, 5, 10, sheet='Sheet1'),
        mkb('IV-X03', 2025, 5, 10, sheet='Sheet1')]
res4 = V._iv_check_sequence([dict(b) for b in desc])
check(has_type(res4, 'ถอยหลัง'), "seq 3 < 5 ในวันเดียวกัน → ฟ้อง 'IV ถอยหลัง'")

# ─────────────────────────────────────────────────────────────
print("\n[V5] _iv_check_cross_day — ข้าม _merged_pages (167) + เลขที่เดียวกันข้ามวัน → IV003 (175-183)")
xday = [mkb('DOC-999', 2025, 5, 1, merged=True),          # _merged_pages → ต้องถูกข้าม (167)
        mkb('DOC-100', 2025, 5, 5),                       # เลขเดียวกัน
        mkb('DOC-100', 2025, 5, 10)]                      # คนละวัน → IV003
xday = [dict(b) for b in xday]
res5 = V._iv_check_cross_day(xday)
check(has_type(res5, 'ซ้ำข้ามวัน'), "DOC-100 โผล่ 2 วัน → ฟ้อง 'เลขที่เอกสารซ้ำข้ามวัน'")
check(has_code(xday[1], 'IV003') and has_code(xday[2], 'IV003'),
      "ผูก issue IV003 เข้าบิลทุกใบในกลุ่มข้ามวัน (side-effect คงเดิม)")
check(not has_code(xday[0], 'IV003'), "บิล _merged_pages ถูกข้าม ไม่ติด IV003 (167)")

# ─────────────────────────────────────────────────────────────
print("\n[V6] _iv_check_ascending — ข้าม _merged_pages (201) + IV ไม่มีเลขท้าย → ข้าม (204)")
asc = [mkb('DOC-555', 2025, 5, 1, merged=True),           # _merged_pages → ข้าม (201)
       mkb('INVOICE-ABC', 2025, 5, 2),                    # ไม่มีเลขท้าย → m_seq None → ข้าม (204)
       mkb('INV-XYZ', 2025, 5, 3)]                        # ไม่มีเลขท้ายอีกใบ
res6 = V._iv_check_ascending([dict(b) for b in asc])
check(isinstance(res6, list) and len(res6) == 0,
      "ทุกใบเข้าเงื่อนไขข้าม (merged/ไม่มีเลขท้าย) → ไม่มี issue + ไม่ throw")

# ─────────────────────────────────────────────────────────────
print("\n[V7] check_iv_date_sequence — IV↔Date ถอยหลังในเดือนเดียวกัน → ฟ้อง (292)")
# เดือนเดียวกัน: วันที่ 5 เลข 0100(100) , วันที่ 10 เลข 0050(50) → วันหลังเลขน้อยกว่า
ivd = [mkb('CB-0100', 2025, 5, 5), mkb('CB-0050', 2025, 5, 10)]
res7 = V.check_iv_date_sequence([dict(b) for b in ivd])
check(has_type(res7, 'IV↔Date ถอยหลัง'), "วันหลัง(10) เลข 50 < วันก่อน(5) เลข 100 → ฟ้องถอยหลัง")

# ─────────────────────────────────────────────────────────────
print("\n[V8] detect_iv_period_mismatch — งวด 'ปี4หลักล้วน' (335-337,347-349) + อ่านงวดไม่ได้→None (340)")
# 'INV-2025-001': lead='2025001' → (a)เดือน00 ไม่ผ่าน, (b)ปี20/เดือน25 ไม่ผ่าน, (c)ปี4หลักล้วน 2025 → mo=None
yo = V.detect_iv_period_mismatch('INV-2025-001', dt.date(2024, 5, 1))
check(yo is not None and 'ปี' in str(yo['iv_period']),
      f"เลขฝังปี 2025 ล้วน + วันที่ปี 2024 → คืนงวดระดับปี ({yo})")
check(yo is not None and yo['mismatch'] is True, "ปี 2025 ≠ 2024 → mismatch=True")
# lead 1-3 หลัก (อ่านงวดไม่ได้แบบมั่นใจ) → return None (340) — ต่างจากเคส 'XYZ' ที่ไม่มีเลขเลย
none_case = V.detect_iv_period_mismatch('AB12', dt.date(2025, 5, 1))
check(none_case is None, "'AB12' (เลขนำ 2 หลัก) → อ่านงวดไม่ได้ → None (340)")

# ─────────────────────────────────────────────────────────────
print("\n[V9] check_product_typos — ชนเพดาน MAX_TYPO_NAMES → log SYS002 + คืน [] (377-385)")
# CFG เป็น mappingproxy (อ่านอย่างเดียว — ตั้งใจกันแก้ config ระหว่างรัน) → ไม่ patch ค่า
#   แต่ป้อน "ชื่อ unique เกินเพดานจริง" (3001 > ค่าเริ่มต้น 3000) ให้ชนกิ่ง cap ตรง ๆ
#   ตัดออกก่อนทำ O(n²) จึงเร็ว (return ที่ 385) — ทดสอบเพดานด้วย config จริงล้วน
_cap = int(V.CFG.get('MAX_TYPO_NAMES', 3000))
big_items = [{'seq': i, 'name': f'สินค้าทดสอบหมายเลข{i:06d}',
              'name_raw': f'สินค้าทดสอบหมายเลข{i:06d}',
              'qty': 1.0, 'unit': 'ชิ้น', 'price': 10.0, 'amount': 10.0}
             for i in range(_cap + 1)]
big_bill = mkb('IV-CAP', 2025, 5, 1, items=big_items)
with contextlib.redirect_stdout(io.StringIO()):
    capped = V.check_product_typos([dict(big_bill)])
check(capped == [], f"ชื่อ unique {_cap + 1} > เพดาน {_cap} → ข้ามการตรวจ + คืน [] (377-385)")

# ─────────────────────────────────────────────────────────────
print("\n[V10] check_product_typos — primary (rapidfuzz) พลาด → ใช้ fallback loop (441-449)")
# ชื่อคล้ายกันมาก ratio≈96 (≥threshold 88) ไม่มีตัวเลข/สเปกต่าง → ควรจับเป็น typo ได้ทั้งสองทาง
sim_bills = [
    mkb('IV-S1', 2025, 5, 1, items=[{'seq': 1, 'name': 'เหล็กเส้นกลมมอก', 'name_raw': 'เหล็กเส้นกลมมอก',
                                     'qty': 1.0, 'unit': 'เส้น', 'price': 10.0, 'amount': 10.0}]),
    mkb('IV-S2', 2025, 5, 2, items=[{'seq': 1, 'name': 'เหล็กเส้นกลมมอ', 'name_raw': 'เหล็กเส้นกลมมอ',
                                     'qty': 1.0, 'unit': 'เส้น', 'price': 10.0, 'amount': 10.0}]),
]
import rapidfuzz.process as _rfproc
_orig_cdist = _rfproc.cdist


def _boom(*a, **k):
    raise RuntimeError('forced-primary-failure (test)')


try:
    _rfproc.cdist = _boom                 # บังคับให้ primary path ระเบิด → ตก except (441)
    _out = io.StringIO()
    with contextlib.redirect_stdout(_out):
        fb = V.check_product_typos([dict(b) for b in sim_bills])
    printed = _out.getvalue()
    check('fallback' in printed, "primary พลาด → เข้ากิ่ง except + แจ้งใช้ fallback (441-442)")
    check(any(t.get('name1') and t.get('name2') for t in fb),
          f"fallback loop จับคู่ typo ได้สำเร็จ (443-449)  → {len(fb)} คู่")
finally:
    _rfproc.cdist = _orig_cdist           # คืน rapidfuzz เดิมเสมอ
check(_rfproc.cdist is _orig_cdist, "คืน rapidfuzz.process.cdist เดิม (ไม่ทิ้ง monkeypatch ค้าง)")
# กัน regression: primary path ปกติ (ไม่ patch) ก็ยังจับคู่ typo เดิมได้
norm = V.check_product_typos([dict(b) for b in sim_bills])
check(any(t.get('name1') for t in norm), "primary path ปกติยังจับ typo คู่เดิมได้ (ผลตรงกับ fallback)")

# ─────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
if FAIL:
    print(f"VALIDATORS EXTRA: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    print("=" * 64)
    sys.exit(1)
else:
    print(f"VALIDATORS EXTRA: ผ่าน {PASS} / ล้มเหลว 0")
    print("=" * 64)
    print("RESULT: ✅ กิ่งตรวจลำดับ/วันที่/งวด/typo ครบ + คืน state เดิม + ไม่กระทบ golden hash")
    sys.exit(0)
