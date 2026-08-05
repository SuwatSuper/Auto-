# -*- coding: utf-8 -*-
"""oracle_provenance.py — ORACLE §3.1 (provenance): "เงินก้อนไหนที่ระบบไม่เคยอ่านจากเอกสาร"

บทเรียน ADR-182: ถ้า subtotal มาจากผลรวมรายการ แล้ว VAT001 เอาผลรวมรายการไปเทียบกับ subtotal
= เทียบตัวเอง → "ตรง" เสมอ (false-clean). parser เก็บ `amount_source` ไว้แล้วเพื่อกันเรื่องนี้
— oracle นี้ตรวจว่า "ยอดที่ระบบเติมเอง" ถูกแจ้งให้ผู้ใช้รู้หรือไม่ และคิดเป็นเงินเท่าไร

รัน:  python3 oracle_provenance.py <data_dir>
"""
import sys
import os
import io
import glob
import contextlib
import importlib
from collections import Counter

DATA = sys.argv[1] if len(sys.argv) > 1 else "tests/real_cases"

app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
files = sorted(glob.glob(os.path.join(DATA, "*.xls*")))
with contextlib.redirect_stdout(io.StringIO()):
    app.reset_run_state()
    bills, fi = app.parse_all_files(files)
    for b in bills:
        app.compute_bill_confidence(b)
    app.run_audit_core(bills, {}, isolate=True)

READ = "ocr"                       # = อ่านจากเอกสารจริง
combos = Counter()
risk = []                          # บิลที่ "ยอดตัดสิน" ไม่ได้อ่านจากเอกสาร
money_all = 0.0
money_risk = 0.0

for b in bills:
    src = b.get("amount_source") or {}
    combos[(src.get("subtotal"), src.get("vat"), src.get("total"))] += 1
    sub = b.get("subtotal")
    if isinstance(sub, (int, float)):
        money_all += float(sub)
    # "ตรวจ VAT ไม่ได้จริง" = subtotal หรือ vat ไม่ได้อ่านจากเอกสาร
    #   (total ที่ derive จาก sub+vat เป็นเรื่องปกติ ไม่นับเป็นความเสี่ยง)
    bad = [k for k in ("subtotal", "vat") if src.get(k) not in (READ,)]
    if bad:
        codes = sorted({i["code"] for i in (b.get("issues") or [])
                        if isinstance(i, dict) and i.get("code")})
        if isinstance(sub, (int, float)):
            money_risk += float(sub)
        risk.append((b, bad, codes))

print("=" * 78)
print("ORACLE PROVENANCE — เงินที่ระบบ 'เติมเอง' ถูกแจ้งหรือไม่")
print("=" * 78)
print(f"data={DATA}  ไฟล์={len(files)}  บิล={len(bills)}")

print("\n── แหล่งที่มาของยอด (subtotal, vat, total) ──")
for k, n in combos.most_common():
    mark = "  ← ตรวจ VAT ได้จริง" if k[0] == READ and k[1] == READ else "  ← ยอดตัดสินไม่ได้อ่านจากเอกสาร"
    print(f"  {str(k):<46} {n:>4} ใบ{mark}")

print(f"\nยอดก่อน VAT รวมทั้งชุด        : {money_all:,.2f} บาท")
print(f"ยอดที่ 'ระบบเติมเอง' (เสี่ยง) : {money_risk:,.2f} บาท "
      f"({(money_risk/money_all*100 if money_all else 0):.1f}%)")

print(f"\n── บิลที่ยอดตัดสินไม่ได้อ่านจากเอกสาร: {len(risk)} ใบ ──")
unflagged = []
for b, bad, codes in risk:
    tag = f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
    told = [c for c in codes if c.startswith("VAT")]
    print(f"  {tag}: เติมเอง={bad} sub={b.get('subtotal')} vat={b.get('vat')} "
          f"conf={b.get('amount_confidence')} → กฎที่ฟ้อง={codes or '(เงียบ)'}")
    if not told:
        unflagged.append(tag)

print("=" * 78)
if unflagged:
    print(f"\n❌ {len(unflagged)} ใบ: ยอดถูกเติมเอง แต่ไม่มีกฎตระกูล VAT* แจ้งเลย")
    print("   → VAT001/002/003 เทียบค่าที่ระบบเพิ่งคำนวณกับตัวมันเอง = 'ตรง' หลอก (ADR-182)")
    for t in unflagged[:20]:
        print("     •", t)
    print("\n   หมายเหตุ: r_vat010 ('VAT ไม่ได้ตรวจจริง') ถูกตั้ง enabled=False")
    print("   (rules_engine.py: 'v9.1: ปิด/ลบการทำงานตามคำขอ') → ต้องให้เจ้าของระบบตัดสิน")
elif risk:
    print("\n✅ ทุกใบที่ยอดถูกเติมเอง มีกฎ VAT* แจ้งแล้ว")
else:
    print("\n✅ ทุกใบอ่านยอดตัดสิน (subtotal+vat) จากเอกสารจริง")
