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
  • OPTIONAL_CRITICAL = pythainlp
        มีผลต่อ text/typo แต่ degrade ได้ (โค้ดกันไว้) → major mismatch = FAIL, อื่นๆ = WARN
        (เชิงประจักษ์: ขาด pythainlp แล้ว hash ยังตรง baseline "เท่าที่พิสูจน์บน corpus ปัจจุบัน" → ไม่ FAIL โดยไม่จำเป็น;
         การรับประกันนี้ขึ้นกับว่าข้อมูลเรียก path ที่พึ่ง Thai-NLP หรือไม่ — gate ไม่ได้ verify เอง)
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
REQUIRED_CRITICAL = ("pandas", "xlrd", "openpyxl", "rapidfuzz")
OPTIONAL_CRITICAL = ("pythainlp",)
AUXILIARY = ("matplotlib", "plotly", "tqdm")

_ENV_ALLOW = "PUOPUY_ALLOW_VERSION_MISMATCH"

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
    if level == LV_OK:
        return ST_OK
    if strict:
        # โหมดเข้ม: อะไรที่ไม่ตรงเป๊ะ = FAIL ทั้งหมด
        return ST_FAIL

    if name == "python":
        # ต่างที่ major หรือ minor = อันตราย ; patch = เตือน
        return ST_FAIL if level in (LV_MAJOR, LV_MINOR, LV_MISSING) else ST_WARN

    if name in REQUIRED_CRITICAL:
        # หัวใจ parse/คำนวณ: ขาด/major/minor = FAIL ; patch = WARN
        return ST_FAIL if level in (LV_MISSING, LV_MAJOR, LV_MINOR) else ST_WARN

    if name in OPTIONAL_CRITICAL:
        # degrade ได้: เฉพาะ major = FAIL ; ขาด/minor/patch = WARN
        return ST_FAIL if level == LV_MAJOR else ST_WARN

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
    if name in OPTIONAL_CRITICAL:
        return "optional"
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
        tag = "" if it.level == LV_OK else f"  [{it.level}]"
        lines.append(f"  {_ICON[it.status]} {it.name:11}: {got:14} (ล็อก {it.want}){tag}")
    lines.append("=" * 60)
    if rep.failures:
        lines.append("  🚨 พบความต่างระดับอันตราย (อาจทำ golden hash เพี้ยน):")
        for it in rep.failures:
            lines.append(f"     • {it.name}: {it.got} ≠ {it.want} ({it.level})")
        if rep.allow_mismatch:
            lines.append(f"  ⚠️  ผ่อนผันด้วย {_ENV_ALLOW}=1 — รันต่อทั้งที่เสี่ยง (คุณรับความเสี่ยงเอง)")
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
    print(format_report(rep), file=stream)
    if rep.failures and exit_on_fail and not rep.allow_mismatch:
        sys.exit(1)
    return rep.ok


if __name__ == "__main__":
    _strict = "--strict" in sys.argv[1:]
    ok = enforce(strict=_strict, exit_on_fail=True)
    sys.exit(0 if ok else 1)
