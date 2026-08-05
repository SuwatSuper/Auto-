# -*- coding: utf-8 -*-
"""test_adr179_moneycol_footer.py — ตรึงพฤติกรรม + ครอบ branch ของการอ่าน "ยอดเงินบนเอกสาร"

ครอบ 3 การแก้ที่ผูกกันในสายเดียว (ยอดก่อน VAT / VAT / ยอดรวม ต้องมาจากเอกสารจริง ไม่ใช่ค่าที่ระบบเดา):

  ADR-179  `_pb_money_col`      — กัน amt_col ชี้ "คอลัมน์ helper" แล้วคว้ายอดรวมทั้งไฟล์มาเป็น subtotal
                                  (เคสจริง TKH_69_07.xls ชีต 2 → VAT001+VAT012 false positive)
  ADR-182  `_pb_footer_triple`  — อ่าน footer ได้แม้เอกสารไม่พิมพ์อัตรา 0.07 (เดิม 384 บิลตกไปใช้
                                  ผลรวมรายการเป็น subtotal → VAT001 เทียบตัวเองตลอดกาล = "ตรงหลอก")
  ADR-184  `_unit_canon`        — หน่วยฝั่งอังกฤษ (Pcs./PCS.) = หน่วยไทย (ท่อน/เส้น) ตัด ITM015 FP

หลักที่ตรึงไว้: ทุกฟังก์ชัน "อ่านเซลล์ให้ถูก" เท่านั้น — ห้ามปรับ/แต่ง/เดาค่าเงินเด็ดขาด
(ถ้าไม่มั่นใจต้องคืน None แล้วปล่อยพฤติกรรมเดิม) เพื่อให้ VAT001 ยังจับยอดที่ผิดจริงได้เหมือนเดิม.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONHASHSEED", "0")
os.environ.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from parser_p2 import _pb_money_col, _pb_footer_triple, _pb_amounts_from_vatrow  # noqa: E402
from puopuy_units import _unit_canon  # noqa: E402

_fail = 0


def _check(name, ok):
    global _fail
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        _fail += 1


def _df(rows, ncols):
    """สร้าง DataFrame จาก dict {(r,c): value} ให้เหมือนชีต Excel ที่อ่านด้วย header=None"""
    m = np.full((max(r for r, _ in rows) + 1, ncols), np.nan, dtype=object)
    for (r, c), v in rows.items():
        m[r, c] = v
    return pd.DataFrame(m)


print("=" * 60)
print("ADR-179/179/181 — money column + footer triple + unit canon")
print("=" * 60)

# ── ADR-179 _pb_money_col ────────────────────────────────────────────────────
# เคสปกติ: amt_col มีค่าในแถว VAT → ต้องคืนค่าเดิมไม่แตะ (golden-neutral path)
d = _df({(0, 3): 100.0, (1, 3): 7.0, (2, 3): 107.0}, 5)
_check("amt_col มีค่าในแถว VAT → คืน amt_col เดิม (ไม่เปลี่ยนเส้นทาง)",
       _pb_money_col(d, 1, 3, 5) == 3)

# เคสบั๊กจริง: amt_col (คอลัมน์ helper) ว่างในแถว VAT แต่คอลัมน์เงินจริงมีค่า
d = _df({(0, 2): 89374.55, (0, 4): 1.0,
         (1, 2): 6256.22,
         (2, 4): 134103.35}, 5)
_check("amt_col ว่างในแถว VAT → ย้ายไปคอลัมน์ที่มีค่า (กันคว้ายอดรวมทั้งไฟล์)",
       _pb_money_col(d, 1, 4, 5) == 2)

# ไม่มีคอลัมน์ไหนมีค่าในแถว VAT เลย → fail-safe คืนค่าเดิม (ไม่เดา)
d = _df({(0, 1): 500.0, (1, 1): np.nan, (2, 1): 535.0}, 3)
_check("ไม่มีคอลัมน์ใดมีค่าในแถว VAT → คืน amt_col เดิม (fail-safe ไม่เดา)",
       _pb_money_col(d, 1, 1, 3) == 1)

# ค่า 0 ในแถว VAT ไม่นับเป็นคอลัมน์เงิน (ต้อง > 0)
d = _df({(0, 1): 500.0, (1, 0): 0.0, (1, 2): 35.0, (2, 1): 535.0}, 3)
_check("ค่า 0 ในแถว VAT ไม่ถูกเลือก (เลือกคอลัมน์ที่มีค่า > 0)",
       _pb_money_col(d, 1, 1, 3) == 2)

# guard: amt_col / vat_row เป็น None → คืนตามที่รับมา
_check("amt_col=None → คืน None (guard)", _pb_money_col(d, 1, None, 3) is None)
_check("vat_row=None → คืน amt_col เดิม (guard)", _pb_money_col(d, None, 1, 3) == 1)

# guard: amt_col เกินขอบคอลัมน์ → ไม่ระเบิด IndexError
d = _df({(0, 1): 500.0, (1, 1): 35.0}, 3)
_check("amt_col เกินจำนวนคอลัมน์ → ไม่ครัช (ไปเส้นค้นหาแทน)",
       _pb_money_col(d, 1, 99, 3) in (1, 99))

# ── _pb_amounts_from_vatrow เดินผ่าน _pb_money_col จริง (integration) ────────
d = _df({(0, 2): 89374.55, (0, 4): 1.0,
         (1, 2): 6256.22,
         (2, 2): 95630.77, (2, 4): 134103.35}, 5)
res = {"subtotal": None, "vat": None, "total": None}
_pb_amounts_from_vatrow(d, res, 1, 4, 0, 2)
_check("อ่านยอดผ่านคอลัมน์เงินจริง ไม่ใช่คอลัมน์ helper (subtotal 89,374.55)",
       res["subtotal"] == 89374.55 and res["vat"] == 6256.22 and res["total"] == 95630.77)

# ── ADR-182 _pb_footer_triple ───────────────────────────────────────────────
# triple สอดคล้องกันเอง (vat = sub×7%, total = sub+vat) → รับ
d = _df({(0, 5): 19626.17, (1, 5): 1373.8319, (2, 5): 21000.0019}, 6)
_check("เจอ triple ที่สอดคล้องกันเอง → คืน (sub, vat, total) ตามที่พิมพ์บนเอกสาร",
       _pb_footer_triple(d, 0, 2, 6) == (19626.17, 1373.8319, 21000.0019))

# มีหลาย triple → เลือกอันที่ subtotal สูงสุด (ยอดรวมท้ายบิล ไม่ใช่ยอดกลางบิล)
d = _df({(0, 2): 100.0, (1, 2): 7.0, (2, 2): 107.0,
         (3, 2): 1000.0, (4, 2): 70.0, (5, 2): 1070.0}, 3)
_check("หลาย triple → เลือก subtotal สูงสุด (ยอดท้ายบิล)",
       _pb_footer_triple(d, 0, 5, 3) == (1000.0, 70.0, 1070.0))

# ไม่มี VAT ที่เข้าคู่ → None (ไม่เดา)
d = _df({(0, 1): 5000.0, (1, 1): 999.0, (2, 1): 5999.0}, 2)
_check("ไม่มีเลขที่เป็น 7% ของ subtotal → คืน None (ไม่เดา)",
       _pb_footer_triple(d, 0, 2, 2) is None)

# มี VAT ถูกแต่ไม่มียอดรวม → None (ต้องครบทั้งสามขา)
d = _df({(0, 1): 1000.0, (1, 1): 70.0}, 2)
_check("มี sub+vat แต่ไม่มี total → คืน None (ต้องครบสามขา)",
       _pb_footer_triple(d, 0, 1, 2) is None)

# total อยู่เหนือ subtotal → ปฏิเสธ (ลำดับแถวไม่สมเหตุผล)
d = _df({(0, 1): 1070.0, (1, 1): 1000.0, (2, 1): 70.0}, 2)
_check("total อยู่เหนือ subtotal/vat → ปฏิเสธ (ลำดับแถวผิด)",
       _pb_footer_triple(d, 0, 2, 2) is None)

# ตัวเลขน้อยกว่า 3 ตัว → None ทันที
d = _df({(0, 1): 1000.0, (1, 1): 70.0, (2, 0): np.nan}, 2)
_check("ตัวเลขในช่วงน้อยกว่า 3 ตัว → คืน None",
       _pb_footer_triple(d, 0, 0, 2) is None)

# ช่วงแถวกลับด้าน (hi < lo) → None (guard)
d = _df({(0, 1): 1000.0, (1, 1): 70.0, (2, 1): 1070.0}, 2)
_check("ช่วงแถวไม่ถูกต้อง (row_start > row_end) → คืน None (guard)",
       _pb_footer_triple(d, 5, 1, 2) is None)

# row_end เกินจำนวนแถวจริง → clamp ไม่ครัช
_check("row_end เกินจำนวนแถว → clamp แล้วยังอ่านได้ (ไม่ครัช)",
       _pb_footer_triple(d, 0, 999, 2) == (1000.0, 70.0, 1070.0))

# ค่าที่เป็นข้อความ/ค่าว่างถูกข้าม ไม่พัง
d = _df({(0, 0): "ยอดก่อนภาษี", (0, 1): 1000.0,
         (1, 0): "ภาษี 7%", (1, 1): 70.0,
         (2, 0): "รวมทั้งสิ้น", (2, 1): 1070.0}, 2)
_check("มีข้อความปนในช่วง footer → ข้ามข้อความ อ่านตัวเลขได้ปกติ",
       _pb_footer_triple(d, 0, 2, 2) == (1000.0, 70.0, 1070.0))

# ── ADR-184 _unit_canon (EN ↔ TH) ───────────────────────────────────────────
_check("Pcs. ยุบกลุ่มเดียวกับ ท่อน (ตัด ITM015 false positive)",
       _unit_canon("Pcs.") == _unit_canon("ท่อน"))
_check("PCS. (ตัวพิมพ์ใหญ่) ยุบกลุ่มเดียวกับ เส้น",
       _unit_canon("PCS.") == _unit_canon("เส้น"))
_check("piece / ea ยุบกลุ่มเดียวกับ ชิ้น",
       _unit_canon("piece") == _unit_canon("ชิ้น") == _unit_canon("ea"))
_check("หน่วยคนละกลุ่มยังต่างกัน (ยังจับของจริงได้: คิว ≠ ตัน)",
       _unit_canon("คิว") != _unit_canon("ตัน"))
_check("ม้วน ≠ แพ็ค (ยังฟ้องหน่วยต่างกลุ่มจริง)",
       _unit_canon("ม้วน") != _unit_canon("แพ็ค"))
_check("ค่าว่าง/None → คืนสตริงว่าง (guard)",
       _unit_canon("") == "" and _unit_canon(None) == "")
_check("หน่วยที่ไม่รู้จัก → คืนตัวมันเอง (ไม่เดา)",
       _unit_canon("หน่วยประหลาด") == "หน่วยประหลาด")

# ── ADR-189 ส่วนลดต้อง "พิสูจน์จากเอกสาร" ไม่ใช่ "เดาจากช่วงตัวเลข" ──────────
from rules_engine_rules_a import r_itm001  # noqa: E402
from parser_p1 import _pb_build_item  # noqa: E402


def _bill(items):
    return {"items": items, "file": "X.xls", "sheet": "1"}


# เดิม: ยอดต่ำกว่า qty×price 1–50% → ถือว่า "น่าจะเป็นส่วนลด" → ข้ามเงียบทุกกรณี
#       = ยอดที่พิมพ์ผิดจริงทั้งแถบถูกกลืน. ใหม่: ไม่มีส่วนลดบนเอกสาร → ต้องฟ้อง.
_r = r_itm001(_bill([{"seq": 1, "name": "เหล็ก", "qty": 10, "price": 100,
                      "amount": 800, "discount": None}]), {}, {})
_check("ยอดต่ำกว่า 20% โดยไม่มีส่วนลดในเอกสาร → ต้องฟ้อง (ปิด blind spot เดิม)",
       bool(_r) and "ไม่พบส่วนลดในเอกสาร" in _r[0])

_r = r_itm001(_bill([{"seq": 1, "name": "เหล็ก", "qty": 10, "price": 100,
                      "amount": 800, "discount": 0.20}]), {}, {})
_check("มีส่วนลด 20% บนเอกสารและกระทบยอดลงตัว → เงียบ (ไม่ใช่ error)", not _r)

_r = r_itm001(_bill([{"seq": 1, "name": "เหล็ก", "qty": 10, "price": 100,
                      "amount": 750, "discount": 0.20}]), {}, {})
_check("มีส่วนลด 20% แต่ยอดไม่ลงตัว → ต้องฟ้องพร้อมยอดที่ควรได้",
       bool(_r) and "ควรได้ 800.00" in _r[0])

_r = r_itm001(_bill([{"seq": 1, "name": "เหล็ก", "qty": 10, "price": 100,
                      "amount": 1000, "discount": None}]), {}, {})
_check("qty×price = amount เป๊ะ → เงียบ", not _r)

# parser: จับเซลล์ส่วนลดในแถวเดียวกันได้ทั้งรูป 0.25 และ 25
_d = pd.DataFrame([[1, "สีพ่น", "แกลลอน", 15.0, 2970.0, 0.25, 33412.5]])
_it = _pb_build_item(_d, 0, 1, 1, 3, 2, 4, 6)
_check("parser จับส่วนลดรูปทศนิยม (0.25) ได้", _it is not None and _it["discount"] == 0.25)

_d = pd.DataFrame([[1, "สีพ่น", "แกลลอน", 15.0, 2970.0, 25.0, 33412.5]])
_it = _pb_build_item(_d, 0, 1, 1, 3, 2, 4, 6)
_check("parser จับส่วนลดรูปเปอร์เซ็นต์ (25) ได้", _it is not None and _it["discount"] == 0.25)

_d = pd.DataFrame([[1, "สีพ่น", "แกลลอน", 15.0, 2970.0, None, 44550.0]])
_it = _pb_build_item(_d, 0, 1, 1, 3, 2, 4, 6)
_check("ยอดตรงอยู่แล้ว → ไม่ต้องหาส่วนลด (discount=None)",
       _it is not None and _it["discount"] is None)

_d = pd.DataFrame([[1, "สีพ่น", "แกลลอน", 15.0, 2970.0, None, 30000.0]])
_it = _pb_build_item(_d, 0, 1, 1, 3, 2, 4, 6)
_check("ยอดเพี้ยนแต่ไม่มีเซลล์ส่วนลดที่กระทบยอดได้ → discount=None (ไม่เดา)",
       _it is not None and _it["discount"] is None)

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] ยอดเงินอ่านถูกคอลัมน์/แถว + หน่วย EN↔TH + ส่วนลดพิสูจน์จากเอกสาร")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
