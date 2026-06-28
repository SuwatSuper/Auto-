# CLAUDE.md — กฎ + แผนที่ระบบ "ปุ้มปุ้ย (Puopuy)" · ฉบับล็อก (อายุใช้งาน 5 ปี+)

> ไฟล์นี้คือ **สัญญาเดียว** ที่ Claude Code ทุก session ต้องอ่านก่อนทำสิ่งใด ๆ กับ repo นี้.
> เขียนให้ **คนที่ไม่เคยเห็นระบบนี้** (รวม Claude Code ที่เพิ่งเปิด repo มาเย็น ๆ) อ่านแล้วเข้าใจ + รู้ว่าไฟล์ไหนทำอะไร + ไปหาอะไรที่ไหน.
> ระบบนี้ทำงาน **production จริง** (ตรวจใบกำกับภาษี/VAT ภาษาไทยแบบ offline) ต้องนิ่งยาว ≥5 ปี.
> เจ้าของ = **Tor** (ผู้พัฒนา/ผู้ดูแลคนเดียว). "อนุมัติ" = ข้อความจาก Tor ในเทิร์นนั้นเท่านั้น.

---

## 0 · หลักการสูงสุด (อ่านก่อนทุกอย่าง)

1. **โหมดเริ่มต้น = LOCKED.** ค่าเริ่มต้นของ *ทุก* คำขอคือ **"ไม่แก้"**. หน้าที่หลัก = *หาบั๊ก + รายงาน* ไม่ใช่ *แก้ทันที*.
2. **"ถูกต้อง" ของระบบนี้ = golden hash** — ไม่ใช่ความเห็นของคุณ (Claude), ไม่ใช่ linter, ไม่ใช่ "น่าจะดีกว่า".
3. **ลำดับความสำคัญ (ห้ามสลับ):** `Stability > Reliability > Maintainability > Consistency > Predictability > Scalability > Performance > Features`. **Features = ห้ามเพิ่ม** เว้นแต่ Tor สั่งชัดเจน.
4. **golden ปัจจุบัน (แหล่งจริง = ไฟล์ ไม่ใช่ค่าที่จำ):**
   - corpus  : `23b315e8…`  (= `baseline.json._sha256`, 148 ไฟล์ `/mnt/project`, 1056 บิล)
   - fixture : `ad0c9dad…`  (= `tests/fixtures/baseline_fixture.json._sha256`, 3 บิล)
   - **เชื่อค่าใน `baseline.json` เสมอ ไม่เชื่อเลขที่จำมาจาก session ก่อน.**

---

## 1 · ระบบนี้คืออะไร + แผนที่ (สำหรับ Claude Code ที่เพิ่งเปิดมา ยังไม่รู้จักระบบ)

> repo นี้มี ~150 ไฟล์ .py + 83 เทส + 66 เอกสาร. **อย่าสแกนมั่ว** — ใช้แผนที่นี้ชี้ก่อนว่าควรเปิดไฟล์ไหน.

### 1.1 Pipeline ภาพรวม (end-to-end)
```
ไฟล์ Excel ผู้ขาย (.xls/.xlsx, เซลล์ภาษาไทย)
   │  [file_guard → parser_*]   อ่าน + แกะเป็น "bill objects"
   ▼
bills (list of dict)  ──►  rules_engine (~56 กฎ r_*)  ──►  ติด issues[] ให้แต่ละบิล
   │
   ├─►  golden_master/regression_full ──► hash ผลตรวจ = "23b315e8" (oracle)
   │
   └─►  ชั้นรายงาน (advisory — ไม่กระทบ hash):
          • build_consolidated_report.py → Error Report .xlsx (4 ชีต: ภาพรวม/ต้องแก้/ขึ้นกับ master/ข้อสังเกต)
          • super_ultra_viewer.py        → company_summary .txt + .xlsx (สรุปต่อบริษัท × เดือน)
          • agents/vendor_report*.py      → รายงานผู้ขาย .txt (ภาษาคน ก๊อปส่งลูกค้า)
```
มี **ชั้น agents** (Tier 1–4, Hybrid Hierarchical + Mesh) ห่อเครื่องยนต์เดิมไว้ — **แต่ agent ไม่เปลี่ยนผลตรวจ** (engine==agent พิสูจน์ด้วย `verify_golden.py`). กฎหลักอยู่ที่ engine ไม่ใช่ agent.

### 1.2 Data model — "bill object" (dict) ที่กฎทุกตัวอ่าน
ฟิลด์หลัก: `company`/`company_raw` · `tax_id`/`tax_id_raw` · `branch`/`branch_no` · `iv_number`/`iv_number_raw` · `iv_date` (datetime.date) · `iv_date_str` · `address` · `subtotal`/`vat`/`total` · `sheet` (ชื่อชีต Excel) · `file` · `block_idx` · `items` (list of `{seq,name,name_raw,qty,unit,price,amount}`) · **`issues`** (list of `{code, …}` — ผลตรวจสะสมที่นี่).
กฎข้ามไฟล์ (เช็คเลขเรียง/ซ้ำ) รับ corpus ทั้งหมดผ่าน `ctx['all_bills_for_iv_check']`.

### 1.3 แผนที่โมดูล (ไฟล์ไหนทำอะไร — เปิดตามนี้)
**Entry / orchestration**
- `main.py` → `ปุ้มปุ้ย_ultimate_v9_modular.py` — entry หลัก + public surface
- `agents/orchestrator.py` — DAG runner ของชั้น agents

**Parser (Excel → bills)** — re-export chain, ซอยตามเพดาน ≤600 LOC
- `parser.py` (hub) → `parser_p0.py`/`parser_p0a.py`/`parser_p1.py`/`parser_p2.py` (ชั้นแกะข้อมูล, byte-identical extract)
- `parser_guards.py` — **ปราการรับ input** (กันไฟล์เพี้ยน/last-resort IV) ← จุดหลักของ "ดักบั๊ก input"
- `file_guard.py` — กันไฟล์ untrusted ก่อน parse · `parser_reexport.py` — ตัวช่วย re-export

**Rules engine (~56 กฎ — หัวใจระบบ)** — re-export chain
- `rules_engine.py` (hub) → `rules_engine_base.py` + `rules_engine_rules_a.py` / `_b.py` / `_c.py` (กลุ่มกฎ `r_<CODE>`)
- `code_labels.py` — แปลง 56 รหัส → (field บล็อกบริษัท, คำภาษาคน, **เลน** fix/check/review/note/master)
- `code_registry.py` — แหล่งความจริงเดียวของ "จักรวาลรหัสตรวจ"
- **หากฎตัวไหน:** `grep -rn "def r_<CODE>" rules_engine_rules_*.py` (เช่น DOC001 → `r_doc001`)

**Domain / config / leaf utils**
- `config.py`/`config_base.py` — ค่าคงที่/โดเมน (รวม `REVIEW_CODES`, dict ต่าง ๆ) · `state.py` — runtime state (mutable)
- `core_utils.py` · `master.py` (บริษัทอ้างอิง) · `puopuy_dates.py` (วันที่/งวด IV) · `puopuy_units.py` (หน่วย/Decimal)
- `thai_text.py` (fuzzy-dict typo, category, OCR, formality) · `thai_postal.py` (รหัสไปรษณีย์→จังหวัด) · `unit_detection_ext.py`

**Reports (advisory — golden ต้องไม่ขยับ)**
- `issue_consolidator.py` — รวม findings + จัด **เลน** (`REVIEW_ONLY` derive จาก `code_labels.MAP`) → ป้อน:
- `build_consolidated_report.py` — Error Report .xlsx 4 ชีต · `super_ultra_viewer.py` — company_summary
- `agents/vendor_report*.py` — รายงานผู้ขาย · `reporting.py` / `report_precision.py` — ด่านความแม่นก่อนส่งลูกค้า

**Golden / governance (ตาข่ายนิรภัย)**
- `golden_master.py` — สร้าง snapshot/hash · `golden_snapshot.py` — โครงสร้าง snapshot
- `regression_full.py` — engine+agent+baseline ต้องตรงหมด · `verify_golden.py` — agent==engine · `regression_oracle.py`
- `version_gate.py` — ด่านเวอร์ชัน deps · `make_release.py` — build→extract→verify→ส่ง (ลบ zip ถ้า drift)
- `test_golden_single_source.py` — **doc-sync** (พื้นผิวเอกสารทุกตัวต้องอ้าง hash ปัจจุบัน)
- `INVARIANTS/check_invariants.py` — fixture + pins · **`INVARIANTS/DECISIONS.md` — ADR ledger (append-only, แหล่งประวัติการตัดสินทั้งหมด)**

**Robustness / determinism guards (อย่าถอด)**
- `parallel_audit.py` (parallel==serial) · `parse_canary.py` (parse-rate ร่วง) · `offline_guard.py` (ออฟไลน์ล้วน) · `hashseed_guard.py` (PYTHONHASHSEED=0) · `mesh_contract.py` (สัญญา producer) · `doctor.py` (ตรวจความพร้อมระบบ)

**Agents (ห่อ core ที่พิสูจน์แล้ว)**
- `agents/core_access.py` — ประตูเดียวสู่เครื่องยนต์เดิม · `agents/mesh.py` — blackboard
- Tier-2 ตรวจซ้ำ: `verification_agent.py` + `verification_lenses*.py` (คลังเลนส์) · Tier-3 `synthesis_agent.py` · Tier-4 `super_agent.py`
- advisory: `vat_/taxid_/wht_/formula_/notepad_agent.py` · critical: `import_agent.py`/`report_agent.py`

**Tests** — `test_*.py` (83 ไฟล์) · `tests/fixtures/` (fixture 3 บิล) · `tests/real_cases/` (เคสจริงย่อ) · `conftest.py` · `hooks/pre-commit` (git hook รัน gate) · `.claude/settings.local.json` (ตั้งค่า Claude Code)

### 1.4 เอกสารที่ต้องอ่าน + "จะหา X ที่ไหน"
- **เริ่มจาก:** ไฟล์นี้ (CLAUDE.md) → `GOLDEN.md` (อภิธาน hash) → banner บนสุดของ `INVARIANTS/DECISIONS.md` (สถานะปัจจุบัน)
- **ดัชนีเอกสารทั้งหมด:** `DOCS_INDEX.md` · ปฐมนิเทศ: `README.md`, `อ่านก่อนใช้.md` · วิธีรัน: `QUICKSTART_VSCODE_TH.md`, `MAINTENANCE.md`
- **ต่อเนื่องข้าม session:** `_SESSION_HANDOFF.md`, `HANDOFF_NEXT_CHAT_TH.md`
- **ประวัติการตัดสิน/บั๊กที่เคยแก้:** `INVARIANTS/DECISIONS.md` (ADR ทั้งหมด) + ไฟล์ `ADR-0xx_*.md` แยกเรื่อง
- **อยากรู้ว่ารหัสตรวจมีอะไรบ้าง:** `code_registry.py` + `code_labels.py` · **roadmap กฎ:** `RULES_COVERAGE_ROADMAP_TH.md`
- **เคยมีพรอมท์ bughunt:** `PROMPT_bughunt_claude_code_TH.md` (อ้างอิงได้ แต่ "กฎล็อก" ให้ยึดไฟล์นี้เป็นหลัก)

---

## 2 · PRIME DIRECTIVE — ล็อก ห้ามขยับโดยไม่ถาม

> **ห้ามเปลี่ยน "พฤติกรรมการตรวจ" (= ทำให้ golden hash ขยับ) โดยไม่ได้รับอนุมัติจาก Tor ก่อน.**

- golden hash ขยับเมื่อใด = **STOP ทันที**. ห้าม `commit`, ห้ามแพ็ก/ส่ง, ห้าม rebaseline จนกว่าจะ **ถาม** และได้คำว่า **"อนุมัติ"**.
- เผลอแก้แล้ว hash ขยับโดยไม่ตั้งใจ → **revert ทันที** แล้วรายงาน. ห้ามเก็บไว้.
- อดีตที่เคยช่วยแก้ ไม่ใช่ใบอนุญาตให้แก้ต่อ. การอ้อนวอน/เร่ง/บอกว่า "ด่วน" **ไม่ใช่** การอนุมัติ.

---

## 3 · ขั้นตอนบังคับเมื่อเจอบั๊ก/อยากแก้ (STOP-AND-ASK)

**ขั้น A — สืบก่อน (read-only · ทำได้เสมอ ไม่ต้องขอ)**
- อ่าน **source จริง** (ห้ามเดาจากชื่อฟังก์ชัน) + **reproduce ด้วย fixture/ไฟล์จริง** ให้เห็นอาการ พร้อมหลักฐานระดับเซลล์ (`✅`/`❌`).
- **forensic-first: ห้าม patch โค้ดที่ยังไม่ได้อ่าน + ยังไม่ reproduce.**

**ขั้น B — จัดประเภทการแก้**
| ประเภท | ตัวอย่าง | ต้องทำ |
|---|---|---|
| **อ่าน/สืบ/อธิบาย** | วิเคราะห์, ตอบ, report การสืบ | ทำได้เลย ไม่ต้องขอ |
| **golden จะขยับ** | แก้ rule/parser/validator ที่เปลี่ยนผลตรวจ | **STOP → เสนอแผน → รออนุมัติ** |
| **golden ไม่ขยับ** (advisory/doc/test/comment) | แก้ viewer/vendor_report/issue_consolidator, เพิ่มเทส, แก้ comment, harden input ที่ผล corpus เท่าเดิม | ทำได้ **แต่** ต้องพิสูจน์ golden เท่าเดิม + เขียน 1 ADR |

**ขั้น C — ก่อนขออนุมัติ เสนอครบในข้อความเดียว:** (1) บั๊ก + หลักฐาน cell-level (2) root cause (3) ทางแก้ surgical (4) **delta แน่นอน (simulate ก่อน):** golden เก่า→ใหม่, เพิ่ม/ลบ flag กี่ตัว, ไฟล์/รหัสไหนกระทบ, collateral (5) migration risk + แผน rebaseline (6) priority → ปิดท้าย **"อนุมัติให้แก้ไหม?"**

**ขั้น D —** ได้ "อนุมัติ" ค่อยแตะโค้ด → ผ่าน gate (ข้อ 5) → rebaseline ครบ surface → 1 ADR. **ไม่อนุมัติ/เงียบ = ไม่แตะ** (บันทึก ADR สถานะ `รออนุมัติ` ได้).

---

## 4 · กฎเหล็ก (ห้ามผ่อนทุกข้อ)
- **golden = oracle เดียว.** lint (F821/F405) under-report สำหรับ re-export hub → เชื่อ golden + `run_ci.sh` เสมอ.
- **1 ADR ต่อ 1 การแก้** ใน `INVARIANTS/DECISIONS.md` (append-only — **ห้ามลบ/แก้ ADR เก่า**; hash ในเอกสารอดีต = หลักฐาน).
- **surgical เท่านั้น** — ห้าม rewrite, ห้าม refactor golden-path ที่ไม่จำเป็น, ห้าม "จัดระเบียบ" เผื่ออนาคต.
- **false negative อันตรายกว่า false positive** — **ห้ามปิด flag** (โดยเฉพาะ typo/หน่วย) โดยไม่ได้อนุมัติ **รายคำ** จาก Tor.
- **รายงาน = advisory** — แก้ได้ แต่ golden ต้องไม่ขยับ และ **พิสูจน์ทุกครั้ง** (`golden_master` ก่อน/หลัง).

---

## 5 · คำสั่งยืนยัน (gate — รัน "ก่อนประกาศเสร็จ" ทุกครั้ง)
```bash
# 0) ล้าง bytecode ก่อนเสมอ — .pyc ค้าง = อ่าน hash ผิด (เคยหลอกว่า hash ไม่ขยับ)
find . -name __pycache__ -type d -exec rm -rf {} + ; find . -name '*.pyc' -delete
# determinism env — ตั้งทุกครั้ง (ขาดตัวใด hash เพี้ยน)
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1

python3 regression_full.py . /mnt/project baseline.json   # 1) golden corpus → engine==agent==baseline=23b315e8
python3 INVARIANTS/check_invariants.py                     # 2) fixture ad0c9dad + pins
python3 test_golden_single_source.py                       # 3) doc-sync
bash run_ci.sh /mnt/project                                # 4) เต็ม (ทุกเทส + parallel==serial + canary) ต้อง exit 0
python3 make_release.py <pkg_dir> /mnt/project <out.zip>   # 5) แพ็ก (เฉพาะเมื่อได้รับอนุมัติ release)
```
> ข้อ 1 ไม่ได้ `23b315e8` ตั้งแต่เปิด session = **หยุด แจ้ง Tor ห้ามแก้อะไร** (env/ไฟล์เพี้ยน ต้องสืบก่อน).

---

## 6 · กับดัก (landmines — เคยทำระบบพัง/ข้อมูลหายมาแล้ว · ห้ามแตะ)
- **ห้ามติดตั้ง `pythainlp`** — golden 51 typo มาจาก `CONSTRUCTION_DICT` ไม่ใช่ pythainlp. ติดเมื่อใด hash drift.
- **deps pin ตายตัว ห้าม bump:** `pandas==2.2.2  numpy==2.2.6  xlrd==2.0.1  openpyxl==3.1.5  rapidfuzz==3.10.1` (กระทบ sort/format/dtype/fuzzy). คุมด้วย `version_gate.py`.
- **แตก zip ด้วย Python `zipfile` เท่านั้น** — `unzip` Linux ทำชื่อไทยเพี้ยน.
- **master file kill-safe:** process ถูก kill ทิ้ง **stub** → run ถัดไปสำรอง stub เป็น `.user.bak` ทับ master จริง = ข้อมูลหายถาวร. มี `_file_is_stub()` guard (ดู `master.py`, ADR-039/040/049) — **ห้ามถอด**.
- **portable golden:** `golden_snapshot` ต้อง strip absolute path (ADR-037) — ห้ามฝัง path เครื่องกลับเข้า snapshot.
- **rebaseline ต้องครบทุก surface** ไม่งั้น doc-sync แดง: `baseline.json` · `RETIRED_PREFIXES`/`RETIRED_FIXTURE_PREFIXES` (`test_golden_single_source.py`) · banner+row `DECISIONS.md` · `GOLDEN.md` · `.vscode/{tasks,launch}.json` · `Makefile` · `.github/workflows/ci.yml` · `MAINTENANCE.md` · `QUICKSTART_VSCODE_TH.md` · `_SESSION_HANDOFF.md` · characterization label. ใช้ `test_golden_single_source.py` จับว่าครบ.
- **ไฟล์ >600 LOC** (`parser_p1/p2.py`, `validators.py`, `rules_engine_rules_a.py`) อยู่ใน whitelist พร้อมแผน split รอบ F4 — **ห้าม split เองโดยไม่ได้อนุมัติ** (golden-path + de-star re-export chain เสี่ยงสูง).

---

## 7 · สามเสาที่ต้องคงให้ "ซ่อมได้" แม้ล็อกแล้ว (Tor เน้นย้ำ — เพราะล็อกแล้วแก้ยาก)
> lock = แช่แข็ง **"พฤติกรรมการตรวจ (golden)"** เท่านั้น — **ไม่ใช่** แช่แข็งการกันไฟล์เสีย/การดูแลเครื่อง.

### 7.1 Input Validation — ดักบั๊กจากไฟล์ Excel (ไฟล์ใหม่จะเสียแบบใหม่เสมอ)
- แยก 2 เคสก่อน (forensic-first): **(A) parser ล่ม/อ่านเซลล์ผิด** → harden กันล่ม; ถ้า **golden 148 ไฟล์เท่าเดิม** = **golden-neutral แก้ได้ (พิสูจน์ + 1 ADR)** ← ช่องที่ทำให้ดักบั๊ก input ไม่ตัน. **(B) กฎควรจับ/ไม่ควรจับเพิ่ม** → เปลี่ยนผลตรวจ = **STOP-AND-ASK**.
- บังคับพิสูจน์: หลังเพิ่ม guard รัน `golden_master` → corpus **ต้องได้ `23b315e8` เป๊ะ**. กลไก/แพตเทิร์น: `parser_guards.py` · `file_guard.py` · `log_system_issue()` (กฎ crash → ชีต System Issues ไม่ปนผล) · `_failed_files` (ข้ามไฟล์เสีย ที่เหลือยังครบ) · money-serial guard (ADR-055) · DOC001 guard (ADR-057/058). เทส: `test_input_hardening.py`, `test_parser_negative.py`, `test_bughunt_hardening.py`.

### 7.2 Resource Management — ทรัพยากรเครื่องระยะยาว (รัน 5 ปีไม่ให้เครื่องพัง)
- RAM / memory fragmentation / cache โตไม่จำกัด / temp / master = **เกือบทั้งหมด golden-neutral** (เปลี่ยน "วิธีรัน" ไม่ใช่ "ผลลัพธ์") → **แก้ได้ ไม่ต้องปลดล็อก**.
- **บังคับพิสูจน์ 3 ชั้น** (cache/parallel เคยแอบเปลี่ยน output): (1) `golden_master` เท่าเดิม (2) `verify_parallel`/`parallel_audit` → parallel==serial (3) รัน 2 รอบในโปรเซสเดียวผลเท่ากัน.
- กลไก (อย่าถอด): cache trim + `gc.collect` (v6.2) · kill-safe `_file_is_stub()` · perf canary (`parse_canary.py`/`test_perf_budget.py`).

### 7.3 Environment Locking — ล็อกสภาพแวดล้อม (เสาที่ขยับยากที่สุด · ขยับเมื่อจำเป็นจริงเท่านั้น)
- ทำให้ golden **reproduce ได้ตลอด 5 ปี**. env ไม่นิ่ง = reproduce hash ไม่ได้ = **ตาข่ายนิรภัยพังทั้งระบบ**.
- **Freeze:** Python **3.12** + deps pin (ดูข้อ 6) คุมด้วย `version_gate.py`+`constraints.txt` · determinism env บังคับ · golden portable (ADR-037).
- **เก็บ snapshot ถาวร 1 ชุด** (container/venv freeze) → ปี 2030 rebuild เป๊ะได้. สูตร: `pip install -r requirements.txt -c constraints.txt` บน Python 3.12.
- **ขั้นตอนหนีเมื่อ "ต้อง" เปลี่ยน runtime** (เช่น security patch บังคับ 3.13 / dep EOL) = อันตรายที่สุด: (1) **STOP-AND-ASK** (2) ทำบนสำเนา — rebaseline corpus ใหม่ใต้ runtime ใหม่ + ตรวจ diff ทุกบิลว่าเปลี่ยนเพราะ runtime ไม่ใช่บั๊ก (3) ผ่าน `run_ci.sh` เต็ม + 1 ADR (4) เก็บ snapshot runtime เก่าไว้ย้อน.
- **ปี พ.ศ. ขยายถึง 2056** (ADR-049). **model-independent (หัวใจการล็อก):** gate ไม่ขึ้นกับ Claude เวอร์ชันไหน — ปีที่ 5 ถ้า Claude Code เป็นโมเดลใหม่ ก็ยังต้องผ่าน `run_ci.sh` เหมือนเดิม. **gate เขียว = ปลอดภัย ไม่ว่าใคร/โมเดลไหนแก้.**

---

## 8 · Session start checklist (ทำทุกครั้งที่เปิด Claude Code บน repo นี้)
1. อ่าน **ข้อ 1** (แผนที่) ถ้ายังไม่รู้จักระบบ → แล้วอ่าน `GOLDEN.md` + banner `INVARIANTS/DECISIONS.md`.
2. ยืนยัน baseline (ข้อ 5.0–5.1): ล้าง pycache → `regression_full` → **ต้องได้ `23b315e8`**. ไม่ได้ = **หยุด แจ้ง Tor**.
3. ทำงานโหมด **LOCKED**: อ่าน/สืบได้เสมอ · แก้ที่ขยับ golden = **STOP-AND-ASK** (ข้อ 3).
4. ก่อนพูดว่า "เสร็จ": ผ่าน gate ครบ (ข้อ 5) + (ถ้าแก้) 1 ADR + rebaseline ครบ surface.

---

### สรุป 1 บรรทัด
**อ่าน/สืบได้เสมอ · แก้ที่ทำให้ golden ขยับ = หยุดแล้วถาม Tor ก่อนทุกครั้ง · input-hardening & resource = golden-neutral แก้ได้ · ความจริงอยู่ที่ `baseline.json` + `run_ci.sh` ไม่ใช่ความเห็นของ AI.**
