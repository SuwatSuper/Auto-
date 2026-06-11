#!/usr/bin/env bash
# package.sh — แพ็ก deliverable zip แบบ "reproducible + ชื่อไฟล์ไทยไม่พัง"
#
# ทำไมต้องมี (บทเรียนจริง): `git archive --format=zip` *ไม่ตั้ง* UTF-8 language-encoding flag
#   (general-purpose bit 0x800) บน entry → `unzip` (Info-ZIP) เดา encoding ผิด → ชื่อไฟล์ภาษาไทย
#   เพี้ยน → โมดูลหลัก "ปุ้มปุ้ย_ultimate_v9_modular.py" หาย → ระบบ import ไม่ได้ (แพ็กพังเงียบ).
#   สคริปต์นี้แพ็กผ่าน Python zipfile ที่ตั้ง flag 0x800 ให้ชื่อ non-ASCII อัตโนมัติ + self-verify.
#
# ใช้:
#   bash package.sh                 # → dist/pukpui_v9_2_hardened.zip
#   bash package.sh /path/out.zip   # ระบุปลายทางเอง
#
# แพ็ก "เฉพาะไฟล์ที่ git track" (กรอง .git/cache/master_companies.json/.env อัตโนมัติตาม .gitignore).
set -u
cd "$(dirname "$0")" || exit 2

PREFIX="pukpui_v9_2_hardened"
OUT="${1:-dist/${PREFIX}.zip}"
mkdir -p "$(dirname "$OUT")" 2>/dev/null || true

PY="${PYTHON:-python3}"
"$PY" - "$OUT" "$PREFIX" <<'PYEOF'
import sys, os, subprocess, zipfile

out, prefix = sys.argv[1], sys.argv[2]

# รายการไฟล์ที่ git track (UTF-8 จริง, NUL-separated, เรียงให้ลำดับคงที่ = reproducible)
raw = subprocess.run(["git", "-c", "core.quotepath=false", "ls-files", "-z"],
                     capture_output=True, check=True).stdout
files = sorted(f for f in raw.decode("utf-8").split("\0") if f)
if not files:
    sys.exit("❌ git ls-files ว่าง — รันในโฟลเดอร์ repo ที่ commit แล้ว")

tmp = out + ".tmp"
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        # Python zipfile ตั้ง flag 0x800 (UTF-8) ให้ชื่อที่มี non-ASCII โดยอัตโนมัติ
        z.write(f, f"{prefix}/{f}")

# ── self-verify: ถ้าพังให้ตายตรงนี้ (ไม่ปล่อยแพ็กเสียออกไป) ──────────────────
MAIN = f"{prefix}/ปุ้มปุ้ย_ultimate_v9_modular.py"
JUNK = ("/.git/", "__pycache__", "/master_companies.json")
with zipfile.ZipFile(tmp) as z:
    names = set(z.namelist())
    if MAIN not in names:
        os.remove(tmp); sys.exit(f"❌ โมดูลหลักหายจากแพ็ก: {MAIN}")
    no_flag = [i.filename for i in z.infolist()
               if any(ord(c) > 127 for c in i.filename) and not (i.flag_bits & 0x800)]
    if no_flag:
        os.remove(tmp); sys.exit(f"❌ UTF-8 flag หายบน {len(no_flag)} entry (unzip จะแตกชื่อเพี้ยน): {no_flag[:3]}")
    junk = [n for n in names if any(j in n for j in JUNK) or n.endswith((".pyc", ".env"))]
    if junk:
        os.remove(tmp); sys.exit(f"❌ มีไฟล์ที่ไม่ควรแพ็ก (cache/secret): {junk[:5]}")

os.replace(tmp, out)
n_thai = sum(1 for f in files if any(ord(c) > 127 for c in f))
print(f"✅ packaged {len(files)} ไฟล์ → {out}")
print(f"   UTF-8 flag: OK ({n_thai} ไฟล์ไทย) · โมดูลหลัก: OK · ไม่มี cache/secret")
PYEOF
