# -*- coding: utf-8 -*-
"""test_adr122_new_rules.py — [ADR-122] กฎใหม่ 3 ตัว: VAT012 / ADDR010 / ADDR007

ยืนยัน "ฟ้องเมื่อควรฟ้อง / เงียบเมื่อควรเงียบ / ไม่ครัชทุก input" สำหรับ:
  • VAT012  — บาทตัวอักษร (ยอดรวมเป็นคำ) ≠ ยอดตัวเลข total (กันแก้เลขลืมแก้อักษร)
  • ADDR010 — จังหวัดในที่อยู่ไม่ใช่ 1 ใน 77 จังหวัดจริง (สะกดผิด/ปลอม)
  • ADDR007 — รหัสไปรษณีย์ ↔ อำเภอ/เขต ไม่สอดคล้อง (เสริม ADDR006)
+ ตัวแปลง baht_text_to_decimal ความถูกต้อง + crash-safety (adversarial input).

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_adr122_new_rules.py
"""
import os, sys, io, contextlib, warnings, importlib
from decimal import Decimal
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine as RE
from puopuy_units import baht_text_to_decimal
from thai_postal import invalid_province_in_address, district_postal_mismatch

PASS, FAIL = 0, []
def check(c, l):
    global PASS
    if c: PASS += 1; print(f"  ✅ {l}")
    else: FAIL.append(l); print(f"  ❌ {l}")

def _bill(**kw):
    b = {'items': [], 'issues': [], 'address': '', 'total': None, 'total_text': None}
    b.update(kw); return b

print("=" * 64)
print("ADR-122 — VAT012 / ADDR010 / ADDR007 (ฟ้อง/เงียบ/ไม่ครัช)")
print("=" * 64)

# ── [A] ตัวแปลง baht_text_to_decimal ──────────────────────────────────────
print("\n[A] baht_text_to_decimal — ความถูกต้อง")
cases = [('ห้าหมื่นสามพันห้าร้อยบาทถ้วน', '53500'),
         ('หนึ่งบาทเก้าสิบเก้าสตางค์', '1.99'),
         ('สองแสนแปดหมื่นสี่พันแปดร้อยสามบาทถ้วน', '284803'),
         ('ศูนย์บาทถ้วน', '0'),
         ('หกหมื่นเก้าสิบเอ็ดบาทยี่สิบสตางค์', '60091.20')]
for txt, exp in cases:
    got = baht_text_to_decimal(txt)
    check(got == Decimal(exp), f"'{txt[:30]}' = {got} (want {exp})")
# คืน None เมื่อไม่ใช่บาทอักษรสะอาด
for bad in ['แผ่นสเตนเลส 304', 'ท่อ PVC', None, '', 'บาท', 123, [1]]:
    check(baht_text_to_decimal(bad) is None, f"ไม่ใช่บาทอักษร {bad!r} → None (เงียบ)")
# ครอบ branch: ล้าน / satang>99 / ล้านไม่มีเลขนำ / เลขอารบิก-ไทย / _thai_words_to_int เดี่ยว
from puopuy_units import _thai_words_to_int
for txt, exp in [('หนึ่งล้านบาทถ้วน', '1000000'), ('สองล้านห้าแสนสามหมื่นบาทถ้วน', '2530000'),
                 ('สิบล้านบาทถ้วน', '10000000'), ('หนึ่งล้านสองแสนสามหมื่นสี่พันห้าร้อยหกสิบเจ็ดบาทถ้วน', '1234567')]:
    check(baht_text_to_decimal(txt) == Decimal(exp), f"ล้าน: '{txt[:24]}' = {exp}")
check(baht_text_to_decimal('ล้านบาท') is None, "'ล้านบาท' (ไม่มีเลขนำ) → None")
check(baht_text_to_decimal('หนึ่งบาทหนึ่งร้อยสตางค์') is None, "สตางค์>99 → None")
check(baht_text_to_decimal('๑๒๓บาท') is None, "เลขอารบิก/ไทย ปน → None")
check(baht_text_to_decimal('หนึ่งบาทเศษ') is None, "เศษหลังบาทไม่ใช่ถ้วน/สตางค์ → None")
check(_thai_words_to_int('สิบ') == 10, "_thai_words_to_int('สิบ')=10")
check(_thai_words_to_int('ยี่สิบเอ็ด') == 21, "ยี่สิบเอ็ด=21")
check(_thai_words_to_int('') is None, "_thai_words_to_int('')=None")
check(_thai_words_to_int('abcเหล็ก') is None, "เศษไม่ใช่คำเลข → None")
check(_thai_words_to_int(None) is None, "_thai_words_to_int(None)=None")

# ── [B] VAT012 — ฟ้องเมื่อ บาทอักษร ≠ ตัวเลข ; เงียบเมื่อตรง ──────────────
print("\n[B] r_vat012")
check(RE.r_vat012(_bill(total=1070.0, total_text='หนึ่งพันเจ็ดสิบบาทถ้วน'), None, {}) == [],
      "ตรงกัน (1,070 = หนึ่งพันเจ็ดสิบ) → เงียบ")
o = RE.r_vat012(_bill(total=1070.0, total_text='หนึ่งหมื่นเจ็ดสิบบาทถ้วน'), None, {})
check(len(o) == 1, "ต่างกัน (เลข 1,070 ≠ อักษร 10,070) → ฟ้อง")
check(RE.r_vat012(_bill(total=1070.0, total_text=None), None, {}) == [], "ไม่มี total_text → เงียบ")
check(RE.r_vat012(_bill(total=None, total_text='หนึ่งพันบาท'), None, {}) == [], "ไม่มี total → เงียบ")
check(RE.r_vat012(_bill(total=1070.0, total_text='ขยะที่แปลงไม่ได้ xyz'), None, {}) == [],
      "แปลงบาทอักษรไม่ได้ → เงียบ (ไม่ FP)")

# ── [C] ADDR010 — จังหวัดปลอม/สะกดผิด ─────────────────────────────────────
print("\n[C] r_addr010")
check(RE.r_addr010(_bill(address='99 ต.x อ.y จังหวัดเชียงใหม่ 50000'), None, {}) == [],
      "จังหวัดจริง (เชียงใหม่) → เงียบ")
check(RE.r_addr010(_bill(address='99 กรุงเทพมหานคร 10110'), None, {}) == [], "กรุงเทพมหานคร → เงียบ")
check(len(RE.r_addr010(_bill(address='99 จังหวัดสมุทปราการ 10540'), None, {})) == 1,
      "สมุทปราการ (สะกดผิด) → ฟ้อง")
check(len(RE.r_addr010(_bill(address='99 จังหวัดมั่วซั่ว 12345'), None, {})) == 1, "จังหวัดปลอม → ฟ้อง")

# ── [D] ADDR007 — ไปรษณีย์ ↔ อำเภอ ────────────────────────────────────────
print("\n[D] r_addr007")
check(RE.r_addr007(_bill(address='ต.บ่อวิน อำเภอบางพลี จังหวัดสมุทรปราการ 10540'), None, {}) == [],
      "บางพลี + 10540 (ตรง) → เงียบ")
o = RE.r_addr007(_bill(address='ต.x อำเภอบางบ่อ จังหวัดสมุทรปราการ 10540'), None, {})
check(len(o) == 1, "บางบ่อ + 10540 (รหัสของบางพลี) → ฟ้อง")
check(RE.r_addr007(_bill(address='ต.x อ.เมือง จังหวัดขอนแก่น 40000'), None, {}) == [],
      "เมืองขอนแก่น + 40000 (ตรง) → เงียบ")

# ── [E] crash-safety — ทุก input ไม่ครัช (กฎ + helper) ────────────────────
print("\n[E] crash-safety (adversarial)")
crash = []
for v in [None, '', 123, 45.6, True, [1], {'a': 1}, b'x', 'ก' * 9000, '😀จ.😀']:
    for fn in (invalid_province_in_address, district_postal_mismatch):
        try: fn(v)
        except Exception as e: crash.append((fn.__name__, type(e).__name__))
    for r in (RE.r_vat012, RE.r_addr010, RE.r_addr007):
        try: r(_bill(address=v, total_text=v, total=v), None, {})
        except Exception as e: crash.append((r.__name__, type(e).__name__))
check(not crash, f"ทุก adversarial input ไม่ครัช (พบ {len(crash)})")
for c in crash[:10]: print("     ❌", c)

print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL: print("   ❌", l)
    sys.exit(1)
print("✅ ครบ — ADR-122 กฎใหม่ 3 ตัว: ฟ้อง/เงียบถูก + ไม่ครัชทุก input")
