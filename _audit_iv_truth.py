# -*- coding: utf-8 -*-
"""_audit_iv_truth.py — ตรวจอิสระ: เลขที่เอกสาร (iv_number) ที่ระบบรายงาน
ตรงกับ "เลขจริงในเซลล์ของไฟล์" หรือไม่ — ทั้ง 834 บิล.

วิธี (อิสระจาก scoring ของ parser): เปิดไฟล์ดิบ (xlrd/.xls, openpyxl/.xlsx) อ่าน
ทุกเซลล์พร้อม "ชนิดเซลล์จริง" (TEXT/NUMBER/DATE) แล้วจำแนกว่า iv_number ที่ระบบอ่าน
ปรากฏในชีตอย่างไร:
  TEXT_EXACT     เซลล์ข้อความตรงเป๊ะ                         → ✅ อ่านถูก (เลขเอกสารคือ text)
  NUM_INT_EXACT  เซลล์ตัวเลขจำนวนเต็ม = เลขนั้น               → ✅ อ่านถูก (เลขเอกสารเป็น numeric)
  TEXT_CONTAINS  เซลล์ข้อความที่ "มี" เลขนั้นอยู่ (prefix/suffix) → ✅ อ่านถูก
  FLOAT_TAIL     เลขตรงกับ "หางทศนิยม" ของ float (เช่น .04000000001) → ❌ บั๊ก (คว้าเศษ float)
  MONEY_FRAGMENT เลขเป็นชิ้นส่วนของเซลล์เงิน/ตัวเลขเท่านั้น    → ⚠️ ต้องรีเช็ค
  DATE_FRAGMENT  เลขมาจาก serial วันที่                        → ⚠️ ต้องรีเช็ค
  NOT_FOUND      ไม่พบเลขนี้ในเซลล์ใดของชีตเลย                  → ⚠️ ต้องรีเช็ค (อาจกุ/ผิด)

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 _audit_iv_truth.py
"""
import contextlib, io, os, sys, glob, re, json

os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
sys.path.insert(0, ".")
os.chdir(os.path.dirname(os.path.abspath(__file__)) or ".")

with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import xlrd

try:
    import openpyxl
except Exception:
    openpyxl = None


def norm(x):
    return re.sub(r"[^0-9A-Za-z]", "", str(x or "")).upper()


def digits(x):
    return re.sub(r"\D", "", str(x or ""))


# ── อ่านเซลล์ดิบทั้งชีต: คืน dict[sheet_name] -> list[(r,c,value,kind)] ─────
# kind: 'T'=text 'N'=number 'D'=date
_CACHE = {}


def read_cells(path):
    if path in _CACHE:
        return _CACHE[path]
    sheets = {}
    if path.lower().endswith(".xlsx"):
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        for ws in wb.worksheets:
            rows = []
            for r, row in enumerate(ws.iter_rows()):
                for cell in row:
                    v = cell.value
                    if v is None or v == "":
                        continue
                    dt = cell.data_type  # 's','n','d','f',...
                    kind = "D" if dt == "d" else ("N" if isinstance(v, (int, float)) and dt != "s" else "T")
                    rows.append((r, cell.column - 1, v, kind))
            sheets[ws.title] = rows
        wb.close()
    else:
        bk = xlrd.open_workbook(path)
        for sh in bk.sheets():
            rows = []
            for r in range(sh.nrows):
                for c in range(sh.ncols):
                    v = sh.cell_value(r, c)
                    t = sh.cell_type(r, c)
                    if v == "" or v is None:
                        continue
                    kind = "T" if t == 1 else ("N" if t == 2 else ("D" if t == 3 else "?"))
                    rows.append((r, c, v, kind))
            sheets[sh.name] = rows
    _CACHE[path] = sheets
    return sheets


def classify(target, cells):
    """คืน (class, cell_ref, cell_repr) ของ match ที่ดีที่สุด"""
    tgt = norm(target)
    tdig = digits(target)
    if not tgt:
        return ("EMPTY", "", "")
    best = ("NOT_FOUND", "", "")
    rank = {
        "TEXT_EXACT": 6, "NUM_INT_EXACT": 5, "TEXT_CONTAINS": 4,
        "DATE_FRAGMENT": 3, "FLOAT_TAIL": 2, "MONEY_FRAGMENT": 1, "NOT_FOUND": 0,
    }
    for (r, c, v, kind) in cells:
        if kind == "T":
            nv = norm(v)
            if not nv:
                continue
            if nv == tgt:
                return ("TEXT_EXACT", f"[{r},{c}]", repr(v))  # ดีที่สุด — คืนทันที
            if tgt and tgt in nv:
                cand = ("TEXT_CONTAINS", f"[{r},{c}]", repr(v))
                if rank[cand[0]] > rank[best[0]]:
                    best = cand
        elif kind == "N":
            try:
                fv = float(v)
            except Exception:
                continue
            s = repr(fv)
            # จำนวนเต็มตรงเป๊ะ (เลขเอกสาร numeric ที่ถูกต้อง)
            if fv == int(fv) and tdig and str(int(fv)) == tdig:
                cand = ("NUM_INT_EXACT", f"[{r},{c}]", s)
                if rank[cand[0]] > rank[best[0]]:
                    best = cand
                continue
            # หางทศนิยม float (บั๊ก TNT): target == ส่วนหลังจุด
            if "." in s and tdig:
                ipart, fpart = s.split(".", 1)
                if fpart == tdig or fpart.rstrip("0") == tdig or tdig == fpart:
                    cand = ("FLOAT_TAIL", f"[{r},{c}]", s)
                    if rank[cand[0]] > rank[best[0]]:
                        best = cand
                    continue
                # target เป็นชิ้นส่วนของตัวเลข (เช่น อยู่กลางยอดเงิน)
                if tdig in s.replace(".", ""):
                    cand = ("MONEY_FRAGMENT", f"[{r},{c}]", s)
                    if rank[cand[0]] > rank[best[0]]:
                        best = cand
            elif tdig and tdig in s:
                cand = ("MONEY_FRAGMENT", f"[{r},{c}]", s)
                if rank[cand[0]] > rank[best[0]]:
                    best = cand
        elif kind == "D":
            if tdig and tdig in digits(v):
                cand = ("DATE_FRAGMENT", f"[{r},{c}]", repr(v))
                if rank[cand[0]] > rank[best[0]]:
                    best = cand
    return best


def main():
    data = sys.argv[1] if len(sys.argv) > 1 else "/mnt/project"
    files = sorted(glob.glob(os.path.join(data, "*.xls")) + glob.glob(os.path.join(data, "*.xlsx")))
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        all_bills, _ = app.parse_all_files(files)

    from collections import Counter, defaultdict

    counts = Counter()
    flagged = []  # (class, file, sheet, block, iv_number, iv_raw, cell_ref, cell_repr)
    for b in all_bills:
        path = b.get("filepath") or b.get("file")
        sheet = str(b.get("sheet"))
        iv = b.get("iv_number")
        raw = b.get("iv_number_raw") or iv
        try:
            sheets = read_cells(path)
        except Exception as e:
            counts["READ_ERROR"] += 1
            flagged.append(("READ_ERROR", os.path.basename(path), sheet, b.get("block_idx"), iv, raw, "", str(e)[:40]))
            continue
        cells = sheets.get(sheet)
        if cells is None and " + " in sheet:
            # ชื่อชีตแบบรวม (parser รวมหลายชีตเป็นบล็อกเดียว) เช่น '4 + 4 (2)'
            merged = []
            for part in sheet.split(" + "):
                merged.extend(sheets.get(part.strip(), []))
            if merged:
                cells = merged
        if cells is None:
            for sn, cc in sheets.items():
                if str(sn) == sheet:
                    cells = cc
                    break
        if cells is None:
            counts["SHEET_MISSING"] += 1
            flagged.append(("SHEET_MISSING", os.path.basename(path), sheet, b.get("block_idx"), iv, raw, "", f"sheets={list(sheets)[:6]}"))
            continue
        cls, ref, rep = classify(raw, cells)
        counts[cls] += 1
        if cls in ("FLOAT_TAIL", "MONEY_FRAGMENT", "DATE_FRAGMENT", "NOT_FOUND"):
            flagged.append((cls, os.path.basename(path), sheet, b.get("block_idx"), iv, raw, ref, rep))

    print("=" * 70)
    print("ตรวจความตรงของ เลขที่เอกสาร (iv_number) — 834 บิล / อิสระจาก parser")
    print("=" * 70)
    total = sum(counts.values())
    GOOD = {"TEXT_EXACT", "NUM_INT_EXACT", "TEXT_CONTAINS"}
    good = sum(v for k, v in counts.items() if k in GOOD)
    print(f"รวม {total} บิล")
    print("-" * 70)
    for k in ["TEXT_EXACT", "NUM_INT_EXACT", "TEXT_CONTAINS",
              "FLOAT_TAIL", "MONEY_FRAGMENT", "DATE_FRAGMENT", "NOT_FOUND",
              "SHEET_MISSING", "READ_ERROR", "EMPTY"]:
        if counts.get(k):
            mark = "✅" if k in GOOD else "❌" if k == "FLOAT_TAIL" else "⚠️"
            print(f"  {mark} {k:14} : {counts[k]}")
    print("-" * 70)
    print(f"อ่านถูก (faithful) : {good}/{total}  ({100*good/total:.1f}%)")
    print(f"ต้องรีเช็ค          : {total-good}")
    if flagged:
        print("\n" + "=" * 70)
        print(f"รายการต้องรีเช็ค ({len(flagged)}):")
        print("=" * 70)
        for cls, f, sh, blk, iv, raw, ref, rep in flagged[:80]:
            print(f"  [{cls}] {f} ชีต'{sh}' บล็อก{blk}")
            print(f"        iv_number={iv!r}  raw={raw!r}  match={ref} {rep}")
    else:
        print("\n✅ ไม่มีบิลที่ต้องรีเช็ค — เลขที่เอกสารทุกใบอ่านตรงเซลล์จริง")
    # เขียนผลละเอียดเป็น JSON ไว้ตรวจซ้ำ
    with open("_iv_truth_report.json", "w", encoding="utf-8") as fh:
        json.dump({"counts": dict(counts), "flagged": flagged}, fh, ensure_ascii=False, indent=1)
    return 0 if counts.get("FLOAT_TAIL", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
