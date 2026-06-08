# -*- coding: utf-8 -*-
"""test_perf_budget.py — PERF CANARY: กันงาน scaling-sensitive ระเบิด (Performance)

บริบท: profiling (ดู PERF_BASELINE.md) ชี้ว่า hotspot จริงคือ parse ต่อเซลล์ ; ส่วนความเสี่ยง
"ระเบิดเชิงอัลกอริทึม" ที่ชัดสุดคือ check_product_typos (O(n²) เต็มเมื่อ ≤500, window เมื่อ >500).
เทสนี้เป็น "canary" — จับ regression ระดับ catastrophic (เช่น มีคนทำให้กลายเป็น O(n³) หรือถอด
window/spec-cache) ไม่ใช่ micro-benchmark (จึงตั้ง budget กว้างเพื่อกัน flaky ใน CI ช้า).

ปรับ budget/ขนาดได้ผ่าน env:
    PUOPUY_PERF_N        (default 800)   จำนวนชื่อสังเคราะห์ (อยู่เหนือ 500 → ครอบ window)
    PUOPUY_PERF_BUDGET_S (default 30)    เพดานเวลา (วินาที)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validators import check_product_typos

N = int(os.environ.get("PUOPUY_PERF_N", "800"))
BUDGET = float(os.environ.get("PUOPUY_PERF_BUDGET_S", "30"))

_fail = 0


def _check(label, cond):
    global _fail
    print(("  ✅ " if cond else "  ❌ ") + label)
    if not cond:
        _fail += 1


# ชื่อสังเคราะห์: ครึ่งมีเลขกำกับ (spec ต่าง) + ครึ่งความยาวคละ — กระตุ้น window + spec-cache
names = []
for i in range(N):
    if i % 2 == 0:
        names.append(f"วัสดุก่อสร้างชนิดพิเศษหมายเลข{i}")
    else:
        names.append("ท่อเหล็กกล้าเคลือบสังกะสีรุ่น" + ("ก" * (i % 11)) + str(i))
bills = [{"items": [{"name": nm, "amount": 1.0, "seq": j}]} for j, nm in enumerate(names)]

t0 = time.perf_counter()
typos = check_product_typos(bills)
elapsed = time.perf_counter() - t0

print(f"  ⏱️  check_product_typos({N} ชื่อ) = {elapsed:.3f}s (budget {BUDGET:.0f}s)")
_check(f"เสร็จภายใน budget ({elapsed:.3f}s ≤ {BUDGET:.0f}s)", elapsed <= BUDGET)
_check("คืน list (โครงสร้างผลถูกต้อง)", isinstance(typos, list))

print("=" * 56)
if _fail == 0:
    print("RESULT: ✅ perf canary ผ่าน (ไม่มี regression เชิงอัลกอริทึมระดับ catastrophic)")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — สงสัย regression ด้านประสิทธิภาพ")
    sys.exit(1)
