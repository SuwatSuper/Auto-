# INVARIANTS / DECISIONS — สมุดบันทึกข้อตัดสินที่ "ล็อกแล้ว" (ปุ้มปุ้ย v9.x)

> เอกสารนี้คือ **แหล่งความจริงเดียว** ของ "อะไรห้ามขยับ และเพราะอะไร"
> ใครก็ตามที่จะแก้โค้ดในระบบนี้ ต้องอ่านหัวข้อ §1–§4 ก่อนเสมอ
> รูปแบบ = Architecture Decision Record (ADR) แบบ append-only — **ห้ามลบรายการเก่า**
> ถ้าข้อตัดสินเปลี่ยน ให้เพิ่ม ADR ใหม่ที่อ้าง superseded ของเดิม (เก็บประวัติไว้)

เครื่องมือที่บังคับใช้เอกสารนี้โดยอัตโนมัติ:
- `INVARIANTS/check_invariants.py` — tripwire (golden fixture + pin tests) รันได้ทุกที่ ไม่ต้องมีข้อมูลจริง
- `hooks/pre-commit` (ติดตั้งผ่าน `INVARIANTS/install_hooks.sh`) — บล็อก commit ถ้า invariant แตก
- `golden_master.py` / `verify_golden.py` / `regression_full.py` — golden เต็มบนข้อมูลจริง 81 ไฟล์

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
| **ข้อมูลจริง (ทางการ)** | 81 | `ec61907f…` | ผู้ใช้รันยืนยันบนเครื่องตน (ข้อมูลไม่อยู่ใน repo) |
| sandbox (`/mnt/project`) | 106 | `f1ac8421f23726ec00abe193968070827240cb2c381cae6cf854e2be307d209e` | ยืนยันใน sandbox (engine==agent, 836 บิล) |
| fixture (in-repo) | 1 ไฟล์ | `d8bcde8555034a203f80d2a596c42ea57b2f1a39ce67003f5629cea03185b07c` | ยืนยันใน CI/pre-commit (เร็ว ~3s, ไม่ต้องมีข้อมูลจริง) |

**กฎ:** การเปลี่ยน golden ของ "ข้อมูลจริง 81 ไฟล์" ทำได้ก็ต่อเมื่อ **ผู้ใช้สั่งโดยตรง**
เท่านั้น และต้องบันทึก ADR ใหม่อธิบายเหตุผล + regen baseline ด้วย `golden_master.py`.

> sandbox 106 ไฟล์ **ไม่ใช่** ตัวเลขทางการ — ใช้ยืนยัน "ชั้น agent/advisory ไม่ทำผลเพี้ยน"
> เท่านั้น. ตัวเลขทางการต้องรันบน 81 ไฟล์จริง.

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
