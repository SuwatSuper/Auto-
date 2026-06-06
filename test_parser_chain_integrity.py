# -*- coding: utf-8 -*-
"""test_parser_chain_integrity.py — [OPT-2 ก] guard ความสมบูรณ์ของ auto re-export chain
   parser_p0a → parser_p0 → parser_p1 → parser_p2 → parser.py

ราก (OPT-2 / B2, HANDOFF): เดิม chain ทำ explicit re-export ด้วยมือ ~57–95 ชื่อ/ชั้น →
  เพิ่ม/ลบ 1 สัญลักษณ์ต้นน้ำ ต้องไล่แก้ทุกชั้น (blast radius สูง). OPT-2 ก เปลี่ยนเป็น
  `parser_reexport.reexport(upstream, globals(), exclude=...)` (auto จาก upstream.__all__,
  bind object เดิม → golden ไม่ขยับ). guard นี้พิสูจน์ว่า auto re-export **ครบ + identity**:

  C1 auto-edge: ทุกชื่อใน `upstream.__all__` (ยกเว้น exclude ที่ documented) **ต้องอยู่ปลายน้ำ
     และเป็น object เดียวกัน** (`downstream.n is upstream.n`). จับทั้ง "ต้นน้ำเพิ่มของแต่หลุด"
     และ "rebind/คัดผิดตัว". exclude เปลี่ยน = เทสแดง → คนแก้ต้องตั้งใจ (กัน drift เงียบ).
  C1b explicit-edge: parser ← parser_p2 ยัง explicit (public API curate ด้วยมือ โดยเจตนา) →
     ทุกชื่อใน `from parser_p2 import (...)` ต้องมีจริงใน parser_p2.
  C2 public-contract: ทุกชื่อใน `parser.__all__` ต้องเข้าถึงได้บน `parser`.

static (AST) + import จริงของ chain เท่านั้น — ไม่รัน audit, **hash ไม่ขยับ**.
    PYTHONHASHSEED=0 python3 test_parser_chain_integrity.py
exit 0 = ผ่าน, 1 = chain แตก/พื้นผิว public ไม่ครบ/identity เพี้ยน
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


# auto-edge: (downstream, upstream, exclude) — re-export ทั้ง upstream.__all__ ยกเว้น exclude
#   exclude ของ parser_p2 = ที่ p2 จัดการเอง (Decimal/ROUND_HALF_UP จาก stdlib + helper ภายใน p1)
AUTO_EDGES = [
    ("parser_p0", "parser_p0a", frozenset()),
    ("parser_p1", "parser_p0", frozenset()),
    ("parser_p2", "parser_p1", frozenset({
        "Decimal", "ROUND_HALF_UP", "_RATE_MARKERS",
        "_rightmost_num_has_decimal", "_row_has_rate_marker",
    })),
]
# explicit-edge: parser ยัง curate public API ด้วยมือ (โดยเจตนา ไม่ใช่ debt)
EXPLICIT_EDGES = [("parser", "parser_p2")]


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
    print("PARSER CHAIN INTEGRITY (OPT-2 ก) — auto re-export chain ต้องสมบูรณ์ + identity")

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

    # C1 auto-edge: upstream.__all__ - exclude ต้องอยู่ปลายน้ำ + เป็น object เดียวกัน (identity)
    c1_missing = []
    c1_notid = []
    n_links = 0
    for downstream, upstream, exclude in AUTO_EDGES:
        up_ns = mods[upstream]
        dn_ns = mods[downstream]
        for name in [n for n in getattr(up_ns, "__all__", []) if n not in exclude]:
            n_links += 1
            if not hasattr(dn_ns, name):
                c1_missing.append(f"{downstream} ⊉ {upstream}.{name}")
            elif getattr(dn_ns, name) is not getattr(up_ns, name):
                c1_notid.append(f"{downstream}.{name} ≠ {upstream}.{name}")
    check(not c1_missing,
          f"C1 auto-edge: {n_links} สัญลักษณ์ auto re-export ครบทุกชั้น"
          + ("" if not c1_missing else f" — ขาด: {c1_missing[:8]}"))
    check(not c1_notid,
          f"C1 identity: re-export bind object เดิม (ไม่ rebind/คัดผิดตัว)"
          + ("" if not c1_notid else f" — เพี้ยน: {c1_notid[:8]}"))

    # C1b explicit-edge: parser ← parser_p2 (public API curate มือ) — ชื่อใน from-import ต้องมีจริง
    c1b_missing = []
    n_explicit = 0
    for downstream, upstream in EXPLICIT_EDGES:
        imported = _from_imports(os.path.join(HERE, f"{downstream}.py"), upstream)
        up_ns = mods[upstream]
        for name in sorted(imported):
            n_explicit += 1
            if not hasattr(up_ns, name):
                c1b_missing.append(f"{downstream} ← {upstream}.{name}")
    check(not c1b_missing,
          f"C1b explicit-edge: parser public API {n_explicit} ชื่อ มีจริงใน upstream"
          + ("" if not c1b_missing else f" — ขาด: {c1b_missing[:8]}"))

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
