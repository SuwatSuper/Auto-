# -*- coding: utf-8 -*-
"""oracle_zero_lines.py — วัดผลกระทบของช่องโหว่ 'ศูนย์ถูกมองเป็นค่าหาย' ใน ITM001

ORACLE: อ่านบิลจาก engine แล้วนับบรรทัดที่
  qty/price/amount "มีค่าอยู่จริง (ไม่ใช่ None)" แต่ตัวใดตัวหนึ่งเป็น 0
  และ qty×price ≠ amount  → ต้องถูกฟ้อง แต่ ITM001 ข้ามเพราะ `not (a and b and c)`

รัน:  python3 oracle_zero_lines.py <data_dir>
"""
import sys
import os
import io
import glob
import contextlib
import importlib

DATA = sys.argv[1] if len(sys.argv) > 1 else "tests/real_cases"

app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
files = sorted(glob.glob(os.path.join(DATA, "*.xls*")))
with contextlib.redirect_stdout(io.StringIO()):
    app.reset_run_state()
    bills, fi = app.parse_all_files(files)
    for b in bills:
        app.compute_bill_confidence(b)
    app.run_audit_core(bills, {}, isolate=True)

TOL = 0.01
n_lines = n_zero = n_blind = 0
blind = []
for b in bills:
    for it in (b.get("items") or []):
        if not isinstance(it, dict):
            continue
        q, p, a = it.get("qty"), it.get("price"), it.get("amount")
        if not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                   for x in (q, p, a)):
            continue
        n_lines += 1
        has_zero = (q == 0 or p == 0 or a == 0)
        if not has_zero:
            continue
        n_zero += 1
        if abs(q * p - a) > TOL:                      # ผิดจริง แต่ ITM001 ข้าม
            n_blind += 1
            blind.append(f"{b['file']}#{b['sheet']}/{b.get('iv_number')} "
                         f"#{it.get('seq')}: qty={q} price={p} amount={a} "
                         f"→ ควรได้ {round(q*p,2)} (ต่าง {round(a-q*p,2)})")

print(f"data={DATA}  บิล={len(bills)}  บรรทัดที่ตรวจได้={n_lines}")
print(f"  บรรทัดที่มีศูนย์อย่างน้อยหนึ่งช่อง : {n_zero}")
print(f"  ในนั้น qty×price ≠ amount (ตาบอด) : {n_blind}")
for x in blind[:30]:
    print("    •", x)
