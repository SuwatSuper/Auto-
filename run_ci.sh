#!/usr/bin/env bash
# run_ci.sh — รันด่าน CI ทั้งหมดในเครื่อง (ลำดับเดียวกับ .github/workflows/ci.yml)
#
# ใช้:
#   bash run_ci.sh                 # gate+smoke+pinned+mesh+agents+regression(fixture)
#   bash run_ci.sh /path/to/data   # + regression เต็มบนข้อมูลจริง (baseline ec61907f…) ถ้าระบุ data dir
#
# ต้องรันจากโฟลเดอร์ระบบ (ที่มี config.py). ทุกขั้นตั้ง PYTHONHASHSEED=0 เพื่อ reproduce hash.
set -u
export PYTHONHASHSEED=0
export PUOPUY_AUDIT_DATE="${PUOPUY_AUDIT_DATE:-2026-06-02}"   # pin วันที่ตรวจ → กฎวันที่ไม่ขยับตามเวลา
cd "$(dirname "$0")" || exit 2

PY="${PYTHON:-python3}"
REAL_DATA="${1:-}"
fail=0

run() {  # run "<label>" <cmd...>
  local label="$1"; shift
  echo ""
  echo "════════════════════════════════════════════════════════════════"
  echo "▶ $label"
  echo "════════════════════════════════════════════════════════════════"
  if "$@"; then
    echo "✔ ผ่าน: $label"
  else
    echo "✘ ล้มเหลว: $label (exit $?)"
    fail=1
  fi
}

run "[1] version gate"            "$PY" version_gate.py
# [1b] invariant tripwire — สัญญาเดียวกับ pre-commit hook (golden fixture + pin). fail-fast.
run "[1b] invariants (golden fixture + pin)" "$PY" INVARIANTS/check_invariants.py
run "[2] smoke test"             "$PY" smoke_test.py
run "[3] pinned logic"           "$PY" test_pinned_logic.py
run "[3b] parser negative/fuzz"  "$PY" test_parser_negative.py
run "[3c] rules coverage"        "$PY" test_rules_coverage.py
run "[3c2] vat002 tolerance 0.50 (ADR-005)" "$PY" test_vat002_tolerance.py
run "[3d] verification agent"    "$PY" test_verification_agent.py
run "[3d2] verification lens pin"  "$PY" test_verification_lens_pin.py
run "[3d3] verification lens unit" "$PY" test_verification_lenses_unit.py
run "[3m] offline audit (zero outbound)" "$PY" test_offline_audit.py
run "[3n] input hardening (untrusted file)" "$PY" test_input_hardening.py
run "[3o] validators coverage" "$PY" test_validators_coverage.py
run "[3p] parse canary (pin)" "$PY" test_parse_canary.py
run "[3q] parse canary (fixture rate)" "$PY" parse_canary.py tests/fixtures --baseline tests/fixtures/canary_baseline_fixture.json
run "[3e] parser helpers"        "$PY" test_parser_helpers.py
run "[3f] validators"            "$PY" test_validators.py
run "[3g] rules extra (≥90% cov)"      "$PY" test_rules_extra.py
run "[3h] units extra (≥90% cov)"      "$PY" test_units_extra.py
run "[3i] validators extra (≥90% cov)" "$PY" test_validators_extra.py
run "[3j] parser extra (≥90% cov)"     "$PY" test_parser_extra.py
run "[3k] rules extra 2 (≥90% cov)"    "$PY" test_rules_extra2.py
run "[3l] parser extra 2 (≥90% cov)"   "$PY" test_parser_extra2.py
run "[4] mesh contract"          "$PY" test_mesh_contract.py
run "[4b] vendor report (.txt รายผู้ขาย)" "$PY" test_vendor_report.py
run "[5] agent contracts (fixture)" "$PY" test_agents.py . tests/fixtures
run "[6] regression (fixture)"   "$PY" regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json

# [9] pip-audit — สแกนช่องโหว่ dependency (OBJ-OFFLINE). ไม่มี tool = เตือนแล้วข้าม (ไม่ทำ CI ตก)
if command -v pip-audit >/dev/null 2>&1; then
  if [ -f requirements.txt ]; then
    run "[9] pip-audit (requirements.txt)" pip-audit -r requirements.txt
  else
    run "[9] pip-audit (env)" pip-audit
  fi
else
  echo ""
  echo "ℹ ข้าม [9] pip-audit (ยังไม่ติดตั้ง). ติดตั้ง:  pip install pip-audit --break-system-packages"
fi

# ── OBJ-TEST: coverage gate + lint/format/type (graceful — ไม่มี tool = ข้าม ไม่ทำ CI ตก) ──
LINT_SCOPE="offline_guard.py file_guard.py agents/verification_lenses.py agents/verification_agent.py test_offline_audit.py test_input_hardening.py test_validators_coverage.py test_verification_lens_pin.py test_verification_lenses_unit.py"
MYPY_SCOPE="agents/contracts.py agents/base.py offline_guard.py file_guard.py"
if "$PY" -m coverage --version >/dev/null 2>&1; then
  # P2: เปิดวัด branch แล้ว (line≥90 บังคับเหมือนเดิม). บังคับ branch ด้วย: ตั้ง env ก่อนรัน เช่น
  #   PUOPUY_COV_BRANCH_MIN=79 bash run_ci.sh   (floor ปัจจุบันที่ผ่านทุกโมดูล — ดู DECISIONS.md §6.1)
  run "[10] coverage gate (line ≥90% + วัด branch)" "$PY" coverage_gate.py
else echo ""; echo "ℹ ข้าม [10] coverage gate (pip install coverage --break-system-packages)"; fi
if "$PY" -m ruff --version >/dev/null 2>&1; then
  run "[11] ruff (lint, scope)" "$PY" -m ruff check $LINT_SCOPE
else echo ""; echo "ℹ ข้าม [11] ruff (pip install ruff --break-system-packages)"; fi
if "$PY" -m black --version >/dev/null 2>&1; then
  run "[12] black --check (scope)" "$PY" -m black --check $LINT_SCOPE
else echo ""; echo "ℹ ข้าม [12] black (pip install black --break-system-packages)"; fi
if "$PY" -m mypy --version >/dev/null 2>&1; then
  run "[13] mypy (contracts/base + new)" "$PY" -m mypy $MYPY_SCOPE
else echo ""; echo "ℹ ข้าม [13] mypy (pip install mypy --break-system-packages)"; fi

if [ -n "$REAL_DATA" ]; then
  run "[7] regression (ข้อมูลจริง 81 ไฟล์, baseline ec61907f…)" \
      "$PY" regression_full.py . "$REAL_DATA"
  run "[8] agent contracts (ข้อมูลจริง — เช็คเลข baseline ครบ)" \
      "$PY" test_agents.py . "$REAL_DATA"
  # [8b] parse canary บนข้อมูลจริง — ต้องมี canary_baseline.json (สร้างครั้งแรกด้วย --write-baseline)
  if [ -f canary_baseline.json ]; then
    run "[8b] parse canary (ข้อมูลจริง)" \
        "$PY" parse_canary.py "$REAL_DATA" --baseline canary_baseline.json
  else
    echo ""
    echo "ℹ ข้าม [8b] parse canary (ยังไม่มี canary_baseline.json). สร้างครั้งแรก:"
    echo "    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 $PY parse_canary.py \"$REAL_DATA\" --write-baseline canary_baseline.json"
  fi
else
  echo ""
  echo "ℹ ข้าม regression เต็ม (ไม่ได้ระบุ data dir). รันด้วย:  bash run_ci.sh /path/to/data"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
if [ "$fail" -eq 0 ]; then
  echo "✅ CI ผ่านทั้งหมด"
else
  echo "❌ CI มีขั้นที่ล้มเหลว — ดูด้านบน"
fi
echo "════════════════════════════════════════════════════════════════"
exit "$fail"
