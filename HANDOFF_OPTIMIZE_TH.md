# 🤝 HANDOFF — ปุ้มปุ้ย v9.2 → รอบ OPTIMIZE (ส่งมอบให้แชทใหม่)

> อ่านไฟล์นี้ก่อนเริ่มทุกครั้ง. งานต่อไป = **OPTIMIZE** (performance + maintainability) โดย
> **ห้ามทำให้ stability/golden ถอยหลัง**. ลำดับความสำคัญคงเดิม:
> 1.Stability 2.Reliability 3.Maintainability 4.Consistency 5.Predictability 6.Scalability 7.Performance.
> Performance อยู่ "ท้ายๆ" โดยเจตนา — เร็วขึ้นแต่ผลตรวจเพี้ยน = ล้มเหลว.

---

## 0. สถานะปัจจุบัน (verified — อย่าเชื่อความจำ เชื่อตัวเลขนี้)

- **branch:** `claude/focused-lovelace-otUNP`
- **golden hashes (แหล่งความจริง = `baseline.json._sha256`; สรุปทุกค่าใน `GOLDEN.md`):**
  - `35b2f7c8…` = golden จริง **106 ไฟล์/834 บิล** (Python 3.12) ← baseline เดียวที่นับ
  - `d8bcde85…` = fixture 3 บิล (ใช้ dev ได้ ไม่ใช่หลักฐานรับรอง)
  - `ec61907f…` = corpus ย่อย 81 ไฟล์ · `fff69fc6…` = report hash
- **เขียวยืนยันแล้ว (บน sandbox Python 3.11 + `PUOPUY_ALLOW_VERSION_MISMATCH=1`):**
  run_ci.sh **53 ด่าน** · pytest **48 passed** · coverage line **≥90%** · fixture golden ไม่ขยับ
- **ขนาด:** ~19,025 LOC (py non-test) · 47 test files · CI 52 `run` steps
- **คะแนนรวม ~8.5/10** (Test/Safety 9.5, Stability/Reliability/Security 9.0, **Maintainability 7.0, Performance 7.5** ← เป้า optimize)

### ⚠ sandbox limitation (สำคัญที่สุด)
แชทนี้/สภาพแวดล้อม CI **ไม่มี `/mnt/project` (106 ไฟล์จริง) และเป็น Python 3.11 ไม่ใช่ 3.12**
→ hash-gate ที่รันได้จริง = **fixture `d8bcde85`** เท่านั้น. ทุกงานที่อาจกระทบ golden ต้องปิดท้าย
ด้วย **`⚠ NEEDS_REAL_DATA_CERT`** + คำสั่งให้เจ้าของรันบนเครื่องจริง (ดู §5).

---

## 1. กฎเหล็ก (พกไปทุกขั้น — ละเมิด = งานเป็นโมฆะ)

- **[R1] FORENSIC-FIRST** — อ่าน source/ข้อมูลจริงก่อน อ้าง `file:line` เป็นหลักฐาน ห้ามเดา
- **[R2] NO FLOATING MODULES** — โค้ดใหม่ต้องมี call site จริงจาก entrypoint
  (`ปุ้มปุ้ย_ultimate_v9_modular`/`main`/`run_agents`). `test_reachability.py` บังคับใน CI แล้ว
- **[R3] HASH-GATE** — วัด golden ก่อน/หลังทุกการเปลี่ยน บน **106 ไฟล์จริง** ผ่าน entry จริง
  ห้าม rebaseline บน fixture / ห้าม rebaseline แบบไม่มี before-after
- **[R4] CERTIFICATION-COMPLETE** — fixture-only **ไม่นับว่าเสร็จ**. งานเสร็จเมื่อ certify บน 106 ไฟล์
  (= `35b2f7c8` หรือ hash ใหม่ documented พร้อมเหตุผล) **หรือ** ติดบล็อก `⚠ NEEDS_REAL_DATA_CERT`
- **WORKFLOW:** DIAGNOSE → DECIDE GATE → FIX (incremental ทีละจุด) → VERIFY (golden+CI) → CERT
- **OUTPUT ต่อข้อเสนอ:** Current risk / Root cause (file:line) / Long-term impact / Solution /
  Migration risk / Priority / **Hash expectation** / **Cert status**

### 🛡 PRESERVE — ของดีที่ "ห้ามถอด" ระหว่าง optimize
`version_gate.enforce(exit_on_fail=True)` · `hashseed_guard` (re-exec PYTHONHASHSEED=0) ·
numpy ใน version_gate · `golden_master` ที่ hash *data structure* (ไม่ใช่ report ที่มี timestamp) +
`isolate=True` · guards ทั้งหมด (reachability/report-det/reset/package/merged-cell/code-table/field-codes/
golden-single-source) · advisory layer (ultra_agent/lenses/vendor_report) = **READ-ONLY**

---

## 2. 🎯 OPTIMIZE BACKLOG (เรียงตามลำดับที่ควรทำ)

### OPT-0 ★ ต้องทำก่อนเพื่อนเลย — REAL-DATA CERT (ปลดล็อกทุกอย่าง)
ถ้ายังไม่ certify บน 106 ไฟล์ → ทุก optimize ต่อจากนี้ "วัด before/after ไม่ได้" = ทำ R3 ไม่ได้.
**รัน §5 ให้ครบก่อน** ยืนยัน baseline = `35b2f7c8` แล้วค่อยเริ่ม optimize (จะได้มี "before" จริง).

### OPT-1 PERFORMANCE — parser hot path (Hash: **ต้องไม่ขยับ** = byte-identical)
- **Current (PERF_BASELINE.md, วัดจริง):** `parse_all_files` ~17.6s/836 บิล = **88% ของเวลา**.
  hot spots: `parser_p2.parse_sheet` ~13.5s · `parser_p0.detect_item_columns` ~4.3s ·
  **`parser_p0a._dic_int_run` 16,553 calls / ~3.9s** (สแกนรันตัวเลขต่อเซลล์ — เป้าอันดับ 1)
- **Root cause:** per-cell Python loop ใน `_dic_*` (parser_p0a) + materialize/แปลงซ้ำ.
- **Approach (ห้ามเปลี่ยนผลลัพธ์):** vectorize/cache เฉพาะ hot loop (เช่น `_dic_int_run`,
  `_dic_item_rows`, `_dic_collect_numeric`) ให้ **คืนค่าเท่าเดิมเป๊ะทุก path** — optimize เชิงกลไก
  ไม่ใช่เชิงตรรกะ. ทำทีละฟังก์ชัน + วัด golden ทุกครั้ง.
- **Hash expectation:** **ห้ามขยับ** (ถ้าขยับ = เปลี่ยนพฤติกรรม ไม่ใช่ optimize → หยุด ย้อน).
- **Gate:** `verify_parallel.py` มีอยู่แล้วเทียบ serial==parallel; เพิ่มวินัย "serial-เดิม == serial-optimized"
  ด้วย golden hash 106 ไฟล์. **Cert: NEEDS_REAL_DATA_CERT (35b2f7c8 ก่อน==หลัง).**
- **Priority: สูง** (ดัน Performance 7.5→ ; parser คือ 88% ของเวลา)

### OPT-2 MAINTAINABILITY — [F3] re-export chain เปราะ (Hash: ไม่ขยับ)
- **Current (file:line):** chain `parser_p0a → parser_p0 → parser_p1 → parser_p2 → parser.py(__all__)`
  ทำ explicit re-export โยงสัญลักษณ์ข้ามชั้น. **B2 พิสูจน์ความเปราะ:** ลบ 1 ฟังก์ชันใน parser_p0
  → ImportError ทันทีจาก parser_p1:9/parser_p2:10 (ต้องแก้ 6+ จุดประสานกัน).
- **Long-term impact:** เพิ่ม/ลบ/ย้ายฟังก์ชัน parser มี blast radius สูง = บั๊กง่าย = ราก "งอกบั๊ก".
- **Approach (DECIDE GATE ก่อน):** ออปชัน (ก) แทน explicit list ด้วย `__all__`-driven re-export
  ที่ derive อัตโนมัติ ; (ข) รวม parser_p0a/p0/p1/p2 กลับเป็นโมดูลเดียวที่จัดระเบียบ (เสี่ยง coverage/
  file-size gate ≤600 LOC) ; (ค) ปล่อย chain ไว้แต่เพิ่ม guard ที่ assert chain integrity.
  **ต้องเสนอ options+tradeoffs ขออนุมัติก่อนแตะ** (นี่คือ core parser — golden ผูกอยู่).
- **Hash expectation:** **ต้องไม่ขยับ** (เป็นการจัดระเบียบ import ไม่ใช่ logic). **Cert: NEEDS_REAL_DATA_CERT.**
- **Priority: กลาง** (ดัน Maintainability 7.0→ ; แต่เสี่ยงสูง ทำหลัง OPT-1 พิสูจน์ cert workflow แล้ว)
- **พ่วง B2:** เมื่อ chain ถูกจัดระเบียบแล้ว ค่อย retire `detect_item_columns_safe`/`_compute_col_confidence`
  (parser_p0.py:83,54 — dead additive, ดู P3_FOLLOWUP §6 B2) ได้ปลอดภัย.

### OPT-3 SCALABILITY — report styling รายเซลล์ (Hash: report อาจขยับ — ระวัง)
- **Current:** `reporting_p2.build_clean_report` ใส่ style ต่อเซลล์ (โน้ตใน docstring: พอสำหรับหลักพัน-หมื่น
  บิล; หลายแสนบิลจะช้า/แรมโต).
- **Approach:** ตามที่โน้ตไว้แล้ว — (1) แบ่งไฟล์ตามงวด/บริษัท (ไม่แตะ builder, ปลอดสุด) →
  (2) xlsxwriter constant_memory → (3) batch styling. **ทุกออปชันต้องผ่าน `verify_report_det.py`
  (report hash) + ดูหน้าตารายงานด้วยตา** (style ไม่ครอบใน hash).
- **Hash expectation:** audit golden **ไม่ขยับ** ; report hash `fff69fc6` **อาจขยับ** ถ้าเปลี่ยน builder →
  ต้อง re-verify + documented. **Cert: NEEDS_REAL_DATA_CERT (report-det 106 ไฟล์).**
- **Priority: ต่ำ** (ทำเมื่อปริมาณจริงแตะหลายแสนบิล — ตอนนี้ ~3000 บิล/วัน สบาย)

### OPT-4 CONSISTENCY — รวม 3 taxonomy รายงาน (Hash: report อาจขยับ)
- **Current:** `code_labels.MAP` / `config.FIELD_CODES` / `vendor_report_base.FIELD_LAYOUT` ใช้กลุ่มต่างกัน
  (มี guard `test_code_tables_consistency` กัน drift แล้ว แต่ยังเป็น 3 ตาราง).
- **Approach:** derive ทั้งสามจาก `code_registry.py` (single source) — **แต่ taxonomy ต่างกันจริง**
  (DOC002/VAT008 จัดกลุ่มไม่ตรงข้ามตาราง) → การ derive จะเปลี่ยน layout = report hash ขยับ.
- **Decision ปัจจุบัน:** guard พอแล้ว (drift จับได้). ทำเมื่อมีเวลา + ยอม re-verify report hash.
- **Priority: ต่ำ** · **Hash:** report อาจขยับ → **Cert: NEEDS_REAL_DATA_CERT.**

### OPT-5 CI/INFRA (Hash: ไม่ขยับ)
- pre-commit hook ต้อง `install_hooks.sh` เอง → พิจารณา bootstrap อัตโนมัติใน doctor/setup
- golden cert ใน CI = fixture-only (เพราะไม่มี 106 ไฟล์ใน CI) → คงสภาพ; เพิ่ม README ว่า real cert
  ต้องทำนอก CI · `verify_parallel`/`parse_canary(real)` ยัง gated หลังข้อมูลจริง

### DEFERRED (อย่าแตะจนมีหลักฐาน — ดู P3_FOLLOWUP §5/§6)
- **C2 lens consensus +2/-1** — advisory; แตะเมื่อ (ก) ใช้ verdict ตัดสินจริง (ข) เห็นป้ายหลอกจริง
- **C1 Excel serial** — NO-FIX (การขยายช่วงจะ "อันตราย" = รับ spurious date-type cell)
- **merged-cell handler** — ทำเฉพาะถ้า `diagnose_merged_cells.py <106 ไฟล์>` ขึ้น 🚩 จริง

---

## 3. แผนที่ระบบ (ที่ต้องรู้ก่อน optimize)

```
entrypoints: ปุ้มปุ้ย_ultimate_v9_modular.py (หลัก) · main.py (ASCII shim) · run_agents.py (CLI ไม่โต้ตอบ)
audit core (golden-locked, ลำดับศักดิ์สิทธิ์): run_audit_core() — เรียกที่เดียว, read-only ทุก agent
parser (hot path): parser_p0a (ฐาน _dic_*) → parser_p0 → parser_p1 → parser_p2 → parser.py
rules: rules_engine(+_base/_rules_a..c) · validators.py
reporting: reporting_p0..p2 (clean report) · super_ultra_viewer/ultra_agent/vendor_report (advisory R/O)
agents: agents/ (orchestrator + 4 tier; dynamic load ผ่าน __init__:_LAZY)
safety-net: golden_master/golden_snapshot/verify_golden/regression_full/version_gate/coverage_gate
  + guards: test_reachability/report_det/reset_completeness/package_integrity/code_tables_consistency
single-source: baseline.json (golden) · code_registry.py (รหัส) · GOLDEN.md (อภิธาน hash) · agents/_shared.TIER1
```

---

## 4. คำสั่ง dev บน sandbox (Python 3.11 — ต้องใส่ override)
```bash
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_ALLOW_VERSION_MISMATCH=1
python3 golden_master.py . /tmp/g.json tests/fixtures   # fixture golden → ต้อง d8bcde85
bash run_ci.sh            # 53 ด่าน (standalone)
python3 -m pytest         # 48 passed (subprocess collector)
python3 test_reachability.py   # ไม่มี floating
```

## 5. ⚠ NEEDS_REAL_DATA_CERT — เจ้าของรันบน Python 3.12 + 106 ไฟล์จริง (ปิดวงจร)
```bash
# baseline ก่อน optimize (ต้องได้ 35b2f7c8 ทั้ง 3 บรรทัด — นี่คือ "before" ของ OPT-1/2)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . <106 ไฟล์>
# หลัง optimize แต่ละจุด: รันซ้ำ → ต้องได้ 35b2f7c8 เท่าเดิม (ถ้าต่าง = optimize เปลี่ยนพฤติกรรม → หยุด)
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_parallel.py <106 ไฟล์> 8   # serial==parallel
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 verify_report_det.py <106 ไฟล์>   # report fff69fc6
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 diagnose_merged_cells.py <106 ไฟล์>  # iv_date ครบ
```

## 6. กับดัก (traps ที่เคยเจอจริง)
1. **golden archive UTF-8:** `git archive` ทำชื่อไฟล์ไทยพังตอน unzip → **ใช้ `bash package.sh` เท่านั้น**
   (มี guard `test_package_integrity`). โมดูลหลัก `ปุ้มปุ้ย_ultimate_v9_modular.py` เป็นชื่อไทย.
2. **[F3] re-export chain:** ลบ/ย้ายสัญลักษณ์ใน parser_p0 → ต้องแก้ parser_p1/p2/parser.py `__all__` พร้อมกัน
   (ไม่งั้น ImportError ทั้ง chain).
3. **PRODUCT_MASTER:** `test_rules_extra.py:330` rebind → อย่าให้ reset_run_state reload (จะทับ rebind).
4. **fixture ≠ golden:** d8bcde85 (3 บิล) ผ่านไม่ได้แปลว่า 35b2f7c8 (106 ไฟล์) ผ่าน — ต้อง cert จริง.
5. **report hash ≠ audit hash:** เปลี่ยน builder กระทบ `fff69fc6` ไม่กระทบ `35b2f7c8` (คนละชั้น).

---

> **เริ่มงานแชทใหม่:** อ่าน §0-1 → รัน §4 ยืนยันเขียว → เลือก OPT (แนะนำ OPT-0 cert ก่อน แล้ว OPT-1 perf) →
> ทำตาม WORKFLOW + ติด Hash/Cert status ทุกชิ้น. ดูบันทึกการตัดสินใจเดิมที่ `P3_FOLLOWUP_TH.md §5/§6`.
