# -*- coding: utf-8 -*-
"""test_addr_smart.py — ตรึงตรรกะ SMART-ADDR (ADR-014): ADDR001 + ADDR003 field-based

โจทย์: เลิก false alarm "ที่อยู่ไม่ตรง" ทั้งที่ตรงจริง (ลำดับ/ช่องว่าง/label ฟอร์มต่าง).
ทดสอบ (generic ทุกที่อยู่ — ไม่ผูกบริษัทใด):
  • ตรงกันแต่คนละลำดับ + space + คำย่อ (ซ./ถ./กรุงเทพฯ) → ไม่เตือน
  • คนละเขต/แขวง/ไปรษณีย์ → ERROR (ADDR001)
  • label ฟอร์มเปล่า "ห้องเลขที่ -" → ไม่นับว่าขาด
  • อาคาร/ชั้นต่างจริง → WARNING (ADDR003) ; เหมือนกัน (คนละ space) → ไม่เตือน

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_addr_smart.py
"""

import os
import sys
import io
import contextlib
import warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
with contextlib.redirect_stdout(io.StringIO()):
    import importlib

    importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
import rules_engine_rules_a as A

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def ctx():
    return {}


# master generic (เลข/ชื่อสมมุติ — ทดสอบตรรกะ ไม่ผูกบริษัทจริง)
M = {
    "address_full": (
        "ห้องเลขที่ - หมู่บ้าน - ชั้นที่ - อาคารพี23 เลขที่ 5/32 ตรอก/ซอย ศรีนครินทร์ 46/1 "
        "ถนนศรีนครินทร์ แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250"
    ),
    "address_parts": {
        "house_no": "5/32",
        "soi": "ศรีนครินทร์ 46/1",
        "road": "ศรีนครินทร์",
        "subdistrict": "หนองบอน",
        "district": "ประเวศ",
        "province": "กรุงเทพมหานคร",
        "zipcode": "10250",
    },
}

print("=" * 64)
print("SMART-ADDR (ADR-014) — เทียบที่อยู่ทีละ field, generic")
print("=" * 64)

# [1] ตรงกัน แต่คนละลำดับ + space ต่าง + คำย่อ → ไม่เตือน (ดับ false alarm)
b_same = {
    "address": "5/32 ซ.ศรีนครินทร์46/1 ถ.ศรีนครินทร์ แขวงหนองบอน เขตประเวศ กรุงเทพฯ 10250"
}
check(A.r_addr001(b_same, M, ctx()) == [], "ตรงกัน คนละลำดับ+space+ย่อ → ADDR001 เงียบ")

# [2] บิลเรียงแบบคนเขียน (เลขที่→อาคาร→ชั้น→ซอย) ลำดับต่างฟอร์ม → ไม่เตือน
b_order = {
    "address": "เลขที่ 5/32 อาคารพี 23 ชั้นที่ 3 ซอยศรีนครินทร์ 46/1 หนองบอน ประเวศ กรุงเทพมหานคร 10250"
}
check(
    A.r_addr001(b_order, M, ctx()) == [], "ลำดับแบบคนเขียน (anchor ครบ) → ADDR001 เงียบ"
)

# [3] คนละเขต + แขวง + ไปรษณีย์ → ERROR
b_diff = {"address": "เลขที่ 5/32 ถนนสุขุมวิท แขวงคลองตัน เขตวัฒนา กรุงเทพมหานคร 10110"}
out = A.r_addr001(b_diff, M, ctx())
check(out and "ไม่ตรงทะเบียน" in out[0], "คนละเขต/แขวง/ไปรษณีย์ → ADDR001 ฟ้อง ERROR")
check(
    all(k in out[0] for k in ("ไปรษณีย์", "เขต", "แขวง")),
    "ระบุ field ที่ต่างครบ (ไปรษณีย์/เขต/แขวง)",
)

# [4] ไปรษณีย์ผิดตัวเดียว (เขต/แขวงตรง) → ยังฟ้อง (anchor ไม่ครบ)
b_zip = {
    "address": "เลขที่ 5/32 ถนนศรีนครินทร์ แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10110"
}
check(A.r_addr001(b_zip, M, ctx()) != [], "ไปรษณีย์ผิด (anchor ไม่ครบ) → ADDR001 ฟ้อง")

# [5] label ฟอร์มเปล่า "ห้องเลขที่ -" / "ชั้นที่ -" → ไม่นับว่ามีข้อมูล (ไม่ทำให้ฟ้อง)
b_empty = {
    "address": "เลขที่ 5/32 ห้องเลขที่ - ชั้นที่ - แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250"
}
check(
    A.r_addr001(b_empty, M, ctx()) == [], "label เปล่า '-' → ไม่นับขาด → ADDR001 เงียบ"
)

# [6] ADDR003: อาคารต่างจริง → WARNING
b_bldg = {
    "address": "เลขที่ 5/32 อาคารเอ็กซ์วาย แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250"
}
check(A.r_addr003(b_bldg, M, ctx()) != [], "อาคารต่างจริง → ADDR003 เตือน (WARNING)")

# [7] ADDR003: อาคารเดียวกันแต่ space ต่าง ("พี23" vs "พี 23") → ไม่เตือน
b_bldg_ok = {
    "address": "เลขที่ 5/32 อาคารพี 23 แขวงหนองบอน เขตประเวศ กรุงเทพมหานคร 10250"
}
check(
    A.r_addr003(b_bldg_ok, M, ctx()) == [], "อาคารเดียวกัน (space ต่าง) → ADDR003 เงียบ"
)

# [8] standalone (ไม่มี master) — คงพฤติกรรมเดิม: ขาดไปรษณีย์/location → ฟ้อง
check(
    A.r_addr001({"address": "เลขที่ 5/32 ถนนสุขุมวิท"}, None, ctx()) != [],
    "standalone ไม่มี master + ขาดไปรษณีย์ → ฟ้อง (เดิม)",
)
check(
    A.r_addr001({"address": "5/32 แขวงหนองบอน เขตประเวศ 10250"}, {}, ctx()) == [],
    "standalone มีไปรษณีย์+เขต/แขวง → เงียบ (เดิม)",
)

# [9] helper: _addr_field_match
check(
    A._addr_field_match("กรุงเทพฯ", "กรุงเทพมหานคร") is True,
    "_addr_field_match คำพ้องจังหวัด → True",
)
check(
    A._addr_field_match("10110", "10250") is False,
    "_addr_field_match ไปรษณีย์ต่าง → False",
)
check(
    A._addr_field_match("", "ประเวศ") is False,
    "_addr_field_match บิลว่าง+ทะเบียนมี → False",
)
check(
    A._addr_field_match("ประเวศ", "-") is None,
    "_addr_field_match ทะเบียน '-' → None (ไม่เช็ค)",
)

print("\n" + "=" * 64)
print(f"SMART-ADDR: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ ที่อยู่ตรง→เงียบ / ต่างจริง→เตือน (generic ทุกที่อยู่)")
sys.exit(0)
