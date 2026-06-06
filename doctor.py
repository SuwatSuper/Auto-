# -*- coding: utf-8 -*-
"""doctor.py — ตรวจ "ความพร้อมระบบ" แบบ non-interactive (offline) ก่อนเริ่มงาน

ตอบคำถามเดียว: **เครื่องนี้พร้อมรันปุ้มปุ้ย v9.1 ให้ผล reproduce ได้ไหม?**
รวมการตรวจที่กระจายอยู่หลายที่ ให้เห็นภาพเดียวจบ + บอก "ต้องแก้อะไร" เป็นข้อ ๆ:

  [1] Python interpreter      — major.minor ตรง config._LOCKED (3.12) ไหม
  [2] Dependencies            — เรียก version_gate.check() (pandas/xlrd/openpyxl/rapidfuzz ฯลฯ)
  [3] Environment             — PYTHONHASHSEED=0 (จำเป็นต่อ golden) + PUOPUY_AUDIT_DATE (โหมดทดสอบ)
  [4] Git hooks               — pre-commit ติดตั้งแล้วไหม (กัน golden พังตอน commit)
  [5] Fixtures / baseline     — ไฟล์ tripwire ในแพ็กเกจครบไหม
  [6] Tripwire (ออปชัน --full)— รัน check_invariants.py (golden fixture + pin) จริง

ใช้:
    python3 doctor.py            # ตรวจเร็ว (ไม่รัน tripwire)
    python3 doctor.py --full     # + รัน invariant tripwire (golden fixture + pin)
exit 0 = พร้อมใช้ (ไม่มี blocker), 1 = มีปัญหาต้องแก้ก่อน
หมายเหตุ: เป็น read-only ล้วน (ไม่แก้ไฟล์/ไม่ต่อ network) — ปลอดภัยรันได้ทุกเมื่อ.
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

FULL = "--full" in sys.argv[1:]

OK, WARN, FAIL = "✅", "⚠️", "🚨"
_problems: list[str] = []  # blocker (ทำให้ exit 1)
_advice: list[str] = []  # คำแนะนำ (ไม่ block)


def _print_header() -> None:
    print("=" * 64)
    print("PUOPUY DOCTOR — ตรวจความพร้อมระบบ (offline, read-only)")
    print(f"  root: {HERE}")
    print(f"  mode: {'full (+tripwire)' if FULL else 'quick'}")
    print("=" * 64)


# ── [1] Python interpreter ───────────────────────────────────────────────────
def check_python() -> None:
    print("\n[1] Python interpreter")
    try:
        from config import _LOCKED as LOCKED

        want = str(LOCKED.get("python", "3.12"))
    except Exception:
        want = "3.12"
    got = f"{sys.version_info.major}.{sys.version_info.minor}"
    if got == want:
        print(f"  {OK} Python {got} ตรงเวอร์ชันล็อก ({want})")
    else:
        print(
            f"  {FAIL} Python {got} ≠ ล็อก {want} — golden hash อาจเพี้ยน (dict/float ข้ามไมเนอร์)"
        )
        _problems.append(
            f"ใช้ Python {want}: สร้าง venv → python{want} -m venv .venv "
            "&& .venv/bin/pip install -r requirements.txt -c constraints.txt"
        )


# ── [2] Dependencies (ผ่าน version_gate) ─────────────────────────────────────
def check_deps() -> None:
    print("\n[2] Dependencies (เวอร์ชันล็อก — กระทบ golden)")
    try:
        import version_gate as vg

        rep = vg.check()
    except Exception as e:
        print(f"  {FAIL} เรียก version_gate ไม่ได้: {type(e).__name__}: {e}")
        _problems.append(
            "ติดตั้ง deps: pip install -r requirements.txt -c constraints.txt"
        )
        return
    for it in rep.items:
        icon = {"ok": OK, "warn": WARN, "fail": FAIL}.get(it.status, WARN)
        got = it.got or "ไม่ได้ติดตั้ง"
        print(f"  {icon} {it.name:11} ต้องการ {it.want:8} พบ {got}")
    if rep.failures:
        _problems.append(
            "ปรับเวอร์ชัน deps ให้ตรง: pip install -r requirements.txt -c constraints.txt"
        )
    elif rep.warnings:
        _advice.append(
            "มี dependency ชั้นแสดงผล/optional ไม่ตรง (ไม่กระทบ golden) — ติดตั้งให้ครบเพื่อฟีเจอร์เต็ม"
        )


# ── [3] Environment ──────────────────────────────────────────────────────────
def check_env() -> None:
    print("\n[3] Environment variables")
    hashseed = os.environ.get("PYTHONHASHSEED", "")
    if hashseed == "0":
        print(f"  {OK} PYTHONHASHSEED=0 (reproduce golden ได้)")
    else:
        print(
            f"  {WARN} PYTHONHASHSEED='{hashseed or '(ไม่ตั้ง)'}' — golden ต้องตั้ง =0 ก่อนรัน"
        )
        _advice.append("ก่อนรัน golden/regression: export PYTHONHASHSEED=0")
    audit_date = os.environ.get("PUOPUY_AUDIT_DATE", "")
    if audit_date:
        print(
            f"  {OK} PUOPUY_AUDIT_DATE={audit_date} (โหมดทดสอบ/golden — ผลนิ่งตามเวลา)"
        )
    else:
        print(
            f"  {OK} PUOPUY_AUDIT_DATE ไม่ตั้ง → ใช้วันที่จริง (โหมด production ปกติ)"
        )


# ── [4] Git hooks ────────────────────────────────────────────────────────────
def check_hooks() -> None:
    print("\n[4] Git pre-commit hook (กัน golden พังตอน commit)")
    if not os.path.isdir(os.path.join(HERE, ".git")):
        print(f"  {WARN} ไม่ใช่ git repo ที่นี่ — ข้าม (ถ้าใช้ git ให้ติดตั้ง hook)")
        return
    hook = os.path.join(HERE, ".git", "hooks", "pre-commit")
    if os.path.isfile(hook):
        print(f"  {OK} pre-commit hook ติดตั้งแล้ว")
    else:
        print(f"  {WARN} ยังไม่ติดตั้ง pre-commit hook")
        _advice.append("ติดตั้ง hook กัน golden พัง: bash INVARIANTS/install_hooks.sh")


# ── [5] Fixtures / baseline ──────────────────────────────────────────────────
def check_fixtures() -> None:
    print("\n[5] Fixtures / baseline (in-repo — ใช้ tripwire/CI)")
    need = [
        "tests/fixtures/fixture_invoices.xlsx",
        "tests/fixtures/baseline_fixture.json",
        "tests/fixtures/canary_baseline_fixture.json",
        "baseline.json",
    ]
    missing = [p for p in need if not os.path.isfile(os.path.join(HERE, p))]
    for p in need:
        ok = os.path.isfile(os.path.join(HERE, p))
        print(f"  {OK if ok else FAIL} {p}")
    if missing:
        _problems.append(
            f"ไฟล์ fixture/baseline หาย: {missing} — แตก zip/clone ใหม่ให้ครบ"
        )


# ── [6] Tripwire (ออปชัน) ────────────────────────────────────────────────────
def check_tripwire() -> None:
    print("\n[6] Invariant tripwire (golden fixture + pin)")
    if not FULL:
        print("  • ข้าม (ใส่ --full เพื่อรันจริง ~5s)")
        return
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    env.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
    r = subprocess.run(
        [sys.executable, "INVARIANTS/check_invariants.py"],
        cwd=HERE,
        env=env,
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        print(f"  {OK} invariant ครบ (engine==agent==baseline + pin)")
    else:
        print(f"  {FAIL} invariant แตก (exit {r.returncode})")
        for ln in (r.stdout or "").strip().splitlines()[-4:]:
            print(f"       | {ln}")
        _problems.append(
            "invariant แตก — ดู INVARIANTS/check_invariants.py ; ห้าม commit จนกว่าจะแก้"
        )


def main() -> int:
    _print_header()
    check_python()
    check_deps()
    check_env()
    check_hooks()
    check_fixtures()
    check_tripwire()

    print("\n" + "=" * 64)
    if not _problems:
        print(f"RESULT: {OK} ระบบพร้อมใช้งาน — ไม่มี blocker")
        if _advice:
            print("  ข้อแนะนำ (ไม่บังคับ):")
            for a in _advice:
                print(f"    • {a}")
        print("=" * 64)
        return 0
    print(f"RESULT: {FAIL} ยังไม่พร้อม — ต้องแก้ {len(_problems)} เรื่อง:")
    for p in _problems:
        print(f"    • {p}")
    if _advice:
        print("  ข้อแนะนำเพิ่ม:")
        for a in _advice:
            print(f"    • {a}")
    print("=" * 64)
    return 1


if __name__ == "__main__":
    sys.exit(main())
