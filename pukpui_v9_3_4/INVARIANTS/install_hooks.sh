#!/usr/bin/env bash
# install_hooks.sh — ติดตั้ง git hooks จาก hooks/ ไป .git/hooks/ (ครั้งเดียวต่อ clone)
#
# ทำไมต้องติดตั้ง: git ไม่ version-control .git/hooks/ — ไฟล์ใน hooks/ จึงเป็น "ต้นฉบับ"
#   ที่ commit ตามไปกับ repo ได้ แล้วสคริปต์นี้ก๊อปไปยังตำแหน่งที่ git เรียกใช้จริง.
#
# ใช้:  bash INVARIANTS/install_hooks.sh
# ทางเลือก (git ≥ 2.9): git config core.hooksPath hooks   # ชี้ git ไปอ่าน hooks/ ตรง ๆ

set -u
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
[ -z "$ROOT" ] && ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 2

SRC="hooks/pre-commit"
DST=".git/hooks/pre-commit"

if [ ! -f "$SRC" ]; then
  echo "❌ ไม่พบ $SRC"; exit 1
fi
if [ ! -d ".git/hooks" ]; then
  echo "❌ ไม่พบ .git/hooks — รันในโฟลเดอร์ที่เป็น git repo"; exit 1
fi

cp "$SRC" "$DST"
chmod +x "$DST" 2>/dev/null || true
echo "✅ ติดตั้ง pre-commit hook แล้ว: $DST"
echo "   ทดสอบ:  PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 INVARIANTS/check_invariants.py"
echo "   ทางเลือก (แทน cp):  git config core.hooksPath hooks"
