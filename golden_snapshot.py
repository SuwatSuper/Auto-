# -*- coding: utf-8 -*-
"""
golden_snapshot.py — แหล่งความจริงเดียวของ "golden snapshot"
    (MASTER ทดสอบ + canonical serializer + โครง snapshot + วิธีคำนวณ SHA256)

ทำไมต้องมีไฟล์นี้ (v9.1 DECOUPLE):
    เดิม golden_master.py (เส้น engine) และ verify_golden.py (เส้น agent) ต่าง "ก๊อป"
    ของสามอย่างนี้ไว้ในตัวเอง:
        1) MASTER (master ทดสอบ)         — ต้องเหมือนกันเป๊ะ ผล hash ถึงเทียบกันได้
        2) canonical(obj)                — สูตร serialize แบบ deterministic
        3) โครง snapshot + วิธี hash      — field/ลำดับ/encoding ต้องตรงกัน
    ถ้าแก้ที่หนึ่งลืมอีกที่ (เช่นอัป MASTER ฝั่งเดียว) → hash เทียบกันไม่ได้ →
    verify_golden อาจรายงาน "ไม่ตรง" ทั้งที่โค้ดถูก (false mismatch) หรือแย่กว่านั้น
    เทียบผ่านทั้งที่ทั้งคู่ผิดเหมือนกัน. รวมไว้ที่เดียว = ตรงกันโดยโครงสร้าง.

ทั้ง golden_master.py และ verify_golden.py insert PKG_DIR ลง sys.path + chdir มาที่ PKG_DIR
ก่อน import โมดูลนี้ จึง import ได้ทั้งคู่ (รวมตอนถูกเรียกเป็น subprocess จาก regression_full.py).
"""
import os
import json
import hashlib

# ---------------------------------------------------------------------------
# master ทดสอบมาตรฐาน — "เส้น engine" และ "เส้น agent" ต้องใช้ชุดนี้ชุดเดียวกัน
#   (ผล hash ถึงเทียบกันได้). อยากเปลี่ยน master ทดสอบ: แก้ที่นี่ "ที่เดียว".
# ---------------------------------------------------------------------------
MASTER = {
    "ฉี อัน คอนสตรัคชั่น": {
        "name": "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด",
        "tax_id": "0105566206726",
        "branch": "สำนักงานใหญ่",
        "address": "เลขที่ 5/32 ซอย ศรีนครินทร์ 46/1 เขตประเวศ กรุงเทพมหานคร 10250",
        "iv_prefix": "IV",
    }
}


def write_master_file(path: str = "master_companies.json") -> None:
    """เขียนไฟล์ master_companies.json จาก MASTER (โมดูลหลักอ่านไฟล์นี้ตอน input_master_data)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(MASTER, f, ensure_ascii=False)


def canonical(obj):
    """แปลงทุกชนิดให้ serialize ได้แบบ deterministic (set→sorted list, อื่นๆ→str).

    กฎ (คงที่ — ห้ามเปลี่ยนถ้าไม่ตั้งใจ rebase baseline):
      - None/bool/int/float/str  → คงค่าเดิม
      - dict                     → คีย์เรียงด้วย str(key) แล้ว canonical ค่าซ้ำ
      - list/tuple               → canonical สมาชิกตามลำดับ
      - set                      → ['__set__'] + สมาชิก canonical เรียงด้วย json ของมัน (เสถียร)
      - datetime/date            → ISO 8601
      - numpy scalar/array       → แปลงเป็น python ก่อน canonical
      - อื่นๆ                     → '<TypeName>repr' (กันค่าแปลกหลุดเข้า hash โดยไม่รู้ตัว)
    """
    import datetime as _dt
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): canonical(obj[k]) for k in sorted(obj.keys(), key=str)}
    if isinstance(obj, (list, tuple)):
        return [canonical(x) for x in obj]
    if isinstance(obj, set):
        return ['__set__'] + sorted([canonical(x) for x in obj],
                                    key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    # numpy / pandas / อื่นๆ
    try:
        import numpy as np
        if isinstance(obj, np.generic):
            return canonical(obj.item())
        if isinstance(obj, np.ndarray):
            return [canonical(x) for x in obj.tolist()]
    except Exception:
        # numpy ไม่ได้ติดตั้ง / ไม่ใช่ชนิด numpy — ตกไป fallback ด้านล่าง (ไม่กลืน error อื่น)
        pass
    return f'<{type(obj).__name__}>{obj!r}'


def build_snapshot(file_list, all_bills, filename_issues,
                   dup_items, iv_seq, iv_date, typos, summary) -> dict:
    """ประกอบ snapshot dict (โครง field/ลำดับ "คงที่" — ทั้งสองเส้นต้องเหมือนกัน)."""
    return {
        'n_files':         len(file_list),
        'file_names':      [os.path.basename(f) for f in file_list],
        'n_bills':         len(all_bills),
        'all_bills':       canonical(all_bills),
        'filename_issues': canonical(filename_issues),
        'dup_items':       canonical(dup_items),
        'iv_seq':          canonical(iv_seq),
        'iv_date':         canonical(iv_date),
        'typos':           canonical(typos),
        'summary':         canonical(summary),
    }


def hash_snapshot(snapshot: dict) -> str:
    """คำนวณ SHA256 ของ snapshot (json canonical: sort_keys, indent=0, utf-8).

    หมายเหตุ: คำนวณจาก snapshot ที่ "ยังไม่มีคีย์ _sha256" (golden_master เพิ่ม _sha256
    หลังคำนวณเสร็จแล้วค่อยเขียนไฟล์) — สูตรนี้ตรงกับของเดิมเป๊ะ.
    """
    blob = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=0)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()


def snapshot_and_hash(file_list, all_bills, filename_issues,
                      dup_items, iv_seq, iv_date, typos, summary):
    """สะดวก: คืน (snapshot, sha256_hex) ในครั้งเดียว."""
    snap = build_snapshot(file_list, all_bills, filename_issues,
                          dup_items, iv_seq, iv_date, typos, summary)
    return snap, hash_snapshot(snap)
