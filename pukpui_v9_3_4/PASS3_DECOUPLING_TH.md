# พาส 3 — Decoupling & Modular Refactoring (สรุปงานที่ทำ + พิสูจน์แล้ว)

เอกสารนี้สรุปงาน "ผ่าตัด God File" รอบพาส 3 ที่ทำต่อจากพาส 1–2 โดยยึดหลัก
**Golden Master / Characterization Testing** — ทุกก้าวพิสูจน์ว่าเครื่องยนต์ให้ผลลัพธ์
**เหมือนเดิม 100%** ด้วยลายนิ้วมือ SHA256 บนข้อมูลจริง 81 ไฟล์ / 632 บิล

> **Baseline ที่ใช้ค้ำทุกการเปลี่ยนแปลง**
> `SHA256 = 7b60b01fa76438c6fd1db795da6f8b8b9ad62e2a63de6fc1f92a2feb8cf04e5d`
> (BILLS=632 FILES=81 fn_issues=3 dup=1 iv_seq=26 iv_date=0 typos=34 companies=2)
> รันซ้ำได้ด้วย: `PYTHONHASHSEED=0 python3 golden_master.py . out.json /path/to/data`

---

## 1. ผลลัพธ์หลัก: ตัด Circular Dependency จนเป็น DAG แท้

**ปัญหาเดิม (พาส 1–2):** โมดูล `validators` / `analytics` / `reporting` ยังวิ่งกลับไป
`import` ฟังก์ชันจาก `main` (เช่น `from ปุ้มปุ้ย_ultimate_v9_modular import clean_tax_id, ...`)
ทำให้เกิด **วงพึ่งพา (cycle):** `main → {validators, analytics, reporting} → main`
ต้องแก้ด้วย "ลำดับ import ที่เปราะ" + import-gate หลายจุดใน main

**พาส 3 แก้ที่ราก:** ย้าย "ตัวช่วยที่ใช้ร่วม" ลงไปอยู่ใน **leaf module** แล้วให้ทุกโมดูล
import จากต้นทางจริง — ไม่มีใคร import จาก main อีก

```
ก่อน (มี cycle)                         หลังพาส 3 (DAG ไหลทางเดียว)
─────────────────                       ───────────────────────────
        main                                      config · state
       ↗  �‖  ↖   (วนกลับ)                              │
validators analytics reporting          puopuy_core/dates/units · diagnostics · thai_text
       ↖  ‖  ↗                                         │
        main                            core_utils · parser · webverify · master · rules_engine
                                                       │
                                        validators · analytics · reporting
                                                       │
                                                     main  (orchestrator — ไม่มีใคร import)
```

**ยืนยัน:** `grep` หาโมดูลที่ยัง `import ปุ้มปุ้ย_ultimate_v9_modular` → **ว่างเปล่า**
(เหลือเพียง `agents/core_access.py` ที่เรียกผ่าน `importlib` ซึ่งเป็นขอบ orchestration โดยตั้งใจ)

---

## 2. สิ่งที่ทำราย Increment (พิสูจน์ byte-identical ทุกก้าว)

| Inc. | ทำอะไร | ผลต่อ main | byte-identical |
|------|--------|:----------:|:--------------:|
| **3a** | ย้าย `parse_filename` / `merge_continuation_bills` / `_declared_period_from_filename` → `parser.py`; ลบ `_from_main` lazy-proxy hack; **ตัด validators→main** | 1,826 → 1,696 | ✅ |
| **3b** | สร้าง **`core_utils.py`** (leaf) ย้าย `sort_bills_by_date` / `parse_address_input` / `clean_pp20_address`; ย้าย style `thin`/`bottom_only` → `config.py`; **ตัด analytics→main และ reporting→main** | → 1,635 | ✅ + Excel 9 ชีตผ่าน |
| **3c** | สร้าง **`webverify.py`** (leaf) ย้ายชั้นตรวจสอบสินค้าออนไลน์ทั้งหมด (web governor `_WEB_STATE`, cache sqlite, tier1/tier2, `verify_product`, `run_product_verification`) | 1,619 → 1,346 | ✅ |
| **3d** | สร้าง **`master.py`** ย้ายชั้นข้อมูลหลักบริษัท (`input_master_data`/`load`/`save`/`parse_master_blob`/`validate_master_entry`) | 1,346 → 1,188 | ✅ |
| **3e** | ย้าย analytics ตัวคำนวณบริสุทธิ์ (`load_audit_excel`/`cluster_*`/`detect_price_outliers`/`detect_unit_anomalies`) → `analytics.py` (`run_analytics` ที่ใช้ HTML capture คงไว้ใน main) | 1,188 → ~1,078 | ✅ |
| **3f** | ย้าย `check_filename_consistency` + `check_duplicate_items` → `validators.py` | → ~1,050 | ✅ (golden path) |
| **3g** | ย้าย `get_files_via_upload`/`get_files_via_drive` → `parser.py` (ชั้นค้นไฟล์) | → **1,027** | ✅ |

ทุก Increment: ลบ import-gate ที่ไม่จำเป็นออกจาก main, เพิ่ม `from <module> import *` (re-export)
เพื่อรักษา public API ที่ `golden_master` / `agents` พึ่ง — จึงไม่กระทบของเดิม

---

## 3. ตาราง LOC ปัจจุบัน (เทียบเป้าหมาย)

| โมดูล | บทบาท | LOC ปัจจุบัน | เป้าหมาย |
|-------|-------|:-----------:|:--------:|
| `ปุ้มปุ้ย_ultimate_v9_modular.py` | **Orchestrator** (core เหลือ orchestration แท้) | **1,027** | 200–300 |
| `parser.py` | Data Extraction + file discovery | 1,661 | ~1,800 |
| `rules_engine.py` | Audit Logic (56 กฎ) | 1,560 | ~2,100 |
| `reporting.py` | Excel report | 1,468 | — |
| `config.py` | ค่าคงที่/regex/สไตล์ | 690 | — |
| `analytics.py` | confidence + post-hoc analytics (cluster/outlier) | 760 | — |
| `validators.py` | cross-bill / sequence / duplicate / filename | 527 | — |
| `webverify.py` 🆕 | online verification (leaf) | 318 | — |
| `thai_text.py` | Thai NLP (leaf) | 221 | — |
| `master.py` 🆕 | master-data (leaf) | 183 | — |
| `puopuy_core.py` | core helpers (leaf) | 101 | — |
| `diagnostics.py` | system logger (leaf) | 99 | — |
| `core_utils.py` 🆕 | shared helpers (leaf) | 79 | ~800* |
| `puopuy_dates.py` / `puopuy_units.py` / `state.py` | leaves | 79 / 46 / 40 | — |

\* เป้า ~800 ของ `core_utils` อิงภาพประเมินเดิม — ของจริงตัวช่วยที่ใช้ร่วมกระชับกว่า
(บางส่วนแยกไป `puopuy_core/dates/units` แล้ว) จะโตขึ้นเมื่อดูดตัวช่วยที่เหลือจาก main เพิ่ม
จะ **ไม่ปั่นบรรทัดเทียม** เพื่อให้ครบ 800

**God File: 4,951 → 1,027 บรรทัด** (ลดลง ~79%) — พาส 1–2 → 1,826; พาส 3a–3g → 1,027

---

## 4. งานที่เหลือ (roadmap ต่อ)

**สถานะ:** การ์ดที่ระบุไว้ในพาส 3 รอบนี้ทำครบแล้ว (analytics/duplicate/filename/getfiles ย้ายแล้ว)
สิ่งที่ยังเหลือใน main คือ **orchestration แท้** ที่เชื่อมหลายเลเยอร์ (จึงควรอยู่ที่ orchestrator):
`parse_all_files` (parser→validators→analytics), `run_all_rules` (rules_engine→analytics),
`run_analytics` (ใช้ HTML capture), `run_self_check`, `reset_run_state`, `print_audit_banner`, `main()`

> ⚠️ **ทำไม main ยัง 1,027 ไม่ใช่ 300:** จากการวัดจริง main แบ่งเป็น
> **header 558 บรรทัด** (dependency-lock banner + LOCK CHECK + display/HTML fallback + re-export
> facade 11 `import *` + P-DAG markers) · **orchestration helpers ~252** · **`main()` ~216**
> การย้ายฟังก์ชันที่เหลือเข้า leaf ใด ๆ จะสร้าง coupling ผิดทิศ/วนกลับ (เช่น `run_all_rules`
> เรียก `build_unit_index` ที่อยู่ใน analytics → rules_engine ต้องพึ่ง analytics) จึงไม่ทำ

**เส้นทางจริงสู่ main ~300–400 (พาส 3-final / คาบเกี่ยวพาส 5) — ทำได้แต่เป็นชุดใหญ่ ต้องพิสูจน์ทีละก้าว:**
1. **`bootstrap.py`** — ย้าย dependency-lock banner + LOCK CHECK (โค้ด print/ตรวจเวอร์ชัน ~150–200 บรรทัด,
   ไม่ใช่ business logic, ไม่อยู่ใน golden path) ออกเป็นฟังก์ชัน ให้ main เรียกครั้งเดียว
2. **`htmlout.py`** (leaf) — ย้ายกลไก display/HTML/`_CAPTURED_HTML` (~30 บรรทัด) ให้ main + pipeline
   ใช้ list capture ตัวเดียวกัน (แก้ปม coupling ของ `run_analytics`/`reset_run_state`)
3. **`pipeline.py`** — ย้าย stage functions (`parse_all_files`/`run_all_rules`/`run_analytics`/`run_self_check`)
   เป็นโมดูล orchestration ที่อยู่ "ใต้ main เหนือ leaf" (import parser/validators/rules/analytics ได้
   โดยไม่วน) → main เหลือเป็น "ผู้คุมงาน" เรียก pipeline ตามคิว
4. **ถอด re-export facade** — แก้ `golden_master.py` + `agents/core_access.py` ให้ import จาก leaf
   โดยตรง (แทน `app.X`) เพื่อให้ main ไม่ต้องเป็น facade อีก → ลบ 11 `from X import *`

หลังครบ 4 ข้อ main ≈ `main()` (216) + reset/banner (~40) + import เฉพาะที่ main ใช้ (~60) ≈ **~320**
(ถ้าต้องการต่ำกว่านี้ ต้องหั่น `main()` เองเป็น sub-steps ใน pipeline เพิ่ม)

**พาส 4 — AI ให้แม่นขึ้น (advisory layer):** ต่อยอด `agents/ai_review_agent.py` ที่มีอยู่

**พาส 5 — regression เต็ม + เอกสาร + ส่งมอบ:** รัน `golden_master` + `verify_golden` (agent path)
+ `test_agents` ครบ, ปิดเอกสาร, แพ็กส่ง

---


## 5. วิธีพิสูจน์ว่ายังเหมือนเดิม (รันเองได้)

```bash
# เครื่องยนต์เดิม (ทางตรง)
PYTHONHASHSEED=0 python3 golden_master.py . out.json /path/to/data   # ต้องได้ 7b60b01f...

# สายการผลิตแบบ agent (พิสูจน์ว่า agent ก็ให้ผลเดิม)
PYTHONHASHSEED=0 python3 verify_golden.py . baseline.json /path/to/data

# พฤติกรรมเชิงสถาปัตยกรรม (isolation / degrade / สร้าง Excel จริง)
PYTHONHASHSEED=0 python3 test_agents.py . /path/to/data
```

**กฎเหล็กของการ refactor นี้:** ไม่แตะ business logic — ย้ายโค้ดแบบ verbatim เท่านั้น,
ทุกการย้ายต้องผ่าน golden_master ก่อนถือว่าเสร็จ
