# -*- coding: utf-8 -*-
"""test_bs4_dt006_tor_calendar.py — [BS-4/ADR-117] วันที่ไม่มีจริงในปฏิทิน → DT006 (ครบทั้ง 2 เส้น parser)

ช่องโหว่ที่ prompt ชี้: วันที่ผิดปฏิทิน (31/04, 30/02, 29/02 ปีปกติ) parse ไม่ได้แล้ว "drop เงียบ"
→ บิลไม่มีวันที่ → ไม่ถูกฟ้องว่า "วันที่ผิด".

ผลตรวจจริง (forensic):
  • เส้น PB (parser_p1) ครอบคลุมแล้ว: parse_date_any คืน None + เซลล์หน้าตาเป็นวันที่ → set _bad_date
    → DT006 "วันที่ไม่มีจริงในปฏิทิน ต้องแก้". (ไม่แตะ — ครอบคลุมดีแล้ว.)
  • เส้น TOR (parser_p2 _tor_try_date) เป็น "รูที่เหลือ": วันที่ ISO ผิดปฏิทิน drop เงียบ →
    ตกไป DT005 "ไม่มีวันที่" (มิสเลด). [ADR-117] mirror เส้น PB: set _bad_date → DT006.

ตรึง: parse_date_any คืน None เฉพาะวันผิดปฏิทิน (valid/leap ยัง parse ได้) ;
      _tor_try_date set _bad_date เฉพาะ ISO ผิดปฏิทิน (valid ยัง parse) ;
      apply_bad_date_check emit DT006 จาก _bad_date ; เงียบเมื่อมีวันที่จริง.
self-contained: ไม่พึ่ง corpus. exit 0 = ผ่าน, 1 = พบปัญหา.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from puopuy_dates import parse_date_any
from parser_p2 import _tor_try_date
from validators import apply_bad_date_check, apply_missing_date_check

_fail = 0


def _check(label, cond):
    global _fail
    print(("  [PASS] " if cond else "  [FAIL] ") + label)
    if not cond:
        _fail += 1


# 1) parse_date_any: วันผิดปฏิทิน → None ; valid/leap → parse ได้ (กันยิงพลาดวันถูก)
_check("parse_date_any('31/04/2026') → None", parse_date_any("31/04/2026") is None)
_check("parse_date_any('30/02/2026') → None", parse_date_any("30/02/2026") is None)
_check("parse_date_any('29/02/2025') → None (ปีปกติไม่มี 29 ก.พ.)", parse_date_any("29/02/2025") is None)
_check("parse_date_any('29/02/2024') → ได้วันที่ (ปีอธิกสุรทิน)", parse_date_any("29/02/2024") is not None)
_check("parse_date_any('15/05/2026') → ได้วันที่ (วันถูกต้อง)", parse_date_any("15/05/2026") is not None)

# 2) เส้น TOR [ADR-117]: ISO ผิดปฏิทิน → set _bad_date (เดิม drop เงียบ)
r_bad = {"iv_date": None, "iv_date_str": ""}
ret = _tor_try_date(r_bad, "2026-04-31", "2026-04-31")
_check("_tor_try_date('2026-04-31') คืน False (ไม่ใช่วันที่จริง)", ret is False)
_check("_tor_try_date ตั้ง _bad_date = '2026-04-31'", r_bad.get("_bad_date") == "2026-04-31")
# valid ISO → parse ได้ ไม่ตั้ง _bad_date
r_ok = {"iv_date": None, "iv_date_str": ""}
_check("_tor_try_date('2026-05-15') คืน True (วันถูก)", _tor_try_date(r_ok, "2026-05-15", "2026-05-15") is True)
_check("วันถูก → ไม่ตั้ง _bad_date", r_ok.get("_bad_date") is None and r_ok.get("iv_date") is not None)
# guard: _bad_date ที่ตั้งแล้วไม่ถูกเขียนทับ (เซลล์ถัดมาผิดปฏิทินอีก → คงค่าแรก, mirror PB)
r_dup = {"iv_date": None, "iv_date_str": "", "_bad_date": "2026-04-31"}
_tor_try_date(r_dup, "2026-06-31", "2026-06-31")
_check("_bad_date แรกไม่ถูกเขียนทับ (คงค่าเดิม)", r_dup.get("_bad_date") == "2026-04-31")
# non-date cell ที่ไม่เข้า regex ISO → ไม่ตั้ง _bad_date (ไม่ false-positive)
r_non = {"iv_date": None, "iv_date_str": ""}
_tor_try_date(r_non, "ค่าสินค้า", "ค่าสินค้า")
_check("เซลล์ไม่ใช่วันที่ → ไม่ตั้ง _bad_date", r_non.get("_bad_date") is None)
# เซลล์เป็น datetime native (ปี พ.ศ. >2500 → ลบ 543) → parse ตรง ไม่แตะ _bad_date
import datetime as _dt
r_native = {"iv_date": None, "iv_date_str": ""}
_check("datetime native → True", _tor_try_date(r_native, _dt.datetime(2569, 5, 15), "2569-05-15") is True)
_check("datetime native พ.ศ.→ค.ศ. (2569→2026)", r_native.get("iv_date").year == 2026)

# 3) apply_bad_date_check: _bad_date → DT006 (เส้นปลายร่วมของทั้ง PB + TOR)
b_tor = {"iv_date": None, "_bad_date": "2026-04-31", "iv_number": "INV1", "items": [{"x": 1}], "total": 100, "issues": []}
apply_bad_date_check([b_tor])
codes = [i["code"] for i in b_tor["issues"]]
_check("ฟ้องเคสผิด: _bad_date → DT006 ยิง", "DT006" in codes)
_check("detail DT006 บอก 'ไม่มีจริงในปฏิทิน'",
       any("ไม่มีจริงในปฏิทิน" in i["detail"] for i in b_tor["issues"] if i["code"] == "DT006"))

# 4) เงียบเคสถูก: บิลมีวันที่จริง → DT006 ไม่ยิง
b_good = {"iv_date": __import__("datetime").date(2026, 5, 15), "_bad_date": None,
          "iv_number": "INV2", "items": [{"x": 1}], "total": 100, "issues": []}
apply_bad_date_check([b_good])
_check("บิลมีวันที่จริง → DT006 เงียบ", "DT006" not in [i["code"] for i in b_good["issues"]])

# 5) DT006 (specific) ชนะ DT005 (generic): บิล _bad_date ไม่ถูกฟ้องเป็น "ไม่มีวันที่"
b_excl = {"iv_date": None, "_bad_date": "31/04/2026", "iv_number": "INV3", "items": [{"x": 1}], "total": 100, "issues": []}
apply_missing_date_check([b_excl])
_check("บิล _bad_date ไม่ขึ้น DT005 'ไม่มีวันที่' (กันมิสเลด)",
       "DT005" not in [i["code"] for i in b_excl["issues"]])

print("=" * 60)
if _fail == 0:
    print("RESULT: [PASS] วันผิดปฏิทิน → DT006 ครบทั้งเส้น PB + TOR ; วันถูก parse ปกติ")
    sys.exit(0)
print(f"RESULT: [FAIL] {_fail} ข้อไม่ผ่าน")
sys.exit(1)
