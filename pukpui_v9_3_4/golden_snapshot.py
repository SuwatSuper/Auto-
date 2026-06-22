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
import atexit
import shutil

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


def _file_has_stub_marker(path: str) -> bool:
    """True ถ้าไฟล์ master ที่ path มี marker `_golden_stub` (= ไฟล์ stub ทดสอบ ไม่ใช่ master จริง)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return isinstance(data, dict) and bool(data.get("_golden_stub"))
    except (OSError, ValueError):
        return False


def _atomic_write_json(path: str, payload: dict) -> None:
    """เขียน JSON แบบ atomic (temp + fsync + os.replace) — kill กลางคันไม่ทำไฟล์ครึ่ง ๆ/ว่าง."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)   # atomic บน FS เดียวกัน


def _restore_master_file(path: str, backup: str) -> None:
    """[P0-FIX ข้อมูลหาย] คืน master เดิมของผู้ใช้จากไฟล์สำรอง (เรียกโดย atexit ตอนโปรเซสจบ).

    [BUGHUNT v9.3.1/ADR-039] คืน "เฉพาะเมื่อไฟล์ปัจจุบันเป็น stub หรือหายไป" — กันเผลอทับ master จริง
    ที่อาจถูกกู้คืนแล้วด้วย backup เก่า. ถ้าไฟล์ปัจจุบันเป็น master จริงอยู่แล้ว → ปล่อย backup ไว้ (ไม่ลบข้อมูล).
    """
    try:
        if not os.path.exists(backup):
            return
        if (not os.path.exists(path)) or _file_has_stub_marker(path):
            os.replace(backup, path)   # atomic; ทับ golden stub กลับเป็นของผู้ใช้
    except OSError:
        pass   # คืนไม่ได้ → ปล่อย backup ไว้ให้ผู้ใช้กู้เอง (ดีกว่าทำโปรเซส exit พัง)


def write_master_file(path: str = "master_companies.json") -> None:
    """เขียนไฟล์ master_companies.json จาก MASTER (โมดูลหลักอ่านไฟล์นี้ตอน input_master_data).

    [P0-FIX ข้อมูลหาย] เครื่องมือ golden/verify (golden_master / verify_golden / verify_parallel /
    verify_report_det / build_consolidated_report / e2e_test / profile_baseline) เรียกฟังก์ชันนี้
    "ในโฟลเดอร์โปรเจกต์" ซึ่งเดิม **เขียนทับ master จริงของผู้ใช้ทิ้งถาวร** ด้วย stub ทดสอบ 1 บริษัท.
    แก้ที่จุดเดียว: ถ้ามี master เดิมอยู่ → สำรองไว้ก่อน แล้ว 'คืนค่าเดิมอัตโนมัติเมื่อโปรเซสจบ' (atexit).
    ระหว่างรันไฟล์ยังเป็น golden MASTER ครบถ้วน → golden hash / report hash ไม่ขยับ (พฤติกรรม sandbox เดิม).

    [BUGHUNT v9.3.1/ADR-039] กันข้อมูลหายถาวร 2 ทาง:
      1) ห้าม copy2 ทับ .user.bak ถ้าไฟล์ปัจจุบันเป็น stub อยู่แล้ว (รอบก่อนถูก kill ก่อน atexit) —
         เดิมทับ → .user.bak (ที่ยังเก็บ master จริง) กลายเป็น stub → master จริงหายถาวร.
      2) ห้ามทับ .user.bak ที่มีอยู่แล้ว (ถือว่าเก็บ master จริงไว้ครบแล้ว).
      เขียน stub แบบ atomic (temp+fsync+replace) — kill กลาง write ไม่ทำไฟล์ครึ่ง/ว่าง.
    """
    backup = path + ".user.bak"
    if os.path.exists(path):
        try:
            # [INF1 FIX 2026-06-20 · แทน ADR-039 #2] สำรอง master "ทุกครั้งที่ไฟล์ปัจจุบันเป็นของจริง" (ไม่ใช่ stub).
            #   เดิม ADR-039 #2 = "ห้ามทับ .user.bak ที่มีอยู่" (สำรองครั้งเดียว) — แต่ทำข้อมูลหายได้:
            #   รอบก่อนถูก kill ก่อน atexit → .user.bak เก่าค้าง + live=stub. ผู้ใช้ใส่ master "ใหม่" (live=จริง).
            #   รอบถัดมา (เดิม) ไม่สำรองของใหม่เพราะ backup มีอยู่ → atexit คืน backup "เก่า" ทับของใหม่ = หายถาวร.
            #   ใหม่: refresh backup จาก live เมื่อ live เป็นของจริง → .user.bak สะท้อน "master ก่อนรอบนี้" เสมอ
            #   = สัญญาที่ถูกต้องของ backup (กู้สิ่งที่อยู่ก่อนเครื่องมือ golden แตะ). คงกติกาเดิมข้อสำคัญ:
            #   live=stub → ไม่ทับ backup (กัน stub กลืน master จริงที่ backup เก็บไว้). atomic: temp+replace.
            if not _file_has_stub_marker(path):
                _tmp_bak = backup + ".tmp"
                shutil.copy2(path, _tmp_bak)
                os.replace(_tmp_bak, backup)
            if os.path.exists(backup):
                atexit.register(_restore_master_file, path, backup)
        except OSError:
            pass   # สำรองไม่ได้ → ยังเขียน golden ตามเดิม (อย่าทำให้เครื่องมือล้ม)
    # [STUB-MARKER] ใส่ "_golden_stub": true เฉพาะ "ในไฟล์" (ไม่แตะ MASTER dict ที่ใช้คำนวณ golden) —
    #   _is_real_master จะใช้ marker นี้แยก stub ออกจาก master จริง "โดยไม่เดาจากเนื้อหา"
    #   (เดิมเดาจากเลขภาษี → master จริงของบริษัทเดียวกับ stub เช่น ฉีอัน ถูกตีเป็น stub ทิ้งทั้งที่เป็นของจริง)
    _payload = dict(MASTER)
    _payload["_golden_stub"] = True
    _atomic_write_json(path, _payload)


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


def _path_prefixes(file_list):
    """[v9.3 PORTABLE GOLDEN — P0-A] รวม prefix ของโฟลเดอร์ข้อมูลทุกรูป (dirname/abspath/realpath,
    มี/ไม่มีตัวคั่นท้าย) เรียงยาว→สั้น เพื่อ strip ออกจาก snapshot ก่อน hash.
    ตัดรูป degenerate ('', '.', '/', sep เดี่ยว) ทิ้ง — กันการ strip กว้างเกินจนกินเนื้อข้อมูล."""
    pres = set()
    for f in (file_list or []):
        d = os.path.dirname(str(f))
        for cand in {d, os.path.abspath(d) if d else '', os.path.realpath(d) if d else ''}:
            cand = (cand or '').rstrip('/\\')
            if cand in ('', '.', '/', '\\') or len(cand) < 2:
                continue
            pres.add(cand + os.sep)
            pres.add(cand + '/')      # กันเคสคนละ separator (Windows path ใน Unix และกลับกัน)
            pres.add(cand)
    return sorted(pres, key=len, reverse=True)


def _strip_paths(obj, prefixes):
    """[v9.3 PORTABLE GOLDEN — P0-A] เดิน recursive คืน "สำเนา" ที่ปลอด path ของเครื่อง:
      - key 'filepath' (ของแต่ละ bill) → os.path.basename ตรง ๆ (กันเคส degenerate เช่น data dir = '.')
      - สตริงอื่นทั้งหมด (รวม summary) → แทนที่ทุก occurrence ของ prefix ด้วย ''
    ห้าม mutate ของเดิม — pipeline/รายงานยังใช้ filepath เต็มต่อ (พฤติกรรม engine ไม่เปลี่ยน)."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == 'filepath' and isinstance(v, str):
                out[k] = os.path.basename(v)
            else:
                out[k] = _strip_paths(v, prefixes)
        return out
    if isinstance(obj, (list, tuple)):
        return [_strip_paths(x, prefixes) for x in obj]
    if isinstance(obj, str):
        s = obj
        for p in prefixes:
            if p in s:
                s = s.replace(p, '')
        return s
    return obj


def build_snapshot(file_list, all_bills, filename_issues,
                   dup_items, iv_seq, iv_date, typos, summary) -> dict:
    """ประกอบ snapshot dict (โครง field/ลำดับ "คงที่" — ทั้งสองเส้นต้องเหมือนกัน).

    [v9.3 PORTABLE GOLDEN — P0-A] snapshot ถูก sanitize ให้ path-independent ก่อนคืน:
    เดิม bill['filepath'] เก็บ path เต็ม + summary พก path → hash ผูกกับตำแหน่งโฟลเดอร์
    (corpus เดียวกันคนละ path = hash คนละค่า → ย้ายเครื่อง/โฟลเดอร์ = false regression).
    แก้จุดเดียวนี้ครอบทั้งเส้น engine (golden_master) และ agent (verify_golden).
    fail-closed: sanitize แล้วยังเหลือ prefix ใน blob → raise ทันที (ห้ามคืน hash สกปรก)."""
    prefixes = _path_prefixes(file_list)
    snap = {
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
    snap = _strip_paths(snap, prefixes)
    blob = json.dumps(snap, ensure_ascii=False, sort_keys=True, indent=0)
    for p in prefixes:
        if p in blob:
            raise RuntimeError(
                f"[PORTABLE GOLDEN fail-closed] sanitize ไม่สะอาด — ยังพบ prefix {p!r} ใน snapshot blob")
    return snap


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
