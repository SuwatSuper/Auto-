#!/usr/bin/env bash
# run_ci.sh — รันด่าน CI ทั้งหมดในเครื่อง (ลำดับเดียวกับ .github/workflows/ci.yml)
#
# ใช้:
#   bash run_ci.sh                 # gate+smoke+pinned+mesh+agents+regression(fixture)
#   bash run_ci.sh /path/to/data   # + regression เต็มบนข้อมูลจริง (baseline 35b2f7c8…) ถ้าระบุ data dir
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
run "[3c-addr] smart address (ADDR001+003)" "$PY" test_addr_smart.py
run "[3c2] vat002 tolerance 0.50 (ADR-005)" "$PY" test_vat002_tolerance.py
run "[3c3] TAX008 (B1 — เลขภาษีเดียวชื่อต่าง, ไม่พึ่ง master)" "$PY" test_tax008.py
run "[3c4] ADDR006 (B2 — ไปรษณีย์↔จังหวัด, ไม่พึ่ง master)" "$PY" test_addr006.py
run "[3c5] BR004 (B3 — เทียบสาขากับ master)" "$PY" test_br004.py
run "[3d] verification agent"    "$PY" test_verification_agent.py
run "[3d2] verification lens pin"  "$PY" test_verification_lens_pin.py
run "[3d3] verification lens unit" "$PY" test_verification_lenses_unit.py
run "[3m] offline audit (zero outbound)" "$PY" test_offline_audit.py
run "[3n] input hardening (untrusted file)" "$PY" test_input_hardening.py
run "[3o] validators coverage" "$PY" test_validators_coverage.py
run "[3p] parse canary (pin)" "$PY" test_parse_canary.py
run "[3q] parse canary (fixture rate)" "$PY" parse_canary.py tests/fixtures --baseline tests/fixtures/canary_baseline_fixture.json
run "[3e] parser helpers"        "$PY" test_parser_helpers.py
run "[3e2] OPT-1 differential (_dic_int_run/detect byte-identical)" "$PY" test_dic_int_run_equiv.py
run "[3e3] OPT-1b differential (_label_based_amounts byte-identical)" "$PY" test_label_amounts_equiv.py
run "[3e4] parser branch coverage (edge/error path, golden-neutral)" "$PY" test_parser_branch.py
run "[3f] validators"            "$PY" test_validators.py
run "[3g] rules extra (≥90% cov)"      "$PY" test_rules_extra.py
run "[3h] units extra (≥90% cov)"      "$PY" test_units_extra.py
run "[3i] validators extra (≥90% cov)" "$PY" test_validators_extra.py
run "[3j] parser extra (≥90% cov)"     "$PY" test_parser_extra.py
run "[3k] rules extra 2 (≥90% cov)"    "$PY" test_rules_extra2.py
run "[3l] parser extra 2 (≥90% cov)"   "$PY" test_parser_extra2.py
run "[3l2] v9.2 fixes (หน้าต่อ/บาทตัวอักษร/VATmarker/ITM008)" "$PY" test_v9_2_fixes.py
run "[3r] crosscheck idempotency (call-once tripwire)" "$PY" test_crosscheck_idempotency.py
run "[3s] typo sliding-window (>500 names)" "$PY" test_typo_window.py
run "[3t] perf canary (algorithmic blowup guard)" "$PY" test_perf_budget.py
run "[3u] parallel merge — non-empty system_issues" "$PY" test_parallel_merge_nonempty.py
run "[3u2] parallel merge contract (#3 exc-key/#4a file=None/#cap config)" "$PY" test_parallel_merge_contract.py
run "[3v] issue consolidator (Agent ยุบรหัส→ข้อสรุป)" "$PY" test_issue_consolidator.py
run "[3w] super ultra viewer (label คน + บล็อกบริษัท)" "$PY" test_super_ultra_viewer.py
run "[3w1] honesty รายผู้ขาย (A1 — 'ตรง'=เทียบ master จริง ; รองรับบริษัทใหม่)" "$PY" test_honesty_per_bill.py
run "[3w1b] SYS-* summary (A5 — silent skip กฎ crash มองเห็นได้ท้ายการรัน)" "$PY" test_sys_summary.py
run "[3w0] precision council (รีพอร์ตลูกค้า 10 ผู้ตรวจ + 2-tier)" "$PY" test_report_precision.py
run "[3w2] Ultra Agent (ตรวจทาน-ยืนยันด้วยหลักฐานอิสระ)" "$PY" test_ultra_agent.py
# ── structural tripwires (ไม่ใช้ข้อมูลจริง — กัน drift เชิงโครงสร้าง/แหล่งความจริง) ──
run "[3x] golden single-source (doc↔baseline.json sync)" "$PY" test_golden_single_source.py
run "[3x2] FIELD_CODES coverage (แดชบอร์ดเห็นทุกกฎ — กัน false-clean)" "$PY" test_field_codes_coverage.py
run "[3x2b] rule status (A2 — active/disabled/unavailable + เหตุผล ไม่หลอกตา)" "$PY" test_rule_status.py
run "[3x3] date 2-digit year (พ.ศ./ค.ศ. ไม่ขัดกัน)" "$PY" test_date_2digit_year.py
run "[3x4] code-table consistency (MAP+FIELD_LAYOUT ตามทันทุกรหัส)" "$PY" test_code_tables_consistency.py
run "[3x5] A-hardening (advisory/รายงานทนข้อมูลเพี้ยน — ไม่ครัช)" "$PY" test_a_hardening.py
run "[3x6] merged-cell integrity (real_cases — ค่าวิกฤตไม่หายจาก merge)" "$PY" diagnose_merged_cells.py tests/real_cases
run "[3x8] reachability guard (ไม่มี floating module + CI ไม่เขียวบนโค้ดตาย)" "$PY" test_reachability.py
run "[3x8b] parser chain integrity (auto re-export ครบ + identity) [OPT-2 ก]" "$PY" test_parser_chain_integrity.py
run "[3x9] report determinism (รายงาน Excel นิ่ง บน fixtures)" "$PY" test_report_det.py
run "[3x10] reset completeness (parse 2 รอบในโปรเซสเดียว ผลเท่ากัน)" "$PY" test_reset_completeness.py
run "[3x7] package integrity (deliverable zip — ชื่อไฟล์ไทยไม่พัง)" "$PY" test_package_integrity.py
run "[3y] run_addon_pack guard (shoulder feature)" "$PY" test_run_addon_pack_guard.py
run "[3z] file-size ceiling (≤600 LOC/ไฟล์, F4)" "$PY" test_file_size_ceiling.py
run "[3z2] monolith surface contract (26-name getattr API, de-star P1)" "$PY" test_monolith_surface.py
run "[4] mesh contract"          "$PY" test_mesh_contract.py
run "[4b] vendor report (.txt รายผู้ขาย)" "$PY" test_vendor_report.py
run "[4c] real cases (false-positive ที่ลูกค้ารายงาน)" "$PY" test_realcases_v9_2.py
run "[5] agent contracts (fixture)" "$PY" test_agents.py . tests/fixtures
run "[5b] agent meta-conformance (structural, ทุก agent ยึดสัญญาฐาน)" "$PY" test_agent_conformance.py .
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
  # P2: line≥90 บังคับ + [coverage push 2026-06] บังคับ branch ≥85 ด้วย (floor ADR ที่ทุกกลุ่มผ่านแล้ว:
  #   parser 90.3 / rules_engine 85.6 (ตึงสุด) / validators 93.9 / units 100). override ได้: PUOPUY_COV_BRANCH_MIN=NN
  run "[10] coverage gate (line ≥90% + branch ≥85)" env PUOPUY_COV_BRANCH_MIN="${PUOPUY_COV_BRANCH_MIN:-85}" "$PY" coverage_gate.py
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
  run "[7] regression (ข้อมูลจริง 106 ไฟล์, baseline 35b2f7c8…)" \
      "$PY" regression_full.py . "$REAL_DATA"
  run "[8] agent contracts (ข้อมูลจริง — เช็คเลข baseline ครบ)" \
      "$PY" test_agents.py . "$REAL_DATA"
  # [8c] พิสูจน์ parallel == serial บนข้อมูลจริง (golden+issues+recoveries ตรงเป๊ะ) — workers=8 บีบ merge หลาย chunk
  run "[8c] verify parallel == serial (ข้อมูลจริง, workers=8)" \
      "$PY" verify_parallel.py "$REAL_DATA" 8
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
