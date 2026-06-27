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

# ── [ADR-103] cross-bill O(n) canary: run_rules บนบิล distinct ต้อง "sub-quadratic" ──
#   เดิมกฎ cross-bill (TAX008/DOC003/IV001/DOC001) วน all_bills ทุกใบ → O(n²) ในจำนวนบิลรวม.
#   แก้ด้วยดัชนี xbill_tax_index/xbill_file_index (เดินเฉพาะกลุ่มเดียวกัน). ถ้ามีคนถอดดัชนี (กลับเป็น
#   scan ทั้งหมด) → ratio(2N/N) จะพุ่งเข้าหา 4 (quadratic). วัดเป็น "อัตราส่วน" → ไม่ขึ้นกับความเร็วเครื่อง.
import datetime as _dt
import io as _io
import contextlib as _ctx
from rules_engine import run_rules as _run_rules


def _xb_bills(n):
    out = []
    for i in range(n):
        t = f"{1000000000000 + i:013d}"          # เลขภาษี 13 หลัก ต่างกันทุกใบ (กลุ่มละ 1 → ดัชนีต้องช่วย)
        out.append({"company": f"บริษัท ท{i} จำกัด", "company_raw": f"บริษัท ท{i} จำกัด",
                    "tax_id": t, "tax_id_raw": t, "branch": "สำนักงานใหญ่", "branch_no": "00000",
                    "iv_number": f"IV{i:05d}", "iv_number_raw": f"IV{i:05d}",
                    "iv_date": _dt.date(2025, 5, 15), "iv_date_str": "15/05/2025",
                    "file": f"F{i}.xls", "filepath": f"F{i}.xls", "sheet": "1",
                    "subtotal": 100.0, "vat": 7.0, "total": 107.0, "block_idx": 0, "issues": [],
                    "items": [{"seq": 1, "name": "เหล็ก", "name_raw": "เหล็ก", "qty": 1.0,
                               "unit": "เส้น", "price": 100.0, "amount": 100.0}]})
    return out


def _xb_time(n):
    bills = _xb_bills(n)
    t0 = time.perf_counter()
    with _ctx.redirect_stdout(_io.StringIO()):
        for b in bills:
            _run_rules(b, {}, {"month": 5, "month_end": None, "year": 2025},
                       unit_index={}, all_bills_ref=bills)
    return time.perf_counter() - t0


_XBN = int(os.environ.get("PUOPUY_PERF_XBILL_N", "2500"))
_t_n = _xb_time(_XBN)
_t_2n = _xb_time(_XBN * 2)
_ratio = (_t_2n / _t_n) if _t_n > 0 else 99.0
print(f"  ⏱️  cross-bill run_rules: N={_XBN} {_t_n:.2f}s · 2N={_XBN * 2} {_t_2n:.2f}s · "
      f"ratio={_ratio:.2f} (เชิงเส้น≈2 · O(n²)≈4)")
_check(f"cross-bill sub-quadratic (ratio {_ratio:.2f} < 3.2 → ดัชนี xbill ทำงาน ไม่ใช่ O(n²))",
       _ratio < 3.2)

# ── [ADR-119/PERF-F4] REPEATED-VENDOR canary: เคสจริง = ผู้ขายรายเดียวมีหลายบิล (กลุ่มใหญ่) ──
#   blind spot เดิม: _xb_bills ใช้ tax/file distinct ทุกใบ (กลุ่มละ 1) → กฎ cross-bill ที่ "วนต่อกลุ่ม"
#   ดูเป็น O(n) เสมอ. แต่จริง ผู้ขายรายเดียวมีหลายบิล → กลุ่มใหญ่ → ถ้ากฎ recompute clean_tax_id/
#   normalize ต่อคู่ในกลุ่ม (เดิม r_tax008/r_iv001) = O(G²)/vendor. ดัชนี precompute ต่อบิล (ADR-119)
#   ทำให้ ratio(2N/N) คง sub-quadratic แม้กลุ่มใหญ่. ถ้ามีคนถอด precompute → ratio พุ่งเข้า 4.
def _xb_time_grouped(n, nv=25):
    base = _xb_bills(n)
    for i, b in enumerate(base):                 # ยุบให้เหลือ nv ผู้ขาย (กลุ่มละ n/nv) + ไฟล์เดียวกันต่อผู้ขาย
        v = i % nv
        t = f"{2000000000000 + v:013d}"
        b["tax_id"] = b["tax_id_raw"] = t
        b["company"] = b["company_raw"] = f"บริษัท เวนเดอร์{v} จำกัด"
        b["file"] = b["filepath"] = f"G{v}.xls"
    t0 = time.perf_counter()
    with _ctx.redirect_stdout(_io.StringIO()):
        for b in base:
            _run_rules(b, {}, {"month": 5, "month_end": None, "year": 2025},
                       unit_index={}, all_bills_ref=base)
    return time.perf_counter() - t0


_gt_n = _xb_time_grouped(_XBN)
_gt_2n = _xb_time_grouped(_XBN * 2)
_gratio = (_gt_2n / _gt_n) if _gt_n > 0 else 99.0
print(f"  ⏱️  cross-bill (repeated vendors) run_rules: N={_XBN} {_gt_n:.2f}s · 2N={_XBN * 2} {_gt_2n:.2f}s · "
      f"ratio={_gratio:.2f} (เชิงเส้น≈2 · O(n²)≈4)")
# threshold 3.5 (margin เหนือ ~3.05 ที่วัดได้): precompute ต่อบิล (ADR-119) เป็น constant-factor (ตัด recompute
#   clean_tax_id/normalize ใน loop ~5x) — loop ต่อกลุ่มยังเป็น G² แต่ body ถูกลง ; canary นี้จับ regression
#   เชิงโครงสร้าง (ถอด precompute/ดัชนี → ทั้ง run_rules เอียง quadratic) ; byte-identity คุมด้วย golden + differential test.
_check(f"cross-bill repeated-vendor ไม่ระเบิด (ratio {_gratio:.2f} < 3.5 → precompute/ดัชนีทำงาน)",
       _gratio < 3.5)

print("=" * 56)
if _fail == 0:
    print("RESULT: ✅ perf canary ผ่าน (ไม่มี regression เชิงอัลกอริทึมระดับ catastrophic)")
    sys.exit(0)
else:
    print(f"RESULT: ❌ {_fail} ข้อไม่ผ่าน — สงสัย regression ด้านประสิทธิภาพ")
    sys.exit(1)
