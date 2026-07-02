# -*- coding: utf-8 -*-
"""
machine_check.py — ตอบคำถามเดียว: "เครื่องนี้โฮสต์ระบบปุ้มปุ้ยได้ไหม?" [ADR-163]

ปิด gap 5 ปีอันดับ 1: เครื่องหลักพังปี 3 → ได้เครื่องใหม่มา แล้ว "เพิ่งมารู้" ว่า
Python/OS ไม่เข้ากับ wheelhouse (cp312, linux x86_64) ตอนติดตั้งพัง.
tool นี้เช็คให้จบใน 30 วินาที "ก่อน" commit เครื่อง — ใช้ตอน (ก) เลือกเครื่องสำรอง/เครื่องใหม่
(ข) ซ้อมกู้คืนประจำปี (OPERATOR_RUNBOOK ข้อ 9).

ใช้: python3 machine_check.py        (รันจากโฟลเดอร์ release ที่แตกแล้ว ถ้ามี wheels/ จะเช็คให้ด้วย)
สแตนด์อโลน stdlib ล้วน — รันได้แม้ Python เวอร์ชันอื่น (เพื่อรายงานว่า "ผิดเวอร์ชัน").
exit 0 = เครื่องพร้อม ; 1 = มีข้อไม่ผ่าน (ดูวิธีแก้ท้ายรายงาน)
"""
import os
import sys
import glob
import shutil
import platform
import tempfile

OK, WARN, FAIL = "✅", "⚠️", "🚨"
_fails = []
_fixes = []


def _row(icon, label, detail):
    print("  {} {:16}: {}".format(icon, label, detail))


def main():
    print("=" * 64)
    print("MACHINE CHECK — เครื่องนี้โฮสต์ระบบปุ้มปุ้ยได้ไหม? [ADR-163]")
    print("=" * 64)

    # [1] Python 3.12.x (wheelhouse เป็น cp312 — เวอร์ชันอื่นติดตั้ง offline ไม่ได้)
    v = sys.version_info
    vs = "{}.{}.{}".format(v.major, v.minor, v.micro)
    if (v.major, v.minor) == (3, 12):
        _row(OK, "Python", vs + " (ต้อง 3.12.x — ตรง)")
    else:
        _row(FAIL, "Python", vs + " — ต้องเป็น 3.12.x (wheels เป็น cp312)")
        _fails.append("python")
        _fixes.append("ติดตั้ง Python 3.12: Ubuntu → `sudo apt install python3.12 python3.12-venv` "
                      "หรือใช้ pyenv/uv สร้าง 3.12 แยก แล้วรันระบบด้วย python3.12")

    # [2] OS/สถาปัตยกรรม (wheels เป็น linux x86_64)
    mach = platform.machine()
    plat = sys.platform
    if plat.startswith("linux") and mach in ("x86_64", "AMD64"):
        _row(OK, "OS/arch", "{} / {} (ตรง wheelhouse)".format(plat, mach))
    else:
        _row(FAIL, "OS/arch", "{} / {} — wheelhouse รองรับเฉพาะ linux x86_64".format(plat, mach))
        _fails.append("os")
        _fixes.append("ใช้เครื่อง/VM Linux x86_64 (เช่น Ubuntu 24) — ARM/Windows/macOS "
                      "ติดตั้งจาก wheelhouse นี้ไม่ได้")

    # [3] pip พร้อมไหม (ติดตั้ง offline ต้องมี pip)
    try:
        import importlib.util as _u
        has_pip = _u.find_spec("pip") is not None
    except Exception:
        has_pip = False
    if has_pip:
        _row(OK, "pip", "มี")
    else:
        _row(FAIL, "pip", "ไม่มี — ติดตั้ง offline ไม่ได้")
        _fails.append("pip")
        _fixes.append("ติดตั้ง pip: `sudo apt install python3-pip` หรือ `python3 -m ensurepip`")

    # [4] wheelhouse (ถ้ารันจากโฟลเดอร์ release)
    whl = sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "wheels", "*.whl")))
    if len(whl) >= 21:
        _row(OK, "wheels/", "{} ไฟล์ (ครบสำหรับติดตั้ง offline)".format(len(whl)))
    elif whl:
        _row(WARN, "wheels/", "{} ไฟล์ — น้อยกว่าที่คาด (21) ตรวจว่าแตก zip ครบ".format(len(whl)))
    else:
        _row(WARN, "wheels/", "ไม่พบ — ถ้าจะเช็คให้ครบ ให้รันไฟล์นี้จากในโฟลเดอร์ release ที่แตกแล้ว")

    # [5] พื้นที่ดิสก์ (ระบบ+corpus+ทำงาน ~ ต้องการเผื่อ ≥ 2GB)
    try:
        free_gb = shutil.disk_usage(os.getcwd()).free / (1024 ** 3)
        if free_gb >= 2:
            _row(OK, "ดิสก์ว่าง", "{:.1f} GB".format(free_gb))
        else:
            _row(FAIL, "ดิสก์ว่าง", "{:.1f} GB — ต้องการ ≥ 2 GB".format(free_gb))
            _fails.append("disk")
            _fixes.append("เคลียร์พื้นที่ดิสก์ให้ว่าง ≥ 2 GB ก่อนติดตั้ง")
    except Exception as e:
        _row(WARN, "ดิสก์ว่าง", "เช็คไม่ได้ ({})".format(type(e).__name__))

    # [6] เขียนไฟล์ชั่วคราวได้ (สิทธิ์พื้นฐาน)
    try:
        with tempfile.NamedTemporaryFile(prefix="puopuy_chk_", delete=True) as f:
            f.write(b"ok")
        _row(OK, "สิทธิ์เขียน", "เขียน temp ได้")
    except Exception as e:
        _row(FAIL, "สิทธิ์เขียน", "เขียน temp ไม่ได้ ({})".format(type(e).__name__))
        _fails.append("write")
        _fixes.append("ตรวจสิทธิ์ผู้ใช้/พื้นที่ /tmp")

    print("=" * 64)
    if not _fails:
        print("  ✅ เครื่องนี้พร้อมโฮสต์ระบบ — ขั้นถัดไป:")
        print("     1) ติดตั้ง offline ตาม QUICKSTART ในแพ็ก (pip --no-index --find-links wheels ...)")
        print("     2) ยืนยันความถูกต้อง: python3 regression_full.py . tests/fixtures "
              "tests/fixtures/baseline_fixture.json  → ต้องได้ ad0c9dad…")
        print("     3) python3 doctor.py")
        print("=" * 64)
        return 0
    print("  🚨 ไม่ผ่าน {} ข้อ — วิธีแก้:".format(len(_fails)))
    for i, fx in enumerate(_fixes, 1):
        print("     {}) {}".format(i, fx))
    print("=" * 64)
    return 1


if __name__ == "__main__":
    sys.exit(main())
