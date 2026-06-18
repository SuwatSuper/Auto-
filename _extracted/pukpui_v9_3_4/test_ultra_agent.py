# -*- coding: utf-8 -*-
"""test_ultra_agent.py — ตรวจ Ultra Agent (ตัวช่วยตรวจทาน-ยืนยันความจริง).

ครอบ: checksum บิล (arith/vat), เลขภาษี mod-11, verdict ของ verify_finding
(ยืนยัน/ควรตรวจซ้ำ/น่าจะปกติ), การ emit + consolidate, และ determinism.
advisory ล้วน — ไม่แตะ golden (ตรวจแยกใน CI).

รัน: PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_ultra_agent.py
"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ultra_agent as UA   # noqa: E402

_FAILS = []


def chk(name, cond):
    print(("  ✅ " if cond else "  ❌ ") + name)
    if not cond:
        _FAILS.append(name)


def _valid_tax13():
    """สร้างเลขภาษี 13 หลักที่ mod-11 ถูกต้อง (12 หลักแรกคงที่ + คำนวณหลักเช็ค)."""
    base = "010555678901"  # 12 หลัก
    chk_sum = sum(int(base[i]) * (13 - i) for i in range(12))
    last = (11 - (chk_sum % 11)) % 10
    return base + str(last)


def _bill(sub, vat, tot, **kw):
    b = {"file": kw.get("file", "X_69_05.xls"), "sheet": kw.get("sheet", "1"),
         "company": kw.get("company", "บริษัท ทดสอบ จำกัด"),
         "tax_id": kw.get("tax_id", _valid_tax13()),
         "iv_number": kw.get("iv", "IV1"),
         "iv_date": kw.get("iv_date", datetime.datetime(2026, 5, 1)),
         "iv_date_str": kw.get("iv_date_str", "01/05/2026"),
         "subtotal": sub, "vat": vat, "total": tot,
         "items": kw.get("items", []), "issues": kw.get("issues", [])}
    return b


def main():
    print("=" * 64)
    print("TEST Ultra Agent — checksum / mod-11 / verdict / determinism")
    print("=" * 64)

    # ── checksums ──
    cs_ok = UA.bill_checksums(_bill(100.0, 7.0, 107.0))
    chk("checksum: 100+7=107 → arith_ok", cs_ok["arith_ok"] is True)
    chk("checksum: vat 7 = 7%×100 → vat_ok", cs_ok["vat_ok"] is True)
    cs_bad = UA.bill_checksums(_bill(100.0, 7.0, 120.0))
    chk("checksum: 100+7≠120 → arith_ok False", cs_bad["arith_ok"] is False)
    cs_vat = UA.bill_checksums(_bill(100.0, 10.0, 110.0))
    chk("checksum: vat 10 ≠ 7% → vat_ok False (arith ยังถูก)",
        cs_vat["vat_ok"] is False and cs_vat["arith_ok"] is True)

    # ── เลขภาษี mod-11 ──
    good = _valid_tax13()
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)
    chk("mod-11: เลขถูก → True", UA.thai_tax_valid(good) is True)
    chk("mod-11: พลิกหลักสุดท้าย → False", UA.thai_tax_valid(bad) is False)
    chk("mod-11: ไม่ครบ 13 หลัก → None", UA.thai_tax_valid("123") is None)

    # ── verify_finding: verdict ──
    # TAX006 (checksum ไม่ผ่าน) + เลขผิดจริง → ยืนยัน
    r = UA.verify_finding(_bill(100, 7, 107, tax_id=bad), "TAX006", "", UA.bill_checksums(_bill(100, 7, 107)), [])
    chk("TAX006 + เลขผิดจริง → ยืนยัน", r["verdict"] == UA.V_CONFIRM)
    # TAX006 ฟ้อง แต่เลขถูกตามสูตร → น่าจะปกติ (หลักฐานค้าน)
    r = UA.verify_finding(_bill(100, 7, 107, tax_id=good), "TAX006", "", UA.bill_checksums(_bill(100, 7, 107)), [])
    chk("TAX006 ฟ้อง แต่ mod-11 ผ่าน → น่าจะปกติ", r["verdict"] == UA.V_LIKELY_OK)
    # ITM001 + ยอดรวมไม่ลงตัว → ยืนยัน
    bad_bill = _bill(100, 7, 120)
    r = UA.verify_finding(bad_bill, "ITM001", "#1", UA.bill_checksums(bad_bill), [])
    chk("ITM001 + ยอดรวมไม่ลงตัว → ยืนยัน", r["verdict"] == UA.V_CONFIRM)
    # ITM001 + ยอดรวมถูก (line-level) → ควรตรวจซ้ำ (ไม่เคลียร์บรรทัด)
    ok_bill = _bill(100, 7, 107)
    r = UA.verify_finding(ok_bill, "ITM001", "#2", UA.bill_checksums(ok_bill), [])
    chk("ITM001 + ยอดรวมถูก → ควรตรวจซ้ำ (เฉพาะบรรทัด)", r["verdict"] == UA.V_RECHECK)
    # DOC001 (วันที่ เชิงโครงสร้าง, RELIABLE) → ยืนยัน
    r = UA.verify_finding(ok_bill, "DOC001", "ชีต=7 แต่วันที่=18", UA.bill_checksums(ok_bill), [])
    chk("DOC001 (วันที่ โครงสร้าง) → ยืนยัน", r["verdict"] == UA.V_CONFIRM)
    # ITM010 (typo fuzzy) → ควรตรวจซ้ำ
    r = UA.verify_finding(ok_bill, "ITM010", '#2: "มั้วน" → "ม้วน"', UA.bill_checksums(ok_bill), [])
    chk("ITM010 (typo fuzzy) → ควรตรวจซ้ำ", r["verdict"] == UA.V_RECHECK)
    # ITM018 (จำนวน=0 มียอด) → ยืนยัน
    r = UA.verify_finding(ok_bill, "ITM018", "#1 จำนวน=0", UA.bill_checksums(ok_bill), [])
    chk("ITM018 (จำนวน=0 มียอดเงิน) → ยืนยัน", r["verdict"] == UA.V_CONFIRM)

    # ── ครอบคลุมทุกรหัส A-Z: ทุก code (lane finding) ต้อง classify + ตัดสินได้ ไม่ crash ──
    import code_labels as C
    all_codes = sorted(C.MAP.keys())
    finding_codes = [c for c in all_codes if C.lane_of(c) in ("fix", "check", "master", "review")]
    note_codes = [c for c in all_codes if C.lane_of(c) == "note"]
    classified = UA.RELIABLE_CODES | UA.FUZZY_CODES | UA.MASTER_CODES
    unclassified = [c for c in finding_codes if c not in classified]
    chk(f"ทุกรหัส finding ({len(finding_codes)}) ถูก classify ครบ (ไม่มีตกหล่น)", not unclassified)
    if unclassified:
        print("     ⚠️ ตกหล่น:", unclassified)
    chk("รหัส NOTE แยกออกจากชุด finding ครบ", set(note_codes) == UA.NOTE_CODES)
    # ไม่มีรหัสซ้ำข้ามชุด (RELIABLE/FUZZY/MASTER แยกขาดกัน)
    overlap = (UA.RELIABLE_CODES & UA.FUZZY_CODES) | (UA.RELIABLE_CODES & UA.MASTER_CODES) | (UA.FUZZY_CODES & UA.MASTER_CODES)
    chk("ชุด RELIABLE/FUZZY/MASTER ไม่ทับกัน", not overlap)

    valid_verdicts = {UA.V_CONFIRM, UA.V_RECHECK, UA.V_LIKELY_OK}
    test_bill = _bill(100, 7, 107, items=[{"seq": 1, "name": "x", "name_raw": "x",
                                           "qty": 1.0, "price": 100.0, "amount": 100.0, "unit": "ชิ้น"}])
    cs0 = UA.bill_checksums(test_bill)
    crashed, badv = [], []
    for c in finding_codes:
        try:
            rr = UA.verify_finding(test_bill, c, "#1 รายละเอียด", cs0, [])
            if rr["verdict"] not in valid_verdicts:
                badv.append((c, rr.get("verdict")))
        except Exception as e:
            crashed.append((c, type(e).__name__ + ":" + str(e)[:40]))
    chk(f"verify_finding รันได้ทุกรหัส ({len(finding_codes)}) ไม่ crash", not crashed)
    if crashed:
        print("     ⚠️ crash:", crashed[:5])
    chk("ทุกรหัสได้ verdict ที่ถูกต้อง (🔴/🟡/🟢)", not badv)
    # FUZZY+MASTER (บิลปกติ) → ต้องเป็น 'ควรตรวจซ้ำ' เสมอ
    fm_wrong = [(c, UA.verify_finding(test_bill, c, "#1", cs0, [])["verdict"])
                for c in sorted(UA.FUZZY_CODES | UA.MASTER_CODES)
                if UA.verify_finding(test_bill, c, "#1", cs0, [])["verdict"] != UA.V_RECHECK]
    chk("FUZZY+MASTER ทุกตัว → ควรตรวจซ้ำ (บิลปกติ)", not fm_wrong)
    if fm_wrong:
        print("     ⚠️ ผิด:", fm_wrong[:5])

    # ── verify_company + emit + consolidate ──
    tid = _valid_tax13()
    g = [_bill(100, 7, 107, tax_id=tid, iv=f"IV{i}") for i in range(3)]
    g[0]["issues"] = [{"code": "DOC001", "detail": "ชีต=7 แต่วันที่=18", "severity": "WARNING"}]
    # บิลชื่อพิมพ์ต่าง (จำกัด เกิน) แต่ tax เดียว → ต้องรวมเป็น 1 กลุ่ม
    g[1]["company"] = "บริษัท ทดสอบ จำกัด จำกัด"
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        vcs = UA.build_ultra(g, master_present=True)
    chk("build_ultra: รวมเป็น 1 บริษัท×เดือน (group ด้วยเลขภาษี)", len(vcs) == 1)
    chk("build_ultra: นับ 3 บิล", vcs[0]["n"] == 3)
    chk("build_ultra: checksum ยอดผ่าน 3/3", vcs[0]["arith_pass"] == 3)
    chk("build_ultra: มี 1 จุดตรวจทาน (DOC001)", len(vcs[0]["checks"]) == 1)
    chk("build_ultra: DOC001 + พี่น้องวันที่ปกติ → ยืนยัน (overall)", vcs[0]["overall"] == UA.V_CONFIRM)

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        with contextlib.redirect_stdout(io.StringIO()):
            p = UA.emit_ultra_summary(g, d, master_present=True)
        txt = open(p, encoding="utf-8").read()
    chk("emit: ไฟล์มีหัว 'Ultra Agent'", "Ultra Agent" in txt)
    chk("emit: โชว์ยอดก่อน VAT (300)", "300" in txt)
    chk("emit: DOC001 ถูกตัดสิน 'ยืนยัน'", "ยืนยัน" in txt)
    chk("emit: ระบุ checksum อิสระ", "checksum" in txt and "VAT 7%" in txt)

    # ── determinism: รัน 2 ครั้ง → verdict เหมือนกัน ──
    with contextlib.redirect_stdout(io.StringIO()):
        v1 = UA.build_ultra(g, master_present=True)
        v2 = UA.build_ultra(g, master_present=True)
    chk("determinism: verdict ภาพรวมเหมือนกัน 2 รอบ",
        [x["overall"] for x in v1] == [x["overall"] for x in v2])

    print("-" * 64)
    if _FAILS:
        print(f"❌ FAIL: {len(_FAILS)} ข้อ → {_FAILS}")
        return 1
    print("✅ PASS — Ultra Agent: checksum/mod-11/verdict/consolidate/determinism ครบ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
