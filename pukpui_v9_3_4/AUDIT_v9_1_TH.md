# รายงานตรวจสอบสถาปัตยกรรม & ปรับปรุงโครงสร้าง — ปุ้มปุ้ย v9.1

> **บทบาทผู้จัดทำ:** Principal Software Architect / Production Reliability Engineer / Code Auditor / Long-Term Maintenance Specialist
> **ภารกิจ:** ยกระดับ *ความเสถียร / เชื่อถือได้ / บำรุงรักษาง่าย / สม่ำเสมอ / คาดเดาได้* ของระบบเดิม — **ไม่เพิ่มฟีเจอร์**
> **เป้าสถาปัตยกรรม:** Hyper **Hybrid Hierarchical + Mesh** (เสริมแกนเดิม ไม่รื้อ)

---

## 0. สรุปผู้บริหาร (อ่าน 60 วินาที)

ระบบนี้ผ่านการ hardening มาดี (P1–P5) และมีสถาปัตยกรรมสองระนาบที่สะอาดอยู่แล้ว
(control plane = `orchestrator`, data plane = `mesh`). การตรวจรอบนี้พบว่า **ความเสี่ยงที่สูงที่สุด
ไม่ใช่ "บั๊กการคำนวณ" แต่เป็น "โครงสร้างที่เปราะต่อการบำรุงรักษา"** — โดยเฉพาะการที่ "ลำดับศักดิ์สิทธิ์
ของการตรวจ" ถูกคัดลอกด้วยมือไว้หลายที่ ซึ่งจะทำให้ผลตรวจของสองเส้นทาง (engine / agent) เพี้ยน
*เงียบ ๆ* ในอนาคต.

**ทำไปแล้ว 4 อย่าง (พิสูจน์ว่าปลอดภัยด้วย golden hash ทั้งสองชุด):**

| รหัส | สิ่งที่แก้ | ชนิด |
|------|-----------|------|
| A+B | รวม "ลำดับศักดิ์สิทธิ์" เป็น **แหล่งความจริงเดียว** `run_audit_core()` (engine/agent/golden เรียกตัวเดียวกัน) + เส้น agent ได้ error-isolation เท่า engine | refactor (พฤติกรรมคงเดิม) |
| C | รวม `MASTER` + `canonical()` + โครง snapshot/hash เป็นไฟล์เดียว `golden_snapshot.py` | refactor |
| C-ext | ยุบ `MASTER` ที่ก๊อปไว้ 4 ที่ → เหลือ 1 | refactor |
| Portability | `e2e_test.py` เลิก hardcode `/home/claude` → ใช้โฟลเดอร์สคริปต์ (เดิมพังบน Windows) | bugfix |

**ผลพิสูจน์ (หลังแก้ทั้งหมด):**

```
ด่าน CI (fixture)         : gate ✅  smoke 27/27 ✅  pinned ✅  mesh 16/16 ✅  agents 37/37 ✅
regression (fixture)      : engine == agent == baseline   hash d8bcde85… ✅  (ไม่เปลี่ยน)
regression (จริง 81 ไฟล์)  : engine == agent == baseline   hash ec61907f… ✅  (ไม่เปลี่ยน)
e2e_test (รันจาก cwd อื่น) : 632 บิล + Excel 9 ชีต ✅       (เดิมรันได้เฉพาะเครื่อง dev)
```

> **หัวใจของความปลอดภัย:** ทุกการแก้ในรอบนี้ถูกตรวจด้วย **golden master 2 ชุด** (`ec61907f` ข้อมูลจริง,
> `d8bcde85` fixture). ถ้า byte ใดของผลตรวจเปลี่ยน hash จะเปลี่ยนทันที. hash ทั้งสอง **ไม่ขยับเลย**
> = พฤติกรรม/ผลตรวจ "เหมือนเดิมเป๊ะทุก field".

---

## 1. ลำดับความสำคัญที่ยึดถือ (ตามที่กำหนด)

```
1. Stability    2. Reliability   3. Maintainability   4. Consistency
5. Predictability   6. Scalability   7. Performance   8. New Features (ห้าม เว้นได้รับอนุญาต)
```

ก่อนเสนอ "ฟีเจอร์ใหม่" ตรวจตามลำดับ: ปรับปรุงของเดิมได้ไหม → refactor ได้ไหม → ปรับสถาปัตยกรรมได้ไหม
→ ปรับ validation ได้ไหม. **รอบนี้ไม่มีฟีเจอร์ใหม่แม้แต่อย่างเดียว** — มีแต่ refactor + bugfix ที่พฤติกรรมคงเดิม.

---

## 2. baseline ที่ยืนยันก่อนแตะโค้ด (จุดอ้างอิงถอยกลับ)

| ด่าน | คำสั่ง | ผลก่อนแก้ |
|------|--------|-----------|
| smoke | `python smoke_test.py` | 27/27 ✅ |
| agents (จริง) | `python test_agents.py . /mnt/project` | 38/38 ✅ |
| regression (จริง) | `python regression_full.py . /mnt/project` | `ec61907f` engine==agent==baseline ✅ |
| CI (fixture) | `bash run_ci.sh` | 6 ด่านผ่าน, `d8bcde85` ✅ |

> ทุกคำสั่งตั้ง `PYTHONHASHSEED=0` (+ `PUOPUY_AUDIT_DATE=2026-06-02` สำหรับกฎวันที่) เพื่อให้ hash reproduce ได้.

---

## 3. ตารางสรุป Findings

| # | หมวด | ระดับ | สถานะ | หัวข้อ |
|---|------|-------|-------|--------|
| **A** | Maintainability | 🔴 P1 | ✅ แก้แล้ว | "ลำดับศักดิ์สิทธิ์" ก๊อป 3 ที่ + docstring อ้างเลขบรรทัดที่ไม่มีจริง |
| **B** | Reliability | 🔴 P1 | ✅ แก้แล้ว | error-isolation ไม่สมมาตร (agent ล้ม, engine รอด) |
| **C** | Maintainability | 🟠 P2 | ✅ แก้แล้ว | `MASTER`/`canonical`/snapshot ก๊อปข้าม golden_master ↔ verify_golden |
| **G** | Portability | 🟠 P2 | ✅ แก้แล้ว | `e2e_test.py` hardcode `/home/claude` |
| **D** | Maintainability | 🟡 P3 | 📋 แนะนำ | DRY: `_parse_llm_json`×3 (ดริฟต์), `_num`×3, `_max_sev`×2 |
| **E** | Reliability | 🟢 P4 | 📋 แนะนำ | silent swallow ตกแต่งกราฟ/สีแท็บ 3 จุด + bookkeeping 5 จุด |
| **F** | Architecture/Scalability | 🟠 P2 | 📋 แนะนำ | ไฟล์ใหญ่: parser 1642 / rules_engine 1559 / reporting 1496 บรรทัด |

---

## 4. รายละเอียด Findings ที่ "แก้แล้ว"

### 🔴 Finding A — "ลำดับศักดิ์สิทธิ์" ถูกคัดลอกด้วยมือ 3 ที่  ·  [แก้แล้ว]

- **ความเสี่ยงปัจจุบัน (Current risk):** ลำดับการตรวจหลัก (dup → rules → IV-seq/date → typos →
  summary → crosscheck) ถูกเขียนซ้ำใน **3 ไฟล์**: `main()`, `agents/orchestrator._run_audit_core()`,
  และ `golden_master.py`. การ sync อาศัย "วินัยการก๊อปให้ตรง" ล้วน ๆ. ยิ่งกว่านั้น docstring ของ
  orchestrator อ้างเลขบรรทัด `main() 4782–4844` ซึ่ง **ไม่มีอยู่จริง** (ไฟล์หลักเหลือ 1020 บรรทัดหลัง
  modularize) → คู่มืออ้างอิงล้าสมัยไปแล้ว.
- **ต้นเหตุ (Root cause):** ตอน modularize จากสคริปต์ก้อนเดียว ไม่มีการ "ดึงลำดับแกน" ออกเป็นฟังก์ชัน
  สาธารณะให้ทุกเส้นเรียกร่วม. แต่ละ entry point จึงถือสำเนาลำดับของตัวเอง.
- **ผลกระทบระยะยาว (Long-term impact):** วันหนึ่งมีคนเพิ่ม/สลับขั้นตรวจใน `main()` แต่ลืม
  `orchestrator` (หรือกลับกัน) → "สองสมอง" คิดไม่ตรงกัน → ผล Excel ของเส้น production (agent)
  ต่างจากเส้นพิสูจน์ (engine) → golden hash ดริฟต์ **เงียบ ๆ** จนกว่าจะมีคนรัน regression. นี่คือ
  ความเสี่ยง "ระเบิดเวลา" ที่อันตรายที่สุดต่อผู้ดูแล 10 ปี.
- **วิธีแก้ที่ใช้ (Recommended solution → done):** ดึงลำดับเป็น **แหล่งความจริงเดียว** ในเครื่องยนต์หลัก
  แบ่ง 2 เฟสให้ตรงโครงสร้าง `main()` (มีการแสดงผลคั่นกลาง):
  - `_audit_core_rules(all_bills, master, isolate=True, log=None)` — dup→rules→iv/typos/summary
  - `_audit_core_crosschecks(all_bills)` — apply_iv_period + apply_sheet_date
  - `run_audit_core(...)` = สองเฟสติดกัน (สำหรับเส้นไม่มี display คั่น)
  จากนั้น `main()` / `orchestrator._run_audit_core` / `golden_master` **เรียกตัวเดียวกันหมด**.
  ข้อความ console ของ `main` วิ่งผ่าน `log=print` → พิมพ์เหมือนเดิมทุกบรรทัด; เส้น agent/golden เงียบเหมือนเดิม.
- **ความเสี่ยงการย้าย (Migration risk):** **ต่ำมาก.** เป็น extract-method ล้วน. พิสูจน์แล้วว่า
  ทั้ง `ec61907f` และ `d8bcde85` ไม่เปลี่ยน + `main` ยังพิมพ์ข้อความ PATCH4B + ผล field-by-field ตรง baseline.
- **ระดับความสำคัญ (Priority):** 🔴 P1 (สูงสุด — กันผลตรวจเพี้ยนเงียบ).

### 🔴 Finding B — error-isolation ไม่สมมาตรระหว่างสองเส้น  ·  [แก้แล้ว]

- **ความเสี่ยงปัจจุบัน:** เส้น engine (`main`) ห่อ `check_invoice_sequence/typos/summary` ด้วย
  `try/except` + log `SYS003` → ถ้าพังก็ degrade (รายงานส่วนที่เหลือยังออก). แต่เส้น agent
  (`orchestrator._run_audit_core` เดิม) **ไม่มี try/except** → ขั้นใดขั้นหนึ่งโยน exception = ทั้ง
  pipeline ล้ม.
- **ต้นเหตุ:** สำเนาลำดับฝั่ง agent ถูกเขียนแบบ "ตรงไปตรงมา" โดยไม่ลอกชั้น isolation (P1-FIX-ISOLATION)
  ที่ `main` มี.
- **ผลกระทบระยะยาว:** เส้นที่ใช้ใน production จริง (agent/orchestrator) **ทนทานน้อยกว่า** เครื่องยนต์
  ที่มันควรจะสะท้อนเป๊ะ. ข้อมูลลูกค้าแปลก ๆ (เช่นชีตผิดรูป) ที่ `main` ย่อยได้ กลับทำเส้น agent ล้มทั้งงาน.
- **วิธีแก้ที่ใช้:** เนื่องจากแก้ Finding A ด้วยฟังก์ชันร่วม `_audit_core_rules(isolate=True)` ชั้น
  isolation จึงอยู่ในที่เดียวและ **ทั้งสองเส้นได้เท่ากันอัตโนมัติ**. semantics ตรงกับ `main` เป๊ะ (ถ้า
  IV-seq หรือ IV-date ตัวใดพัง → ทั้งคู่เป็น list ว่าง เหมือน `main`).
- **ความเสี่ยงการย้าย:** **ต่ำมาก.** บนข้อมูล golden ทุกขั้นไม่โยน → ผล/hash เท่าเดิม. ผลของการแก้คือ
  "เพิ่มความทน" เฉพาะตอนเจอข้อมูลเสีย (เส้นทางที่ปกติไม่เกิด).
- **ระดับความสำคัญ:** 🔴 P1.

### 🟠 Finding C — `MASTER`/`canonical`/snapshot ก๊อปข้ามเครื่องมือพิสูจน์  ·  [แก้แล้ว]

- **ความเสี่ยงปัจจุบัน:** `golden_master.py` (เส้น engine) และ `verify_golden.py` (เส้น agent) ต่าง
  ก๊อป **3 อย่าง**: (1) `MASTER` ทดสอบ (2) `canonical()` (3) โครง snapshot + วิธี hash. คอมเมนต์ในโค้ด
  เองยอมรับว่า *"คัดลอกจาก golden_master เป๊ะ — ต้องเหมือนกัน hash ถึงเทียบได้"*.
- **ต้นเหตุ:** สองสคริปต์ถูกเขียนแยกกันโดยไม่มีโมดูลกลางสำหรับ "นิยามการ hash".
- **ผลกระทบระยะยาว:** ถ้าวันหน้าอัป `MASTER` หรือปรับ `canonical` ฝั่งเดียว → hash ของสองเส้นจะ
  *เทียบกันไม่ได้* → `verify_golden` รายงาน "ไม่ตรง" ทั้งที่โค้ดถูก (**false mismatch** ทำ CI แดงโดยไม่มีบั๊กจริง)
  หรือแย่กว่า: ทั้งคู่ผิดเหมือนกันแล้ว "ผ่าน" หลอก ๆ.
- **วิธีแก้ที่ใช้:** สร้าง `golden_snapshot.py` รวม `MASTER`, `canonical()`, `build_snapshot()`,
  `hash_snapshot()`, `snapshot_and_hash()`, `write_master_file()`. ทั้งสองสคริปต์ `import` ชุดเดียวกัน
  → ตรงกันโดยโครงสร้าง ไม่ใช่ด้วยการก๊อป.
- **ความเสี่ยงการย้าย:** **ต่ำ.** เนื้อโค้ดที่ดึงออกเป็นชุดเดิมเป๊ะ. ทั้งสอง hash ไม่เปลี่ยน.
- **ระดับความสำคัญ:** 🟠 P2.

### 🟠 Finding G — `e2e_test.py` hardcode path `/home/claude`  ·  [แก้แล้ว]

- **ความเสี่ยงปัจจุบัน:** บรรทัด `sys.path.insert(0,'/home/claude')` + `os.chdir('/home/claude')`
  ตรึงไว้กับเครื่อง dev เดิม → รันบน Windows ของผู้ใช้ (`C:\Users\...`) **ไม่ได้เลย** (ImportError/FileNotFound).
- **ต้นเหตุ:** เขียน path สมบูรณ์แบบฮาร์ดโค้ดตอน prototype.
- **ผลกระทบระยะยาว:** เครื่องมือ E2E ใช้ตรวจรับงานไม่ได้นอกเครื่อง dev → ทีมหลุดการทดสอบสำคัญ.
- **วิธีแก้ที่ใช้:** ใช้ `_HERE = os.path.dirname(os.path.abspath(__file__))` แทน → ย้ายไปไหนก็รันได้
  (พิสูจน์: รันจาก `/tmp` ผ่าน 632 บิล + Excel 9 ชีต). พ่วงดึง `MASTER` จาก `golden_snapshot`.
- **ความเสี่ยงการย้าย:** **ต่ำ.** ไฟล์นี้ไม่อยู่ในด่าน CI (ไม่กระทบ gate). พฤติกรรมเดิมบนเครื่อง dev คงอยู่.
- **ระดับความสำคัญ:** 🟠 P2 (บั๊กพกพา — กระทบความสามารถทดสอบ).

---

## 5. รายละเอียด Findings ที่ "แนะนำให้ทำต่อ" (ยังไม่แตะ — เพื่อคุมความเสี่ยง)

### 🟡 Finding D — โค้ดซ้ำในชั้น advisory (LLM/helper)

- **ความเสี่ยงปัจจุบัน:** `_parse_llm_json` นิยามใน 3 agent (`ai_review`, `super`, `synthesis`) และ
  **ดริฟต์ไม่ตรงกันแล้ว**; `_num` ซ้ำ 3 ที่; `_max_sev` ซ้ำ 2 ที่.
- **ต้นเหตุ:** helper เล็ก ๆ ถูกก๊อปตอนเพิ่ม agent ทีละตัว.
- **ผลกระทบระยะยาว:** แก้บั๊กการ parse JSON จาก LLM ที่หนึ่ง อีกสองที่ยังพังเหมือนเดิม → พฤติกรรม
  ไม่สม่ำเสมอข้าม agent.
- **วิธีแก้ที่แนะนำ:** ย้าย `_parse_llm_json` → `agents/llm_provider.py` (มีอยู่แล้ว), ย้าย `_num`/`_max_sev`
  → `agents/base.py` เป็น helper ร่วม. แก้ทีละตัว + รัน `test_agents.py` หลังแต่ละก้าว.
- **ความเสี่ยงการย้าย:** **ต่ำ-กลาง.** เป็น advisory ล้วน (ไม่กระทบ golden hash) แต่ต้องระวัง 3 สำเนา
  ที่ดริฟต์ — ต้องเลือก "เวอร์ชันที่ถูกต้องที่สุด" เป็นตัวกลาง แล้วทดสอบว่า output ของ Ai/super/synthesis
  ไม่เปลี่ยนเชิงโครงสร้าง (มี `test_agents` ครอบ degrade/skip อยู่แล้ว).
- **ระดับความสำคัญ:** 🟡 P3.

### 🟢 Finding E — silent swallow ที่เหลือ

- **ความเสี่ยงปัจจุบัน:** `reporting.py` มี `except Exception: pass` 3 จุดรอบการ **ตกแต่งกราฟ/สีแท็บ**
  (openpyxl chart fill, tab color) และ `parser.py` มี broad-swallow ~5 จุดในงาน bookkeeping (เคลียร์ state,
  ต่อ audit-log, print วินิจฉัย, ปิด workbook). หมายเหตุ: handler จับ float ใน parser (`ValueError,TypeError`)
  พร้อม fallback **ไม่ใช่บั๊ก** — ถูกต้องแล้ว ไม่ต้องแตะ.
- **ต้นเหตุ:** ป้องกันแบบกว้างเกินจำเป็นในเส้นที่ "พังก็ไม่ควรล้มงาน".
- **ผลกระทบระยะยาว:** ต่ำ — จุดเหล่านี้ถ้าพังก็แค่กราฟไม่มีสี/ไม่มี log ตกแต่ง (รายงานยังครบถูกต้อง).
  ความเสี่ยงเดียวคือ "ซ่อนสัญญาณ" ของบั๊กที่ไม่คาด.
- **วิธีแก้ที่แนะนำ:** เปลี่ยน `pass` → เขียน `stderr` สั้น ๆ (แบบเดียวกับที่ `agents/contracts.record()`
  ทำกับ mesh.publish แล้ว) เพื่อให้ "ไม่กลืนเงียบ" แต่ยังไม่ล้ม pipeline. ไม่ต้องแคบ exception (จุดเหล่านี้
  ตั้งใจกว้างเพราะ best-effort).
- **ความเสี่ยงการย้าย:** **ต่ำมาก** (เพิ่ม log เฉย ๆ) แต่ **ระวัง:** การพิมพ์ stderr ใน hot-path ต่อเซลล์
  อาจรบกวน performance/log noise — ทำเฉพาะจุดที่ไม่ใช่ per-cell loop.
- **ระดับความสำคัญ:** 🟢 P4 (สุขอนามัยโค้ด).

### 🟠 Finding F — ไฟล์ monolithic (Scalability/Maintainability)

- **ความเสี่ยงปัจจุบัน:** `parser.py` 1642, `rules_engine.py` 1559, `reporting.py` 1496 บรรทัด.
  ไฟล์ใหญ่ทำให้ navigate/review/test ยาก และเพิ่มโอกาส merge conflict.
- **ต้นเหตุ:** ระบบโตจากสคริปต์ก้อนเดียว; การ modularize ทำในระดับ "แยกหน้าที่หยาบ" แล้วแต่ยังไม่ย่อย
  ไฟล์ใหญ่.
- **ผลกระทบระยะยาว:** ต้นทุนการบำรุงรักษาสูงขึ้นเรื่อย ๆ; ผู้ดูแลใหม่ใช้เวลาเข้าใจนาน; การเพิ่มกฎเสี่ยง
  กระทบส่วนอื่นในไฟล์เดียวกัน.
- **วิธีแก้ที่แนะนำ (ทำเป็น "เฟส" มี gate):**
  - `rules_engine.py` → แยกเป็นแพ็กเกจ `rules/` ตามหมวด (เช่น `rules/vat.py`, `rules/taxid.py`,
    `rules/date.py`, `rules/item.py`) โดยคง `RULES` registry เป็นจุดรวม (กฎอ้างด้วยรหัสเดิม).
  - `parser.py` → แยกชั้น io (อ่าน workbook), detect (หา VAT row/หัวตาราง), reconcile (จำนวนเงิน),
    merge (หน้าต่อ) เป็นโมดูลย่อย.
  - `reporting.py` → แยกตาม "ชีต" (Dashboard / Summary / Errors / …) เป็น builder ย่อย.
  - **ทุกก้าว**: ย้ายโค้ดแบบไม่แก้ logic → รัน `regression_full.py` (ต้องคง `ec61907f` + `d8bcde85`).
- **ความเสี่ยงการย้าย:** **กลาง-สูง** — แม้ pure-move แต่จำนวนจุดสัมผัสเยอะ; `import *` ปัจจุบันทำให้
  namespace กว้าง ต้องระวังชื่อชน. **บังคับทำทีละไฟล์/ทีละ PR + ผ่าน golden ทั้งสองชุดทุกครั้ง**.
- **ระดับความสำคัญ:** 🟠 P2 (สำคัญต่ออายุ 10 ปี แต่ไม่เร่ง — ทำเป็นชุด ๆ ได้).

---

## 6. การแก้รอบนี้เสริม "Hyper Hybrid Hierarchical + Mesh" อย่างไร

```
                         ┌──────────────────────────────────────────────┐
   CONTROL PLANE         │  Orchestrator (ลำดับชั้น/ดีเทอร์มินิสติก)         │
   (ใครรันเมื่อไหร่)        │  Import → ⭐core→ Tier1 → Tier2 → AI → Tier3 → Super → Report → Notepad │
                         └───────────────┬──────────────────────────────┘
                                         │ เรียก
                         ┌───────────────▼──────────────────────────────┐
   ⭐ SINGLE SOURCE       │  run_audit_core()  ←─── main() ก็เรียกตัวนี้      │   ← v9.1: แกนเดียว
   OF TRUTH (แกนตรวจ)     │  _audit_core_rules() + _audit_core_crosschecks │     golden_master ก็เรียก
                         │  (isolate=True → ทนทานเท่ากันทุกเส้น)            │
                         └───────────────┬──────────────────────────────┘
                                         │ findings (advisory)
                         ┌───────────────▼──────────────────────────────┐
   DATA PLANE            │  FindingsMesh (blackboard/แนวราบ)               │
   (ใครเห็นผลของใคร)        │  publish / by_* / correlate_by_bill            │
                         └──────────────────────────────────────────────┘
```

- **Hierarchical (control plane) แข็งขึ้น:** เดิมแกนตรวจมี "สำเนาความจริง" หลายชุด. ตอนนี้มี
  **แกนเดียว** ที่ทุก entry point เรียกร่วม → ลำดับชั้นมี "หัวใจเดียว" ที่เชื่อถือได้ (consistency +
  predictability ตามลำดับความสำคัญข้อ 4–5).
- **Mesh (data plane) ไม่ถูกแตะ:** การแก้ทั้งหมดอยู่ฝั่ง control/verification → mesh ยังเป็น advisory
  บริสุทธิ์ (ผล Excel byte-identical คงเดิม).
- **Verification เป็น mesh เล็ก ๆ ของตัวเอง:** `golden_snapshot.py` กลายเป็น "แหล่งความจริงเดียว" ของ
  การพิสูจน์ — engine path กับ agent path สองโหนดนี้ยึด nucleus เดียวกัน → เทียบกันได้เสมอ.

---

## 7. วิธีรัน/ตรวจสอบ (เรียงตามความเร็ว)

```bash
# (เร็วสุด) ด่าน CI ทั้งชุดบน fixture — เหมือนที่ GitHub Actions รัน
PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 bash run_ci.sh
#   → ต้องเห็น "✅ CI ผ่านทั้งหมด" และ fixture hash d8bcde85…

# (เต็ม) regression บนข้อมูลจริง 81 ไฟล์ — ต้อง ec61907f และ engine==agent
PYTHONHASHSEED=0 python3 regression_full.py . /mnt/project

# (เสริม) e2e เต็ม — สร้าง Excel จริงแล้วเปิดกลับมาตรวจครบชีต (รันจาก cwd ไหนก็ได้แล้ว)
PYTHONHASHSEED=0 python3 e2e_test.py
```

> ทุกด่านต้อง `PYTHONHASHSEED=0`. ถ้าจะเปลี่ยน `MASTER` ทดสอบ: แก้ที่ **`golden_snapshot.py` ที่เดียว**
> (ทั้ง engine/agent/oracle/e2e จะตามทันทีโดยไม่ต้องไล่แก้หลายไฟล์อีก).

---

## 8. การถอยกลับ (Rollback)

แต่ละ Finding เป็น commit แยกใน git (ภายในแพ็กเกจ) เรียงดังนี้:

```
399d89f  P2/P3: converge MASTER + fix e2e path        (Finding C-ext + G)
1bf669f  P2 (Finding C): dedup -> golden_snapshot.py   (Finding C)
10cc455  P1: unify sacred audit sequence               (Finding A + B)
4c565aa  baseline: green (ec61907f / d8bcde85)         (จุดเริ่ม)
```

ถอยทีละขั้นได้ด้วย `git revert <hash>` โดยไม่กระทบขั้นอื่น. ถ้าจะถอยทั้งหมดกลับ baseline:
`git reset --hard 4c565aa`. ทุก commit ผ่าน golden ทั้งสองชุดแล้ว — การถอยจึงปลอดภัยและคาดเดาได้.

---

## 9. สรุปหลักการที่ยึด (เพื่อผู้ดูแล 10 ปี)

1. **อย่ามี "ความจริง" สองชุด** — ลำดับศักดิ์สิทธิ์/นิยาม hash/fixture ต้องมีแหล่งเดียว (รอบนี้ทำแล้ว).
2. **เส้นทางทุกเส้นต้องทนเท่ากัน** — isolation ที่ engine มี เส้น agent ต้องมีด้วย (รอบนี้ทำแล้ว).
3. **พิสูจน์ทุกการแก้ด้วย golden 2 ชุด** — byte เปลี่ยน = hash เปลี่ยน = รู้ทันที.
4. **refactor ก่อนเสมอ ฟีเจอร์ทีหลัง** — รอบนี้ไม่เพิ่มฟีเจอร์เลย.
5. **ไฟล์ใหญ่แยกเป็นเฟส มี gate** — อย่ารื้อทีเดียว (Finding F).

*— จบรายงาน —*
