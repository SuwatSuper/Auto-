# -*- coding: utf-8 -*-
"""test_adr123_borderline_clear.py — [ADR-123] เคลียร์คำ "ตรวจตาเพิ่ม/ก้ำกึ่ง" ให้ขาด

หลักเจ้าของ (เด็ดขาด): "คำผิดในรายการสินค้า ต้องเป็นคำที่ผิดแน่ๆ เท่านั้น"
ADR-123 จัด 2 กลุ่มตามคำตัดสินเจ้าของ:
  • กลุ่ม A (ผิดแน่) → ITM010 pattern deterministic → Precision Council = CLEAR (รีเช็ค)
        — ที่เพิ่มรอบนี้: หล็กฉาก→เหล็กฉาก (ใช้ (?<!เ) กัน FP ทับ "เหล็กฉาก" ที่ถูก)
  • กลุ่ม B (ทับศัพท์หลายรูปใช้จริง) → ลบ pattern + whitelist → เงียบทั้ง ITM010/ITM011
        — แกลอน · อิฐบล็อค · ตู้คอนซูเมอร์ · พุ๊ก/พุ๊กเคมี · อะครีลิค · อีพ๊อกซี่ · แป๊ป/แป็ป

ทดสอบ 3 ด้าน: (1) recall กลุ่ม A ยังฟ้อง (2) กลุ่ม B เงียบ (3) FP=0 บนรูปที่ถูก
+ lookbehind หล็กฉาก ถูกต้องทุกบริบท + ไม่ครัชทุก input.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_adr123_borderline_clear.py
"""
import os, sys, io, contextlib, warnings, importlib
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE); sys.path.insert(0, HERE)
with contextlib.redirect_stdout(io.StringIO()):
    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine as RE
import report_precision as RP
from config import PYTHAINLP_WHITELIST, THAI_TYPO_PATTERNS, SPELLING_PATTERNS

PASS, FAIL = 0, []
def check(c, l):
    global PASS
    if c: PASS += 1; print(f"  ✅ {l}")
    else: FAIL.append(l); print(f"  ❌ {l}")

def _bill(*names):
    return {'company': 'X', 'items': [{'seq': i + 1, 'name': n, 'name_raw': n, 'qty': 1,
            'unit': 'อัน', 'price': 1, 'amount': 1} for i, n in enumerate(names)],
            'issues': [], 'address': '', 'total': None, 'total_text': None,
            'iv_number': '1', 'sheet': 's', 'file': 'f', 'block_idx': 0}

def _typo_hits(name):
    """รวมผลกฎ typo-family ของชื่อสินค้า 1 รายการ → list ของ (rule, detail)"""
    b = _bill(name); out = []
    for fn in ('r_itm004', 'r_itm010', 'r_itm011', 'r_itm012'):
        f = getattr(RE, fn, None)
        if not f: continue
        for r in f(b, None, {}):
            out.append((fn, str(r)))
    return out

print("=" * 64)
print("ADR-123 — เคลียร์ก้ำกึ่ง: กลุ่ม A ฟ้อง / กลุ่ม B เงียบ / FP=0")
print("=" * 64)

# ── [A] recall — กลุ่ม A (คำผิดแน่ๆ) ต้องยังฟ้อง ──────────────────────────
print("\n[A] recall กลุ่ม A — คำผิดแน่ๆ ยังฟ้อง")
groupA = ['หล็กฉาก 3 มม.', 'ลวด มั้วน', 'เเป๊ปกลม', 'บอลวาวล์', 'ฝ้าสมาร์มบอร์ด',
          'ทองเหลอง', 'ลายเสอ', 'แกนลอน 20 ลิตร', 'การาไนช์ 3*1', 'ปูนเปอร์ตแลนด์',
          'สีเปรย์หล่อลื่น', 'สกรูปลายสว่าง']
for t in groupA:
    check(len(_typo_hits(t)) > 0, f"ฟ้อง  ← {t!r}")

# ── [B] กลุ่ม B (ทับศัพท์หลายรูป) — ต้องเงียบสนิท (ไม่ ITM010/ITM011) ────────
print("\n[B] กลุ่ม B (whitelist) — เงียบสนิท")
groupB = ['สีรองพื้น 5 แกลอน', 'อิฐบล็อค', 'ตู้คอนซูเมอร์ 24 ช่อง', 'พุ๊กเคมี + สตัด M16',
          'พุ๊ก 3 หุน', 'สีน้ำอะครีลิค', 'สีอีพ๊อกซี่ Base D', 'แป๊ปกล่องสแตนเลส',
          'เหล็กแป็ปกลมดำ']
for t in groupB:
    hits = _typo_hits(t)
    check(len(hits) == 0, f"เงียบ ← {t!r}  (hits={[h[1][:30] for h in hits]})")

# ── [C] FP=0 — รูปที่ถูกต้องต้องไม่ฟ้อง (รวม lookbehind หล็กฉาก) ──────────────
print("\n[C] FP=0 — รูปที่ถูกต้องไม่ฟ้อง")
correct = ['เหล็กฉาก 3 มม.', 'เหล็กฉากเหล็กฉาก', 'ราวเหล็กฉากยาว', 'แกลลอน',
           'อะคริลิก', 'อีพ็อกซี่', 'บล็อกคอนกรีต', 'พุกพลาสติก']
for t in correct:
    hits = [(fn, d) for fn, d in _typo_hits(t) if '→' in d or 'ใกล้เคียง' in d or 'น่าจะ' in d]
    check(len(hits) == 0, f"ไม่ฟ้อง ← {t!r}  (hits={[h[1][:30] for h in hits]})")

# ── [D] lookbehind (?<!เ)หล็กฉาก — แยก typo จากคำถูกแม่นยำ ──────────────────
print("\n[D] (?<!เ)หล็กฉาก lookbehind")
check(len(_typo_hits('หล็กฉาก')) > 0, "หล็กฉาก (ตก เ) → ฟ้อง")
check(len([1 for _, d in _typo_hits('เหล็กฉาก') if 'หล็กฉาก' in d]) == 0, "เหล็กฉาก (ถูก) → ไม่ฟ้อง")
check(len(_typo_hits('ขาหล็กฉาก')) > 0, "ขาหล็กฉาก (เ ไม่นำหน้า) → ฟ้อง")

# ── [E] หล็กฉาก ต้องเข้า ITM010 → Precision Council = CLEAR (รีเช็ค ไม่ก้ำกึ่ง) ─
print("\n[E] หล็กฉาก → ITM010 → CLEAR (ไม่ใช่ตรวจตาเพิ่ม)")
b = _bill('หล็กฉาก 3 มม.')
issues = []
for fn in ('r_itm004', 'r_itm010', 'r_itm011'):
    f = getattr(RE, fn, None)
    if f:
        for r in f(b, None, {}):
            d = r if isinstance(r, dict) else {'code': fn.replace('r_', '').upper(), 'detail': str(r),
                                               'file': 'f', 'sheet': 's'}
            issues.append(d)
has_itm010 = any(i.get('code') == 'ITM010' for i in issues)
check(has_itm010, "หล็กฉาก ติด ITM010 (pattern deterministic)")
# ทุก ITM-issue บนบิลนี้ council ต้องไม่เป็น SOFT (เพราะ ITM010 หนุน)
soft = 0
for i in issues:
    if i.get('code') in ('ITM010', 'ITM011'):
        res = RP.council_review(i, bill=b, fixlist=issues)
        if res['tier'] == RP.SOFT: soft += 1
check(soft == 0, f"ไม่มี SOFT (ตรวจตาเพิ่ม) บนบิลหล็กฉาก (soft={soft})")

# ── [F] whitelist/patterns invariants ──────────────────────────────────────
print("\n[F] โครงสร้าง config — pattern/whitelist ตรงเจตนา ADR-123")
for w in ['แกลอน', 'อิฐบล็อค', 'ตู้คอนซูเมอร์', 'คอนซูเมอร์', 'พุ๊กเคมี', 'พุ๊ก',
          'อะครีลิค', 'อีพ๊อกซี่', 'แป๊ป', 'แป็ป']:
    check(w in PYTHAINLP_WHITELIST, f"'{w}' อยู่ใน PYTHAINLP_WHITELIST (กลุ่ม B)")
_pat_strs = [p for p, _ in list(THAI_TYPO_PATTERNS) + list(SPELLING_PATTERNS)]
# pattern กลุ่ม B ต้องถูกลบออกจาก ITM010/ITM004 แล้ว
for removed in ['พุ๊ก', 'ครีลิ', 'อีพ๊อก']:
    check(removed not in _pat_strs, f"ลบ pattern '{removed}' จาก ITM010/ITM004 แล้ว")
# pattern กลุ่ม A (หล็กฉาก) ต้องมี + ใช้ negative lookbehind
check(any('หล็กฉาก' in p for p in _pat_strs), "มี pattern หล็กฉาก (กลุ่ม A)")
check(any('(?<!เ)หล็กฉาก' == p for p in _pat_strs), "pattern หล็กฉาก ใช้ (?<!เ) กัน FP")
# pattern กลุ่ม A อื่นที่ต้องคงไว้
for kept in ['แกนลอน', 'เเป๊ป', 'วาวล์']:
    check(any(kept in p for p in _pat_strs), f"คง pattern '{kept}' (กลุ่ม A)")

# ── [G] crash-safety — ทุก input ไม่ครัช ──────────────────────────────────
print("\n[G] crash-safety (adversarial)")
crash = []
for v in [None, '', 'เ' * 5000, 'หล็กฉาก' * 500, '\x00หล็กฉาก', '😀หล็กฉาก😀', 'ก' * 9000]:
    try: _typo_hits(v if isinstance(v, str) else '')
    except Exception as e: crash.append((repr(v)[:20], type(e).__name__))
check(not crash, f"ไม่ครัชทุก input (found {len(crash)})")
for c in crash[:5]: print("     ❌", c)

print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL: print("   ❌", l)
    sys.exit(1)
print("✅ ครบ — ADR-123: กลุ่ม A ฟ้อง(รีเช็ค) · กลุ่ม B เงียบ · FP=0 · ไม่ครัช")
