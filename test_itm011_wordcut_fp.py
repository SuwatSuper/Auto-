# -*- coding: utf-8 -*-
"""test_itm011_wordcut_fp.py — ล็อก ADR-119: ITM011/ITM012 ตัด false-positive คลาส "ตัดคำกลางคำ"

บริบท (BUG-1): regex เดิม `re.findall(r'[ก-๙][ก-๙์]{3,19}', name)` จำกัด 20 ตัว/คำ → คำประสมไทย
ไม่มีช่องว่างยาวเกิน 20 ('ข้อต่อสามทางเกลียวชุบสังกะสี' = 28 ตัว) ถูกตัดเป็นหน้าต่าง 20 ตัว →
ท่อนที่ 2 เริ่ม "กลางคำ" = เศษคำ 'บสังกะสี' → fuzzy ใกล้ 'สังกะสี' 93% = FP (ต้นฉบับ 'ชุบสังกะสี' ถูก).
แก้ (ADR-119): เก็บเฉพาะท่อนแรกของแต่ละ Thai run (run[:20]) → ตัดเศษ ; token ≤20 ตัวเดิมเท่าเดิมเป๊ะ.

เทสนี้ล็อก 2 ทิศพร้อมกัน (กัน regression ทั้งสองด้าน):
  • [FP gone]  คำประสมยาว >20 ตัวที่ "สะกดถูก" → ITM011 เงียบ (ไม่มี token ผีจากการตัดคำ)
  • [recall]   typo "จริง" ที่อยู่ใน run ≤20 ตัว → ITM011 ยังฟ้องเหมือนเดิม (ไม่หาย)

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_itm011_wordcut_fp.py
"""
import os
import sys
import io
import re
import contextlib
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine_rules_b as B
import rules_engine as RE

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def _it(seq, name):
    return {"seq": seq, "name": name, "name_raw": name}


print("=" * 64)
print("ADR-119 — ITM011/ITM012 ตัด FP 'ตัดคำกลางคำ' (BUG-1) + recall typo จริงคงครบ")
print("=" * 64)

# ── [A] FP คลาสตัดคำต้อง "หายไป" ────────────────────────────────────────
print("\n[A] คำประสมยาว >20 ตัว ที่สะกดถูก → ITM011 ต้องเงียบ (ไม่มี token ผี)")
# เคสจริงจาก corpus: KNT_69_012 ชีต 13.2 #3 — เซลล์ 'ข้อต่อสามทางเกลียวชุบสังกะสีDN25'
FP_NAME = "ข้อต่อสามทางเกลียวชุบสังกะสีDN25"
out = B.r_itm011({"items": [_it(3, FP_NAME)]}, None, {})
check(not any("บสังกะสี" in x for x in out),
      f"'{FP_NAME}' → ไม่ฟ้อง token ผี 'บสังกะสี' (เดิม FP ~93%)")
check(out == [], f"'{FP_NAME}' → ITM011 เงียบสนิท (ต้นฉบับ 'ชุบสังกะสี' สะกดถูก)")

# white-box: extraction ใหม่ต้องไม่คาย 'บสังกะสี' (ขอบซ้ายปลอมจากการตัด run)
toks = [run[:20] for run in re.findall(r"[ก-๙][ก-๙์]+", FP_NAME) if len(run) >= 4]
check("บสังกะสี" not in toks, f"extraction ไม่มี fragment 'บสังกะสี' (tokens={toks})")
# ท่อนแรกต้องเท่ากฎเดิมเป๊ะ (กัน behavior drift ของคำ ≤20 ตัว)
old_first = re.findall(r"[ก-๙][ก-๙์]{3,19}", FP_NAME)[0]
check(toks[0] == old_first, "ท่อนแรกของ run = เท่ากฎเดิมเป๊ะ (run[:20] == window แรก)")

# ── [B] typo "จริง" ใน run ≤20 ตัว ต้องยังฟ้อง (recall ไม่ถอย) ───────────
print("\n[B] typo จริงยังฟ้องเหมือนเดิม (recall lock)")
# 'มั้วน' (KRR/SHS ฯลฯ) — ADR-056 ยืนยันเป็น typo จริง 'ม้วน'
out_b1 = B.r_itm011({"items": [_it(2, "สายไฟเบอร์ออฟติก เข้าหัว มั้วน 300 เมตร")]}, None, {})
check(any("มั้วน" in x and "ม้วน" in x for x in out_b1), "'มั้วน' → ยังฟ้องใกล้ 'ม้วน'")
# [ADR-121] 'แผ่นเจียร์' เลิกฟ้องแล้ว (whitelist — TOA/HomePro มาตรฐานวงการ) → ใช้ 'อิฐบล็อค' แทน
#   (คำก้ำกึ่งที่ "คงฟ้อง" — ราชบัณฑิตฯ = อิฐบล็อก) เพื่อล็อก recall ของ ITM011 fuzzy run ≤20 ตัว
out_b2 = B.r_itm011({"items": [_it(2, "อิฐบล็อค 190*190*90")]}, None, {})
check(len(out_b2) >= 1, "'อิฐบล็อค' → ยังฟ้อง (recall ของคำ run ≤20 ไม่หาย)")
# [ADR-121] ยืนยัน 'แผ่นเจียร์' เงียบแล้ว (whitelist)
out_b3 = B.r_itm011({"items": [_it(5, "แผ่นเจียร์ MAKITA ขนาด 4 นิ้ว")]}, None, {})
check(not any("แผ่นเจียร์" in x for x in out_b3), "'แผ่นเจียร์' → ITM011 เงียบ (ADR-121 whitelist)")

# ── [C] คำประสมที่ถูก ยาว ≤20 ตัว → ไม่ฟ้อง (กัน FP อีกทาง) ──────────────
print("\n[C] คำประสมสะกดถูกที่ยาว ≤20 ตัว → ไม่ฟ้อง")
out_c = B.r_itm011({"items": [_it(1, "ชุบสังกะสี")]}, None, {})
check(out_c == [], "'ชุบสังกะสี' (เดี่ยว, 10 ตัว) → ไม่ฟ้อง")

# ── [D] ITM012 (ฝาแฝด regex เดียวกัน) — เคสยาว >20 ต้องไม่คาย fragment ──
print("\n[D] ITM012 (ฝาแฝด) — long compound ไม่คาย fragment")
out_d = RE.r_itm012({"items": [_it(3, FP_NAME)]}, None, {})
check(not any("บสังกะสี" in x for x in out_d), "ITM012: 'บสังกะสี' ไม่ออกมาเป็น suggestion")

# ── สรุป ───────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
if FAIL:
    for l in FAIL:
        print("   ❌", l)
    sys.exit(1)
print("✅ ครบ — ADR-119: FP 'ตัดคำกลางคำ' หาย + typo จริงยังฟ้อง (recall lock)")
