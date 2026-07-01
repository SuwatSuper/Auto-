# -*- coding: utf-8 -*-
"""test_forward_compat.py — [ADR-088 / FC-1] ตาข่ายกัน "ระบบล้าหลังเงียบ" (5-year rot tripwire)

ที่มา: core paths (pukpui_modular_base / golden_master / verify_golden) เรียก
  warnings.filterwarnings('ignore') แบบ global เพื่อกลบ noise ตอนอ่าน .xls
  → ผลข้างเคียง: DeprecationWarning / FutureWarning ถูกกลบไปด้วย. ในโหมด "freeze"
  ไม่กระทบ แต่ตอน "กลับมาแก้ปีที่ 4-5" (bump pandas/numpy/Python) deprecation จะถูก
  กลืนเงียบ → ระบบทำงานต่อจน API ที่ deprecated ถูกถอด แล้วพังกะทันหันโดยไม่มีสัญญาณ.

ด่านนี้: รัน parse จริง (fixtures) โดย "ปลด" การกลบ warning แล้วบังคับว่า
  **ห้ามมี Deprecation/Future จากโค้ดของเราเอง** (= idiom ตกยุคที่เราเขียน).
  ถ้า dep-bump ในอนาคตทำให้ idiom เราตกยุค → ด่านนี้แดงทันที (ก่อนของถูกถอดจริง).

ขอบเขต/เจตนา:
  • fail เฉพาะ warning ที่ "ต้นทาง" อยู่ในไฟล์ของเรา (actionable — เราแก้ได้)
  • third-party (ใน deps) แค่ "รายงาน" ไม่ทำ CI ตก (เราแก้ที่โค้ดเขาไม่ได้ + deps freeze แล้ว)
  • golden-neutral: เป็น test ล้วน — ไม่แตะ production / ไม่กระทบการคำนวณ → hash ไม่ขยับ
"""
import os
import sys
import glob
import io
import importlib
import contextlib
import warnings

HERE = os.path.dirname(os.path.abspath(__file__))
# หมวดที่นับว่าเป็น "สัญญาณของล้าหลัง"
_ROT = (DeprecationWarning, FutureWarning, PendingDeprecationWarning)


def _is_ours(filename: str) -> bool:
    """warning นี้มาจากซอร์สของเราเอง (ไม่ใช่ deps ใน site-packages / stdlib)?"""
    if not filename:
        return False
    fp = os.path.abspath(filename)
    if HERE not in fp:
        return False
    low = fp.replace("\\", "/").lower()
    return ("site-packages" not in low) and ("/lib/python" not in low) and ("dist-packages" not in low)


def main() -> int:
    # import app (จุดนี้ trigger global filterwarnings('ignore') ของ core)
    app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")

    # คลุมทั้ง 2 read path: openpyxl (.xlsx, fixtures) + xlrd (.xls, real_cases ถ้ามี)
    files = sorted(glob.glob(os.path.join(HERE, "tests", "fixtures", "*.xlsx")))
    files += sorted(glob.glob(os.path.join(HERE, "tests", "real_cases", "*.xls")))
    if not files:
        print("RESULT: ❌ ไม่พบไฟล์ทดสอบ (fixtures/real_cases) — ตาข่าย forward-compat รันไม่ได้")
        return 1

    # ปลดการกลบ warning ที่ core ตั้งไว้ แล้วจับให้หมด
    warnings.resetwarnings()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # เงียบ stdout/stderr ของ pipeline (เราสนใจแค่ warning ที่ record ไว้)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            all_bills, _fn = app.parse_all_files(files)
            try:
                from golden_snapshot import MASTER
                app.run_audit_core(all_bills, MASTER, isolate=True)
            except Exception:
                # ด่านนี้โฟกัสเส้น parse (จุดที่ idiom pandas/openpyxl ตกยุคจะโผล่) —
                # audit core ล้มด้วยเหตุอื่นไม่เกี่ยว ปล่อยผ่าน (มีด่านอื่นคุม)
                pass

    ours = []
    third = []
    for w in caught:
        if not isinstance(w.message, _ROT) and w.category not in _ROT:
            continue
        cat = w.category.__name__
        fn = os.path.basename(w.filename or "?")
        msg = str(w.message)[:110]
        (ours if _is_ours(w.filename) else third).append((cat, fn, w.lineno, msg))

    if third:
        print("ℹ third-party deprecation (deps — ไม่ทำ CI ตก, ไว้เป็นสัญญาณตอนวางแผน upgrade):")
        seen = set()
        for cat, fn, ln, msg in third:
            key = (cat, fn)
            if key in seen:
                continue
            seen.add(key)
            print(f"     ⚠ {cat} @ {fn} — {msg}")

    print("=" * 64)
    if ours:
        print(f"RESULT: ❌ พบ {len(ours)} Deprecation/Future จาก \"โค้ดของเรา\" — idiom ตกยุค ต้องแก้:")
        for cat, fn, ln, msg in ours:
            print(f"   ❌ {cat} {fn}:{ln} — {msg}")
        print("   (แก้ที่ call-site ในไฟล์ของเรา ให้ใช้ API ที่ไม่ deprecated — golden ต้องไม่ขยับ)")
        return 1
    print("RESULT: ✅ forward-compat สะอาด — ไม่มี idiom ตกยุคจากโค้ดของเราใน parse path "
          f"({len(files)} fixtures, deps={'มี' if third else 'ไม่มี'} third-party deprecation)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
