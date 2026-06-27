# -*- coding: utf-8 -*-
"""test_stub_marker.py — กันบั๊ก "master จริงถูกตีเป็น stub" กลับมา (STUB-MARKER fix)

เหตุการณ์จริง (มิ.ย. 2026): ผู้ใช้ใส่ master ฉีอันจริงจาก ภ.พ.20 (เลขภาษี 0105566206726 —
บังเอิญเป็นบริษัทเดียวกับ golden stub) → _is_real_master ตรรกะเก่า "เดาจากเลขภาษี" ตีเป็น stub
→ โยน master ทิ้ง → รายงานขึ้น "ไม่มีใน master (ตรวจไม่ได้)" ทั้งที่ master อยู่ในไฟล์.

Fix: stub ที่เครื่องมือ golden/verify เขียน มี key "_golden_stub": true ในไฟล์ —
  • master.load_master() ตัด key ออก + จำใน LAST_LOADED_WAS_STUB
  • _is_real_master เช็ค marker เป็นชั้นแรก ; เนื้อหา (key+tax ตรง stub เป๊ะ) เป็น fallback
    เฉพาะไฟล์ stub รุ่นเก่าก่อนมี marker

self-contained: ใช้ tmp MASTER_FILE — ไม่แตะ master จริงของผู้ใช้ / ไม่พึ่ง /mnt/project
"""
import importlib
import json
import os
import sys
import tempfile

PASS = True


def _check(label, cond):
    global PASS
    print(f"  {'✅' if cond else '❌'} {label}")
    if not cond:
        PASS = False


def main():
    import master as M
    import pukpui_modular_funcs as F
    from golden_snapshot import write_master_file
    # [ADR-102] golden_snapshot.MASTER ว่างแล้ว → นิยาม stub fixture เองสำหรับสร้าง master จริงในเคส 1
    STUB = {
        "ฉี อัน คอนสตรัคชั่น": {
            "name": "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด",
            "tax_id": "0105566206726",
        }
    }

    stub_key = next(iter(STUB))
    stub_tax = STUB[stub_key].get("tax_id")

    def _patch_cfg(mf):
        """master.py ใช้ CFG ที่ import มาเป็นชื่อ local — แพตช์ตรงนั้น (CFG จริงเป็น mappingproxy แก้ไม่ได้)"""
        M.CFG = dict(M.CFG)
        M.CFG["MASTER_FILE"] = mf

    with tempfile.TemporaryDirectory() as td:
        mf = os.path.join(td, "master_companies.json")
        _patch_cfg(mf)
        try:
            # ── เคส 1: master จริง — บริษัทเดียวกับ stub (เลขภาษีชน) แต่ key ผู้ใช้ต่าง ──
            real = {
                "ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์)": {
                    "name": "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์) จำกัด",
                    "tax_id": stub_tax,
                }
            }
            json.dump(real, open(mf, "w", encoding="utf-8"), ensure_ascii=False)
            importlib.reload(M)
            _patch_cfg(mf)  # reload รีเซ็ต CFG ref — ตั้งใหม่
            m = M.load_master()
            _check("master จริง (เลขภาษีตรง stub) → _is_real_master = True",
                   F._is_real_master(m) is True)
            _check("ไม่มี key '_golden_stub' หลุดเข้า dict", "_golden_stub" not in (m or {}))

            # ── เคส 2: stub ที่เครื่องมือ golden เขียน (มี marker ในไฟล์) ──
            write_master_file(mf)
            importlib.reload(M)
            _patch_cfg(mf)
            m2 = M.load_master()
            raw = json.load(open(mf, encoding="utf-8"))
            _check("ไฟล์ stub มี _golden_stub=true", raw.get("_golden_stub") is True)
            _check("load_master ตัด marker ออก (ไม่ปนเป็นบริษัท)", "_golden_stub" not in (m2 or {}))
            _check("stub (มี marker) → _is_real_master = False", F._is_real_master(m2) is False)

            # ── เคส 3: stub รุ่นเก่า (ไม่มี marker) — [ADR-102] golden_snapshot.MASTER ว่างแล้ว →
            #    legacy heuristic (ชั้น 2) เทียบ set(keys)==set() ไม่ติด → ตีเป็น "ของจริง" (True).
            #    marker (เคส 2) คือเกราะหลักแล้ว; golden ว่าง = ไม่มี stub marker-less ใหม่เกิดขึ้น.
            json.dump(STUB, open(mf, "w", encoding="utf-8"), ensure_ascii=False)
            importlib.reload(M)
            _patch_cfg(mf)
            m3 = M.load_master()
            _check("stub เก่าไม่มี marker + golden ว่าง (ADR-102) → legacy heuristic inert → True",
                   F._is_real_master(m3) is True)

            # ── เคส 4: ผู้ใช้พิมพ์สด in-memory (ไม่ผ่านไฟล์) — ต้องไม่ติด flag ค้าง ──
            importlib.reload(M)
            _patch_cfg(mf)
            fresh = {"ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์)": {"name": "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป(ไทยแลนด์) จำกัด", "tax_id": stub_tax}}
            _check("master พิมพ์สด in-memory → True", F._is_real_master(fresh) is True)

            # ── เคส 5: master จริงหลายบริษัท (มีรายอื่นปน) — พฤติกรรมเดิมต้องคงอยู่ ──
            multi = dict(real)
            multi["สยามมิตร สตีล"] = {"name": "บริษัท สยามมิตร สตีล จำกัด", "tax_id": "0105500000001"}
            _check("master หลายบริษัท → True (พฤติกรรมเดิมคง)", F._is_real_master(multi) is True)

            # ── เคส 6: ว่าง/None → False (พฤติกรรมเดิมคง) ──
            _check("master ว่าง → False", F._is_real_master({}) is False)
            _check("master None → False", F._is_real_master(None) is False)
        finally:
            importlib.reload(M)   # คืน CFG ref เดิมของโมดูล

    print()
    if PASS:
        print("RESULT: ✅ STUB-MARKER — master จริงไม่ถูกตีเป็น stub / stub มี marker ถูกกันถูกต้อง")
        return 0
    print("RESULT: ❌ STUB-MARKER มีเคสไม่ผ่าน — ดูด้านบน")
    return 1


if __name__ == "__main__":
    sys.exit(main())
