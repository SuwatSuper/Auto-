# -*- coding: utf-8 -*-
"""test_parser_chain_integrity.py — [OPT-2 ออปชัน (ค)] guard ความสมบูรณ์ของ re-export chain
   parser_p0a → parser_p0 → parser_p1 → parser_p2 → parser.py

ราก (OPT-2 / B2, HANDOFF): chain ทำ **explicit re-export** โยงสัญลักษณ์ข้ามชั้นด้วยมือ
  (`from parser_pX import (A,B,C,...)`). ลบ/ย้าย 1 ฟังก์ชันต้นน้ำ → ปลายน้ำ ImportError ทันที
  (ต้องแก้ 6+ จุดประสานกัน) ; หรือเพิ่มฟังก์ชันแล้วลืมร้อยผ่าน chain → หลุดจากพื้นผิว public เงียบ ๆ.

guard นี้เปลี่ยน "ความเปราะ" ให้เป็น "เทสแดงที่ระบุจุดชัด" แทน ImportError ปริศนากลางทาง:
  C1 chain-link: ทุกชื่อใน `from <upstream> import (...)` ของแต่ละโมดูล **ต้องมีจริง** ในโมดูลต้นน้ำ
     (จับ "ลบสัญลักษณ์ต้นน้ำแต่ปลายน้ำยังอ้าง" → บอกตรง ๆ ว่าลิงก์ไหน/ชื่ออะไรพัง)
  C2 public-contract: ทุกชื่อใน `parser.__all__` **ต้องเข้าถึงได้** บน `parser`
     (จับ "เพิ่มของให้ public แต่ลืมร้อยผ่าน chain" → __all__ ประกาศแต่ของไม่มาถึง)

static (AST) + import จริงของ chain เท่านั้น — ไม่รัน audit, **hash ไม่ขยับ**.
    PYTHONHASHSEED=0 python3 test_parser_chain_integrity.py
exit 0 = ผ่าน, 1 = chain แตก/พื้นผิว public ไม่ครบ
"""
import os
import sys
import io
import ast
import contextlib
import importlib
import warnings

warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

# โหลด engine ให้ครบก่อน (idiom เดียวกับเทสพี่น้อง) — แล้วค่อยตรวจ chain
_buf = io.StringIO()
with contextlib.redirect_stdout(_buf):
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')
import parser as P  # noqa: E402  (reachable — ผูก A2 ของ reachability guard)

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


# ลำดับ chain (downstream → upstream ที่มัน import มา)
CHAIN_EDGES = [
    ("parser_p0", "parser_p0a"),
    ("parser_p1", "parser_p0"),
    ("parser_p2", "parser_p1"),
    ("parser", "parser_p2"),
]


def _from_imports(path, upstream):
    """คืน set ของชื่อที่ไฟล์ `path` ทำ `from <upstream> import (...)` (ไม่รวม import *)."""
    names = set()
    tree = ast.parse(open(path, encoding="utf-8").read())
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module == upstream:
            for a in n.names:
                if a.name == "*":
                    continue
                names.add(a.name)
    return names


def main():
    print("PARSER CHAIN INTEGRITY (OPT-2 ค) — re-export chain ต้องสมบูรณ์")

    # โหลดทุกโมดูลใน chain (พังตรงนี้ = chain แตกอยู่แล้ว → รายงานชัด)
    mods = {}
    for m in ("parser_p0a", "parser_p0", "parser_p1", "parser_p2", "parser"):
        try:
            mods[m] = importlib.import_module(m)
        except Exception as e:
            check(False, f"import {m} ได้ — แต่ล้มเหลว: {type(e).__name__}: {e}")
    if len(mods) < 5:
        print("=" * 64)
        print("RESULT: ❌ chain import ไม่ครบ — แก้ re-export ให้ครบก่อน")
        return 1

    # C1: ทุกชื่อใน `from <upstream> import (...)` ต้องมีจริงใน upstream
    c1_missing = []
    n_links = 0
    for downstream, upstream in CHAIN_EDGES:
        imported = _from_imports(os.path.join(HERE, f"{downstream}.py"), upstream)
        up_ns = mods[upstream]
        for name in sorted(imported):
            n_links += 1
            if not hasattr(up_ns, name):
                c1_missing.append(f"{downstream} ← {upstream}.{name}")
    check(not c1_missing,
          f"C1 chain-link: {n_links} สัญลักษณ์ที่ re-export มีครบใน upstream"
          + ("" if not c1_missing else f" — ขาด: {c1_missing[:8]}"))

    # C2: ทุกชื่อใน parser.__all__ ต้องเข้าถึงได้บน parser
    public = list(getattr(P, "__all__", []))
    c2_missing = [n for n in public if not hasattr(P, n)]
    check(not c2_missing,
          f"C2 public-contract: parser.__all__ {len(public)} ชื่อ เข้าถึงได้ครบ"
          + ("" if not c2_missing else f" — ขาด: {c2_missing[:8]}"))

    # C2b: ไม่มีชื่อซ้ำใน __all__ (กัน drift เงียบเวลาเพิ่มมือ)
    dup = sorted({n for n in public if public.count(n) > 1})
    check(not dup, f"C2b parser.__all__ ไม่มีชื่อซ้ำ (พบซ้ำ: {dup or 'ไม่มี'})")

    print("=" * 64)
    if not FAIL:
        print(f"RESULT: ✅ re-export chain สมบูรณ์ — {n_links} ลิงก์ + public {len(public)} ชื่อ ครบทุกชั้น")
        return 0
    print(f"RESULT: ❌ {len(FAIL)} ข้อไม่ผ่าน — chain เปราะแตกจริง (ดูชื่อ/ลิงก์ที่ระบุด้านบน)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
