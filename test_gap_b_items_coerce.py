# -*- coding: utf-8 -*-
"""test_gap_b_items_coerce.py — [GAP-B / ADR-124] run_rules ต้อง coerce 'items' เป็น list เสมอ

อาการ (เดิม): ถ้า bill['items'] "มีอยู่แต่เป็น non-list" (None/int/str/tuple — บิลภายนอก/บางส่วน/
ไฟล์เพี้ยนอนาคต) บรรทัด `for _it in bill['items']` ใน run_rules อยู่ "นอก" try ของกฎ → โยน
TypeError → bumper ที่ pukpui_modular_funcs ดักแล้ว "ข้ามทั้งบิล" = false-negative (ทั้งใบไม่ถูก
ตรวจเลย โผล่เป็น 'ตรง' หลอก). เป็นพี่น้องของ GAP-A (ADR-120 coerce ฟิลด์ข้อความ) แต่เป็น "ตัว container".

แก้ (golden-neutral): coerce items→[] ที่ต้น run_rules. corpus จริงทุกบิล items เป็น list → no-op →
golden คง 23b315e8.

ทดสอบ: (A) ไม่ throw ทุก non-list (B) บิลยัง "ถูกตรวจจริง" (ไม่ถูกข้าม) — tax_id เสียยังโดนฟ้อง
(C) items ถูก coerce เป็น list.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_gap_b_items_coerce.py
"""
import os, sys, io, contextlib, warnings, importlib
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine as RE

PASS, FAIL = 0, []
def check(c, l):
    global PASS
    if c: PASS += 1; print(f"  ✅ {l}")
    else: FAIL.append(l); print(f"  ❌ {l}")

def _bill(**over):
    b = {'company': 'X', 'company_raw': 'X', 'tax_id': '', 'tax_id_raw': '', 'branch': '',
         'branch_no': '', 'iv_number': '', 'iv_number_raw': '', 'iv_date': None, 'iv_date_str': '',
         'address': '', 'subtotal': None, 'vat': None, 'total': None, 'total_text': None,
         'sheet': 's', 'file': 'f', 'block_idx': 0, 'issues': [], 'items': []}
    b.update(over); return b

print("=" * 64)
print("GAP-B / ADR-124 — run_rules coerce items→list (กัน false-negative ข้ามทั้งบิล)")
print("=" * 64)

# ── [A] run_rules ไม่ throw บน items non-list ทุกแบบ ──────────────────────
print("\n[A] run_rules ไม่ throw (items non-list)")
for label, v in [('None', None), ('int', 5), ('float', 4.5), ('str', 'เหล็ก'),
                 ('bool', True), ('dict', {'a': 1}),
                 ('tuple', ({'seq': 1, 'name': 'x', 'name_raw': 'x', 'qty': 1, 'unit': 'อัน',
                             'price': 1, 'amount': 1},)),
                 ('missing', '__DEL__')]:
    b = _bill()
    if v == '__DEL__':
        del b['items']
    else:
        b['items'] = v
    try:
        RE.run_rules(b, {}, {}, None, [])
        threw = False
    except Exception as e:
        threw = True; print("     →", type(e).__name__, str(e)[:50])
    check(not threw, f"items={label} → ไม่ throw")
    check(isinstance(b['items'], list), f"items={label} → coerce เป็น list แล้ว")

# ── [B] บิลยัง "ถูกตรวจจริง" (ไม่ถูกข้าม) — หัวใจของ fix ────────────────────
print("\n[B] บิล items=None ยังถูกตรวจ (ไม่ใช่ skip เงียบ = false-negative)")
# tax_id สั้น/ขยะ ต้องโดนกฎ tax ฟ้อง แม้ items=None
b = _bill(items=None, company='บริษัท ทดสอบ จำกัด', company_raw='บริษัท ทดสอบ จำกัด',
          tax_id='12345', tax_id_raw='12345')
RE.run_rules(b, {}, {}, None, [])
codes = {i.get('code') for i in b['issues']}
check(len(b['issues']) > 0, f"items=None + tax_id ขยะ → ยังมี issue ({len(b['issues'])} จุด: {sorted(codes)[:5]})")
check(any(c and c.startswith('TAX') for c in codes),
      "→ กฎ TAX ฟ้อง tax_id ขยะ (พิสูจน์ว่า 'ตรวจจริง' ไม่ใช่ข้ามทั้งบิล)")
# bill ที่มี items=list ปกติ (ตรง) ต้องไม่งอก issue เกิน (ไม่ regress)
b2 = _bill(items=[{'seq': 1, 'name': 'เหล็กเส้น', 'name_raw': 'เหล็กเส้น', 'qty': 1.0,
                   'unit': 'เส้น', 'price': 10.0, 'amount': 10.0}],
           tax_id='0105566206726', tax_id_raw='0105566206726', subtotal=10.0, vat=0.7, total=10.7)
RE.run_rules(b2, {}, {}, None, [])
check(isinstance(b2['items'], list) and len(b2['items']) == 1, "items=list ปกติ → คงเดิม (ไม่ทำลายข้อมูล)")

# ── [C] tuple-of-items: coerce เป็น [] (conservative — ไม่เดา) ────────────
print("\n[C] non-list ถูก coerce เป็น [] (conservative)")
b3 = _bill(items=({'seq': 1, 'name': 'x'},))
RE.run_rules(b3, {}, {}, None, [])
check(b3['items'] == [], "tuple → [] (ไม่ทำให้กฎ item ครัชภายหลัง)")

print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL: print("   ❌", l)
    sys.exit(1)
print("✅ ครบ — GAP-B: items coerce เป็น list · ไม่ throw · บิลถูกตรวจจริง (กัน false-negative)")
