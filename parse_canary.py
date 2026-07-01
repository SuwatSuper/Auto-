# -*- coding: utf-8 -*-
"""parse_canary.py — เตือน "อัตราการ parse ร่วง" โดยไม่ต้องพึ่ง golden hash

ทำไมต้องมี (DECISIONS.md §5/§6): เคยมี regression `_FastFrame` ที่ทำบิลร่วง 836→52.
golden จับได้ (hash เปลี่ยน) แต่บอกแค่ "ต่าง" — ไม่บอกว่า "parse พัง". canary นี้บอกตรง ๆ
ว่า "บิลหาย X%, มีไฟล์ที่เคยอ่านได้แต่ตอนนี้ได้ 0 บิล กี่ไฟล์" และ **ใช้ได้กับข้อมูลใหม่
ที่ยังไม่มี golden** (เช่นชุดข้อมูลเดือนใหม่).

แนวคิด: parse ข้อมูลด้วย entry เดียวกับระบบจริง (`parse_all_files`) → ทำ "โปรไฟล์ parse"
(จำนวนบิล/ไฟล์, อัตราเฉลี่ย, บิลต่อไฟล์, ไฟล์ที่ได้ 0 บิล) แล้วเทียบกับ baseline ที่บันทึกไว้.

วิธีใช้:
    # 1) สร้าง canary baseline (ครั้งแรก บนชุดข้อมูลที่ถือว่า "ถูก")
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
        python3 parse_canary.py <data_dir> --write-baseline canary_baseline.json

    # 2) ตรวจ regression (ทุกครั้งหลังแก้ parser)
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
        python3 parse_canary.py <data_dir> --baseline canary_baseline.json [--drop-pct 10]

ถ้าไม่ระบุ --baseline แต่มี golden snapshot (มีคีย์ n_bills/n_files/file_names) จะใช้เป็น
ฐานเทียบ "หยาบ" ได้ (เทียบยอดรวม+จำนวนไฟล์ ; ไม่มีต่อ-ไฟล์):
    python3 parse_canary.py <data_dir> --golden baseline.json

exit 0 = อยู่ในเกณฑ์ (หรือไม่มีฐานเทียบ = เตือนเฉย ๆ), 1 = ร่วงเกินเกณฑ์, 2 = รันไม่สำเร็จ
"""
import os
import sys
import json
import glob
import argparse
import warnings
import importlib
import contextlib
import io

warnings.filterwarnings("ignore")

KIND = "parse_canary_baseline"


def _profile(data_dir):
    """parse data_dir แล้วคืนโปรไฟล์ (deterministic — reset state + กลืน stdout ที่รก)."""
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    os.chdir(here)
    file_list = sorted(
        glob.glob(os.path.join(data_dir, "*.xls")) + glob.glob(os.path.join(data_dir, "*.xlsx"))
    )
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
        app.reset_run_state()
        all_bills, _fn_issues = app.parse_all_files(file_list)

    per_file = {}
    for b in all_bills:
        # bill ผูกกับไฟล์ผ่านคีย์ 'file' (basename) — ดู parser.py
        fn = str(b.get("file", "?"))
        per_file[fn] = per_file.get(fn, 0) + 1
    n_files = len(file_list)
    n_bills = len(all_bills)
    names = [os.path.basename(f) for f in file_list]
    # ไฟล์ที่ "ได้ 0 บิล" = อยู่ในรายการไฟล์แต่ไม่โผล่ใน per_file (parse ไม่ออกบิล/ถูกข้าม)
    zero_files = sorted([n for n in names if per_file.get(n, 0) == 0])
    return {
        "_kind": KIND,
        "data_dir": os.path.abspath(data_dir),
        "n_files": n_files,
        "n_bills": n_bills,
        "parse_rate": round(n_bills / n_files, 4) if n_files else 0.0,
        "n_zero_files": len(zero_files),
        "zero_files": zero_files,
        "per_file": dict(sorted(per_file.items())),
    }


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _compare(now, base, drop_pct):
    """เทียบโปรไฟล์ปัจจุบันกับ baseline. คืน (fails:list, warns:list)."""
    fails, warns = [], []
    factor = 1.0 - (drop_pct / 100.0)

    b_bills = base.get("n_bills", 0)
    n_bills = now["n_bills"]
    if b_bills > 0 and n_bills < b_bills * factor:
        drop = 100.0 * (b_bills - n_bills) / b_bills
        fails.append(f"บิลรวมร่วง {b_bills} → {n_bills} (−{drop:.1f}% > เกณฑ์ {drop_pct:.0f}%)")
    elif n_bills < b_bills:
        warns.append(f"บิลรวมลดเล็กน้อย {b_bills} → {n_bills} (ในเกณฑ์)")
    elif n_bills > b_bills:
        warns.append(f"บิลรวมเพิ่ม {b_bills} → {n_bills} (อาจตั้งใจ — ทบทวนถ้าไม่คาด)")

    b_rate = base.get("parse_rate", 0.0)
    if b_rate > 0 and now["parse_rate"] < b_rate * factor:
        fails.append(
            f"อัตรา parse ร่วง {b_rate:.2f} → {now['parse_rate']:.2f} บิล/ไฟล์ (เกินเกณฑ์)"
        )

    # per-file: ไฟล์ที่ baseline เคย >0 แต่ตอนนี้ = 0 → "ไฟล์ยุบ" (ฟันที่คมที่สุดของ canary)
    b_per = base.get("per_file") or {}
    if b_per:
        collapsed = sorted(
            fn for fn, c in b_per.items() if c > 0 and now["per_file"].get(fn, 0) == 0
        )
        # ไฟล์ที่หายจาก data ไปเลย ≠ parser พัง → แยกเป็น warn
        present = set(now["per_file"].keys()) | set(now.get("zero_files", []))
        truly_collapsed = [fn for fn in collapsed if fn in present]
        missing = [fn for fn in collapsed if fn not in present]
        if truly_collapsed:
            fails.append(
                f"{len(truly_collapsed)} ไฟล์เคยอ่านได้แต่ตอนนี้ได้ 0 บิล "
                f"(เช่น {', '.join(truly_collapsed[:3])}{'…' if len(truly_collapsed) > 3 else ''})"
            )
        if missing:
            warns.append(f"{len(missing)} ไฟล์หายจากชุดข้อมูล (data เปลี่ยน ไม่ใช่ parser พัง)")
        # ไฟล์ที่บิลลดแต่ยังไม่ถึง 0 → warn
        reduced = sorted(
            fn
            for fn, c in b_per.items()
            if c > 0 and 0 < now["per_file"].get(fn, 0) < c
        )
        if reduced:
            warns.append(
                f"{len(reduced)} ไฟล์บิลลดลง (ยังไม่ถึง 0) — ทบทวน: "
                f"{', '.join(reduced[:3])}{'…' if len(reduced) > 3 else ''}"
            )
    else:
        # ไม่มี per_file (เช่นเทียบจาก golden snapshot) → เทียบจำนวนไฟล์แทน
        b_files = base.get("n_files", 0)
        if b_files and now["n_files"] < b_files:
            warns.append(f"จำนวนไฟล์ลด {b_files} → {now['n_files']} (data เปลี่ยน?)")

    return fails, warns


def main():
    ap = argparse.ArgumentParser(description="parse-rate canary (ไม่พึ่ง golden hash)")
    ap.add_argument("data_dir", help="โฟลเดอร์ไฟล์ .xls/.xlsx")
    ap.add_argument("--baseline", help="canary baseline JSON (มี per_file)")
    ap.add_argument("--golden", help="golden snapshot JSON (ใช้เทียบหยาบ: n_bills/n_files)")
    ap.add_argument("--write-baseline", metavar="OUT", help="เขียนโปรไฟล์ปัจจุบันเป็น baseline")
    ap.add_argument("--drop-pct", type=float, default=10.0, help="เกณฑ์ร่วง %% (ดีฟอลต์ 10)")
    args = ap.parse_args()

    if not os.path.isdir(args.data_dir):
        print(f"❌ ไม่พบโฟลเดอร์ข้อมูล: {args.data_dir}")
        return 2

    now = _profile(args.data_dir)
    print("=" * 64)
    print("PARSE CANARY — โปรไฟล์การ parse")
    print("=" * 64)
    print(f"  ไฟล์            : {now['n_files']}")
    print(f"  บิลรวม          : {now['n_bills']}")
    print(f"  อัตรา parse     : {now['parse_rate']:.2f} บิล/ไฟล์")
    print(f"  ไฟล์ที่ได้ 0 บิล : {now['n_zero_files']}")
    if now["zero_files"]:
        head = ", ".join(now["zero_files"][:5])
        print(f"      ({head}{'…' if now['n_zero_files'] > 5 else ''})")

    if args.write_baseline:
        with open(args.write_baseline, "w", encoding="utf-8") as f:
            json.dump(now, f, ensure_ascii=False, sort_keys=True, indent=1)
        print("-" * 64)
        print(f"✅ เขียน canary baseline → {args.write_baseline}")
        return 0

    base = None
    src = None
    if args.baseline and os.path.isfile(args.baseline):
        base, src = _load(args.baseline), f"canary baseline ({args.baseline})"
    elif args.golden and os.path.isfile(args.golden):
        base, src = _load(args.golden), f"golden snapshot ({args.golden})"

    if base is None:
        print("-" * 64)
        print("ℹ ไม่มีฐานเทียบ (ระบุ --baseline หรือ --golden) — แสดงโปรไฟล์เฉย ๆ")
        print("  สร้างฐาน:  python3 parse_canary.py <data> --write-baseline canary_baseline.json")
        return 0

    print("-" * 64)
    print(f"เทียบกับ: {src}  (เกณฑ์ร่วง {args.drop_pct:.0f}%)")
    fails, warns = _compare(now, base, args.drop_pct)
    for w in warns:
        print(f"  ⚠️  {w}")
    print("=" * 64)
    if fails:
        for fmsg in fails:
            print(f"  ❌ {fmsg}")
        print("RESULT: ❌ parse ร่วงเกินเกณฑ์ — สงสัย regression ของ parser")
        return 1
    print("RESULT: ✅ อัตรา parse ปกติ (ไม่ร่วงเกินเกณฑ์)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
