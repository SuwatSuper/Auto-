# INVARIANTS / DECISIONS — สมุดบันทึกข้อตัดสินที่ "ล็อกแล้ว" (ปุ้มปุ้ย v9.x)

> เอกสารนี้คือ **แหล่งความจริงเดียว** ของ "อะไรห้ามขยับ และเพราะอะไร"
> ใครก็ตามที่จะแก้โค้ดในระบบนี้ ต้องอ่านหัวข้อ §1–§4 ก่อนเสมอ
> รูปแบบ = Architecture Decision Record (ADR) แบบ append-only — **ห้ามลบรายการเก่า**
> ถ้าข้อตัดสินเปลี่ยน ให้เพิ่ม ADR ใหม่ที่อ้าง superseded ของเดิม (เก็บประวัติไว้)

เครื่องมือที่บังคับใช้เอกสารนี้โดยอัตโนมัติ:
- `INVARIANTS/check_invariants.py` — tripwire (golden fixture + pin tests) รันได้ทุกที่ ไม่ต้องมีข้อมูลจริง
- `hooks/pre-commit` (ติดตั้งผ่าน `INVARIANTS/install_hooks.sh`) — บล็อก commit ถ้า invariant แตก
- `golden_master.py` / `verify_golden.py` / `regression_full.py` — golden เต็มบนข้อมูลจริง 148 ไฟล์ (`/mnt/project`)

> ⚡ **สถานะปัจจุบัน (ล่าสุด — ดู ADR-021 ท้ายไฟล์):** corpus ทางการ = **148 ไฟล์ `/mnt/project` (1056 บิล)** · golden = **`08e6abfd…`** (= `baseline.json._sha256` = แหล่งความจริงเดียวของค่า hash) · สาย 81 ไฟล์ และ 106-เก่า **ปลดระวางแล้ว** (ค่า hash เดิมก่อน F2-cont อยู่ใน ADR-018/ADR-019/ADR-021 + เอกสารที่ลงวันที่) — เลข hash ในเอกสารอดีตคือ "หลักฐาน" เก็บไว้ ห้ามแก้

---

## §0 — สภาพแวดล้อม deterministic (ต้องตั้งทุกครั้ง ผล hash ถึงตรง)

| ตัวแปร/ของ | ค่าที่ล็อก | เหตุผล |
|---|---|---|
| `PYTHONHASHSEED` | `0` | กัน set/dict iteration order สุ่ม → hash เพี้ยน |
| `PUOPUY_AUDIT_DATE` | `2026-06-02` | ตรึง "วันที่ตรวจ" → กฎอิงวันที่ไม่ขยับตามนาฬิกาเครื่อง |
| Python | `3.12.x` | ไลบรารีหัวใจถูกพิสูจน์บน 3.12 |
| pandas | `2.2.2` | **กระทบ golden โดยตรง** (sort/format/dtype) |
| xlrd | `2.0.1` | อ่าน .xls — กระทบ golden |
| openpyxl | `3.1.5` | อ่าน .xlsx — กระทบ golden |
| rapidfuzz | `3.10.1` | คะแนน fuzzy — กระทบ typo/ชื่อบริษัท → golden |
| numpy | `<3` | reproduce ได้บน numpy 2.x ; กัน major bump |

> บังคับใช้โดย `version_gate.py` (อ่าน `config._LOCKED`). ถ้าเวอร์ชันไม่ตรงระดับอันตราย
> → หยุดทำงาน (ยืนยันจะรันทั้งที่เสี่ยง: `PUOPUY_ALLOW_VERSION_MISMATCH=1`).
> ติดตั้งให้ตรง: `pip install -r requirements.txt -c constraints.txt`

---

## §1 — GOLDEN HASH (Invariant สูงสุด — ห้ามขยับโดยไม่ตั้งใจ)

ผลตรวจหลัก (engine) ถูก "แช่แข็ง" ด้วย SHA256 ของ snapshot canonical
(สูตรเดียวใน `golden_snapshot.py`). ค่าที่ล็อก:

| ชุดข้อมูล | จำนวนไฟล์ | golden `_sha256` | สถานะการพิสูจน์ |
|---|---|---|---|
| **ข้อมูลจริง (ทางการ) — `/mnt/project`** | 148 | `08e6abfd…` (= `baseline.json._sha256`) | ผู้ใช้รันยืนยันบนเครื่องตน · engine==agent==baseline (1056 บิล) · rebaseline ADR-058 |
| fixture (in-repo) | 1 ไฟล์ | `d8bcde8555034a203f80d2a596c42ea57b2f1a39ce67003f5629cea03185b07c` | ยืนยันใน CI/pre-commit (เร็ว ~3s, ไม่ต้องมีข้อมูลจริง) |

**กฎ:** การเปลี่ยน golden ของ "ข้อมูลจริง 148 ไฟล์ (`/mnt/project`)" ทำได้ก็ต่อเมื่อ **ผู้ใช้สั่งโดยตรง**
เท่านั้น และต้องบันทึก ADR ใหม่อธิบายเหตุผล + regen baseline ด้วย `golden_master.py`.

> คอร์ปัสทางการ = **148 ไฟล์ `/mnt/project`** (ชุด 81 ไฟล์เดิมปลดระวางแล้ว — ดู ADR-019).
> คุณสมบัติ engine==agent พิสูจน์แล้วและ **ไม่ขึ้นกับชุดข้อมูล** (ดู §6 / `verify_golden.py`).

---

## §2 — ADR-001 : engine == agent == baseline (เส้น advisory ห้ามแตะคำตัดสิน)

- **คำตัดสินจริง** มาจาก `run_audit_core` (engine) เท่านั้น → เขียนลง Excel
- งานเพิ่มทุกชั้น (agents / verification lenses / mesh / LLM) เป็น **advisory** ล้วน
  - ห้ามเขียนทับ `b['issues']` หรือเปลี่ยนผลตรวจหลักเด็ดขาด
  - แสดงผลเป็น findings `VERIFY-*` แยกต่างหาก
- **Invariant ที่ต้องจริงเสมอ:** `engine_hash == agent_hash == baseline_hash`
  - พิสูจน์โดย `regression_full.py` (รัน 2 เส้นในโปรเซสแยก แล้วเทียบ hash)
- **เหตุผล:** ถ้าชั้น advisory แอบเปลี่ยนผลตรวจ ระบบจะ "ฉลาดขึ้นแบบควบคุมไม่ได้" —
  ผู้ตรวจสอบบัญชีต้องเชื่อใจว่าเลขชุดเดิม input เดิม = ผลเดิมเป๊ะ (auditability)

---

## §3 — ADR-002 : ออฟไลน์ล้วนในเส้น audit (zero outbound)

- เส้น audit ต้อง **ไม่มี network call ออกนอกเครื่อง** เลย
- บังคับโดย `offline_guard.py` (สวิตช์เดียว: env `PUOPUY_ALLOW_NETWORK`; localhost อนุญาตเสมอ)
- `webverify.py` web_request ปิดเป็นค่าตั้งต้น ; LLM (`agents/llm_provider.py`) =
  Local Ollama opt-in เท่านั้น และ **อยู่นอกเส้น deterministic/CI** (offline → งดออกเสียง)
- input untrusted ผ่าน `file_guard.py` (กัน zip-bomb / ไฟล์ใหญ่ผิดปกติ) ก่อนแตะ parser
- **เหตุผล:** ข้อมูลใบกำกับภาษีเป็นข้อมูลลับ ห้ามรั่ว ; ผลตรวจต้อง reproduce ได้ offline 100%

---

## §4 — ADR-003 : กฎโดเมน VAT = 7% เป๊ะ (ground truth — นักบัญชี)

- กติกา: `vat == round(subtotal × 0.07, 2)` ปัด **ROUND_HALF_UP**
- ยอมต่างได้เฉพาะ "เศษการปัด" — **ห้ามใช้ "แถบ %" (percentage band)** เด็ดขาด
- จุดที่ใช้กฎนี้:
  - engine: `r_vat002` ใน `rules_engine.py` (คำตัดสินจริง)
  - advisory: เลนส์ `L8_vat_7pct` (`lens_vat_7pct_exact`) ใน `agents/verification_lenses.py`
- **threshold การยอมต่าง (tolerance) เป็นข้อตัดสินของผู้ใช้** — ปัจจุบัน `r_vat002` = `diff < 0.50`
  (ตั้งใน ADR-005) ; ดูประวัติ/เหตุผลใน ADR-LOG ด้านล่าง

---

## §5 — ADR-004 : บทเรียน revert `_FastFrame` (ห้ามทำซ้ำ)

- เคยลอง materialize sheet → numpy (`_FastFrame`) เพื่อเร่ง perf ทะลุ 30%
- **ผลข้างเคียง: บิลร่วง 836 → 52 + golden hash เปลี่ยน → revert ทิ้งทันที**
- **กฎที่ได้:** การ optimize parser **ทุกครั้ง** ต้อง golden-verify ทุกก้าว
  ; ถ้า bill count หรือ parse rate ร่วง = สัญญาณ regression แม้ test อื่นเขียว
- ตาข่ายเสริมจับเคสนี้โดยไม่พึ่ง golden: `parse_canary.py` (ดู §6)
- การ optimize ที่ปลอดภัยและทำไปแล้ว: `parser.py` เปลี่ยน scalar `iloc[r,c] → iat[r,c]`
  (ค่าเท่ากันเป๊ะ, golden ไม่ขยับ, ~18% end-to-end)

### §5.1 — บทเรียนการซอยไฟล์ (OBJ-MAINT) — "global ที่ถูก rebind จากภายนอก"
- เมื่อแยกฟังก์ชันออกเป็นโมดูลย่อยด้วย `from base import *` แล้ว ชื่อจะเป็น **คนละ binding**
  (snapshot ตอน import). ถ้ามีโค้ด/เทสภายนอก rebind module-global (เช่น `rules_engine.PRODUCT_MASTER = …`)
  ฟังก์ชันที่ย้ายไป base จะอ่าน `base.PRODUCT_MASTER` (ของเดิม) → **patch ไม่ถึง** → เทสล้ม
  ทั้งที่ golden ไม่ขยับ (เพราะข้อมูล golden ไม่ populate global นั้น).
- **กฎ:** global ที่ถูก rebind จากภายนอก + ฟังก์ชันที่อ่านมัน (bare name) **ต้องอยู่โมดูลเดียวกัน**
  กับ namespace ที่ถูก patch. ตรวจก่อนซอย: `grep -rnE "\b(R|<mod>)\.[A-Za-z_]+ *="` ในเทสทั้งหมด.
- **เกราะที่จับได้:** ชุดเทสเต็ม (ไม่ใช่ golden อย่างเดียว) — ต้องรัน full suite หลังซอยทุกครั้ง.
- **กรณีมี internal caller** (เช่น `_record_text_num` ถูกเรียกโดย `_pb_build_item` ; `parse_sheet`
  ถูกเรียกโดย `parse_file`) → ย้ายไป shell ไม่ได้ (จะ break golden). วิธีแก้ที่ทน refactor:
  เทส patch ที่ **`fn.__globals__['NAME']`** (โมดูลนิยามจริงของ fn) ไม่ใช่ `shell.NAME` —
  ให้ผลเท่า monolith เดิมเป๊ะ และไม่ผูกกับเลขเลเยอร์.
- ⚠️ **false pass:** การซอยอาจทำให้เทสที่ patch `shell.parse_sheet` "ผ่านแบบหลอก" (boom ไม่ทำงาน
  เพราะ caller อ่าน binding ในเลเยอร์ตน) — เทสผ่านเพราะ input บังเอิญให้ผลเดียวกัน ไม่ใช่เพราะกิ่งทำงาน.
- ⚠️ **golden ไม่ใช่ตาข่ายเสมอ:** `reporting.py` ไม่ถูก golden แตะ (golden_master ใช้ write_report=False).
  ตาข่ายจริง = (1) `from reporting import *` surface ต้องเท่าเดิมเป๊ะ (ไม่งั้น main:607 พัง),
  (2) **report-cell-hash** (รัน build_clean_report บน 148 ไฟล์ → hash ทุก cell ทุกชีต) old==new,
  (3) smoke/e2e. ใช้ทั้งสามแทน golden.
- ⚠️ **future-import ต้องตรงต้นฉบับ:** splitter ใส่ `from __future__ import annotations` ใน layer/shell
  *เฉพาะเมื่อไฟล์เดิมมี* (parser มี → ใส่ ; reporting ไม่มี → ไม่ใส่). ถ้าใส่เกินใน shell ที่ไม่มี __all__
  → ชื่อ `annotations` รั่วเข้า `import *` surface (+1 ชื่อ) และเปลี่ยน annotation eval เป็น lazy.
- ⚠️ **ไฟล์ที่ไม่มี __all__ เดิม:** shell ต้อง **ไม่ประกาศ __all__** (คง default `import *` = ชื่อไม่ขึ้น _).
  layer files ยังใช้ auto-__all__ (รวม _ เพื่อ cascade) ได้ตามปกติ.

---

## §6 — ตาข่ายนิรภัย (ลำดับความเชื่อถือ)

1. **golden master + pin tests** = เกราะตัวจริง (จับ "พฤติกรรมเปลี่ยน")
   - `regression_full.py` (golden เต็ม), `test_pinned_logic.py`, `test_verification_lens_pin.py`
2. **parse-rate canary** (`parse_canary.py`) = จับ parse regression แบบ 836→52 เร็ว ๆ
   โดยไม่ต้องพึ่ง hash (ใช้ได้กับข้อมูลใหม่ที่ยังไม่มี golden)
3. **coverage gate** (`coverage_gate.py`) = วัด "บรรทัดถูกรัน" (ไม่ใช่ "บั๊กถูกจับ")
   — เป็นตาข่ายรอง ไม่ใช่หลัก
4. **lint/type** (ruff/black/mypy) = สุขอนามัยโค้ด

> **ความจริงที่ต้องจำ:** coverage 90% ไม่ได้แปลว่าไม่มีบั๊ก มันแปลว่า "โค้ด 90% ถูกรันระหว่างเทส"
> เท่านั้น. ความถูกต้องเชิงพฤติกรรมมาจาก golden + pin เป็นหลัก.

### §6.1 — Branch coverage (เปิดวัดใน P2 — gate แบบ opt-in)

`coverage_gate.py` เปิด `--branch` แล้ว รายงาน 3 ตัวเลขแยกต่อโมดูล: line% / branch% / combined%
- **LINE gate** = บังคับ ≥ `PUOPUY_COV_MIN` (ดีฟอลต์ 90) — เหมือนเดิม
- **BRANCH gate** = บังคับ ≥ `PUOPUY_COV_BRANCH_MIN` **เฉพาะเมื่อตั้ง env นี้** ; ไม่ตั้ง = รายงานเฉย ๆ
  (เปิด branch แล้วตัวเลขจะเข้มขึ้น → ตั้งเกณฑ์ต่ำกว่า line ก่อน แล้วไต่ขึ้น)

ค่า branch ที่ "วัดได้ตอนเปิด P2" (ใช้เป็นจุดตั้งต้นการไต่):

| module | line% | branch% | combined% |
|---|---|---|---|
| parser.py | 95.2 | 87.3 | 92.2 |
| rules_engine.py | 95.1 | 85.0 | 91.2 |
| validators.py | **100.0** | **93.8** | **97.6** |
| puopuy_units.py | 100.0 | 100.0 | 100.0 |
| TOTAL (แกน) | 95.9 | 87.5 | 92.7 |

> ค่า validators ไต่ขึ้นจาก 79.4 → 93.8 ใน ADR-010 (เพิ่ม `test_validators_branch.py`). ดูด้านล่าง.

floor ปลอดภัยปัจจุบัน (ผ่านทุกโมดูล) ขยับขึ้นเป็น **branch 85** (lowest = rules_engine 85.0) ;
ตั้ง `PUOPUY_COV_BRANCH_MIN=85` ได้แต่ rules_engine อยู่พอดีขอบ (เปราะ) — แนะนำตั้ง **84** เป็น floor
ที่มี margin แล้วค่อยไต่ rules_engine ขึ้นในงานถัดไป.

---

## ADR-LOG (append-only — เพิ่มล่างสุดเสมอ)

### ADR-001 (สถาปัตยกรรม) — advisory แยกจาก engine
- สถานะ: **ACTIVE**
- สรุป: ดู §2.

### ADR-002 (ความปลอดภัย) — ออฟไลน์ล้วน
- สถานะ: **ACTIVE**
- สรุป: ดู §3.

### ADR-003 (โดเมน) — VAT 7% เป๊ะ, ห้าม band
- สถานะ: **ACTIVE**
- สรุป: ดู §4.

### ADR-004 (perf) — ห้าม materialize parser โดยไม่ golden-verify
- สถานะ: **ACTIVE**
- สรุป: ดู §5.

### ADR-005 (โดเมน/threshold) — tolerance ของ VAT002
- สถานะ: **ACTIVE** (ลงมือใน Pass P4 — ผู้ใช้ตัดสิน 0.50)
- การเปลี่ยนแปลง: `r_vat002` (rules_engine.py) `diff < 1.00` → `diff < 0.50`
  ให้ตรงกฎโดเมน §4 (ยอมเฉพาะเศษปัด) — **แตะจุดเดียว** (บรรทัด 1007)
  ; line 1003 (`abs(vat) ≤ 1.00` discriminator rate/amount) และ r_vat003 **ไม่แตะ**
- ล็อกพฤติกรรมด้วย pin: `test_vat002_tolerance.py` (0.40/0.49 เงียบ · 0.50/0.70/1.00 ฟ้อง · rate ข้าม)
- ผลกระทบที่ยืนยันแล้ว (sandbox):
  - golden sandbox (106) = `f1ac8421…` **ไม่ขยับ** (0 ใบอยู่ในช่วง [0.50,1.00))
  - golden fixture = `d8bcde85…` **ไม่ขยับ** → pre-commit hook ผ่าน, ไม่ต้อง regen fixture
  - micro-proof: diff 0.70 ฟ้องใหม่ ✅ / diff 0.40 ยังเงียบ ✅ (patch มีผลจริง ไม่ใช่ no-op)
- ⚠️ **ผลทางการ (81 ไฟล์)** ต้องรันเครื่องผู้ใช้ (ข้อมูลไม่อยู่ใน repo):
  `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . <81 ไฟล์>`
  - คาด (ตาม handoff): 0 ใบ → `ec61907f…` ไม่ขยับ
  - ถ้า hash ขยับและยอมรับ → regen ตั้งใจ: `python3 golden_master.py . baseline.json <81 ไฟล์>`
  - บันทึกผลจริงที่นี่: `engine_hash = ____________` (ผู้ใช้เติม)
- หมายเหตุ: ถ้าจะเข้มถึง `0.01` = ฟ้องเพิ่ม ~4 ใบ → ต้อง regen baseline โดยตั้งใจ (คนละเรื่องกับ 0.50)

### ADR-006 (maintainability/OBJ-MAINT) — ซอย rules_engine.py
- สถานะ: **ACTIVE** (ลงมือแล้ว — pure extraction + re-export, golden byte-identical)
- เดิม `rules_engine.py` = 1559 บรรทัด → ซอยเป็น 5 ไฟล์ (≲600/ไฟล์):
  - `rules_engine_base.py` (151) — imports + constants + helpers/infra (toolkit รวม, auto `__all__`)
  - `rules_engine_rules_a/b/c.py` (422/372/391) — กฎ r_* กลุ่มละ ~1/3 (`from base import *`)
  - `rules_engine.py` (220) — re-export ทั้ง 4 + **PRODUCT_MASTER cluster** + RULES + run_rules
- วิธี extract: slice ช่วงบรรทัดด้วย AST (ไม่พิมพ์ body ใหม่) → ทุก body byte-identical
- PRODUCT_MASTER cluster (global + load_product_master + _build_product_whitelist +
  validate_product_word + r_itm009 + r_itm012) **คงไว้ในไฟล์ shell** เพราะ external-rebind (ดู §5.1)
- ผลยืนยัน (sandbox): golden `f1ac8421…` ไม่ขยับ · fixture engine==agent==baseline ·
  full test suite 22/22 ผ่าน · coverage family 95.1% line (≈ก่อนซอย 95.0%)
- coverage_gate: เปลี่ยนเป็น "เกตระดับกลุ่ม" (rules_engine family รวมเป็นหน่วยเดียว) →
  ความหมายเกตเท่าเดิม ไม่ถูกหลอกด้วย granularity การซอย
- ⚠️ ผลทางการ 81 ไฟล์ (`ec61907f`) = ผู้ใช้รันยืนยัน (เหมือน ADR-005)
- คงเหลือใน OBJ-MAINT: ซอย `parser.py` (1642) และ `reporting.py` (1496) ด้วยสูตรเดียวกัน
  (ตรวจ external-rebind global ก่อน + รัน full suite + golden ทุกก้าว)

### ADR-007 (maintainability/OBJ-MAINT) — ซอย parser.py
- สถานะ: **ACTIVE** (ลงมือแล้ว — DAG-layered extraction, golden byte-identical)
- เดิม 1642 บรรทัด → 4 ไฟล์ (≲600/ไฟล์): `parser_p0.py` (573, header+bottom layer),
  `parser_p1.py` (515), `parser_p2.py` (492), `parser.py` (shell 30 = re-export + __all__ เดิม)
- call-graph ภายในเป็น DAG (ไม่มี cycle) → topo-sort (callee ก่อน caller) → chunk ≲500 บรรทัด/ไฟล์
  → cascade import เชิงเส้น (p1←p0, p2←p1, shell←p2) → เป็นไปไม่ได้ที่จะมี forward/cross ref
- extract ด้วย AST line-slice (byte-identical), ไม่มี decorator/global statement
- **เทสที่ต้องแก้ (เพราะ internal caller — ดู §5.1):** 2 จุด เปลี่ยนมา patch `fn.__globals__`
  - `test_parser_extra.py`: `_MAX_TEXT_NUM_RECOVERIES` (เคย fail หลังซอย)
  - `test_parser_extra2.py`: `parse_sheet` boom (เคย false-pass หลังซอย — boom ไม่ทำงาน)
- ผลยืนยัน (sandbox): golden `f1ac8421…` ไม่ขยับ · fixture engine==agent==baseline ·
  full suite 21/21 · parser family cov 95.1% line (=ก่อนซอย)
- ⚠️ ผลทางการ 81 ไฟล์ (`ec61907f`) = ผู้ใช้รันยืนยัน
- คงเหลือ: ซอย `reporting.py` (1496)

### ADR-008 (maintainability/OBJ-MAINT) — ซอย reporting.py
- สถานะ: **ACTIVE** (ลงมือแล้ว — DAG-layered extraction, report-output byte-identical)
- เดิม 1497 บรรทัด → 4 ไฟล์ (≲600/ไฟล์): `reporting_p0.py` (588), `reporting_p1.py` (522),
  `reporting_p2.py` (330), `reporting.py` (shell 7 = docstring + `from reporting_p2 import *`, **ไม่มี __all__**)
- call-graph DAG (0 cycle, 0 decorator) → topo + cascade เชิงเส้นเหมือน parser
- **ต่างจากกรณีอื่น:** golden ไม่แตะ reporting → ใช้ตาข่าย 3 ชั้น (ดู §5.1): import* surface เท่าเดิม
  (83 ชื่อ) · report-cell-hash 106 ไฟล์/9 ชีต = `87d8797766…` (old==new) · smoke+e2e
- reporting เดิม **ไม่มี** `from __future__ import annotations` → shell/layer ไม่ใส่ (กัน `annotations` รั่ว + คง eager eval)
- reporting เดิม **ไม่มี** `__all__` → shell ไม่ประกาศ __all__ (คง default import* = ไม่ขึ้น _)
- ไม่มีเทส patch reporting attr → ไม่มี rebind hazard
- ผลยืนยัน (sandbox): golden `f1ac8421…` ไม่ขยับ (พิสูจน์ core ไม่เปลี่ยน) · full suite 21/21 ·
  report-cell-hash old==new (พิสูจน์ Excel เหมือนเป๊ะ)
- ⚠️ ผลทางการ 81 ไฟล์: split ไม่กระทบ golden → คาดว่าได้ `ec61907f` เท่าเดิม (ผู้ใช้ยืนยัน)
- OBJ-MAINT ครบทั้ง 3 ไฟล์ (rules_engine/parser/reporting). คงเหลือ: **OBJ-PERF** (เสี่ยงสุด ทำท้ายสุด)

### ADR-009 (performance/OBJ-PERF) — materialize sheet cells (step 1: _detect_vat_rows)
- สถานะ: **ACTIVE** (step 1/N — ทำทีละฟังก์ชัน verify เต็มทุกก้าว)
- ปัญหา (profiled 106 ไฟล์): pandas scalar cell access (`.iat`) ~2.95M ครั้ง = ~72s (boxing/`_get_value`/`__finalize__`).
  ตัวร้อน: `_detect_vat_rows`, `_row_has_vat_marker`, `_row_label_match`, `_label_based_amounts`, `_is_tor_format`
- วิธี safe: materialize ทั้งชีตครั้งเดียว `M = df.to_numpy(dtype=object)` แล้วอ่าน `M[r,c]`
  - **พิสูจน์:** 836 ชีต/555,176 cell — `M[r,c]` เท่ากับ `.iat` เชิงพฤติกรรม (isna/str/เป็นตัวเลข/float) = 0 ต่าง
  - ⚠️ **ห้าม** `df.values`/`.tolist()`: unify dtype ข้ามคอลัมน์ (int→float → `str` เปลี่ยน) = กับดักที่ทำ `_FastFrame` พัง (836→52)
  - ⚠️ **ห้าม wrap df** (mimic semantics) แบบ `_FastFrame` — วิธีนี้ไม่ wrap แค่ materialize ด้วย accessor ที่พิสูจน์แล้ว
- step 1: `_detect_vat_rows` (parser_p1) — local, ไม่เปลี่ยน signature
- **ตาข่าย report ต้อง normalize timestamp:** build_clean_report เขียน cell A4 = `datetime.now()` (ระดับนาที, reporting_p2:51,242)
  → report raw-hash **ไม่ deterministic**. ใช้ **det-hash** (normalize เฉพาะ `dd/mm/yyyy HH:MM`; วันที่ใบกำกับจริงไม่มีเวลา → ไม่โดน)
  - แก้บันทึก ADR-008: การ match `87d8797766…` เดิม = "บังเอิญรันในนาทีเดียวกัน". det-hash ยืนยันภายหลัง:
    ก่อนซอย reporting (6116d31) = หลังซอย+perf = `fff69fc608…` → split ถูกจริง
- ผลยืนยัน step1: golden `f1ac8421` ไม่ขยับ · det-report-hash `fff69fc608…` (perf-on==perf-off==ก่อนซอย) ·
  full suite 21/21 · `_detect_vat_rows` ~15.2s→~0.19s/pass
- step 2 (`_is_tor_format`, `_pb_scan_header` — local, ไม่เปลี่ยน signature): golden/det-hash/suite เท่าเดิมทุกตัว
  · **เวลา parse จริง (unprofiled 106 ไฟล์): 46.9s → 29.2s = 1.6× (−38%)** จาก 3 ฟังก์ชัน (step1+2)
- step 3 (**threaded** — เปลี่ยน signature `df`→`M` ในตัวร้อนต่อแถว, materialize ครั้งเดียวใน caller's loop):
  `_pb_find_vat_row`→`_row_has_vat_marker` · `_label_based_amounts`→`_row_label_match`+`_rightmost_num`
  (ทั้ง 3 helper มี caller เดียว = contained ; แต่ละ helper แตะ df ผ่าน `.iat` อย่างเดียว)
  - เทส 3 จุดที่เรียก helper ตรง ๆ ต้องส่ง `df.to_numpy(dtype=object)` (สัญญา helper เปลี่ยน — data/ผลคาดหวังเท่าเดิม)
  - ✅ golden `f1ac8421` ไม่ขยับ (tripwire เดียวกับที่จับ `_FastFrame` 836→52) · det-hash `fff69fc608` · canary ผ่าน · suite 21/21 · smoke+e2e
  - **เวลา parse จริง: 46.9s → 11.6s = 4.0× (−75%)** cumulative (step1+2+3)
- step 4 (`detect_item_columns` คลัสเตอร์ `_dic_*` — thread M ผ่าน 7 helper ต่อ-cell):
  `_dic_item_rows`/`_dic_text_score`/`_dic_find_name`/`_dic_find_amt`/`_dic_collect_numeric`/`_dic_score_combo`/`_dic_pick_qty_price` รับ M
  · `_dic_find_seq`/`_dic_int_run` คง df (column-vectorized `df.iloc[:,c].dropna()` — เร็วอยู่แล้ว, ไม่เข้ากับ M)
  · เทส 3 จุด `_dic_pick_qty_price` ส่ง `df_q.to_numpy(dtype=object)`
  · ✅ golden `f1ac8421` / det-hash `fff69fc608` / suite 21/21 · **46.9s → 9.7s = 4.8×**
- ⚠️ ผลทางการ 81 ไฟล์ (`ec61907f`) = ผู้ใช้ยืนยัน (perf ไม่กระทบ golden → คาดว่าเท่าเดิม)
- ✅ ผู้ใช้ยืนยัน 81 ไฟล์ = `ec61907f` (P4 + 3 split + perf step1–4) — engine ของจริงปลอดภัย
- step 5 (precompile regex `_strip_thai_marks`/`_cell_to_num` — module-level compiled): golden/det-hash/suite เท่าเดิม · **46.9s → 8.9s = 5.3×**
- step 6 (**parallel-over-files** — `parallel_audit.py`, ADDITIVE/opt-in, ไม่แตะ parse_all_files เดิม):
  worker เรียก parse_all_files (เดิม) บน chunk ต่อเนื่อง → parent merge ตามลำดับ file_list
  · _SYSTEM_ISSUES dedup key มี `file` → ไม่มี dup ข้าม worker (merge = concat ตามลำดับพอ) · _TEXT_NUM เคารพ cap
  · พิสูจน์ serial==parallel (workers=4 บังคับ merge หลาย chunk แม้ nproc=1): golden `f1ac8421` + det-hash `fff69fc608` ตรง · serial path ไม่แตะ (additive)
  · ⚠️ sandbox nproc=1 → วัด speedup ไม่ได้ ; บนเครื่องหลายคอร์ของผู้ใช้คาดได้ ~N× ต่อ batch
  · เครื่องมือ: `verify_parallel.py [DATA_DIR] [WORKERS]` (รันบน 81 ไฟล์เพื่อยืนยันก่อนใช้จริง)
  · ⚠️ sandbox นี้ sys_issues=0 → path merge ของ issues พิสูจน์เชิงตรรกะ + golden สะอาด ; ข้อมูลที่มี issue (81 ไฟล์) คือบททดสอบจริง — รัน verify_parallel.py ยืนยัน

**OBJ-PERF สรุป: parse 46.9s → 8.9s = 5.3× (single-core) + parallel path พร้อมใช้ (multi-core) — ผลทุกชั้น byte-identical**

### ADR-010 (OBJ-TEST) — ดัน branch coverage ของ validators.py (79.4 → 93.8)
- สถานะ: **ACTIVE** (ลงมือแล้ว — เพิ่ม pin/coverage test, golden byte-identical)
- ปัญหา: validators.py เป็นโมดูลแกนที่ branch ต่ำสุด (79.4%) — กิ่ง detection หลัก
  (IV ซ้ำ/ถอยหลัง/ข้ามวัน/เดือนไม่ตรง/sheet-day/DT004/DOC001) + guard + fallback ไม่ถูกตรวจ
- วิธี: เพิ่มไฟล์ **`test_validators_branch.py`** (32 เคส) สร้างบิลสังเคราะห์จุดชนวนแต่ละกิ่ง
  - positive detection ทุกชนิด + guard (no iv_date/iv_number, group เล็ก, dedup source)
  - `detect_iv_period_mismatch` ครบทุกเส้นตีความงวด (ปี4+เดือน/ปี2+เดือน/ปี4อย่างเดียว/อ่านไม่ได้)
  - `check_product_typos` fallback path (monkeypatch `rapidfuzz.process.cdist` ให้ raise → ลง except)
- ผล (coverage_gate): validators **line 93.5→100.0 · branch 79.4→93.8 · combined 88.0→97.6**
  - TOTAL แกน: branch 85.6→87.5 ; validators กลายเป็น branch สูงสุดในกลุ่ม non-trivial
- ✅ golden fixture `d8bcde85…` ไม่ขยับ · tripwire เขียวครบ · เป็น test ล้วน ไม่แตะโค้ดโดเมน
- ลงทะเบียนใน `coverage_gate.py` TESTS (วัดในเกตทุกครั้ง) + อัปเดตตาราง §6.1
- floor ปลอดภัยใหม่: branch 85 (lowest = rules_engine 85.0) ; งานถัดไป = ไต่ rules_engine ขึ้น

### ADR-011 (OBJ-A / verification) — ขยายคลังเลนส์ 22 → 30 ผู้ตรวจ
- สถานะ: **ACTIVE** (ลงมือแล้ว — advisory เพิ่ม 8 เลนส์, golden byte-identical)
- ผู้ใช้สั่ง "ให้ระบบคุมได้มากขึ้น" → เลือกขยาย **verification lenses** (ไม่ใช่ agent)
  เพราะ agents เป็น advisory ไม่เพิ่มพลังตรวจจับ ; เลนส์ = ผู้ตรวจซ้ำต่อ-Error (consensus)
- เพิ่ม 8 เลนส์ (PRECISION-FIRST, self-contained, deterministic) ใน `agents/verification_lenses.py`:
  - L23 vat_zero_exempt (vat=0+sub>0 → ค้าน, อาจยกเว้น) · L24 item_count_sanity (0 รายการ+sub>0 → ค้าน, parse artifact)
  - L25 line_amount_negative (รายการ amount<0 → ยืนยัน) · L26 duplicate_line_in_bill (รายการซ้ำในบิล → ยืนยัน)
  - L27 company_multi_taxid (บริษัทเดียว ≥2 เลขภาษี → ยืนยัน, ใช้ดัชนีใหม่ company_taxids)
  - L28 total_lt_subtotal (total<sub, sub>0 → ยืนยัน) · L29 decimal_scale_error (ratio≈10/100 → ยืนยัน, decimal slip)
  - L30 vat_present_no_base (มี vat แต่ sub หาย/0 → ยืนยัน, VAT ลอย)
- ผลต่อ pin (ตามขั้นตอน docstring "ดู diff → อัปเดต EXPECT/ROSTER"): เปลี่ยน **เฉพาะ IVJ** (บิลยอดติดลบ)
  score 2→3 จาก L25 (ยัง CONFIRMED) ; บิลอื่นทุกใบ vote 0 จากเลนส์ใหม่ (ออกแบบให้ abstain เมื่อไม่เกี่ยว)
- ✅ golden fixture `d8bcde85…` ไม่ขยับ (engine==agent==baseline) · b['issues'] ไม่เปลี่ยน (advisory)
  · lens unit 62/62 · lens pin 14/14 (roster 30) · full CI เขียวครบ (ruff/black/mypy)
- อัปเดต: pin ROSTER_EXPECT+8/IVJ, unit test +24 เคส, check_invariants label 22→30

### ADR-012 (OBJ-A / verification) — ขยายคลังเลนส์ 30 → 34 (มิติ เวลา/งวด/รายการ)
- สถานะ: **ACTIVE** (ลงมือแล้ว — advisory เพิ่ม 4 เลนส์, golden byte-identical)
- ปิดมิติที่ยังบอด + reuse domain logic จาก core (ไม่เขียนใหม่ → ไม่ดริฟต์):
  - L31 future_date — วันที่ในใบ > audit_today (เคารพ PUOPUY_AUDIT_DATE) → ยืนยัน (มิติเวลา)
  - L32 iv_period_conflict — reuse `detect_iv_period_mismatch`; งวดในเลขขัดวันที่ (IV/DT/DOC/SEQ) → ยืนยัน/ค้าน
  - L33 qty_negative — รายการ qty ติดลบ → ยืนยัน (คู่ขนาน L25 ที่ดู amount)
  - L34 subtotal_zero_with_items — subtotal หาย/0 แต่ Σรายการ>0 → subtotal parse ไม่ได้ (ยืนยัน)
- ผลต่อ pin: **roster +4 เท่านั้น ไม่มี vote เปลี่ยน** (ทุกเลนส์ใหม่ abstain บนบิล pin — precision-first)
- ✅ golden `d8bcde85…` ไม่ขยับ · lens unit 72/72 · lens pin 14/14 (roster 34) · full CI เขียวครบ
- ใช้ `core.get(...)` (optional symbol) → ถ้า core ไม่เปิด symbol เลนส์ abstain (ไม่พัง)

### ADR-013 (ฟีเจอร์/ผู้ใช้สั่ง) — รายงานลูกค้ารายผู้ขาย (.txt) เพิ่มเข้า audit
- สถานะ: **ACTIVE** (ผู้ใช้สั่งเพิ่มฟีเจอร์ — additive, golden byte-identical)
- ความต้องการ: ออก .txt แยกทีละ vendor ภาษาคน พร้อมส่งลูกค้า — **output อีกอันข้าง Excel (ไม่ทับ)**
- ทำเป็น 2 ชิ้นแยก (เหมือน notepad): 
  - `agents/vendor_report.py` — ตรรกะจัดฟอร์แมตล้วน (pure): group by vendor, map กฎ→10 ช่อง,
    ช่องผ่าน="ตรง"/ไม่ผ่าน="ควรรีเช็ค N บิลครับ" (ภาษาคน, ตัดโค้ดกฎออกด้วย `_CODE_RE`)
  - `agents/vendor_report_agent.py` — `VendorReportAgent` เขียน .txt (UTF-8-SIG+CRLF) รายผู้ขาย
- map ช่อง (ผัง 10 ช่องตามผู้ใช้): CMP/ADDR/TAX/BR/DOC*/DT*/IV*/ITM*/VAT(หลัง)/VAT(ก่อน)
- ชื่อไฟล์ `{ลำดับ}.{ชื่อย่อ}.txt` (เรียงยอดมาก→น้อย, deterministic) ใน report_dir เดียวกับ Excel
- integrate orchestrator: รัน **หลัง ReportAgent ก่อน NotepadAgent** (อ้าง ctx.report_path = "คุยกับ" Excel)
  - advisory/ไม่ critical · เขียนเฉพาะ write_vendor_report (ดีฟอลต์ตาม write_report) → golden run (report=False) ไม่เขียน
- CLI: `--no-vendor-report` / `--vendor-report-dir` / `--vendor-report-memo` ใน run_agents.py
- ✅ golden `d8bcde85…` ไม่ขยับ (advisory read-only) · agent contracts 37/37 · test_vendor_report 22/22
  · super `_EXPECTED`=9 ไม่กระทบ (vendor_report รันหลัง super) · notepad ยัง "ท้ายสุด" · full CI เขียว
- เพิ่มใน run_ci.sh [4b] + export ใน agents/__init__.py

### ADR-014 (โดเมน/ผู้ใช้สั่ง) — SMART-ADDR: ADDR001+ADDR003 เทียบที่อยู่ทีละ field
- สถานะ: **ACTIVE** (ผู้ใช้สั่งแก้ business logic — **เปลี่ยนผลตรวจ → ต้อง regen baseline จริง**)
- ปัญหา: false alarm "ที่อยู่ไม่ตรง" ทั้งที่ตรงจริง เพราะเทียบข้อความ "เป็นก้อน" (string containment)
  → ลำดับต่าง (ฟอร์ม ภ.พ.20 vs คนเขียน) / ช่องว่าง ("พี 23" vs "พี23") / label+dash ("ห้องเลขที่ -")
- วิธีแก้ (generic ทุกที่อยู่ — **ไม่ hardcode ที่อยู่ใด**): เปลี่ยนเป็น "แยก field แล้วเทียบทีละช่อง"
  - แกนเดียว `_addr_smart_diff(b,m)` ใช้ร่วม ADDR001(ERROR)/ADDR003(WARNING) — รวมตรรกะตามที่ผู้ใช้ขอ
  - parse 2 ฝั่งด้วย `parse_address_input` (reuse) + heuristic ฝั่งบิลไม่มี label (เลขนำหน้า, ไปรษณีย์ 5 หลักท้าย, 2 token ไทยท้าย=แขวง/เขต)
  - normalize: ลบ space, ตัด label เปล่า/'-', รวมคำพ้อง (กทม.=กรุงเทพมหานคร)
  - เทียบ field ด้วย `fuzz.token_sort_ratio ≥ 90`
  - **anchor** = ไปรษณีย์+เขต+แขวง+เลขที่ ตรงครบ → ที่อยู่ถูก (ไม่เตือน) ; ดับ false alarm
  - severity: space/ลำดับ/label ต่าง→เงียบ (INFO) · anchor ต่างจริง→ERROR (ADDR001) · อาคาร/ชั้น/ห้องต่าง→WARNING (ADDR003)
- ⚠️ **ผลกระทบ golden:** บน fixture (ไม่มี ADDR issue) → `d8bcde85…` **ไม่ขยับ** (ยืนยันแล้ว)
  - บน **ข้อมูลจริง 81 ไฟล์** → ADDR issue จะ **ลดลง** (false alarm หาย) = `ec61907f…` **จะเปลี่ยน**
  - ผู้ใช้ต้อง **regen baseline โดยตั้งใจ** หลังตรวจผลว่าถูกต้อง:
    `PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 golden_master.py . baseline.json <81 ไฟล์>`
    แล้วบันทึก hash ใหม่ที่นี่ (ของเดิม ec61907f = ก่อน ADR-014)
- ทดสอบ: `test_addr_smart.py` (14 เคส) — ตรง/คนละลำดับ/space/label เปล่า→เงียบ ; คนละเขต/ไปรษณีย์→ERROR
  · อัปเดต `test_rules_extra.py` ADDR001 (ถ้อยคำ "ขาด"→"ไม่ตรงทะเบียน") · run_ci.sh [3c-addr]
- ✅ fixture golden ไม่ขยับ · full CI เขียวครบ · ไม่แตะกฎอื่น (diff เฉพาะ r_addr001/003 + helper)

### ADR-015 (correctness/บั๊กยืนยันแล้ว) — นิยาม `_compute_col_confidence` ที่หายไป
- สถานะ: **ACTIVE** (Phase 0 ของงาน ITM01/ITM008 — แก้บั๊กที่ยืนยันได้ ; golden ไม่ขยับ)
- บั๊กที่ยืนยัน (Phase 0): `detect_item_columns_safe` (parser_p0.py) เรียก `_compute_col_confidence`
  ที่ **ไม่มี def ทั้ง repo** → dead-on-arrival (NameError). เดิม test ตรึงไว้ว่า "พังโดยตั้งใจ".
- แก้: นิยาม `_compute_col_confidence(df, seq_col, qty_col, price_col, amt_col) → 'HIGH'|'LOW'`
  ตาม contract ที่ documented (qty×price≈amount ผ่าน ≥50% ของ item rows = HIGH) — fail-safe ไม่โยน
- ⚠️ **ไม่กระทบ golden:** `detect_item_columns_safe` **ไม่มี call site ใน production** (pipeline ใช้
  `detect_item_columns` 6-tuple ที่ parser_p2.py ตรง ๆ) → fixture `d8bcde85…` ไม่ขยับ · 81 ไฟล์ไม่ต้อง rebaseline
- อัปเดต `test_parser_extra.py`: จากเดิม assert NameError → assert คืน 7-tuple + conf∈{HIGH,LOW}

> **Phase 0 — บันทึกข้อค้นพบ (สำคัญ):** สมมุติฐาน 2/3 ในเอกสารแก้บั๊ก *ไม่ตรง* call graph จริง:
> (1) `detect_item_columns_safe` เป็น dead code ไม่ใช่เส้น production → ไม่ได้ทำให้เกิด cascade
> fallback ตามที่อ้าง ; (2) `r_itm008` คิด median **ต่อใบกำกับ** + guard เข้ม (≥5 รายการ,
> qty×price≈amount ≥80%, ratio>50×) — ไม่ได้ pool ข้ามบริษัท.
> การแก้ ITM01 (กลุ่มกฎลำดับ ITM002/013/014) และ ITM008-b (over-sum) ให้ถูกต้อง **ต้อง reproduce
> บนไฟล์จริง 81/103** ก่อน (ไม่อยู่ใน repo) — ห้ามแก้ engine + rebaseline v9.2 แบบเดา. รอไฟล์จริง.

### ADR-016 (ฟีเจอร์/adapter — DECISION GATE ทาง A) — puopuy_ingest.py (reconcile layer)
- สถานะ: **ACTIVE** (Phase 2-3 framework แบบ offline — module ใหม่ ไม่แตะ engine → golden ไม่ขยับ)
- เหตุ: ITM01/ITM008-b รากอยู่ที่ engine (ห้ามแก้/ต้องมีไฟล์จริง) → ทำ adapter layer แทน (ทาง A)
- `puopuy_ingest.py` ให้ "checksum ที่ใบกำกับมีแต่ระบบยังไม่ใช้":
  - `thai_words_to_number` — ยอดตัวอักษรไทย → เลข (หลัก/สิบ/ร้อย/พัน/หมื่น/แสน/ล้าน, เอ็ด, ยี่สิบ,
    บาท/สตางค์/ถ้วน, วงเล็บ TOR) — อ่านไม่ออก → None (fail loud)
  - `normalize_vat_rate` — 0.07 (สัดส่วน) และ 7 (เปอร์เซ็นต์เต็ม SBT) → สัดส่วน
  - `reconcile_totals` — 3 ทาง: grand=net+vat · words=grand/net · line_sum=net · vat=net×rate (tol 1.00 กัน float noise)
  - `classify_row` — words_total/vat/grand_total/subtotal/line_item/blank → **words ไม่ถูกมองเป็น line_item** (ราก ITM01)
  - `ingest_bill` — ยอดไม่ reconcile → `needs_human_review`=True + reason เดียว (ไม่ออก 'ลืมเลขลำดับ')
  - `TEMPLATE_REGISTRY` — SEED 4 template (TKH/SEI/TOR/SBT) จากตาราง 2.1 — **ต้อง validate กับไฟล์จริงก่อน production**
- ทดสอบ `test_puopuy_ingest.py` (31 เคส): Thai-words (รวม 2,608,006.25 + วงเล็บ), VAT 0.07/7, over-sum→MISMATCH, classify
- ✅ golden fixture `d8bcde85…` ไม่ขยับ · ruff/black สะอาด · run_ci.sh [3c-ingest] · full CI เขียว
- ⚠️ **ยังไม่ wire เข้า pipeline** (advisory standalone) — รอ reproduce บนไฟล์จริง 81/103 เพื่อ:
  (1) validate TEMPLATE_REGISTRY (2) เลือกจุด integrate (3) ตัดสิน rebaseline v9.2 ถ้าจะให้กระทบผลตรวจ

### ADR-017 (Quality pass — ยก 4 มิติ <9 → 9) — โซน "ไม่แตะ golden" 2026-06
- สถานะ: **ACTIVE** — งานคุณภาพล้วน (ไม่เพิ่มฟีเจอร์). พิสูจน์แล้วทุก hash ไม่ขยับ.
- ขอบเขต: ยก Maintainability/Consistency/Scalability/Performance จาก 8.0–8.5 → 9.0 โดยใช้
  การ "พิสูจน์/ป้องกัน + cosmetic + test" เป็นหลัก (Tier 0) ; แตะ engine เฉพาะ behavior-neutral.

**สิ่งที่ทำ (ทั้งหมด byte-identical):**
- **Consistency:** ตั้ง `config.APP_VERSION` เป็นแหล่งเดียว → banner (`v8.1/52` → dynamic),
  HTML display + HTML dashboard (`v5.8` → `v{APP_VERSION}`). พิสูจน์ว่า version string อยู่ใน
  **HTML เท่านั้น ไม่อยู่ใน Excel** → `verify_report_det` ยังได้ `fff69fc6…` เป๊ะ.
  + entrypoint ASCII `main.py` (re-export ตัวจริงชื่อไทย ไม่ rename) + รวม alias `_max_sev`→`max_severity`.
- **Maintainability:** `MAINTENANCE.md` (รวมกฎโดยนัย) + แก้ F8 (`gen_explanation(state→subject)` กันบัง
  module `state` ; แก้ caller webverify keyword ด้วย) + ลบ dead double-assignment ใน validators.
- **Scalability:** พิสูจน์ `serial == parallel` บนข้อมูลจริง 106 ไฟล์ (workers 4 และ 8 → `f1ac8421…`)
  + `test_parallel_merge_nonempty.py` บังคับ SYS001 จริง → ทดสอบ merge `_SYSTEM_ISSUES` ที่ไม่ว่าง
  ข้าม worker (จุดที่ sandbox เดิม=0 ทำให้ไม่เคยทดสอบ) → ตรง serial เป๊ะ
  + `test_typo_window.py` ครอบเส้น sliding-window (>500 ชื่อ).
- **Performance:** `profile_baseline.py` + `PERF_BASELINE.md` (artifact ทำซ้ำได้) ชี้ hotspot จริง =
  parse ต่อเซลล์ (`_dic_int_run` 16,553 ครั้ง / `_row_label_match` 35,661 ครั้ง) ~88% ของเวลา —
  **ไม่ใช่ typo** + `test_perf_budget.py` canary กัน regression เชิงอัลกอริทึม.

**ประตูตรวจ (รันแล้วผ่านทั้งหมด หลังแก้):**
- audit/fixture `d8bcde85…` · sandbox 106 `f1ac8421…` · report-det `fff69fc6…` · invariants 4/4
- เทสเดิม 25/25 + เทสใหม่ 4/4 + smoke 27/27 + agents(fixture)

**ยังไม่ทำ (Tier 2 — รอ golden gate บน 81 ไฟล์จริง + อนุมัติ):**
- refactor side-effect cross-check → pure (ลบรากของ non-idempotency ; ปัจจุบันตรึงด้วยเทส call-once)
- ลด hot loop parser เพื่อ perf · ห่อ `try/finally` sqlite ใน webverify

#### ADR-017 (ต่อ) — Tier 2 push: (a) idempotency + (c) sqlite ทำแล้ว ; (b) parser defer
- **(a) cross-check idempotent โดยโครงสร้าง** ✅ — เพิ่ม `validators._append_issue_unique` (เติม issue
  เฉพาะที่ยังไม่มี dict เท่ากันเป๊ะ). ใช้กับ IV003/IV004/DT004/DOC001. พิสูจน์ hash-neutral:
  d8bcde85/f1ac8421/fff69fc6 ไม่ขยับ (content-dedup ไม่ชน issue ของ \"กฎ\" code เดียวกัน เพราะ
  name/detail ต่างกันเชิงโครงสร้าง). อัป `test_crosscheck_idempotency.py`: assert เรียกซ้ำ→คงเดิม (n2==1).
  เพิ่มเข้า coverage_gate → validators branch 93.8%→93.9%.
- **(c) webverify sqlite `conn` ห่อ try/finally** ✅ — กัน leak เมื่อ exception หลุดก่อน close
  (path online/opt-in นอกเส้น golden → ไม่กระทบ hash).
- **(b) ลด hot loop parser (`_dic_int_run`/`_row_label_match`) — DEFER โดยตั้งใจ.**
  เหตุผล: ต้นทุนเป็น intrinsic (pandas indexing / normalize ต่อเซลล์) ไม่มี optimization ที่
  \"เห็นชัดว่า byte-identical\" — materialize/vectorize เสี่ยงผลต่าง subtle ที่ยืนยันกับ 81 ไฟล์ทางการ
  (`ec61907f`) ไม่ได้. perf อยู่ที่ 9 แล้ว และ `parse_all_files_parallel` (พิสูจน์แล้ว byte-identical)
  โจมตี bottleneck นี้ตรง ๆ อยู่แล้ว → การแก้ in-place เป็นความเสี่ยงซ้ำซ้อน. ทำได้เมื่อมี 81 ไฟล์จริง
  + รีวิว diff + ผ่าน regression (ตามวินัย \"ห้ามแก้ engine แบบเดา\").

### ADR-018 (Agent consolidation — ยุบหลายรหัส→ข้อสรุปเดียว) 2026-06
- สถานะ: **ACTIVE** — ชั้น advisory อ่านอย่างเดียว (`issue_consolidator.py`). ไม่แตะ engine/ผลตรวจ →
  golden hash ไม่ขยับ (d8bcde85/f1ac8421 ยืนยันแล้ว).
- ปัญหา: บิล/รายการเดียวกันเด้งหลายรหัสที่ชี้ปัญหาเดียวกัน (เช่นรายการ #2 → ITM004+005+010+011+015)
  → ชีต Error ยาวเกินจริง คนต้องมานั่งสรุปเอง.
- ทำ: `consolidate_bill/consolidate_all` ยุบ issue ต่อ "จุด" (ITM→ต่อรายการจาก '#N'; อื่น→ต่อหมวดระดับบิล)
  → 1 ข้อสรุป/จุด + รหัสที่เกี่ยว + หมวด + ความรุนแรงสูงสุด + bucket (ต้องแก้/ขึ้นกับ master/ข้อสังเกต).
  `build_consolidated_report.py` ออก Excel 4 ชีต (ภาพรวม + 3 เลน).
- ผลบนข้อมูลจริง 106 ไฟล์: ดิบ 782 → consolidated 678 → **ต้องแก้ 169 ใน 157 บิล** (master 139 / review 370).
- ตรึงด้วย `test_issue_consolidator.py` (5 รหัส/รายการ → 1 ข้อสรุป + bucket ถูก) · run_ci [3v].
- หมายเหตุ: นี่คือ "งานที่ชั้น agent ควรทำ" — ปัจจุบันเป็น post-processor แยก (ไม่ผูกใน ReportAgent
  เพื่อคง byte-identical). ถ้าจะฝังลงชีต Error ในรายงานหลัก = แก้ reporting → re-pin `fff69fc6`
  (cosmetic) โดย audit `ec61907f` ไม่ขยับ.

### ADR-019 (Super Ultra Viewer — label ภาษาคน + บล็อกต่อบริษัท) 2026-06
- สถานะ: **ACTIVE** — ชั้น advisory อ่านอย่างเดียว. golden d8bcde85/f1ac8421 ยืนยันไม่ขยับ.
- 3 ชั้น (ไม่แตะ engine): `code_labels.py` (59 รหัส → field+คำคน+เลน) → `viewers.py` (10 FieldViewer
  ตัดสิน ตรง/ผิดต่อช่อง) → `super_ultra_viewer.py` (ประกอบบล็อกต่อบริษัท×เดือน + .txt/.xlsx).
- คำภาษาคน: จาก detail จริงใน /mnt/project (เช่น ITM010/011→'ชื่อสินค้าสะกดผิด', CMP005→'ชื่อบริษัทไม่ครบ',
  DOC001→'วันที่ในบิลไม่ตรงชื่อชีต'). เลิกโชว์ jargon '#2: ...[soft]'.
- ไม่มี master: CMP001/TAX003 → เลน MASTER → ช่องขึ้น '— ไม่มี master ตรวจไม่ได้' (ไม่มั่วว่าผิด/ตรง).
- ผลจริง 106 ไฟล์: 62 บริษัท×เดือน → ต้องแก้ 27 / ควรตรวจ 1 / ตรง 34. บล็อกคลีนจบ 'ตรงครับ ✅'.
- ตรึง: test_super_ultra_viewer.py (13 เคส, รวม ITM010+011 ยุบ label เดียว) · run_ci [3w].
- หมายเหตุ: นี่คือ label/นำเสนอชั้น advisory; ถ้าจะฝังลงรายงานหลัก = แก้ reporting → re-pin fff69fc6
  (cosmetic) โดย audit ec61907f ไม่ขยับ.

### ADR-020 (รายงานพร้อมส่งบัญชี + ปิด Tier-0) 2026-06
- **ADVISORY ยกระดับ**: `code_labels.clean_detail` + worklist รายบิลใน `super_ultra_viewer`
  → แต่ละจุดต้องแก้บอก ไฟล์/วันที่/ชีต/ลำดับ #N/ประเภท/ของเดิม→ที่ควร/ชื่อสินค้า/วิธีแก้.
  ยุบหลายรหัสจุด+ประเภทเดียวกัน (ITM010+ITM011 typo) → 1 บรรทัด (เลือก detail ที่มี 'X→Y').
  Excel เพิ่มชีต "ต้องแก้ รายบิล" (worklist) + "วิธีอ่าน". txt แยก ต้องแก้/พร้อมส่ง. ทั้งหมด read-only.
- **Tier-0 ปิดแล้ว**: (B) `.github/workflows/ci.yml` (offline gate: invariants+fixture+เทส) ;
  (D) ปัก `numpy==2.2.6` ใน constraints (2.4.x ทำ coverage พัง).
- golden d8bcde85/f1ac8421/fff69fc6 ไม่ขยับ. เทส 31/31 (viewer test ครอบ worklist+merge). ADR-019 ต่อยอด.

---

## ADR-018 — Re-baseline golden: corpus 81 → 106 ไฟล์ (P1-a)

**วันที่:** 2026-06-05  •  **สถานะ:** ตัดสินแล้ว (ทำ)

**บริบท:** รายงานตรวจประเมิน v9.2 ชี้ว่า `baseline.json` ค้างที่ corpus 81 ไฟล์
(`ec61907f…`) ขณะข้อมูลจริงต่างชุด → ด่าน golden แดงโดยโครงสร้าง (corpus mismatch)
ไม่ใช่ logic regress. โค้ดให้ผล deterministic ทุก path (พิสูจน์แล้ว).

**ตัดสินใจ:** ตั้ง corpus มาตรฐานใหม่ = ชุดไฟล์ในโปรเจ็ค (`/mnt/project`, 106 ไฟล์ /
836 บิล) แล้ว re-baseline:
`PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 golden_master.py . baseline.json <corpus>`
→ golden ใหม่ = `f1ac8421…`  (แทนที่ `ec61907f…` / 81 ไฟล์)

**ผลที่ยืนยัน (รันจริง):** `run_ci.sh /mnt/project` เขียวทั้งชุด —
engine == agent == baseline = `f1ac8421…`, test_agents step F รันจริง (ไม่ skip),
parallel == serial. fixture golden (`d8bcde85…`) และ report-det (`fff69fc6…`) ไม่กระทบ.

**กัน drift:** guard `CORPUS MISMATCH` ใน regression_full + test_agents derive `n_files`
จาก baseline.json (เลิก hard-code) — ถ้าเปลี่ยน corpus อีก จะแจ้งชัดและให้ re-baseline.

**ย้อนกลับ:** baseline เดิม (81/`ec61907f…`) สำรองไว้ภายนอกรีโป; กู้คืนได้ด้วย
`golden_master.py` บนชุด 81 ไฟล์เดิม.

---

## ADR-019 — Golden ปัจจุบัน = 106 ไฟล์ `/mnt/project` / `73f5bf87…` (supersedes ADR-018) · 81 ปลดระวาง

**วันที่:** 2026-06-05 · **สถานะ:** ACCEPTED · **ขอบเขต golden:** docs/traceability เท่านั้น (engine ไม่แตะ — hash ไม่ขยับ)

**บริบท / ปัญหา (F1 — single source of truth):**
- ที่ผ่านมามี hash 3 ค่าถูกอ้างปนกันว่า "ปัจจุบัน" ทั่ว repo: `ec61907f` (81 ไฟล์, ยุค v9.1), `f1ac8421` (106-เก่า, ADR-018), `73f5bf87` (ค่าใน `baseline.json` จริงตอนนี้). ไม่มีแหล่งความจริงเดียว → ทุกคำกล่าว "frozen" เชื่อถือไม่ได้.
- `README` เคยมี 2 แถวขัดกันเอง (81 ไฟล์/632 บิล **และ** 106 ไฟล์/836 บิล อ้าง `73f5bf87` เหมือนกัน — เป็นไปไม่ได้) และ docstring/VS Code tasks ยังสั่งให้คาดหวัง `f1ac8421` / "81 ไฟล์".
- **คอร์ปัส 81 ไฟล์มาจากโปรเจกต์อื่นที่ถูกยุบไปแล้ว** (ยืนยันโดยเจ้าของระบบ) — เลข "81" เป็นความจำค้างจากอดีต ไม่มีอยู่จริงอีก. คอร์ปัสจริงของระบบนี้ = ไฟล์ใน `/mnt/project` (106 ไฟล์).
- **ช่องโหว่ ledger:** ADR-018 บันทึก 106→`f1ac8421` แต่ `baseline.json` จริง = `73f5bf87` → มีการเปลี่ยนพฤติกรรม `f1ac8421→73f5bf87` บนคอร์ปัสเดิมที่ **ไม่เคยถูกบันทึกเป็น ADR**. สาเหตุที่แท้จริงของ transition นี้ไม่ปรากฏใน-ledger และไม่มี snapshot ยุค `f1ac8421` ให้ diff ในแพ็กเกจนี้.

**ข้อตัดสิน:**
1. **คอร์ปัสทางการ = 106 ไฟล์ `/mnt/project` (834 บิล) อย่างถาวร.** สาย 81 ไฟล์ปลดระวาง (retired) — ไม่ใช่แค่ re-baseline ชั่วคราว.
2. **แหล่งความจริงเดียวของค่า hash = `baseline.json._sha256` (`73f5bf87…`).** เอกสาร/CI ที่ต้องอ้าง "hash ปัจจุบัน" ให้ชี้/อ่านจากไฟล์นี้ ห้าม hardcode literal ใหม่ในร้อยแก้ว.
3. **เลข hash ในเอกสารที่ลงวันที่ไว้** (CHANGELOG_v9_1, AUDIT_v9_x, PASS3, REBUILD_STATUS, ADR เก่า ฯลฯ) = หลักฐานที่ถูกต้อง ณ เวลานั้น → **เก็บไว้ ห้ามเขียนทับ** (เขียนทับ = ปลอม audit trail). แก้เฉพาะพื้นผิวที่อ้างว่า "ปัจจุบัน/operational".
4. supersedes **ADR-018** เฉพาะค่า hash (`f1ac8421` → `73f5bf87`); เหตุผลการย้าย 81→106 ของ ADR-018 ยังคงมีผล.

**สิ่งที่แก้ (golden-risk = ZERO, docs/operational เท่านั้น):**
- `README.md` (รวม 2 แถวขัดกัน → 1 แถวทางการ 106/834/`73f5bf87`), `regression_full.py` docstring, `version_gate.py` docstring, `agents/orchestrator.py` docstring (neutralize literal → `baseline.json._sha256`), `.vscode/tasks.json`×3, `.vscode/launch.json`×1, `DECISIONS.md` L11 + banner.
- **ไม่แก้:** หลักฐานอดีตใน `validators.py:31` / `puopuy_units.py:74` / `analytics.py:228` (ผูกการตัดสินใจ OBJ-1A — เป็นเหตุผล ไม่ใช่ "current golden").
- **เฟส-2 (ค้าง):** sync ร้อยแก้ว handoff — `HANDOVER_TH.md`, `_SESSION_HANDOFF.md`, `QUICKSTART_VSCODE_TH.md` (ยังพูด 81/`ec61907f`).

**กลไกกัน drift (ใหม่):** `test_golden_single_source.py` — อ่าน `baseline.json._sha256` แล้ว assert ว่าพื้นผิว operational ทุกตัวอ้างค่านั้น และ **ไม่มี** hash ค่าอื่นที่อ้างว่าปัจจุบันหลงเหลือ. ถ้าใครแก้ baseline แล้วลืมอัปเดตเอกสาร → test แดงทันที.

**VERIFY (acceptance):**
`PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 regression_full.py . /mnt/project`
→ engine == agent == baseline == `73f5bf87` (**ต้องไม่ขยับ** — ADR นี้เป็น docs-only). และ `python3 test_golden_single_source.py` → PASS.

**ย้อนกลับ:** revert diff เอกสาร/operational ข้างต้น — ไม่มีผลต่อ engine.

**ค้างให้ตัดสิน (ไม่บล็อก):** ถ้าต้องการรู้สาเหตุ `f1ac8421→73f5bf87` ต้อง diff โค้ด/snapshot ยุค `f1ac8421` (ไม่มีในแพ็กเกจนี้) — เชิงฟังก์ชันระบบนิ่ง/deterministic อยู่แล้ว จึงไม่ใช่ blocker.

---

### ADR-021 — Rebaseline `73f5bf87 → 35b2f7c8`: VAT money-math เป็น Decimal+ROUND_HALF_UP (F2-cont) · supersedes ADR-019 เฉพาะค่า hash

**วันที่:** 2026-06 · **สถานะ:** ACCEPTED · **ประเภท:** rebaseline (เปลี่ยน golden — improvement-only ตามนโยบาย)

**บริบท / ปัญหา**
- F2 (ADR-020 ก่อนหน้าในสาย rules) ย้ายเลขเงินใน `rules_engine_rules_c` (r_vat006/007/r_itm) ไป Decimal+ROUND_HALF_UP สำเร็จแบบ hash-neutral แต่ยังเหลือ float money-arithmetic ในเส้น golden 4 จุด (sweep): `parser_p0.py` (VAT บิลรวมข้ามหน้า), `parser_p2.py` ×2 (VAT derived PATCH5/PATCH6), `rules_engine_rules_a.py:406` (qty×price ใน r_itm001).
- float ในเส้นเงินมี 2 ความเสี่ยง: (ก) error การคูณทศนิยม, (ข) `round()` ของ Python = banker's rounding (half-to-even) ≠ กฎปัดเศษบัญชี (HALF_UP). ทำให้ VAT ที่ parser เก็บ "ไม่ตรง" กับ VAT ที่ rules/verification-lenses (หลัง F2) คำนวณ → เสี่ยง inconsistency ภายในเส้นเงิน.

**สิ่งที่ทำ**
- แปลงทั้ง 4 จุดเป็น `(_D(x) * Decimal('0.07')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)` (qty×price ใช้ `_D(qty)*_D(price)`); คง type-gate / threshold / การแสดงผล (`:.2f`) เดิมเป๊ะ; ที่ parser **cast กลับเป็น `float` ตอนเก็บ** เพื่อคงชนิดที่ serialize → hash ขยับเฉพาะเมื่อ "ค่าปัดเศษต่างจริง" ไม่ใช่เพราะชนิดเปลี่ยน.
- `rules_engine_rules_a.py:406` = **hash-neutral** (เหมือน r_itm ใน rules_c). 3 จุด parser = **ขยับ hash**.

**หลักฐาน improvement-only (forensic diff baseline ↔ snapshot ใหม่ ทีละบิล)**
- เปลี่ยน **2 บิลจาก 834** เท่านั้น · ทั้งคู่ต่างกัน **1 สตางค์** ที่ `vat` (+ `total` ที่ derived) · `subtotal` ไม่เปลี่ยน · `issues` ไม่เปลี่ยน (ไม่มี finding โผล่/หาย) · counts ทุกตัวเท่าเดิม (dup/iv_seq/iv_date/typos/companies).
  - `SEE_69_053.xls` sheet16: subtotal=`228386.49999999997` (float artifact ของ 228386.50) → ผลคูณจริง `15987.0549999…` → HALF_UP = **15987.05** (ใหม่ ถูก). เดิม float error ดันแตะ `15987.055` → ปัดผิดเป็น 15987.06.
  - `TSH_69_0514.xls` sheet11: subtotal=`498137.5` (สะอาด) → ผลคูณ `34869.625` เป๊ะ → HALF_UP = **34869.63** (ใหม่ ถูก). เดิม banker's rounding (half-to-even) → 34869.62.
- ทั้งสองเป็น "ปัดเศษถูกต้องขึ้น" ตามกฎบัญชีไทย (HALF_UP) + ทำให้ parser **consistent** กับ rules/verification-lenses หลัง F2 → improvement ล้วน ไม่มี regression.

**การตัดสินใจ**
1. **golden ใหม่ = `35b2f7c8c288faa1b996b4110022a28324ff3c7eb53b9f65b553147fd62138ba`** (regenerate `baseline.json` ผ่าน blessed path `golden_master.py . baseline.json /mnt/project`).
2. supersedes **ADR-019** เฉพาะค่า hash (`73f5bf87` → `35b2f7c8`); เหตุผล single-source / corpus 106 ไฟล์ ของ ADR-019 ยังคงมีผลทั้งหมด.
3. `73f5bf87` เข้าสถานะ **ปลดระวาง** → เพิ่มใน `RETIRED_PREFIXES` ของ `test_golden_single_source.py` (tripwire จะจับถ้าหลงเหลือในพื้นผิวปัจจุบัน).
4. determinism: golden ใหม่ 10/10 รอบ = 1 unique hash.

**พื้นผิวที่อัปเดต (sync กับ baseline.json):** `baseline.json` (regen), `README.md`, `version_gate.py` docstring (neutralize → ไม่มี literal), `.vscode/tasks.json`/`launch.json`, `_SESSION_HANDOFF.md`, `QUICKSTART_VSCODE_TH.md`, `run_ci.sh`, `DECISIONS.md` (banner + ตาราง §1), `test_golden_single_source.py` (RETIRED += 73f5bf87), handoff docs หลัก. เอกสาร dated/narrative อื่น (AUDIT/PASS/MAINTENANCE/MESH/REBUILD/PERF ฯลฯ) คง `73f5bf87` ไว้เป็น "หลักฐานเวลานั้น" ตาม ADR-019 convention (tripwire จงใจไม่สแกน).

**ผลลัพธ์ที่ต้องเห็น (verify):**
→ `regression_full.py . /mnt/project` = engine == agent == baseline == `35b2f7c8`.
→ `test_golden_single_source.py` → PASS. → `test_agents.py` → 38/38. → determinism 10/10 = 1 hash.

**ย้อนกลับ:** restore `baseline.json` จาก backup (`73f5bf87`) + revert 3 จุด parser (rules_a:406 คง Decimal ได้ เพราะ neutral) + revert เอกสาร/tripwire. ไม่มีผลต่อ business logic อื่น.

### ADR-022 (OPT-1 / performance) — parser hot path: _dic_int_run/_dic_find_seq อ่าน M (byte-identical) · supersedes ADR-017(b) defer
- สถานะ: ✅ **CERTIFIED** (2026-06 เจ้าของรัน `regression_full.py . /mnt/project` บน py3.12 →
  `35b2f7c8` **engine==agent==baseline** = golden ไม่ขยับบนข้อมูลจริง 106 ไฟล์. R3/R4 ปิดวงจรครบ.)
- ราก (PERF_BASELINE §Hotspot): `parser_p0._dic_find_seq` เรียก `_dic_int_run` ต่อคอลัมน์ด้วย
  `df.iloc[:,c].dropna()` → hot loop **16,553 ครั้ง/106 ไฟล์ ~3.9s** (~20% ของ parse).
  `detect_item_columns` materialize `M = df.to_numpy(dtype=object)` อยู่แล้ว แต่อยู่ **หลัง** seq-detect.
- การแก้ (เชิงกลไก ไม่แตะตรรกะ): ย้าย `M = df.to_numpy(dtype=object)` ขึ้นบนสุดของ `detect_item_columns`
  แล้วส่งให้ `_dic_find_seq(M, ncols)` / `_dic_int_run(M, c)` ที่อ่าน `M[:,c]` + ข้าม `pd.isna(v)`
  แทน `df.iloc[:,c].dropna()`. per-value `int(float(str(v)))` + ช่วง 1..50 **ไม่แตะ**.
- ความถูกต้อง (byte-identical):
  - `M[r,c] ≡ df.iat[r,c]` เชิงพฤติกรรม — ทีมพิสูจน์แล้ว 836 ชีต/555k cell (ADR §OBJ-PERF step4, บรรทัด 250-252).
    `for v in M[:,c] if not pd.isna(v)` ≡ `df.iloc[:,c].dropna()` (ข้าม null ตามลำดับแถวเหมือนกัน).
  - **`test_dic_int_run_equiv.py`** (ใหม่, run_ci [3e2]): differential vs implementation เดิม (เก็บ inline เป็น oracle) —
    **9,703 คอลัมน์ + 1,528 เฟรม = 0 ต่าง** รวมเส้น exception (เช่น 'inf'→OverflowError ที่
    `except (ValueError,TypeError)` เดิมไม่จับ → โค้ดเดิม crash เหมือนกัน → โปร่งใสแม้ใน error path).
  - fixture golden `d8bcde85…` **ไม่ขยับ** · run_ci 53 ด่านเขียว · pytest 49 · coverage parser line 92.7%.
- perf (synthetic, sandbox py3.11, 800 บล็อก): `detect_item_columns` **6.09× (−83.6%)**.
  เคส no-seq ที่ ADR-017(b) กังวลว่าจะจ่าย to_numpy เพิ่ม → กลับ **8.64× เร็วขึ้น** (to_numpy ครั้งเดียว
  < ~15 `df.iloc[:,c].dropna()`/บล็อก) — ข้อกังวล "redundant risk / tradeoff" ของ ADR-017(b) ไม่เกิดจริง.
- supersedes **ADR-017(b)** (defer hot loop): handoff OPT-1 = high priority; การแก้นี้พิสูจน์ byte-identical
  ได้ "โดยไม่ต้องมี 106 ไฟล์" ผ่าน differential oracle ที่จะยังคุมต่อเมื่อรันบนข้อมูลจริง.
- ⚠ **NEEDS_REAL_DATA_CERT (R3/R4):** ตัวเลข perf จริง + ยืนยัน `35b2f7c8` (regression_full)
  / `fff69fc6` (report-det) ก่อน==หลัง ต้องรันบน 106 ไฟล์จริง (py3.12). ดู OPTIMIZE_REPORT_TH.md §cert.
- ย้อนกลับ: revert 2 helper ใน `parser_p0a.py` + การย้าย M ใน `parser_p0.py` (diff เล็ก, contained,
  ไม่มี call site อื่น). `test_dic_int_run_equiv.py` เป็น additive test (ลบได้ถ้าย้อน).

### ADR-023 (OPT-1b / performance) — parser hot path #2: _label_based_amounts normalize แถวเดียว (byte-identical)
- สถานะ: ✅ **CERTIFIED** (2026-06 เจ้าของรันที่ endpoint 812a9ab บน 106 ไฟล์ py3.12 → `35b2f7c8` engine==agent==baseline)
- ราก (PERF_BASELINE:26): `_row_label_match` = hot loop อันดับ 2 (**35,661 ครั้ง/~2.5s**). `_label_based_amounts`
  (parser_p1) เรียกมัน **3 ครั้ง/แถว** (TOTAL/VAT/SUBTOTAL) ด้วย `continue` short-circuit → แต่ละครั้ง
  recompute `normalize_text(M[r,c]).lower()` ซ้ำ ≤3× ต่อเซลล์ (สำหรับแถวที่ไม่ match = ส่วนใหญ่).
- การแก้: normalize ทั้งแถวครั้งเดียวเก็บ `row_norm` (เซลล์ไม่ว่าง ตามลำดับคอลัมน์) แล้วเช็ก 3 label set
  ด้วย `any(_label_in_text(s, L) for s in row_norm)`. `_row_label_match` เดิม **ไม่ถูกแตะ** (ยัง public/re-export).
- ความถูกต้อง (byte-identical): `normalize_text` เป็น **total** (None/NaN→'' ; อื่น `str()` — ไม่ throw)
  → precompute เต็มแถวให้ผลเท่า short-circuit เดิมทุก path (ไม่มีเส้น exception ใหม่). `any(...)` ตามลำดับ
  คอลัมน์ ≡ `_row_label_match` (True ที่ match แรก). **`test_label_amounts_equiv.py`** (run_ci [3e3]):
  differential vs โค้ดเดิม (ใช้ `_row_label_match` ที่ไม่ถูกแตะเป็น oracle) = **2,503 บล็อก, 0 ต่าง**.
- perf (synthetic): ~**1.11× (−10%)** บน `_label_based_amounts` (ส่วนที่เหลือ = `_rightmost_num` ที่ยังสแกน).
- fixture `d8bcde85` ไม่ขยับ · run_ci เขียว · pytest 51 · ย้อนกลับ: revert `_label_based_amounts` เดียว (contained).

### ADR-024 (OPT-2 ก / maintainability) — auto re-export internal parser chain · supersedes ADR-017(c) guard-only
- สถานะ: ✅ **CERTIFIED** (2026-06 เจ้าของรันที่ endpoint 812a9ab บน 106 ไฟล์ py3.12 → `35b2f7c8` engine==agent==baseline ; chain integrity 216 ลิงก์ + reachability สะอาด)
- ราก (B2/[F3]): chain `parser_p0a→p0→p1→p2` ทำ explicit re-export ด้วยมือ ~57–95 ชื่อ/ชั้น →
  ลบ/ย้าย 1 สัญลักษณ์ต้นน้ำ = ImportError ทั้ง chain (แก้ 6+ จุด). blast radius สูง.
- เจ้าของสั่ง "เอาแบบกระโดดถึง 9 ไม่เอาขยับนิดเดียว" → เลือก **(ก)** (ไม่ใช่ (ค) guard-only ของ ADR-017).
  (ข) ยุบโมดูล = **ชน file-size gate ≤600 LOC** (รวม ~2,500 LOC) → ทำไม่ได้โดยไม่ถอดเกต.
- การแก้: `parser_reexport.py` → `reexport(upstream, globals(), exclude=...)` ดึง `upstream.__all__`
  เข้า namespace ปลายน้ำ โดย **bind object เดิม (getattr)** — **zero-star (ไม่ใช่ `import *`)** กันราก
  surface-leak เดิม (annotations รั่ว, บรรทัด 120). edge ภายใน: p0←p0a(57), p1←p0(64) full ;
  p2←p1(95) exclude 5 (Decimal/ROUND_HALF_UP จาก stdlib + 3 helper M8 ภายใน p1). **parser.py คง
  explicit __all__ โดยเจตนา** (public API = contract ต้อง curate มือ ไม่ใช่ debt).
- ความถูกต้อง (byte-identical): bind object เดิม → โค้ดที่รันคือ object เดียวกันทุกตัว → golden ไม่ขยับ.
  surface พิสูจน์: re-export count 57/64/95 + `__all__` 64/100/118 **เท่าเดิมเป๊ะ** ; identity
  `downstream.X is upstream.X` ครบ ; `parser.__all__` เข้าถึงครบ ; fixture `d8bcde85` ไม่ขยับ.
  **`test_parser_chain_integrity.py`** อัป (run_ci [3x8b]): C1 auto-edge **216 ลิงก์ completeness+identity**
  + C1b explicit-edge (parser 70) + C2 public-contract (68). reachability: `parser_reexport` reachable (ไม่ floating).
- **B2 ไม่ retire:** `detect_item_columns_safe`/`_compute_col_confidence` — ADR-015 จงใจชุบชีวิต + มีเทสตรึง.
- ย้อนกลับ: revert import header 3 ไฟล์ (p0/p1/p2) + ลบ `parser_reexport.py` (contained). cert แยก commit (812a9ab).

### ADR-025 (coverage push — Test/Safety) — parser branch 83→90% + บังคับ branch≥85 (golden-neutral)
- สถานะ: **ACTIVE** (เทสล้วน — golden ไม่ขยับ ไม่ต้อง cert)
- ราก: coverage_gate วัด parser family branch 83.0% (< floor 85 ที่ ADR ตั้ง). OPT-1b ทำให้
  `_row_label_match` orphan จาก caller → coverage บางกิ่งหลุดเพิ่ม.
- การแก้: `test_parser_branch.py` (97 เคส, run_ci [3e4]) — unit ตรง helper edge/error path
  (_pick_best_iv scoring, taxid/branch scan, _reconcile_amounts, _pb_* builders,
  _compute_col_confidence, check_iv_format เกณฑ์ 2/3, row-helper ที่ orphan). เรียก helper ตรง
  ไม่แตะ audit core → **fixture d8bcde85 ไม่ขยับ**.
- ผล (วัดจริง): parser branch **83.0→90.3%** · line 91.9→96.3% ; TOTAL branch **86.0→89.0%** · line 94.7→96.5%.
- codify: run_ci [10] บังคับ **line≥90 + branch≥85** (เดิม branch วัดเฉย ๆ). ทุกกลุ่มผ่าน
  (parser 90.3 / rules_engine 85.6 ตึงสุด / validators 93.9 / units 100) → กัน branch regression เงียบ.

### ADR-026 (รีพอร์ตลูกค้า / precision) — Precision Council 10 ผู้ตรวจ + รีพอร์ต 2 ชั้น
- สถานะ: **ACTIVE** (advisory/READ-ONLY — golden d8bcde85/35b2f7c8 ไม่ขยับ)
- เหตุ: สรุปต่อบริษัท (super_ultra_viewer) = ฉบับ "ส่งตรงลูกค้า ผิดไม่ได้". เดิมมี 34 lenses +
  ConfidenceAgent + ultra_agent แต่ยังไม่มี "ด่านสุดท้ายเฉพาะรีพอร์ตลูกค้า" ที่ตัดสินว่า
  จุดที่จะรายงาน "ชัดพอส่งไหม" (โดยเฉพาะ fuzzy typo ต้องผิดแบบชัด).
- ทำ: `report_precision.py` — สภา 10 ผู้ตรวจ deterministic (typo severity / unit sanity /
  taxid checksum / name spacing / seq gap / amount presence / subtotal reconcile / empty items /
  cross-consensus / master echo) reuse ตรรกะ core → vote CONFIRM/RECHECK/ABSTAIN → tier.
- ผู้ใช้เลือก **(ค) 2 ชั้น**: clear→รีพอร์ตหลัก ; soft→บรรทัด "ตรวจตาเพิ่ม" + footer
  "ตรงครับ (มี N จุดให้ตรวจตาเพิ่ม)" (precision สูง, ไม่ทิ้ง/ไม่ซ่อนของจริง).
  fuzzy: ITM010=clear ; ITM011 "ใกล้เคียง (ตรวจสอบ)"=soft ; CMP001 ชื่อ-vs-master=soft (precision-first).
- ไม่ใช่ ML/training — rule-based โปร่งใส ("เทรน" = คาลิเบรต threshold ด้วยเทสเคส).
- ตรึง: `test_report_precision.py` (20 เคส, run_ci [3w0]) + test_super_ultra_viewer +5 เคส (soft/clear).
  reachability สะอาด (report_precision reachable ผ่าน super_ultra_viewer) · golden ไม่ขยับ ·
  coverage ไม่ตก (parser 90.3 / total 89.0). คะแนน 10 ด้านไม่ดรอป (Test/Safety/Correctness หนุนขึ้น).
- v2 (note): re-surface ITM015 (หน่วยผิด เช่น เหล็กเพลท/เส้น) เข้าสรุปเมื่อ council ยืนยัน — ตอนนี้ยัง _HIDE_IN_SUMMARY.

### ADR-027 (B1 — TAX008: เลขภาษีเดียวกันแต่ชื่อบริษัทต่างกัน) — **PENDING REBASELINE (golden-affecting)**
- สถานะ: **PROPOSED** — โค้ด+เทสพร้อม, รอเจ้าของ rebaseline golden บน corpus จริง (Claude Code ห้าม fabricate hash).
- เหตุ: เลขภาษี 13 หลักตัวเดียวถูกใช้กับ "คนละบริษัทกันจริง" ข้ามบิล (คลาส เจ.อาร์./ฉีหยวน) = สัญญาณสวมเลข/ปลอม.
  ตรวจได้ **แม้ไม่มี master** (internal consistency ข้ามทั้ง corpus).
- ทำ: `r_tax008` (rules_engine_rules_c) — group ด้วย clean_tax_id ; ฟ้องเมื่อ tax เดียวจับคู่ชื่อ normalize
  ที่ "ต่างกันชัด ≥ 2 ชื่อ". กัน FP: เกณฑ์แนว CMP001 (exact/substring ย่อ-เต็ม/fuzz.token_sort_ratio ≥ 85) +
  ตัด marker สาขา/(สำนักงานใหญ่). cross-bill ผ่าน ctx['all_bills_for_iv_check'] (เหมือน DOC003).
  conservative: tax ไม่ครบ 13 หลัก / ไม่มี all_bills_ref / ชื่อขาด → เงียบ.
- register: RULES (CRITICAL, enabled) · code_labels.MAP (F_TAX, FIX) · config.FIELD_CODES (เลขภาษี) ·
  FIELD_LAYOUT (prefix TAX auto) · ultra_agent.FUZZY_CODES (ตรวจอิสระต่อบิลไม่ได้ → ควรตรวจซ้ำ).
- behavior ที่เปลี่ยน: เพิ่ม issue TAX008 บนบิลที่เลขภาษีถูกใช้กับชื่อต่างกันจริง → **golden เปลี่ยนบน corpus จริง**.
- ผลต่อ golden: fixtures = ไม่ขยับ (d8bcde85 — fixture ไม่มี pattern นี้ = ไม่มี FP) ; corpus จริง 35b2f7c8 = **จะเปลี่ยน**.
- เทส: `test_tax008.py` (ยิงเมื่อชื่อต่างจริง ; เงียบเมื่อต่างแค่เว้นวรรค/สาขา/ย่อ-เต็ม/tax ไม่ครบ).
- rebaseline (เจ้าของ): รัน regression_full.py บน corpus จริง → ตรวจจำนวน/ความถูกต้องที่ยิง → golden_master.py . baseline.json → อัปเดต GOLDEN.md/banner.

### ADR-028 (B2 — ADDR006: รหัสไปรษณีย์ ↔ จังหวัด ไม่สอดคล้อง) — **PENDING REBASELINE (golden-affecting)**
- สถานะ: **PROPOSED** — โค้ด+เทส+ตารางข้อมูลพร้อม, รอเจ้าของ rebaseline.
- เหตุ: รหัสไปรษณีย์ 5 หลักต้องสอดคล้องจังหวัดในที่อยู่ (ฟอร์แมตถูก ≠ ตรงพื้นที่). ตรวจได้ **แม้ไม่มี master**.
- ทำ: `thai_postal.py` — ตาราง prefix 2 หลัก → จังหวัด (data-driven, **derive จากข้อมูลจริง 7,436 ตำบล**
  ของ thailand-geography-data/thailand-geography-json ครบ 77 จังหวัด ; ไม่เดาจากความจำ).
  `r_addr006` (rules_engine_rules_c) ฟ้องเมื่อ "ในที่อยู่ระบุจังหวัด X แต่ไม่มีไปรษณีย์ใด prefix ตรง X เลย".
- กัน FP/ทับซ้อน: map เป็น 'จังหวัด → เซ็ต prefix' (บางจังหวัดหลาย prefix: เชียงใหม่=50,58) ;
  **เว้นกรุงเทพฯ/กทม.** (ADDR005 ดูแลช่วง 10xxx แล้ว) ; ดึงจังหวัด/ไปรษณีย์ไม่ได้/กำกวม → เงียบ.
- register: RULES (WARNING, enabled) · code_labels.MAP (F_ADDR, CHECK) · config.FIELD_CODES (ที่อยู่) ·
  FIELD_LAYOUT (prefix ADDR auto) · ultra_agent.FUZZY_CODES.
- ผลต่อ golden: fixtures = ไม่ขยับ ; corpus จริง 35b2f7c8 = **จะเปลี่ยน**.
- เทส: `test_addr006.py` (ยิงเมื่อขัดชัด ; เงียบเมื่อสอดคล้อง/ไม่มีจังหวัด/ไม่มี zip/เป็น กทม./มี zip ถูกอยู่ด้วย).
- หมายเหตุ: ตาราง `PROVINCE_POSTAL_PREFIXES` แก้ไข/เพิ่มได้ (dict) — เจ้าของควร review ก่อน rebaseline.

### ADR-029 (B3 — BR004: เทียบสาขากับ master) — **PENDING REBASELINE (golden-affecting)**
- สถานะ: **PROPOSED** — โค้ด+เทสพร้อม, รอเจ้าของ rebaseline.
- เหตุ: master เก็บ branch ไว้แต่ไม่มีกฎเอามาเทียบ (BR001/BR002 เช็คแค่รูปแบบ/มีหรือไม่ ไม่ใช่ "ตรง master").
- ทำ: `r_br004` (rules_engine_rules_a) — normalize สาขา 2 ฝั่ง (branch_no 5 หลัก / label 'สำนักงานใหญ่'→00000 /
  'สาขา NNNNN') แล้วฟ้องเมื่อต่างกันชัด. ส่วน "ไม่มี master / master ไม่มี branch" จัดการที่ honesty A1
  (ช่องสาขาขึ้น "ตรวจไม่ได้") — **ไม่กระทบ golden**. BR004 = เฉพาะเมื่อมี master + master มี branch.
- conservative: m=None / master ไม่มี branch / บิลระบุสาขาไม่ชัด → เงียบ.
- register: RULES (ERROR, enabled) · code_labels.MAP (F_BRANCH, FIX) · config.FIELD_CODES (สาขา) ·
  FIELD_LAYOUT (prefix BR auto) · ultra_agent.MASTER_CODES (เทียบ master → ควรตรวจซ้ำ offline).
- ผลต่อ golden: fixtures = ไม่ขยับ ; corpus จริง 35b2f7c8 = **จะเปลี่ยนเฉพาะเมื่อ master มี branch ที่ขัดกับบิล**.
- เทส: `test_br004.py` (ยิงเมื่อสาขาต่าง master ; เงียบเมื่อตรง/ไม่มี master/ข้อมูลไม่ชัด).

### ADR-030 (B4 — DT001 filename-period) — **NO CHANGE (สอบแล้วไม่พบบั๊ก)**
- สถานะ: **CLOSED / golden ไม่ขยับ** — สอบสวนตามคำขอแล้ว ไม่แก้ parser (priority ต่ำ + ไม่มีบั๊กจริง).
- ข้อสงสัย (จาก work order): `_filename_period_ce` อ่าน `XXX_69_012.xls` เป็น "เดือน 12" (012→12) ผิด.
- หลักฐาน (forensic, ทดสอบจริง): `_filename_period_ce('XXX_69_012.xls')` → **(2026, 1)** = มกราคม **ถูกต้อง**
  (regex `(\d{1,2})` จับ '01' แล้วเหลือ '2' เป็นชุดที่ 2 — ตรงกับ "พฤติกรรมที่ควรเป็น" ที่ work order ระบุเอง).
  ทดสอบเพิ่ม: `_69_12`→ธ.ค. / `_69_01`→ม.ค. / `69.05`→พ.ค. ถูกทุกเคส.
- สรุป: บั๊ก `0NN→NN` **ไม่มีอยู่จริง** — DT001 (NOTE) ที่ over-fire (ถ้ามีบน corpus จริง) = **บิลคร่อมเดือนจริง**
  (วันบิล ≠ งวดชื่อไฟล์ โดยชอบ) ซึ่งเป็นสิ่งที่ DT001 ตั้งใจ flag เป็นหมายเหตุ. จึงไม่แก้ parser → golden ไม่ขยับ.

### ADR-031 (D1 — IV007: เลขใบกำกับ "ไม่สมเหตุสมผล" absolute validity) — **PENDING REBASELINE (golden-affecting)**
- สถานะ: **PROPOSED** — โค้ด+เทสพร้อม, รอเจ้าของ rebaseline golden บน corpus จริง (Claude Code ห้าม fabricate hash).
- เหตุ (forensic — TNT_69_01.xls): เลขที่จริง "01954" (r5c20) แต่ parser ดึง iv_number = "0000000002"
  (เศษ float ของ VAT "1416233.0000000002"). IV002 เป็น consistency-only (เทียบความยาว/เสียงข้างมากในไฟล์)
  → ทั้งไฟล์เป็นเลขขยะคล้ายกันก็ "consistent" เลยเงียบ. ต้องมี "absolute validity" จับเลขขยะตรง ๆ.
- ทำ: `r_iv007` (rules_engine_rules_c) — ฟ้องเมื่อ iv (ค่าสัมบูรณ์ ไม่พึ่ง master/บิลอื่น):
  (ก) ศูนย์ล้วน  (ข) เลขเดียวซ้ำทั้งหมด (≥4 หลัก)  (ค) placeholder = ≥8 หลักแต่ตัดศูนย์นำเหลือ ≤2 หลัก
  ('0000000002'→'2')  (ง) ตรงเศษทศนิยมของยอดเงิน (subtotal/vat/total) = parser คว้าเศษ float.
  conservative: เลขรูปแบบสมเหตุผล (หลายหลักไม่ซ้ำ เช่น IV6905000279/01954) → เงียบ ; ว่าง → ปล่อย IV005.
- register: RULES (ERROR, enabled) · code_labels.MAP (F_IV, FIX) · config.FIELD_CODES (เลขที่ IV) ·
  FIELD_LAYOUT (prefix IV auto) · ultra_agent.RELIABLE_CODES (absolute → ยืนยันอิสระต่อบิลได้).
- ผลต่อ golden: fixtures = ไม่ขยับ (ไม่มี FP บน fixture) ; corpus จริง 35b2f7c8 = **จะเปลี่ยน** (บิลเลขขยะ เช่น TNT).
- เทส: `test_iv007.py` (ยิง: ศูนย์ล้วน/ซ้ำ/placeholder/เศษยอด ; เงียบ: เลขจริง/สั้น/ว่าง/อักษรล้วน).
- coverage: เพิ่ม test_iv007 (+ test_tax008/addr006/br004) เข้า coverage_gate.TESTS → rules_engine branch ≥85% คงผ่าน.

### ADR-032 (D2-GUARD — post-extraction: ปฏิเสธ iv ขยะ/มาจากยอดเงิน → ว่าง) — **PENDING REBASELINE (golden-affecting)**
- สถานะ: **PROPOSED** — โค้ด+เทสพร้อม, รอเจ้าของวัดผล (จำนวน iv ที่เปลี่ยน) บน corpus จริงก่อน rebaseline.
- **ตัดสินแล้ว (เจ้าของ): ทำ "GUARD เท่านั้น" แบบ post-extraction** — D2-EXTENSION (จับเลขไม่ขึ้นต้น IV เช่น
  '01954') ⏸️ เลื่อน (golden กว้าง/ตรวจสอบไม่ได้ถ้าไม่มี corpus) · D3 ❌ ไม่ทำ (โซน ⛔ ห้ามแตะยอด, ดู ADR-033).
- เหตุ (root cause ของ D1): parser เลือก iv จาก `_pick_best_iv` ซึ่งคว้า '0000000002' จากเซลล์ VAT
  '1416233.0000000002' (เศษ float). guard ตัดต้นตอ (D1 = flag ชั้นกฎ, D2 = ปฏิเสธชั้น parse).
- ทำ (**post-extraction validation — ไม่แก้ flow การ extract**): `core_utils.validate_iv_post(bill)` เรียกใน
  `parse_file` (parser_p2) **หลัง parse ครบ** (มี iv + ยอด) → ปฏิเสธ iv ที่ (ก) `iv_digits_garbage` (ศูนย์ล้วน/
  เลขเดียวซ้ำ/placeholder) (ข)(ค) `iv_amount_fragment` (ตรง/เป็นเศษทศนิยมของ subtotal/vat/total) → ตั้ง
  `iv_number=''` (+raw). flow extract เดิมไม่ถูกแตะ (ปลอดภัย/คาดเดาได้กว่าการ skip กลาง extraction).
  `iv_digits_garbage`/`iv_amount_fragment` อยู่ใน `core_utils` = **single-source** ใช้ร่วม r_iv007 (D1).
- ความซื่อสัตย์: iv ขยะ → ว่าง → IV005 (ไม่มีเลขที่) จับ ; ถ้าหลุดถึงชั้นกฎ → IV007 (safety-net) จับ —
  **โชว์ "ไม่มี/เลขเสีย" ตรง ๆ ดีกว่าโชว์เลขผิด** (ตรงหลักการ "ทุก agent ต้องซื่อสัตย์").
- ขอบเขตผลกระทบ: bounded — เปลี่ยน iv เฉพาะบิลที่ปัจจุบัน iv เป็นเลขขยะ (ชุดเดียวกับที่ IV007 ฟ้อง).
- ผลต่อ golden: fixtures = ไม่ขยับ (golden d8bcde85 + parse canary นิ่ง — fixture ไม่มี iv ขยะ) ;
  corpus จริง 35b2f7c8 = **จะเปลี่ยนเฉพาะบิล iv ขยะ** (iv ว่าง → กระทบ IV001/003/005/DOC003 ของบิลนั้น).
  เจ้าของต้องวัด "iv เปลี่ยนกี่บิล" บน corpus จริงก่อน rebaseline.
- เทส: `test_iv_parser_guard.py` (post-extraction: เศษ float/ขยะ → iv ว่าง ; iv จริง → ไม่แตะ ; parse_file เรียก guard).

### ADR-033 (D3 — sanitize เศษ float ในเซลล์ยอดเงินตอน parse) — **WON'T DO (ตัดสินแล้ว: ไม่ทำ)**
- สถานะ: **REJECTED / NOT IMPLEMENTED** — เจ้าของตัดสิน "ไม่ทำ" (priority ต่ำสุด + เสี่ยง golden สูง + ใกล้ ⛔).
- **ทางเลือกที่ทำได้แทน (golden-safe):** ถ้าต้องการให้ "ยอดใน Excel ดูสะอาด" (ไม่โชว์ `.0000000002`) →
  ตั้ง **number format** ของเซลล์ Excel เป็น 2 ตำแหน่ง (`'#,##0.00'`) ที่ **ชั้นแสดงผลเท่านั้น** — ไม่แตะ
  ค่าที่เก็บ ไม่กระทบ golden (คนละเรื่องกับ sanitize ค่าจริง). จัดเป็นงานกอง C ได้ถ้าเจ้าของต้องการ.
- ข้อเสนอ: ปัด/normalize ตัวเลขเงินที่อ่านจาก Excel ให้ ≤2 ตำแหน่งตอน parse (เช่น 1416233.0000000002 →
  1416233.00) ตามนโยบาย Decimal/ROUND_HALF_UP — ตัดต้นตอเศษ float ที่ระดับแหล่ง.
- เหตุที่ "ยังไม่ทำ" (ตัดสินแบบ conservative):
  1. **เสี่ยง golden สูงและกว้าง** — เปลี่ยนค่าเงินดิบกระทบ VAT001/002/003 ของหลายบิลทั่ว corpus
     (มากกว่า D2 ที่ bounded เฉพาะบิล iv ขยะ).
  2. **ใกล้โซน ⛔ "ห้ามแตะ ยอด VAT/total/subtotal"** — แม้ D3 แตะค่า "ดิบ" ไม่ใช่ "derived" แต่ผลลัพธ์
     ป้อนเข้า VAT-math โดยตรง → ควรให้เจ้าของยืนยันก่อนชัด ๆ.
  3. **คุณค่าส่วนเพิ่มต่ำ** — บั๊กจริง (iv ขยะ) แก้ครบแล้วด้วย D1 (flag) + D2 (root cause). D3 เป็นแค่
     "ความสะอาดของตัวเลข" (ยอดดูสวย) — ไม่ใช่ correctness ที่จำเป็น.
- ถ้าเจ้าของอนุมัติรอบถัดไป: ทำที่จุดอ่านเลขเงิน (parser_p2 `_pb_finalize_amounts`/จุด OCR ตัวเลข) +
  negative fixture (เซลล์มีเศษ float → ยอดถูกปัด ≤2 ตำแหน่ง) + วัดผล golden บน corpus จริง + ADR sign-off.

### ADR-034 (MATCH-GUARD — กัน fuzzy ผูกข้ามบริษัท) — ACCEPTED, IMPLEMENTED 2026-06-10
- ปัญหา (พบจากรันจริง corpus + master จริง 1 บริษัท): `fuzz.partial_ratio` ให้คะแนน 75-80 จากคำอุตสาหกรรมร่วม
  ("...คอนสตรัคชั่น จำกัด") → บิลของ 4 นิติบุคคลอื่น (ทีเค 2514 / หนิงโป หงหยวน / ที บีท / ไวดู) รวม 81 บิล
  ถูกผูกกับ master ฉีอัน แล้วโดน CMP001 + TAX003("อันตราย") + ADDR001 = false positive ตรงเข้ารายงานลูกค้า.
- ตัดสิน: guard ที่ bind site เดียว (rules_engine.run_rules): master≠None และ score<90 และเลขภาษีบิลครบ 13 หลัก
  ≠ เลขภาษี master → unbind เป็น '(ไม่พบใน master)' (A1 honesty แสดง "ตรวจไม่ได้").
  ชื่อเหมือนมาก ≥90 (รวม exact/substring=100) + เลขต่าง → **คงผูก** เพื่อให้ TAX003 จับเคสสวมเลข (คลาสฉีหยวน).
  เลขบิลอ่านไม่ได้ → พฤติกรรมเดิม (conservative). threshold 90 เป็น literal มี comment กำกับที่จุดใช้.
- หลักฐาน (corpus 106 ไฟล์/834 บิล): CMP001 81→0, TAX003 81→0, ADDR001 81→0, matched 161→80;
  ฉีอันจริง 80 บิล score=100 ไม่กระทบ; fixture golden d8bcde85 ไม่ขยับ; corpus golden ขยับ → ADR-036.
- เทส: `test_match_guard.py` (8 เคส) ผูก CI ขั้น [3x12].

### ADR-035 (Ultra report timestamp → injectable clock) — ACCEPTED, IMPLEMENTED 2026-06-10
- ปัญหา: `company_summary_ultra.txt` ใช้ `datetime.now()` → hash รายงานเปลี่ยนข้ามนาที (จับได้จากเทส 5 รอบ:
  ต่างแค่บรรทัด "สร้างเมื่อ" 1/879 บรรทัด).
- ตัดสิน: ใช้ `audit_today()` (pin ได้ด้วย PUOPUY_AUDIT_DATE) แบบเดียวกับ audit core — ชั้น advisory เท่านั้น
  ไม่กระทบ audit golden. ผล: เทส 5 รอบ ultra hash นิ่ง (85047d0b…) ตรงกันทุกรอบ.

### ADR-036 (REBASELINE golden 106 ไฟล์: 35b2f7c8 → d3c01886) — EXECUTED 2026-06-10
- เหตุ: เปิดใช้งานจริงของ batch ที่สะสมรอ rebaseline: B1 TAX008 / B2 ADDR006 / B3 BR004 / D1 IV007 /
  D2-guard (ADR-031/032 ชุดรอบ 12) + MATCH-GUARD (ADR-034) — ทุกตัวมี negative-fixture test ใน CI.
- วิธี: รันจริงบน corpus ทางการ /mnt/project (106 ไฟล์/834 บิล) ด้วย PYTHONHASHSEED=0
  PUOPUY_AUDIT_DATE=2026-06-02 ผ่าน golden_master.py **2 รอบ digest ตรงกัน** → ติดตั้ง baseline.json;
  สร้าง canary_baseline.json (corpus จริง) ครั้งแรก; `regression_full.py . /mnt/project` ผ่าน:
  engine == agent == baseline ✅. ค่าใหม่: `d3c0188684433253660edd81c985b01c7a38c1c2657861c7025a38769d405802`.
- 35b2f7c8 ปลดระวาง (ดูตาราง GOLDEN.md); พื้นผิว operational ทั้งหมด sync แล้ว (test_golden_single_source ✅);
  fixture golden d8bcde85 + report-det fixture ไม่เปลี่ยน. หมายเหตุ: audit hash ไม่ผูกเครื่อง (machine-independent,
  ยืนยันแนวทางเดิม) — เครื่องเจ้าของรัน regression_full ครั้งแรกควรได้ค่าเดียวกันด้วย version pins เดิม.

### ADR-037 (v9.3 PORTABLE GOLDEN — P0-A + re-baseline) — EXECUTED 2026-06-10
- ปัญหา (พิสูจน์เชิงประจักษ์): build_snapshot ทำ basename เฉพาะ file_names — ทุก bill พก 'filepath'
  เต็ม + summary พก path → baseline ฝัง path 1,668 จุด → hash ผูกตำแหน่งโฟลเดอร์
  (corpus เดียวกันคนละ path = คนละ hash; ย้ายเครื่อง/โฟลเดอร์ = false regression; hash ที่ rebase
  บนเครื่องหนึ่งจะ reproduce บนเครื่องอื่นไม่ได้เลย).
- แก้: sanitizer จุดเดียวใน golden_snapshot.build_snapshot (ครอบทั้งเส้น engine/agent) —
  _path_prefixes(file_list) + _strip_paths (filepath→basename, สตริงอื่น prefix-strip, คืนสำเนา
  ไม่ mutate live bills) + fail-closed assert (เหลือ prefix ใน blob → raise).
- หลักฐาน: corpus 106 ไฟล์วาง 2 path → hash เท่ากัน + snapshot byte-identical ; field-diff เทียบ
  baseline เก่า = ต่าง 1,668 จุด "ทั้งหมดเป็นเรื่อง path ล้วน" (semantic equivalence — ไม่มีอย่างอื่นเปลี่ยน) ;
  test_report_det/verify_report_det เขียว (ไม่กระทบ live bills/รายงาน).
- Re-baseline: fixture d8bcde85 → 269ddaed0c6d… ; ข้อมูลจริง d3c01886 (path-bound, ปลดระวาง) →
  `d6b23d127999e62c2a898554c012e60c1d8731dffec212770569fa6ec8818173` (golden_master ×2 ตรงกัน,
  regression_full: engine==agent==baseline ✅, canary re-baseline พร้อม data_dir แบบ portable).
  หมายเหตุ: ตั้งแต่ค่านี้ golden reproduce ข้ามเครื่อง/โฟลเดอร์ได้ เมื่อ corpus เนื้อหาเดียวกัน + pins เดิม.
- งานร่วมรอบ v9.3: rules_c เส้นตัดสินเงิน (r_vat008 เพดาน 10000 / sub≈total tol 1, r_vat009 sub==0)
  ย้ายเป็น Decimal โดยคง float() เป็น type-gate (acceptance เดิมเป๊ะ) — พิสูจน์ hash-identical บน
  corpus เต็ม + fixture ; จุด float ที่เหลือทุกจุดติดป้าย F2-exempt ; เทสขอบ test_rules_c_decimal_gates.py
  ผูก CI [3x13] + coverage_gate.TESTS. verify_golden เพิ่ม argparse (--baseline/--data) แบบ
  backward-compatible + echo config ลง stderr ทั้งสอง CLI (กันสับ arg).

### ADR-038 (F-MONEYIV v9.3.1 — กัน "ยอดเงินบนบิล" ถูกอ่านเป็นเลขที่เอกสาร) — ACCEPTED, IMPLEMENTED 2026-06-17 — **NO REBASELINE (golden-neutral พิสูจน์ด้วย dormancy)**
- ปัญหา (ลูกค้ารายงาน — ไฟล์ SHS 69.05 เพิ่ม 21 บิล): รายงานฟ้อง false positive 4 จุด —
  (1) "เลขที่เอกสาร 200500 ใช้ซ้ำ 04/05 & 12/05" (จริง: 200,500 = ยอดก่อน VAT, doc จริง '05070'/'05309' คนละชุด),
  (2) "202000 ฝังงวด 2020" (จริง: 202,000 = preVAT วันที่ 7, doc '05171'),
  (3) "204000 ฝังงวด 2040" (จริง: 204,000 = preVAT วันที่ 13, doc '05351'),
  (4) "05380/05414/05642/05677/05715 รีเช็ค" (จริง: doc เรียงปกติ ไม่มี anomaly).
- root cause (forensic, อ่าน source จริง): _parse_block ตั้ง header_end = row_start+20 → ชีต 19 แถว
  ถูกสแกน "ครอบทั้งชีตรวมแถวยอดรวม". _pick_best_iv รับเลขล้วน ≥5 หลัก (score=len×2+15) →
  subtotal 6 หลัก '200500' (score 27) ชนะเลขเอกสารจริง 5 หลัก '05070' (score 25). money-guard เดิม
  (\.\d) ไม่ติด เพราะ pandas อ่านยอดที่ลงตัวเป็น int (สตริงไม่มี '.0'). ชีตที่ "รอด" รอดโดยบังเอิญ —
  เศษ float ของ VAT/total (เช่น 13535.900000000001) สร้าง candidate ขยะคะแนนสูงกว่า → ทริป
  iv_digits_garbage → apply_iv_lastresort_if_needed กู้ '05380' กลับมาถูก. ทั้ง 4 false positive
  เป็น collateral ปลายน้ำของ misread จุดเดียวนี้ (IV003/DT004-period/IV004 ฟ้องตาม).
- ทางเลือกที่ตัดทิ้ง: แก้ score ของ _pick_best_iv (เสี่ยง golden ทั้ง corpus) ❌ ; แตะยอดเงินตอน parse
  (ชน ADR-033 WON'T DO — โซนห้ามแตะยอด) ❌. เลือก: post-guard เชิง business-invariant หลัง finalize.
- แก้ (surgical, leaf module): เพิ่ม reject_iv_equal_amount(df, result, row_start, header_end, ncols)
  ใน parser_guards.py — บังคับ invariant "เลขที่เอกสาร ≠ ยอดเงินใด ๆ บนบิลเดียวกัน" (subtotal/vat/
  total + ยอดรายการ; เทียบเฉพาะค่าจำนวนเต็มลงตัว via _bill_amount_strings). ถ้า iv == ยอด → ล้าง iv
  แล้วเรียก apply_iv_lastresort_if_needed กู้เลขจริง ('05070' ได้ +20 near_date จาก cell วันที่ติดกัน
  score 40 ชนะทุกยอดรายการ). เรียกใน _parse_block step 8b (หลัง _pb_finalize_amounts ก่อน pop _iv_score).
- หลักฐาน golden-neutral (พิสูจน์ก่อนแตะโค้ด): สแกน corpus 834 บิล → ไม่มีบิลใด iv == ยอดของตัวเอง
  (0 ราย) → เงื่อนไข if ไม่เคยเป็นจริงบน corpus → guard dormant 100% → hash ไม่ขยับ "เชิงโครงสร้าง".
  ยืนยันเชิงประจักษ์: golden_master ก่อน/หลัง + regression_full [7] บน /mnt/project →
  engine == agent == baseline == `d6b23d127999e62c2a898554c012e60c1d8731dffec212770569fa6ec8818173`
  (ไม่ขยับ) ; verify_parallel serial==parallel ค่าเดียวกัน (bills=834).
- ผลทดสอบไฟล์จริง SHS: 21/21 บิลได้ doc เรียงถูก (05029..05746) ; iv==ยอด = 0 ; รัน validators
  ทุกเส้น (check_invoice_sequence/iv_date_sequence/apply_iv_period_crosscheck/apply_missing_iv_check)
  → issue = 0 → false positive ทั้ง 4 หาย.
- CI: เพิ่ม test_iv_money_misread.py (5 unit + integration presence-gated) ผูกด่าน [3b4]; ผ่าน 81/81 gates
  (coverage/ruff/black/mypy เขียว). version → v9.3.1 (golden เดิม ไม่ rebaseline).

---

### ADR-044 (2026-06-18) — REBASELINE golden 106 ไฟล์: `d6b23d12` → `bb042554` (TNT_69_03 float-tail IV)
- บริบท: Principal-Architect audit เต็มระบบ พบ `regression_full.py` / `verify_golden.py` / CI gate
  [7]+[8] บน corpus จริง /mnt/project **แดง** ทั้งที่โค้ด v9.3.4 ถูก. สาเหตุ = baseline ค้างเป็น
  พฤติกรรม **ก่อน ADR-041** (float decimal-tail IV) → baseline ไม่ถูก regenerate → drift เงียบ.
- root cause (forensic, อ่าน source/cell จริง): ADR-041/ADR-024 อ้างตัวเอง "golden-neutral" แต่พิสูจน์
  เฉพาะ tests/real_cases (KRR/STC/TKH — **ไม่มี TNT**) + fixtures. ไฟล์ `TNT_69_03.xls` (ชีต "6")
  เป็นไฟล์เดียวใน corpus เต็มที่ trigger บั๊ก: ยอดรวม pandas float = `87282.04000000001` →
  โค้ดเก่าคว้าหาง `04000000001` เป็นเลขเอกสาร ; ADR-041 แก้ให้อ่าน raw cell `[5,20]`='03210' ถูกต้อง.
  → "golden-neutral" จริง ๆ ผิดบน corpus เต็ม (ผลถูกขึ้น แต่ hash ขยับ).
- before/after diff (834 บิล): เปลี่ยน **เฉพาะ iv ของ TNT_69_03** — all_bills ต่าง 2 แถว
  (iv_number `04000000001`→`03210`, IV002 false-flag หาย, issue list ปลายน้ำ) · iv_seq 28→29
  (+ '3320(09/03)→3072(11/03) ลดลง' ของจริง) · iv_date 3→2 (− '03179↔04000000001' false positive หาย).
  **ยอดเงิน subtotal/VAT/total ทั้ง 834 บิล ไม่ขยับแม้แต่บาทเดียว.** dup/files/filename_issues/typos ตรงเป๊ะ.
- decision: rebaseline `d6b23d12…` → `bb04255422d64b21e3c00db235912054a62999b3ed1ebc2d4644888b9f3633a4`.
  revert float-tail guard = นำบั๊กกลับ → ตัดทิ้ง. คง baseline เก่า = gate แดงค้าง + ฟ้องเลขขยะ → ตัดทิ้ง.
- ทางเลือกที่ตัดทิ้ง: คง d6b23d12 (gate แดงถาวร) ❌ ; revert ADR-041 (false positive กลับทั้ง corpus) ❌.
- หลักฐาน: `golden_master.py . baseline.json /mnt/project` ×2 = `bb042554…` (deterministic) ;
  `regression_full.py [7]` → engine == agent == baseline ✅ ; `test_agents.py [8]` ✅ ;
  `test_golden_single_source.py [3x]` ✅ (พื้นผิว operational sync ; d6b23d12 ขึ้นทะเบียน retired).
- พื้นผิวที่อัปเดต: baseline.json · GOLDEN.md · DECISIONS.md (banner+ledger) · MAINTENANCE.md ·
  ci.yml · QUICKSTART_VSCODE_TH.md · _SESSION_HANDOFF.md · Makefile · run_ci.sh · .vscode/{tasks,launch}.json
  · test_golden_single_source.py. เอกสารประวัติที่อ้าง d6b23d12 คงไว้ (หลักฐานอดีต).
- backup: `baseline.d6b23d12.pre-rebaseline.json`. รายละเอียดเต็ม: `ADR-044_rebaseline_tnt_floattail.md`.

---

### ADR-045 (2026-06-18) — ตรวจ iv-number ทั้งคอร์ปัสตรงเซลล์จริง + เพิ่มการ์ด [8d] (independent oracle)
- บริบท: ด้านบนขอตรวจว่า "เลขที่เอกสาร (iv_number) ที่ระบบรายงาน ตรงกับเลขจริงในเซลล์ของไฟล์ทั้งหมดไหม"
  ต่อยอดจากบั๊ก TNT float-tail (ADR-044) — เผื่อมีไฟล์อื่นเป็นแบบเดียวกัน.
- วิธี (forensic, อิสระจาก scoring ของ parser และอิสระจาก golden): `_audit_iv_truth.py` เปิดไฟล์ดิบ
  (xlrd/.xls, openpyxl/.xlsx) อ่านทุกเซลล์พร้อม "ชนิดจริง" (TEXT/NUMBER/DATE) แล้วจำแนกว่า iv_number
  ที่ระบบอ่านปรากฏในชีตอย่างไร: TEXT_EXACT/NUM_INT_EXACT/TEXT_CONTAINS = อ่านถูก ;
  FLOAT_TAIL (คว้าหางทศนิยม เช่น .04000000001) = บั๊ก ; MONEY_FRAGMENT/DATE_FRAGMENT/NOT_FOUND = ต้องรีเช็ค.
- ผลบนคอร์ปัสจริง 834 บิล: **TEXT_EXACT 834/834 (100.0%)** · FLOAT_TAIL = 0 · NOT_FOUND = 0.
  ทุกใบที่ระบบรายงานตรงกับเซลล์ข้อความจริงในไฟล์เป๊ะ. TNT ที่เคยพังอ่านถูกแล้ว (ชีต '6' → '03210'
  ไม่ใช่หาง float '04000000001'). → ไม่มีบั๊ก ไม่ต้องแก้โค้ด production.
- decision: เพิ่ม `_audit_iv_truth.py` เป็นการ์ด CI [8d] (เฉพาะรันบนข้อมูลจริง) — เป็น **independent oracle**
  ที่ golden จับไม่ได้: ถ้า rebaseline ผิด (baseline เองมี float-tail) golden จะ "ผ่าน" บน baseline ที่ผิด
  แต่ [8d] เทียบไฟล์ดิบตรง ๆ จึงจับได้. เกตตกเฉพาะ FLOAT_TAIL (ลายเซ็นบั๊กที่ยืนยันแล้ว) — กัน false-fail
  บน layout ใหม่ที่ถูกต้อง (เลข numeric ปกติ/เลขในข้อความ = ผ่าน).
- เพิ่ม `_audit_iv_truth` เข้า ALLOWLIST_TOOLS ของ `test_reachability.py` (standalone tool มี __main__).
- ไม่แตะ production logic · golden ไม่ขยับ (bb042554 คงเดิม) · CI: 84 เกต ✔ 0 ✘.

---

### ADR-046 (2026-06-18) — แก้ F-1/F-2/F-4 (ปัดเงิน HALF_UP + provenance + assert→raise) + rebaseline bb042554→662c9132
- บริบท: deep bug-hunt (BUGHUNT_DEEP) พบความไม่สอดคล้องปัดเศษเงิน + provenance หาย + assert ใน prod. ด้านบนอนุมัติแก้ทั้งหมด.
- F-1 [MEDIUM] ปัดเงินไม่สม่ำเสมอ: เดิม `round(x,2)` (banker's half-to-even) ปนกับ Decimal+ROUND_HALF_UP ที่ระบบประกาศใช้.
  หลักฐาน SHS_68_117 ช.7: derive VAT=round(8742.125,2)=8742.12 แต่ HALF_UP=8742.13. แก้: helper เดียว `_money_q`
  (Decimal+HALF_UP→float, None-safe) ใน puopuy_units แทน round() ทุกจุดเติม/รวม/derive ยอด (parser_p0a/p1/p2).
- F-2 [LOW] 50 บิล TOR_67_08 ไม่มี amount_source: TOR-path ข้าม _pb_finalize_amounts → เรียกเพิ่มท้าย _parse_tor_sheet.
  ยอดครบอยู่แล้ว → ไม่ derive/ไม่เปลี่ยนยอด เพิ่มแค่ provenance ('ocr') + confidence.
- F-4 [INFO] assert→raise (report_precision/viewers) — golden-neutral.
- ไม่แก้: F-3 (vat เยื้องคอลัมน์) — วัดจริง 410/412 บิล derive-VAT มีเซลล์ตรงกันอยู่แล้ว ค่าถูก 411/412 →
  แก้ column-detection จะ churn 410 บิลเพื่อค่าที่ถูกอยู่แล้ว = risk สูง ประโยชน์ ~0 (F-1 จัดการเคส SHS แล้ว).
  F-5 (กฎ VAT ไม่ปัดสตางค์) = feature ใหม่ ไม่ทำจนกว่าได้อนุมัติ.
- blast radius (validate ทีละใบ): 61/834 บิลเปลี่ยน = 11 ค่าเงิน (ถูกทั้งหมด: 9 ล้าง float-noise, SHS vat→8742.13,
  SEE cascade→15987.06) + 50 provenance (ยอดไม่เปลี่ยน). **0 บิล issues เปลี่ยน · issue-code totals เหมือนเดิม ·
  โครงสร้างคงที่** (iv_seq=29,iv_date=2,typos=42,dup=1,companies=2). deterministic.
- golden bb042554→662c9132 · surfaces sync ครบ · bb042554 retired · backup baseline.bb042554.pre-F1F2.json.
  รายละเอียดเต็ม: `ADR-046_fix_money_rounding_provenance.md`.

## ADR-047 — แก้ CMP006 ตัดชื่อ บจ. ยาวกลางคำ + rebaseline `662c9132`→`df91493f` (18.06.2026)
- บริบท: ออดิตเชิงรีพอร์ต — รันจริง 106 ไฟล์/834 บิล ตรวจรายงานลูกค้า **ทั้งสองตัว** (company_summary.txt +
  รายงานรายผู้ขาย .txt) เทียบกฎที่เปิด. ยอดก่อน VAT/ยุบต่อบริษัท×เดือน/pinpoint/สำนวน "รีเช็ค" ผ่านหมด
  (Σ ยอด=162,860,908.87 ตรงเป๊ะ, 834 บิลไม่หาย). ความต่าง typo fuzzy ของสองรายงาน = เจตนา (ล็อกด้วยเทสต์).
- บั๊ก: `r_cmp006` (rules_engine_rules_a.py:121–122) ตัดชื่อ บจ. ด้วย `[:45]` → ชื่อยาว (มี "(ไทยแลนด์)")
  ถูกตัดกลางคำ "จำกัด"→"จำ" หลอกตา (parser ดึงชื่อเต็มถูก ; detail ถูก hash → กระทบ golden + โผล่ทั้งสองรายงาน).
  หลักฐาน: KRR_69_012 ช.17.1 เซลล์ [5,7] ชื่อเต็ม แต่ detail ตัดเหลือ "...จำ". ชื่อจริงยาวสุด 67 ตัว, เกิน 80 = 0.
- แก้: `[:45]`→ตัดที่ 80 + `…` เมื่อยาวเกินจริง (กันบั๊กตัดกลางคำทุกกรณี ไม่ใช่แค่ขยับเพดาน). rules_a 590 LOC.
- blast radius (validate ทีละใบ): 80/834 บิลเปลี่ยน — **เฉพาะฟิลด์ issues (detail CMP006)** ; 0 บิลฟิลด์อื่นเปลี่ยน.
  "...จำ"→"...จำกัด". **issue-code totals เหมือนเดิม** (CMP006 80→80) · 0 การตัดกลางคำเหลือ · โครงสร้างคงที่
  (iv_seq=29,iv_date=2,typos=42,dup=1,companies=2). ยอด/provenance ไม่ขยับ. deterministic.
- ไม่ทำ: แก้ที่ชั้นรายงาน (กู้ชื่อจาก detail ที่ตัดแล้วไม่ได้) ; ขยาย cap ชื่อสินค้า rules_b (คำบรรยายยาวจริง ตัดสมเหตุผล).
- golden 662c9132→df91493f · surfaces sync ครบ · 662c9132 retired · backup baseline.662c9132.pre-trunc.json.
  รายละเอียดเต็ม: `ADR-047_fix_cmp006_name_truncation.md`.

---

## ADR-048 — Re-baseline 106/834 → 148/1056 + แก้ BR สํา nikhahit + TKH คอลัมน์ส่วนลด (2026-06-19)

**บริบท:** เจ้าของสั่ง forensic review ไฟล์ใหม่ทั้งหมด แก้ทุกปัญหา แล้วส่งระบบสมบูรณ์.
คอร์ปัสจริง `/mnt/project` เปลี่ยนมาก: +42 ไฟล์ใหม่ (270 บิล) + แก้ 16 ไฟล์เดิม (106 ไฟล์: 834→786 บิล)
→ ปัจจุบัน **148 ไฟล์ / 1056 บิล**. (เปลี่ยนไฟล์เป็นของเจ้าของ — โค้ดเดิมบนไฟล์ปัจจุบันก็ได้ 786 บิล)

**Forensic (ก่อน rebaseline):** ทั้งคอร์ปัส 1056 บิล — IV 1056/1056, tax_id 1056/1056, ocr-subtotal 654/654 faithful
(2 เคส "ไม่เจอ" = ชีตต่อเนื่อง "4 + 4 (2)" ข้อมูลอยู่ในชีตจริงครบ = artifact). item_sum/derived ถูกทุกบิล. 0 วันที่ invalid.

**2 บั๊กที่แก้ (ระบบอ่านผิด → ฟ้องผิด):**
- **A. BR สํา nikhahit (16 บิล TSH_69_056):** หัวบิล "(สํานักงานใหญ่)" ใช้ ◌ํ(U+0E4D)+า(U+0E32) แทน ำ(U+0E33);
  NFC ไม่ fold → ตัวจับสาขาหา 'สำนักงานใหญ่' พลาด. แก้: `normalize_text` fold `\u0e4d\u0e32→\u0e33` (puopuy_core.py). BR 16→0.
- **B. TKH ส่วนลด (18 บรรทัด/6 บิล TKH_69_05):** col14=ส่วนลด 25% → qty×price≠amount → fallback อ่าน qty=0.25 (ส่วนลด) ผิด.
  แก้: discount-aware detection ใน `_dic_pick_qty_price` (parser_p0a) → qty=15 ถูก; ITM001 มี logic ส่วนลดอยู่แล้ว → 18→0. ไม่แตะกฎ.

**surgical (per-bill diff โค้ดเดิม↔แก้ บนไฟล์ปัจจุบัน):** discount เปลี่ยนเฉพาะ TKH_69_05; fold เปลี่ยนเฉพาะไฟล์มี "ํา".
นอกจากนี้แก้ agent notepad (advisory — `PUKPUI_MAIN_MODULE` ชี้โมดูลผิดหลังซอย monolith; golden ไม่ขยับ).

**ตัดสินใจ:** golden ใหม่ `ddd06191…` (148/1056) · `df91493f`(106/834) ปลดระวาง (RETIRED_PREFIXES) ·
backup `baseline.df91493f.pre-corpus148.json` · ไฟล์แก้: puopuy_core.py, parser_p0a.py, pukpui_modular_funcs.py · ดูเต็มใน ADR-048_corpus148_br_nikhahit_tkh_discount.md


## ADR-049 — Longevity: ขยายหน้าต่างปีพ.ศ.ในชื่อไฟล์ (ระเบิดเวลา 2040→2056) (2026-06-19)
- สถานะ: **ACTIVE** · golden `ddd06191` ไม่ขยับ (ไม่มีไฟล์คลังปีในช่วง 83-99)
- เหตุ: longevity hunt ("รัน 2-3 ปีทุกวันไม่แก้อะไร พังมั้ย") พบ time-bomb เดียว — `_filename_period_ce` (parser_p2.py) หน้าต่างหยุดที่ พ.ศ.2 หลัก=82 (ค.ศ.2039); ปี 83 (ค.ศ.2040) คืน None → DT001 เสื่อม
- แก้: `((2558,2582,-543),(2015,2039,0),(58,82,1957),(15,39,2000))` → `((2558,2599,-543),(2015,2056,0),(58,99,1957),(15,39,2000))` — พ.ศ.2หลัก 82→99 + 4หลักถึง 2599/2056; คง CE-2หลัก 15-39 กันกำกวม 40-56
- ขอบเขตถัดไป: ปี "00"/ค.ศ.2057 (อีก 31 ปี สม่ำเสมอ). สอดคล้อง test_fix_round2.py (y2(83)→2040, y4(2599)→2056); IV-embedded/parser_p0a/puopuy_dates รองรับถึง 2599 อยู่แล้ว
- เทส: test_fix_round2.py PASS 14/0, test_date_2digit_year.py PASS · นอกจากนี้พิสูจน์เชิงประจักษ์: future-date ค.ศ.2029 (EXIT0, 1056 บิล, ปรับตัว), corrupt/empty file (graceful skip + SYS001 audit trail ครบใน Excel), state reset + memory-cap → รัน 2-3 ปี SOLID

## ADR-050 — รายงานโชว์เลขที่เอกสาร "ตรงใบจริง" (iv_number_raw) + IV004 เลขไม่เรียง → ฟ้องช่องหลัก (2026-06-19)
- สถานะ: **ACTIVE** · advisory ล้วน · golden `ddd06191` ไม่ขยับ (engine==agent==baseline ยืนยันหลังแก้ทุกจุด)
- เหตุ (เจ้าของแจ้ง): เลขที่เอกสารในรายงาน (Excel + Notepad + ultra) "ไม่ตรงกับความเป็นจริง" — `iv_number` (normalized) ตัดขีด/อักขระออก (เซลล์ `IV6905-020012` → โชว์ `IV6905020012`; เพี้ยน `IV6905-2000.6` → `IV69052000`)
- หลักการ: `iv_number` (normalized) = LOGIC (match/dedup/**golden oracle — ห้ามแตะ regression_oracle.py**); `iv_number_raw` = DISPLAY (ตรงใบ)
- แก้ DISPLAY → `iv_number_raw` **9 จุด**: agents/base.py `bill_ref` (ครอบทุก agent_report reference), ultra_agent.py `_bill_ref_str` (ultra), super_ultra_viewer.py:213 (company_summary pinpoint 327/332/352), reporting_p0.py:234/281/347 (Excel low-conf/high-risk/timeline), reporting_p1.py:556 (ชีต บิลซ้ำ — key dedup คง norm แต่ช่องโชว์ใช้เลขดิบ), analytics.py:189 (WHT finding), agents/ai_review_agent.py:92
- ผลตรวจ (คลังเต็ม 1056 บิล, production AUTO): leak จริง=0 ทุกรายงาน — ชีตบิลซ้ำ 20/22 มีขีด (เดิม 0), ทุกบิล 561 มีขีด, รายการสินค้า 1739 มีขีด; ultra เพี้ยนโชว์ `IV6905-2000.6` ตรงเซลล์. หมายเหตุ: บิลซ้ำ+analytics เจอตอนตรวจคลังเต็ม (test 2 ไฟล์ไม่มีบิลซ้ำ)
- IV004 (เลขใบกำกับไม่ไล่ตามวัน) เดิม soft → ช่อง "เลขที่ iv" ขึ้น "ตรง" + ยกตรวจตาเพิ่ม (เจ้าของไม่ยอมรับ). แก้: เพิ่ม `"IV004"` ใน `_STRUCTURAL` (report_precision.py) → firm/clear → ฟ้องช่องหลัก + คำตัดสิน. คลังจริงฟ้อง 3/1056 บิล (TNT_69_03, TSH_68_0112, ไฟล์เทส — ของจริงล้วน) → false positive ต่ำมาก
- เทส: regression_full `ddd06191` (engine==agent==baseline); test_super_ultra_viewer PASS (10 viewers+composer); test_vendor_report 52/0; doc-sync gate PASS


---

### ADR-051 — แก้ DT001 "012" filename parse (false positive) + ลด noise ITM007/ITM015 · rebaseline ddd06191→ba9deda0
**วันที่:** 2026-06-19 · **สถานะ:** ACTIVE · **สั่งโดย:** ผู้ใช้ (forensic audit หน้า Error Report ทั้ง 1056 บิล — "ผิดจริงทุกรายการมั้ย/ระบบรวนมั้ย")

**บริบท / ปัญหาที่พบ:** ตรวจ forensic อ่านเซลล์จริง + รัน pipeline ทั้ง 199 รายการในหน้า Error Report (Excel) พบ false positive จริงตามที่ผู้ใช้สงสัย:
- **DT001 (51) ส่วนใหญ่เป็นบั๊ก parse** — `parse_filename` (parser_p0a.py) อ่านชื่อไฟล์ `69.012` เป็น **เดือน 12 (ธ.ค.)** เพราะ legacy `int("012")=12` แต่บิลทั้ง 8 ไฟล์ (`KNT/KRR/KTV/SBT/SEE/SEI/SHS/TKH _69_012`) ลงวันที่ **มกราคม** + งวดที่ระบบเองแสดง = 69.01 (ม.ค.) → "012" = ม.ค.(01)+part2 ไม่ใช่ ธ.ค. → DT001 ฟ้อง "วันที่ ม.ค. ไม่ตรงเดือน 12" = false positive
- **ITM007 (10) "Jumper ชื่อสั้นเกินไป"** = ชื่อสินค้าจริง (สาย jumper) ของ บจ.เจียนโป (40 บิล → 0% ผิดจริง) — อยู่ใน `issue_consolidator.REVIEW_ONLY` แล้ว แต่ Excel `_lane` ใช้ `config.REVIEW_CODES` คนละชุด ยังจัดเป็น FINDING
- **ITM015 (44) "ชื่อเดียวกันหลายหน่วย"** (PCS./เส้น, คิว/ตัน) = ผู้ขายใช้หลายหน่วยปกติ ไม่ใช่ error คำนวณ (Notepad ซ่อนอยู่แล้ว แต่ Excel โชว์ใน FINDING)

**ตัดสินใจ + การแก้:**
1. **parse_filename (parser_p0a.py, fallback legacy):** token เดือน leading-zero + ≥3 หลัก → เดือน = 2 หลักแรก ("012"→01). **Scope จำกัดมาก**: เฉพาะ "01N" (`mstr.startswith('0') and len(mstr)>=3 and int(mstr) in 1..12`); 2 หลัก และ token ที่ int ไม่ใช่ 1-12 ("057","127","0112","0405") **คงพฤติกรรมเดิมเป๊ะ (month=None)** → ลบ DT001 false positive 22 ตัว (51→29)
2. **config.REVIEW_CODES:** เพิ่ม ITM007 + ITM015 → ย้ายเข้าเลน "ข้อควรตรวจสอบ" (advisory) ใน Excel · **golden-safe** (config.REVIEW_CODES ใช้ใน reporting/_lane เท่านั้น ไม่อยู่ใน golden path — ยืนยัน hash ไม่ขยับหลังเพิ่ม) → Error Report 199→123 แถว, ข้อควรตรวจสอบ 705→754
3. **rebaseline ddd06191 → ba9deda0** (148 ไฟล์/1056 บิล) — golden เปลี่ยนเฉพาะ DT001

**หลักฐาน (forensic):**
- map เดือน parse_filename vs โหมดวันที่บิลจริง **ทั้ง 148 ไฟล์** — ก่อนแก้ mismatch 10 ตัว (8× "012" parse=12 บิล=1 + SHS_68_12 + TNT_69_01); หลังแก้ 8/8 "012"→เดือน 1 ถูกต้อง เหลือ mismatch แค่ 2 (SHS_68_12 ธ.ค.มีบิล ม.ค., TNT_69_01 ม.ค.มีบิล พ.ค. = บิลผิดงวดจริง คงไว้)
- golden เปลี่ยนเฉพาะ DT001: ITM004=407, ITM005=289, ITM010=23, ITM015=44, DOC001=9, DT002=8, IV004=3, ITM016=5 **เท่าเดิมทุกตัว**
- **บทเรียน:** fix แรก (เอา 2 หลักแรกทุก token) แตะ 4-หลัก "0106"/"0112"/"0405" (ไม่ใช่ MMDD เสมอ บิลคนละเดือน) → สร้าง mismatch ใหม่ 6 → **revert เป็น minimal** (เฉพาะ leading-zero "01N")
- ITM007 อยู่ใน issue_consolidator.REVIEW_ONLY อยู่แล้ว (M6) — config.REVIEW_CODES ตกหล่น → แก้ให้ sync กัน

**เทส/พิสูจน์:** `regression_full.py . /mnt/project` = ba9deda0 (engine==agent==baseline ✅) · doc-sync gate PASS · check_invariants PASS (fixture ไม่ขยับ — DT001 fix ไม่แตะ fixture) · test_super_ultra_viewer + test_vendor_report 52/0 PASS

**คงเหลือ (ไม่แก้ในรอบนี้ — ต้องอนุมัติ/ตรวจแยก):**
- ITM011/ITM019 = ผสม (มั้วน/แกลอน ผิดจริง แต่ กระเบื้องพื้น/ปี๊ป เป็นคำถูกที่ dict ไม่รู้จัก) — คงไว้ FINDING เพราะจับ typo จริงเป็นส่วนใหญ่; ถ้าจะลดต้องทำ whitelist
- DT002 (8 future) = artifact ของ audit date ตรึง 2026-06-02 (บิล 04-05/06) — ในรันจริง (today จริง) จะหายเอง


---

### ADR-052 — `parse_date_any` จับเลขที่อยู่ "2/12-2/13" เป็นวันที่ → 1970 (false positive) · golden-RESTORING
**วันที่:** 2026-06-20 · **สถานะ:** ACTIVE · **golden ไม่เปลี่ยน (คง `ba9deda0`)** · **สั่งโดย:** ผู้ใช้ (ตรวจ "อ่านไฟล์ทั้งโปรเจคได้มั้ย + คะแนนระบบ" → เจอ drift ระหว่าง verify → สั่งแก้ให้สมบูรณ์)

**บริบท:** โค้ดใน `pukpui_v9_3_4_RECHECK_20260620.zip` รัน engine บน /mnt/project ได้ `bcfcaf37` ≠ `baseline.json` (`ba9deda0`) ของแพ็กเกจเอง (นิ่งทุกรอบ = deterministic). diff: ต่างแค่ `iv_seq` (15→20), 5 บิลใน `ที่อยู่ เลขที่.xls` (วันเพี้ยน), `summary`; key อื่นตรง baseline เป๊ะ.

**Root cause (forensic เซลล์+regex):** date cell `r6c16` = serial `244471` = พ.ศ.2569 (เกิน `Timestamp.max` 2262 → pandas คืน `datetime(2569,5,2)` → parse ถูกเป็น 2026-05-02). **แต่** cell ที่อยู่ `r5c4`="2/12-2/13 หมู่ที่ 3..." ถูก `parse_date_any` คืน `datetime(1970,2,12)` ชนะก่อน: regex `m_yy` (P4 เปลี่ยนเป็น `re.search` ไม่ anchor) จับ embedded "12/2/13" → yy=13 → `_ivp_year2_to_ce(13)`=None (นอกช่วงปีจริง) → **fallback `(13+2500)-543=1970`** → วันที่ขยะชนะ date cell จริง → false flag "IV วันที่ไม่สอดคล้อง" 5 ใบ.

**ตัดสินใจ+แก้ (1 ไฟล์ `puopuy_dates.py`):** ปี 2 หลักที่ `_ivp_year2_to_ce` คืน None ("ตีความไม่ได้") → **ห้าม fabricate วันที่** (สร้างเฉพาะ `_ce is not None`). เคารพ contract ของ helper เอง (docstring: ช่วงกำกวมคืน None ให้ชั้นบนตัดสิน). corpus 66–69 อยู่ช่วง 58–99 → `_ce`≠None → พฤติกรรมเดิมทุกบิล (golden-safe).
```python
# เดิม: year = _ce if _ce is not None else (yy+2500)-543 ; if 1<=mon<=12 and 1<=day<=31: return datetime(year,mon,day)
# ใหม่: if _ce is not None and 1<=mon<=12 and 1<=day<=31: return datetime(_ce,mon,day)
```

**หลักฐาน:** ที่อยู่ "2/12-2/13" → None (เดิม 1970) · legit คงเดิมทุกเคส ('วันที่ 11/05/69'→2026-05-11, '5/5/69'→2026-05-05, '1/1/15'→2015-01-01, '11/05/2569'→2026-05-11) · 5 บิลกลับเป็น 2026-05-xx · `iv_seq` 20→15.

**เทส/พิสูจน์ (คลังจริง 148/1056):** `regression_full.py . /mnt/project` = `ba9deda0` (engine==agent==baseline ✅ exit 0) · check_invariants (fixture `269ddaed` + pins) ✅ · **test_*.py 81/81 PASS** · version/smoke/e2e/verify_golden/verify_parallel/verify_report_det PASS · diff vs zip เดิม = 1 ไฟล์.

**บทเรียน:** (1) helper ที่ออกแบบให้คืน None สำหรับ "ตีความไม่ได้" — ผู้เรียกต้องเคารพ None ห้ามใส่ค่าเดา (fabricate วันจากปีกำกวม → เศษเลขในที่อยู่กลายเป็นวันที่). (2) `re.search` ไม่ anchor ต้องคู่กับ gate ค่าเข้มงวด (ช่วงปีจริง). (3) ไฟล์ QA edge-case (serial พ.ศ.เต็ม) = canary ที่ทำให้ drift โผล่ตอน verify แทนเงียบ. รายละเอียดเต็ม: `ADR-052_dt003_addr_misread_date_1970.md`.


---

### ADR-053 — รอบเสริมทนทาน 5 ปี: serial พ.ศ.robust + characterization net + release gate · golden ไม่เปลี่ยน (`ba9deda0`)
**วันที่:** 2026-06-20 · **สถานะ:** ACTIVE · **สั่งโดย:** ผู้ใช้ ("แก้ทั้งหมด + เทสทั้งโปรเจค เพื่อระบบสมบูรณ์สุดสำหรับ 5 ปี")

**บริบท:** หลัง ADR-052 ผู้ใช้ถาม "สมบูรณ์แบบยัง" → ระบุจุดเปราะ 6 ข้อ → สั่งปิดหมด. ทุกข้อ golden-safe (hash ไม่ขยับ).

**ทำ (A/B/C/E):**
- **A `make_release.py`** (ปิด #1 process gap): build→extract→รัน regression_full+check_invariants บน tree ที่แตกจาก zip→เทียบ hash==baseline. พลาด→ลบ zip+exit1. negative test: inject drift→ปฏิเสธ+ลบ zip ✅. "zip ที่ไม่ reproduce golden" สร้างไม่ได้.
- **B `parse_date_any` สาขา float** (ปิด #2): serial เก็บปี พ.ศ.ตรงๆ (244471=พ.ศ.2569, เกิน 30000-70000) → xldate→-543→รับปี 2015-2056. golden-safe (corpus ส่ง datetime → สาขานี้ไม่ทำงานบน golden; hash=`ba9deda0`).
- **C `test_date_parse_characterization.py`** (ปิด #3/#4): 36 เคสล็อกทุกสาขา (datetime/serial/Thai-month/2+4digit/leap/**adversarial 11→None**/null) + tripwire ADR-052. wire run_ci.sh [3x3b]. 36/36 PASS. จับ regression สาขาเร็วโดยไม่ต้องรัน golden ใหญ่.
- **E (ตรวจ ไม่แก้โค้ด #6):** pythainlp optional แท้ — `pythainlp_spell_check` guard `if not PYTHAINLP_AVAILABLE: return []`; 51 typos มาจาก CONSTRUCTION_DICT ไม่ใช่ pythainlp → ติดตั้งเพิ่มอาจ drift → ไม่ติดตั้งคือถูก. version_gate แจ้ง optional ชัดแล้ว.

**เลือกไม่ทำ (เหตุผล):**
- **D ITM011/019 whitelist — ไม่ทำ:** ค้นพบ `ITM011`/`ITM019` **อยู่ใน golden snapshot** (ฝัง all_bills[].issues) → แตะ=golden ขยับ. มัน "จับ typo จริงเป็นส่วนใหญ่" (มั้วน/แกลอน ผิดจริง) → suppress=เสี่ยง **false negative** (แพงกว่า FP ในระบบ audit) + ต้อง rebaseline + ไม่มี ground-truth คำ legit. flag-for-review = default ปลอดภัยสุด. ถ้าจะลด: ผู้รู้โดเมน curate คำ→ใส่ dict→rebaseline+ADR (build กลไกได้ทันทีที่ได้คำ แต่ไม่เดาเอง).
- **DT002 future-date — ไม่ใช่บั๊ก:** artifact ของ audit date ตรึง 2026-06-02; production จริงหายเอง.

**เทส:** regression_full=`ba9deda0` (engine==agent==baseline ✅ หลังทุกข้อ) · check_invariants+doc-sync+package_integrity ✅ · **test_*.py 82/82** · แพ็กเกจออกผ่าน make_release (hash gate บังคับ). diff vs ADR-052 zip: +2 ไฟล์ (make_release, characterization) แก้ 2 (puopuy_dates สาขา float, run_ci.sh). รายละเอียด: `ADR-053_hardening_5yr_serial_characterization_releasegate.md`.

**หลักการตรึงอนาคต:** (1) ห้าม suppress การจับของจริงเพื่อลด FP เว้นมี ground-truth+อนุมัติ+rebaseline. (2) ทุกแพ็กเกจออกผ่าน make_release (ห้าม zip มือ). (3) แก้ parser/date ต้องผ่าน characterization test ก่อน.


---

### ADR-054 — แก้ desync ITM015 ใน REVIEW_ONLY (consolidated report จัด 34 ใบผิดเป็น "ต้องแก้") · golden ไม่เปลี่ยน (`ba9deda0`)
**วันที่:** 2026-06-20 · **สถานะ:** ACTIVE · advisory · **สั่งโดย:** ผู้ใช้ (forensic audit รีพอร์ต)

**พบ:** `ITM015` ∈ `config.REVIEW_CODES` (ADR-051) แต่ตกหล่นจาก `issue_consolidator.REVIEW_ONLY` → `build_consolidated_report` (เลนด้วย REVIEW_ONLY บรรทัด 114) จัด ITM015-only 34 ใบเป็น "ต้องแก้" ผิด.
**หลักฐาน:** ITM015-only ทั้ง 34 = ทราย[คิว,ตัน]/ปูน[ถุง,ลบ.ม.] = หลายหน่วยปกติของวัสดุก่อสร้าง **ไม่ใช่ error** → ADR-051 ถูก.
**แก้:** เพิ่ม "ITM015" ใน REVIEW_ONLY (sync config.REVIEW_CODES ตาม invariant). advisory — golden `ba9deda0` ไม่ขยับ.
**ผล:** ต้องแก้ 204→161 (ย้าย 43 = 34 ITM015-only + 9 ITM015+review-อื่น) · review 628→671 · report tests ผ่าน 4/4.
**ค้าง:** (1) code_labels ITM015='fix' (3-way label inconsistency, design call). (2) reverse desync ITM003/VAT006/VAT010 (ไม่อยู่ corpus). (3) lane ใช้ REVIEW_ONLY hardcoded ไม่ใช่ code_labels action tier → 'note'/'check' tier (DT001/CMP006/IV004) ตก "ต้องแก้" — เสนอผู้ใช้ตัดสิน. รายละเอียด: `ADR-054_itm015_review_lane_desync.md`.


---

### ADR-055 — แก้ money-serial อ่านเป็นวันที่ใน header scan (เซลล์เงิน 43600 → 15/05/2019) · rebaseline ba9deda0→0563245c
**วันที่:** 2026-06-20 · **สถานะ:** ACTIVE · **golden เปลี่ยน `ba9deda0` → `0563245c`** (rebaseline ตั้งใจ) · **สั่งโดย:** ผู้ใช้ (forensic audit รีพอร์ต — "ถ้าเจอผิดจริงให้แก้")

**ความเสี่ยงเดิม (🔴 correctness):** บิล `TSH_68_0112.xls` ชีต `4.12` มีเซลล์วันที่จริง [3,16]=`'40/12/2568'` (วัน 40 — typo ของ 04/12 ไม่มีจริงในปฏิทิน). `parse_date_any('40/12/2568')` คืน `None` ถูกต้อง แต่ header scan วิ่งต่อแล้วไปเจอเซลล์ [10,19]=`43600.0` (= line-total ของรายการ #2: 400×109) ซึ่งอยู่ในช่วง Excel-serial ค.ศ. (30000-70000) → `parse_date_any(43600)` แปลงเป็นวันที่ **15/05/2019** (มั่ว). ผลพวง: ฟ้อง `DT004` (งวด 62/05 ≠ IV 68/12) + `DOC001` (ชีต 04/12 ≠ บิล 15/05) + วันที่มั่วยัง **poison** IV-sequence ข้ามชีต → ชีต `2.01` ฟ้อง `IV004` เท็จ (เทียบกับ "ใบก่อนหน้า 15/05").

**Root cause:** `parser_p1.py::_pb_scan_header` (บรรทัด 561-565) ส่ง **ทุกเซลล์** เข้า `parse_date_any` รวมเซลล์ยอดเงิน. เมื่อ date cell จริงเป็น typo (parse ไม่ได้) → loop คว้าเซลล์เงินตัวแรกในช่วง serial มา fabricate วันที่. เซลล์เงิน 43600 บาท แยกจาก serial วันที่ (43600 = 15/05/2019) ไม่ได้ด้วยค่าเปล่า ๆ — ต้องใช้ context (เป็น header date scan).

**ทางแก้ (surgical · call-site):** ใน `_pb_scan_header` ก่อนเรียก `parse_date_any(v)` เพิ่ม guard: ถ้า `v` เป็น `int/float` เปล่า (ไม่ใช่ bool/datetime) อยู่ในช่วง `30000 < v < 70000` → ข้าม (ไม่ถือเป็นวันที่). **ไม่แตะ `parse_date_any`** (utility คงสัญญาเดิม 100% + characterization test `ser_ce_inrange` 46150→2026-05-08 ยังผ่าน). วันที่ข้อความ / datetime object / พ.ศ.-serial (>200000 เช่น 244419 ของ TNT) **ไม่กระทบ** (พิสูจน์: patch global ก็เปลี่ยน 1 บิลเดียวกัน).

**Migration risk / delta (วัด exact บนคลัง 148/1056):** เปลี่ยน **iv_date เพียง 1 บิล** (TSH_68_0112 ชีต 4.12: `15/05/2019`→`''`, ตั้ง `_bad_date='40/12/2568'`). issue-level delta:
- ชีต 4.12: **ลบ** DOC001 + DT004 (ผลพวงจากวันที่มั่ว) · **เพิ่ม** `DT006` "วันที่ 40/12/2568 ไม่มีจริงในปฏิทิน ต้องแก้วันที่" (ต้นตอจริง actionable)
- ชีต 2.01: **ลบ** IV004 (false flag — เทียบ sequence กับวันที่ poison 15/05)
- `iv_seq` 15→14 · ไม่มี detection จริงหาย · ไม่มี false negative (บิลยัง flag DT006). **ผลถูกต้องมากขึ้นทุกจุด.**

**rebaseline:** `baseline.json` ใหม่ `0563245c1237379f955c1b8070f2b4376d25652a8f8595e01c76d9784ec83ce3`. อัปเดต 9 พื้นผิว doc-sync (MAINTENANCE/QUICKSTART/_SESSION_HANDOFF/DECISIONS banner/.vscode×2 → 0563245c; README/version_gate/orchestrator/constraints/Makefile/ci.yml ใช้ neutral ref ไม่ต้องแก้) · เพิ่ม `ba9deda0` ใน RETIRED_PREFIXES · GOLDEN.md current=0563245c + ledger ba9deda0.

**เทส/พิสูจน์ (คลังจริง 148/1056):** `golden_master.py` = `0563245c` · `regression_full.py . /mnt/project` = `0563245c` (engine==agent==baseline ✅) · check_invariants (fixture `269ddaed` ไม่ขยับ — fix ไม่แตะ fixture/parse_date_any) ✅ · doc-sync PASS (prefix 0563245c) · reachability ✅ · **test_*.py 82/82 PASS** (รวม characterization — parse_date_any ไม่เปลี่ยน). backup: `/tmp/parser_p1.py.bak`, baseline เดิม `/tmp/baseline.ba9deda0.bak`.

**ค้าง (ไม่ทำ — รอผู้ใช้):** ITM010/011/019 typo whitelist (เช่น "บริสุทธิ์" ถูก flag การันต์หลังสระ-FP, "กระเบื้องพื้น"/"แกลอน" variant ปน typo จริง บสังกะสี/หล็กฉาก) — อยู่ใน golden, suppress เสี่ยง false negative, ต้อง curate คำ legit + rebaseline · lane logic ใช้ code_labels action tier · ประกบรีพอร์ตระดับบิลอัตโนมัติ.


---

### ADR-056 — whitelist false-positive typo: "บริสุทธิ์" (การันต์หลังสระ ิ์) + "กระเบื้องพื้น" (fuzzy) · rebaseline 0563245c→be6398d2
**วันที่:** 2026-06-20 · **สถานะ:** ACTIVE · **golden เปลี่ยน `0563245c` → `be6398d2`** (rebaseline ตั้งใจ) · **สั่งโดย:** ผู้ใช้ (ตรวจ ITM typo รายคำ → ยืนยัน FP 2 คำ → อนุมัติแก้)

**ความเสี่ยงเดิม (false positive):** กฎตรวจคำสะกด 2 ตัวฟ้องคำที่**ถูกต้อง** เป็น "สะกดผิด":
1. **ITM010 (pattern):** `THAI_TYPO_PATTERNS` มี `(r'[ะาิีึืุู]์', 'การันต์หลังสระ')` → จับ "ิ์" ใน "บริสุทธิ์" (น้ำตาลทรายขาวบริสุทธิ์) ว่าการันต์ผิด. แต่ "ิ์" (ธิ์/ทธิ์) เป็น**คลัสเตอร์ถูกต้อง**จากบาลี-สันสกฤต (บริสุทธิ์/สิทธิ์/ฤทธิ์) — ฟ้องผิด 4 ครั้ง.
2. **ITM011 (fuzzy):** "กระเบื้องพื้น" ถูกจับว่า ~92% ใกล้ "กระเบื้องปูพื้น" → "อาจสะกดผิด". แต่ "กระเบื้องพื้น" เป็น**ชื่อสินค้าจริง** (ชื่อสั้น คนละแบบ) ไม่ใช่ typo — ฟ้องผิด 7 ครั้ง.

**Root cause:** (1) pattern `[ะาิีึืุู]์` over-broad — รวม ิ ทั้งที่ ิ์ ถูกต้องเกือบทุกคำ ; (2) "กระเบื้องพื้น" ไม่อยู่ใน `PYTHAINLP_WHITELIST`/`CONSTRUCTION_DICT` → fuzzy จับเทียบคำใกล้.

**ทางแก้ (surgical):**
1. `config_base.py` THAI_TYPO_PATTERNS: `[ะาิีึืุู]์` → `[ะาีึืุู]์` (เอา ิ ออก). คง ์ หลังสระอื่น (โอกาส typo สูงกว่า). robust — ครอบ สิทธิ์/ฤทธิ์/บริสุทธิ์ อนาคต ไม่ใช่ whitelist รายคำ.
2. `config_base.py` PYTHAINLP_WHITELIST: เพิ่ม `'กระเบื้องพื้น'` (r_itm011 เช็ค `w in PYTHAINLP_WHITELIST → skip`).

**หลักการ (ไม่ทำลายการจับจริง):** ตรวจ typo รายคำกับการสะกดมาตรฐานไทย — typo จริงทุกตัว**เก็บไว้ครบ** (แกลอน→แกลลอน, มั้วน→ม้วน, หล็กฉาก→เหล็กฉาก, ตู้คอนซูเมอร์→คอนซูมเมอร์, บสังกะสี, ปลายสว่าง→สว่าน ฯลฯ ยังฟ้องเหมือนเดิม). แก้เฉพาะ 2 คำที่พิสูจน์ว่าถูกต้อง.

**Migration risk / delta (วัด exact 148/1056):** **ลบ 11 flag (FP ทั้งหมด) · เพิ่ม 0:**
- ITM011 "กระเบื้องพื้น" ×7 (SHS_68_02, SHS_69_056×2, TKH_69_05_2×2, TSH_69_05__2×2)
- ITM010 "การันต์หลังสระ ิ์" (บริสุทธิ์) ×4 (รันนิ่งรายการ.xls ×4)
- ไม่มี typo จริงหาย (พิสูจน์: scope test diff = ลบ 11 FP เป๊ะ) · `iv_seq/iv_date/dup/typos summary` ไม่ขยับ — เปลี่ยนเฉพาะ all_bills[].issues 11 รายการ.

**rebaseline:** `baseline.json` ใหม่ `be6398d2907583fc6d2e600cc2ccdc9ce406b5c048510eb987cad32a9d56de77`. อัปเดต doc-sync surfaces (MAINTENANCE/QUICKSTART/_SESSION_HANDOFF/DECISIONS banner/.vscode×2/Makefile/ci.yml → be6398d2) · เพิ่ม `0563245c` ใน RETIRED_PREFIXES · GOLDEN.md current=be6398d2 + ledger 0563245c · characterization label → be6398d2.

**เทส/พิสูจน์ (oracle 6/6 เขียว @ be6398d2):** golden_master=`be6398d2` · regression_full (engine==agent==baseline) ✅ · check_invariants (fixture `269ddaed` ไม่ขยับ — แก้ advisory typo rule ไม่แตะ fixture) ✅ · doc-sync PASS (prefix be6398d2) · reachability ✅ · test_*.py 82/82 PASS · make_release hash gate ✅. backup: config_base.py เดิม, baseline `/tmp/baseline.0563245c.bak`.

**ค้าง (รอผู้ใช้ชี้):** รูปไม่มาตรฐานที่ใช้แพร่หลาย — ปี๊ป(→ปี๊บ)/สวิตซ์(→สวิตช์)/เจียร์(→เจียร)/อิฐบล็อค(→อิฐบล็อก)/พุ๊ก(→พุก): ปัจจุบันฟ้องอยู่ (ถือเป็น typo ตามมาตรฐาน). ถ้าผู้ใช้ต้องการ "ปล่อย" คำใด → เพิ่มใน PYTHAINLP_WHITELIST + rebaseline.

---

### ADR-057 — DOC001 false-positive: ชื่อชีตที่เป็น "ลำดับ/เทมเพลต" ถูกอ่านเป็น "วันที่" · rebaseline be6398d2→c50fec27 (LONG guard) + SHORT รอผู้ใช้อนุมัติ
**วันที่:** 2026-06-20 · **สถานะ:** ACTIVE (LONG-only) · **golden เปลี่ยน `be6398d2` → `c50fec27`** (rebaseline ตั้งใจ) · **สั่งโดย:** ผู้ใช้ (forensic audit รายงาน Error Report + ข้อควรตรวจสอบ ทุกบรรทัด → ยืนยัน FP ด้วย ground truth → อนุมัติแก้บั๊ก)

**Current risk (ก่อนแก้):** DOC001 (กฎ "วันที่ในบิล vs ชื่อชีต") มี false positive — flag บิลที่ "ถูกต้อง" ว่าผิด ลดความเชื่อถือ Error Report.

**Root cause:** DOC001 มี 2 producer ที่ตั้งสมมุติฐาน "ชื่อชีต = วันที่":
1. **LONG** (`validators.apply_sheet_date_crosscheck`) — regex `^(\d{1,2})\.(\d{1,2})` อ่าน "N.M" เป็น วัน N เดือน M.
2. **SHORT** (`rules_engine_rules_a.r_doc001`) — ชื่อชีตเลขล้วน อ่านเป็น "วันของเดือน".
ถูกเฉพาะไฟล์ที่ตั้งชื่อชีตตามวันจริง แต่พังกับไฟล์ที่ใช้ชื่อชีตเชิง organize: ลำดับย่อย ("5","5.1","5.2"), สำเนา Excel ("2","2 (2)"…), เลขบิลเดี่ยว ("1"=บิลแรก).

**Ground truth (อ่าน raw .xls ตรง — พิสูจน์ FP 4 ตัว):**
- **TNT_69_03 "5.1","5.2"** [LONG] = FP: ชีต '5','5.1','5.2','5.3' มีวันที่ภายใน **05/03 เหมือนกันทุกใบ** → ".1/.2/.3" เป็นลำดับย่อย ไม่ใช่เดือน. (sh5.3 ไม่ flag เพราะ ".3" บังเอิญ=มี.ค.ตรงวันบิล)
- **TNT_69_03 "2"** [SHORT] = FP: ชีต '2','2 (2)'…'2 (10)' = 10 บิล (doc 03072–03081) ต่างใบ วันที่ 11/03 ทุกใบ → "2" คือเทมเพลตก๊อป 10 ชุด.
- **TSH_69_039 "1"** [SHORT] = FP: ไฟล์ชีตเดียว "1"; IV690304-**04** + cell 04/03/2569 ยืนยันวัน 4 → "1"=บิลแรก.
- **คงไว้ (true positive)**: TSH_68_0106 "1.2"/"4.2", TKH_68_0112 "11.10" (ไฟล์วัน.เดือนจริง — บิลผิดเดือน/วัน copy-paste), SHS_68_02 "6" (ไฟล์วันจริง 10/11 ชีตตรง).

**Recommended solution / สิ่งที่ทำในรอบนี้ (LONG guard — surgical, zero blast radius):**
- `validators.apply_sheet_date_crosscheck`: precompute `filepath → {N: set(date)}` ของชีตเลขล้วน. ก่อน flag "N.M" ถ้ามีชีต "N" (เปล่า) ในไฟล์เดียวกันที่วันที่ภายในตรงกับบิลนี้ → ".M" เป็นลำดับย่อย → ข้าม.
- พิสูจน์ corpus-wide scan: มีไฟล์เดียว (TNT_69_03) ที่มี bareN+dotted sibling → **zero collateral** (true positive ครบ). ไฟล์ multi-month (SHS_68_0112/TKH_68_0112 ".M"=เดือนจริง) ไม่โดน guard เพราะไม่มี bareN sibling.

**Migration risk / delta (วัด exact 148/1056 ด้วย sim_guard ก่อนแตะโค้ด):** **ลบ 2 flag (LONG FP) · เพิ่ม 0:**
- TNT_69_03 5.1, 5.2 (DOC001) → DOC001 รวม 8→6 · issue รวม 914→912 · **รหัสอื่นไม่ขยับเลย** (ITM004=407/ITM005=289/CMP006=50/DT001=29/… เท่าเดิม) · iv_seq/iv_date/dup/typos summary ไม่ขยับ.

**rebaseline:** `baseline.json` ใหม่ `c50fec27a0ace3c9545fb00379a836a70740f11d4d1665724aacee53a5d6badb`. อัปเดต doc-sync surfaces (MAINTENANCE/QUICKSTART/_SESSION_HANDOFF/DECISIONS banner+row/.vscode×2/Makefile/ci.yml → c50fec27) · เพิ่ม `be6398d2` ใน RETIRED_PREFIXES · GOLDEN.md current=c50fec27 + ledger be6398d2 · characterization label → c50fec27. backup: `baseline.be6398d2.pre-adr057.json`.

**เทส/พิสูจน์ (เขียว @ c50fec27):** golden_master=`c50fec27` · regression_full (engine==agent==baseline ✅) · check_invariants (fixture `269ddaed` ไม่ขยับ — LONG guard ไม่แตะ fixture เพราะชีต fixture '2/4/6' ไม่มีจุด/ไม่มี bareN+dotted) · doc-sync PASS (prefix c50fec27) · reachability ✅ · test ชุดเดิม PASS.

**Long-term impact:** Error Report สะอาดขึ้น (ลบ sub-index FP ที่ชัดที่สุด). guard อิงหลักฐานในไฟล์ (sibling sheet + วันที่) ไม่ hardcode → ทนไฟล์ใหม่. ความเสี่ยง false negative ต่ำ (ไฟล์วันจริง guard ไม่ทำงาน).

**Priority:** MEDIUM (correctness ของ advisory report; ไม่กระทบ engine ผลตรวจหลัก).

---

**🔶 รอผู้ใช้อนุมัติ — SHORT-format DOC001 FP (TNT_69_03 "2", TSH_69_039 "1") + lane/design:**
1. **SHORT guard (เลื่อนไว้):** r_doc001 อ่านชีตเลขล้วนเป็น "วัน" — TNT "2" (เทมเพลต) + TSH_69_039 "1" (บิลเดี่ยว) = FP พิสูจน์แล้ว. **แต่** fix นี้ (ต้องมีชีตเลขล้วน ≥2 ตรงวัน ถึงถือเป็น day-naming) จะทำให้ **fixture (ชีต 2/4/6 = วัน 15/20/25) เลิกฟ้อง DOC001** → ต้อง rebaseline fixture (269ddaed→ใหม่) + อัปเดต FIXTURE_SURFACES + check_invariants pin + ตรวจ e2e/super_ultra_viewer + อาจต้องเพิ่มเทส DOC001 ใหม่กันสูญเสีย coverage. = blast radius เกิน "surgical" → **รอผู้ใช้สั่ง** ก่อนทำ (จะทำเป็น ADR-058 แยก).
2. **lane "ต้องแก้" มี soft-tier ปน** — CMP006(check)×50, DT001(note)×29, DT002(note)×8, IV004(check), ITM019(check) ตกเลน "ต้องแก้" เพราะ lane logic ใช้ REVIEW_ONLY hardcoded แทน `code_labels.MAP` action-tier. ปรับให้ "ต้องแก้" เหลือเฉพาะ 'fix'-tier ได้ แต่เปลี่ยน output structure มาก = design call.
3. **DT002 future-date** = artifact ของ `PUOPUY_AUDIT_DATE=2026-06-02` ตรึง — production จริงหายเอง.
4. **DOC001 (ที่เหลือ) ตรวจ "ป้ายแท็บชีต vs วันบิล"** = เรื่อง organize ไฟล์ของผู้ใช้ ไม่ใช่ความผิดในใบกำกับ. ถ้าต้องการลด noise พิจารณาย้าย DOC001 → advisory tier (รออนุมัติ).

---

### ADR-058 — DOC001 SHORT-format false-positive: ชื่อชีตเลขล้วนที่เป็น "เทมเพลตก๊อป/บิลเดี่ยว" ถูกอ่านเป็น "วัน" · rebaseline c50fec27→ae84d3f0 (corpus) + 269ddaed→b5c415bb (fixture)
**วันที่:** 2026-06-21 · **สถานะ:** ACCEPTED, IMPLEMENTED · **golden เปลี่ยน `c50fec27` → `ae84d3f0`** (corpus, rebaseline ตั้งใจ) + **fixture `269ddaed` → `b5c415bb`** · **สั่งโดย:** ผู้ใช้ (อนุมัติชัดเจน — สานต่อรายการที่เลื่อนไว้ใน ADR-057 ข้อ 1) · **เติมเต็ม:** ADR-057 §รอผู้ใช้อนุมัติ ข้อ 1 (SHORT guard)

**Current risk (ก่อนแก้):** DOC001 SHORT producer (`rules_engine_rules_a.r_doc001`) flag false positive — ชื่อชีตเลขล้วน (bare integer) ถูกตีความเป็น "วันของเดือน" เสมอเมื่อ int(sheet) ≠ iv_date.day ทั้งที่ผู้ขายบางรายใช้ชื่อชีตเลขล้วนเพื่อจุดประสงค์อื่น (ลำดับบิล / เทมเพลตที่ Excel ก๊อป) → flag บิลที่ "ถูกต้อง" ว่าผิด ลดความเชื่อถือ Error Report.

**Root cause:** `r_doc001` ตั้งสมมุติฐาน "ชีตเลขล้วน = วันของเดือน" โดยไม่มีหลักฐานว่าไฟล์นั้นใช้ระบบตั้งชื่อชีตตามวันจริง. ชีตเลขล้วน 3 แบบที่ปนกัน: (1) วันจริง (SHS_68_02 ตั้งชื่อชีต 1,4,8,11,… = วันที่), (2) เทมเพลต Excel ก๊อป (TNT_69_03 ชีต "2","2 (2)"…"2 (10)" = สำเนา 10 ชุด วันเดียวกันหมด), (3) บิลเดี่ยว (TSH_69_039 ชีต "1" = บิลแรก ไม่ใช่ "วันที่ 1").

**Ground truth (อ่าน baseline.json 1056 บิล — DOC001 SHORT 3 ตัว):**
- **SHS_68_02 "6"** = TRUE POSITIVE (คงไว้): 11 ชีตเลขล้วน, **10 ตรงวัน** (1,4,8,11,14,17,19,21,24,27) → ไฟล์นี้ตั้งชื่อชีต=วันจริง → ชีต "6" (มีบิลวันที่ 7) = anomaly จริง.
- **TNT_69_03 "2"** = FALSE POSITIVE (ลบ): มีพี่น้องสำเนา "2 (2)".."2 (10)" (เทมเพลตก๊อป 10 ชุด, doc 03072–03081, วันที่ 11 ทุกใบ) → "2" คือเทมเพลต ไม่ใช่ "วัน".
- **TSH_69_039 "1"** = FALSE POSITIVE (ลบ): ไฟล์ชีตเดียว "1" (IV690304-04, วันที่ 4), 0 ชีตเลขล้วนยืนยันวัน → "1" = บิลแรก ไม่ใช่ "วันที่ 1".
- LONG producer 3 ตัว (TKH_68_0112 "11.10", TSH_68_0106 "1.2"/"4.2") = true positive คงครบ (คนละ producer — มี ADR-057 guard แล้ว).

**Recommended solution (2-signal guard ใน r_doc001 — surgical, "ลบ" FP เท่านั้น ไม่เพิ่ม flag):**
จะ flag ก็ต่อเมื่อมีหลักฐานทั้งสองข้อ (ใช้ `c['all_bills_for_iv_check']` หาพี่น้องในไฟล์เดียวกัน):
- (a) **corroborated day-naming:** ในไฟล์เดียวกันมีชีตเลขล้วน ≥2 ชีต (distinct) ที่ int(ชีต)==วันของบิลในชีตนั้น → ฆ่า lone-index FP (TSH_69_039 "1": 0 ชีตยืนยัน).
- (b) **ไม่ใช่เทมเพลตก๊อป:** ชีต "N" ไม่มี Excel copy-sibling `^0*N\s*\(\d+\)$` ในไฟล์เดียวกัน → ฆ่า template-batch FP (TNT_69_03 "2" มี "2 (2)"…).
guard รันเฉพาะตอน "จะ flag" (mismatch) เท่านั้น → cost O(bills/ไฟล์) แค่เคสหายาก, perf กระทบเล็กน้อย. คงข้อความ flag เดิม byte-identical → snapshot ของ true positive (SHS_68_02 "6") ไม่ขยับ.

**Migration risk / delta (วัด exact ด้วย independent re-simulation + deep-diff snapshot):**
- **Corpus:** DOC001 6→4 (−2) · เปลี่ยน **เฉพาะ 2 บิล**: TNT_69_03 "2" + TSH_69_039 "1" (ลบ DOC001, เพิ่ม 0) · 17/18 รหัสไม่ขยับ · 1056 บิล/148 ไฟล์เท่าเดิม · dup/iv_seq/iv_date/typos เหมือนเดิมเป๊ะ · **zero collateral**.
- **Fixture:** ชีต 2/4/6 (= วัน 15/20/25, 0 ชีตยืนยัน, ไม่มี copy-sibling) → ลบทั้ง 3 DOC001 → fixture เหลือ 0 DOC001 (`269ddaed` → `b5c415bb`). ถูกต้อง — flag เดิมของ fixture codify พฤติกรรมบั๊ก (uncorroborated bare-int = flag) ที่กำลังลบ.

**rebaseline:** `baseline.json` ใหม่ `ae84d3f0659c52fde2a17428850844156db77d6214dd73980e8da650d7186b24` · `tests/fixtures/baseline_fixture.json` ใหม่ `b5c415bbd7bf58bac4328fec1c868325e0955f423d01e9695ba50015fc2f02eb`. อัปเดต OPERATIONAL_SURFACES (.vscode×2/QUICKSTART/MAINTENANCE/Makefile/ci.yml/_SESSION_HANDOFF/DECISIONS banner+row/characterization label → ae84d3f0) + FIXTURE_SURFACES (Makefile/ci.yml/MAINTENANCE → b5c415bb) · เพิ่ม `c50fec27` ใน RETIRED_PREFIXES + `269ddaed` ใน RETIRED_FIXTURE_PREFIXES · GOLDEN.md current=ae84d3f0/fixture=b5c415bb + ledger. backup: `baseline.c50fec27.pre-adr058.json`, `tests/fixtures/baseline_fixture.269ddaed.pre-adr058.json`.

**Coverage replacement:** fixture เดิม codify DOC001 SHORT 3 ตัว (พฤติกรรมบั๊ก) → หลัง rebaseline fixture ไม่มี DOC001 แล้ว → เพิ่มเทสหน่วยเฉพาะ `test_doc001_short_guard.py` (positive: corroborated day-naming + mismatch → flag · negative-1: template-batch copy-sibling → ไม่ flag · negative-2: lone-index uncorroborated → ไม่ flag) กันสูญเสีย coverage.

**เทส/พิสูจน์ (เขียว @ ae84d3f0):** golden_master=`ae84d3f0` (cache-cleared, 2× identical = deterministic) · regression_full (engine==agent==baseline ✅) · check_invariants (fixture `b5c415bb` + pins ✅) · doc-sync PASS (prefix ae84d3f0) · test_doc001_short_guard PASS · test ชุดเดิม PASS.

**Long-term impact:** Error Report สะอาดขึ้น (ลบ SHORT FP ที่เหลือทั้ง 2 ตัว). guard อิงหลักฐานในไฟล์ (corroboration + copy-sibling) ไม่ hardcode รายไฟล์ → ทนไฟล์ใหม่. false negative ต่ำ (ไฟล์ที่ตั้งชื่อชีต=วันจริง guard ยังจับ anomaly เช่น SHS_68_02 "6").

**Priority:** MEDIUM (correctness ของ advisory report; ไม่กระทบ engine ผลตรวจหลัก แต่ rebaseline golden ตั้งใจ).

---

### ADR-059 — lane logic refactor: "ต้องแก้" ใช้ REVIEW_ONLY hardcoded แทน MAP action-tier (soft-tier ปนใน must-fix) · golden ไม่เปลี่ยน (advisory)
**วันที่:** 2026-06-21 · **สถานะ:** ACCEPTED, IMPLEMENTED · **golden ไม่เปลี่ยน `ae84d3f0`** (issue_consolidator อ่านอย่างเดียว — report layer) · **สั่งโดย:** ผู้ใช้ (อนุมัติชัดเจน — สานต่อ ADR-057 ข้อ 2) · **เติมเต็ม:** ADR-057 §รอผู้ใช้อนุมัติ ข้อ 2 (lane soft-tier ปน)

**Current risk (ก่อนแก้):** consolidated report (`build_consolidated_report.py` ผ่าน `issue_consolidator.consolidate_bill`) จัด spot ที่เป็น "ข้อสังเกตล้วน" (รหัสเลน check/note ทั้งหมด เช่น CMP006/DT001/DT002/IV004/ITM019) เข้าเลน **"ต้องแก้"** ผิด เพราะ bucket logic ใช้ `REVIEW_ONLY` (set hardcoded 11 รหัส) แทน action-tier จาก `code_labels.MAP` (source of truth เดียวกับ viewer) → ผู้ใช้เห็น "ต้องแก้" ปนของที่จริงเป็นแค่ "ข้อควรสังเกต" → คัดงานพลาด/เสียเวลา. desync ชนิดนี้ ADR-054/M6 เคยตามแก้ทีละรหัสแบบ manual (เปราะ).

**Root cause:** `REVIEW_ONLY` ถูก maintain แยกจาก `code_labels.MAP` → ทุกครั้งที่เพิ่มรหัสเลน soft ใน MAP ต้องจำไปเติม REVIEW_ONLY ด้วย (ไม่มีใครเฝ้า → ตกหล่น). MAP มี 4 เลน: fix(39)/check(17)/note(3)/review(10); REVIEW_ONLY hardcoded ครอบแค่ subset → เลน check/note ตกเป็น "ต้องแก้".

**Recommended solution (derive จาก MAP — surgical, แก้ที่ issue_consolidator.py จุดเดียว):**
`REVIEW_ONLY = {รหัสที่ MAP lane ∈ {check,review,note,master}} ∪ config.REVIEW_CODES` (frozenset).
- soft lane = ทุกเลนที่ "ไม่ใช่ fix".
- ∪ `config.REVIEW_CODES` เพื่อคง **ITM015** (MAP=fix แต่ ADR-051/054 จัดเป็น review: หน่วยซ้ำชื่อเดียว เช่น ทราย=[คิว,ตัน] = ผู้ขายขายหลายหน่วย ไม่ใช่ error) ไม่ให้ถอยกลับเป็น must-fix.
- มี fallback hardcoded เดิม (เผื่อ import code_labels/config ล้ม) → กันรายงานพังเฉย ๆ (longevity).
ไม่แตะ `MAP[ITM015]='fix'` (viewer/company_summary ใช้ `lane_of` ตรง → เปลี่ยน MAP จะกระทบ company_summary ซึ่งอยู่นอก scope ที่อนุมัติ) — sync ที่ชั้นนี้ด้วย ∪ config.REVIEW_CODES แทน.

**Migration risk / delta (simulate ด้วย consolidate_bill จริง บน snapshot ae84d3f0):**
- REVIEW_ONLY: 11 → 31 รหัส (เป็น **superset แท้** ของชุดเดิม — `เดิม − ใหม่ = ∅` → ย้ายได้ทางเดียว ต้องแก้→ข้อสังเกต ไม่มีย้อนกลับ).
- "ต้องแก้" (spot): 144 → 42 (**ย้าย 102 spot ไปข้อสังเกต**): CMP006×50, DT001×29, ITM019×13, DT002×8, IV004×2, ITM-combo (ITM005/ITM015).
- **Safety check (สำคัญสุด):** must-fix แท้ = (MAP=fix ลบ config.REVIEW_CODES = 38 รหัส รวม DOC001) → **0 spot ที่มี must-fix แท้ถูกย้ายไป soft** ✅ (zero false-soft).
- บิลดิบ (bill['issues']) ไม่ถูกแตะ — recall ครบ. company_summary (viewer) ไม่ขยับ (ใช้ MAP ตรง, ไม่ผ่าน issue_consolidator).

**rebaseline:** ไม่มี — golden hash ไม่เปลี่ยน (`ae84d3f0` ก่อน/หลังเท่ากัน, พิสูจน์ด้วย golden_master). issue_consolidator = advisory layer (pure read).

**เทส/พิสูจน์:** golden_master ก่อน/หลัง = `ae84d3f0` เท่ากัน (golden-neutral ✅) · import issue_consolidator → REVIEW_ONLY=31 (frozenset), DOC001∉ (must-fix คงไว้), CMP006/DT001/DT002/IV004/ITM019∈ (soft แล้ว), ITM015∈ (คง soft) · consolidate_bill simulation: 102 ย้าย, 0 must-fix แท้ตก soft · regression_full/check_invariants/doc-sync PASS.

**Long-term impact:** lane logic ผูกกับ MAP (source of truth เดียว) → เพิ่มรหัสใหม่ใน MAP แล้ว lane จัดถูกอัตโนมัติ ไม่ต้องเติม 2 ที่ (กัน desync ระดับโครงสร้าง — ปิดช่องที่ ADR-054/M6 เคยตามแก้ manual).

**Known follow-up (เลื่อน — ต้องอนุมัติ/นอก scope):** `MAP[ITM015]='fix'` ยังไม่สอดคล้องกับ ADR-051/054 (จัด ITM015 เป็น review). ปัจจุบัน sync ด้วย ∪ config.REVIEW_CODES ที่ชั้น report. ถ้าจะแก้ที่ MAP ต้องตรวจผลกระทบ company_summary (viewer) + อาจ rebaseline พื้นผิว golden-safe อื่น → ADR แยกในอนาคต.

**Priority:** MEDIUM (correctness ของ advisory report; ไม่กระทบ engine/golden — แต่ปรับคุณภาพการคัดงานของผู้ใช้โดยตรง).

### ADR-060 — packaging fix: ถอด `pythainlp` ออกจาก auto-install ใน requirements.txt (แก้ความขัดแย้ง requirements ↔ landmine #6) + แก้ corpus count 106→148 ใน constraints.txt · golden ไม่เปลี่ยน (packaging/doc เท่านั้น)
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **golden ไม่เปลี่ยน `ae84d3f0`** (แก้เฉพาะ `requirements.txt`/`constraints.txt` ระดับ comment/บรรทัด install — ไม่แตะโค้ด engine/parser/rules/validators/baseline) · **สั่งโดย:** Tor (อนุมัติชัดเจน — "นายจัดการเลย" สานต่อ audit 2026-06-22 ข้อเดียวที่เสนอให้แก้) · **เกี่ยวข้อง:** landmine #6 (CLAUDE.md §6), ADR-048 (corpus 106→148)

**Current risk (ก่อนแก้):** `requirements.txt` ระบุ `pythainlp==5.0.5` เป็นบรรทัด install ปกติ → คนดูแลคนถัดไป (รวม Claude Code session ใหม่) ที่ทำ `pip install -r requirements.txt` ตรง ๆ ตามคำสั่งในไฟล์ **จะติดตั้ง pythainlp เข้าสาย golden/production** ทั้งที่ landmine #6 ใน `CLAUDE.md` สั่งห้ามชัดเจน ("golden 51 typo มาจาก `CONSTRUCTION_DICT` ไม่ใช่ pythainlp — ติดเมื่อใด hash drift"). เป็น **ความขัดแย้งในเอกสารกันเอง** (requirements บอกให้ลง / CLAUDE.md ห้ามลง) = กับดักที่ทำให้เกิด golden drift เงียบในอนาคตได้จริง. รองลงมา: `constraints.txt` คำสั่ง rebuild ยังเขียน "<ข้อมูลจริง 106 ไฟล์>" (2 จุด) ซึ่งค้างจากก่อน ADR-048 (corpus ขยาย 106→148) → คนทำ rebuild ตามคำสั่งบน 106 ไฟล์จะได้ hash คนละค่า แล้วเข้าใจผิดว่าระบบเพี้ยน.

**Root cause:** (1) pythainlp ถูกใส่ใน requirements.txt ตั้งแต่ก่อนค้นพบว่ามันเป็นต้นเหตุ drift เสี่ยง (golden ทำโดยไม่มีมัน) — ไม่เคยถอดออกเพราะ version_gate รองรับ "missing=OK" อยู่แล้ว เลยไม่มีอาการ แต่ trap ยังอยู่ในไฟล์. (2) corpus count ใน constraints.txt comment ไม่ถูกอัปเมื่อ ADR-048 ขยาย corpus.

**Recommended solution (surgical — แตะ 2 ไฟล์ comment-level เท่านั้น):**
- `requirements.txt`: ถอดบรรทัด `pythainlp==5.0.5` ออกจากชุด auto-install → แทนด้วย comment block อธิบาย (OPTIONAL display-layer; golden สร้างโดยไม่มีมัน; landmine #6; วิธีติดตั้งแยกถ้าจำเป็นจริง `pip install pythainlp==5.0.5`). คง deps หัวใจ + display อื่นครบเดิม.
- `constraints.txt`: **คง** `pythainlp==5.0.5` เป็น constraint-only pin (constraints ไม่ trigger install — มีผลเฉพาะถ้าถูกติดตั้งแยก → คนที่จงใจลงยังได้เวอร์ชันตรึง 5.0.5) + comment ชี้ว่าจงใจถอดจาก requirements. + แก้ "106 ไฟล์" → "148 ไฟล์" (2 จุด) ให้คำสั่ง rebuild ชี้ corpus ปัจจุบัน.
- **ไม่แตะ `config._LOCKED`** (= source of truth ของ version_gate; ยังตรึง pythainlp 5.0.5 ไว้เป็น "เวอร์ชันที่เคยเทสต์" และ version_gate ถือเป็น `OPTIONAL_CRITICAL` = missing-OK อยู่แล้ว) → พฤติกรรม version gate เดิมทุกประการ.

**Migration risk / delta:**
- พฤติกรรม `pip install -r requirements.txt` เปลี่ยน: **ไม่ลง pythainlp อีกต่อไป** — ซึ่งเป็นพฤติกรรมที่ "ถูกต้อง" ตาม landmine #6 (สาย golden/production ต้องไม่มี pythainlp). = ทำให้ requirements สอดคล้องกับ invariant จริง.
- pythainlp เป็น leaf dependency (ไม่มี core lib ใด — pandas/numpy/openpyxl/xlrd/rapidfuzz — พึ่งมัน) → ถอดออกแล้วชุด install ที่เหลือครบ ไม่มี transitive หาย.
- โค้ดรองรับ pythainlp absent อยู่แล้ว (thai_text.py มี guard; cache `_PYTHAINLP_CACHE` lazy) → ไม่มี ImportError/crash.
- เชิงประจักษ์: golden `ae84d3f0` reproduce **โดยไม่มี pythainlp** บน 148 ไฟล์จริง (engine==agent==baseline) + run_ci.sh เต็มเขียว — พิสูจน์ในเซสชันนี้.

**rebaseline:** ไม่มี — golden hash ไม่เปลี่ยน (`ae84d3f0` ก่อน/หลังเท่ากัน). `requirements.txt` ไม่อยู่ใน OPERATIONAL_SURFACES ของ doc-sync (ไม่ถูกสแกน). `constraints.txt` อยู่ใน list แต่ doc-sync ตรวจแค่ "มี current hash (หรือ neutral ref `baseline.json._sha256`) + ไม่มี retired prefix" — neutral ref ใน header ยังอยู่ครบ, ไม่มี retired hash หลุดเข้า → doc-sync ผ่าน.

**เทส/พิสูจน์ (เซสชันนี้, Python 3.12.3 + corpus 148 ไฟล์):** `regression_full.py . /mnt/project` → engine==agent==baseline=`ae84d3f0` ✅ · `test_golden_single_source.py` → PASS (doc-sync) ✅ · `INVARIANTS/check_invariants.py` → 4/4 ✅ · `run_ci.sh /mnt/project` → ✅ CI ผ่านทั้งหมด (84 step, serial==parallel golden=`ae84d3f0`) · ไม่มี retired hash prefix ใน 2 ไฟล์ที่แก้.

**Long-term impact:** ปิดกับดัก golden-drift ที่ใหญ่ที่สุดสำหรับ onboarding คนดูแลใหม่ — requirements.txt สอดคล้องกับ landmine #6 แล้ว (ไม่ต้องพึ่งว่าผู้ติดตั้งจะ "จำได้" ว่าห้ามลง pythainlp). คำสั่ง rebuild ใน constraints.txt ชี้ corpus ถูกต้อง (148) → ลดความสับสนตอน reproduce golden ในอีก 5 ปี.

**Priority:** LOW–MEDIUM (packaging/doc hazard — ไม่ใช่บั๊กการทำงาน แต่เป็นต้นเหตุ incident ที่อาจเกิดได้ถ้าคนดูแลใหม่ทำตาม requirements.txt ตรง ๆ).

---

### ADR-061 — master.save_master รู้จัก stub: กัน "stub ทดสอบ" สำรองทับ `.bak` กู้คืนของจริง · golden ไม่เปลี่ยน (`ae84d3f0`)
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **golden ไม่เปลี่ยน** (`save_master` ไม่อยู่บนเส้น engine/parse/rules — corpus regression ใช้ `load_master` ที่ strip `_golden_stub` อยู่แล้ว) · **สั่งโดย:** Tor (เลือก "แก้ M-2/M-3/M-4 golden-neutral" ในรอบ audit 5-year 2026-06-22) · **เกี่ยวข้อง:** ADR-039/040/049 (master kill-safe), CLAUDE.md landmine #6 (master kill-safe).

**Risk (ก่อนแก้):** `master.save_master` (`master.py`) สำรองไฟล์ live → `.bak` ก่อนทับ โดย guard ตัดสินจาก **จำนวน key อย่างเดียว** (`_json_dict_len(current) >= _json_dict_len(bak)`). ต่างจาก `golden_snapshot.write_master_file` ที่ "รู้จัก stub" (`_file_has_stub_marker`). ถ้าเครื่องมือ golden/test ทิ้ง **stub** ไว้เป็นไฟล์ live (stub = 1 บริษัท + key `_golden_stub` → นับได้ ≥ master จริงขนาดเล็ก) แล้วผู้ใช้ `save_master` รอบใหม่ → **คัดลอก stub ทับ `.bak`** ที่เป็นจุดกู้คืนจริง. พิสูจน์ด้วย repro (พบโดยอิสระ 2 สาย audit). ผลกระทบ "วงแคบ": ไฟล์ live ที่ผู้ใช้เพิ่ง save ยังถูกต้อง + `.bak` (ไม่ใช่ `.user.bak`) ระบบไม่ auto-restore → กระทบเฉพาะ "สำเนากู้คืนด้วยมือ" รุ่นก่อน. = ความไม่สอดคล้องระหว่าง 2 ชั้น (golden_snapshot รู้ stub / save_master ไม่รู้).

**Solution (surgical):** เพิ่ม `_text_is_golden_stub(text)` ใน `master.py` (สมมาตรกับ `golden_snapshot._file_has_stub_marker`) → ใน `save_master` ถ้า live เป็น stub → `keep=False` (ข้ามสำรอง) ก่อนถึง shrink-guard เดิม. ของจริงที่ "หด" ยังกัน `.bak` ตาม ADR-040 เดิมทุกประการ.

**Delta/golden:** ไม่เปลี่ยน — `save_master`/`.bak` ไม่ไหลเข้า hash ใด ๆ. พิสูจน์: `check_invariants.py` 4/4 (`b5c415bb`) + `run_ci.sh` exit 0 (fixture regression `b5c415bb`, engine==agent==baseline) ก่อน/หลังเท่ากัน · ทางการ corpus `ae84d3f0` ไม่กระทบ (รอเจ้าของยืนยันบน 3.12/148 ไฟล์ตามวินัย).
**เทสกันถอย:** `test_recheck_5year.py` [1]+[2] (stub ไม่ทับ .bak + ADR-040 shrink-guard ไม่ถอย) เข้า CI ที่ `[3x14e]`.
**rebaseline:** ไม่มี. **Priority:** MEDIUM (data-loss วงแคบ — สำเนากู้คืนด้วยมือ).

---

### ADR-062 — report retention (เก็บกวาดรายงานเก่า) กันดิสก์โตไม่จำกัดเมื่อรันยาวหลายปี · default ปิด (golden-neutral)
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **golden ไม่เปลี่ยน** (ฟังก์ชันใหม่ ไม่ถูก engine เรียก; default ปิด = พฤติกรรมเดิมเป๊ะ) · **สั่งโดย:** Tor (audit 5-year 2026-06-22).

**Risk (ก่อนแก้):** รายงานหลัก `audit_v58_<ts>.xlsx` (ตั้งชื่อตามเวลา) + โหมด AUTO สร้าง `ตรวจแล้ว_<ts>_<pid>/` ทุกรอบ — **ไม่มีโค้ดลบ/หมุนเวียน** → ดิสก์โตเรื่อย ๆ ตลอด 5 ปี (ไฟล์ input ถูก *ย้าย* ออก input dir ไม่บวม — ที่โตคือ report/archive dir). ไม่ใช่ปัญหา RAM/fd (พิสูจน์แล้วนิ่ง) แต่เป็น operational longevity.

**Solution (surgical):** เพิ่ม `_prune_old_reports(report_dir, keep_days)` ใน `pukpui_modular_funcs.py` (ลบเฉพาะ pattern `audit_v58_*.xlsx` + `ตรวจแล้ว_*` ที่ mtime เก่ากว่า keep_days วัน · ห่อ try/except รายไฟล์ · ไม่แตะไฟล์ผู้ใช้อื่น) → main entry เรียกหลัง report สำเร็จ, gate ด้วย env `PUKPUI_REPORT_RETENTION_DAYS` (**default `0` = ปิด = เก็บทุกไฟล์ = พฤติกรรมเดิม**).

**Delta/golden:** ไม่เปลี่ยน — default ปิด, ฟังก์ชันไม่อยู่บนเส้น engine. พิสูจน์เดียวกับ ADR-061 (CI exit 0 / fixture `b5c415bb`).
**เทสกันถอย:** `test_recheck_5year.py` [3] (default ปิดไม่ลบ / เปิดลบเฉพาะ artifact เก่า / ไม่แตะไฟล์ผู้ใช้).
**rebaseline:** ไม่มี. **Priority:** MEDIUM (operational — เปิดเมื่อ deploy จริงยาว ๆ).

---

### ADR-063 — utf-8 console: กัน `print` ภาษาไทย crash ใต้ locale ascii (LANG=C/cron) · golden-neutral
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **golden ไม่เปลี่ยน** (เปลี่ยนแค่ encoding ขาออกของ stdout/stderr — ไม่แตะค่าที่เข้า hash; เรียกเฉพาะใน `__main__` ไม่ใช่ตอน import) · **สั่งโดย:** Tor (audit 5-year 2026-06-22).

**Risk (ก่อนแก้):** รันใต้ stdout ที่ไม่ใช่ UTF-8 (เช่น `LANG=C`, บาง cron/systemd ที่ไม่ตั้ง locale) → `print()` ภาษาไทย `UnicodeEncodeError` **ตั้งแต่เริ่ม** (ก่อนแตะไฟล์ใด ๆ) = งานล่มทันทีตอน deploy. เป็นความเสี่ยง "สภาพแวดล้อม" ที่เจอบ่อยเมื่อรันยาวข้ามเครื่อง/ปี.

**Solution (surgical):** เพิ่ม `_ensure_utf8_console()` ในไฟล์ entry หลัก → `sys.stdout/stderr.reconfigure(encoding='utf-8')` (Python 3.7+, ห่อ try/except, idempotent) เรียกบรรทัดแรกของ `if __name__ == '__main__'`. ถ้า reconfigure ไม่ได้ → เงียบ (พฤติกรรมเดิม).

**Delta/golden:** ไม่เปลี่ยน. พิสูจน์เดียวกับ ADR-061/062.
**เทสกันถอย:** `test_recheck_5year.py` [4] (เรียกซ้ำได้ ไม่ throw).
**rebaseline:** ไม่มี. **Priority:** MEDIUM (environmental hardening — กันงานล่มตอน deploy/cron).

> **หมายเหตุ audit 5-year 2026-06-22 (เปิดไว้ รอเจ้าของสั่ง):** **M-1 / `r_dt003` (rules_engine_rules_a.py:532 `yr>2030`)** = ระเบิดเวลาในกรอบ 5 ปี: ตั้งแต่ ค.ศ. 2031 (พ.ศ. 2574) บิลปกติทุกใบติด NOTE "digit-swap ของตัวเอง"/"ปีคลุมเครือ" (reproduce แล้ว; เคยบันทึก v9.3.1 "Validators-M1"). เป็น **golden-sensitive** (แตะ logic กฎ) → **STOP-AND-ASK + regression 148 ไฟล์ก่อนแก้** (คาด golden-neutral เพราะ corpus ≤2026 ไม่แตะแบนด์ >2030). ยังไม่แก้ในรอบนี้ — รออนุมัติ. รายละเอียด: `AUDIT_5YEAR_READINESS_pukpui_v9_3_4_TH.md`.

---

### ADR-064..076 — แก้บั๊ก "กฎที่เปิดใช้งาน" (deep audit รอบ 2026-06-22) · Tor อนุมัติ "แก้ทั้งหมด"
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED (โค้ด+เทส) · **สั่งโดย:** Tor ("แก้เลยครับผม แก้ทั้งหมด และส่งระบบที่สมบูรณ์")
**ขอบเขต:** deep audit เฉพาะกฎ `enabled:True` 57 ตัว (5 สายขนาน + verify ซ้ำ) → พบ + แก้ตามนี้. ทุกข้อ reproduce ก่อน-หลัง.
**พิสูจน์ (เท่าที่ cloud env ทำได้):** fixture `b5c415bb` **ไม่ขยับ** · `check_invariants` 4/4 · `test_golden_single_source` PASS · `run_ci.sh` (no-data) exit 0 + เทสใหม่ `[3x14f]` (+`[3x14e]`) · ทุกไฟล์ ≤600 LOC.

| ADR | รหัส | ไฟล์ | แก้ | corpus 148 |
|---|---|---|---|---|
| 064 | **M-1 DT003** | rules_engine_rules_a.py | `yr>2030` → `yr>audit_today().year+1` (ขอบเขตตามเวลา) กันฟ้องบิลปีปัจจุบันเป็น digit-swap ตัวเอง ตั้งแต่ ค.ศ.2031 | golden-neutral (DT003=0) |
| 065 | **CMP003** | rules_engine_rules_a.py | brand blacklist substring → ขอบคำละติน (`(?<![A-Za-z0-9])…(?![A-Za-z0-9])`) กัน CP∈CPF/Tops∈Laptops | golden-neutral (CMP003=0) |
| 066 | **BR001/BR004** | rules_engine_rules_a.py | `'สำนัก' in` → `'สำนักงานใหญ่'/'สนญ'` เต็มคำ กัน "สาขา สำนัก…" ถูกตีเป็นสนญ. | golden-neutral (BR001=0) |
| 067 | **DOC001** | rules_engine_rules_a.py | +guard `1≤int(sheet)≤31` (สอดคล้องเส้น `apply_sheet_date_crosscheck`) กันชีตเลข >31 ตีเป็น "วัน" | golden-neutral (corpus มีแต่ชีต "6"=วันจริง) |
| 068 | **ADDR002** | rules_engine_rules_a.py | ต่างแค่เว้นวรรค (พระราม4 vs พระราม 4) → ไม่ฟ้องสะกดผิด (สอดคล้อง ADDR001) | golden-neutral (ADDR002=0) |
| 069 | **C-1 VAT006/007** | rules_engine_rules_c.py + parser_p2.py | กัน `_D()=None` (เงิน non-finite) ก่อนคำนวณ (เลน TypeError หลุด except → ข้ามกฎ CRITICAL เงียบ) + `math.isfinite` ใน `_tor_scan_*` | golden-neutral (VAT006/007=0; corpus ไม่มี non-finite) |
| 070 | **ITM016** | rules_engine_rules_c.py | dedup key +qty +amount → รายการแยกจริง (qty ต่าง) ไม่ฟ้องซ้ำ | **เปลี่ยน corpus** (ITM016=10, FP 4 บิล) → **rebaseline** |
| 071 | **ADDR005** | rules_engine_rules_c.py | ตัดส่วน "โทร/แฟกซ์" ก่อนหาไปรษณีย์ กันเลข 5 หลักท้าย (เบอร์โทร) ถูกตีเป็น zip | golden-neutral (ADDR005=0) |
| 072 | **DOC003** | rules_engine_rules_c.py | บิลไม่มีวันที่ (None==None) → ไม่ฟ้องซ้ำ (DT005 จับ missing-date แล้ว) | golden-neutral (DOC003=0) |
| 073 | **DT004** | validators.py | YYMM จากเลขนำ ต้อง ≥5 หลัก (เดิม prefix+4หลัก เช่น PO2501 ถูกตีเป็น ปี25/ด.01) | golden-neutral (DT004=0) |
| 074 | **C-2 เลขภาษีไทย** | puopuy_core.py | `clean_tax_id` แปลงเลขไทย ๐-๙ → อารบิก ก่อน strip (ครอบ TAX001/003/005/007/008) | golden-neutral (ไม่มีเลขไทยใน corpus) |
| 075 | **ITM004** | config_base.py | ตัด `0-9` จาก lookaround SPELLING (เลขติดไทย "5นิ้ว" ไม่ใช่ "อังกฤษ+ไทย") | **เปลี่ยน corpus** (ITM004=814, INFO/filtered) → **rebaseline** |
| 076 | **ITM010** | config_base.py | กัน "วาว"/ประกายวาว/วาววับ ถูกเดาเป็น "วาล์ว" (ยังจับ บอลวาว/เกจวาว) | golden-neutral ("วาว" legit=0 ใน corpus) |

**ITM009 (dormant):** กฎ `enabled` แต่ `product_master.json` ไม่มีในแพ็ก → คืน `[]` เสมอ. **ไม่แก้โค้ด** (กฎถูกต้อง ทำงานเมื่อมีไฟล์ data) — เป็น "ขาด data file ทางเลือก" ไม่ใช่บั๊กโค้ด. บันทึกไว้ให้เจ้าของเติม data หรือคงไว้ dormant.

**⚠️ REBALINE REQUIRED (เครื่องเจ้าของเท่านั้น — cloud นี้ไม่มี corpus + เป็น Python 3.11):**
ADR-070 (ITM016) + ADR-075 (ITM004) **เปลี่ยนผลตรวจ corpus 148 ไฟล์จริง** (ลบ false-positive) → golden `ae84d3f0` **จะเปลี่ยน** = ตั้งใจ (ผลถูกขึ้น). ที่เหลือ (064-069,071-074,076) golden-neutral (0 occurrence ใน baseline.json). เจ้าของต้องรันบน **Python 3.12 + /mnt/project**:
```
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1
python3 regression_full.py . /mnt/project        # จะ MISMATCH ae84d3f0 (คาดไว้ — ITM004/ITM016 เปลี่ยน)
# ตรวจ diff ทุกบิลว่าเปลี่ยน "เพราะ ITM004/ITM016 ลบ FP" เท่านั้น (ไม่มี regression อื่น)
python3 golden_master.py . /mnt/project baseline.json --write   # เขียน baseline ใหม่ (ดู MAINTENANCE/REBUILD_STATUS)
python3 test_golden_single_source.py             # มันจะบอก operational surface ที่ต้องอัปค่า hash ใหม่
bash run_ci.sh /mnt/project                       # ต้อง exit 0 บน golden ใหม่
```
**rebaseline:** **จำเป็น** (เฉพาะ ITM004+ITM016). **Priority:** C-1/C-2 = HIGH (FN/FP บนกฎ CRITICAL) · CMP003/BR/ITM016/DOC001/DT004 = MEDIUM (FP เลน fix) · ที่เหลือ = LOW.

---

### ADR-077 — REBASELINE เสร็จสมบูรณ์: golden `ae84d3f0` → `08e6abfd` (ปิดงาน ADR-064..076 บนเครื่องที่มี corpus + Python 3.12)
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("แก้ไขทั้งหมด และ ส่งระบบที่สมบูรณ์มาให้กับเรา")
**บริบท:** ADR-064..076 (deep audit รอบ 2026-06-22) ทำการแก้โค้ดครบแล้ว แต่ทำบนเครื่อง cloud ที่ **ไม่มี corpus 148 ไฟล์ + เป็น Python 3.11** → ยืนยัน golden เต็มบนข้อมูลจริงไม่ได้ จึงทิ้ง `baseline.json` ไว้ที่ `ae84d3f0` พร้อมโน้ต "⚠️ REBASELINE REQUIRED". ผลคือ engine ผลิต `08e6abfd` แต่ baseline ยังเป็น `ae84d3f0` (สถานะ inconsistent/รอ rebaseline). ADR นี้ปิดงานนั้นบนเครื่องที่มี **/mnt/project (148/1056) + Python 3.12.3**.

**ตัวขับ rebaseline (เปลี่ยนผล corpus จริง) — ยืนยันแล้วว่าเป็น false-positive จริง:**
- **ADR-075 ITM004** (เลขติดอักษรไทย): spot-check ชื่อสินค้าจริงที่ถูก suppress = `"ยาว 1ม."`, `"หนา 3มม."`, `"เหล็กแป็ปกลมดำ 4นิ้ว"`, `"60x30x10มม."` — ล้วนเป็น **การเขียนไทยปกติ** (เลข+หน่วยไทย ไม่ต้องเว้นวรรค). flag เดิม "อังกฤษ+ไทยติดกัน" = false-positive แท้ → ลบถูกต้อง.
- **ADR-070 ITM016** (dedup key +qty +amount): สินค้าเดียวกัน ราคา/หน่วยเท่ากัน แต่ qty ต่าง = คนละบรรทัดจริง → เดิมฟ้อง "ซ้ำ" ผิด (FP 4 บิล) → แก้ถูกต้อง.
- ที่เหลือ (064-069, 071-074, 076) golden-neutral จริง (0 occurrence — ยืนยันด้วย regression: revert เฉพาะ ITM004+ITM016 ทำให้ golden กลับ `ae84d3f0` เป๊ะ ∴ สองตัวนี้คือตัวขับเดียว).

**สิ่งที่ทำในการ rebaseline:**
1. `baseline.json` regenerate ใหม่ผ่าน `golden_master.py . <out> /mnt/project` → `_sha256 = 08e6abfddd6cff6d…` (148/1056) · backup ของเดิมไว้.
2. เพิ่ม `ae84d3f0` เข้า `RETIRED_PREFIXES` (test_golden_single_source.py) พร้อมโน้ตเหตุผล.
3. อัปทุก OPERATIONAL_SURFACES (tasks/launch.json, _SESSION_HANDOFF, QUICKSTART, Makefile, ci.yml, MAINTENANCE, DECISIONS banner) `ae84d3f0`→`08e6abfd` (full+prefix). ledger ประวัติคง `ae84d3f0` ไว้ (ถูกต้องตามเวลา ไม่เขียนทับ).
4. `GOLDEN.md`: ย้าย `08e6abfd` เป็น ✅ ปัจจุบัน · `ae84d3f0` → ⏮️ ปลดระวาง.
5. **fixture `b5c415bb` ไม่ขยับ** (FP fixes ไม่แตะ 3 บิล fixture) → ไม่ต้อง rebaseline fixture.

**พิสูจน์ (เครื่อง corpus จริง + Python 3.12.3):**
- `regression_full.py . /mnt/project baseline.json` → engine == agent == baseline = **`08e6abfd`** ✅
- `check_invariants.py` → fixture `b5c415bb` ✅ · `test_golden_single_source.py` → PASS (สแกน 08e6abfd, no retired) ✅
- `run_ci.sh /mnt/project` → exit 0 (ครบทุก step รวม `[3x14e]`/`[3x14f]`) ✅
- แพ็กผ่าน `make_release.py` (build→extract→verify) + fresh-extraction reproduce `08e6abfd` ✅

**ความเสี่ยง/หมายเหตุ:** การ rebaseline นี้ "รับ" การลด false-positive ที่ Tor อนุมัติ ("แก้ทั้งหมด") + ตรวจแล้วเป็น FP แท้. ผลตรวจ "ถูกขึ้น" (noise ลด, ไม่มี must-fix ที่หาย — ITM004 อยู่เลน INFO/advisory). ถ้าภายหลังพบว่าการ suppress ตัวใดผิด ให้ revert ตัวนั้น + rebaseline กลับ (ADR ใหม่). `ae84d3f0` เก็บใน RETIRED + backup เพื่อย้อนได้.

---

### ADR-078 — packaging hygiene: make_release ตัดไฟล์ output ของเครื่องมือ (snapshot.json / _iv_truth_report.json) ออกจาก release
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("แพคระบบที่สมบูรณ์... เช็คก่อนเพื่อจะเจอบั๊ค")
**บั๊กที่พบ (QA ก่อนส่ง):** `_audit_iv_truth.py` (CI step [8d]) เขียน `_iv_truth_report.json` ลง cwd เสมอ และ `golden_master.py` (default OUT) เขียน `snapshot.json` — ทั้งคู่เป็น **output ของเครื่องมือ ไม่ใช่ source** แต่ `make_release.EXCLUDE_EXACT` มีแค่ `master_companies.json` → ไฟล์ทั้งสองหลุดเข้า release zip (พบใน `pukpui_v9_3_4_REBASELINED_08e6abfd_20260622.zip`).
**แก้:** เพิ่ม `snapshot.json` + `_iv_truth_report.json` เข้า `EXCLUDE_EXACT` ของ make_release.py. golden-neutral (แตะเฉพาะ packaging tool ไม่แตะ engine/baseline). ป้องกัน stray-file leak ในทุก release ถัดไป.
**พิสูจน์:** rebuild release ใหม่ → fresh-extraction ยืนยันไม่มี `snapshot.json`/`_iv_truth_report.json`/`master_companies.json` + reproduce golden `08e6abfd`.

---

### ADR-079 — ประกัน 5 ปี: freeze environment (wheelhouse + lockfile + Dockerfile) + pin CI runner
**วันที่:** 2026-06-22 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("แก้ไขทั้งหมด และ ทำการเทส และ ส่งระบบที่สมบูรณ์")
**บริบท:** Python 3.12 EOL = ตุลาคม 2028 (กลางช่วง 5 ปี). เดิมแพ็ก pin deps เป็น "เลขเวอร์ชัน" เฉย ๆ ไม่มี frozen wheel → ถ้า rebuild บนเครื่องใหม่ปี 2029+ เสี่ยง deps หายจาก PyPI/ลงไม่ได้. นี่คือจุดเสี่ยง 5 ปี ตัวเดียวที่ค้าง.
**สิ่งที่ทำ (golden-neutral — ไม่แตะ engine/baseline):**
1. **`vendor/wheels/`** — 21 wheel (cp312, linux x86_64) ดึงด้วย `pip download -r requirements.txt -c constraints.txt --only-binary=:all:`.
   - ⚠️ **บทเรียน:** ครั้งแรกลืม `-c constraints.txt` → ได้ **numpy 2.5.0** (golden ใช้ **2.2.6**) = จะ drift. แก้ด้วยการใส่ `-c` → numpy 2.2.6 ถูกต้อง. **ไม่มี pythainlp** (landmine #6).
2. **`requirements.lock`** — ตรึงทุกแพ็กเกจ + sha256 (ติดตั้งด้วย `--no-index --find-links vendor/wheels --require-hashes`).
3. **`Dockerfile`** + **`.dockerignore`** — `FROM python:3.12-slim`, ติดตั้ง offline จาก wheelhouse, smoke-test fixture invariant ตอน build.
4. **`BUILD_OFFLINE.md`** — คู่มือ 2 วิธี (venv offline / Docker) + วิธีสร้าง wheelhouse ใหม่ (เตือนเรื่อง `-c constraints.txt`).
5. **pin `ci.yml`** `runs-on: ubuntu-latest` → **`ubuntu-24.04`** (2 จุด: บรรทัด 16, 96) กัน image drift ข้ามปี.
**พิสูจน์ (เทสต์จริง):** สร้าง fresh venv → `pip install --no-index --require-hashes` สำเร็จ (hash ผ่านครบ 21 แพ็ก, numpy 2.2.6, ไม่มี pythainlp) → `regression_full.py . /mnt/project` ใน frozen venv = engine==agent==baseline = **`08e6abfd`** ✅. doc-sync/CI/make_release เขียวครบ.
**ผล:** rebuild ได้เอง offline ถึง 2030+ (venv หรือ Docker). ข้อจำกัด: wheelhouse เป็น linux x86_64/cp312 — Windows/macOS native ต้องสร้าง wheelhouse แยก (หรือใช้ Docker = แนะนำ).

---

### ADR-080 — close-out doc-drift: sync `ae84d3f0`/`ba9deda0` ที่ตกค้าง → `08e6abfd` (3 surface) + ปิดช่อง guard
**วันที่:** 2026-06-23 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ลุยตามคำสั่ง และ ส่งระบบที่สมบูรณ์") · **โซน:** 🟢 เขียว (golden-neutral — แตะเฉพาะ doc/comment/label + test guard)
**บริบท (root cause):** ADR-077 rebaseline `ae84d3f0`→`08e6abfd` "ครบทุก OPERATIONAL_SURFACES" — แต่พื้นผิว 3 ตัวที่ **อ้าง hash แต่ไม่เคยอยู่ใน `test_golden_single_source.OPERATIONAL_SURFACES`** จึงไม่โดน CI จับและถูกข้ามไป:
- `CLAUDE.md` (cold-start contract, สำคัญที่สุด) — §0.4/§1.1/§5/§7.1/§8 ค้าง `ae84d3f0` (6 จุด) → session อนาคตอ่าน §8 แล้วรัน baseline check คาดหวัง `ae84d3f0` → ได้ `08e6abfd` → สรุปผิดว่า "ระบบเพี้ยน หยุด".
- `run_ci.sh` (comment บรรทัด 6 + step-name [7]) ค้าง `ba9deda0` → gate ทำงานถูก (อ่าน `baseline.json` จริง) แต่ comment ลวงคนอ่าน.
- `test_date_parse_characterization.py` (characterization label 3 จุด) ค้าง `ae84d3f0` — ทั้งที่ CLAUDE.md §6 ระบุ "characterization label" เป็น rebaseline surface (label เท่านั้น; CASES ตรงพฤติกรรมปัจจุบันแล้ว → เทสยังเขียว 36/36).
**สิ่งที่ทำ (surgical):**
1. แทน `ae84d3f0`→`08e6abfd` ใน CLAUDE.md (6) + test_date_parse_characterization.py (3); `ba9deda0`→`08e6abfd` ใน run_ci.sh (2).
2. `requirements.txt` (ADR-060 note): เขียนใหม่ให้ชี้ golden ปัจจุบัน `08e6abfd` (= baseline.json._sha256) + คงบันทึกประวัติว่าพิสูจน์ครั้งแรก 2026-06-22 ตอน golden ยังเป็น `ae84d3f0` (provenance — เหมือน GOLDEN.md จึงไม่เข้า guard).
3. **เพิ่ม `CLAUDE.md` + `run_ci.sh` + `test_date_parse_characterization.py` เข้า `OPERATIONAL_SURFACES`** ของ `test_golden_single_source.py` → ครั้งหน้า rebaseline ลืมอัปไฟล์ใดไฟล์หนึ่ง = CI แดงทันที (ปิด root cause ถาวร).
**พิสูจน์ (golden-neutral):** ไม่มีโค้ด engine/leaf/parser/rule ถูกแตะ. `check_invariants.py` → fixture `b5c415bb` ✅ (engine==agent==baseline) · `test_golden_single_source.py` → PASS (สแกน 08e6abfd + 3 surface ใหม่, no retired) ✅ · `test_date_parse_characterization.py` → 36/36 ✅ · `test_reachability.py` → ✅.
**ข้อจำกัดสภาพแวดล้อม (โปร่งใส):** รอบนี้ทำบน cloud ที่ **ไม่มี corpus 148 ไฟล์** → ยืนยัน corpus golden `08e6abfd` ได้จาก **ไฟล์** (`baseline.json._sha256`) เท่านั้น ไม่ได้ re-run `regression_full.py . /mnt/project`. การแก้ทั้งหมดเป็น doc/comment/label/test-guard ซึ่ง **ไม่แตะ execution path ของ golden โดยโครงสร้าง** → golden ขยับไม่ได้. fixture (3 บิล รันได้จริง) ยืนยัน engine ไม่ขยับ.

---

### ADR-081 — แก้เทสขัด golden (test_rules_typo_branch "5นิ้ว") + ปิดช่อง "orphan test" ที่ run_ci.sh ไม่เคยรัน
**วันที่:** 2026-06-23 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ลุยตามคำสั่ง และ ส่งระบบที่สมบูรณ์") · **โซน:** 🟢 เขียว (golden-neutral — แก้เฉพาะไฟล์เทส + CI runner)
**บั๊กที่พบ (forensic):** `test_rules_typo_branch.py:61` assert `len(r_itm004("ท่อ 5นิ้ว")) > 0` ("5นิ้ว ต้องฟ้อง") — **ขัด golden ปัจจุบัน `08e6abfd`** ตรง ๆ: ADR-075 ตัด 0-9 ออกจาก lookaround + UNIT_OK guard ทำให้ "5นิ้ว"/"60x30มม." = เขียนไทยปกติ → ไม่ฟ้อง (เป็นตัวขับ rebaseline ADR-077). หลักฐานตรงข้าม 3 ชั้น: (1) engine จริงคืน `[]`, (2) `test_recheck_rules_20260622.py:84` assert `==[]` ("5นิ้ว ไม่ฟ้อง") **ผ่าน** ในชุด CI, (3) GOLDEN.md ADR-064 ระบุ "ITM004 ['5นิ้ว'/'60x30มม.']=เขียนไทยปกติ". → เทสนี้ "ค้างจากก่อน ADR-075" และ **ขัดกับเทสอีกตัวบนโค้ดชุดเดียวกัน**.
**ทำไมไม่ถูกจับ (root cause เชิงระบบ):** `test_rules_typo_branch.py` เป็น **orphan** — `run_ci.sh` ไม่เคยรันเป็น step (มีแต่ `coverage_gate.py` ที่รันใต้ coverage แล้ว **กลืน exit code** ด้วย `check=False, DEVNULL`). ใน `ci.yml` job `pytest` (ผ่าน `conftest.py`) รัน → จริง ๆ **CI GitHub job pytest แดงอยู่** (เทส exit 1). สำรวจพบ orphan รวม 11 ไฟล์ (ไม่อยู่ run_ci.sh) — รัน standalone แล้ว **3 ไฟล์ fail**: ตัวนี้ + `test_typing_leaf` (ADR-082) + `test_cmp004_notepad_visibility` (advisory conflict — ยกให้ Tor ตัดสิน, ดูรายงาน close-out).
**สิ่งที่ทำ (surgical):**
1. `test_rules_typo_branch.py`: แก้ assert "5นิ้ว → ไม่ฟ้อง (`==[]`)" ให้ตรง golden/ADR-075/recheck + เพิ่มเคส **positive จริง** `"ABCนิ้ว"` (อังกฤษ+ไทย — ไม่ใช่เลข) assert ฟ้อง เพื่อคงการเก็บกิ่ง emit ของ lookaround pattern (ไม่ลด coverage). อัป docstring ให้ตรงพฤติกรรมจริง.
2. `run_ci.sh`: เพิ่ม **9 orphan ที่ผ่าน** เป็น step ([3za]–[3zi]) → "ความจริงของ run_ci.sh == pytest job" กัน hidden-failure ซ้ำ (`test_rules_typo_branch`, `test_validators_branch`, `test_validators_missing_checks`, `test_addr_full_coverage`, `test_unit_detection_ext`, `test_fix_round2`, `test_fix_tnt_trio`, `test_report_consistency`, `test_report_summary_fixes`). `test_typing_leaf` ดึงเข้าใน ADR-082 (หลังแก้ annotation) · `test_cmp004` ยังไม่ดึง (รอ Tor).
**พิสูจน์ (golden-neutral):** ไม่แตะ engine/rule. `test_rules_typo_branch.py` → 7/7 ✅ · 9 orphan ที่ wire → ผ่านครบ · `check_invariants.py --fast` fixture `b5c415bb` ✅ · `bash -n run_ci.sh` syntax OK.
