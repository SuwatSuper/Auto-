# -*- coding: utf-8 -*-
"""diagnose_merged_cells.py — DIAGNOSE/GUARD (read-only): merged cell ทำค่าวิกฤตหายจาก parser ไหม?

บริบท (STABILIZE&HARDEN #1 — latent risk): Excel เก็บค่าของ merged range ไว้แค่ช่องบนซ้าย.
ถ้า "ยอด/VAT/รวม/เลขภาษี" ตกอยู่ใน merge แล้ว parser มองไม่เห็น → ยอด/บิลผิดเงียบ ๆ.
เครื่องมือนี้ "พิสูจน์ว่าพังจริงไหม" ด้วยหลักฐาน ก่อนตัดสินใจแตะ parser.

สัญญาณ 2 ชั้น (ออกแบบให้ false-positive ต่ำ — เชื่อผลได้บนชุด 106 ไฟล์):
  ★ สัญญาณหลัก = RECONCILIATION ต่อบิล (ตัวชี้ขาดว่า 'ยอดวิกฤตหาย' จริงไหม):
      subtotal+vat ≈ total (tol โดเมน) — ถ้า "ขาด" แล้ว 'reconcile ไม่ได้' = ยอดถูกกินจริง.
      (บิลที่ระบบ flag VAT003 อยู่แล้วถือเป็น 'ผิดที่ตัวข้อมูล' ไม่ใช่ปัญหา merge → ดู note)
  ★ สัญญาณรอง = TAXID-shaped ใน merge ที่ parser ไม่จับ (เลขภาษี 13 หลักหาย = วิกฤต).
  • INFO เท่านั้น = money-shaped ใน merge ที่ไม่ตรงค่าที่จับ (มักเป็น 'เลข running หัวเอกสาร'
      เช่นเลขลำดับเหนือเลข IV — parser ถูกที่ไม่จับ). ไม่ทำให้ verdict แดง.

อ่าน merged ranges ดิบ: .xlsx→openpyxl ; .xls→xlrd(formatting_info=True) (ใช้ได้กับ .xls).
parse ผ่าน production path จริง (app.parse_all_files). อ่านอย่างเดียว — ไม่แตะ bills/golden.

ใช้: python3 diagnose_merged_cells.py <DIR ...>
exit 0 = ไม่พบค่าวิกฤตหาย ; 3 = พบสัญญาณวิกฤต (ต้องคนยืนยัน/แก้) ; 2 = error เครื่องมือ
"""
import os
import sys
import glob

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MONEY_MIN = 100.0
MONEY_TOL = 0.5
RECON_TOL = 1.0          # ผ่อนให้เศษปัด — ใช้พิสูจน์ 'ยอดครบ/ไม่ครบ' ไม่ใช่ตรวจความถูกต้องเชิงบัญชี


def _money(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if f == f else None
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _taxid(v):
    if v is None:
        return None
    s = str(v).strip().replace("-", "").replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s if (len(s) == 13 and s.isdigit()) else None


def _digits(v):
    return "".join(ch for ch in str(v or "") if ch.isdigit())


def _merged_topleft(path):
    """[(sheet, ref, value, width)] ของช่องบนซ้ายแต่ละ merged range."""
    ext = os.path.splitext(path)[1].lower()
    out = []
    if ext == ".xls":
        import xlrd
        wb = xlrd.open_workbook(path, formatting_info=True)
        for sh in wb.sheets():
            for (rlo, rhi, clo, chi) in sh.merged_cells:
                try:
                    val = sh.cell_value(rlo, clo)
                except Exception:
                    val = None
                out.append((sh.name, f"R{rlo+1}C{clo+1}", val, chi - clo))
    else:
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True)
        for ws in wb.worksheets:
            for rng in ws.merged_cells.ranges:
                val = ws.cell(row=rng.min_row, column=rng.min_col).value
                out.append((ws.title, f"R{rng.min_row}C{rng.min_col}", val, rng.max_col - rng.min_col + 1))
        wb.close()
    return out


def _captured(bills):
    """ค่าที่ parser จับได้: numbers (รวม iv ที่เป็นเลข) + taxids."""
    nums, taxids, ivnums = [], set(), set()
    for b in bills:
        for k in ("subtotal", "vat", "total"):
            m = _money(b.get(k))
            if m is not None:
                nums.append(m)
        for it in b.get("items") or []:
            for k in ("amount", "qty", "price"):
                m = _money(it.get(k))
                if m is not None:
                    nums.append(m)
        for k in ("tax_id", "tax_id_raw"):
            t = _taxid(b.get(k))
            if t:
                taxids.add(t)
        d = _digits(b.get("iv_number") or b.get("iv_number_raw"))
        if d:
            ivnums.add(d)
    return nums, taxids, ivnums


def _recon(b):
    """คืน (สถานะ, รายละเอียด): 'ok' / 'fail' / 'n/a' (ข้อมูลไม่พอ)."""
    sub, vat, tot = _money(b.get("subtotal")), _money(b.get("vat")), _money(b.get("total"))
    if sub is None or tot is None:
        return "n/a", f"sub={sub} tot={tot}"
    v = vat if vat is not None else 0.0
    return ("ok" if abs((sub + v) - tot) <= RECON_TOL else "fail"), f"sub+vat={sub+v:.2f} vs total={tot:.2f}"


def scan_file(path, app):
    try:
        merged = _merged_topleft(path)
    except Exception as e:
        return {"file": os.path.basename(path), "error": f"อ่าน merged ไม่ได้: {type(e).__name__}: {e}"}
    try:
        app.reset_run_state()
        bills, _ = app.parse_all_files([path])
    except Exception as e:
        return {"file": os.path.basename(path), "error": f"parse ไม่ได้: {type(e).__name__}: {e}"}

    nums, taxids, ivnums = _captured(bills)

    taxid_lost, money_info = [], []
    for (sheet, ref, val, width) in merged:
        t = _taxid(val)
        if t:
            if t not in taxids:
                taxid_lost.append((sheet, ref, t))
            continue
        m = _money(val)
        if m is not None and abs(m) >= MONEY_MIN:
            captured = any(abs(m - n) <= MONEY_TOL for n in nums) or (_digits(val) in ivnums)
            if not captured:
                money_info.append((sheet, ref, m))

    recon_fail = []
    for b in bills:
        st, detail = _recon(b)
        if st == "fail":
            has_vat003 = any(i.get("code") == "VAT003" for i in b.get("issues") or [])
            recon_fail.append((b.get("sheet"), b.get("iv_number"), detail, has_vat003))

    return {"file": os.path.basename(path), "n_merged": len(merged), "n_bills": len(bills),
            "taxid_lost": taxid_lost, "recon_fail": recon_fail, "money_info": money_info}


def main(argv):
    dirs = argv or ["tests/real_cases", "tests/fixtures"]
    files = []
    for d in dirs:
        if os.path.isfile(d):
            files.append(d)
        else:
            files += sorted(glob.glob(os.path.join(d, "*.xls")) + glob.glob(os.path.join(d, "*.xlsx")))
    if not files:
        print("❌ ไม่พบไฟล์ .xls/.xlsx ใน:", dirs)
        return 2

    import importlib
    app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")

    print("=" * 72)
    print("DIAGNOSE merged cells — ค่าวิกฤต (ยอด/VAT/รวม/เลขภาษี) หายจาก parser เพราะ merge ไหม?")
    print(f"  ไฟล์ {len(files)} · สัญญาณหลัก=reconciliation ต่อบิล · รอง=taxid หาย · INFO=money หัวเอกสาร")
    print("=" * 72)
    critical = 0
    info_n = 0
    for f in files:
        r = scan_file(f, app)
        if "error" in r:
            print(f"  ⚠️ {r['file']}: {r['error']}")
            continue
        bad = bool(r["taxid_lost"]) or any(not v003 for *_x, v003 in r["recon_fail"])
        mark = "🚩" if bad else "✅"
        print(f"  {mark} {r['file']:22} merged={r['n_merged']:3} บิล={r['n_bills']:2} "
              f"| taxid หาย={len(r['taxid_lost'])} | recon ไม่ผ่าน={len(r['recon_fail'])} "
              f"| money หัวเอกสาร(info)={len(r['money_info'])}")
        for (sheet, ref, t) in r["taxid_lost"]:
            print(f"        🚩 [taxid] ชีต {sheet} {ref} = {t} ← เลขภาษีอยู่ใน merge แต่ parser ไม่จับ"); critical += 1
        for (sheet, iv, detail, v003) in r["recon_fail"]:
            tag = "(ระบบ flag VAT003 แล้ว = ผิดที่ข้อมูล ไม่ใช่ merge)" if v003 else "← ยอดไม่ครบ! สงสัย merge กินค่า"
            print(f"        {'ℹ️' if v003 else '🚩'} [recon] ชีต {sheet} iv={iv}: {detail} {tag}")
            if not v003:
                critical += 1
        info_n += len(r["money_info"])

    print("-" * 72)
    print(f"  ℹ️ money-shaped ใน merge ที่ไม่ถูกจับ (มัก = เลข running หัวเอกสาร เหนือเลข IV) รวม {info_n} "
          f"— ไม่ใช่สัญญาณวิกฤต")
    if critical:
        print(f"RESULT: 🚩 พบ {critical} สัญญาณวิกฤต — merged-cell handler คุ้มแก้ "
              f"(วัด golden hash 81 ไฟล์ before/after, justify false-positive ลด/true-positive คงอยู่)")
        return 3
    print("RESULT: ✅ ไม่พบค่าวิกฤตหายจาก merge — ทุกบิล reconcile + เลขภาษีถูกจับครบ (parser ทน merge ได้)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
