#!/usr/bin/env bash
# verify_round.sh — golden-neutral loop driver for pukpui v9.3.4 fix rounds.
# Proves: (1) real_cases digest unchanged, (2) fixture hash unchanged, (3) standalone tests pass.
set -u
PKG="/home/user/Auto-/_review_extract/pukpui_v9_3_4"
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_ALLOW_VERSION_MISMATCH=1
cd "$PKG" || exit 2

WANT_REAL="95852c68d66225d9fdbdd1678b703978ea63708ec1dd7c9e24d596b1000a84b4"
WANT_FIX="b5c415bbd7bf58bac4328fec1c868325e0955f423d01e9695ba50015fc2f02eb"

echo "──────────────────────────────────────────────"
echo "[A] real_cases digest (golden-neutral sentinel)"
GOT_REAL=$(python3 golden_master.py . /tmp/snap_round.json tests/real_cases 2>/dev/null)
if [ "$GOT_REAL" = "$WANT_REAL" ]; then echo "  ✅ real_cases digest UNCHANGED ($GOT_REAL)"; else echo "  ❌ real_cases digest DRIFTED: $GOT_REAL (want $WANT_REAL)"; fi

echo "[B] fixture regression (engine==agent==baseline)"
FIXOUT=$(python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json 2>/dev/null | grep -E "engine_hash|RESULT")
echo "$FIXOUT" | sed 's/^/  /'
echo "$FIXOUT" | grep -q "$WANT_FIX" && echo "  ✅ fixture hash matches" || echo "  ❌ fixture hash drift"

echo "[C] standalone test suite"
pass=0; fail=0; failed_list=""
for t in $(ls test_*.py | sort); do
  if python3 "$t" >/tmp/t.out 2>&1; then pass=$((pass+1)); else fail=$((fail+1)); failed_list="$failed_list $t"; fi
done
echo "  PASS=$pass FAIL=$fail"
[ -n "$failed_list" ] && echo "  FAILED:$failed_list"
echo "──────────────────────────────────────────────"
