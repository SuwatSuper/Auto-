# INVARIANTS / DECISIONS — สมุดบันทึกข้อตัดสินที่ "ล็อกแล้ว" (ปุ้มปุ้ย v9.x)

> เอกสารนี้คือ **แหล่งความจริงเดียว** ของ "อะไรห้ามขยับ และเพราะอะไร"
> ใครก็ตามที่จะแก้โค้ดในระบบนี้ ต้องอ่านหัวข้อ §1–§4 ก่อนเสมอ
> รูปแบบ = Architecture Decision Record (ADR) แบบ append-only — **ห้ามลบรายการเก่า**
> ถ้าข้อตัดสินเปลี่ยน ให้เพิ่ม ADR ใหม่ที่อ้าง superseded ของเดิม (เก็บประวัติไว้)

เครื่องมือที่บังคับใช้เอกสารนี้โดยอัตโนมัติ:
- `INVARIANTS/check_invariants.py` — tripwire (golden fixture + pin tests) รันได้ทุกที่ ไม่ต้องมีข้อมูลจริง
- `hooks/pre-commit` (ติดตั้งผ่าน `INVARIANTS/install_hooks.sh`) — บล็อก commit ถ้า invariant แตก
- `golden_master.py` / `verify_golden.py` / `regression_full.py` — golden เต็มบนข้อมูลจริง 106 ไฟล์ (`/mnt/project`)

> ⚡ **สถานะปัจจุบัน (ล่าสุด — ดู ADR-021 ท้ายไฟล์):** corpus ทางการ = **106 ไฟล์ `/mnt/project` (834 บิล)** · golden = **`d6b23d12…`** (= `baseline.json._sha256` = แหล่งความจริงเดียวของค่า hash) · สาย 81 ไฟล์ และ 106-เก่า **ปลดระวางแล้ว** (ค่า hash เดิมก่อน F2-cont อยู่ใน ADR-018/ADR-019/ADR-021 + เอกสารที่ลงวันที่) — เลข hash ในเอกสารอดีตคือ "หลักฐาน" เก็บไว้ ห้ามแก้

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
| **ข้อมูลจริง (ทางการ) — `/mnt/project`** | 106 | `d6b23d12…` (= `baseline.json._sha256`) | ผู้ใช้รันยืนยันบนเครื่องตน · engine==agent==baseline (834 บิล) · rebaseline ADR-021 |
| fixture (in-repo) | 1 ไฟล์ | `d8bcde8555034a203f80d2a596c42ea57b2f1a39ce67003f5629cea03185b07c` | ยืนยันใน CI/pre-commit (เร็ว ~3s, ไม่ต้องมีข้อมูลจริง) |

**กฎ:** การเปลี่ยน golden ของ "ข้อมูลจริง 106 ไฟล์ (`/mnt/project`)" ทำได้ก็ต่อเมื่อ **ผู้ใช้สั่งโดยตรง**
เท่านั้น และต้องบันทึก ADR ใหม่อธิบายเหตุผล + regen baseline ด้วย `golden_master.py`.

> คอร์ปัสทางการ = **106 ไฟล์ `/mnt/project`** (ชุด 81 ไฟล์เดิมปลดระวางแล้ว — ดู ADR-019).
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
  (2) **report-cell-hash** (รัน build_clean_report บน 106 ไฟล์ → hash ทุก cell ทุกชีต) old==new,
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
