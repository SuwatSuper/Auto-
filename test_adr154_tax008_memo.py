# -*- coding: utf-8 -*-
"""test_adr154_tax008_memo.py — [ADR-154] r_tax008/_tax008_name/_tax008_clean memoization.

พิสูจน์ 2 อย่าง:
  1) golden-neutral: ค่าที่ memoized function คืน == ค่าที่ pure function คำนวณสด (byte-identical)
     บนทุก input ที่คอร์ปัส/edge เจอ → r_tax008 ผลตรวจไม่ขยับ.
  2) perf: การเรียกซ้ำด้วย input เดิม เป็น cache-hit จริง (ยุบ O(g²) recompute → O(distinct)).

กันถอยหลัง: ถ้ามีใครถอด lru_cache หรือทำ helper ไม่ pure → เทสนี้แดง.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rules_engine_rules_c as C
from puopuy_core import clean_tax_id, normalize_text

fails = 0
def check(cond, msg):
    global fails
    print(('  ✅ ' if cond else '  ❌ ') + msg)
    if not cond:
        fails += 1

print("ADR-154 — r_tax008 memoization (golden-neutral + perf)")

# 1) golden-neutral: memoized == fresh computation over a broad sample (corpus-like + edge)
samples = [
    "บริษัท เอ บี ซี จำกัด", "บริษัท เอ บี ซี จำกัด (สำนักงานใหญ่)",
    "หจก. ทดสอบ ๑๒๓", "บริษัท  เว้นวรรค   เกิน  จำกัด", "",
    "บริษัท สาขาวิชาการ จำกัด", "บ.ทดสอบ สาขา 00001", "  ", "ABC Co., Ltd.",
    "บริษัท กขค จำกัด สำนักงานใหญ่", "เลขไทย๙๙๙", None if False else "x",
]
def _fresh_name(s):
    s2 = C._TAX008_BRANCH_RE.sub('', normalize_text(s))
    import re
    return re.sub(r'\s+', ' ', s2).strip()

ok_name = all(C._tax008_name(s) == _fresh_name(s) for s in samples)
check(ok_name, "_tax008_name(memoized) == fresh normalize สำหรับทุก sample (golden-neutral)")

tax_samples = ["1234567890123", "0-1055-12345-67-8", "๑๒๓", "", "  '1105566000123  ",
               1234567890123, 55.0, None, "ABC123", "１２３４５６７８９０１２３"]
ok_tax = all(C._tax008_clean(s) == clean_tax_id(s) for s in tax_samples)
check(ok_tax, "_tax008_clean(memoized) == clean_tax_id สำหรับทุก sample (golden-neutral)")

# 2) perf: cache-hit จริง (เรียกซ้ำ input เดิม → hits เพิ่ม)
try:
    C._tax008_name.cache_clear(); C._tax008_clean.cache_clear()
except Exception:
    pass
for _ in range(50):
    C._tax008_name("บริษัท เอ บี ซี จำกัด")
    C._tax008_clean("1234567890123")
ni = C._tax008_name.cache_info(); ti = C._tax008_clean.cache_info()
check(ni.hits >= 49, f"_tax008_name cache-hit ทำงาน (hits={ni.hits} จาก 50 เรียกซ้ำ)")
check(ti.hits >= 49, f"_tax008_clean cache-hit ทำงาน (hits={ti.hits} จาก 50 เรียกซ้ำ)")

# 3) end-to-end: r_tax008 ยัง detect 'เลขเดียวชื่อต่าง' และเงียบเมื่อชื่อเดียวกัน (พฤติกรรมเดิม)
#    ใช้ชื่อ "ต่างกันชัด" (คลาส เจ.อาร์./ฉีหยวน) — ไม่ใช่ชื่อคล้ายที่เกณฑ์ conservative ถือว่าเดียวกัน
# กลุ่ม A: เลขเดียว ชื่อต่างชัด (b1 vs b2) → ต้องฟ้อง
b1 = {'tax_id': '1234567890123', 'company': 'บริษัท เอ บี ซี จำกัด'}
b2 = {'tax_id': '1234567890123', 'company': 'ห้างทองเยาวราช จำกัด'}
gA = [b1, b2]
ctxA = {'all_bills_for_iv_check': gA, 'xbill_tax_index': {'1234567890123': gA}}
r1 = C.r_tax008(b1, {}, ctxA)
check(any('เยาวราช' in x for x in r1), "r_tax008: เลขภาษีเดียว ชื่อต่างชัด → ฟ้อง (คลาส anti-fraud คงเดิม)")

# กลุ่ม B: ชื่อเดียวกัน ต่างแค่ (สำนักงานใหญ่) → เงียบ (เกณฑ์ conservative เดิม)
b3 = {'tax_id': '9876543210123', 'company': 'บริษัท เอ บี ซี จำกัด'}
b4 = {'tax_id': '9876543210123', 'company': 'บริษัท เอ บี ซี จำกัด (สำนักงานใหญ่)'}
gB = [b3, b4]
ctxB = {'all_bills_for_iv_check': gB, 'xbill_tax_index': {'9876543210123': gB}}
r3 = C.r_tax008(b3, {}, ctxB)
check(r3 == [], "r_tax008: ต่างแค่ (สำนักงานใหญ่) → เงียบ (ไม่ยุบชนผิด · เกณฑ์เดิม)")

print(("RESULT: ✅ ADR-154 ผ่าน" if fails == 0 else f"RESULT: ❌ {fails} ข้อไม่ผ่าน"))
sys.exit(1 if fails else 0)
