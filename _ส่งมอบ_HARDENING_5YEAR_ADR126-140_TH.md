# ส่งมอบ — รอบ Hardening 5 ปี (ADR-126…140) · 2026-06-29

> โหมด **LOCKED** ตลอดงาน. ทุกการแก้ **golden-neutral** — corpus golden `23b315e8…` **ไม่ขยับ**
> (พิสูจน์ทุก ADR ด้วย `regression_full . corpus`). ไม่มี rebaseline. ไม่แตะพฤติกรรมการตรวจบน corpus.

## 0 · สถานะ gate (§7) — เขียวครบ

| gate | ผล |
|---|---|
| (1) golden reproduce — engine==agent==baseline | ✅ `23b315e8…` |
| (2) `run_ci.sh corpus` (STRICT) | ✅ **126/0/0** (PASS/FAIL/STRICT-FAIL) |
| (3) parse-canary | ✅ 1056 บิล / 148 ไฟล์ / 0 ไฟล์ได้ 0 บิล |
| (4) crash-fuzz / SYS=0 บน corpus | ✅ SYS-* = 0 (1056 บิล) |
| (5) invariants tripwire | ✅ |
| (6) fresh-extract verify (`make_release`) | ✅ **RELEASE OK** · reproduce `23b315e8` · **0 PII/corpus ใน zip** |
| §10 re-vendor wheelhouse | ✅ 21 wheel cp312 (manylinux2014) · 73MB · gitignored |

Env: Python 3.12.3 + deps pin (`pandas 2.2.2 / numpy 2.2.6 / xlrd 2.0.1 / openpyxl 3.1.5 / rapidfuzz 3.10.1`).

## 1 · งานที่ทำ — 16 ADR golden-neutral (126…140)

**Safety-net / release hygiene**
- **ADR-126** file-size tripwire ข้าม venv/dist/cache (เลิก false-red บน deps) + self-test ในตัว
- **ADR-128** `regression_full` temp ผูก PID + atexit (กัน race รันพร้อมกัน)
- **ADR-129** 🔴 `make_release` ไม่แพ็ก `corpus/` (148 ไฟล์ PII ลูกค้า) / `.venv` / `dist` / รายงาน + self-check `_zip_pii` (defense-in-depth) + verify ด้วย corpus path เดิม (portable-golden) — **ปิดช่องข้อมูลลูกค้ารั่วใน release**

**Crash-guards (กัน crash→SYS→ข้ามกฎ/บิล = false-negative · คลาส GAP-A/B)**
- **ADR-130** `_is_seq_token` กัน `int(float())` OverflowError (seq cell ขยะ → บิลทั้งชีตหาย)
- **ADR-131** `run_rules` drop สมาชิก non-dict ใน items (~14 กฎ item/VAT)
- **ADR-132** `core_utils`: `iv_amount_fragment` OverflowError + `sort_bills_by_date` None
- **ADR-133** `consolidate_bill` ทนบิลเพี้ยน (report layer)
- **ADR-134** `check_iv_date_sequence` str-wrap iv_number (golden-path)
- **ADR-138** QA tripwire: `coverage_gate` ไม่ splat bare-string + `version_gate` ไม่ false-green เวอร์ชันหัวใจ
- **ADR-139** `build_unit_index` coerce non-str (ITM015) + viewer note ไม่เงียบ (SYS trail)

**Honesty / state / FP / dead-guard**
- **ADR-127** (§9-1c) rule-status honesty: กฎตรวจตัวตน = `unavailable-resource` เมื่อ master ว่าง (+ **ADR-141** แก้: ADDR001 active จริง → 8 กฎ ; active 62→54)
- **ADR-135** orchestrator mesh ใหม่ทุก `run()` (กัน findings สะสมข้ามการรัน — state leak)
- **ADR-136** `reject_iv_equal_amount` ล้างเฉพาะ iv ตัวเลขล้วน (กันลบเลขเอกสาร alphanumeric = FP)
- **ADR-137** parser รับที่อยู่ label-glued `เลขที่123` (sibling ADR-125)
- **ADR-140** `district_postal_mismatch` (ADDR007) เว้นกรุงเทพฯ จริง (dead-guard)

**Pass-3 (adversarial review งานตัวเอง + fresh-hunt)**
- **ADR-141** แก้ ADR-127: เอา ADDR001 ออกจาก master-dependent (มี standalone path = active จริง) — Pass-3 review จับเอง
- **ADR-142** `parse_date_any` ตัด `'%d/%m/%y'` fallback ที่ fabricate วันปี 2 หลัก (golden-path false-negative:
  `29/2/68`→`2068-02-29` แทน DT006 ; `12/2/13`→`2013` แทน None) — corpus delta=0 (ทุกวันปี 2024-26)

**รวม 18 ADR (126…142).** ทุก ADR: 1 regression test ใหม่ + register `run_ci.sh` + บันทึก `INVARIANTS/DECISIONS.md` (append-only).
Pass-3 critic verdict: **"lock integrity intact, 0 fix-now"** — 18 fix sound + golden-neutral ; 2 bug-class ที่เหลือ
(dual-normalizer divergence VDU-1/TN-03 ; Thai-numeral zip FP TN-02/RULESA-01/03) = **golden-MOVING → owner-gated ถูกต้อง**
(ทุกจุด fail-safe ด้วย try/except/None ; ไม่ใช่ crash).

## 2 · §9 — 4 เป้าหมาย: สถานะ

### 🔴 9-1 master_companies.json
- **(1c · ทำแล้ว — ADR-127 + แก้ ADR-141):** rule-status honest. master ว่าง (ship default ADR-102) → กฎตัวตน
  **8 ตัว** (`CMP001/004/006, ADDR002/003, TAX003, TAX005, BR004`) รายงาน `unavailable-resource: master_companies.json`
  พร้อมวิธีเปิด (`เพิ่ม_master.py`) — เลิกโชว์ active หลอกตา. **(ADR-141: Pass-3 review จับว่า ADDR001 มี standalone
  path = ฟ้องที่อยู่ตัวเองได้แม้ไม่มี master = active จริง → เอาออกจากชุด).** active 62→**54**, unavailable 1→**9** (8 + ITM009). golden-neutral.
- **(1a · เสนอ — ต้องอนุมัติ):** การ join ปัจจุบัน = `match_company` ใช้ **fuzzy ชื่อ** (bind `m`) + tax_id เฉพาะ
  `r_tax005`/`all_masters` ; มี **MATCH-GUARD** (เลขภาษี 13 หลักต่าง + score<90 → ไม่ผูก) กัน cross-company อยู่แล้ว.
  การเปลี่ยน "primary join → tax_id" = **architectural + golden-MOVING** → ขออนุมัติก่อนทำ.
- **(1b · เสนอ — ต้องอนุมัติ):** แพ็ก master จริงลง release = เปิดกฎตัวตน → **เปลี่ยนผล corpus** = rebaseline
  (ต้องมี ADR + เจ้าของอนุมัติ). กลไกพร้อม: ใส่ ภ.พ.20 ผ่าน `เพิ่ม_master.py` → กฎกลับ active อัตโนมัติ (ADR-127).

### 🟡 9-2 UNIT_OK ไม่สอดคล้อง — **เสนอ + วัดผลกระทบแล้ว (golden-MOVING → รอเจ้าของตัดสิน)**
`rules_engine_rules_b.py:106` `UNIT_OK = r"\d+\s*(?:มม|ซม|นิ้ว|เมตร|ม|กก|ก)\.?|\d+['\"]"` ยกเว้น
`มม/ซม/นิ้ว/เมตร/ม/กก/ก` แต่ **ไม่** ยกเว้น `ลิตร/วัตต์/ขีด/แอมป์/โวลต์` → ITM004 ฟ้อง "5ลิตร/5ขีด" ไม่ลงรอย ADR-075.
**ผลกระทบที่วัดบน corpus จริง:** ถ้าขยาย UNIT_OK ให้ครอบ `ลิตร/ล/วัตต์/ว/ขีด/แอมป์/โวลต์` → **เลิกฟ้อง 9 flag**
(เคส `3ลิตร` ใน "สีทาถนน TOA …" + `5ขีด` ใน "ถุงมือผ้า …" — มี SPELLING_PATTERN "ตัวเลข+ลิตร/ขีด ติดกัน" จงใจ).
→ เป็น **golden-MOVING** (เปลี่ยน `23b315e8`). **ทางเลือกให้เจ้าของ:**
1. คงเดิม (เข้มแต่ไม่สอดคล้อง — `5นิ้ว` เงียบ แต่ `3ลิตร` ฟ้อง)
2. ขยาย UNIT_OK ให้สอดคล้อง (เงียบทุกหน่วยติดเลข) → **rebaseline −9 flag** (ต้อง ADR + อนุมัติ)
3. ไปทางตรงข้าม: เลิกยกเว้นทั้งหมด (`5นิ้ว` ก็ฟ้อง) → rebaseline +flag

→ **ไม่แตะ** จนกว่าเจ้าของเลือก (scope เล็ก, เป็น policy).

### 🟡 9-3 Typo dictionary — **กลไกล็อกแข็งแรงแล้ว (ไม่มีงาน golden-neutral เพิ่มที่ชัด)**
flow เพิ่มคำ + ล็อกการตัดสินอยู่ที่ `THAI_TYPO_PATTERNS` / `CONSTRUCTION_DICT` / `PYTHAINLP_WHITELIST` (config_base)
+ `test_typo_decisions_lock.py` (ตรึงรายคำ ADR-084/121/123 + invariant [B]: ไม่มีคำใน CONSTRUCTION_DICT ที่เป็น
typo-pattern target = กัน ปี๊ป-class). **ตรวจแล้ว:** `คอนกรีด` อยู่ทั้ง WHITELIST + เป็น pattern target — **ไม่ใช่บั๊ก**
(regex ITM004/010 ฟ้องคำผิดจริง ; WHITELIST แค่กัน fuzzy ITM011/012 ฟ้องซ้ำ ; ไม่อยู่ใน CONSTRUCTION_DICT = "คำถูก").
การเพิ่ม tripwire "WHITELIST vs pattern" = **invariant ผิด** (จะ flag ดีไซน์ที่ถูก). → คงระบบเดิม.

### 🟢 9-4 wheels cp312 — **ทำแล้ว (§10)**
re-vendor 21 wheel cp312/manylinux2014 (pandas/numpy/rapidfuzz cp312 + xlrd/openpyxl/matplotlib/plotly/tqdm + deps).
`vendor/wheels/` gitignored (ไม่ commit) ; `make_release` แพ็กเข้า OFFLINE zip ให้เอง. `test_forward_compat.py` =
tripwire เตือนตอน Python ขยับรุ่น (ทำซ้ำขั้นตอนนี้).

## 3 · Findings ที่ "เลื่อนให้เจ้าของรีวิว" (real, golden-neutral บน corpus แต่เปลี่ยน behavior อนาคต / เป็น policy / cleanup)

> พบจาก bug-hunt workflow (47 findings, verify อิสระ). ทั้งหมด corpus delta=0 (golden ไม่ขยับ) แต่ **เปลี่ยน
> พฤติกรรมการตรวจบนข้อมูลอนาคต** หรือเป็น tech-debt/cleanup → **ไม่แตะ** ตาม PRIME DIRECTIVE (รอเจ้าของ).

| id | ไฟล์ | สรุป | ทำไมเลื่อน |
|---|---|---|---|
| TN-02 | thai_postal.py:103 | `_ZIP_RE` `\d` (Unicode) จับเลขไทย `๘๓๐๐๐` → ADDR006/007 อาจ FP บนข้อมูลที่มีเลขไทย | normalize-consistency, interdependent กับ TN-03 ; เปลี่ยน detection อนาคต |
| TN-03 | rules_c:51/67/249 | r_addr006 normalize แต่ r_addr007/010 อ่าน address ดิบ → 3 กฎไม่สม่ำเสมอ | เปลี่ยน input ของ addr007/010 = detection อนาคตเปลี่ยน |
| VDU-1 | puopuy_dates.py:62-91 | 2 สาขาแปลงปี 2 หลัก (เดือนไทย vs dd/mm/yy) ต่างกันที่ปีกำกวม (0-14/40-50) | เปลี่ยน date semantics ; ต้องเจ้าของยืนยันนิยามปี |
| PG-03 | parser_guards.py:138 | excel-serial guard (20000-60000) บังคับเฉพาะ branch ตัวเลข ไม่ครอบ branch string | conservative (กันกู้ ไม่ผูกผิด) ; เปลี่ยน iv recovery อนาคต |
| RULESA-02 | rules_a:205 | `_addr_field_match` containment กลบบ้านเลขที่ต่าง ('15/32' vs '5/32') | master-dependent (dormant) ; เปลี่ยน addr-match เมื่อมี master |
| RULESA-01/03 | rules_a:179/166 | zip regex Thai-glued + room/building regex over-match | เปลี่ยน addr detection อนาคต |
| PH-01/02/04 | parser_p1 | branch_no over-grab / single-cell seller / 4 tax extractor ซ้ำ (tech-debt) | parser behavior/refactor — เสี่ยง, ขอ scope ชัด |
| RPT-01/03 | report_precision.py | council promote ITM011 บน ANY-tier / dead branch | report logic/cleanup |
| GOV-04 | golden_snapshot.py:164 | strip-path เพิ่ม bare prefix → over-strip เชิง pathological | แตะ golden machinery — เสี่ยงสูง, low-confidence |
| MCS-01/02 | master.py:26 / config.py:115 | validate prefix ไม่ครบ 17 (แค่ warning) / dead `_UNIT_SYNONYM_GROUPS` | cleanup/cosmetic |
| AMP-2/3 | parallel_audit / lenses_ext | parallel cap per-chunk / lens Decimal→float | advisory determinism edge |

**ถ้าเจ้าของอนุมัติเป็นชุด** — ผมแนะนำลำดับ: TN-02 (normalize เลขไทย, FP-guard แนว ADR-114) → TN-03 (consistency)
→ MCS-02 (ลบ dead code) → ที่เหลือพิจารณารายตัว. ทุกตัวต้องพิสูจน์ golden delta=0 ก่อน.

## 4 · การส่งมอบ
- **source ที่ hard แล้ว** → push branch `claude/puopuy-system-hardening-ax97ys` (ไม่มี corpus/wheels/master ใน git)
- **OFFLINE-complete zip** (72MB, 347 ไฟล์ + 21 wheels, 0 PII, reproduce `23b315e8`) → สร้างด้วย
  `make_release.py . corpus <out.zip>` (verify ผ่านแล้ว) ; rebuild ได้ทุกเมื่อ.
