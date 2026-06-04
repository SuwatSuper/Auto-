# -*- coding: utf-8 -*-
"""check_invariants.py — ตรวจ "invariant ที่ห้ามแตก" แบบเร็ว ไม่ต้องมีข้อมูลจริง

บังคับ DECISIONS.md ข้อ §1 (golden) + §6 (pin) อัตโนมัติ:
  1) GOLDEN FIXTURE — engine == agent == baseline_fixture (regression_full.py บน fixture)
  2) PIN LOGIC      — test_pinned_logic.py  (จุด APPROX ตรึงค่าเดิม)
  3) PIN LENSES     — test_verification_lens_pin.py (คลังเลนส์ 22 + advisory)

ทั้งหมดรันใน-repo ล้วน (~4–5 วินาที) จึงเหมาะเป็น pre-commit hook + ขั้น CI.
ของหนัก (golden 81 ไฟล์จริง) ไม่อยู่ที่นี่ — รันผ่าน regression_full.py บนข้อมูลจริงแยก.

วิธีใช้:
    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 INVARIANTS/check_invariants.py
    python3 INVARIANTS/check_invariants.py --fast    # golden fixture อย่างเดียว (เร็วสุด)
exit 0 = invariant ครบ, 1 = มี invariant แตก (commit ควรถูกบล็อก), 2 = รันเครื่องมือไม่ได้
"""
import os
import sys
import subprocess

# repo root = พาเรนต์ของโฟลเดอร์ INVARIANTS/ (ทำงานถูกไม่ว่าเรียกจากที่ไหน)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ตั้ง env deterministic เสมอ (DECISIONS.md §0) — ไม่พึ่งผู้เรียกตั้งให้
ENV = dict(os.environ)
ENV.setdefault("PYTHONHASHSEED", "0")
ENV.setdefault("PUOPUY_AUDIT_DATE", "2026-06-02")
PY = sys.executable

FAST = "--fast" in sys.argv[1:]

# (label, argv) — ทุกขั้นถือว่า "ผ่าน" เมื่อ exit code == 0
STEPS = [
    (
        "GOLDEN FIXTURE (engine==agent==baseline)",
        ["regression_full.py", ".", "tests/fixtures", "tests/fixtures/baseline_fixture.json"],
    ),
]
if not FAST:
    STEPS += [
        ("PIN LOGIC (APPROX จุดตรึง)", ["test_pinned_logic.py"]),
        ("PIN LENSES (คลังเลนส์ 22 + advisory)", ["test_verification_lens_pin.py"]),
        ("PIN VAT002 tolerance 0.50 (ADR-005)", ["test_vat002_tolerance.py"]),
    ]


def _run(argv):
    path = os.path.join(ROOT, argv[0])
    if not os.path.isfile(path):
        return None, f"ไม่พบเครื่องมือ {argv[0]}"
    r = subprocess.run(
        [PY, path, *argv[1:]],
        cwd=ROOT,
        env=ENV,
        capture_output=True,
        text=True,
    )
    return r, None


def main() -> int:
    print("=" * 64)
    print("CHECK INVARIANTS — golden fixture + pin (DECISIONS.md §1, §6)")
    print(f"  root: {ROOT}")
    print(f"  mode: {'fast (fixture only)' if FAST else 'full (fixture + pins)'}")
    print("=" * 64)

    failed = []
    tool_error = False
    for label, argv in STEPS:
        r, err = _run(argv)
        if err is not None:
            print(f"  ⚠️  {label}: {err}")
            tool_error = True
            failed.append(label)
            continue
        if r.returncode == 0:
            print(f"  ✅ {label}")
        else:
            print(f"  ❌ {label}  (exit {r.returncode})")
            # โชว์ท้าย output ช่วย debug โดยไม่ท่วมจอ
            tail = (r.stdout or "").strip().splitlines()[-3:]
            for ln in tail:
                print(f"       | {ln}")
            failed.append(label)

    print("=" * 64)
    if not failed:
        print("RESULT: ✅ invariant ครบ — ปลอดภัยที่จะ commit")
        return 0
    print("RESULT: ❌ invariant แตก:")
    for f in failed:
        print(f"        • {f}")
    print("  → ห้าม commit จนกว่าจะแก้ ; ฉุกเฉินจริงข้าม hook ได้ด้วย  PUOPUY_SKIP_HOOK=1")
    return 2 if tool_error else 1


if __name__ == "__main__":
    sys.exit(main())
