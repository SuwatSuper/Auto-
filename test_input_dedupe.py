# -*- coding: utf-8 -*-
"""test_input_dedupe.py — [F1-GUARD v9.3] ไฟล์ชื่อซ้ำคนละโฟลเดอร์ต้องถูกตัด + เตือน (กันบิลคูณซ้ำเงียบ)

เคสจริง 11.06.69: โฟลเดอร์ input มีโฟลเดอร์ย่อย (สำเนา) ที่มีไฟล์ชื่อเดียวกัน →
recursive scan หยิบซ้ำ → บิลของบริษัทนั้นถูกนับ ×2 เงียบ ๆ (ยอด 100,010 → 200,020,
DOC003 ฟ้อง "ซ้ำกับบิลอื่น" กับเงาตัวเอง). การ์ดนี้ตัดสำเนา (เก็บ path ตื้นสุด) + เตือน SYS004.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import parser_p2 as P  # noqa: E402
import state  # noqa: E402

_PASS = 0
_FAIL = 0


def check(cond, label):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"  ✅ {label}")
    else:
        _FAIL += 1
        print(f"  ❌ {label}")


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x")


print("[D1] ไม่มีชื่อซ้ำ → พฤติกรรมเดิมเป๊ะ (ครบทุกไฟล์, เรียง sort)")
with tempfile.TemporaryDirectory() as td:
    _touch(os.path.join(td, "A 69.05.xls"))
    _touch(os.path.join(td, "B 69.05.xlsx"))
    _touch(os.path.join(td, "ย่อย", "C 69.05.xls"))
    got = P.get_files_via_drive(td)
    bases = sorted(os.path.basename(f) for f in got)
    check(bases == ["A 69.05.xls", "B 69.05.xlsx", "C 69.05.xls"],
          f"ได้ 3 ไฟล์ครบ ไม่มีตัด (got={bases})")
    check(got == sorted(got), "ลำดับ sorted คงเดิม (C1)")

print("[D2] ชื่อซ้ำคนละโฟลเดอร์ → เก็บตัวตื้นสุด ตัดสำเนา + log SYS004")
with tempfile.TemporaryDirectory() as td:
    state._SYSTEM_ISSUES.clear()
    state._SYSTEM_ISSUE_SEEN.clear()
    state._SYSTEM_ISSUE_KEYS.clear()
    top = os.path.join(td, "SHS 69.05.xls")
    deep = os.path.join(td, "สำเนาเก่า", "SHS 69.05.xls")
    other = os.path.join(td, "TNT 69.01.xls")
    _touch(top)
    _touch(deep)
    _touch(other)
    got = P.get_files_via_drive(td)
    check(len(got) == 2, f"เหลือ 2 ไฟล์ (ตัดสำเนา 1) — got={len(got)}")
    check(os.path.normpath(top) in [os.path.normpath(g) for g in got],
          "เก็บตัว path ตื้นสุด (ไฟล์หลักหน้าโฟลเดอร์)")
    check(os.path.normpath(deep) not in [os.path.normpath(g) for g in got],
          "สำเนาในโฟลเดอร์ย่อยถูกตัด")
    sys_codes = [i.get("code") for i in state._SYSTEM_ISSUES]
    check("SYS004" in sys_codes, f"log SYS004 ลง system issues (got={sys_codes})")

print("[D3] ซ้ำ 3 ชั้น → เหลือตัวเดียว + deterministic (เรียกซ้ำได้ผลเดิม)")
with tempfile.TemporaryDirectory() as td:
    state._SYSTEM_ISSUES.clear()
    state._SYSTEM_ISSUE_SEEN.clear()
    state._SYSTEM_ISSUE_KEYS.clear()
    _touch(os.path.join(td, "K 69.05.xls"))
    _touch(os.path.join(td, "a", "K 69.05.xls"))
    _touch(os.path.join(td, "a", "b", "K 69.05.xls"))
    got1 = P.get_files_via_drive(td)
    got2 = P.get_files_via_drive(td)
    check(len(got1) == 1 and os.path.normpath(got1[0]) == os.path.normpath(os.path.join(td, "K 69.05.xls")),
          "3 สำเนา → เหลือตัวตื้นสุดตัวเดียว")
    check(got1 == got2, "เรียกซ้ำให้ผลเดิม (deterministic)")

print()
print(f"ผล: ✅ {_PASS} | ❌ {_FAIL}")
sys.exit(0 if _FAIL == 0 else 1)
