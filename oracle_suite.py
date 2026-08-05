# -*- coding: utf-8 -*-
"""oracle_suite.py — ORACLE อิสระ (§3.1 ของ CLAUDE_CODE_BUGHUNT.md)

อ่านไฟล์ Excel ดิบเอง คำนวณเอง แล้วเทียบกับผลของ engine
จุดที่สองฝั่งไม่ตรง = บั๊ก

ใช้:  python3 oracle_suite.py <data_dir>
"""
import sys
import os
import io
import glob
import json
import math
import contextlib
import importlib
from collections import defaultdict, Counter

import pandas as pd

DATA = sys.argv[1] if len(sys.argv) > 1 else "tests/real_cases"

# ────────────────────────────────────────────────────────────────
# 1. โหลดผลของ engine
# ────────────────────────────────────────────────────────────────
app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
files = sorted(glob.glob(os.path.join(DATA, "*.xls*")))

with contextlib.redirect_stdout(io.StringIO()):
    app.reset_run_state()
    bills, fi = app.parse_all_files(files)
    for b in bills:
        app.compute_bill_confidence(b)
    app.run_audit_core(bills, {}, isolate=True)

print(f"engine: {len(files)} ไฟล์ → {len(bills)} บิล")

# ────────────────────────────────────────────────────────────────
# 2. อ่านชีตดิบเอง (oracle side)
# ────────────────────────────────────────────────────────────────
RAW = {}          # (file, sheet) -> matrix ของ object
for p in files:
    try:
        xl = pd.ExcelFile(p)
    except Exception as e:                                    # pragma: no cover
        print(f"  !! เปิดไม่ได้ {p}: {e}")
        continue
    for sh in xl.sheet_names:
        df = pd.read_excel(p, sheet_name=sh, header=None)
        RAW[(os.path.basename(p), str(sh))] = df.to_numpy(dtype=object)

print(f"oracle: อ่านดิบ {len(RAW)} ชีต")


def cells(fname, sheet):
    return RAW.get((fname, str(sheet)))


def all_numbers(M):
    """เลขทุกตัวในชีต (float) — ใช้ตรวจ 'ค่านี้มีอยู่จริงในชีตไหม'"""
    out = []
    if M is None:
        return out
    for row in M:
        for v in row:
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
                out.append(float(v))
            elif isinstance(v, str):
                s = v.replace(",", "").replace("฿", "").strip()
                try:
                    out.append(float(s))
                except ValueError:
                    pass
    return out


def all_strings(M):
    out = []
    if M is None:
        return out
    for row in M:
        for v in row:
            if isinstance(v, str) and v.strip():
                out.append(v)
    return out


def near(a, b, tol=0.005):
    return a is not None and b is not None and abs(a - b) <= tol


def present(val, pool, tol=0.005):
    return any(abs(val - p) <= tol for p in pool)


FINDINGS = defaultdict(list)


def report(oracle, msg):
    FINDINGS[oracle].append(msg)


# ────────────────────────────────────────────────────────────────
# ORACLE A — เลขคณิตในบิล
#   ผลรวมรายการ = subtotal · subtotal×7% = vat · subtotal+vat = total
# ────────────────────────────────────────────────────────────────
for b in bills:
    st, vt, tt = b.get("subtotal"), b.get("vat"), b.get("total")
    tag = f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
    if st is not None and vt is not None:
        if not near(round(st * 0.07, 2), vt, 0.51):
            report("A_vat7", f"{tag}: subtotal={st} ×7% = {round(st*0.07,2)} แต่ vat={vt}")
    if st is not None and vt is not None and tt is not None:
        if not near(round(st + vt, 2), tt, 0.02):
            report("A_total", f"{tag}: {st}+{vt}={round(st+vt,2)} แต่ total={tt}")
    items = b.get("items") or []
    isum = sum(it["amount"] for it in items
               if isinstance(it, dict) and isinstance(it.get("amount"), (int, float)))
    if items and st is not None and not near(round(isum, 2), st, 0.02):
        report("A_itemsum", f"{tag}: ผลรวมรายการ={round(isum,2)} แต่ subtotal={st} "
                            f"(ต่าง {round(st-isum,2)})")

# ────────────────────────────────────────────────────────────────
# ORACLE B — provenance : ยอดต้องมาจากเอกสาร ไม่ใช่คำนวณเอง
# ────────────────────────────────────────────────────────────────
for b in bills:
    src = b.get("amount_source") or {}
    tag = f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
    for fld in ("subtotal", "vat", "total"):
        s = src.get(fld)
        if s in (None, "", "unknown"):
            report("B_prov_missing", f"{tag}: {fld} ไม่มี amount_source")
    if src.get("subtotal") == "itemsum" and src.get("vat") in ("derived", "itemsum"):
        report("B_prov_selfref",
               f"{tag}: subtotal=itemsum และ vat=derived → VAT001 เทียบตัวเอง (ADR-182)")

# ────────────────────────────────────────────────────────────────
# ORACLE C — บรรทัดรายการ : qty × price = amount
# ────────────────────────────────────────────────────────────────
for b in bills:
    tag = f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
    for it in (b.get("items") or []):
        if not isinstance(it, dict):
            continue
        q, p, a = it.get("qty"), it.get("price"), it.get("amount")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                   for x in (q, p, a)):
            continue
        exp = round(q * p, 2)
        if near(exp, a, 0.02):
            continue
        disc = it.get("discount")
        if isinstance(disc, (int, float)) and near(round(exp - disc, 2), a, 0.02):
            continue
        report("C_qxp", f"{tag} #{it.get('seq')}: {q}×{p}={exp} แต่ amount={a} "
                        f"(discount={disc!r}) ต่าง {round(a-exp,2)}")

# ────────────────────────────────────────────────────────────────
# ORACLE D — ความซื่อสัตย์ค่า : ทุกค่าต้องมีอยู่จริงในเซลล์ของชีตนั้น
# ────────────────────────────────────────────────────────────────
for b in bills:
    M = cells(b["file"], b["sheet"])
    if M is None:
        report("D_sheet_missing", f"{b['file']}#{b['sheet']}: oracle อ่านชีตนี้ไม่เจอ")
        continue
    nums = all_numbers(M)
    tag = f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
    for fld in ("subtotal", "vat", "total"):
        v = b.get(fld)
        if isinstance(v, (int, float)) and not present(v, nums, 0.02):
            src = (b.get("amount_source") or {}).get(fld)
            if src in ("derived", "itemsum", "calc"):
                continue          # ประกาศตัวว่าคำนวณเอง = ถูกต้องตามสัญญา
            report("D_ghost_money",
                   f"{tag}: {fld}={v} (source={src}) ไม่มีอยู่ในเซลล์ใดของชีตนี้")
    for it in (b.get("items") or []):
        if not isinstance(it, dict):
            continue
        for fld in ("qty", "price", "amount"):
            v = it.get(fld)
            if isinstance(v, (int, float)) and not isinstance(v, bool) \
               and not present(v, nums, 0.02):
                report("D_ghost_item",
                       f"{tag} #{it.get('seq')}: {fld}={v} ไม่มีในเซลล์ของชีตนี้")

# ────────────────────────────────────────────────────────────────
# ORACLE E — ครบชีต : ชีตที่มีลายเซ็นใบกำกับต้องออกบิล
# ────────────────────────────────────────────────────────────────
got = {(b["file"], str(b["sheet"])) for b in bills}
SIG_WORDS = ("ใบกำกับภาษี", "เลขประจำตัวผู้เสียภาษี", "ภาษีมูลค่าเพิ่ม")
for (fname, sh), M in sorted(RAW.items()):
    if (fname, sh) in got:
        continue
    txt = " ".join(all_strings(M))
    hits = [w for w in SIG_WORDS if w in txt]
    has7 = ("7%" in txt) or ("7 %" in txt)
    if len(hits) >= 2 or (hits and has7):
        report("E_lost_sheet",
               f"{fname}#{sh}: มีลายเซ็นใบกำกับ {hits} (7%={has7}) แต่ไม่ออกบิล")

# ────────────────────────────────────────────────────────────────
# ORACLE F — เลขซ้ำ : IV ซ้ำ (แยกผู้ขายเดียวกัน vs ข้ามผู้ขาย)
# ────────────────────────────────────────────────────────────────
byiv = defaultdict(list)
for b in bills:
    if b.get("iv_number"):
        byiv[str(b["iv_number"])].append(b)
for iv, grp in sorted(byiv.items()):
    if len(grp) < 2:
        continue
    keys = {(str(x.get("tax_id")), round(x.get("total") or 0, 2)) for x in grp}
    where = ", ".join(f"{x['file']}#{x['sheet']}" for x in grp)
    if len(keys) == 1:
        report("F_dup_money",
               f"IV {iv} ซ้ำ {len(grp)} ใบ ผู้ขาย+ยอดเดียวกัน = นับเงินซ้ำ ({where})")
    else:
        report("F_dup_cross", f"IV {iv} ซ้ำ {len(grp)} ใบ ข้ามผู้ขาย/ยอด ({where})")

# ────────────────────────────────────────────────────────────────
# ORACLE G — normalize เงียบ
# ────────────────────────────────────────────────────────────────
core = importlib.import_module("puopuy_core")
norm = getattr(core, "normalize_text", None)


def _ws(s):
    return " ".join(str(s).split())


if norm:
    for b in bills:
        tag = f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
        for fld, rawfld in (("company", "company_raw"), ("address", "address_raw"),
                            ("iv_number", "iv_number_raw"), ("tax_id", "tax_id_raw")):
            raw = b.get(rawfld)
            if not isinstance(raw, str):
                continue
            n = norm(raw)
            if n != raw and _ws(n) != _ws(raw):
                codes = {i.get("code") for i in (b.get("issues") or [])
                         if isinstance(i, dict)}
                flagged = codes & {"CMP007", "ADDR011", "ITM004", "CMP006"}
                if not flagged:
                    report("G_silent_norm",
                           f"{tag}: {rawfld} ถูก normalize เปลี่ยนรูป แต่ไม่มีกฎแจ้ง "
                           f"({raw!r} → {n!r})")

# ────────────────────────────────────────────────────────────────
# ORACLE H — เลขภาษี 13 หลัก checksum (mod 11)
# ────────────────────────────────────────────────────────────────
def tax13_ok(t):
    t = "".join(ch for ch in str(t) if ch.isdigit())
    if len(t) != 13:
        return None
    s = sum(int(t[i]) * (13 - i) for i in range(12))
    return (11 - (s % 11)) % 10 == int(t[12])


name_by_tax = defaultdict(set)
for b in bills:
    t, tag = b.get("tax_id"), f"{b['file']}#{b['sheet']}/{b.get('iv_number')}"
    if not t:
        continue
    ok = tax13_ok(t)
    if ok is False:
        codes = {i.get("code") for i in (b.get("issues") or []) if isinstance(i, dict)}
        if not (codes & {"TAX001", "TAX002", "TAX003", "TAX004", "TAX005",
                         "TAX006", "TAX007", "TAX008", "TAX009"}):
            report("H_taxsum", f"{tag}: เลขภาษี {t} checksum ไม่ผ่าน แต่ไม่มีกฎ TAX* แจ้ง")
    if b.get("company"):
        name_by_tax[str(t)].add(str(b["company"]))
for t, names in sorted(name_by_tax.items()):
    if len(names) > 1:
        report("H_tax_multiname", f"เลขภาษี {t} มีชื่อบริษัทต่างกัน {len(names)} ชื่อ: {sorted(names)}")

# ────────────────────────────────────────────────────────────────
# ORACLE I — footer: ยอดที่ engine อ่าน ต้องเป็นยอดของ "บิลนี้" ไม่ใช่ยอดรวมทั้งไฟล์
# ────────────────────────────────────────────────────────────────
tot_by_file = defaultdict(list)
for b in bills:
    if isinstance(b.get("total"), (int, float)):
        tot_by_file[b["file"]].append(b["total"])
for b in bills:
    tt = b.get("total")
    if not isinstance(tt, (int, float)):
        continue
    others = [x for x in tot_by_file[b["file"]] if x is not tt]
    if others and near(tt, round(sum(others), 2), 0.02):
        report("I_filetotal",
               f"{b['file']}#{b['sheet']}: total={tt} เท่ากับผลรวมบิลอื่นทั้งไฟล์ (ADR-179)")

# ────────────────────────────────────────────────────────────────
# สรุป
# ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("ORACLE FINDINGS")
print("=" * 70)
total = 0
for k in sorted(FINDINGS):
    v = FINDINGS[k]
    total += len(v)
    print(f"\n### {k} — {len(v)} จุด")
    for m in v[:15]:
        print("   ", m)
    if len(v) > 15:
        print(f"    ... อีก {len(v)-15}")
if not total:
    print("\n  (ไม่พบความต่างระหว่าง oracle กับ engine)")
print(f"\nรวม {total} จุด")

# รหัสที่ engine ฟ้อง (ใช้เทียบ diff ก่อน/หลังแก้)
codes = Counter()
for b in bills:
    for i in (b.get("issues") or []):
        if isinstance(i, dict) and i.get("code"):
            codes[i["code"]] += 1
print("\nรหัสที่ engine ฟ้อง:", dict(sorted(codes.items())))
