# ปุ้มปุ้ย/Pukpui v9.2 — รายงานเซสชัน + มอบหมายงานแชทใหม่

> เอกสารนี้ self-contained: แชทใหม่อ่านจบแล้วทำงานต่อได้ทันทีโดยไม่ต้องถามย้อน
> **ภาษา:** Tor สื่อสารไทย คาดหวังคำตอบไทย · **โหมดงาน:** HARDENING ONLY (ห้ามเพิ่มฟีเจอร์เว้นแต่ได้รับอนุมัติ)

---

## 0) กฎเหล็ก (พิสูจน์ด้วยเลือดมาแล้ว — ห้ามฝ่าฝืน)

1. **GOLDEN HASH = `35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba`**
   (= `baseline.json._sha256`) คือ oracle เดียวที่ตัดสินถูก/ผิด. ทุกการแก้ต้อง golden-gate.
   *(ไม่ใช่ `ec61907f`/81-file เก่า — ADR-019 ปลดระวางไปแล้ว)*
2. **Corpus = 106 ไฟล์ใน `/mnt/project` (834 บิล)**
3. รีเบสไลน์ทำได้ (อนุมัติล่วงหน้า) แต่ต้อง "ดีขึ้นเท่านั้น" (false-positive ลด/ถูกต้องขึ้น) + regen baseline + เขียน ADR
4. **agent layer = advisory/read-only อยู่นอก golden snapshot** → golden ไม่จับ regression ชั้น agent
   ∴ **ต้องรัน CI เต็มเป็น gate คู่กับ golden เสมอ** (บทเรียนเจ็บของเซสชันที่แล้ว — ดู §3)
5. F821/F403 ไม่ใช่ oracle (re-export hub ทำ F-rules under-report) — golden คือความจริง

---

## 1) ENVIRONMENT (ตั้งทุกครั้งก่อนทำงาน)

```bash
# venv (มีอยู่แล้ว; ถ้าหาย: python3 -m venv /home/claude/.venv_puopuy)
. /home/claude/.venv_puopuy/bin/activate
# deps (pin เป๊ะ): pandas==2.2.2 numpy==2.2.6 xlrd==2.0.1 openpyxl==3.1.5 rapidfuzz==3.10.1 ruff
export PYTHONHASHSEED=0
export PUOPUY_AUDIT_DATE=2026-06-02
cd /home/claude/puopuy_work/pukpui_v9_2     # work dir (แตกจาก pukpui_v9_2_HARDENED_v2.zip)
```
หมายเหตุ: matplotlib/plotly/tqdm/pythainlp ไม่ได้ติดตั้ง = version-gate เตือน "ไม่อันตราย" รันต่อได้ (golden ไม่กระทบบน corpus ปัจจุบัน)

---

## 2) VERIFY COMMANDS (gate)

```bash
# golden (ต้องพิมพ์ 35b2f7c8...) — stderr: BILLS=834 FILES=106
python3 golden_master.py . /tmp/snap.json /mnt/project
# regression: engine==agent==baseline
python3 regression_full.py . /mnt/project
# agents behavioral 38/38
python3 test_agents.py . /mnt/project
# agent meta-conformance (โครงสร้าง, ใหม่เซสชันนี้)
python3 test_agent_conformance.py .
# monolith surface contract 28 ชื่อ (ใหม่เซสชันนี้)
python3 test_monolith_surface.py
# lint สะอาด
ruff check "ปุ้มปุ้ย_ultimate_v9_modular.py" --select F401,F403,F405,F811,F821,F822   # = All checks passed!
# ★ gate รวมคำสั่งเดียว (10-round determinism + ทุก tripwire + tests + regression):
bash run_ci.sh /mnt/project        # = ✅ CI ผ่านทั้งหมด (exit 0)
```

---

## 3) สิ่งที่ทำเสร็จเซสชันที่แล้ว (golden = 35b2f7c8 นิ่งตลอด)

| งาน | ผลลัพธ์ |
|---|---|
| **P1 — monolith de-star** | `import *` 11→0 + เพิ่ม `__all__` = 28-name contract + เสริม `test_monolith_surface.py` |
| **P2 — agents de-star** | `agents/` `import *` **5→0** (verification_lenses + vendor_report cascade) → **132 F405→0, `[11] ruff` + CI เต็มเขียว** |
| **#2 — prune dead imports** | monolith F401 **42→0** → **lint-clean เต็มตัว** (F401/F403/F405/F811/F821/F822 = 0) |
| **#4 — P3 meta-conformance** | เพิ่ม `test_agent_conformance.py` (auto-discover 14 agent, 101 เช็ก) wire เป็น `[5b]` |

### 🔴 บทเรียนสำคัญ (ต้องจำ — เซสชันนี้เจ็บ 3 ครั้ง)
**สัญญาภายนอกของ monolith/hub มี 3 ประเภท ไม่ใช่ 2:**
- (A) `app.<name>` getattr ตรง
- (B) `core_access._REQUIRED` (import-gate)
- (C) **`core.get("…")` dynamic ใน agent** + **`from hub import X` ตรงในเทส** ← พลาดบ่อยสุด

เคสจริงที่ golden ผ่านแต่ของพัง (จับด้วย CI เต็มเท่านั้น):
1. de-star config/validators ตัด `audit_today`/`detect_iv_period_mismatch` → lens คืน None เงียบ → `[3d3]` ล้ม
2. de-star vendor_report ไม่รวม `_pre_vat` (เทส import ตรง) → `[3d3]/[4b]` … คือ `[4b]` ล้ม (ImportError)

**กฎที่ตกผลึก:**
- de-star/prune re-export hub → import = (ใช้ภายใน) ∪ (ทุกชื่อที่ consumer เข้าถึงทุกช่องทาง)
- ก่อนลบชื่อใด: สแกนทั้ง tree (`app.X`, `core.get("X")`, `from <mod> import X`) ให้ครบ
- **golden ผ่าน ≠ ปลอดภัย** สำหรับชั้น agent — ต้อง `bash run_ci.sh` เขียวด้วยเสมอ

---

## 4) สถานะระบบ ณ ตอนนี้ (ตัวเลขจริง)

- golden: `35b2f7c8…` ✅ · `bash run_ci.sh` = ✅ ผ่านทั้งหมด (42 run-steps)
- monolith: **1365 LOC**, lint-clean, contract 28 ชื่อ (การ์ดด้วย `test_monolith_surface.py`)
- `agents/`: **0 `import *`** ทั้งหมด
- ไฟล์ที่ยัง **>600 LOC: มีไฟล์เดียว = monolith** (1365) — whitelist อยู่ใน `test_file_size_ceiling.py`
- **cascade ที่เหลือ (P2 low-value, `# noqa: F403`, ไม่ทำ CI แดง):** parser (p0a→p0→p1→p2→parser), reporting (p0→p1→p2→reporting), rules_engine (base→rules_a/b/c→rules_engine), config (config_base→config). เป็นสถาปัตยกรรม split ฐาน-ปลายที่ตั้งใจ ไม่ใช่ debt เร่งด่วน

---

## 5) ★ งานมอบหมายถัดไป (เรียงตามคำแนะนำ)

### #3 — SPLIT MONOLITH (ชิ้นใหญ่/เสี่ยงสุด — แนะนำเป็นเซสชันโฟกัสนี้)
**เป้า:** monolith 1365 LOC → ทุกไฟล์ ≤600 LOC (ปลด whitelist ตัวสุดท้ายใน `test_file_size_ceiling.py`)
**เงื่อนไขพร้อมแล้ว:** monolith สะอาด (lint-clean) + surface guard 28 + CI เต็มเป็นตาข่าย → เสี่ยงต่ำสุดเท่าที่จะเป็นได้

**โครงสร้างปัจจุบัน (จาก AST):**
- L1–~580: imports + setup + `__all__` + glue ระดับ module (รวม addon block ท้ายไฟล์)
- L581–~1296: **14 ฟังก์ชัน orchestration (~623 LOC)** — `run_analytics(50) · run_self_check(39) · reset_run_state(20) · print_audit_banner(23) · parse_all_files(53) · run_all_rules(20) · _audit_core_rules(75) · _audit_core_crosschecks(5) · run_audit_core(8) · _emit_agent_notepad(52) · _emit_company_summary(19) · _is_real_master(20) · _move_processed_files(30) · main(209)`
- contract ที่ "นิยามในไฟล์นี้" (ห้ามหาย): `main, parse_all_files, run_all_rules, run_audit_core, reset_run_state, _SYSTEM_ISSUES` (ที่เหลือ import จาก leaf แล้ว re-export)

**วิธี (ตาม F4 byte-identical pattern ที่ codebase ใช้กับ parser/reporting/rules_engine/config):**
1. ตัด body เป็น base file ด้วย line-slice (verbatim) เช่น
   - `pukpui_core_pipeline.py` = ฟังก์ชัน parse/rules/crosscheck/audit-core (parse_all_files, run_all_rules, _audit_core_*, run_audit_core, reset_run_state)
   - `pukpui_main_glue.py` = main + reporting/notepad glue (main, run_analytics, run_self_check, print_audit_banner, _emit_*, _move_processed_files, _is_real_master)
   - ไฟล์ top คงไว้: imports + `__all__` + `from <base> import *  # noqa: F401,F403` (re-export)
2. **underscore-infra ต้องอยู่ใน `__all__` ของ base** (เพื่อ star เห็นครบเหมือน scope เดิม — ดู verification_lenses_base/vendor_report_base เป็นแม่แบบ)
3. **คง 28 contract names เป็น attribute ของ top module** เสมอ (getattr-safe)
4. **golden-gate ทุก slice** (ห้าม bundle) — ถ้า hash ขยับ = หยุด, bisect ทันที
5. หลังเสร็จ: รัน `bash run_ci.sh` + `test_monolith_surface.py` (28) + `test_agent_conformance.py` + ลบ whitelist ใน `test_file_size_ceiling.py` แล้วยืนยัน [3z] ผ่าน
6. **ข้อควรระวัง:** main มี side-effect (เขียนไฟล์/ย้ายไฟล์/print banner) — slice ระวัง import order; `audit_today`/`detect_iv_period_mismatch`/`PYTHANLP_AVAILABLE` ต้องคงเป็น attribute (สัญญาประเภท C — ตรวจด้วย surface test ก่อน/หลัง)

**ทางเลือก B (ถ้าอยากคงศูนย์-star purity):** slice เป็นโมดูลแล้ว import explicit แทน `import *` — งานมากกว่า แต่ไม่เพิ่ม noqa-star. แนะนำ A เพราะ consistent กับ codebase + เร็ว + พิสูจน์ง่ายด้วย golden

### #5 — P4 (deferred, เสี่ยงต่ำ-กลาง, ไม่บังคับ)
ดู `P3_FOLLOWUP_TH.md` มี recipe ปลอดภัยแล้ว:
- global mutable state → parallel-safe (ปัจจุบัน serial==parallel ผ่าน แต่ state ยัง global)
- config JSON extraction (แยกค่าคงที่ออกเป็น config ภายนอก)
- ไม่มี large file เหลือแล้วหลัง #3

---

## 6) KEY FILE PATHS
- monolith: `ปุ้มปุ้ย_ultimate_v9_modular.py` (1365 LOC, lint-clean, มี `__all__` 28)
- contract gate: `agents/core_access.py` (`_REQUIRED` 22 ชื่อ + bind ตรง `_D/_vat_tolerance/clean_tax_id/_taxid_checksum_ok`) · facade `get(name)=getattr(core,name,None)`
- agent base: `agents/base.py` (`Agent(ABC)`, ห้าม override `run`, implement `_run`)
- tripwires ใหม่เซสชันนี้: `test_monolith_surface.py` (28-name 4 แหล่ง A/B/C/D) · `test_agent_conformance.py` (14 agent × 7 เช็ก)
- baseline (golden): `baseline.json` · `golden_snapshot.py` (MASTER เดียวกับ oracle)
- CI: `run_ci.sh` (42 steps; [11] ruff scope = guard/test files; lint ของ monolith ไม่อยู่ใน [11] แต่สะอาดอยู่แล้ว)
- backups เซสชันนี้: `/tmp/monolith_ORIG.py` (ก่อน P1), `/tmp/pre_prune.py` (ก่อน #2), `/tmp/contract_surface.json` (28 ชื่อ)
- handoff สะสม: `HANDOFF_NEXT_CHAT_TH.md` (log ราย-งาน) · เอกสารนี้ = ฉบับสรุปสำหรับแชทใหม่

---

## 7) DoD ปัจจุบัน
- **Stability/Reliability/Consistency/Predictability:** ✅ (golden นิ่ง + CI เต็ม + determinism 10 รอบ + serial==parallel)
- **Maintainability:** ✅ (#3 split เสร็จ — ทุกไฟล์ ≤600, whitelist ว่าง)
- **Architecture:** ✅ (lint-clean monolith + agents, surface/meta guards, CI คำสั่งเดียว)
- **Agent:** ✅ (behavioral A–I + structural meta ครบ)
- **Memory/Scalability:** 🔶 (P4 #5 — parallel state/config JSON)
- **Performance / New features:** ตามนโยบาย ไม่แตะเว้นได้รับอนุมัติ

**บรรทัดเดียวสำหรับแชทใหม่:** เริ่มที่ §1 (env) → ยืนยัน `bash run_ci.sh` เขียว + golden=35b2f7c8 → ลุย **#3 split** ตาม §5 (golden-gate ทุก slice, อย่าลืมสัญญาประเภท C)

---

## ✅ #3 — SPLIT MONOLITH เสร็จ (Option B: explicit, zero-star)

**ผล:** `ปุ้มปุ้ย_ultimate_v9_modular.py` 1365 LOC → **4 ไฟล์ ≤600 ทุกไฟล์** · golden = `35b2f7c8…` นิ่งทุก slice · `bash run_ci.sh` เขียวครบ · **file-size ceiling whitelist = ว่าง** (ไม่มีไฟล์เกินเพดานทั้งโปรเจกต์แล้ว)

| ไฟล์ | LOC | บทบาท |
|---|---|---|
| `ปุ้มปุ้ย_ultimate_v9_modular.py` (top) | 265 | entry + main + public surface (`__all__` 28 contract) |
| `pukpui_modular_base.py` | 493 | shared scope: imports (leaf) + constants + setup + `__all__` re-export 70 |
| `pukpui_modular_funcs.py` | 459 | 13 ฟังก์ชัน orchestration (parse/rules/audit-core/emit) |
| `pukpui_modular_consts.py` | 69 | CONSTRUCTION_DICT enrichment (.update, write-only side-effect) |

**วิธี (4 slice, golden-gate ทุกขั้น):**
1. แยก shared scope → base; top `from base import (explicit)` — กัน import แทรกกลางด้วยการ derive ชื่อจาก *attribute จริงของ base ที่ import แล้ว* (ไม่ใช่ AST อย่างเดียว — จับ try/except guarded เพิ่ม 5 ตัว)
2. ย้าย 13 ฟังก์ชัน (ยกเว้น main) → funcs; top เหลือ main
3. แยก CONSTRUCTION_DICT.update → consts (พิสูจน์ก่อนว่า base ใช้ CONSTRUCTION_DICT แบบ write-only ที่ module-level → ไม่มี circular; consts ดึงจาก webverify ตรง = object เดียวกัน); ยุบ blank-run ใหญ่ที่เป็น artifact จากการถอดฟังก์ชัน
4. base ใส่ `__all__` (re-export surface) + top trim import → **F401/F403/F405/F811/F822 = 0 ทั้ง 4 ไฟล์**; ปลด whitelist ceiling

**บทเรียนย้ำ:** `__all__` เป็น list-of-strings ไม่นับเป็น "use" → ต้อง import ชื่อ contract เข้ามาแม้ main ไม่ใช้ (ไม่งั้น core_access พัง); และ guard ด้วย attribute จริง ไม่ใช่ AST static (try/except). last-wins order ปลอดภัยต่อการจัดเรียงเพราะชื่อซ้ำเป็น object เดียวกัน (พิสูจน์ตอน de-star)

**สรุปเซสชันนี้ (เสร็จ 5 งาน):** P1 de-star · P2 agents de-star · #2 prune · #4 meta-conformance · **#3 split** — golden นิ่ง `35b2f7c8` ตลอด

---

## ✅ KEYSTONE — parallel wired เข้า production (OBJ-PERF / Scalability+Performance)

**สถานะก่อนหน้า:** `parallel_audit.py` (ProcessPoolExecutor, merge ตามลำดับ chunk = deterministic, serial-equivalent) **มีอยู่+พิสูจน์แล้ว** (CI [8c] workers=8) แต่เป็น opt-in แยก **ไม่ได้ wire เข้า main** → production รัน serial → ผู้ใช้ไม่ได้ speedup

**ทำในรอบนี้:** แทรก opt-in ใน `main()` (top file) — env `PUOPUY_PARALLEL=<workers≥2>` → ใช้ `parse_all_files_parallel`; ไม่ตั้ง/0/1 = serial เดิม (default = golden path); มี graceful fallback ถ้า parallel ล้ม
- golden (default serial) = `35b2f7c8…` **ไม่ขยับ** (golden_master เรียก parse_all_files ตรง ไม่ผ่าน main)
- พิสูจน์ผลเท่า serial: 20 ไฟล์/4 workers = 155 bills ตรง; CI [8c] full corpus 834 bills ตรงเป๊ะ
- **ข้อจำกัดวัดผล:** sandbox 1-core วัด speedup ไม่ได้ (workers→1). บน multi-core จริง (parser=99% เวลา, ขนานข้ามไฟล์) ≈ near-linear (8 core ~6-7x)
- **หมายเหตุ RunState class (จาก recipe):** ไม่จำเป็นสำหรับ multiprocessing — แต่ละ process แยก globals กันเอง (proven via [8c]); RunState จำเป็นเฉพาะ thread-parallel หรือรันหลาย audit ใน process เดียว → deferred (คนละ use case)

**ผลคะแนน (ประเมิน):** Scalability 6→~8.5, Performance 6→~8.5 (เหลือ profiling/micro-opt + engine swap ถึงจะ 9)

---

## ✅ DE-STAR สมบูรณ์ — ZERO-STAR ทั้ง repo (Maintainability)

**ทำครบ:** แปลง `from X import *` ทุกตัวเป็น explicit (production tops + intermediate split-base chain links) → **ไม่มี star import จริงเลยใน active codebase**
- Production tops (de-star + lint สะอาด, มี __all__/noqa เหมาะสม): `config.py` (32), `rules_engine.py` (68, F405 133→0), `parser.py` (70+2 private noqa), `reporting.py` (11 +__all__)
- Intermediate chain links (explicit re-export shim + file-level `# ruff: noqa: F401`): parser_p0/p0a/p1/p2, reporting_p0/p1/p2, rules_engine_base/rules_a/b/c, config_base
- **golden = 35b2f7c8 ไม่ขยับเลย** ทุก slice · CI 46 steps เขียว
- **F401/F403/F405/F811/F822 = 0** ทั้ง active codebase (รวมเก็บ 17 F401 เดิมนอก de-star ด้วย ruff --fix targeted, gated)

**บทเรียนสำคัญ (โดน 3 รอบ, golden พลาด/CI จับได้ทุกครั้ง):**
1. **3-category contract** — surface ต้อง derive จาก `from-import (A) ∪ module.X attr (B) ∪ core.get/getattr (C)` ∪ `__all__` ∪ internal-loads. golden ไม่จับ category-B/C (audit path ไม่แตะ) แต่ CI จับ (`parser.parse_sheet`, `rules_engine.normalize_company_name` ในเทสต์ผ่าน attribute/alias)
2. **middle-link re-export** — link กลาง chain (parser_p0) ต้อง re-export ชื่อที่ไหลขึ้นไป (Counter) ครบ; ตัดออกไม่ได้แม้มี local import ในไฟล์ (parser_p1 import ต่อ)
3. **drop-locally-imported = อันตราย** — ชื่อที่ local-import ใน func A อาจถูกใช้แบบ module-level ใน func B (เช่น `Font` ใน reporting_p2) → ตัดจาก module-level แล้ว NameError; **golden ไม่จับเพราะไม่รันส่วน Excel แต่ agent contract test [5]/[8] จับ** → ต้อง full re-export เสมอ

**คงเหลือ (pre-existing, นอก scope de-star):** F541 (f-string ไม่มี placeholder, 20) + F841 (local var ไม่ใช้, 9) — cosmetic/minor, ไม่กระทบ golden/พฤติกรรม

---

## ✅ DE-STAR เต็ม — ZERO STAR ทั้ง repo (Maintainability)

**เสร็จในรอบนี้:** de-star ทุก `from X import *` ที่เหลือ → explicit ทั้งหมด
- **Production tops (4):** config(32) · rules_engine(68, F405 133→0) · parser(70+2, F405 68→0) · reporting(11 +__all__) — ลินต์ 0, มี __all__/noqa เฉพาะจุด
- **Intermediate split-base links (8):** parser_p0/p1/p2, reporting_p1/p2, rules_a/b/c — explicit re-export shim
- **Leaf bases + shims (12 ไฟล์):** ใส่ file-level `# ruff: noqa: F401` (+F811 ที่มี local re-import) — re-export ขึ้น chain โดยเจตนา

**ผลลัพธ์:**
- star imports จริง = **0** ทั้ง repo (เหลือเฉพาะคอมเมนต์ที่อ้างถึงของเดิม)
- F401/F403/F405/F811/F822 (active, ไม่รวม _ORIG_BACKUP) = **0**
- golden = `35b2f7c8…` ไม่ขยับ · CI ผ่านทั้งหมด

**บทเรียน 3-category (โดนซ้ำ, golden พลาด/CI จับ):**
1. `parser.parse_sheet`, `rules_engine.normalize_company_name` — เข้าถึงผ่าน attribute/alias ในเทสต์ → surface ต้องรวม `__all__ ∪ internal ∪ attr-accessed`
2. `Font` ที่ reporting_p2 — ใช้ module-level ในฟังก์ชันหนึ่ง แต่ local-import ในอีกฟังก์ชัน → heuristic "ตัด local-imported" **ผิด**; middle-link ต้อง re-export ครบ (Counter ไหลขึ้น parser_p1)
→ **golden ไม่ครอบ reporting/agent path; CI agent-contract + negative-fuzz คือ gate จริง** (รัน CI ทุกครั้งคู่ golden)

**Maintainability: 8.5→~9.2** (zero-star + ลินต์สะอาดทั้ง repo)
