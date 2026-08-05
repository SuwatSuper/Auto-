# -*- coding: utf-8 -*-
"""version_gate.py — ด่านตรวจเวอร์ชัน (FAIL ดังๆ แทนที่จะเตือนเงียบ)

ทำไมต้องมี (P1):
  golden master baseline (hash = `baseline.json._sha256` — แหล่งความจริงเดียว) ถูกพิสูจน์บน "ชุดเวอร์ชันที่ล็อกไว้" (config._LOCKED).
  ถ้าย้ายเครื่อง/อัป Colab แล้วเวอร์ชัน "ที่มีผลต่อพฤติกรรม" เพี้ยน → ผลตรวจ/hash อาจเพี้ยน
  **โดยไม่มีใครรู้** ถ้าเราแค่พิมพ์ ⚠️ แล้วรันต่อ. โมดูลนี้เปลี่ยนเป็น "เพี้ยนระดับอันตราย = exit ≠ 0".

ปรัชญาการจัดระดับ (ไม่ทุก dependency อันตรายเท่ากัน — พิสูจน์เชิงประจักษ์):
  • REQUIRED_CRITICAL = pandas / xlrd / openpyxl / rapidfuzz
        เป็นหัวใจของการ parse/คำนวณ → mismatch ระดับ major **หรือ minor** หรือ "ไม่ได้ติดตั้ง" = FAIL
        (เพราะ minor bump ของ pandas/นับ/เรียง/รูปแบบเลข อาจขยับ golden hash ได้)
  • OPTIONAL_PINNED = pythainlp   [ADR-164 — แก้ ADR-163 ด้วยหลักฐาน]
        สองสถานะถูกต้อง (พิสูจน์เชิงประจักษ์ 2026-07-02: venv+pythainlp 5.0.5 จริง →
        fixture ad0c9dad + real f05358aa "เป๊ะเดิม"): ไม่มี (CI/sandbox) หรือ มี 5.0.5 เป๊ะ
        (เครื่องเจ้าของ — opt-in ฟีเจอร์ webverify ตาม requirements.txt; call-site เดียวอยู่นอก golden path).
        เวอร์ชันอื่น = ยังไม่พิสูจน์ → minor/patch WARN ; major/unknown FAIL.
        (ADR-163 เคยตั้ง FORBIDDEN — บล็อกเครื่อง reference ของเจ้าของเอง → ยกเลิกหลังพิสูจน์)
  • AUXILIARY = matplotlib / plotly / tqdm
        เป็นชั้นแสดงผล/UX → ไม่กระทบ golden hash → mismatch/ขาด = WARN เท่านั้น
  • python : เทียบระดับ major.minor (3.12) — ต่าง = FAIL (พฤติกรรม dict/float อาจต่างข้ามไมเนอร์)

โหมด:
  - ปกติ (strict=False): FAIL เฉพาะเคสอันตรายข้างบน
  - strict=True        : ต้องตรงเป๊ะทุกตัว (ใช้ใน release/audit pipeline ที่ต้อง reproduce 100%)
  - escape hatch       : ตั้ง env  PUOPUY_ALLOW_VERSION_MISMATCH=1  → ลด FAIL ทั้งหมดเป็น WARN
                         (สำหรับคนที่ "รู้ตัวว่ายอมรับความเสี่ยง" — จะมีคำเตือนเด่นชัด)

ใช้:
    python3 version_gate.py            # ด่าน CI: exit 1 ถ้าเพี้ยนระดับอันตราย
    python3 version_gate.py --strict   # ต้องตรงเป๊ะทุกตัว
    >>> import version_gate; version_gate.check().ok      # ใช้ในโค้ด
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# source of truth เดียว: ชุดเวอร์ชันที่ล็อกใน config (ไม่ตั้งซ้ำที่นี่ กัน drift)
from config import _LOCKED as LOCKED

# ── การจัดกลุ่มความสำคัญ (ดู docstring) ──────────────────────────────────────
REQUIRED_CRITICAL = ("pandas", "numpy", "xlrd", "openpyxl", "rapidfuzz")  # [B2-FIX] +numpy (กระทบ hash)
# [ADR-164 — แทนนโยบาย ADR-163] OPTIONAL_PINNED: สองสถานะที่ "พิสูจน์แล้ว" ว่าให้ golden เดียวกัน:
#   ไม่มี (CI/sandbox) หรือ มีที่เวอร์ชันล็อกเป๊ะ (เครื่องเจ้าของ — opt-in webverify ตาม requirements.txt).
#   พิสูจน์เชิงประจักษ์ 2026-07-02: venv + pythainlp==5.0.5 จริง → fixture ad0c9dad + real f05358aa เป๊ะเดิม.
#   เวอร์ชันอื่น = ยังไม่พิสูจน์ → minor/patch WARN ; major/unknown FAIL.
OPTIONAL_PINNED = ("pythainlp",)
AUXILIARY = ("matplotlib", "plotly", "tqdm")

_ENV_ALLOW = "PUOPUY_ALLOW_VERSION_MISMATCH"

# [P1-FIX] exit code เฉพาะของ "version gate ล้ม" — ต้อง ≠ 1 เพื่อให้ regression_full.py แยกออกจาก
#   "hash ไม่ตรง" (ซึ่งใช้ code 1). เดิม gate ใช้ exit(1) เหมือนกัน → ปัญหา env ถูกอ่านเป็น regression.
_EXIT_VERSION_FAIL = 86

# ── ระดับความต่างของเวอร์ชัน ─────────────────────────────────────────────────
LV_OK, LV_PATCH, LV_MINOR, LV_MAJOR, LV_MISSING, LV_UNKNOWN = (
    "ok", "patch", "minor", "major", "missing", "unknown")

# ── สถานะที่ด่านตัดสิน ───────────────────────────────────────────────────────
ST_OK, ST_WARN, ST_FAIL = "ok", "warn", "fail"

_ICON = {ST_OK: "✅", ST_WARN: "⚠️", ST_FAIL: "🚨"}


def parse_version(s: str) -> Tuple[int, ...]:
    """แปลง '2.2.2' / '5.0.5rc1' → (2,2,2) แบบทนทาน (ตัวเลขเท่าที่อ่านได้)."""
    if not s:
        return tuple()
    parts: List[int] = []
    for chunk in str(s).split("."):
        num = ""
        for ch in chunk:
            if ch.isdigit():
                num += ch
            else:
                break
        if num == "":
            break
        parts.append(int(num))
    return tuple(parts)


def diff_level(want: str, got: Optional[str]) -> str:
    """ระดับความต่างระหว่างเวอร์ชันที่ล็อก (want) กับที่ติดตั้งจริง (got).

    เทียบ "เท่าที่ want ระบุ" เท่านั้น: ถ้าล็อกไว้ '3.12' (ไม่มี patch) แล้วติดตั้ง '3.12.3'
    ถือว่า OK (patch ไม่ถูกบังคับ). ถ้าล็อก '2.2.2' (ครบ 3 ชั้น) ติดตั้ง '2.2.5' = patch ต่าง.
    """
    if got is None:
        return LV_MISSING
    w, g = parse_version(want), parse_version(got)
    if not w or not g:
        return LV_UNKNOWN if w != g else LV_OK
    k = len(w)                              # ความละเอียดที่ล็อกระบุ
    g = (g + (0,) * k)[:k]                   # ตัด got ให้เท่าความละเอียดของ want
    if w[0] != g[0]:
        return LV_MAJOR
    if k >= 2 and w[1] != g[1]:
        return LV_MINOR
    if k >= 3 and w[2] != g[2]:
        return LV_PATCH
    return LV_OK


def _installed_version(name: str) -> Optional[str]:
    """หาเวอร์ชันที่ติดตั้งจริง (None = ไม่ได้ติดตั้ง). ใช้ importlib.metadata ก่อน แล้ว __version__."""
    if name == "python":
        return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    try:
        from importlib import metadata as _md
        try:
            return _md.version(name)
        except _md.PackageNotFoundError:
            pass
    except Exception:
        pass
    # fallback: import แล้วอ่าน __version__ (เผื่อชื่อ dist ≠ ชื่อ module)
    try:
        mod = __import__(name)
        return getattr(mod, "__version__", None)
    except Exception:
        return None


def _policy(name: str, level: str, strict: bool) -> str:
    """แปลง (กลุ่ม dependency, ระดับความต่าง) → สถานะ FAIL/WARN/OK ตามนโยบาย."""
    if name in OPTIONAL_PINNED:
        # [ADR-164] สองสถานะถูกต้อง (พิสูจน์แล้ว golden เป๊ะเดิมทั้งคู่): ไม่มี หรือ มีที่ล็อกเป๊ะ.
        #   เวอร์ชันอื่น = ยังไม่พิสูจน์กับ golden → minor/patch WARN ; major/unknown FAIL (ADR-138 spirit).
        if level in (LV_MISSING, LV_OK):
            return ST_OK
        return ST_FAIL if level in (LV_MAJOR, LV_UNKNOWN) else ST_WARN
    if level == LV_OK:
        return ST_OK
    if strict:
        # โหมดเข้ม: อะไรที่ไม่ตรงเป๊ะ = FAIL ทั้งหมด
        return ST_FAIL

    # [ADR-138] LV_UNKNOWN = เวอร์ชันที่ติดตั้ง "แปลงเลขไม่ได้" (เช่น 'dev'/'main' จาก editable/git install)
    #   → เทียบ golden-critical ไม่ได้ = ต้อง FAIL (ไม่ใช่ WARN false-green). env ปกติ (เลขสะอาด) → LV_OK
    #   → ไม่กระทบ. กันรู "ผ่านทั้งที่ยืนยันเวอร์ชันหัวใจไม่ได้".
    if name == "python":
        # ต่างที่ major หรือ minor = อันตราย ; patch = เตือน
        return ST_FAIL if level in (LV_MAJOR, LV_MINOR, LV_MISSING, LV_UNKNOWN) else ST_WARN

    if name in REQUIRED_CRITICAL:
        # หัวใจ parse/คำนวณ: ขาด/major/minor/แปลงไม่ได้ = FAIL ; patch = WARN
        return ST_FAIL if level in (LV_MISSING, LV_MAJOR, LV_MINOR, LV_UNKNOWN) else ST_WARN

    # AUXILIARY และอื่นๆ: แสดงผลล้วน → WARN เท่านั้น
    return ST_WARN


@dataclass
class Item:
    name: str
    want: str
    got: Optional[str]
    level: str
    status: str
    group: str


@dataclass
class Report:
    items: List[Item] = field(default_factory=list)
    strict: bool = False
    allow_mismatch: bool = False

    @property
    def failures(self) -> List[Item]:
        return [i for i in self.items if i.status == ST_FAIL]

    @property
    def warnings(self) -> List[Item]:
        return [i for i in self.items if i.status == ST_WARN]

    @property
    def ok(self) -> bool:
        """ผ่านด่านหรือไม่. ถ้าเปิด escape hatch → FAIL ถูกผ่อนเป็นไม่บล็อก (แต่ยังนับใน failures)."""
        if self.allow_mismatch:
            return True
        return not self.failures


def _group_of(name: str) -> str:
    if name == "python":
        return "python"
    if name in REQUIRED_CRITICAL:
        return "required"
    if name in OPTIONAL_PINNED:
        return "optional_pinned"
    if name in AUXILIARY:
        return "auxiliary"
    return "other"


def check(locked: Optional[Dict[str, str]] = None, strict: bool = False) -> Report:
    """ตรวจทุก dependency ที่ล็อกไว้ คืน Report (ตามรอยได้ทุกตัว)."""
    locked = dict(locked or LOCKED)
    allow = os.environ.get(_ENV_ALLOW, "") == "1"
    rep = Report(strict=strict, allow_mismatch=allow)
    # เรียงให้ python ก่อน แล้วตามลำดับล็อก (deterministic)
    names = (["python"] if "python" in locked else []) + \
            [n for n in locked if n != "python"]
    for name in names:
        want = locked[name]
        got = _installed_version(name)
        level = diff_level(want, got)
        status = _policy(name, level, strict)
        rep.items.append(Item(name=name, want=want, got=got, level=level,
                              status=status, group=_group_of(name)))
    return rep


def format_report(rep: Report) -> str:
    """สร้างตารางรายงาน (คง UX ✅/⚠️/🚨 เดิม + บอกระดับความต่าง)."""
    lines = ["=" * 60, "  🔒 VERSION GATE — ตรวจเวอร์ชันเทียบที่ล็อก (golden baseline)"]
    if rep.strict:
        lines.append("  โหมด: STRICT (ต้องตรงเป๊ะทุกตัว)")
    lines.append("=" * 60)
    for it in rep.items:
        got = it.got if it.got is not None else "ไม่ได้ติดตั้ง"
        if it.group == "optional_pinned" and it.got is None:  # [ADR-164] ไม่มี = สถานะถูกต้อง ไม่ใช่ deficiency
            lines.append(f"  {_ICON[it.status]} {it.name:11}: {got:14} (optional — พิสูจน์แล้วเท่ากับมี {it.want})")
            continue
        tag = "" if it.level == LV_OK else f"  [{it.level}]"
        lines.append(f"  {_ICON[it.status]} {it.name:11}: {got:14} (ล็อก {it.want}){tag}")
    lines.append("=" * 60)
    if rep.failures:
        lines.append("  🚨 พบความต่างระดับอันตราย (อาจทำ golden hash เพี้ยน):")
        for it in rep.failures:
            if it.group == "optional_pinned":  # [ADR-164] เวอร์ชันนอกที่พิสูจน์
                lines.append(f"     • {it.name}: {it.got} ≠ {it.want} ({it.level}) — เวอร์ชันนี้ยังไม่พิสูจน์กับ golden:"
                             f" ใช้ {it.want} เป๊ะ หรือถอนออก (สองสถานะที่พิสูจน์แล้ว)")
                continue
            lines.append(f"     • {it.name}: {it.got} ≠ {it.want} ({it.level})")
        if rep.allow_mismatch:
            lines.append(f"  ⚠️  ผ่อนผันด้วย {_ENV_ALLOW}=1 — รันต่อทั้งที่เสี่ยง (คุณรับความเสี่ยงเอง)")
            # [OBS 2026-06-20] กัน golden drift ซ่อนใต้ version warning (บทเรียนจากบั๊ก C1: name_raw ขยับ
            #   golden แต่ถูกเข้าใจว่า "แค่ version ต่าง"). เตือนชัดว่า golden ยัง "ไม่ได้ยืนยัน" จนกว่าจะรัน regression.
            lines.append("  ⛔ golden ยัง 'ไม่ได้ยืนยัน' ในเวอร์ชันนี้ — ต้องรัน  python3 regression_full.py <data> "
                         "เทียบ baseline._sha256 ก่อนเชื่อผล (version warning ≠ golden ผ่าน)")
        else:
            lines.append("  → หยุดการทำงาน. ติดตั้งให้ตรง:  pip install -r requirements.txt")
            lines.append(f"     (ถ้ายืนยันจะรันทั้งที่เสี่ยง: ตั้ง {_ENV_ALLOW}=1)")
    elif rep.warnings:
        lines.append("  ⚠️ มีความต่างระดับไม่อันตราย (ไม่กระทบ golden hash เท่าที่พิสูจน์บน corpus ปัจจุบัน) — รันต่อได้:")
        for it in rep.warnings:
            got = it.got if it.got is not None else "ไม่ได้ติดตั้ง"
            lines.append(f"     • {it.name}: {got} vs {it.want} ({it.level})")
    else:
        lines.append("  ✅ เวอร์ชันตรงล็อกทุกตัว — ปลอดภัย")
    lines.append("=" * 60)
    return "\n".join(lines)


def enforce(strict: bool = False, exit_on_fail: bool = True, stream=None) -> bool:
    """ตรวจ + พิมพ์รายงาน + (ถ้าตั้ง) exit ≠ 0 เมื่อพบความต่างระดับอันตราย.

    คืน True ถ้าผ่านด่าน. ออกแบบให้ import-safe: เรียกตอน import โมดูลหลักได้
    เพราะนโยบายปกติจะ FAIL เฉพาะเคสที่ "ควรหยุดจริง" (ไม่ false-positive ใน env ที่ reproduce ได้).
    """
    stream = stream or sys.stdout
    rep = check(strict=strict)
    report_txt = format_report(rep)
    def _safe_out(txt, s):
        # [ADR-171/BUGHUNT F-A] banner นี้พิมพ์ "ตอน import" โมดูลหลัก — บนคอนโซลที่ไม่ใช่ utf-8
        #   (Windows redirect/pipe = cp874/cp1252 ไม่มี emoji) เดิม UnicodeEncodeError ฆ่าทั้ง run
        #   ก่อน parse ไฟล์ใด ๆ. ลดรูปด้วย replace แทน (สาระ banner อ่านได้ครบ) — print-only ไม่แตะ hash.
        try:
            print(txt, file=s)
        except UnicodeEncodeError:
            _enc = getattr(s, 'encoding', None) or 'ascii'
            print(txt.encode(_enc, 'replace').decode(_enc, 'replace'), file=s)
    _safe_out(report_txt, stream)
    if rep.failures and exit_on_fail and not rep.allow_mismatch:
        # [P1-FIX ดับเงียบ] เครื่องมือ golden/verify import โมดูลหลักภายใต้ redirect_stdout →
        #   เดิมรายงานนี้ถูกกลืนหมด เหลือแค่ exit(1) เปล่า ๆ ที่ regression_full อ่านเป็น "hash ไม่ตรง".
        #   แก้: เขียนเหตุผลไป stderr ด้วยเสมอ (ไม่ถูก redirect) + exit ด้วยโค้ดเฉพาะ (แยกจาก hash mismatch).
        if stream is not sys.stderr:
            _safe_out(report_txt, sys.stderr)
            _safe_out("🚨 VERSION GATE FAILED — หยุดก่อนคำนวณ hash "
                      "(ปัญหาสภาพแวดล้อม/เวอร์ชัน ไม่ใช่ regression). "
                      f"ผ่อนผันด้วย {_ENV_ALLOW}=1 ถ้ายืนยันจะรันทั้งที่เสี่ยง.", sys.stderr)
        sys.exit(_EXIT_VERSION_FAIL)
    return rep.ok


if __name__ == "__main__":
    _strict = "--strict" in sys.argv[1:]
    ok = enforce(strict=_strict, exit_on_fail=True)
    sys.exit(0 if ok else 1)
