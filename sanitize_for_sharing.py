# -*- coding: utf-8 -*-
"""
sanitize_for_sharing.py — สร้างแพ็ก "แจกจ่ายได้" ปลอด PII จาก release zip [ADR-159]

ปัญหาที่แก้: release หลักมีข้อมูลจริงของลูกค้า (baseline.json = สแนปช็อต 1153 บิลจริง
  มี tax_id/ที่อยู่/ชื่อบริษัท ; tests/real_cases/*.xls = ใบกำกับจริง 3 ไฟล์). ห้ามแชร์ให้คนนอก.
  tool นี้สร้าง "สำเนา shareable" ที่ลบ/ปิดบัง PII ออก โดย "ไม่แตะ" แพ็กหลัก.

วิธีใช้:
    python3 sanitize_for_sharing.py <release.zip>       # → <release>_SHAREABLE.zip

สิ่งที่ทำ:
  • baseline.json      → ปิดบัง (redact) ฟิลด์ PII ใน all_bills (company/address/tax_id/…) เป็น "[REDACTED]"
                          คง _sha256 / n_files / n_bills / โครงสร้าง / รหัส issue ไว้ (fixture CI ยังผ่าน)
  • tests/real_cases/  → ลบทั้งโฟลเดอร์ (ใบกำกับจริง)
  • canary_baseline.json → ลบ (derive จากข้อมูลจริง)

แพ็ก shareable:
  ✅ verify ด้วย fixture golden (ad0c9dad) ได้ปกติ — `bash run_ci.sh` (ไม่ต้องมี corpus)
  ⚠  regression ข้อมูลจริง [7]/[8] ใช้ไม่ได้ (ไม่มี baseline จริง/corpus) = ตั้งใจ (คนนอกไม่มี corpus อยู่แล้ว)
"""
import sys, os, io, json, zipfile

# ฟิลด์ PII ที่เป็น "ค่าจริง" — เก็บค่ามาแทนที่ทุกที่ในบิล (รวมที่ฝังใน issues/reasons)
_PII_VALUE_FIELDS = ("company", "company_raw", "address", "tax_id", "tax_id_raw")
# ฟิลด์ที่ตั้งเป็น [REDACTED] ตรงๆ (semi-identifying — ไม่ค่อยฝังใน free-text)
_PII_NULL_FIELDS = ("master_key", "file", "filepath", "branch", "branch_no",
                    "iv_number", "iv_number_raw")
# รวมไว้ให้ self-check/doctor อ้างอิง
_PII_FIELDS = _PII_VALUE_FIELDS + _PII_NULL_FIELDS
# ไฟล์/โฟลเดอร์ที่ตัดทิ้ง
_DROP_EXACT = {"canary_baseline.json"}


def _is_dropped(name: str) -> bool:
    base = name.split("/")[-1]
    if base in _DROP_EXACT:
        return True
    if "/real_cases/" in ("/" + name) or name.startswith("real_cases/"):
        return True
    return False


def _redact_baseline(raw: bytes) -> bytes:
    """คง _sha256/n_files/n_bills/โครงสร้าง/รหัส issue ; ปิดบัง PII แบบ text-level global:
    (1) null ฟิลด์ PII ที่รู้ชื่อ (2) แทนค่า company/address 'ทุกที่' (รวมฝังใน free-text)
    (3) regex แทน tax-id pattern (13 หลัก/dash) 'ทุกที่' โดยกัน float artifact ด้วย lookaround."""
    import re as _re
    txt = raw.decode("utf-8")
    obj = json.loads(txt)
    # (1) เก็บค่า company/address ทั้งหมด (global) + null ฟิลด์ PII ที่รู้ชื่อ
    vals = set()
    for b in obj.get("all_bills", []):
        for k in ("company", "company_raw", "address"):
            v = b.get(k)
            if isinstance(v, str) and len(v.strip()) >= 3:
                vals.add(v.strip())
        for k in _PII_VALUE_FIELDS + _PII_NULL_FIELDS:
            if k in b and b[k] not in (None, "", [], {}):
                b[k] = "[REDACTED]"
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1)
    # (2) text-level: company/address ที่ฝังใน free-text (issues/reasons) — ยาวสุดก่อน
    for pv in sorted(vals, key=len, reverse=True):
        s = s.replace(pv, "[REDACTED]")
    # (3) text-level: tax-id pattern ทุกที่ (float-safe: (?<![\d.]) … (?![\d.]))
    s = _re.sub(r"(?<![\d.])\d{13}(?![\d.])", "[REDACTED]", s)
    s = _re.sub(r"\d-\d{4}-\d{5}-\d{2}-\d", "[REDACTED]", s)
    obj2 = json.loads(s)   # validate ยังเป็น JSON ถูกต้อง
    obj2["_redacted"] = True
    return json.dumps(obj2, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print("ใช้: python3 sanitize_for_sharing.py <release.zip>")
        return 2
    src = sys.argv[1]
    if not os.path.isfile(src):
        print(f"❌ ไม่พบไฟล์: {src}")
        return 1
    if not zipfile.is_zipfile(src):
        print(f"❌ ไม่ใช่ไฟล์ zip ที่ถูกต้อง (เสียหาย?): {src}")
        return 1
    out = (src[:-4] if src.endswith(".zip") else src) + "_SHAREABLE.zip"

    dropped, redacted = [], []
    with zipfile.ZipFile(src) as zin, \
         zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            name = item.filename
            if _is_dropped(name):
                dropped.append(name)
                continue
            data = zin.read(name)
            if name.split("/")[-1] == "baseline.json":
                try:
                    data = _redact_baseline(data)
                    redacted.append(name)
                except Exception as e:
                    print(f"⚠  redact {name} ไม่ได้ ({e}) → ตัดทิ้งแทนเพื่อความปลอดภัย")
                    dropped.append(name)
                    continue
            zout.writestr(item, data)

    # self-check: (ก) ฟิลด์ PII ต้อง redact หมด (ข) scan เลขภาษี 13 หลัก/รูป dash "ทุกที่" (รวมฝังใน free-text)
    #   โดยกัน float artifact (เศษทศนิยม) ด้วย negative lookaround (?<![\d.]) … (?![\d.])
    import re as _re
    leaked = []
    _taxpat = _re.compile(r"(?<![\d.])\d{13}(?![\d.])|\d-\d{4}-\d{5}-\d{2}-\d")
    with zipfile.ZipFile(out) as z:
        for n in z.namelist():
            if n.split("/")[-1] == "baseline.json":
                txt = z.read(n).decode("utf-8", "ignore")
                obj = json.loads(txt)
                for b in obj.get("all_bills", []):
                    for k in _PII_FIELDS:
                        v = b.get(k)
                        if v not in (None, "", "[REDACTED]", [], {}):
                            leaked.append(f"{n}:{k}={str(v)[:20]}")
                # value-scan: เลขภาษีหลุดในรูปใดก็ตาม
                m = _taxpat.findall(txt)
                if m:
                    leaked.append(f"{n}: พบเลขภาษี {len(m)} จุด (เช่น {m[0]})")
    if leaked:
        # fail-closed: ลบ output ทิ้ง ไม่ให้เหลือแพ็กที่ยังมี PII
        try:
            os.remove(out)
        except OSError:
            pass
        print(f"   🚨 พบ PII หลงเหลือ {len(leaked)} จุด (เช่น {leaked[:3]}) → ลบแพ็ก shareable ทิ้งแล้ว (fail-closed)")
        print("      แก้ _redact_baseline ให้ครอบคลุมก่อน แล้วรันใหม่ — ห้ามแชร์แพ็กที่มี PII")
        return 1
    print(f"✅ แพ็ก shareable: {out}")
    print(f"   • ปิดบัง (redact): {len(redacted)} ไฟล์ {redacted}")
    print(f"   • ตัดทิ้ง: {len(dropped)} รายการ" + (" (real_cases + canary)" if dropped else ""))
    print("   • PII self-check: ✅ ไม่พบ PII หลงเหลือ (ฟิลด์ + scan เลขภาษีทุกที่)")
    print("   หมายเหตุ: verify ด้วย fixture golden (ad0c9dad) ได้ — `bash run_ci.sh` ;"
          " regression ข้อมูลจริงใช้ไม่ได้ (ตั้งใจ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
