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


# ── [7] Corpus drift (data ↔ golden) [ADR-159] ───────────────────────────────
def check_corpus_drift() -> None:
    print("\n[7] Corpus drift (data ↔ golden)")
    import json, hashlib, glob
    man_p = os.path.join(HERE, "corpus_manifest.json")
    data_dir = "/mnt/project"
    if not os.path.isfile(man_p):
        print(f"  {WARN} ไม่พบ corpus_manifest.json (สร้าง: verify_corpus_manifest.py <data> --write)")
        return
    try:
        man = json.load(open(man_p, encoding="utf-8"))
    except Exception as e:
        print(f"  {WARN} อ่าน corpus_manifest.json ไม่ได้: {e}")
        return
    exp = man.get("files", {})
    gold = (man.get("golden_real_corpus") or "")[:8]
    if not os.path.isdir(data_dir):
        print(f"  {OK} ไม่มี corpus บนเครื่องนี้ ({data_dir}) — golden ข้อมูลจริงตรวจที่นี่ไม่ได้ (ใช้ fixture ad0c9dad แทน)")
        return
    cur = {}
    try:
        for fp in sorted(glob.glob(os.path.join(data_dir, "*.xls")) +
                         glob.glob(os.path.join(data_dir, "*.xlsx"))):
            with open(fp, "rb") as f:
                cur[os.path.basename(fp)] = hashlib.sha256(f.read()).hexdigest()
    except Exception as e:
        print(f"  {WARN} อ่าน corpus ไม่ครบ: {e}")
        return
    added = sorted(set(cur) - set(exp))
    removed = sorted(set(exp) - set(cur))
    changed = sorted(k for k in (set(exp) & set(cur)) if exp[k] != cur[k])
    if not (added or removed or changed):
        print(f"  {OK} corpus ตรง manifest ({len(exp)} ไฟล์) → golden {gold}… ต้อง reproduce (ถ้าไม่ = CODE DRIFT)")
    else:
        print(f"  {WARN} corpus DRIFT: +{len(added)} −{len(removed)} ~{len(changed)} ไฟล์ "
              f"→ golden ข้อมูลจริงจะเปลี่ยน (rebaseline ปกติ ไม่ใช่บั๊ก)")
        _advice.append(f"corpus drift ({len(added)+len(removed)+len(changed)} ไฟล์) — รัน "
                       f"`verify_corpus_manifest.py {data_dir}` ดูรายละเอียด + rebaseline ถ้าตั้งใจเปลี่ยน")


# ── [8] Master (ตัวตนบริษัท ภ.พ.20) [ADR-159 · ADR-165: แยก 3 สถานะ] ─────────
def check_master() -> None:
    print("\n[8] Master (ตัวตนบริษัท ภ.พ.20)")
    import json
    mp = os.path.join(HERE, "master_companies.json")
    if not os.path.isfile(mp):
        print(f"  {WARN} ยังไม่มีไฟล์ master — ~24 กฎตัวตน 'หลับ' อยู่ (ระบบทำงาน ~60%)")
        _advice.append("เติม master_companies.json จาก ภ.พ.20 (รัน เพิ่ม_master.py) → ปลดล็อก ~24 กฎตัวตน")
        return
    try:
        data = json.load(open(mp, encoding="utf-8"))
    except Exception as e:
        print(f"  {FAIL} ไฟล์ master 'มีอยู่แต่อ่านพัง' ({type(e).__name__}) — อันตรายกว่าว่าง: "
              f"เข้าใจว่ากฎตัวตนทำงานทั้งที่หลับ")
        _problems.append("แก้ master_companies.json (JSON พัง) หรือรัน เพิ่ม_master.py สร้างใหม่")
        return
    if not isinstance(data, dict):
        print(f"  {FAIL} master ต้องเป็น JSON object แต่เป็น {type(data).__name__} — กฎตัวตนไม่ทำงาน")
        _problems.append("master_companies.json ชนิดผิด — รัน เพิ่ม_master.py สร้างใหม่")
        return
    data.pop("_golden_stub", None)
    n = len(data)
    if n == 0:
        print(f"  {WARN} master ว่าง — ~24 กฎตัวตน (ชื่อ/เลขภาษี/สาขา/ทะเบียน) 'หลับ' อยู่ (ระบบทำงาน ~60%)")
        _advice.append("เติม master_companies.json จาก ภ.พ.20 (4 ฟิลด์: ชื่อ/tax_id/สาขา/ที่อยู่) → ปลดล็อก ~24 กฎตัวตน")
    else:
        bad = sum(1 for v in data.values() if not isinstance(v, dict))
        extra = f" (⚠ {bad} รายการรูปแบบไม่ถูก)" if bad else ""
        print(f"  {OK} master มี {n} บริษัท → กฎตัวตนทำงาน{extra}")
        if bad:
            _advice.append(f"master มี {bad} รายการ value ไม่ใช่ object — แก้ด้วย เพิ่ม_master.py")


# ── [9] PII / การแชร์แพ็ก [ADR-159] ──────────────────────────────────────────
def check_pii() -> None:
    print("\n[9] PII / การแชร์แพ็ก")
    real = os.path.isdir(os.path.join(HERE, "tests", "real_cases"))
    bl = os.path.isfile(os.path.join(HERE, "baseline.json"))
    if real or bl:
        print(f"  {WARN} แพ็กมีข้อมูลจริง (baseline.json / tests/real_cases → tax_id/ที่อยู่)")
        _advice.append("อย่าแชร์ zip ให้คนนอก — ถ้าต้องแจกจ่าย ทำแพ็กปลอด PII: "
                       "`python3 sanitize_for_sharing.py <zip>` (ดู PRIVACY_NOTICE.md)")
    else:
        print(f"  {OK} ไม่มีไฟล์ข้อมูลจริง (นี่คือแพ็ก shareable)")


def main() -> int:
    _print_header()
    check_python()
    check_deps()
    check_env()
    check_hooks()
    check_fixtures()
    check_tripwire()
    check_corpus_drift()
    check_master()
    check_pii()

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
