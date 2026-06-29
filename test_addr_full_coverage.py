# -*- coding: utf-8 -*-
"""test_addr_full_coverage.py — ที่อยู่เทียบ master "ครบทุก field ไม่มีรู" + กัน false-positive

ลูกค้าสั่ง: ADDR ต้องเทียบ master ได้ทุก ๆ อย่าง ไม่มีรู.
เดิม _addr_smart_diff parse 11 field แต่ "รายงาน" แค่ 7 (เลขที่/แขวง/เขต/ไปรษณีย์ + อาคาร/ชั้น/ห้อง)
→ ตก จังหวัด/หมู่/ซอย/ถนน (parse แล้วแต่ไม่เคยฟ้อง). ปิดรูครบ:
  STRICT core (ฟ้องถ้าต่าง/ขาด): เลขที่ ไปรษณีย์ แขวง/ตำบล เขต/อำเภอ หมู่
  SOFT  core (ฟ้องเฉพาะมีทั้งคู่แต่ต่าง): จังหวัด
  SUB   (WARNING): อาคาร ชั้น ห้อง + (soft) ซอย ถนน
กัน FP: soft field ไม่ฟ้อง 'บิลไม่มี' (parser อาจดึงไม่ได้/ไม่มี label)

ใช้ที่อยู่จริง 2 ชุด: master=ฉีหยวน (กรุงเทพ) / bill=เจ.อาร์. (ระยอง) — ต่างกันทุก field
    PYTHONHASHSEED=0 PUOPUY_ALLOW_VERSION_MISMATCH=1 python3 test_addr_full_coverage.py
"""
import os
import sys
import io
import contextlib
import warnings

os.environ.setdefault('PUOPUY_AUDIT_DATE', '2026-06-02')
os.environ.setdefault('PUOPUY_ALLOW_VERSION_MISMATCH', '1')
warnings.filterwarnings('ignore')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)

with contextlib.redirect_stdout(io.StringIO()):
    import importlib
    importlib.import_module('ปุ้มปุ้ย_ultimate_v9_modular')

from rules_engine_rules_a import (parse_address_input, _addr_smart_diff,
                                  _ADDR_ANCHOR, _ADDR_CORE_SOFT, _ADDR_SUB, _ADDR_SUB_SOFT, _ADDR_LABEL)

PASS, FAIL = 0, []


def check(cond, label):
    global PASS
    if cond:
        PASS += 1
        print(f"  ✅ {label}")
    else:
        FAIL.append(label)
        print(f"  ❌ {label}")


# ── ที่อยู่จริง ──
M_ADDR = 'เลขที่ 2441/8 ถนนสุขุมวิท แขวงบางจาก เขตพระโขนง กรุงเทพมหานคร 10260'   # master ฉีหยวน
B_ADDR = '998/38 หมู่บ้านร่มเย็น 5 หมู่ที่ 7 ตำบลมาบยางพร อำเภอปลวกแดง จังหวัดระยอง 21140'  # bill เจ.อาร์.
M = {'name': 'X', 'tax_id': '0', 'address': M_ADDR, 'address_full': M_ADDR,
     'address_parts': parse_address_input(M_ADDR)}


def diff(addr):
    d = _addr_smart_diff({'address': addr}, M)
    return "\n".join(d['core'] + d['sub'])


print("\n[1] เทียบ master ครบทุก field (ไม่มีรู) — 11 field ต้องอยู่ในชุดเทียบ")
allf = set(_ADDR_ANCHOR) | set(_ADDR_CORE_SOFT) | set(_ADDR_SUB) | set(_ADDR_SUB_SOFT)
want = {'house_no', 'moo', 'soi', 'road', 'subdistrict', 'district', 'province', 'zipcode',
        'building', 'floor', 'room'}
check(want <= allf, f"ครบทุก field ({sorted(want - allf) or 'ครบ'})")


print("\n[2] ที่อยู่จริงต่างทุก field → ฟ้อง core ระบุตัวตนครบ (รวม 'จังหวัด' ที่เคยตก)")
txt = diff(B_ADDR)
for fld, lbl in (('zipcode', 'รหัสไปรษณีย์'), ('district', 'เขต/อำเภอ'),
                 ('subdistrict', 'แขวง/ตำบล'), ('house_no', 'เลขที่'), ('province', 'จังหวัด')):
    check(lbl in txt, f"ฟ้อง {lbl} ({fld})")


print("\n[3] จังหวัด — รูที่เคยพลาด ตอนนี้จับแล้ว (เมื่อบิลระบุจังหวัดชัด)")
txt_prov = diff('เลขที่ 2441/8 ถนนสุขุมวิท แขวงบางจาก เขตพระโขนง จังหวัดระยอง 21140')
check('จังหวัดไม่ตรง' in txt_prov, "จังหวัด ระยอง vs ทะเบียน กรุงเทพ → ฟ้อง")


print("\n[FP] กัน false-positive — ที่อยู่ถูก ต้องเงียบ")
check(diff(M_ADDR) == "", "บิล = master เป๊ะ → เงียบ")
check(diff('2441/8 สุขุมวิท บางจาก พระโขนง กรุงเทพ 10260') == "",
      "บิล = master แต่ไม่มี label/ย่อ/สลับ → เงียบ (soi/road ไม่ FP 'บิลไม่มี')")
# จังหวัด soft: บิลไม่ระบุจังหวัด (parser ดึงไม่ได้) แต่ field อื่นตรง → ไม่ฟ้องจังหวัด (กัน FP)
check('จังหวัด' not in diff('เลขที่ 2441/8 แขวงบางจาก เขตพระโขนง 10260'),
      "บิลไม่ระบุจังหวัด (parser ดึงไม่ได้) → ไม่ฟ้องจังหวัด (soft, กัน FP)")


print("\n[4] ต่างแค่ field เดียว → ฟ้องเฉพาะ field นั้น (ไม่ลามฟ้อง field อื่น)")
one = diff('เลขที่ 9999/9 ถนนสุขุมวิท แขวงบางจาก เขตพระโขนง กรุงเทพมหานคร 10260')  # ต่างแค่เลขที่
check('เลขที่ไม่ตรง' in one and 'เขต/อำเภอ' not in one and 'จังหวัด' not in one,
      f"ต่างแค่เลขที่ → ฟ้องเฉพาะเลขที่ ({one!r})")


print("\n" + "=" * 64)
if FAIL:
    print(f"ADDR-FULL: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
    for f in FAIL:
        print(f"   - {f}")
    sys.exit(1)
print(f"ADDR-FULL: ผ่าน {PASS} / ล้มเหลว 0")
print("=" * 64)
print("RESULT: ✅ ที่อยู่เทียบ master ครบทุก field (รวมจังหวัด/หมู่/ซอย/ถนน) + ไม่ false-positive")
sys.exit(0)
