# -*- coding: utf-8 -*-
"""qa_toolchain_gate.py — [ADR-194] ตรวจว่า "เครื่องมือเกต" ตรง pin ใน requirements-dev.txt

ปัญหาที่ปิด (ตระกูลเดียวกับ ADR-188):
    run_ci.sh เช็คแค่ว่า "มีเครื่องมือไหม" (`$PY -m ruff --version`) ไม่เคยเช็คว่า "เวอร์ชันตรง pin ไหม"
    → ติดตั้งด้วย `pip install ruff black mypy` (ไม่ใส่เวอร์ชัน) ได้ตัวใหม่กว่า pin
    → เกตเปลี่ยนความหมายเงียบ ๆ ทั้งที่โค้ดไม่ขยับ:
      · ruff 0.16.1 เปิดชุดกฎ default ~413 กฎ (pin 0.15.19 เปิดแค่ E,F) → เกต [11] แดง 73 ข้อ
      · coverage เวอร์ชันต่าง → เปอร์เซ็นต์ branch ขยับ (ADR-088 บันทึกไว้: 85.3% ↔ 84.5%)
    ผลคือคนไล่บั๊กเสียเวลากับ "บั๊กของเครื่องมือ" แทนบั๊กของระบบ.

สัญญาของเกตนี้:
    · ไม่ได้ติดตั้ง        → ⏭️  ข้าม (คงพฤติกรรม graceful เดิมของ run_ci.sh)
    · ติดตั้งแล้ว/ตรง pin  → ✅
    · ติดตั้งแล้ว/ผิด pin  → ❌ FAIL พร้อมบอกคำสั่งแก้ (เกตต้องแปลว่าเดิมทุกเครื่อง)

exit 0 = ผ่าน/ข้าม · 1 = มีเครื่องมือที่เวอร์ชันไม่ตรง pin
รันได้ทุกที่ (stdlib ล้วน — ไม่ต้องมี corpus/ไลบรารีนอก)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REQ_DEV = os.path.join(HERE, "requirements-dev.txt")

# ชื่อโมดูลสำหรับเรียก `-m <mod> --version` (ต่างจากชื่อแพ็กเกจในบางตัว)
_MODULE = {"pip-audit": "pip_audit"}

_fail = []
_skip = []
_ok = []


def _pins():
    """อ่าน pin จาก requirements-dev.txt → {package: version}"""
    out = {}
    if not os.path.exists(REQ_DEV):
        return out
    with open(REQ_DEV, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            m = re.match(r"^([A-Za-z0-9._-]+)==([A-Za-z0-9._-]+)$", line)
            if m:
                out[m.group(1)] = m.group(2)
    return out


def _installed(pkg):
    """เวอร์ชันที่ติดตั้งจริง — None ถ้าไม่มี"""
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            return version(pkg)
        except PackageNotFoundError:
            pass
    except Exception:
        pass
    # fallback: ถาม CLI ของเครื่องมือเอง
    mod = _MODULE.get(pkg, pkg)
    try:
        r = subprocess.run([sys.executable, "-m", mod, "--version"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            m = re.search(r"(\d+\.\d+(?:\.\d+)?)", (r.stdout or "") + (r.stderr or ""))
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


print("=" * 68)
print("QA TOOLCHAIN GATE — เครื่องมือเกตต้องตรง pin (requirements-dev.txt)")
print("=" * 68)

pins = _pins()
if not pins:
    print("  ⏭️  ไม่พบ requirements-dev.txt หรือไม่มี pin → ข้าม")
    sys.exit(0)

for pkg in sorted(pins):
    want = pins[pkg]
    got = _installed(pkg)
    if got is None:
        print(f"  ⏭️  {pkg:12s} ไม่ได้ติดตั้ง (pin {want}) — เกตที่ใช้ตัวนี้จะถูกข้ามใน run_ci.sh")
        _skip.append(pkg)
    elif got == want:
        print(f"  ✅ {pkg:12s} {got:10s} (ตรง pin)")
        _ok.append(pkg)
    else:
        print(f"  ❌ {pkg:12s} {got:10s} ≠ pin {want}")
        _fail.append((pkg, got, want))

print("-" * 68)
print(f"ตรง pin {len(_ok)} · ไม่ได้ติดตั้ง {len(_skip)} · ผิด pin {len(_fail)}")

if _fail:
    print("\n❌ เครื่องมือเกตเวอร์ชันไม่ตรง pin — ผลเกตจะไม่ใช่ผลของ 'โค้ด' อีกต่อไป")
    print("   (เคสจริง: ruff 0.16.1 แทน 0.15.19 → เกต [11] แดง 73 ข้อ ทั้งที่โค้ดไม่เปลี่ยน)")
    print("\n   แก้:  pip install -r requirements-dev.txt --break-system-packages")
    print("   หรือ: pip install " + " ".join(f"{p}=={w}" for p, _g, w in _fail))
    print("\n   ถ้าตั้งใจอัปเวอร์ชัน: แก้ requirements-dev.txt แล้วรันเกตทั้งชุดใหม่")
    print("   เพื่อยืนยันว่าเกตยังแปลเหมือนเดิม (ห้าม bump เงียบ)")
    print("=" * 68)
    sys.exit(1)

print("✅ เครื่องมือเกตทุกตัวที่ติดตั้งไว้ตรง pin — ผลเกตเทียบข้ามเครื่องได้")
print("=" * 68)
sys.exit(0)
