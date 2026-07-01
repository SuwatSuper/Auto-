# รายงาน DEEP AUDIT กอง 3 (จุดบอด) — ปุ้มปุ้ย v9.3.4

> **งานสืบสวนหาจุดบอดที่ยังไม่มีใครตรวจ** (คนละงานกับ prompt v2 ที่ปิด ADR-152 แล้ว)
> วันที่: 2026-07-01 · ผู้ตรวจ: Principal Reliability Engineer + Code Auditor
> ระบบ: `puopuy_v9_3_4_FIXED_CORPUS_no_wheels` (ผ่าน ADR-152 · 148 ไฟล์จริงที่ `./corpus`)

---

## 0) สรุปผู้บริหาร (Executive Summary)

ตรวจครบ **6 track (A–F)** ด้วย harness/คำสั่งจริงบน corpus 148 ไฟล์. ผล:

| Track | หัวข้อ | ผล | Finding |
|-------|--------|-----|---------|
| A | Fuzz / Robustness | ✅ สะอาด | 0 (parser กันขยะครบ + log SYS) |
| B | Scale / Performance / Memory | 🔴 เจอ + แก้แล้ว | **1** — r_tax008 O(n²) → O(n) (**ADR-154**) |
| C | Code audit โมดูลที่ยังไม่อ่าน | 🟡 เจอ 2 + แก้แล้ว | **2** — issues coerce (**ADR-155**) · webverify tier (**ADR-156**) |
| D | Determinism / Idempotency | ✅ สะอาด | 0 (deterministic ครบทุกมิติ) |
| E | Report Integrity | ✅ สะอาด | 0 (ยอดกระทบยอด + locked format ครบ) |
| F | สกัดกฎ 68 ข้อ | 📋 ส่ง Tor | ตาราง → `TRACK_F_RULES_FOR_TOR_REVIEW_TH.md` |

**รวมแก้ 3 finding — ทั้งหมด golden-neutral (golden `23b315e8…` ไม่ขยับ) + CI 136 gate เขียว 0 fail.**

**เงื่อนไขความซื่อสัตย์:** นี่ไม่ใช่ "ปลอดภัย 100%" — เป็น "ตรวจ 6 track นี้แล้วผลตามข้างบน + เหลือมุมที่ยังไม่ครอบคลุม (ระบุท้ายแต่ละ track)".

### สรุป ADR ที่เพิ่ม (append-only, ต่อจาก ADR-153)
- **ADR-154** [🔴 PERF/Track B] — r_tax008 O(n²)→O(n): memoize `_tax008_name`/`_tax008_clean` (pure) — golden-neutral
- **ADR-155** [🟡 Track C] — run_rules coerce `bill['issues']`→list — กัน silent false-negative
- **ADR-156** [🟡 Track C] — webverify tier state ใช้ `'MID'` ไม่ใช่ `'MEDIUM'` (สาขา NEEDS_REVIEW เดิมตาย) — advisory golden-neutral

---

## 1) BASELINE GATE (ก่อนเริ่ม + หลังแก้)

- สภาพแวดล้อม: Python **3.12.3** · venv · `pip install -r requirements.txt -c constraints.txt` (numpy 2.2.6 / pandas 2.2.2 / xlrd 2.0.1) + QA tools (coverage 7.14.3 / ruff 0.15.19 / black 26.5.1 / mypy 2.1.0 / pip-audit 2.10.1)
- `import pythainlp` → **ModuleNotFoundError** (ตามกฎเหล็ก landmine #6) ✅
- เคลียร์ bytecode ก่อน verify hash เสมอ
- **ก่อนเริ่ม:** golden `23b315e809b6a2d095f2192a68dfc11e789a69b0b8d9f55ed994b70788517301` · `BILLS=1056 … typos=51` · CI 133 gate เขียว ✅
  - (หมายเหตุ: `[3x7] package integrity` ตกตอนแรกเพราะไฟล์ยังไม่ commit ในโฟลเดอร์ที่ extract ใหม่ — `package.sh` ใช้ `git ls-files` → commit แล้วผ่านทันที = artifact ของสภาพแวดล้อม ไม่ใช่บั๊กโค้ด)
- **หลังแก้ทั้งหมด:** golden **ไม่ขยับ** `23b315e8…` · `BILLS=1056 … typos=51` · CI **136 gate เขียว 0 fail** (133 เดิม + 3 test ใหม่) ✅

---

## 2) Track A — Fuzz / Robustness

**ตรวจอะไร:** parser ต้องไม่ครัช/ค้าง/รั่ว กับไฟล์เสีย + ต้อง log SYS (ไม่กลืนเงียบ) + ไม่ดึงบิลปลอมจากขยะ.

**harness:** `_audit_fuzz_harness.py` — ยิงไฟล์ปลอม **15 แบบ** เข้า `parse_all_files` จริง ภายใต้ `ulimit -v 4GB`:
empty · truncated (½/512B/8B) · fake magic PK · not-excel · null bytes 4KB · OLE magic + garbage · huge filename 200 ตัว · high-byte name · random binary 20KB · xml-not-xlsx · **zipbomb 50MB** · **nested zip** · **XML entity-expansion (billion-laughs)**.

**ผล: ✅ สะอาด**
- ไม่ throw · ไม่ค้าง (0.07s รวม) · **bills=0** (ไม่ดึงบิลปลอมจากขยะ)
- **peak RSS 169MB** ใต้เพดาน 4GB — zipbomb ถูก `file_guard` ตัดที่ decompress ratio 1024x > 200x
- **15 SYS001 issues logged** (ไม่กลืนเงียบ) — ตรงพฤติกรรมที่ต้องการ

**มุมที่ยังไม่ครอบคลุม:** ไม่ได้ fuzz ระดับ byte-mutation ของไฟล์ .xls จริง (structure-aware fuzzing เชิงลึก) · ไม่ได้ทดสอบ concurrent-write/ไฟล์ถูกแก้ระหว่างอ่าน. เท่าที่ตรวจ (15 คลาส input เสีย) = สะอาด.

---

## 3) Track B — Scale / Performance / Memory  🔴 **เจอ finding (แก้แล้ว)**

**ตรวจอะไร:** พฤติกรรมที่ scale ใหญ่ (เป้า 4,000–5,000 บริษัท) — เวลาเชิงเส้น / RSS ไม่รั่ว / ไม่มี O(n²).

**harness:** `_audit_scale_harness.py` — ก๊อป corpus × **1/5/10/20** (สูงสุด 21,120 บิล / 2,960 ไฟล์) วัด parse-time และ audit-core-time แยกกัน + current RSS + differential `cProfile`.
⚠️ **ข้อจำกัด:** ข้อมูล synthetic (ก๊อปซ้ำ) ≠ distribution จริง → ทำ dup detection หนักผิดธรรมชาติ → ผลเป็น "เชิงชี้นำ" (รูปทรง O()) ไม่ใช่ตัวเลข production.

**สิ่งที่เจอ:**
- **parse = O(n) ปกติ** — ms/file คงที่ 53→56 (ratio 1.05×)
- **audit-core = O(n²)** — ms/bill = 1.58→3.78→6.63→11.69 (mult 1/5/10/20 · ratio **7.39×**)
- **cProfile ชี้ชัด:** `r_tax008` (rules_engine_rules_c.py) ครอง **21.35/32.0s** ที่ mult=4 (15.85× สำหรับ 4× บิล = quadratic). ตัวประกอบ `clean_tax_id`/`normalize_text`/`re.sub` ที่ superlinear ล้วนเป็น downstream ของการถูกเรียก O(g²) ครั้งใน r_tax008.

**root cause:** r_tax008 ("เลขภาษีเดียวชื่อต่าง" · cross-bill) เดินกลุ่มเลขภาษีเดียวกันขนาด g แต่ **recompute `_tax008_name`/`clean_tax_id` ซ้ำ O(g²) ครั้ง** (normalize ชื่อเดิม ๆ ทุกคู่) แม้ ADR-103 จัด index กลุ่มไว้แล้ว. เป็น **global cross-bill** → ต่างจาก per-file check → **จะกระทบจริงเมื่อผู้ขายใหญ่ 1 ราย (เลขภาษีเดียว) มีใบจำนวนมาก**.

**การแก้ (ADR-154 · golden-neutral):** memoize 2 pure function (`_tax008_name`, `_tax008_clean` = wrap clean_tax_id) ด้วย `@lru_cache` — Track B อนุญาตชัด ("cache/dedup ที่ผลเท่าเดิม"). g² recompute ยุบเหลือ ~distinct.

**พิสูจน์:**
- golden `23b315e8…` **ไม่ขยับ** (byte-identical) · `test_adr154_tax008_memo.py`: memoized == fresh computation ทุก sample + cache-hit ทำงาน + r_tax008 ยัง detect/เงียบตามเกณฑ์เดิม
- **วัดหลังแก้:** ms/bill = 0.98→1.05→1.14→1.43 (ratio **1.46× = O(n) แล้ว**) · mult=20 audit **246.9s → 30.3s (8.1× เร็วขึ้น)**

| mult | บิล | audit ก่อน | audit หลัง | ms/bill ก่อน→หลัง |
|------|-----|-----------|-----------|-------------------|
| 1 | 1,056 | 1.7s | 1.0s | 1.58 → 0.98 |
| 5 | 5,280 | 20.0s | 5.5s | 3.78 → 1.05 |
| 10 | 10,560 | 70.0s | 12.0s | 6.63 → 1.14 |
| 20 | 21,120 | 246.9s | 30.3s | 11.69 → 1.43 |

- **RSS ไม่รั่ว:** residual after-gc 131→285MB ที่ mult 1→20 (bounded — เป็น index ของ batch ล่าสุดที่ค้าง reference ไม่ใช่ leak สะสม)
- `check_product_typos` มี **cap `MAX_TYPO_NAMES=3000`** — เกินเพดาน = ข้าม + log SYS002 (graceful degrade ตามดีไซน์ ไม่ครัช)

**มุมที่ยังไม่ครอบคลุม:** ทดสอบด้วย synthetic (148 บริษัทซ้ำ ๆ) ไม่ใช่ 4,000–5,000 บริษัท *distinct* จริง → ตัวเลข ms เป็นเชิงชี้นำ. แต่รูปทรง O(n²)→O(n) ของ r_tax008 พิสูจน์ด้วย profile จริง.

---

## 4) Track C — Code Audit โมดูลที่ยังไม่อ่าน  🟡 **เจอ 2 finding (แก้แล้ว)**

**ตรวจอะไร:** อ่านโมดูลที่ audit รอบก่อนยังไม่เปิด หา silent-failure / resource leak / dead code / logic ขัดกัน + branch ที่ไม่มี test.

**วิธี:** fan-out **7 audit agent** ครอบโมดูลทั้งพื้นผิว (~60 โมดูล) → adversarial verify ทุก finding (พยายาม refute ก่อน) บน corpus จริง. cluster:
`flagged-unread-core` · `agents-mesh` · `agents-report-llm` · `reporting-layer` · `engine-plumbing` · `orchestration-infra` · `parse-core-robustness`.

**ผล: 5/7 cluster สะอาด · 2 cluster เจอรวม 3 raw finding → verify → 2 จริง (แก้) + 1 unreachable (ไม่แก้)**

### F-C1 (ADR-155) — run_rules ไม่ coerce `bill['issues']`→list = silent false-negative
- **root cause:** run_rules มี guard ครบ (items→list ADR-124, members→dict ADR-131, text→str GAP-A) แต่ `'issues'` ได้แค่ `setdefault('issues', [])` (no-op ถ้ามีอยู่แต่เป็น non-list). ทุกกฎที่พบปัญหา → `add_issue` → `b['issues'].append` ครัช → run_rules ดักเป็น SYS-`<code>` → **ข้ามกฎเงียบ** → บิลที่มี CRITICAL/ERROR จริงโผล่เป็น "ตรง" หลอก.
- **แก้:** `if not isinstance(bill.get('issues'), list): bill['issues'] = []` (แนวเดียว ADR-124). corpus ทุกบิล issues=list → no-op → **golden-neutral**.
- **test:** `test_adr155_issues_coerce.py` — issues=None/''/dict/int/str → coerce + TAX001 ยังฟ้อง (ไม่ silent-skip).

### F-C2 (ADR-156) — webverify เทียบ tier == 'MEDIUM' = สาขาตาย
- **root cause:** `confidence_tier()` คืน `HIGH/MID/LOW` เท่านั้น (พิสูจน์ด้วยรัน: `sorted({confidence_tier(i/100) for i in range(101)})` = `['HIGH','LOW','MID']`) แต่ tier1/tier2_verify เทียบ `tier == 'MEDIUM'` → สาขา `NEEDS_REVIEW` **unreachable** → สินค้า MID (conf 0.7-0.9) ถูกจัดเป็น `UNVERIFIABLE` + risk `HIGH` (over-flag).
- **แก้:** `'MEDIUM'` → `'MID'` (2 จุด). webverify = advisory (golden_master ไม่แตะ) → **golden-neutral**. `'MEDIUM'` ที่ risk_level เป็น label ไม่ใช่ compare (ถูกอยู่แล้ว).
- **test:** `test_adr156_webverify_tier_mid.py` — MID→NEEDS_REVIEW + ไม่มี `== 'MEDIUM'` หลงเหลือ.

### F-C3 — file_info non-dict → run_rules ครัชนอก try (rules_engine:330) — **ตรวจแล้ว = unreachable → ไม่แก้**
- verify (อิสระ): `parse_filename` คืน dict เสมอ + caller เดียวส่ง `b.get('file_info', {})` (default dict). truthy non-dict เข้าไม่ถึง production → **ไม่ปั้น guard ให้โค้ดที่เข้าไม่ถึง** (วินัย reproduce-ก่อนแก้). เป็นขอบเขตที่ต่างจาก guard บิล-data (ADR-124/131/155) โดยเจตนา.

**cluster ที่สะอาด (หลักฐาน):** parse-core-robustness (parser_p0/p1/p2, unit_detection_ext, validators, thai_text/postal, puopuy_dates) = สะอาด → ยืนยันว่า freeze parse-core สมเหตุสมผล. agents-mesh/report, reporting-layer, orchestration-infra = สะอาด (โมดูลเหล่านี้ hardened หนัก มี ADR/try-guard ครบ).

**มุมที่ยังไม่ครอบคลุม:** อ่านเชิง static + reproduce เฉพาะ finding — ไม่ได้ทำ mutation testing เต็มทุกกฎ · coverage-gap เชิงลึกทุก branch ปล่อยให้ CI gate [10] (line≥90 / branch≥85) ดูแลอยู่แล้ว.

---

## 5) Track D — Determinism / Idempotency  ✅ **สะอาด**

**ตรวจอะไร:** ผลตรวจเท่ากันทุกครั้ง ไม่ขึ้นกับลำดับไฟล์/รอบรัน/workload ก่อนหน้า.

**harness:** `_audit_determinism_harness.py` — รันหลายรอบใน process เดียว + สลับลำดับไฟล์ 2 seed + รันหลัง junk-workload:

| เงื่อนไข | ผล |
|----------|-----|
| run1 == run2 (idempotent) | **True** |
| order-independent (seed 1) | **True** |
| order-independent (seed 999) | **True** |
| clean-after-junk-workload | **True** |
| == golden `23b315e8…` | **True** |

**ผล: ✅ สะอาด** — deterministic ครบทุกมิติ (68 กฎรัน). `reset_run_state()` เคลียร์ครบ (รวมหลังยิง junk). memoization ADR-154 ไม่กระทบ (pure cache → ค่าเท่าเดิมข้ามรอบ).

**มุมที่ยังไม่ครอบคลุม:** ไม่ได้ทดสอบ determinism ข้าม Python minor version / ข้าม OS (pin ไว้ 3.12 + PYTHONHASHSEED=0 ตามสเปก).

---

## 6) Track E — Report Integrity  ✅ **สะอาด**

**ตรวจอะไร:** report render ได้ไม่ error + ยอดกระทบยอด (subtotal รวม = ยอดโชว์) + locked format.

**วิธี:** generate `super_ultra_viewer.py` บน corpus จริง (96 บริษัท×เดือน) + รัน **8 locked test** + reconcile ยอดอิสระ (`_audit_report_reconcile.py` ด้วย semantics เดียวกับ viewer เป๊ะ).

**ผล: ✅ สะอาด**
- locked test ผ่านครบ 8: `test_super_ultra_viewer / test_vendor_report / test_report_consistency / test_report_summary_fixes / test_report_c1_c2 / test_report_precision / test_report_lane_aspect / test_report_det`
- **ยอดกระทบยอด:** 96/96 บล็อก — displayed prevat == Σ(subtotal ต่อบิล) เป๊ะ (grand 156,791,263.53 ตรงทั้งสองทาง · 0 mismatch)
- **locked format ครบ:** 1 บริษัท+เดือน = 1 block · ยอด = ก่อน VAT · ใช้คำ **"รีเช็ค"** ไม่ใช่ "แก้" · pinpoint **ไฟล์/เลขเอกสาร** (เช่น "ไฟล์ TSH เลขที่เอกสาร IV680101-76") ไม่ใช่ "(N ใบ)"
- `super_ultra_viewer` ใช้ `makedirs(exist_ok=True)` → ไม่ silent-fail เมื่อไม่มีโฟลเดอร์ output

**หมายเหตุ:** ครั้งแรก harness reconcile ของผู้ตรวจเจอ "3 mismatch" — สืบพบว่าเป็น **บั๊กของ harness เอง** (ใช้ raw tax_id.strip() แทน `clean_tax_id` + ไม่มี fallback `total−vat`) ไม่ใช่บั๊ก report. แก้ harness ให้ตรง semantics viewer → 0 mismatch. (บันทึกไว้เพื่อความโปร่งใส — ไม่ปั้น finding)

**มุมที่ยังไม่ครอบคลุม:** eyeball เชิงตัวเลขบน corpus ปัจจุบัน (96 บล็อก) — ไม่ได้ทดสอบ report บน distribution สุดโต่ง (บริษัทเดียวหมื่นบิล).

---

## 7) Track F — สกัดกฎ 68 ข้อ → ให้ Tor รีวิว  📋

**ผลลัพธ์:** `TRACK_F_RULES_FOR_TOR_REVIEW_TH.md` — ตาราง **68 กฎ** (รหัส | เช็คอะไร | เกณฑ์/ค่าคงที่ | severity | พึ่ง master? | ไฟล์:บรรทัด) สกัดจากโค้ดจริงทุกฟังก์ชัน.

**⚠️ กฎเหล็ก Track F:** AI **สกัดว่ากฎเช็คอะไร** เป็นภาษาคนเท่านั้น — **ไม่ตัดสิน**ว่าถูกกฎหมายภาษีไหม (ทำ authoritative ไม่ได้). **Tor (จบบัญชี) เป็นผู้รีวิว** ว่าตรงกฎหมาย VAT/สรรพากรปัจจุบันหรือไม่. ถ้า Tor ชี้ว่ากฎใดผิด → เป็น finding ที่ต้อง **Tor อนุมัติการแก้** (อาจ rebaseline golden ตั้งใจ).

ค่าคงที่เชิงบัญชีที่ควรให้ Tor ยืนยัน: VAT 7% · VAT tolerance ±0.50 บาท · เลขภาษี 13 หลัก + checksum mod-11 · หัก ณ ที่จ่าย 3% เกณฑ์ 1,000 บาท · fuzzy ชื่อบริษัท ≥ 85.

**หมายเหตุความครบถ้วน:** ตาราง 68 = ทะเบียน RULES ครบ (enabled 63 / disabled 5: DOC002/VAT010/BR003 + 2). กฎ cross-check เพิ่มที่ไม่อยู่ในทะเบียนหลัก (DT005/DT006/IV005/IV006 ผ่าน `_audit_core_crosschecks`) ไม่รวมในตาราง — ระบุไว้เพื่อความโปร่งใส.

---

## 8) POST-CHANGE VERIFICATION

- ✅ golden `23b315e809b6a2d095f2192a68dfc11e789a69b0b8d9f55ed994b70788517301` **ไม่ขยับ** (BILLS=1056 · typos=51)
- ✅ `run_ci.sh ./corpus` = **136 gate เขียว · 0 fail** (133 เดิม + 3 test ใหม่ ADR-154/155/156)
- ✅ test ใหม่ทุกตัวของ 3 fix ผ่าน
- ✅ reachability guard เขียว (ย้าย harness ออกนอก repo แล้ว — ไม่มี floating module)
- ✅ 3 fix แตะเฉพาะ: `rules_engine_rules_c.py` (memoize) · `rules_engine.py` (1 guard) · `webverify.py` (2 compare) + 3 test + run_ci.sh + DECISIONS.md — **ไม่แตะ parse-core logic / กฎเชิงบัญชี / golden**

---

## 9) สิ่งที่ยังไม่ครอบคลุม (บอกตรง ๆ)

1. **synthetic ≠ real distribution** (Track B) — ทดสอบด้วย corpus ซ้ำ ไม่ใช่ 4,000–5,000 บริษัท distinct จริง. รูปทรง O() พิสูจน์ด้วย profile แล้ว แต่ตัวเลข ms เป็นเชิงชี้นำ.
2. **Track F รอ Tor ตัดสิน** — AI สกัดกฎได้ แต่ความถูกต้องเชิงบัญชี/กฎหมายภาษีต้องให้ Tor รีวิว.
3. **ไม่ได้ทำ:** structure-aware byte-fuzzing เชิงลึกของ .xls · mutation testing เต็มทุกกฎ · determinism ข้าม OS/Python version · report บน distribution สุดโต่ง.
4. **ไม่รับประกัน "ปลอดภัย 100%"** — ไม่มี audit ใดพิสูจน์แบบนั้นได้. รายงานนี้ = "ตรวจ 6 track นี้แล้วผลตามข้างบน + เหลือมุมข้อ 1–3 ที่ยังไม่ครอบคลุม".

— จบรายงาน DEEP AUDIT กอง 3 —
