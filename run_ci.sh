#!/usr/bin/env bash
# run_ci.sh — รันด่าน CI ทั้งหมดในเครื่อง (ลำดับเดียวกับ .github/workflows/ci.yml)
#
# ใช้:
#   bash run_ci.sh                 # gate+smoke+pinned+mesh+agents+regression(fixture)
#   bash run_ci.sh /path/to/data   # + regression เต็มบนข้อมูลจริง (baseline 23b315e8…) ถ้าระบุ data dir
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
# [FIX 11.06.69] ด่านกันถอยหลังของ 3 เคสจริง — input ซ้ำเงียบ / คอลัมน์ชื่อแพ้คอลัมน์หน่วย / เลขเอกสารโดด 4-5 หลัก
run "[3b1] input dedupe guard (F1/SYS004)"      "$PY" test_input_dedupe.py
run "[3b2] name-col unit-like guard (F3)"       "$PY" test_dic_find_name_unitlike.py
run "[3b3] iv last-resort 4-5 digit (F2)"       "$PY" test_pb_iv_lastresort.py
# [F-MONEYIV v9.3.1] ยอดเงินบนบิล (เช่น subtotal 6 หลัก) ถูกอ่านเป็นเลขที่เอกสาร → กู้เลขจริง (เคส SHS 21 บิล)
run "[3b4] iv≠money guard (F-MONEYIV)"          "$PY" test_iv_money_misread.py
run "[3b5] ADR-136 iv≠money ล้างเฉพาะตัวเลขล้วน (iv มีอักษรไม่ถูกล้าง=FP)" "$PY" test_adr136_iv_alnum_guard.py
run "[3c] rules coverage"        "$PY" test_rules_coverage.py
run "[3c-addr] smart address (ADDR001+003)" "$PY" test_addr_smart.py
run "[3c2] vat002 tolerance 0.50 (ADR-005)" "$PY" test_vat002_tolerance.py
run "[3c2b] vat itemsum guard (ADR-109 — bool/non-finite item ไม่ครัชเงียบ)" "$PY" test_vat_itemsum_guard.py
run "[3c3] TAX008 (B1 — เลขภาษีเดียวชื่อต่าง, ไม่พึ่ง master)" "$PY" test_tax008.py
run "[3c4] ADDR006 (B2 — ไปรษณีย์↔จังหวัด, ไม่พึ่ง master)" "$PY" test_addr006.py
run "[3c4b] ADDR province word-boundary (ADR-110 — กัน substring FP)" "$PY" test_addr_province_boundary.py
run "[3c4c] ADR-122 กฎใหม่ VAT012/ADDR010/ADDR007 (บาทอักษร↔ตัวเลข, จังหวัดปลอม, ไปรษณีย์↔อำเภอ)" "$PY" test_adr122_new_rules.py
run "[3c4c2] ADR-140 ADDR007 เว้นกรุงเทพฯ จริง (dead-guard fix)" "$PY" test_adr140_bkk_skip.py
run "[3c4c3] ADR-143 เลขไทยในรหัสไปรษณีย์ไม่ FP (ADDR006/007 normalize)" "$PY" test_adr143_thai_zip.py
run "[3c4d] ADR-123 เคลียร์ก้ำกึ่ง (กลุ่ม A ฟ้องรีเช็ค / กลุ่ม B เงียบ / FP=0 / lookbehind หล็กฉาก)" "$PY" test_adr123_borderline_clear.py
run "[3c4e] ADR-125 ที่อยู่ 2 บรรทัด — กู้บ้านเลขที่หาย (KNT/CETI) + guard ไม่เก็บบรรทัดสินค้า" "$PY" test_adr125_addrline_houseno.py
run "[3c4f] ADR-137 ที่อยู่ label-glued 'เลขที่123'/'หมู่ที่4' ถูกเก็บ (sibling ADR-125)" "$PY" test_adr137_addr_glued.py
run "[3c5] BR004 (B3 — เทียบสาขากับ master)" "$PY" test_br004.py
run "[3c6] IV007 (D1 — เลขใบกำกับขยะ absolute validity)" "$PY" test_iv007.py
run "[3c7] IV parser guard (D2 — ไม่คว้าเศษ float เป็นเลขเอกสาร)" "$PY" test_iv_parser_guard.py
run "[3c7b] ADR-132 core_utils guards (iv_amount_fragment OverflowError + sort file/sheet None)" "$PY" test_adr132_core_utils_guards.py
# ── [BS-1..4] ปิดช่องโหว่การตรวจจับ (detection blind spots) — golden-neutral, corpus=0 (ADR-114..117) ──
run "[3c8] BS-1 เลขภาษี full-width ０-９ (ADR-114)"      "$PY" test_bs1_taxid_fullwidth.py
run "[3c9] BS-2 VAT011 ใบมียอดแต่ VAT=0 (ADR-115)"      "$PY" test_bs2_vat011_zero.py
run "[3c10] BS-3 TAX009 ชื่อเดียวเลขภาษีต่าง (ADR-116)"  "$PY" test_bs3_tax009_samename.py
run "[3c11] BS-4 DT006 วันผิดปฏิทินเส้น TOR (ADR-117)"   "$PY" test_bs4_dt006_tor_calendar.py
run "[3c12] re-bughunt fixes — viewer grouping clean_tax_id (ADR-118)" "$PY" test_adr118_viewer_grouping.py
run "[3d] verification agent"    "$PY" test_verification_agent.py
run "[3d2] verification lens pin"  "$PY" test_verification_lens_pin.py
run "[3d3] verification lens unit" "$PY" test_verification_lenses_unit.py
run "[3m] offline audit (zero outbound)" "$PY" test_offline_audit.py
run "[3n] input hardening (untrusted file)" "$PY" test_input_hardening.py
run "[3n2] fuzz matrix — 60 กฎรอด non-str/edge (GAP-A: ไม่ครัช→SYS→ข้ามกฎ=FN)" "$PY" test_fuzz_rules_robust.py
run "[3n3] GAP-B — run_rules coerce items→list (items non-list ไม่โยน→กันข้ามทั้งบิล=FN)" "$PY" test_gap_b_items_coerce.py
run "[3n4] ADR-131 — run_rules drop สมาชิก non-dict ใน items (กัน ~14 กฎครัช→ข้ามเงียบ=FN)" "$PY" test_adr131_item_member.py
run "[3o] validators coverage" "$PY" test_validators_coverage.py
run "[3o2] typing leaf (ADR-112 — mypy leaf 4 โมดูล; skip ถ้าไม่มี mypy)" "$PY" test_typing_leaf.py
run "[3p] parse canary (pin)" "$PY" test_parse_canary.py
run "[3q] parse canary (fixture rate)" "$PY" parse_canary.py tests/fixtures --baseline tests/fixtures/canary_baseline_fixture.json
run "[3e] parser helpers"        "$PY" test_parser_helpers.py
run "[3e2] OPT-1 differential (_dic_int_run/detect byte-identical)" "$PY" test_dic_int_run_equiv.py
run "[3e3] OPT-1b differential (_label_based_amounts byte-identical)" "$PY" test_label_amounts_equiv.py
run "[3e4] parser branch coverage (edge/error path, golden-neutral)" "$PY" test_parser_branch.py
run "[3e5] ADR-130 _is_seq_token OverflowError guard (seq cell ขยะยาว ไม่ทำบิลทั้งชีตหาย)" "$PY" test_adr130_seq_overflow.py
run "[3f] validators"            "$PY" test_validators.py
run "[3f1] ADR-134 check_iv_date_sequence str-wrap iv_number (กัน non-str ครัช)" "$PY" test_adr134_iv_number_str.py
run "[3g] rules extra (≥90% cov)"      "$PY" test_rules_extra.py
run "[3h] units extra (≥90% cov)"      "$PY" test_units_extra.py
run "[3i] validators extra (≥90% cov)" "$PY" test_validators_extra.py
run "[3j] parser extra (≥90% cov)"     "$PY" test_parser_extra.py
run "[3k] rules extra 2 (≥90% cov)"    "$PY" test_rules_extra2.py
run "[3l] parser extra 2 (≥90% cov)"   "$PY" test_parser_extra2.py
run "[3l2] v9.2 fixes (หน้าต่อ/บาทตัวอักษร/VATmarker/ITM008)" "$PY" test_v9_2_fixes.py
run "[3r] crosscheck idempotency (call-once tripwire)" "$PY" test_crosscheck_idempotency.py
run "[3s] typo sliding-window (>500 names)" "$PY" test_typo_window.py
run "[3s2] rules typo branch (ADR-113 — r_itm004/r_itm010 emit, 5นิ้ว=ไม่ฟ้อง ADR-075)" "$PY" test_rules_typo_branch.py
run "[3s3] ITM011/012 word-cut FP (ADR-119 — 'ชุบสังกะสี' เงียบ + typo จริงยังฟ้อง)" "$PY" test_itm011_wordcut_fp.py
run "[3t] perf canary (algorithmic blowup guard)" "$PY" test_perf_budget.py
run "[3u] parallel merge — non-empty system_issues" "$PY" test_parallel_merge_nonempty.py
run "[3u2] parallel merge contract (#3 exc-key/#4a file=None/#cap config)" "$PY" test_parallel_merge_contract.py
run "[3v] issue consolidator (Agent ยุบรหัส→ข้อสรุป)" "$PY" test_issue_consolidator.py
run "[3v1] ADR-133 consolidate_bill ทนบิลเพี้ยน (issues=None/non-dict/non-str code)" "$PY" test_adr133_consolidator_robust.py
run "[3v2] report lane/aspect (ADR-111 — CMP005 must-fix + ITM019/020 หน่วย)" "$PY" test_report_lane_aspect.py
run "[3w] super ultra viewer (label คน + บล็อกบริษัท)" "$PY" test_super_ultra_viewer.py
run "[3w0a] ADR-139 advisory robust (build_unit_index coerce non-str + viewer note ไม่เงียบ)" "$PY" test_adr139_advisory_robust.py
run "[3w1] honesty รายผู้ขาย (A1 — 'ตรง'=เทียบ master จริง ; รองรับบริษัทใหม่)" "$PY" test_honesty_per_bill.py
run "[3w1b] SYS-* summary (A5 — silent skip กฎ crash มองเห็นได้ท้ายการรัน)" "$PY" test_sys_summary.py
run "[3w0] precision council (รีพอร์ตลูกค้า 10 ผู้ตรวจ + 2-tier)" "$PY" test_report_precision.py
run "[3w0b] รายงานลูกค้า C1+C2 (ระบุไฟล์ + หน่วยสะกดผิดขึ้นช่องรายการสินค้า)" "$PY" test_report_c1_c2.py
run "[3w2] Ultra Agent (ตรวจทาน-ยืนยันด้วยหลักฐานอิสระ)" "$PY" test_ultra_agent.py
# ── structural tripwires (ไม่ใช้ข้อมูลจริง — กัน drift เชิงโครงสร้าง/แหล่งความจริง) ──
run "[3x] golden single-source (doc↔baseline.json sync)" "$PY" test_golden_single_source.py
run "[3x-typo] typo decisions lock (ADR-084) + _kw_in_name characterization (ADR-085/087 safety net)" "$PY" test_typo_decisions_lock.py
run "[3x-itm005] ITM005 precision characterization (ADR-087 F1 sniper — FP cut + recall lock)" "$PY" test_itm005_precision.py
run "[3x-fc] forward-compat deprecation tripwire (ADR-088/FC-1 — กันระบบล้าหลังเงียบตอน bump dep ปีที่ 4-5)" "$PY" test_forward_compat.py
run "[3x-fc2] ADR-138 QA tripwire robust (coverage_gate ไม่ splat + version_gate ไม่ false-green)" "$PY" test_adr138_gate_robust.py
run "[3x2] FIELD_CODES coverage (แดชบอร์ดเห็นทุกกฎ — กัน false-clean)" "$PY" test_field_codes_coverage.py
run "[3x2b] rule status (A2 — active/disabled/unavailable + เหตุผล ไม่หลอกตา)" "$PY" test_rule_status.py
run "[3x3] date 2-digit year (พ.ศ./ค.ศ. ไม่ขัดกัน)" "$PY" test_date_2digit_year.py
run "[3x3a] ADR-142 ตัด %d/%m/%y fallback (วันเสีย/กำกวม→None→DT006 ไม่ fabricate วันอนาคต)" "$PY" test_adr142_date_2digit_fallback.py
run "[3x3b] date parse characterization (ทุกสาขา + adversarial, ADR-053)" "$PY" test_date_parse_characterization.py
run "[3x3b2] ADR-144 เดือนไทย+ปีกำกวม→None (สอดคล้อง m_yy ; ไม่ fabricate วันมั่ว)" "$PY" test_adr144_thai_month_ambiguous.py
run "[3x3c] DOC001 SHORT guard (ADR-058 — เทมเพลตก๊อป/บิลเดี่ยว ไม่ใช่ 'วัน')" "$PY" test_doc001_short_guard.py
run "[3x4] code-table consistency (MAP+FIELD_LAYOUT ตามทันทุกรหัส)" "$PY" test_code_tables_consistency.py
run "[3x5] A-hardening (advisory/รายงานทนข้อมูลเพี้ยน — ไม่ครัช)" "$PY" test_a_hardening.py
run "[3x6] merged-cell integrity (real_cases — ค่าวิกฤตไม่หายจาก merge)" "$PY" diagnose_merged_cells.py tests/real_cases
run "[3x8] reachability guard (ไม่มี floating module + CI ไม่เขียวบนโค้ดตาย)" "$PY" test_reachability.py
run "[3x8b] parser chain integrity (auto re-export ครบ + identity) [OPT-2 ก]" "$PY" test_parser_chain_integrity.py
run "[3x9] report determinism (รายงาน Excel นิ่ง บน fixtures)" "$PY" test_report_det.py
run "[3x10] reset completeness (parse 2 รอบในโปรเซสเดียว ผลเท่ากัน)" "$PY" test_reset_completeness.py
run "[3x11] stub-marker (master จริงไม่ถูกตีเป็น stub)" "$PY" test_stub_marker.py
run "[3x12] match-guard (กัน fuzzy ผูกข้ามบริษัท)" "$PY" test_match_guard.py
run "[3x13] rules_c Decimal gates (ค่าขอบเงิน)" "$PY" test_rules_c_decimal_gates.py
run "[3x14] bughunt hardening (crash/data-integrity guards, golden-safe)" "$PY" test_bughunt_hardening.py
run "[3x14b] bughunt recheck (IV dup ข้ามหลัก/VAT004/ANTI_PREFIX/_D nan-inf/leap พ.ศ./addr005)" "$PY" test_bughunt_recheck.py
run "[3x14c] re-audit 2026-06-20 (F1/F2/L1-L3/L4/P3/P4/A-C1/A-M1/A-L3/REP-C1/C2/M1)" "$PY" test_recheck_20260620.py
run "[3x14d] re-audit 2026-06-21 (P-MED2 label-row≠item/ITM016 + V-F3 DOC001 sheet day.month sanity)" "$PY" test_recheck_20260621.py
run "[3x14e] 5-year hardening (ADR-061 .bak stub-aware/ADR-062 report retention/ADR-063 utf8 console)" "$PY" test_recheck_5year.py
run "[3x14f] enabled-rules fixes 2026-06-22 (ADR-064..076: M-1/C-1/C-2/CMP003/BR/ITM016/DOC001/DT004/ADDR/ITM004/010)" "$PY" test_recheck_rules_20260622.py
run "[3x7] package integrity (deliverable zip — ชื่อไฟล์ไทยไม่พัง)" "$PY" test_package_integrity.py
run "[3x7b] make_release hygiene (ADR-129 — ไม่แพ็ก corpus PII/.venv/dist + self-check)" "$PY" test_make_release_hygiene.py
run "[3y] run_addon_pack guard (shoulder feature)" "$PY" test_run_addon_pack_guard.py
run "[3z] file-size ceiling (≤600 LOC/ไฟล์, F4 + ADR-126 self-test ข้าม venv/dist/cache)" "$PY" test_file_size_ceiling.py
run "[3z2] monolith surface contract (26-name getattr API, de-star P1)" "$PY" test_monolith_surface.py
run "[4] mesh contract"          "$PY" test_mesh_contract.py
run "[4a] ADR-135 mesh reset ต่อ run() (กัน findings สะสมข้ามการรัน)" "$PY" test_adr135_mesh_reset.py
run "[4b] vendor report (.txt รายผู้ขาย)" "$PY" test_vendor_report.py
run "[4b2] unit language note (ADR-091 — flag เฉพาะหน่วยเดียวกัน 2 สคริปต์)" "$PY" test_unit_lang_note.py
run "[4b3] unit missing rules (ADR-105/106 — ITM020 ทั้งบิลไม่มีหน่วย + ZWNJ/header)" "$PY" test_unit_missing_rules.py
run "[4b4] ITM001 lump-sum guard (ADR-107 — กัน V×V≠V ปลอม + parser ไม่เดา qty/price)" "$PY" test_itm001_lumpsum.py
run "[4b5] ITM020 collapse (ADR-108 — ยุบ 'ทั้งบิลไม่มีหน่วย' เป็นสรุปต่อไฟล์ ไม่ร่ายทีละบิล)" "$PY" test_itm020_collapse.py
run "[4c] real cases (false-positive ที่ลูกค้ารายงาน)" "$PY" test_realcases_v9_2.py
run "[5] agent contracts (fixture)" "$PY" test_agents.py . tests/fixtures
run "[5b] agent meta-conformance (structural, ทุก agent ยึดสัญญาฐาน)" "$PY" test_agent_conformance.py .
run "[6] regression (fixture)"   "$PY" regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json

# [9] pip-audit — สแกนช่องโหว่ dependency (OBJ-OFFLINE). ไม่มี tool = เตือนแล้วข้าม (ไม่ทำ CI ตก)
# [CI-STRICT 11.06.69] PUOPUY_CI_STRICT=1 → gate 9-13 "ห้ามข้าม": tool หาย = CI ตกทันที
#   (ปิดรู "เขียวหลอก" — เครื่องที่ไม่ติดตั้ง QA tools เคยผ่านโดยข้าม 5 gates เงียบ ๆ).
#   default ยังเป็น graceful-skip (dev เครื่องเบารันได้) ; เครื่อง certify ตั้ง STRICT=1 เสมอ.
_strict_skip() {  # $1 = ชื่อ gate, $2 = คำสั่งติดตั้ง
  echo ""
  if [ "${PUOPUY_CI_STRICT:-0}" = "1" ]; then
    echo "✘ [STRICT] $1 — tool ไม่ติดตั้ง (ติดตั้ง: $2)"; fail=1
  else
    echo "ℹ ข้าม $1 (ติดตั้ง: $2)"
  fi
}
# [ADR-097] ตรวจ pip-audit แบบเดียวกับ QA gate อื่น (coverage/ruff/black/mypy ใช้ "$PY" -m …):
#   เดิมใช้ `command -v pip-audit` ซึ่งพึ่ง "binary บน PATH" เท่านั้น → ถ้าสั่งรันด้วย $PY จาก venv
#   ที่ bin ไม่อยู่บน PATH (เช่น PYTHON=/path/venv/bin/python โดยไม่ activate) STRICT จะ "ตก"
#   ทั้งที่ pip-audit ติดตั้งครบในสภาพแวดล้อมเดียวกับ $PY = false-red (ชนิดเดียวกับรู "เขียว/แดงหลอก"
#   ที่ ADR-096 ปิดไป). แก้: ลอง module form ก่อน (สอดคล้อง $PY และ gate อื่น) → ถ้าไม่ได้ค่อย
#   fallback เป็น binary บน PATH (backward-compat เครื่องเดิม) → ไม่มีก็ STRICT ตกตามเดิม. golden-neutral.
if "$PY" -m pip_audit --version >/dev/null 2>&1; then
  if [ -f requirements.txt ]; then
    run "[9] pip-audit (requirements.txt)" "$PY" -m pip_audit -r requirements.txt
  else
    run "[9] pip-audit (env)" "$PY" -m pip_audit
  fi
elif command -v pip-audit >/dev/null 2>&1; then
  if [ -f requirements.txt ]; then
    run "[9] pip-audit (requirements.txt)" pip-audit -r requirements.txt
  else
    run "[9] pip-audit (env)" pip-audit
  fi
else
  _strict_skip "[9] pip-audit" "pip install pip-audit --break-system-packages"
fi

# ── OBJ-TEST: coverage gate + lint/format/type (graceful — ไม่มี tool = ข้าม ไม่ทำ CI ตก) ──
LINT_SCOPE="offline_guard.py file_guard.py agents/verification_lenses.py agents/verification_agent.py test_offline_audit.py test_input_hardening.py test_validators_coverage.py test_verification_lens_pin.py test_verification_lenses_unit.py"
MYPY_SCOPE="agents/contracts.py agents/base.py offline_guard.py file_guard.py"
if "$PY" -m coverage --version >/dev/null 2>&1; then
  # P2: line≥90 บังคับ + [coverage push 2026-06] บังคับ branch ≥85 ด้วย (floor ADR ที่ทุกกลุ่มผ่านแล้ว บน Py3.12+pinned:
  #   parser branch 85.3 / rules_engine 85.1 (ตึงสุด) / validators 85.2 / units 100). override ได้: PUOPUY_COV_BRANCH_MIN=NN
  # [drift-fix 2026-06] GitHub CI (ci.yml) ตั้ง PUOPUY_COV_BRANCH_MIN=85 แล้วเช่นกัน → local==CI เข้มเท่ากัน
  run "[10] coverage gate (line ≥90% + branch ≥85)" env PUOPUY_COV_BRANCH_MIN="${PUOPUY_COV_BRANCH_MIN:-85}" "$PY" coverage_gate.py
else _strict_skip "[10] coverage gate" "pip install coverage --break-system-packages"; fi
if "$PY" -m ruff --version >/dev/null 2>&1; then
  run "[11] ruff (lint, scope)" "$PY" -m ruff check $LINT_SCOPE
else _strict_skip "[11] ruff" "pip install ruff --break-system-packages"; fi
if "$PY" -m black --version >/dev/null 2>&1; then
  run "[12] black --check (scope)" "$PY" -m black --check $LINT_SCOPE
else _strict_skip "[12] black" "pip install black --break-system-packages"; fi
if "$PY" -m mypy --version >/dev/null 2>&1; then
  run "[13] mypy (contracts/base + new)" "$PY" -m mypy $MYPY_SCOPE
else _strict_skip "[13] mypy" "pip install mypy --break-system-packages"; fi

if [ -n "$REAL_DATA" ]; then
  run "[7] regression (ข้อมูลจริง 148 ไฟล์, baseline 23b315e8…)" \
      "$PY" regression_full.py . "$REAL_DATA"
  run "[8] agent contracts (ข้อมูลจริง — เช็คเลข baseline ครบ)" \
      "$PY" test_agents.py . "$REAL_DATA"
  # [8c] พิสูจน์ parallel == serial บนข้อมูลจริง (golden+issues+recoveries ตรงเป๊ะ) — workers=8 บีบ merge หลาย chunk
  run "[8c] verify parallel == serial (ข้อมูลจริง, workers=8)" \
      "$PY" verify_parallel.py "$REAL_DATA" 8
  # [8d] เลขที่เอกสาร (iv_number) ตรงเซลล์จริง — ตรวจอิสระจาก baseline (กัน float-tail/คว้าเลขผิด แม้ rebaseline ผิด)
  #   ADR-044: บั๊ก TNT float decimal-tail เคยหลุดเพราะ golden เทียบ baseline ที่ผิดเอง → ด่านนี้เทียบไฟล์ดิบตรง ๆ
  run "[8d] iv-number ตรงเซลล์จริง (ข้อมูลจริง — อิสระจาก golden)" \
      "$PY" _audit_iv_truth.py "$REAL_DATA"
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
