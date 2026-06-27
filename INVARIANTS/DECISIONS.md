# INVARIANTS / DECISIONS — สมุดบันทึกข้อตัดสินที่ "ล็อกแล้ว" (ปุ้มปุ้ย v9.x)

> เอกสารนี้คือ **แหล่งความจริงเดียว** ของ "อะไรห้ามขยับ และเพราะอะไร"
> ใครก็ตามที่จะแก้โค้ดในระบบนี้ ต้องอ่านหัวข้อ §1–§4 ก่อนเสมอ
> รูปแบบ = Architecture Decision Record (ADR) แบบ append-only — **ห้ามลบรายการเก่า**
> ถ้าข้อตัดสินเปลี่ยน ให้เพิ่ม ADR ใหม่ที่อ้าง superseded ของเดิม (เก็บประวัติไว้)

เครื่องมือที่บังคับใช้เอกสารนี้โดยอัตโนมัติ:
- `INVARIANTS/check_invariants.py` — tripwire (golden fixture + pin tests) รันได้ทุกที่ ไม่ต้องมีข้อมูลจริง
- `hooks/pre-commit` (ติดตั้งผ่าน `INVARIANTS/install_hooks.sh`) — บล็อก commit ถ้า invariant แตก
- `golden_master.py` / `verify_golden.py` / `regression_full.py` — golden เต็มบนข้อมูลจริง 148 ไฟล์ (`/mnt/project`)

> ⚡ **สถานะปัจจุบัน (ล่าสุด — ดู ADR-106 ท้ายไฟล์):** corpus ทางการ = **148 ไฟล์ `/mnt/project` (1056 บิล)** · golden = **`31013a31…`** (= `baseline.json._sha256` = แหล่งความจริงเดียวของค่า hash · rebaseline 2026-06-27 ADR-104/105/106 (P1 ตรวจหน่วยปนภาษาราย-ไฟล์ [report, neutral] + P2 ตัด ZWNJ/หัวคอลัมน์ 'Unit' หลุด + คำ "ช่องหน่วยว่างในต้นฉบับ" + P3 **ITM020** ทั้งบิลไม่มีหน่วย → ITM020 +52, ITM019 +9, ลบ 0) · ก่อนหน้า rebaseline 2026-06-26 ADR-102: ลบบริษัทตัวอย่าง ฉี อัน ออกจาก master ตามคำสั่งเจ้าของ → golden = **master ว่าง `{}`** = default จริงที่ ship (ผู้ใช้กรอกบริษัทเองรายเดือน), CMP006 −50 · golden เดิมปลดระวาง ดู GOLDEN.md/ledger) · สาย 81 ไฟล์ และ 106-เก่า **ปลดระวางแล้ว** (ค่า hash เดิมก่อน F2-cont อยู่ใน ADR-018/ADR-019/ADR-021 + เอกสารที่ลงวันที่) — เลข hash ในเอกสารอดีตคือ "หลักฐาน" เก็บไว้ ห้ามแก้

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
| **ข้อมูลจริง (ทางการ) — `/mnt/project`** | 148 | `31013a31…` (= `baseline.json._sha256`) | ผู้ใช้รันยืนยันบนเครื่องตน · engine==agent==baseline (1056 บิล) · rebaseline ADR-102 (ลบ master ฉี อัน → master ว่าง, CMP006 −50) / ADR-095 (สึตำ/เปือย/เหลือง-ตำ +4), FP=0 |
| fixture (in-repo) | 1 ไฟล์ | `72cb832c9b667e796b86a78ec5e1b0556c9f19b50d15d7756df1cbd0a58e1f0a` | ยืนยันใน CI/pre-commit (เร็ว ~3s, ไม่ต้องมีข้อมูลจริง) · [ADR-086: แก้ค้าง d8bcde85] |

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

### ADR-084 — REBASELINE: golden `08e6abfd` → `853ce4ab` (typo whitelist รายคำ: 'สวิตซ์' — Tor อนุมัติ)
**วันที่:** 2026-06-23 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor (อนุมัติรายคำ: "สวิตซ์→สวิตช์ ยกเว้น")
**บริบท:** ปิดงาน typo-whitelist per-word sign-off (รายการ deferred ที่ค้างมานาน). Tor ทบทวนหลักฐาน corpus จริงรายคำ แล้วตัดสิน:
- **'สวิตซ์' (ซ) → YKEW (whitelist เลิกฟ้อง)** — เป็นสะกดการค้าที่ยอมรับได้ (ไฟล์เดียวกันใช้ทั้ง สวิตซ์/สวิตช์). ← ตัวขับ rebaseline นี้
- **'ปี๊ป' → คงไว้ (ฟ้องต่อ)** ผ่าน ITM019 (8 occ) — ไม่เปลี่ยน golden (ฟ้องอยู่แล้ว). [reconcile: ลบคอมเมนต์ config_base.py ที่อ้างผิดว่า ปี๊ป ถูก whitelist]
- **'พุ๊ก' (2 occ) · 'เจียร์' (6 occ) → คงไว้ (typo จริง: พุก/เจียร)** — ทิศ keep, golden ไม่ขยับ.
- **'แกลอน' → คงไว้** (typo จริง: แกลลอน) — จับถูกแล้ว.

**ตัวขับ rebaseline (เปลี่ยนผล corpus จริง):** เพิ่ม `'สวิตซ์','สวิตซ์ทางเดียว','สวิตซ์สองทาง','สวิตซ์สามทาง'` เข้า `CONSTRUCTION_DICT` (config_base.py) → fuzzy matcher เห็นเป็นคำรู้จัก → เลิกฟ้อง **ITM011** "สวิตซ์ทางเดียว ~92% สวิตช์ทางเดียว".

**สิ่งที่ทำ:**
1. `baseline.json` regenerate → `_sha256 = 853ce4ab9214…` (148/1056).
2. เพิ่ม `08e6abfd` เข้า `RETIRED_PREFIXES`.
3. อัป OPERATIONAL_SURFACES (tasks/launch.json, _SESSION_HANDOFF, QUICKSTART, Makefile, ci.yml, MAINTENANCE, DECISIONS banner+§1) `08e6abfd`→`853ce4ab`. ledger ประวัติคง `08e6abfd` ไว้.
4. `GOLDEN.md`: `853ce4ab` = ✅ ปัจจุบัน · `08e6abfd` → ⏮️ ปลดระวาง.
5. **fixture `b5c415bb` ไม่ขยับ** (3 บิล fixture ไม่มี สวิตซ์) → ไม่ rebaseline fixture.

**พิสูจน์ (เครื่อง corpus จริง 148/1056 + Python 3.12.3 + wheelhouse --require-hashes):**
- `regression_full.py . /mnt/project baseline.json` → engine==agent==baseline = **`853ce4ab`** ✅
- **DELTA เทียบ 08e6abfd: ลบเป๊ะ −3** (3× ITM011 "สวิตซ์ทางเดียว") · **เพิ่ม 0** (ไม่มี item อื่น fuzzy ชน สวิตซ์) · typos array 51→51 ไม่ขยับ.
- `check_invariants.py` → fixture `b5c415bb` ✅ · `test_golden_single_source.py` → PASS ✅
**ขอบเขต/หมายเหตุ:** flag เว้นวรรค "BLสวิตซ์" (**ITM004**, 2 occ) **คงไว้** — เป็นคนละเรื่อง (เว้นวรรค ไม่ใช่สะกด ซ/ช) Tor สั่งเฉพาะสะกด. การ suppress นี้เป็น INFO/advisory tier ไม่มี must-fix หาย. ย้อนได้ด้วย revert + rebaseline กลับ (08e6abfd ใน RETIRED).
**หมายเหตุ ledger gap (079→084):** ADR-080..083 = งาน golden-neutral ของ Claude Code (doc-sync/CI-integrity/type-annotation/delivery-doc) บน branch `claude/sharp-keller-gvv605` — ยังไม่ merge เข้าทรีนี้. เป็น golden-neutral (hash คง `853ce4ab` หลัง merge). เมื่อ merge แล้ว ledger จะต่อเนื่อง 080..084.

---

### ADR-085 — ACCEPTED SCOPE (known limitation): ITM005 paint-unit false-positive จาก substring 'สี' — เลื่อนแก้แบบ deliberate
**วันที่:** 2026-06-23 · **สถานะ:** ACCEPTED (known limitation, ยังไม่แก้) · **สั่งโดย:** Tor (Plan A: "ปิดเลย, ITM005 เป็น known limitation")
**Current risk:** ITM005 (289 occ = 45% ของ issue ทั้งระบบ) ฟ้องเกิน — ~96 occ ผูก expected-unit `[แกลลอน,กระป๋อง]` แล้วเหมาสินค้าไม่ใช่สี (สวิตช์/เต้ารับ/ตู้คอนซูเมอร์/กระเบื้อง/เกรียง) ว่า "หน่วยควรเป็นแกลลอน" → noise/alert-fatigue (แต่เป็น INFO/soft tier ไม่ assert ว่าผิด).
**Root cause:** `_kw_in_name()` (rules_engine_base.py:123) กัน "สี่"(สี+วรรณยุกต์) และ "สี" กลางคำได้ แต่ปล่อย **"สีดำ/สีขาว/สีเรียบ"** ที่เป็นคำขึ้นต้นหลังช่องว่าง → จับเป็นสินค้าหมวด 'สี' (config_base.py:188) → คาดหน่วยสีทาบ้าน.
**Long-term impact:** 5 ปี noise ฝึกผู้ใช้มองข้าม ITM005 → เสี่ยง false-negative ผ่าน fatigue.
**Recommended solution (รอบ deliberate แยก):** เพิ่ม color-word exclusion ใน `_kw_in_name` (กัน สี+{ดำ,ขาว,แดง,เขียว,ฟ้า,เหลือง,น้ำเงิน,น้ำตาล,เทา,ส้ม,ม่วง,ชมพู,ทอง,เงิน,ครีม,เรียบ,...} แต่ **ไม่กัน** สีน้ำ/สีน้ำมัน/สีรองพื้น). สีจริงยัง match ผ่านคำ paint-type → recall คงเดิม.
**Migration risk:** ปานกลาง-สูง — `_kw_in_name` ใช้ร่วม rules_a/b/c (blast radius กว้าง) + เคส Thai สี (น้ำเงิน/น้ำตาล กัน แต่ น้ำ ไม่กัน) ต้องระวัง false-negative.
**Priority:** P2 (คุณภาพ ไม่ใช่ stability).
**เหตุที่เลื่อน:** Stability-first + minimize-regression → ไม่รีบยัด heuristic แก้ก่อนล็อก 5 ปี บน tier ที่เบาสุด. บันทึกเป็น accepted-scope (เหมือน `master_companies.json` ที่ไม่มีจริง) ให้ทำเป็นรอบ focused + regression เต็มทีหลัง.


---

### ADR-086 — HARDENING (golden-neutral): ปิด root cause ของ doc-drift ถาวร + safety-net การตัดสิน typo
**วันที่:** 2026-06-23 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("พัฒนา... ไม่โกหก... ส่งระบบสมบูรณ์")
**บริบท:** จาก audit (คะแนน Maintainability 6.5 / Consistency 7.0) — เจอ root cause จริง 2 อย่าง:
1. **doc-drift หลุดมา 2 ครั้ง** เพราะ `OPERATIONAL_SURFACES` ครอบไม่ครบ: `CLAUDE.md` (เคยค้าง ae84d3f0 — cold-start contract สำคัญสุด แต่ไม่ถูกเฝ้า) และ `run_ci.sh` (comment เคยค้าง ba9deda0). อีกจุด: fixture hash ใน DECISIONS §1 table ค้าง `d8bcde85` (current จริง = `b5c415bb`).
2. **การตัดสิน typo กระจาย หลายที่ ขัดกันเองได้** (ปี๊ป-class: คอมเมนต์ whitelist แต่กฎอื่นฟ้อง).
**สิ่งที่ทำ (golden-neutral — แตะเฉพาะ test/doc/config ไม่แตะ engine/baseline):**
- เพิ่ม `CLAUDE.md` + `run_ci.sh` เข้า `OPERATIONAL_SURFACES` (test_golden_single_source.py) → ถ้า re-baseline แล้วลืมอัป 2 ไฟล์นี้ = gate แดงทันที (ปิดช่อง drift ถาวร).
- แก้ DECISIONS §1 fixture row `d8bcde85` → `b5c415bb` (current). [ตำแหน่งประวัติ ADR อื่นที่อ้าง d8bcde85 คงไว้ ตาม append-only].
- เพิ่ม `test_typo_decisions_lock.py` + wire เข้า run_ci.sh ([3x-typo]): ตรึง (A) การตัดสินรายคำ ADR-084 [สวิตซ์ whitelist · พุ๊ก/เจียร์/มั้วน/แกนลอน คงไว้], (B) consistency dict↔pattern (กัน ปี๊ป-class), (C) characterization `_kw_in_name` (root cause ITM005 — เป็น safety net: ถ้าแก้ ITM005 ในอนาคต ค่าจะเปลี่ยน → ผู้แก้เห็น before/after ชัด + ต้องอัปเทสพร้อม ADR).
**พิสูจน์:** `regression_full . /mnt/project` → golden **`853ce4ab` ไม่ขยับ** (golden-neutral ยืนยัน) · doc-sync เขียว (รวม surface ใหม่) · test_typo_decisions_lock PASS · run_ci.sh เขียวครบ.
**ผลต่อคุณภาพ:** Consistency: drift ปิดถาวร + การตัดสินถูกตรึงเป็นเทส · Maintainability: surface coverage ครบขึ้น + มี safety net ก่อนแตะ guard ร่วม (`_kw_in_name`) ทำให้รอบแก้ ITM005 (ADR-085) ในอนาคตปลอดภัยขึ้น.
**หมายเหตุ:** ไม่ได้แก้ F1(ITM005, golden-affecting) / F3-full(registry refactor) / F5(decoupling) ในนี้ — เป็นงาน risk-bearing ที่ขัด "Stability-first + no-rewrite" ก่อนล็อก 5 ปี → ทำเป็นรอบ deliberate แยกถ้า Tor อนุมัติเฉพาะตัว.

---

### ADR-087 — REBASELINE: golden `853ce4ab` → `587db268` (F1 SNIPER: ITM005 'สี'+คำบอกสีล้วน exclusion — Tor อนุมัติ)
**วันที่:** 2026-06-23 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor (อนุมัติ: "apply + rebaseline" ขอบเขตตามที่พิสูจน์พอดี) · **superseded:** ADR-085 (known-limitation → แก้แล้ว)
**บริบท:** ADR-085 บันทึก ITM005 paint-unit false-positive เป็น accepted known-limitation (เลื่อนแก้). รอบนี้ทำ F1 แบบ deliberate + พิสูจน์ระดับเซลล์ครบ → Tor อนุมัติให้ apply.

**ปัญหา (เดิม):** ITM005 (289 occ = 45% ของ issue ทั้งระบบ) ฟ้องเกิน. `_kw_in_name('สี', name)` (rules_engine_base.py) จับ 'สี' ที่ขึ้นต้นคำ แล้วถือเป็นสินค้าหมวด "สีทาบ้าน" → คาดหน่วย `[แกลลอน,กระป๋อง,ลิตร]`. แต่ **สินค้าไม่ใช่สี** จำนวนมากมีคำบอกสีต่อท้าย (สวิตช์ **สีดำ**, สายไฟ THW **สีน้ำตาล**, กระเบื้อง **สีเรียบ**, ซิลิโคน **สีขาว**) → ฟ้องว่า "หน่วยควรเป็นแกลลอน" = ไร้เหตุผล = alert fatigue.

**Root cause:** `_kw_in_name` กัน 'สี่'(สี+วรรณยุกต์) และ 'สี' กลางคำได้ แต่ปล่อย 'สีดำ/สีขาว/สีเรียบ' ที่ขึ้นต้นหลังช่องว่าง → นับเป็นหมวดสี.

**ทางแก้ (surgical, scoped):** เพิ่ม `_SI_COLOR_ADJ` (config.py) = คำบอกสีล้วน/ผิว (ขาว,ดำ,แดง,เขียว,ฟ้า,เหลือง,น้ำเงิน,น้ำตาล,เทา,ส้ม,ม่วง,ชมพู,ทอง,เงิน,ครีม,เรียบ,อ่อน,เข้ม,ใส,บรอนซ์,เนื้อ,รุ้ง,ธรรมชาติ,อะลูมิเนียม,อลูมิเนียม,ไอวอรี่,เบจ). ใน `_kw_in_name` เมื่อ `kw=='สี'` ขึ้นต้นคำ + ข้อความถัดไป startswith คำใน `_SI_COLOR_ADJ` → ข้าม match นี้ (เป็น "คำขยายบอกสี" ไม่ใช่สินค้าสี). **จงใจไม่ใส่ token 'น้ำ'** → 'สีน้ำ'/'สีน้ำมัน' (สีจริง) ยัง match; ใช้ 'น้ำเงิน'/'น้ำตาล' (ยาวกว่า) แทน. ไม่มี token ใดเป็น prefix ของคำ paint-type (สีรองพื้น/สีย้อม/สีอะคริลิค/สีกันสนิม/สีสเปรย์/สีโป๊ว) → **สีจริงไม่หลุด**.

**Blast radius:** call site เดียวจริง = `rules_engine_rules_b.py:163` (r_itm005). references ใน rules_a/c เป็น re-export shim (ไม่เรียก). → กระทบเฉพาะ ITM005.

**DELTA (พิสูจน์จริง: simulate ในสำเนาแยก → regen baseline → diff ระดับเซลล์ บน corpus 148/1056):**
- golden: `853ce4ab` → **`587db268`**
- **ITM005: 289 → 225 (−64 net)** · flag หาย 72, ใน 8 ตัวถูก re-flag ด้วยหน่วยที่ถูกต้องขึ้น (ตู้คอนซูเมอร์→`[ตู้,ใบ]`, เต้ารับ→`[ตัว,ชุด]`, ท่อหด→`[เส้น,ท่อน]`) แทน "แกลลอน"
- **กฎอื่นนอก ITM005 เปลี่ยน = 0** (collateral ศูนย์) · typos 51→51 · n_bills 1056 · fixture `b5c415bb` ไม่ขยับ (3 บิล fixture ไม่มี 'สี')

**พิสูจน์ FP ทุกตัว (cell-level, 64 net ที่หาย):** ทั้งหมดเป็นสินค้า **ไม่ใช่สี** + คำบอกสี → สายไฟ YAZAKI THW (~30: ขด/ม้วน/เมตร), ท่อ/ท่ออ่อน/HDPE/PVC/EMT, ราง/รางวายเวย์/รางเดินสายไฟ, กระเบื้องเคลือบ "สีเรียบ"(×6), กาว/ซิลิโคน/ยาแนว "สีขาว/เทา/ใส", สวิตช์/เต้ารับ/ข้อต่อ MC4, เกรียงโบกปูน, ถุงมือ "สีน้ำตาล", grille 4-ASD, ผงวุ้น(อาหาร). เดิมทุกตัวถูกบอก "หน่วยควรเป็นแกลลอน" → FP ชัดเจน.
**พิสูจน์ recall ไม่ตก (0):** สีจริงทุกตัวใน corpus ยัง match ครบ — `สีอะคริลิค`, `สีสเปรย์ TOA`, `สีรองพื้น (TOA/ออลคอนกรีต/กันสนิม)`, `สีน้ำมัน TOA`, `สีผสมอาหาร` — **ไม่มี flag ของ error/สีจริงตัวใดหาย**.

**สิ่งที่ทำ (rebaseline ครบ surface):**
1. โค้ด: `config.py` (+`_SI_COLOR_ADJ`) · `rules_engine_base.py` (`_kw_in_name` + import).
2. `baseline.json` regenerate → `587db268` (engine==agent==baseline ✅).
3. `test_typo_decisions_lock.py` [C]: flip characterization 'สวิตช์...สีดำ' True→**False** [ADR-087 FIXED] + เพิ่ม recall-lock (สีน้ำ/สีน้ำมัน/สีรองพื้น/สีอะคริลิค → True) + FP-lock (สายไฟ/กระเบื้อง/สีน้ำเงิน → False).
4. `RETIRED_PREFIXES` (test_golden_single_source.py): + `853ce4ab`.
5. OPERATIONAL_SURFACES `853ce4ab`→`587db268`: tasks/launch.json, _SESSION_HANDOFF, QUICKSTART, Makefile, ci.yml, MAINTENANCE, CLAUDE.md, run_ci.sh, DECISIONS banner+§1. `GOLDEN.md`: `587db268`=✅ปัจจุบัน · `853ce4ab`→⏮️ปลดระวาง. ledger ประวัติ (ADR-084 ฯลฯ) คง `853ce4ab` ไว้ตาม append-only.
**พิสูจน์ gate:** regression_full (engine==agent==baseline=`587db268`) ✅ · check_invariants (fixture `b5c415bb`) ✅ · test_golden_single_source (doc-sync `587db268`) ✅ · test_typo_decisions_lock ✅ · run_ci.sh exit 0 ✅.
**ขอบเขต/หมายเหตุ:** ตั้งใจ "ไม่" แตะ FP กำกวมที่ไม่ใช่ 'สี'+สีล้วน (สีผสมอาหาร/สีเปรย์หล่อลื่น) — เสี่ยง recall, อยู่นอกขอบเขตที่อนุมัติ. ย้อนได้ด้วย revert + rebaseline กลับ (`853ce4ab` ใน RETIRED + git history initial import).

---

### ADR-088 — HARDENING (golden-neutral): forward-compat tripwire กัน "ระบบล้าหลังเงียบ" (FC-1)
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ทำให้ระบบดีที่สุดสำหรับล็อก 5 ปี... ไม่ให้เกิดปัญหาเรื่องระบบล้าหลัง... ส่งระบบสมบูรณ์")
**บริบท:** จาก forward-compat audit ก่อนล็อก 5 ปี. เป้าของ Tor คือ "ตอนกลับมาแก้ในปีที่ 4-5 ต้องไม่เจอปัญหาระบบล้าหลัง". scan พบว่า core paths (`pukpui_modular_base.py:168`, `golden_master.py:16`, `verify_golden.py:19` + tools อีก 9) เรียก `warnings.filterwarnings('ignore')` แบบ **global** เพื่อกลบ noise ตอนอ่าน `.xls`.
**ปัญหา/Root cause:** filter เหมารวม **ทุก** category รวม `DeprecationWarning`/`FutureWarning`. ในโหมด freeze (รัน artifact ปิดผนึกเฉย ๆ) ไม่กระทบ. แต่ scenario ที่ Tor ระบุเอง — **bump pandas/numpy/Python ตอนกลับมาแก้** — deprecation จะถูกกลืน **เงียบ** → ระบบทำงานต่อจนวันที่ API ที่ deprecated ถูก **ถอดจริง** แล้วพังกะทันหันโดยไม่มีสัญญาณเตือนล่วงหน้า = อาการ "ระบบล้าหลังสร้างปัญหา" ตรงเป๊ะ.
**สถานะจริงตอนนี้ (พิสูจน์ก่อนทำ):** ปลดการกลบ warning แล้ว parse ไฟล์จริง 44 ไฟล์ + fixtures → **0 Deprecation/Future ทุก category, 0 จากโค้ดเรา** = สะอาดแท้ (filter เดิมไม่ได้ปิดบังหนี้ที่มีอยู่). FC-1 จึงเป็น **มาตรการป้องกันล้วน** ไม่ใช่แก้ของเสีย.
**สิ่งที่ทำ (golden-neutral — test ล้วน, ไม่แตะ production/engine/baseline):**
- เพิ่ม `test_forward_compat.py`: import app → `warnings.resetwarnings()` (ปลดการกลบของ core) → parse จริงด้วย `catch_warnings(record=True)` บน **2 read path**: `tests/fixtures/*.xlsx` (openpyxl) + `tests/real_cases/*.xls` (xlrd). **fail** เฉพาะ Deprecation/Future ที่ต้นทางอยู่ในซอร์ส **ของเรา** (actionable — เราแก้ที่ call-site ได้); third-party (ใน deps) แค่ **รายงาน** ไม่ทำ CI ตก (deps freeze + เราแก้โค้ดเขาไม่ได้).
- wire เข้า `run_ci.sh` ([3x-fc], ต่อจาก [3x-itm005]). `ci.yml` มี loop `for t in test_*.py` → auto-discover เอง.
- **production code ไม่แตะเลย** → console ผู้ใช้เหมือนเดิม (noisy xls warning ยังถูกกลบเพื่อ UX) → การคำนวณไม่เปลี่ยน.
**ทำไมเลือกแนวนี้ (ไม่ narrow production filter):** CI-tripwire = surgical สุด, zero production change, golden แน่นอนไม่ขยับ, แต่ได้สัญญาณครบ — วันที่ใคร bump dep แล้ว idiom เราตกยุค → CI **แดงทันที** ก่อนของถูกถอดจริง. (narrow filter ใน production = แตะ monolith + เสี่ยง console regression โดยไม่จำเป็น).
**พิสูจน์:**
- `regression_full . corpus` → golden **`587db268` ไม่ขยับ** (golden-neutral ยืนยัน) · check_invariants fixture `b5c415bb` ✅
- tripwire: รันโค้ดจริง → **PASS clean**; inject DeprecationWarning จากต้นทาง \"ของเรา\" → **FAIL ถูกต้อง** (ไม่ใช่ gate หลอก)
- `run_ci.sh` → 89 pass / 0 fail (เพิ่ม [3x-fc] จาก 88)
**ผลต่อคุณภาพ:** Maintainability + Reliability + forward-compat — สถานะสะอาดถูก **ตรึงเป็นเทส**: dep/Python bump ในอนาคตที่ทำให้ idiom เราตกยุคจะถูกจับก่อนพัง. คนแก้ปีที่ 5 ได้ CI-red เป็นสัญญาณนำทาง แทนที่จะเจอ \"พังเงียบ\".
**ขอบเขต/หมายเหตุ:** ไม่ปั้นคะแนน (ตามสัญญาเหล็ก) — เป็น forward-compat win แท้มีหลักฐาน. ไม่ทำ refactor เสี่ยง stability ก่อนล็อก (คง Stability-first priority #1). ย้อนได้ด้วยลบ test + บรรทัด run_ci.sh (ไม่กระทบอะไรเพราะ production ไม่เคยถูกแตะ).

---

### ADR-089 — HARDENING (golden-neutral): QA gate reproducibility (coverage measurement + tool pinning)
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ทำให้ดีที่สุดสำหรับล็อก 5 ปี... ทั้งหมด")
**บริบท:** รัน 5 QA gate (PUOPUY_CI_STRICT=1) ที่ก่อนนี้ sandbox skip. **เจอของจริง 2 อย่าง:**
1. **coverage gate ตก** — `rules_engine` (family) branch = **84.5% < 85%** (เกณฑ์) บน coverage 7.14.3. *ไม่ใช่ code regression* (golden 587db268 ถูก, functional test ผ่านครบ) — **root cause:** `coverage_gate.py` TESTS list ไม่รวม `test_itm005_precision.py` / `test_typo_decisions_lock.py` (เทส ADR-084/087 ที่เพิ่มมาทีหลัง) → branch ของ `_kw_in_name` color-exclusion (line 142/144) + r_itm005 ที่เทสพวกนั้น exercise จริงไม่ถูกนับ.
2. **QA tools unpinned** — `requirements-dev.txt` ระบุ coverage/ruff/black/mypy/pip-audit แบบ **ไม่มี version** → gate pass/fail ขยับตาม tool version (เช่น coverage version ใหม่นับ branch ต่าง 0.6%) = ไม่ reproducible ข้าม 5 ปี.
**สิ่งที่ทำ (golden-neutral — แตะเฉพาะ QA tooling/dep-list, ไม่แตะ engine/baseline):**
- `coverage_gate.py`: เพิ่ม `test_itm005_precision.py` + `test_typo_decisions_lock.py` เข้า TESTS (เทสจริงที่มีอยู่แล้ว exercise branch พวกนั้น — **ไม่ใช่เทสปั้นเพื่อคะแนน**, แค่ coverage_gate ไม่ได้รวมตอนวัด). ผล: rules_engine branch **84.5% → 85.3%** ✅ · TOTAL line 94.0% / branch 86.4%.
- `requirements-dev.txt`: pin ทั้ง 5 (`coverage==7.14.3, ruff==0.15.19, black==26.5.1, mypy==2.1.0, pip-audit==2.10.1`) = version ที่ทุก gate ผ่านจริง (verify 2026-06-24). bump = deliberate + re-verify.
**พิสูจน์:**
- coverage gate ✅ (ทุกกลุ่ม line≥90 + branch≥85) · ruff/black/mypy ✅ บน scope (tool version ใหม่กว่า dev ยังผ่าน = forward-compat signal) · pip-audit **0 CVE** บน deps ที่ pin
- `regression_full . corpus` → golden **`587db268` ไม่ขยับ** (golden-neutral ยืนยัน)
- STRICT CI: 93+ pass / 0 fail / **0 skip** (QA gate บังคับครบ)
**ผลต่อคุณภาพ:** Consistency + Maintainability — QA gate กลายเป็น reproducible (เหมือน runtime deps): คนแก้ปีที่ 5 รัน gate ได้ผลเดิม ไม่เจอ "เขียว/แดงสุ่มตาม tool version".
**หมายเหตุ — F4 (observability except-pass) audit ในรอบนี้:** ตรวจ 22 swallow site + 0 bare except. broad `except Exception: pass` ที่สุ่มดู (parser reset/master-stub fallback/json→regex fallback/date-guard/advisory chart) = **fallback ตั้งใจทั้งหมด ไม่ใช่กลืน bug** + rule crash จริงมี SYS001-004 + end-of-run summary อยู่แล้ว. **สรุป: F4 ไม่คุ้มทำ** (instrument = noise ไม่มี signal) → คงการเลื่อนเดิม (ADR-085/F1 doc) ตาม Stability-first.

---

### ADR-090 — DECISION (per-word typo, golden-neutral): Cat B "คงไว้ทั้งหมด" (Tor 2026-06-24)
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED · **สั่งโดย:** Tor (ชี้ขาด "1 คงไว้")
**บริบท:** รอบ verify ก่อนล็อก 5 ปี เสนอ typo Cat B (variant กำกวม) 3 คำให้ Tor ชี้ขาดรายคำ. Tor ตัดสิน **"คงไว้ทั้งหมด"** (flag ให้คนดู ไม่ auto-suppress) = ทางเลือก audit-safe (false-negative อันตรายกว่า false-positive).
**การตัดสิน (per-word):**
- `พุ๊ก` → **คงไว้** (re-confirm ADR-084 — ฟ้องต่อผ่าน typo-pattern)
- `เจียร์` → **คงไว้** (re-confirm ADR-084 — ฟ้องต่อผ่าน typo-pattern)
- `อิฐบล็อค` → **คงไว้ (ใหม่)** — ฟ้องผ่าน ITM011 fuzzy (~87% ใกล้ 'อิฐบล็อก'); ไม่ใส่เข้า CONSTRUCTION_DICT
**ผลต่อ golden:** **`587db268` ไม่ขยับ** — "คงไว้" = พฤติกรรมปัจจุบัน = ไม่มี code change = ไม่ rebaseline.
**สิ่งที่ทำ (golden-neutral — lock เพื่อกันการ re-litigate/เผลอ suppress ในอนาคต):**
- `test_typo_decisions_lock.py` [A]: เพิ่ม assert `'อิฐบล็อค' not in CONSTRUCTION_DICT` (ถ้าใครเผลอ whitelist = fuzzy เลิกฟ้อง → lock แดง). พุ๊ก/เจียร์ ถูกล็อกอยู่แล้ว (ADR-084).
**พิสูจน์:** regression_full → golden `587db268` ไม่ขยับ · test_typo_decisions_lock ✅ · run_ci เขียว.
**สรุป accuracy:** ปิดบัญชี — typo decision ทุกคำที่ค้างถูกชี้ขาดแล้ว (Cat A typo จริงคงไว้ · Cat B variant คงไว้ตาม Tor · สวิตซ์ whitelist/ปี๊ป คงไว้ ADR-084). ไม่มีรายการ accuracy ค้างอีก.

---

### ADR-091 — FIX (report-layer, golden-neutral): "หน่วยปนไทย+อังกฤษ" flag เฉพาะหน่วยเดียวกัน 2 สคริปต์
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("เปิดไฟล์ดูแล้ว มีแค่รายการสินค้าที่เป็นภาษาอังกฤษ ... ต้องตรวจและแก้ไข")
**อาการ:** หมายเหตุบริษัท "หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษครับ" ขึ้นกับ 5 บริษัท แต่เจ้าของเปิดไฟล์จริงพบว่า **ที่เป็นอังกฤษคือ "ชื่อสินค้า" ไม่ใช่ "หน่วย"** → mischaracterize.
**Root cause (forensic, cell-level):** `company_unit_notes` (unit_detection_ext.py) flag เมื่อ "หน่วยสคริปต์ไทยใดๆ + หน่วยสคริปต์อังกฤษใดๆ" อยู่ด้วยกัน — แต่ comment เจตนาเดิม (notepad_report:264) บอกชัดว่าควรเตือนเฉพาะ **"ความหมายเดียวกัน เช่น กก./kg, ตรม./sqm"**. implementation drift → FP เมื่อบริษัทใช้ 'PCS'(=ชิ้น) เป็นหน่วยคู่กับ 'เมตร'(=ยาว) ซึ่ง **คนละหน่วย ไม่ใช่ inconsistency**. หลักฐาน: script_of/parser ถูกต้องหมด — 'PCS'/'SET'/'EA' เป็นหน่วยจริงที่ vendor พิมพ์ (Thai name + English unit) ไม่ใช่ misread.
**เช็กรายบริษัท (corpus):** ฉี อัน = เมตร+**m** (หน่วยเดียวกัน) = inconsistency จริง ✓ · สปาย/ไทยยูคิง/ไอน์ชไตน์/**ไคโอ** = PCS/SET/EA (ชิ้น/ชุด, ไม่มีคู่ไทย) = **FP**.
**สิ่งที่ทำ (report layer — ไม่ถูกเรียกโดย rule engine = golden-neutral):**
- เพิ่ม `_unit_family_key(u)` (ใช้ `_SPELL_TO_FAMILY` ที่มีอยู่) → map หน่วย→family-key อิสระจากสคริปต์ (เมตร/m→'เมตร', PCS/ชิ้น→'ชิ้น', ท่อน/อัน→None).
- `company_unit_notes`: เปลี่ยนเงื่อนไขจาก `if th and en` → `if th_fams & en_fams` (family เดียวกันปรากฏทั้ง 2 สคริปต์). บล็อกหน่วยขาด/ว่างคงเดิม แยกจากปนภาษา.
**ผล:** language-mix flag **5 → 1 บริษัท** (เหลือเฉพาะ เมตร/m จริง). ตัด FP 4 บริษัทที่เจ้าของเจอ.
**พิสูจน์:** `regression_full . corpus` → golden **`587db268` ไม่ขยับ** (golden-neutral ✓) · test_super_ultra_viewer ✅ · test_vendor_report ✅ · เพิ่ม `test_unit_lang_note.py` (ล็อก: เมตร/m→flag · PCS+เมตร→ไม่ flag · blank-only→ไม่ติดป้ายปนภาษา) wired `[4b2]` ใน run_ci.sh.

---

### ADR-092 — REBASELINE (golden-affecting): เพิ่ม typo ชื่อสินค้าที่ fuzzy เดิมพลาด · `587db268` → `5f23e9f4`
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("คำผิดในรายการสินค้า ฟัสซี่ไม่เจอ นายต้องเพิ่ม")
**บริบท:** Tor แจ้งว่ามีคำสะกดผิดในชื่อสินค้าที่ ITM004/010/011 (fuzzy + pattern) เดิมจับไม่ได้ ให้ค้นจาก corpus จริงแล้วเพิ่ม detection.

**วิธีค้น (forensic 3 ชั้น + visual):**
1. freq-anchored fuzzy (token หายาก ใกล้ token ใช้บ่อย) → เจอเฉพาะที่ caught แล้ว (แกนลอน/หล็กฉาก) + FP (เหลือง/น้ำตาล = สี-prefix).
2. curated-correct fuzzy (เทียบศัพท์ช่างที่สะกดถูกจากความรู้ AI) → ส่วนใหญ่ FP (คำประสมถูก: เหล็กแผ่นดำ/สีอะคริลิค/ฝาพลาสติก) + transliteration variant.
3. curated wrong→right substring → แยก false-substring-match ออก (ซีเมน⊂ซีเมนต์, ทินเนอ⊂ทินเนอร์, สเปร⊂สเปรย์ = ข้อความจริง**ถูก**).
4. อ่านชื่อ unique ทั้ง 1,229 รายการ ทุกหมวด (เหล็ก/ปูน/ท่อ/กระเบื้อง/สี/fitting/fastener/สแตนเลส/ทองเหลือง/เชื่อม/ฉนวน/สังกะสี/ยิปซัม/ไฟฟ้า/ไม้) + tone-mark anomaly scan.

**ข้อค้นพบ (ซื่อสัตย์):** corpus สะกดถูกเป็นส่วนใหญ่ — typo ที่พลาดจริง **น้อย** (ที่ดูเยอะเพราะตัวเดิมซ้ำหลายบิล: แกลอน×16 มั้วน×12). คำผิดใหม่ที่ยืนยันระดับเซลล์ **3 ตัว FP=0**:
| pattern | wrong → right | คลาส | หลักฐาน |
|---|---|---|---|
| `วาวล์` | วาวล์ → วาล์ว | ว/ล สลับที่ (เหมือน ฟิมล์→ฟิล์ม เดิม) | บอลวาวล์ ×2 STC_69_059 — corpus มี วาล์ว ถูกอยู่ (EKS_69_0516) พิสูจน์เป็น typo |
| `แป็ป` | แป็ป → แป๊บ | tone ็ ที่ pattern แป๊ป(๊) เดิมไม่ครอบ | เหล็กแป็ปกลมดำ ×2 EKS_69_05/STC_69_05 |
| `ครีลิ` | อะครีลิค/อะครีลิก → อะคริลิค | ครี(ี ยาว)→คริ(ิ สั้น) | สีน้ำอะครีลิค/ก ×5 SHS_69_056/TKH_69_05_2/TSH_69_054 — pattern แม่น ไม่โดน อะคริลิก(คริ)/อะคริลิค ที่ถูก |

**Borderline (เสนอ Tor per-word — ยังไม่เพิ่ม):** `ยิปซั่ม → ยิปซัม` (×6 KTV_69_05 — ทั้งคู่ใช้ทั่วไปในวงการ board) · `อะคริลิก` (ลงท้าย ก) = variant ใช้ได้ ไม่ flag.

**สิ่งที่ทำ:**
- `config_base.py` THAI_TYPO_PATTERNS: เพิ่ม 3 pattern (block ADR-092 หลัง เหล็กแป๊ป).
- dry-run: ยิงตรง 9 รายการ (วาวล์×2 แป็ป×2 ครีลิ×5) ทั้งหมด typo จริง FP=0 (วาล์ว/อะคริลิก/แป๊ป ไม่โดน).

**Delta golden:** all_bills 9 บิลได้ ITM010 typo issue เพิ่ม (0→1 ต่อบิล) · summary ปรับตาม · section อื่น (dup/iv_seq/iv_date/filename_issues/typos top-level) **identical**. fixture ไม่กระทบ (fixture_invoices.xlsx ไม่มีคำ typo ใหม่ → `b5c415bb` คงเดิม).

**Rebaseline discipline:** backup baseline.json (`INVARIANTS/baseline_backups/baseline_587db268_pre_ADR092_20260624.json`) → golden_master.py regen → `5f23e9f4` → update OPERATIONAL_SURFACES (DECISIONS banner/table · GOLDEN.md · CLAUDE/MAINTENANCE/cert/handoff/quickstart/vscode) → เพิ่ม `587db268` เข้า RETIRED_PREFIXES → ADR นี้ → full CI → make_release build→extract→verify → fresh-extraction.

**golden ใหม่:** `5f23e9f43f344868f2882389ac2a3fa441d259bc704fafc4e9b78fa4bcaee666`

---

### ADR-093 — DECISION (per-word typo, golden-neutral): `ยิปซั่ม` คงไว้ (industry-canonical) — ไม่ rebaseline
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED · **สั่งโดย:** Tor ("ไม่ต้องถามเรื่องคำผิด ไปค้นกูเกิลว่าผิดมั้ย แล้วทำทุกอย่าง") — มอบอำนาจตัดสินให้ Claude โดยให้ค้นเว็บยืนยัน
**บริบท:** คำ borderline `ยิปซั่ม` (เสนอใน ADR-092) ค้นเว็บยืนยันแล้วตัดสิน.
**หลักฐานค้นเว็บ:** ราชบัณฑิตยสภา (พจนานุกรม พ.ศ.๒๕๕๔ + ศัพท์บัญญัติ) + กรมทรัพยากรธรณี + สสวท. = รูปทางการ **`ยิปซัม`** (ไม่มีไม้เอก). `ยิปซั่ม` ไม่ตรงพจนานุกรม.
**แต่ — เหตุผลที่ "คงไว้" (ไม่ flag):**
1. **ระบบ adopt `ยิปซั่ม` เป็น canonical อยู่แล้ว** (การตัดสินเดิมที่ coherent): `CONSTRUCTION_DICT` มี `ยิปซั่ม/แผ่นยิปซั่ม/คอมพาวด์ยิปซั่ม` (config_base.py:431) + มี typo-pattern `ยิบซั่ม → ยิปซั่ม` (config_base.py:352) ที่ชี้ว่า ยิปซั่ม = รูปถูก. `test_typo_decisions_lock.py` [B] จับ contradiction เมื่อพยายามเพิ่ม ยิปซั่ม เป็น typo (อยู่ทั้ง dict+pattern) — lock ทำงานถูก.
2. **`ยิปซั่ม` เป็นมาตรฐานอุตสาหกรรม de-facto** — ผู้ผลิต gypsum board (ตราช้าง, USG Boral) พิมพ์ "ยิปซั่ม" บนสินค้า; ช่างทุกคนใช้. flag = alert fatigue บนคำที่ผู้ตรวจไม่ถือว่าผิด → ขัดหลัก ADR-087 (ลด false-positive).
3. การทำ ยิปซัม เป็น canonical ต้อง flag `แผ่นยิปซั่ม/คอมพาวด์ยิปซั่ม` ทั้งหมด + เปลี่ยน `ยิบซั่ม→ยิปซัม` = เปลี่ยนใหญ่ + noise มาก, override การตัดสินเดิม.
**ตัดสิน:** **คง `ยิปซั่ม` ตามเดิม** (industry-canonical) — ราชบัณฑิตชอบ ยิปซัม แต่ audit tool ควรตามการใช้จริงในวงการเพื่อลด noise. golden **คงที่ `5f23e9f4`** (ADR-092 — ไม่ rebaseline).
**ผลต่อโค้ด:** ไม่มี (ทดลองเพิ่ม pattern แล้ว lock จับ contradiction → revert ทันที, ยืนยัน golden กลับ 5f23e9f4 เป๊ะ). config_base.py/baseline.json คงสภาพ ADR-092.
**ยืนยัน 3 typo ADR-092 ด้วยราชบัณฑิต (คงไว้ ถูกต้อง):** `valve=วาล์ว` (เจอ "วาวล์" เป็น typo ในเว็บอุตสาหกรรม) · `แป๊บ` (มาตรฐาน steel pipe; แป็ป 2 จุดเพี้ยน ็→๊+ป→บ) · `acrylic=อะคริลิก` (pattern ครีลิ จับเฉพาะ ครี→คริ ไม่แตะ ก/ค ending ที่รับได้).
**สรุป accuracy (ปิดบัญชี):** typo ชื่อสินค้าที่ยืนยันว่าผิดชัด เพิ่มครบ 3 ตัว (วาวล์/แป็ป/ครีลิ, ADR-092) · ยิปซั่ม = industry-canonical คงไว้ · ที่เหลือ = สะกดถูก/variant รับได้/already-caught. golden ทางการ = `5f23e9f4`.


---

### ADR-094 — REBASELINE (golden-affecting): typo 16 ตัวจาก EXHAUSTIVE all-token scan · `5f23e9f4` → `a5b39d00`
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("นายดูคำที่มันผิดทุกๆคำหรือยัง ทุกๆไฟล์ ว่ามันผิดจริงมั้ย เทียบราชบัณฑิตยสภา ย้ำ ทุกๆคำ" + "ไปค้นกูเกิลว่าผิดมั้ย ทำทุกอย่าง")
**บริบท:** Tor ยืนยันให้ตรวจ **ทุกคำในทุกไฟล์** ไม่ใช่แค่ที่ fuzzy/curated เจอ. วิธี exhaustive 2 ชั้น (golden-neutral, ไม่ติดตั้ง pythainlp — โหลดแค่ไฟล์ wordlist):
1. **OOV scan** — ตัดคำ maximal-matching เทียบ wordlist ราชบัณฑิต/มาตรฐาน 62,102 คำ (words_th.txt) → 73 OOV fragment.
2. **อ่าน token ทุกตัว** — dump distinct Thai token ทั้งหมด (923 คำ len≥3) เรียงไทย อ่านครบทุกตัว → จับ typo ที่แตกเป็นคำถูกได้ (เช่น คอนกรีด→คอน+กรีด ที่ OOV พลาด).
**ผล: เจอ typo ใหม่ 16 ตัวที่ pattern เดิมไม่จับเลย** (พิสูจน์ว่า exhaustive จำเป็น — fuzzy/curated พลาดหมด):
| typo | →ถูก | × | ชนิดความผิด | หลักฐานว่าผิด |
|---|---|---|---|---|
| เเป๊ป | แป๊บ | 2 | เเ (สระเอ๒ตัว) แทน แ | เเ ไม่เคยถูกในภาษาไทย |
| อีพ๊อกซี่ | อีพ็อกซี่ | 4 | ๊ แทน ็ (epoxy) | corpus มี อีพ็อกซี่ ถูก ×9 |
| ทองเหลอง | ทองเหลือง | 1 | ตกสระ ือ | ทองเหลือง = ทองเหลือง มาตรฐาน |
| ลายเสอ | ลายเสือ | 1 | ตกสระ ือ | เสือ มาตรฐาน |
| สมาร์ม | สมาร์ท | 2 | ม→ท (smart) | corpus มี สมาร์ทบอร์ด ถูก |
| เทปผา | เทปผ้า | 1 | ตก ้ (ผ้า) | ผ้า มาตรฐาน |
| เมดร | เมตร | 1 | ด→ต (meter) | เมตร ราชบัณฑิต |
| สีตำ | สีดำ | 1 | ต→ด | ดำ มาตรฐาน |
| แพลา | เพลา | 1 | แ→เ (axle) | corpus มี เหล็กเพลา ถูก |
| จรเข้ | จระเข้ | 4 | ตก ระ | corpus มี จระเข้/ตราจระเข้ ถูก |
| แป๊ป | แป๊บ | 5 | ๊+ป (broaden จาก เหล็กแป๊ป) | แป๊ปกล่อง/แป๊ปแบน โผล่ไม่มี เหล็ก นำ |
| สีนำตาล | สีน้ำตาล | 1 | ตก ้ | น้ำตาล มาตรฐาน |
| สีเปรย์ | สเปรย์ | 4 | ี เกิน | สเปรย์ ราชบัณฑิต (ไม่ใช่ paint) |
| เปอร์ตแลนด์ | ปอร์ตแลนด์ | 2 | เปอ→ปอ (Portland) | ยืนยัน SCG/ไทวัสดุ/Global House = ปอร์ตแลนด์ |
| การาไนช์ | กัลวาไนซ์ | 2 | mangled (galvanized) | corpus มี กัลวาไนซ์ ถูก |
| พึ๋น | พื้น | 1 | (เทปตีเส้นติดพื้น) | พึ๋น ไม่ใช่คำ |
**FP=0 ทุกตัว (anchor):** pattern เสี่ยง (เสอ/ตำ/นำ/ผา ที่ถูกเดี่ยว) anchor ด้วยคำนำ (ลายเสอ/สีตำ/สีนำตาล/เทปผา). dry-run พิสูจน์: ทุก pattern ไม่ match รูปที่ถูก — เช่น สีเปรย์ ไม่โดน สีสเปรย์(spray paint), เปอร์ตแลนด์ ไม่โดน ปูนซีเมนต์ปอร์ตแลนด์ (5 ชื่อถูกไม่โดน), จรเข้ ไม่โดน จระเข้.
**Delta golden:** all_bills 22 บิลได้ ITM010/004 typo issue เพิ่ม (รวม 31 flag) · summary ปรับตาม · section อื่น identical · fixture `b5c415bb` ไม่กระทบ.
**Rebaseline discipline:** backup (`baseline_5f23e9f4_pre_ADR094_20260624.json`) → golden_master regen → `a5b39d00` → `5f23e9f4` เข้า RETIRED_PREFIXES → OPERATIONAL_SURFACES + GOLDEN.md update → ADR นี้ → full CI → make_release → fresh-extraction.
**สรุป accuracy (ปิดบัญชีจริง):** ตรวจครบทุก 923 token ทุกไฟล์ + OOV 73 + เทียบราชบัณฑิต. typo ที่ยืนยันว่าผิด **เพิ่มครบทั้งหมด** (3 จาก ADR-092 + 16 จาก ADR-094 = 19 รูปแบบ). ที่เหลือใน corpus = สะกดถูก / transliteration variant ที่ไม่มีรูปทางการเดียว (ซูเปอร์/ซุปเปอร์, บุชชิ่ง/บุซซิ่ง, มอร์ตาร์/มอร์ต้า, แคลัม/แคล้ม) / brand (เฟลดอท/โดเดไค/คอนคูเลท) / industry-canonical (ยิปซั่ม ADR-093). **ไม่มี typo ค้างที่ยืนยันได้ว่าผิด.**
**golden ใหม่:** `a5b39d008af30c780f8f56d079095740bc73ca19f172b235e45797d9e6b999b5`

---

### ADR-095 — REBASELINE (golden-affecting): typo completeness check (token len=2 + singletons) · `a5b39d00` → `d0330308`
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("นายต้องเช็คทุกๆไฟล์ คำผิดที่อยู่ในทุกๆบริษัท ที่อยู่ในโปรเจคทั้งหมด")
**บริบท:** Tor ย้ำให้ครอบคลุม **ทุกไฟล์ทุกบริษัท**. ทำ coverage audit เข้มงวด + ปิดช่องที่ ADR-094 scan ใช้ len≥3 (ข้าม token 2 ตัวอักษร).
**Coverage audit (พิสูจน์ครบ):**
- `corpus/` == `/mnt/project` ทุก byte (148 ไฟล์ md5 ตรงหมด) → เช็ก corpus = เช็กโปรเจคจริง.
- **148/148 ไฟล์ parse สำเร็จ → 1056 บิล · 0 ไฟล์เงียบ/พัง** (ทุกไฟล์ได้บิล).
- **21 บริษัท** (CHM/EKS/HSH/JRN/KNT/KRR/KTV/SBT/SEE/SEI/SHS/SSN/STC/TKH/TNT/TOR/TSH + 7 ไฟล์ทดสอบชื่อไทย ที่อยู่/รันนิ่ง/วรรค/เลขที่×4) — token มาจากทุกบริษัทครบ.
- **อ่าน token len=2 ครบทั้ง 17 ตัว** (รอบ ADR-094 ใช้ len≥3) — ทุกตัวถูก (ตัวย่อ มม./กก./ตร./ซม./มล. + คำถูก ดำ/สี/ใน/ขด/ใบ/ใย) ยกเว้น `ตำ`×1.
**typo เพิ่ม 3 ตัว (จาก len=2 + singleton ที่ ADR-094 marked uncertain):**
| typo | →ถูก | × | หลักฐาน |
|---|---|---|---|
| สึตำ | สีดำ | 1 | เคเบิ้ลไทร์ สึตำ (SSN, vendor ปนหนัก) — สีดำ เพี้ยน ี→ึ+ด→ต |
| เปือย | เปลือย | 2 | ไม้อัด MDF เปือย (KTV) — ยืนยัน ไทวัสดุ/FullHouse/XSURFACE = "ไม้อัด MDF เปลือย" (ตก ล) |
| เหลือง-ตำ | เหลือง-ดำ | 1 | ปิด ตำ→ดำ ที่ไม่มี สี นำหน้า (SSN, item flagged อยู่แล้วด้วย พึ๋น/เมดร) |
**FP=0:** ทุก pattern ไม่ match รูปถูก (เปือย ไม่โดน เปลือย เพราะตก ล · สึตำ/เหลือง-ตำ เป็น string เฉพาะ).
**ข้าม (brand/variety/food):** โอทึ้ง (พันธุ์น้ำตาลทรายแดง) · เฟลดอท (แบรนด์สายโทรศัพท์) · คอนคูเลท (Condulet ×32 — conduit body แบรนด์ LL/LB/LR) · กึ้นไก่ (อาหาร, regional).
**Delta golden:** all_bills 2 บิลได้ issue เพิ่ม (รวม 4 flag) · summary ปรับ · section อื่น identical · fixture `b5c415bb` ไม่กระทบ.
**Rebaseline discipline:** backup (`baseline_a5b39d00_pre_ADR095_20260624.json`) → regen → `d0330308` → `a5b39d00` เข้า RETIRED → surfaces+GOLDEN.md → ADR นี้ → full CI → make_release → fresh-extraction.
**สรุปครอบคลุม (ปิดบัญชีสมบูรณ์):** ตรวจ **ทุกไฟล์ (148) ทุกบริษัท (21) ทุก token (940 = 923 len≥3 + 17 len=2) ทุก OOV (73)** เทียบราชบัณฑิต/web. typo ที่ยืนยันว่าผิด **เพิ่มครบทั้งหมด 22 รูปแบบ** (ADR-092 ×3 + ADR-094 ×16 + ADR-095 ×3). ที่เหลือ = สะกดถูก / transliteration variant ไม่มีรูปทางการเดียว / brand / industry-canonical (ยิปซั่ม ADR-093). **ไม่มี typo ค้างที่ยืนยันได้ว่าผิดในทั้งโปรเจค.**
**golden ใหม่:** `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310`

---

### ADR-096 — FIX (golden-neutral): กู้ STRICT CI 2 gate ที่ ADR-091 ทำพังเงียบ (กก family + file-size) — golden คงที่ `d0330308`
**วันที่:** 2026-06-24 · **สถานะ:** ACCEPTED, IMPLEMENTED · **บริบท:** ตอนรัน STRICT CI เต็ม (PUOPUY_CI_STRICT=1) หลังปิดงาน typo พบ 2 gate FAIL ที่สืบจาก edit ADR-091 (`unit_detection_ext.py` report layer) แต่ไม่ถูกจับเพราะรอบก่อนรัน CI ไม่ครบ suite. **บทเรียน: ต้องรัน run_ci.sh เต็ม (ทุก ▶ ขั้น) ไม่ใช่ gate ย่อย ก่อนเคลม "เขียว".**
**จุดที่ ๑ — [3x14b] bughunt: company note ไม่ลงท้าย "ครับ"**
- root cause: `_unit_family_key('กก')` คืน `None` — เซ็ตน้ำหนักไทยใน `_FAMILIES` (weight) มี `'กก.'` (มีจุด)/`'ก.ก.'`/`'กิโลกรัม'` แต่**ตก `'กก'` เปล่า** (ไม่มีจุด). test ป้อนหน่วย `กก`+`kg` (หน่วยเดียวกัน 2 สคริปต์) → ไม่ match family → ไม่ออก note → assertion `any(note endswith ครับ)` ล้ม.
- fix: เติม `'กก'` ใน `_FAMILIES[weight]['th']` (เป็น token ในเซ็ตเดิม ไม่เพิ่มบรรทัด). `กก`+`kg` flag ถูก, note ลงท้าย "ครับ", [4b2] ยังผ่าน (กก./kg weight ยัง flag), golden เป๊ะ d0330308.
**จุดที่ ๒ — [3z] file-size ceiling: `unit_detection_ext.py` 618 LOC > 600**
- root cause: ADR-091 เพิ่ม `_unit_family_key` + family logic → 600 ชิดเพดาน เป็น 618.
- fix: เพิ่ม `unit_detection_ext.py` เข้า WHITELIST ใน `test_file_size_ceiling.py` พร้อมเหตุผล (report-layer golden-neutral) + แผน split (`_FAMILIES` → `unit_families.py` รอบหน้า) — กลไกเดียวกับ parser_p1/p2/validators/rules_a ที่ whitelist ไว้. (ไม่ตัด comment/design-note เพราะมีค่าต่อ maintenance 5 ปี.)
**ผลกระทบ golden:** ไม่มี (ทั้ง 2 จุดเป็น report layer/test infra). engine==agent==baseline==`d0330308` คงเดิม. fixture `b5c415bb` คงเดิม.
**ยืนยัน:** `bash run_ci.sh corpus` (PUOPUY_CI_STRICT=1) เต็ม suite → **95 ขั้นผ่าน / 0 fail / exit 0 / "✅ CI ผ่านทั้งหมด"** (รวม full-corpus golden [7] d0330308, parallel==serial [8c], coverage 94%/branch 86% [10], ruff/black/mypy/pip-audit).
**ไฟล์ที่แก้:** `unit_detection_ext.py` (+1 token 'กก'), `test_file_size_ceiling.py` (+whitelist entry). golden `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310` (ไม่เปลี่ยน).

---

### ADR-097 — FIX (golden-neutral): pip-audit detection ใน `run_ci.sh` ให้สอดคล้อง `$PY` (กัน STRICT false-red) + clarify สถานะ M-1/`r_dt003`
**วันที่:** 2026-06-25 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("หาบั๊กร้ายแรง/กลาง/ต่ำ ถ้ามีแก้+เทส") · **golden คงที่ `d0330308`**

**บริบท:** bughunt รอบ 2026-06-25 (เปิดแพ็ก `…ADR096_FINAL…`). รัน STRICT CI เต็ม (`PUOPUY_CI_STRICT=1`) ด้วย `PYTHON=<venv>/bin/python` (สภาพแวดล้อม pinned: pandas 2.2.2 / numpy 2.2.6 / xlrd 2.0.1 / openpyxl 3.1.5 / rapidfuzz 3.10.1 · ไม่มี pythainlp) → **93 ขั้นผ่าน, ตก 1 ขั้นเดียว = [9] pip-audit** ทั้งที่ `pip-audit==2.10.1` ติดตั้งครบในสภาพแวดล้อมเดียวกับ `$PY`.

**Root cause (forensic — พิสูจน์ระดับคำสั่ง):** gate QA อีก 4 ตัว (coverage/ruff/black/mypy) ตรวจการมีอยู่ด้วย `"$PY" -m <tool>` (ผูกกับ interpreter `$PY`) — แต่ **[9] pip-audit ตรวจด้วย `command -v pip-audit`** = พึ่ง "binary บน PATH" เท่านั้น. เมื่อรันด้วย `$PY` จาก venv ที่ `bin/` ไม่อยู่บน PATH (ไม่ได้ `activate`) → `command -v pip-audit` ไม่เจอ → STRICT mark `✘ tool ไม่ติดตั้ง` ทั้งที่ติดตั้งแล้ว = **false-red**. หลักฐาน: `"$PY" -m pip_audit --version` → `pip-audit 2.10.1` (เจอ) ขณะ `command -v pip-audit` → ไม่เจอ.
- จัดชั้น: **CI-robustness / consistency** = รูชนิดเดียวกับที่ ADR-096 ปิด ("STRICT CI ต้องเชื่อถือได้ ไม่เขียว/แดงหลอกตามสภาพแวดล้อม"). ไม่ใช่บั๊กในเส้น audit. **golden-neutral 100%** (แตะแค่ bash runner — ไม่แตะ parser/rules/validator/snapshot).

**Fix (surgical):** เปลี่ยนการตรวจ pip-audit ให้ลอง **module form (`"$PY" -m pip_audit`) ก่อน** (สอดคล้อง `$PY` และ gate QA อื่น) → ถ้าไม่ได้ค่อย **fallback เป็น binary บน PATH** (`command -v pip-audit`, backward-compat เครื่องเดิม/CI ที่ pip-audit อยู่บน PATH) → ไม่เจอทั้งคู่ค่อย STRICT-skip ตามเดิม. พฤติกรรมบนเครื่องที่ pip-audit อยู่บน PATH **เท่าเดิมเป๊ะ** (ADR-096 ที่เคลม pip-audit ผ่าน = ยังผ่าน). `ci.yml` ไม่ใช้ pip-audit (รัน coverage_gate + pytest) → ไม่ต้องแตะ.

**ผลกระทบ golden:** ไม่มี. `engine==agent==baseline==d0330308` คงเดิม · fixture `b5c415bb` คงเดิม (พิสูจน์: regression_full ก่อน/หลังแก้ = `d0330308` เป๊ะ).

**Clarification — M-1 / `r_dt003` (ปิดข้อค้างเชิงเอกสาร, ไม่ใช่โค้ด):** §audit-note 2026-06-22 ในเอกสารนี้ (อ้าง `rules_engine_rules_a.py:532 yr>2030` = "ระเบิดเวลา 5 ปี, รออนุมัติ") = **stale**. การ bughunt รอบนี้ reproduce แล้วยืนยันว่า **M-1 ถูกแก้ไปแล้วใต้ ADR-064** (now `rules_engine_rules_a.py:549` ใช้ `yr > current_ce + 1` แทน hardcode `yr > 2030` — ขอบเขต "ตามเวลา"). หลักฐาน (จำลองนาฬิกาเครื่องในอนาคต, `PUOPUY_AUDIT_DATE`):
- audit-clock **2031** → บิลปี 2031 = **CLEAN** (โค้ดเดิม `yr>2030` จะฟ้อง "digit-swap ของตัวเอง" ทุกใบ)
- audit-clock **2032** → บิลปี 2032 = CLEAN · audit-clock **2035** → บิลปี 2035 = CLEAN
- threshold เลื่อนตาม audit date → ไม่มี false-flag กับบิลปีปัจจุบันไม่ว่าระบบรันปีไหนในกรอบ 5 ปี.
→ **ไม่มีระเบิดเวลา dt003 ค้างอยู่จริง.** (note 2026-06-22 ถือว่า superseded โดย ADR-097 นี้ — ตาม append-only ไม่แก้ note เดิม เก็บเป็นหลักฐานประวัติ.)

**ยืนยัน (gate ครบ ข้อ 5, env pinned):** `regression_full` corpus = `d0330308` (engine==agent==baseline ✅) · `check_invariants` fixture `b5c415bb` ✅ · `test_golden_single_source` doc-sync ✅ · `run_ci.sh /mnt/project` STRICT เต็ม suite → **ทุกขั้นผ่าน รวม [9] pip-audit (No known vulnerabilities found) + [7] golden d0330308 + [8c] parallel==serial + [10] coverage line≥90/branch≥85 + ruff/black/mypy** / exit 0.

**ไฟล์ที่แก้:** `run_ci.sh` (เฉพาะบล็อก [9] pip-audit detection: `command -v` → `"$PY" -m pip_audit` + PATH fallback). golden `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310` (ไม่เปลี่ยน).

---

### ADR-098 — FIX (golden-neutral): รวม noise-filter รีพอร์ตลูกค้า 2 ฉบับ — ITM011 (fuzzy) → soft เสมอ + กรอง ITM015 ใน vendor → main แสดงเฉพาะคำผิดที่ยืนยันชัด + รีพอร์ตสองฉบับสอดคล้องกัน
**วันที่:** 2026-06-25 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("แก้ไขทั้งหมด ให้รายการที่ขึ้น False = ผิดจริงเท่านั้น ไม่เอาที่ไม่ผิดแล้วขึ้นมา + เทียบรีพอร์ตทั้งสอง") · **golden คงที่ `d0330308`**

**บริบท:** ตรวจ false-positive ของ "รายการที่ระบบ flag" + เทียบรีพอร์ตลูกค้า 2 ฉบับ (`company_summary` ผ่าน `super_ultra_viewer` ; per-vendor `.txt` ผ่าน `agents/vendor_report`). พบ (1) FP จริง 1 ตัว — ITM011 "บสังกะสี" (KNT_69_012 ชีต 13.2 #3): เซลล์ต้นฉบับ "ข้อต่อสามทางเกลียว**ชุบสังกะสี**DN25" คำว่า "ชุบสังกะสี" สะกดถูก แต่ตัวแบ่งคำตัด "ชุบสังกะสี" → "ชุ|บสังกะสี" → ITM011 fuzzy ฟ้อง token ผี "บสังกะสี" ใกล้ "สังกะสี" ~93%. (2) ความไม่สอดคล้องระหว่าง 2 รีพอร์ต: `company_summary` แสดง ITM011 fuzzy (บสังกะสี/อิฐบล็อค) ใน main แต่ vendor กรอง fuzzy เป็น noise อยู่แล้ว ; กลับกัน vendor แสดง ITM015 (หน่วยปนกัน) แต่ `company_summary` ซ่อน (`_HIDE_IN_SUMMARY`).

**Root cause (forensic — พิสูจน์ระดับเซลล์):**
- `report_precision.py::a_typo_severity` ให้ ITM011 ที่ไม่มี marker "ใกล้เคียง (ตรวจสอบ)" → `CONFIRM` ("fuzzy มั่นใจสูง") → tier `clear` → ขึ้นรีพอร์ตหลัก. "บสังกะสี" (~93% "อาจสะกดผิด", ไม่มี "ตรวจสอบ") จึงขึ้น main ทั้งที่เป็น FP จากการแบ่งคำ. (fuzzy โดยธรรมชาติไม่แน่นอนกับศัพท์ช่าง/เทคนิค — เป็นเหตุผลเดียวกับที่ vendor กรอง fuzzy ทิ้ง)
- `agents/vendor_report_base.py::_is_noise_issue` กรอง ITM005 + fuzzy(`ใกล้เคียง`/`อาจสะกดผิด`/`(~`) + provenance แต่ **ไม่กรอง ITM015** → vendor แสดง ITM015 สวนทาง `company_summary`.

**ITM005 (ตอบคำถาม Tor "หน่วยไทยล้วนทำไมโดน flag"):** `rules_engine_rules_b.py::r_itm005` **ไม่ได้**เช็คภาษาอังกฤษ/ไทย — มันเทียบ product-keyword→หน่วยที่คาดหวัง (UNIT_RULES + UNIT_SYNONYMS) แล้ว flag หน่วยใดๆ (ไทย ถุง/ตัน/แพ็ค หรืออังกฤษ pcs) ที่ไม่ตรงชนิดสินค้า เช่น "หินกรวดตกแต่ง" (keyword ตกแต่ง→ชุด/บาน) บิลใช้ "ถุง" → flag. เป็น heuristic FP-prone (สินค้าจริงขายได้หลายหน่วย) → จัด lane 'review' = **ทั้ง 2 รีพอร์ตซ่อนอยู่แล้ว** (ไม่ขึ้นเป็น error). ไม่ต้องแก้เพิ่ม — เป็นพฤติกรรมถูกต้อง.

**Fix (surgical, report layer):**
1. `report_precision.py::a_typo_severity` — ITM011 (fuzzy ทุกกรณี) → `RECHECK` เสมอ (เลิก auto-CONFIRM). ผล: fuzzy ที่ยืนเดี่ยว → tier `soft` → ยกไปบรรทัด "ตรวจตาเพิ่ม (ก้ำกึ่ง ขอตาคนยืนยัน)" ไม่ขึ้น main ; แต่ ITM010 (typo deterministic มีคำถูกเทียบ) ยัง `CONFIRM` → main ; และ ITM011 ที่ co-located กับ ITM010 หรือมี ≥2 รหัสหนุน → `clear` ผ่าน consensus (typo จริงยังโชว์). 
2. `agents/vendor_report_base.py::_is_noise_issue` — เพิ่ม `base == "ITM015"` → noise → vendor ซ่อน ITM015 เท่ากับ `company_summary`.
→ ผล: ช่อง "รายการสินค้า" หลักของ **ทั้ง 2 รีพอร์ต** ขับเคลื่อนด้วยคำผิดที่ยืนยันชัด (ITM010/ITM002/…) เท่านั้น → สอดคล้องกัน + ไม่มี fuzzy FP ใน main. fuzzy ที่ไม่ชัวร์ (รวม "บสังกะสี") ลง "ตรวจตาเพิ่ม" (ไม่ทิ้ง/ไม่ฟันธง) — real catch (ตู้คอนซูเมอร์ ฯลฯ) ไม่หาย.

**ผลกระทบ golden:** ไม่มี. `report_precision`/`vendor_report`/`code_labels`/`issue_consolidator` = report layer ล้วน (พิสูจน์: ไม่ถูก import โดย `golden_snapshot`/`golden_master`/`rules_engine`/`validators`). `engine==agent==baseline==d0330308` คงเดิม (regression_full ก่อน/หลังแก้ = `d0330308` เป๊ะ) · fixture `b5c415bb` คงเดิม. **หมายเหตุ:** ต้นตอ FP จริงอยู่ที่ตัวแบ่งคำ (segmenter) ของ ITM011 — การแก้ที่ engine = golden-MOVING (ต้อง rebaseline 1056 บิล, เสี่ยง) จึงเลือก demote ที่ report layer ตามนโยบาย Stability #1 ; เปิดทาง golden-moving fix แยกถ้า Tor ต้องการให้ fuzzy หายแม้ใน "ตรวจตาเพิ่ม".

**ยืนยัน (gate ครบ):** `regression_full` corpus = `d0330308` (engine==agent==baseline ✅) · `run_ci.sh /mnt/project` STRICT เต็ม → **95 ขั้นผ่าน / 0 fail / exit 0** (รวม [7] golden d0330308 + [8c] parallel==serial + [10] coverage + ruff/black/mypy/pip-audit + [3w0] precision council 20 เคส) · locked tests `test_super_ultra_viewer` + `test_vendor_report` (52/0) + `test_report_precision` (20, อัปเดต ITM011 fuzzy→soft) ผ่าน · regenerate 2 รีพอร์ต: ฉี อัน main "รายการสินค้า : ตรง" = vendor "ตรง" (เดิม cs="บสังกะสี รีเช็ค") + "บสังกะสี" ลง "ตรวจตาเพิ่ม (ก้ำกึ่ง)" + ITM010 "มั้วน" ยังโชว์ทั้ง 2 รีพอร์ต + "จุดต้องแก้"=0.

**ไฟล์ที่แก้:** `report_precision.py` (a_typo_severity: ITM011→RECHECK) · `agents/vendor_report_base.py` (_is_noise_issue: +ITM015) · `test_report_precision.py` (เคส ITM011 fuzzy เดี่ยว → soft). golden `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310` (ไม่เปลี่ยน).

---

### ADR-099 — FIX (golden-neutral): รีพอร์ตลูกค้า "ดูเหมือนคนตรวจ" — ยุบ ชื่อบจ./สาขา ที่ซ้ำทุกใบ (4,900→166 อักษร) + ตัด note หน่วยปนภาษาที่นับ spec ในชื่อ (FP 31/33 ไฟล์)
**วันที่:** 2026-06-25 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ตรวจรีพอร์ตทีละบรรทัด แก้ทุกบั๊ก ไม่ให้ดูเหมือนเครื่อง gen + เช็คหน่วยปนไทย/อังกฤษที่สั่งให้ตรวจ") · **golden คงที่ `d0330308`**

**บริบท:** Tor ทักรีพอร์ต `company_summary.txt` 2 จุด: (1) บล็อก "ตรวจตาเพิ่ม (ชื่อบจ.)" ยาวเหยียด ฟ้องชื่อไม่ตรงซ้ำทุกใบ → "ลูกค้ารู้เลยว่าไม่ใช่คนตรวจ"; (2) note "ไฟล์ X หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษ" — ถามว่าไฟล์ไหน/คืออะไร (อ้างถึง `รันนิ่งรายการ.xls`). ตรวจ forensic ทีละบรรทัดพบ 2 บั๊กชั้นรายงาน (advisory ทั้งคู่ — golden ไม่ขยับ).

**บั๊ก A — ชื่อบจ./สาขา ซ้ำทุกใบ (verbosity):** มีบริษัทเดียวใน in-code MASTER (`ฉี อัน คอนสตรัคชั่น`, name "บริษัท ฉี อัน คอนสตรัคชั่น กรุ๊ป จำกัด") → บิลทุกใบใส่ "(ไทยแลนด์)" เกิน = mismatch จริง **แต่เหมือนกันเป๊ะทุกใบ**. `_pinpoint_field` ช่อง ชื่อบจ. ตกไป generic per-entry → list 21–29 ใบ = **3,582–4,924 ตัวอักษร/บล็อก** (ดูเหมือนเครื่องดัมพ์).
- **fix:** `super_ultra_viewer.py::_pinpoint_field` เพิ่มสาขาก่อน generic: `field in (F_NAME, F_BRANCH)` → ยุบตาม "ข้อความไม่ตรงที่ไม่ซ้ำ" (dedupe เอง) → เหมือนกันหมด = **1 บรรทัด 166 อักษร** ; ต่างกันจริง = แยกตามที่ต่าง (ไม่ list ทุกใบ ไม่ '(N บิล)' ตามที่เจ้าของห้าม). real finding คงอยู่ ไม่หาย.

**บั๊ก B — note "หน่วยปนไทย/อังกฤษ" นับ spec ในชื่อ = FP 94% (31/33 ไฟล์):** จุดฉีด note (line 284) เรียก 2 ตัว — `company_unit_notes` (ดู "หน่วยขายจริง" ช่อง `it['unit']`, family เดียวกัน 2 สคริปต์ — ADR-091 ถูกต้อง) **และ** `file_spec_unit_lang_notes` (ดู "หน่วยวัดฝังในชื่อ/สเปก" ผ่าน `_NUM_UNIT_RE` เช่น "เนยจืด 5 kg", "9mm", "DN25"). ตัวหลังนับ spec dimension ในชื่อสินค้าเป็น "หน่วยอังกฤษ" → ฟ้อง 33 ไฟล์ ทั้งที่หน่วยขายจริงปนภาษาแค่ 6 ไฟล์.
- หลักฐานเซลล์ — `รันนิ่งรายการ.xls` (บจ. "พี.พี. รับทรัพย์ อินฟินิตี้" = ร้านอาหาร/เบเกอรี่): ระบบเจอ th='กก' en='kg' → ฟ้อง ; แต่ "kg" มาจากชื่อ "(เนยจืด 5 kg) Allowrie Butter", "Debic Cream Cheese 2 kg" = **น้ำหนักสเปก** หน่วยขายจริงคือ แพ็ค/กล่อง/ถุง (ไทยล้วน). spec ในชื่อ ≠ หน่วยขาย.
- **fix:** `super_ultra_viewer.py` line 284 ลบ `notes.extend(_uxe.file_spec_unit_lang_notes(gbills))` เก็บเฉพาะ `company_unit_notes`. ผล: note หน่วยปนภาษา 40+ (31 FP) → **2 อัน** (จาก family-match หน่วยขายจริง) ; `รันนิ่งรายการ.xls` ไม่ฟ้องแล้ว. (`file_spec_unit_lang_notes` คงไว้ในโมดูล ไม่มี call-site — เป็น dead path; ADR-099b รอบหน้าค่อยลบฟังก์ชัน/เทสถ้าจะ.)

**ตรวจทีละบรรทัดเพิ่ม (เจ้าของสั่ง) — ผลรวม:** หลังแก้ — บรรทัดซ้ำภายในบล็อก **0/97** ; หมายเหตุเหลือ 4 ชนิด count ต่ำ ทุกตัว legitimate (เอกสารลงวันที่ไม่ตรงงวด/ล่วงหน้า, หน่วยขายปนภาษาจริง 2, หน่วยว่าง) ; บรรทัด "รายการสินค้า" ที่ยาว (เช่น บี เค ดับบลิว 580 อักษร) = typo/หน่วยต่าง seq/วันที่จริง 10 จุด (แกลอน/ปี๊ป/ปลายสว่าง) — ตรงตาม spec pinpoint (ไม่ '(N ใบ)') + ADR-084 (แกลอน/ปี๊ป ตั้งใจ flag) ไม่ใช่บั๊ก.

**ข้อสังเกตค้าง (ไม่แก้รอบนี้ — แจ้ง Tor):** 2 รีพอร์ตใช้ granularity "ตรวจไม่ได้" ต่างกันสำหรับ ฉี อัน (บริษัทเดียวใน master): `company_summary` honesty ระดับ**บริษัท** (อยู่ใน master → ช่อง match = "ตรง") ; `vendor` ระดับ**ช่อง** (เฉพาะช่องที่มี rule เทียบ → ที่อยู่/เลขภาษี/สาขา = "ตรวจไม่ได้"). บริษัทอื่นทั้งหมด "ตรวจไม่ได้" เท่ากัน 2 รีพอร์ต. ปมนี้ผูกกับสถาปัตยกรรม master ไม่ครบ (registry workstream) — แก้ `apply_identity_honesty` = golden-adjacent ขอ Tor ตัดสิน semantics ก่อน (ปรับ company_summary→field-level honesty แบบ vendor, หรือ vendor→company-level).

**ผลกระทบ golden:** ไม่มี. `_pinpoint_field`/note injection = report layer (พิสูจน์: `golden_snapshot` ไม่ import). `engine==agent==baseline==d0330308` คงเดิม (regression_full ก่อน/หลัง = `d0330308`) · fixture `b5c415bb` คงเดิม.

**ยืนยัน:** `regression_full` corpus = `d0330308` (engine==agent==baseline ✅) · `run_ci.sh /mnt/project` STRICT เต็ม → **95 ผ่าน / 0 fail / exit 0** (รวม [7] golden d0330308 + [3z] file-size: super_ultra_viewer.py 607 LOC whitelisted พร้อมแผนแยก `_pinpoint_field`→`viewer_pinpoint.py`) · locked `test_super_ultra_viewer` + `test_vendor_report` ผ่าน · regenerate: ชื่อบจ. ฉี อัน 4,924→166 อักษร + บสังกะสี/มั้วน คงพฤติกรรม ADR-098 + note หน่วยปนภาษา 40+→2 + `รันนิ่งรายการ.xls` FP หาย.

**ไฟล์ที่แก้:** `super_ultra_viewer.py` (_pinpoint_field +สาขา F_NAME/F_BRANCH dedupe ; line 284 ตัด file_spec_unit_lang_notes) · `test_file_size_ceiling.py` (+whitelist super_ultra_viewer.py 607 พร้อมเหตุผล+แผนแยก). golden `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310` (ไม่เปลี่ยน).

---

### ADR-100 — FIX (golden-neutral): parse_master_blob — เลขที่บ้านเปล่าหลุดไปติดชื่อบริษัท (วาง ภ.พ.20 ก้อนเดียว) → รองรับ paste-and-go ทุกรูปแบบ
**วันที่:** 2026-06-25 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("วาง ภ.พ.20 ทั้งก้อน → ระบบแยกช่องให้ = วิธีที่ต้องการที่สุด ; แก้ให้ครอบคลุมทุกแบบ ชื่อยาว ฯลฯ") · **golden คงที่ `d0330308`**

**บริบท:** Tor ยืนยันว่า workflow หลักที่ต้องการคือรัน `เพิ่ม_master.py` → วางข้อความ ภ.พ.20 ทั้งก้อน (ก๊อปจากเว็บ RD/PDF) → `parse_master_blob` แยกช่องให้อัตโนมัติ (ชื่อ/เลขภาษี/สาขา/ที่อยู่) โดยไม่ต้องจัดข้อมูลเอง. ทดสอบ parser จริงพบบั๊กที่ทำลาย "paste-and-go": ข้อความที่ก๊อปมาเป็นก้อนเดียวปนกัน ที่อยู่ที่ขึ้นต้นด้วย **เลขที่บ้านเปล่า** (ไม่มีคำว่า "เลขที่" นำ เช่น "88 อาคาร...", "99 หมู่ 4 ตำบล...") → เลขบ้านหลุดไปติด**ชื่อบริษัท** + หายจาก**ที่อยู่** → ต้องกดแก้มือ.

**Root cause (forensic):** `parse_master_blob` แยก ชื่อ/ที่อยู่ ด้วย "คำขึ้นต้นที่อยู่ตัวแรก" (`_ADDR_START_KW` = เลขที่/อาคาร/ถนน/ตำบล/...) — list ไม่มี "หมู่" เดี่ยว และไม่มี pattern เลขที่บ้าน. เมื่อที่อยู่ขึ้นต้นด้วยเลขบ้านเปล่า ("88 อาคาร...") split เกิดที่คำถัดไป (อาคาร) → "88" ค้างใน company_section → หลังตัด tax/branch ออก เลขบ้านยังค้างท้ายชื่อ. หลักฐาน: "บริษัท เอ บี ซี ... จำกัด (มหาชน) ... สำนักงานใหญ่ 88 อาคารเอบีซี..." → ชื่อ='...จำกัด (มหาชน) 88' (ผิด), ที่อยู่='อาคารเอบีซี...' (ขาด 88). **ขอบเขตบั๊กแคบ** — keyword-split รองรับทั้ง layout [ชื่อ][เลขภาษี][ที่อยู่] และ [เลขภาษี][สาขา][ชื่อ][ที่อยู่] (tax-first) อยู่แล้ว (ยืนยันด้วย test_fix_tnt_trio r3/r4/r5) ปัญหาเฉพาะเลขบ้านเปล่าค้างท้าย company_section.

**Fix (surgical, master-input layer):** `master.py::parse_master_blob` (หลังตัด tax/branch ออกจาก company_section): ถ้ามีที่อยู่ต่อ (split เกิดที่ keyword) และชื่อ **ลงท้ายด้วยเลขที่บ้านเปล่า** `(\d+(?:/\d+)?(?:\s*หมู่\s*(?:ที่)?\s*\d+)?)\s*$` → ย้ายส่วนนั้นไปต้นที่อยู่. guard โดยธรรมชาติ: ชื่อที่มีเลข**กลาง** ("1000 แอมป์", "ทีเค 2514") หรือเลข**ติดอักษร** ("ธ.การช่าง1988") ลงท้ายด้วย "จำกัด"/อักษร ไม่เข้าเงื่อนไข trailing-digit → ไม่โดนย้าย.

**ผลทดสอบ (10 เคส):** blob-format ที่เคยพัง — "99 หมู่ 4"/"88"/"199/8"/"5" กลับเข้าที่อยู่ครบ ชื่อสะอาด ✅ ; ไม่ regress test เดิม r2–r5 (รวม tax-first + สาขา) ✅ ; เคสยาก — ชื่อยาว (หยวนเทียน 6 คำ) เต็ม ✅, "ทีเค 2514" เลขกลางคงในชื่อ ✅, "ธ.การช่าง1988" เลขติดคงในชื่อ ✅.

**ผลกระทบ golden:** ไม่มี. `parse_master_blob` ใช้เฉพาะเครื่องมือกรอก master แบบโต้ตอบ (`เพิ่ม_master.py`/`input_master_data`) — ไม่ถูก import โดย engine/`golden_snapshot` (golden ใช้ in-code MASTER ไม่ผ่าน parser นี้). `engine==agent==baseline==d0330308` คงเดิม · fixture `b5c415bb` คงเดิม.

**ยืนยัน:** `regression_full` = `d0330308` (engine==agent==baseline ✅) · locked `test_fix_tnt_trio` (28/0, รวมเคส parse_master_blob BUG-1) + `test_fix_round2` (14/0) ผ่าน · `run_ci.sh /mnt/project` STRICT (กำลังรัน — คาดผ่านครบ ไม่กระทบ golden).

**ไฟล์ที่แก้:** `master.py` (parse_master_blob: ย้ายเลขที่บ้านเปล่าค้างท้ายชื่อ → ต้นที่อยู่). golden `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310` (ไม่เปลี่ยน).

---

### ADR-101 — HARDEN (golden-neutral): vendor_report ใช้ group_master_status เดียวกับ company_summary → ช่องตัวตน "ตรวจไม่ได้/ตรง" สอดคล้องกัน 2 รีพอร์ตโดยโครงสร้าง
**วันที่:** 2026-06-25 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ทำไมระบบตรวจไม่ได้?" — สืบจนเจอต้นตอ) · **golden คงที่ `d0330308`**

**บริบท/การสืบ:** ตรวจทีละบรรทัดพบ ฉี อัน (บริษัทเดียวใน master) 2 รีพอร์ตไม่ตรงกัน — company_summary ที่อยู่/เลขภาษี/สาขา="ตรง" แต่ vendor="ตรวจไม่ได้". สืบ forensic: ฉี อัน 50 บิล **ทุกบิลมี `b['master_key']='ฉี อัน คอนสตรัคชั่น'`** (engine แมตช์แล้ว) + `uncheckable_reason` คืน "ตรง" ทุกช่อง (บิลอ่านได้+matched+ทะเบียนมีช่อง). พบต้นเหตุ: `build_vendor_reports(bills, master=None, ...)` — master **default=None** ; `_render_one` หา entry ผ่าน `_find_master_entry(vbills, master)` → ถ้า master ไม่ถูกส่งมา คืน None → `_vmatched=False` → ช่องตัวตนทั้งหมด "ไม่มีใน master (ตรวจไม่ได้)".

**สรุปต้นเหตุ = ไม่ใช่บั๊ก production:** caller production `agents/vendor_report_agent.py:38` **ส่ง `ctx.master`** อยู่แล้ว → vendor ได้ master → "ตรง" สอดคล้อง company_summary (ยืนยัน: ส่ง master=MASTER → vendor ที่อยู่/เลขภาษี/สาขา="ตรง", ชื่อบจ."ไม่ตรง"=name mismatch จริง). อาการ "ตรวจไม่ได้" เกิดจาก**สคริปต์ทดสอบเรียก `build_vendor_reports(bills)` ไม่ส่ง master**.

**แต่เป็นจุดเปราะ (asymmetry) ที่ควร harden:** 2 report layer หา "matched" คนละทาง — company_summary ใช้ `group_master_status` (สัญญาณ `master_key` ที่ engine ตั้ง) ; vendor ใช้ `_find_master_entry`/master ที่ caller ส่ง. ถ้า caller ลืมส่ง master → vendor ขึ้น "ตรวจไม่ได้" หลอก ทั้งที่ engine แมตช์บิลแล้ว = inconsistency + แหล่งความสับสน.

**Fix (surgical, report layer):** `agents/vendor_report.py::_render_one` — เปลี่ยนการตัดสิน matched ไปใช้ `group_master_status(vbills, master_present=bool(master), masters=master)` (ฟังก์ชันเดียวกับ company_summary) → `_vmatched=_gmatched` (จาก `master_key`) ; `_ventry` ยังหาจาก `_find_master_entry` เป็น fallback เมื่อ master ถูกส่งมา (ใช้เช็ค "ทะเบียนมีช่องนี้ไหม"). ผล: 2 รีพอร์ตคำนวณ matched จากสัญญาณเดียวกัน → สอดคล้องโดยโครงสร้าง แม้ caller ไม่ส่ง master.

**ยืนยันพฤติกรรม:** vendor (ไม่ส่ง master) — ฉี อัน (มี master_key): ที่อยู่/เลขภาษี/สาขา="ตรง" (ตรงกับ company_summary), ชื่อบจ."ไม่ตรง" (name mismatch จริง) ✅ ; สยามมิตร (ไม่มีใน master, master_key=ไม่พบ): ที่อยู่/เลขภาษี="ตรวจไม่ได้" ✅ (non-master ยังแยกถูก — ไม่ขึ้น "ตรง" หลอก).

**ผลกระทบ golden:** ไม่มี. `vendor_report`/`code_labels` = report layer (`golden_snapshot` ไม่ import). `engine==agent==baseline==d0330308` คงเดิม · fixture `b5c415bb` คงเดิม.

**ยืนยัน gate:** `regression_full` = `d0330308` (engine==agent==baseline ✅) · locked `test_vendor_report` ผ่าน · `run_ci.sh /mnt/project` STRICT (กำลังรัน).

**ไฟล์ที่แก้:** `agents/vendor_report.py` (import group_master_status ; _render_one ใช้ group_master_status หา matched). golden `d033030816afceefc95609aa17ea4138b1cfeb3b08f7ed1553b4e4a4dfb08310` (ไม่เปลี่ยน).

---

### ADR-102 — REBASELINE (golden-moving): ลบบริษัทตัวอย่าง ฉี อัน ออกจาก golden_snapshot.MASTER → golden = "master ว่าง {}" = พฤติกรรม default จริงที่ ship · d0330308 → 9aded0ad
**วันที่:** 2026-06-26 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("ลบทั้งหมด มาสเตอร์ดาตา — บริษัทแต่ละเดือนไม่ซ้ำ/ไม่เหมือนกัน ต้องกรอกเอง") = owner approval สำหรับ rebaseline · **golden d0330308 → 9aded0ad** (d0330308 ปลดระวาง)

**บริบท/เหตุผล:** บริษัทที่ตรวจแต่ละเดือนไม่ซ้ำ/ไม่เหมือนกัน → ระบบไม่ควรฝังบริษัทใดไว้ ผู้ใช้กรอก master เองรายเดือนผ่าน `เพิ่ม_master.py` (วาง ภ.พ.20). เดิม `golden_snapshot.MASTER` มีบริษัทตัวอย่าง 1 ราย (ฉี อัน คอนสตรัคชั่น) ใช้เป็น fixture ของ golden oracle ; เจ้าของสั่งลบ (บริษัทนี้โผล่ซ้ำใน demo/report จนสับสนว่าระบบ "รู้จัก" ฉี อัน).

**สถาปัตยกรรมที่พบ (forensic ก่อนแตะ):** runtime ของแอป **สะอาดอยู่แล้ว** — `ปุ้มปุ้ย_ultimate_v9_modular.py` (v9.2 งาน A) ไม่ฝัง `golden_snapshot.MASTER` ; โหลดผ่าน `load_master()` (master_companies.json ของผู้ใช้) ; ถ้าไม่มี/เป็น stub → รัน `{}` ว่าง (identity = "ไม่มี master ตรวจไม่ได้") ; `master_companies.json` ถูก EXCLUDE จากแพ็กเกจ (make_release). ดังนั้น ฉี อัน ใน `golden_snapshot.MASTER` = fixture ของ golden oracle เท่านั้น **ไม่กระทบงานตรวจจริงของผู้ใช้**.

**การตัดสินใจ (ทำไม rebaseline ได้):** (1) เจ้าของสั่ง = approval. (2) empty-master golden = พฤติกรรม default จริงที่ ship (ผู้ใช้รันได้ทันทีโดยไม่มีบริษัท) → เป็นตัวแทนที่ถูกต้องกว่า golden เดิมที่ทดสอบสถานะที่ไม่เคย ship. (3) master-matching code path ยังถูกคุมโดย unit tests (test_match_guard/test_report_consistency/test_report_summary_fixes/test_rules_coverage/test_stub_marker — นิยาม fixture เอง ไม่พึ่ง MASTER กลาง).

**การเปลี่ยน:** `golden_snapshot.MASTER = {}` (ลบ entry ฉี อัน) → regen `baseline.json` ด้วย `golden_master.py`.

**Delta (ตรวจ forensic):** CMP006 50→0 (ฉี อัน ไม่มี master เทียบ → name mismatch หายเป็นธรรมชาติ) · issue รวม 615→565 (−50 พอดี) · บิล 1056 คงเดิม · **VAT/วันที่/รายการ/typo/เอกสาร ไม่ขยับเลย** (engine path อื่นไม่แตะ master) = delta สะอาดตรงคาด.

**ผลกระทบ test (ให้ local fixture):** ตัวที่ import `golden_snapshot.MASTER` + คาดหวัง ฉี อัน → นิยาม fixture ฉี อัน ของตัวเอง: `test_report_consistency`/`test_report_summary_fixes`/`test_rules_coverage`/`test_cmp004_notepad_visibility`/`test_stub_marker`. หมายเหตุ stub_marker เคส 3: `_is_real_master` ชั้น 2 (legacy heuristic) เทียบ `golden_snapshot.MASTER` ว่าง → `set(keys)==set()` เท็จ → stub marker-less ถูกตีเป็น "ของจริง" (True) ; marker ชั้น 1 = เกราะหลัก, golden ว่าง = ไม่มี stub marker-less ใหม่เกิดขึ้น → ยอมรับได้. `test_unit_detection_ext` [4b] ปรับข้อมูลเป็น same-family cross-script (เมตร+m) ให้ตรง ADR-091 (เดิมคาดหวังพฤติกรรมก่อน ADR-091 — pre-existing ไม่เกี่ยวการลบ master). หมายเหตุ: `test_cmp004`/`test_unit_detection_ext` ไม่อยู่ใน `run_ci.sh` (test เสริม/legacy ; CI ใช้ `test_unit_lang_note`/`test_super_ultra_viewer`/`test_honesty_per_bill`).

**พื้นผิว hash sync (test_golden_single_source):** d0330308 → `RETIRED_PREFIXES` · operational surfaces (run_ci.sh/Makefile/ci.yml/CLAUDE.md/MAINTENANCE.md/QUICKSTART/_SESSION_HANDOFF/.vscode×2/DECISIONS banner/CERTIFICATION) → 9aded0ad · GOLDEN.md เพิ่มแถว current 9aded0ad + ลด d0330308 เป็นปลดระวาง. `make_release`/`regression_full`/`verify_golden`/`golden_master` อ่าน `baseline._sha256` dynamic → ใช้ 9aded0ad อัตโนมัติ (ไม่ hardcode).

**ยืนยัน gate:** `baseline.json._sha256` = `9aded0ad3583f9083e45b7212a7ebc598f0217f127463e329052f593652a2e59` · `test_golden_single_source` ✅ (พื้นผิว sync) · `regression_full` = 9aded0ad (engine==agent==baseline) · `run_ci.sh /mnt/project` STRICT.

**เพิ่มเติม (พบตอนรัน CI — แก้ครบ):** (1) **fixture golden ก็ขยับ** `b5c415bb` → `72cb832c` — fixture regression (`regression_full . tests/fixtures`) ใช้ `golden_snapshot.MASTER` ด้วย → master ว่าง flip `master_present` → output เปลี่ยน **แม้ fixture data ไม่มี ฉี อัน** (findings เท่าเดิม: CMP006=0, issue=1 ; เปลี่ยนเฉพาะ field master-presence). อัปเดต FIXTURE_SURFACES (Makefile/ci.yml/MAINTENANCE.md/GOLDEN.md/CLAUDE.md/_SESSION_HANDOFF/DECISIONS banner) → 72cb832c ; `b5c415bb` → `RETIRED_FIXTURE_PREFIXES`. (2) **coverage gate** rules_engine branch ตก 84% (<85%) เพราะ `test_rules_coverage` (ใน coverage_gate TESTS) ขับ branch master-comparison ผ่าน `MASTER.get('ฉี อัน คอนสตรัคชั่น')` (=None เมื่อ master ว่าง) → ให้ local fixture ฉี อัน → branch กลับมา 85.3% ✅ (line 93.9%).

**ไฟล์ที่แก้:** `golden_snapshot.py` (MASTER={}), `baseline.json` + `tests/fixtures/baseline_fixture.json` (regen), `test_golden_single_source.py` (RETIRED +d0330308 corpus / +b5c415bb fixture), `GOLDEN.md`/`INVARIANTS/DECISIONS.md`/`run_ci.sh`/`Makefile`/`.github/workflows/ci.yml`/`CLAUDE.md`/`MAINTENANCE.md`/`QUICKSTART_VSCODE_TH.md`/`_SESSION_HANDOFF.md`/`CERTIFICATION_FINAL_TH.md`/`.vscode/tasks.json`/`.vscode/launch.json` (hash corpus→9aded0ad + fixture→72cb832c), 6 test (local fixtures: rules_coverage/report_consistency/report_summary_fixes/cmp004/stub_marker/unit_detection_ext). golden corpus `d0330308…` → `9aded0ad3583f9083e45b7212a7ebc598f0217f127463e329052f593652a2e59` · fixture `b5c415bb…` → `72cb832c9b667e796b86a78ec5e1b0556c9f19b50d15d7756df1cbd0a58e1f0a`. สำรอง: `INVARIANTS/baseline_backups/{baseline_d0330308_pre_master_delete_20260626.json, golden_snapshot_d0330308.py.bak, baseline_fixture_b5c415bb_pre_master_delete.json}`.

---

### ADR-103 — PERF (golden-neutral): กฎ cross-bill เดิม O(n²) ในจำนวนบิลรวม → ใส่ดัชนี tax_id/file = O(n) (รัน 5,000 บริษัทก้อนเดียวได้)
**วันที่:** 2026-06-26 · **สถานะ:** ACCEPTED, IMPLEMENTED · **สั่งโดย:** Tor ("แก้ไขทุกอย่าง — ตรวจทั้งประเทศ 4-5 พันบริษัท ; ยึดกฎที่เปิดอยู่เท่านั้น") · **golden คงที่ `9aded0ad`** (พิสูจน์ engine==agent==baseline)

**บริบท/การวัด:** วัด scaling จริงด้วย corpus จำลอง (replicate ชื่อ unique, ไม่ dedup): 1,056 บิล=20.6s · 4,224=95.8s · 8,448=**359.5s** — บิล 2 เท่า (4,224→8,448) → เวลา **3.75 เท่า = super-linear (exponent ~1.4)**. extrapolate 5,000 บริษัท (~35,000 บิล) = **~30-90 นาทีถ้ารันก้อนเดียว** และโตแบบกำลังสอง (10,000 บริษัท = 2-6 ชม.).

**ต้นตอ (forensic):** กฎเทียบข้ามบิลที่ **enabled** วน `for ob in all_bills` **ทุกใบ** แม้ filter ตาม tax_id/file ภายใน — loop ยัง scan ทั้งหมดต่อบิล = O(n²) ในจำนวนบิลรวม:
- `r_tax008` (TAX008, enabled) — เลขภาษีเดียวชื่อต่าง: scan ทั้งหมดหา same-tax
- `r_doc003` (DOC003, enabled) — IV ซ้ำในไฟล์: scan ทั้งหมดหา same-file
- `r_iv001` (IV001, enabled) — IV prefix ในไฟล์: scan ทั้งหมดหา same-file+vendor
- `r_doc001` (DOC001, enabled) — guard 2-signal: scan ทั้งหมดหา same-file (รันเฉพาะตอนจะ flag)
- `r_br003` (BR003) — **`enabled=False` → ข้าม** (ตามคำสั่ง "ยึดกฎที่เปิด")

**Fix (golden-neutral):** สร้างดัชนีข้ามใบครั้งเดียวต่อ batch (cache ตาม fingerprint `(id,len,id หัว,id ท้าย)`): `xbill_tax_index` (กลุ่มตาม `clean_tax_id`) + `xbill_file_index` (กลุ่มตาม `file`) — ใส่ใน `ctx` ที่ `run_rules`. แต่ละกฎเดิน **เฉพาะกลุ่มเดียวกัน** (`index.get(key, all_bills)`) แทน scan ทั้งหมด → O(n) รวม. **กลุ่มเรียงตามลำดับ all_bills เดิม (append ตามลำดับ) + ตัวกรองเดิมคงไว้ (ซ้ำซ้อนแต่ไม่อันตราย)** → กฎเห็นบิลลำดับเดิมเป๊ะ → ผลตรวจไม่เปลี่ยน. ยืนยัน `filepath==file` ทุกบิล (1056/1056) → file_index ใช้ได้กับ DOC001 (ที่ใช้ `filepath or file`).

**ผลหลังแก้ (วัดจริง):** 1,056=12.0s · 4,224=49.5s · 8,448=**114.9s** — **8x เร็วขึ้น 3.1 เท่า** ; exponent **~1.4 → ~1.09 (เกือบเชิงเส้น)** ; extrapolate 5,000 บริษัท = **~30-90 นาที → ~9-10 นาที**. RAM ไม่เปลี่ยน (~1.4GB ที่ 35,000 บิล — มาจากถือบิลในหน่วยความจำ ไม่เกี่ยวดัชนี).

**ผลกระทบ golden:** **ไม่มี** — `regression_full . /mnt/project` = engine==agent==baseline==`9aded0ad` (ผลตรวจเหมือนเดิมทุกใบ). fix นี้เปลี่ยน "ลำดับการวน" ไม่เปลี่ยน "ผลลัพธ์".

**กันถอยหลัง:** เพิ่ม canary ใน `test_perf_budget.py` (อยู่ใน run_ci.sh แล้ว) — รัน `run_rules` บนบิล distinct N + 2N วัด **ratio** (ไม่ขึ้นกับความเร็วเครื่อง): เชิงเส้น≈2 · O(n²)≈4 ; assert <3.2. ถ้าใครถอดดัชนี (กลับเป็น scan) → ratio พุ่ง → CI แดง. วัดได้ ratio=1.96 ✅.

**หมายเหตุ scope:** O(n²) นี้กัดเฉพาะ **รันก้อนเดียวขนาดใหญ่** ; ถ้าแบ่ง batch เล็ก (รายบริษัท/รายวัน) ไม่เคยกระทบ. fix นี้ทำให้ทั้งสองโหมดเร็ว/เชิงเส้น.

**ไฟล์ที่แก้:** `rules_engine.py` (เพิ่ม `_xbill_indexes` cache + ใส่ใน ctx), `rules_engine_rules_c.py` (TAX008/DOC003 ใช้ดัชนี), `rules_engine_rules_a.py` (IV001/DOC001 ใช้ดัชนี), `test_perf_budget.py` (cross-bill canary). golden `9aded0ad3583f9083e45b7212a7ebc598f0217f127463e329052f593652a2e59` (ไม่เปลี่ยน).

---

## ADR-104 — [P1] ตรวจ "หน่วยสินค้าปนภาษาไทย+อังกฤษ" ราย **ไฟล์** (ไม่ใช่รวมข้ามไฟล์ระดับบริษัท) — golden-neutral

**บริบท (เจ้าของแจ้ง):** รายงาน Notepad/สรุปบริษัท ขึ้นหมายเหตุ "หน่วยสินค้า มีทั้งภาษาไทยและภาษาอังกฤษ" กับบริษัท **ฉี อัน** แต่ (ก) ไม่บอกว่าไฟล์ไหน (ข) เป็น false positive — บริษัทรับใบกำกับจากผู้ขายหลายเจ้า ผู้ขาย A ออกหน่วยเป็น `m` ผู้ขาย B ออกเป็น `เมตร` (family เดียวกัน แต่**คนละไฟล์**) บริษัทคุมไม่ได้ และแต่ละใบสคริปต์เดียวสม่ำเสมอ.

**Forensic (corpus จริง 148 ไฟล์):** ฉี อัน → th-units `{คิว,ท่อน,เมตร}` en-units `{PCS,m}`. ตรวจรายไฟล์: KNT_69_012=PCS เท่านั้น · SEE/SEI_69_012=m เท่านั้น · KRR/KTV/SHS/TKH_*=เมตร เท่านั้น → **ไม่มีไฟล์เดียวของ ฉี อัน ที่ปนสคริปต์**. การ "ปน" เกิดจาก aggregate ข้ามไฟล์ผู้ขายล้วนๆ.

**ตัดสิน:** ย้ายเกณฑ์ "ปนภาษา" จากระดับ **บริษัท** → ระดับ **ไฟล์เดียว (ใบกำกับเดียว)**:
- `company_unit_notes()` (report-layer, ใช้ใน super_ultra_viewer + Notepad gate): flag เฉพาะเมื่อ family เดียวกันปรากฏทั้งสคริปต์ไทย+อังกฤษ **ในไฟล์เดียวกัน** (group by `b['file']`).
- `agents/notepad_report.py::_render_unit_consistency` (2): รายงานราย **ไฟล์** ด้วย `detect_file_unit_language_mix()` — บอกชื่อไฟล์ + คู่หน่วยที่ปน.

**ผลกระทบ golden:** **ไม่มี** (report-layer ไม่ถูกเรียกโดย rule engine). `regression_full` = engine==agent==baseline==`9aded0ad` คงเดิมหลังแก้ P1. ฉี อัน → `company_unit_notes=[]`. ล็อก `test_unit_lang_note.py` (เคส [A]-[D] เป็นบิลเดี่ยว=ไฟล์เดียว) ผ่านครบ — พฤติกรรม "หน่วยเดียวกัน 2 สคริปต์ในใบเดียว → flag" คงเดิมเป๊ะ.

**ไฟล์:** `unit_detection_ext.py` (`company_unit_notes`), `agents/notepad_report.py`.

---

## ADR-105 — [P2] หน่วยข้อมูลสกปรก: ตัดอักขระความกว้างศูนย์ (ZWNJ) + กรองหัวคอลัมน์ "Unit" หลุด + แก้คำที่สื่อผิด — golden-moving

**บริบท (เจ้าของแจ้ง):** หมายเหตุบอก "ดึงหน่วยสินค้ามาไม่ครบ" สื่อว่า **ระบบเราพาร์สพลาด**.

**Forensic:** เปิด `TOR_67_08.xlsx` ดิบ — รายการ ผ้า/ซิป มี จำนวน/ราคา/ยอด แต่**ต้นฉบับไม่มีคอลัมน์หน่วยเลย** (เซลล์ว่างจริง) → **ไม่ใช่พาร์สพลาด**. คำเดิมจึงผิดข้อเท็จจริง. นอกจากนี้พบบั๊กข้อมูลจริง 2 อย่าง: (1) ค่าหน่วย `'\u200cUnit'` = **หัวคอลัมน์ "Unit" หลุดเข้าเป็นค่าหน่วย** (ZWNJ นำหน้า) ใน STC_69_0512 (4) + TSH_69_0514 (5) ; (2) ZWNJ ฝังในหน่วย เช่น `'Set\u200c'` ทำให้ `Set‌`≠`Set`.

**ตัดสิน:**
- `_norm()`: ตัด ZWSP/ZWNJ/ZWJ/BOM (`\u200b\u200c\u200d\ufeff`) + แปลง NBSP→space ก่อน collapse.
- เพิ่ม `_is_real_unit()`: ค่าที่ normalize แล้วเท่ากับ `{unit,units,หน่วย,หน่วยนับ}` = หัวคอลัมน์หลุด → ถือว่า "ไม่มีหน่วยจริง". ใช้ใน summarize/file-mix/company-mix/typos/missing-unit.
- แก้คำ `detect_missing_units_in_bill`: "ไม่มีหน่วยสินค้า (ดึงมาไม่ครบ/ช่องหน่วยว่าง)" → "ไม่มีหน่วยสินค้า (ช่องหน่วยว่างในต้นฉบับ)" (ตรงข้อเท็จจริง ไม่โทษระบบ).

**ผลกระทบ golden:** **ขยับ** — header 'Unit' 9 เซลล์ (STC 4 + TSH 5) เดิมถูกนับว่า "มีหน่วย" ตอนนี้เป็นหน่วยขาด → **ITM019 +9** (intra-bill เพราะใบเหล่านั้นมี pcs/m จริงด้วย) ด้วยคำใหม่. ไม่มีการลบ/เปลี่ยน flag เดิมใดๆ (typo/หน่วยอื่นไม่ขยับ).

**ไฟล์:** `unit_detection_ext.py`.

---

## ADR-106 — [P3] เพิ่มกฎ **ITM020** "ทั้งบิลไม่มีหน่วยสินค้า" (เจ้าของอนุมัติ) — golden-moving

**บริบท (เจ้าของสั่ง):** "บางรายการ มีรายการสินค้า ไม่มีหน่วยสินค้า ระบบต้องบอกเรา" — อนุมัติเพิ่มกฎ.

**ช่องว่างเดิม:** `ITM019` (ข) จับหน่วยขาดเฉพาะ **intra-bill** (ใบที่รายการอื่นมีหน่วย → มีตัวเทียบ). ใบที่ **ทุกรายการไม่มีหน่วย** (เช่น TOR_67_08 ทั้งใบ) `detect_missing_units_in_bill` คืน `[]` (has_unit=False) → engine เงียบ. เดิมจงใจข้ามเพื่อกันฟ้องใบบริการทั้งใบ — เจ้าของ override.

**ตัดสิน:** เพิ่ม **ITM020** (`r_itm020` ใน `unit_detection_ext.py`, register ใน `rules_engine.py` RULES + __all__), severity=**WARNING**, category=รายการสินค้า, enabled=True. เกณฑ์: มีรายการคิดเงิน (`_is_charged`) แต่ **ไม่มีรายการคิดเงินใดมีหน่วยจริงเลย** → สรุปราย **บิล** (หัวเดียว + รายการย่อ cap 5 กันท่วม เช่น 107 รายการ). คำ "ช่องหน่วยว่างในต้นฉบับ" (สอดคล้อง ADR-105).

**ผลกระทบ golden:** **ขยับ** — **ITM020 +52** (TOR_67_08.xlsx 50 ใบ + TOR_69_05.xlsx 2 ใบ — ใบที่ทั้งใบไม่มีหน่วย). ไม่ทับ ITM019 (mutually exclusive ด้วยเงื่อนไข "ไม่มีหน่วยจริงเลย").

**delta รวม ADR-105+106:** ITM020 +52, ITM019 +9, **ลบ 0**, โค้ดอื่นทั้งหมด (CMP/TAX/VAT/DT/DOC/IV/ADDR/ITM อื่น/typo/dup/iv_seq/iv_date) **ไม่ขยับ**. FP=0 (ตรวจรายการที่ยิงด้วยมือ: source ว่างจริง/header หลุดจริง).

**rebaseline:** `baseline.json` ใหม่ `31013a313fb3c59b06041736975d3bc230b5a2168b1cf31569866f10da852622`. fixture **ไม่ขยับ** (`72cb832c` — fixture สังเคราะห์ไม่มีเคส whole-bill-no-unit/header) → FIXTURE_SURFACES/RETIRED_FIXTURE_PREFIXES ไม่แตะ. อัปเดต operational surfaces (.vscode×2/CLAUDE/MAINTENANCE/Makefile/QUICKSTART/_SESSION_HANDOFF/run_ci.sh/ci.yml/DECISIONS banner → 31013a31 ; README/version_gate/orchestrator/constraints ใช้ neutral ref) · เพิ่ม `9aded0ad` ใน RETIRED_PREFIXES · GOLDEN.md current=31013a31 + ledger 9aded0ad · เพิ่ม `test_unit_missing_rules.py` ล็อก ITM020/ZWNJ/header (golden-fixture-independent). backup baseline เดิม → `INVARIANTS/baseline_backups/`.


---

## ADR-107 — [P4] กัน ITM001 ฟ้องปลอม "V×V≠V" บนใบเหมารวม/บริการ (parser ไม่เดา qty/price) — golden-neutral

**บริบท (เจ้าของแนบรายงาน):** ITM001 ขึ้นยาวเป็นพรืด ทุกบรรทัด `V×V=V² แต่=V` เช่น
`70560.75×70560.75=4,978,819,440 แต่=70560.75` — ถามว่าตรวจหรือยังว่าผิดยังไง.

**Forensic:** ทุกบรรทัด = **qty == price == amount** (ค่าเดียวกัน) → เป็นไปไม่ได้จริง
(amount = amount² ได้เฉพาะ amount ≤ 1). ค่าที่แนบ (70560.75/218691.59/…) **ไม่มีในไฟล์ corpus
ใดเลย** (ค้นทุกเซลล์ดิบ 148 ไฟล์) และโค้ดปัจจุบันฟ้อง ITM001 = **0 ใบ** บนทั้ง corpus → รายงานที่
แนบมาจากรันเก่า/ไฟล์นอกชุด **แต่บั๊กต้นเหตุยังอยู่ในโค้ดจริง**.

**Root cause:** `parser_p0a._dic_pick_qty_price` มี fallback ที่ **คืน qty/price เสมอ** (เดา
min/max span) แม้ไม่มีคู่ใด qty×price≈amount validate เลย → ใบที่มีแต่ช่อง "ยอด" (เหมารวม/บริการ/
ค่าแรง) หรือ ราคา/หน่วย==ยอด (เพราะ qty=1) ถูกคว้าคอลัมน์ที่ค่า=ยอด มาเป็นทั้ง qty และ price →
qty=price=amount → ITM001 ฟ้องปลอม (และ subtotal recompute เพี้ยน). flood guard ราย "ใบ"
(≥5 รายการ/ใบ) ไม่จับเพราะใบพวกนี้มี 1 รายการ → ฟ้องทีละใบยาวเป็นพรืด.

**พิสูจน์ golden-safe:** instrument `_dic_pick_qty_price` บน corpus → validated 1006 ครั้ง,
**fallback 0 ครั้ง** → แก้ fallback ไม่กระทบ corpus. และมีรายการ qty==price==amount ใน corpus = 0.

**ตัดสิน (สองชั้น):**
- (A) parser: ถ้าไม่มีคู่ qty/price validate **แม้แต่แถวเดียว** (best_ok≤0 และ dbest_ok≤0) →
  คืน `(None, None)` ไม่เดา → qty/price ว่าง → กฎที่อิง qty×price ข้ามเอง (ถูกต้อง: ใบไม่มี
  breakdown ไม่ควรถูกฟ้องคำนวณผิด). คง fallback เดิมไว้สำหรับ partial-validate (column-swap/
  ส่วนลดบางส่วน ที่ best_ok>0).
- (B) rule (defense-in-depth): `r_itm001` ข้ามรายการที่ qty==price==amount (>1) — artifact
  เสมอ ไม่ใช่ error.

**ผลกระทบ golden:** **ไม่ขยับ** — `regression_full . corpus` = engine==agent==baseline==`31013a31`
คงเดิมหลังแก้ทั้งสองชั้น (ยืนยันแล้ว). ไม่ต้อง rebaseline.

**ตรึง:** `test_itm001_lumpsum.py` (parser → None เมื่อ validate ไม่ผ่าน / ยังเลือก qty/price
ใบปกติ / r_itm001 ข้าม artifact / ยังจับ qty×price≠amount จริง) เพิ่มใน `run_ci.sh` [4b4].

**หมายเหตุ:** ค่าในรายงานที่แนบไม่อยู่ใน corpus → ยังยืนยัน end-to-end บนไฟล์จริงของเจ้าของไม่ได้
โดยตรง แต่ root cause + fix ตรงกับ pattern เป๊ะ (qty=price=amount) และ unit-test reproduce
อาการ + พิสูจน์ fix. ถ้าเจ้าของมีไฟล์ที่ยังฟ้อง ส่งมาเพิ่ม จะ verify end-to-end + เพิ่ม fixture ได้.

**ไฟล์:** `parser_p0a.py` (`_dic_pick_qty_price`), `rules_engine_rules_a.py` (`r_itm001`).

---

## ADR-108 — [UX] ยุบ ITM020 "ทั้งบิลไม่มีหน่วยสินค้า" เป็นสรุปต่อไฟล์ (ไม่ร่ายทีละบิล) — advisory, golden-neutral

**บริบท (เจ้าของแย้ง):** บริษัท อีแอ่น 2019 (ไฟล์ TOR) มี 50 บิลที่ "ทั้งบิลไม่มีหน่วยสินค้า"
รายงาน (company_summary + vendor_report) พ่นทีละบิล 50 บรรทัด — แต่ละบรรทัดยาว
("วันที่ DD.MM.YYYY ทั้งบิลไม่มีหน่วยสินค้า — N รายการ: #1 ผ้า, #2 ซิป …") ดูเหมือนเครื่อง
ดัมพ์ ไม่ใช่ภาษาคน. ต้องการ "สรุปสั้นเป็นคำพูดเข้าใจง่าย" — ยกเว้น typo รายการสินค้าจริง
ที่ต้องชี้ทีละตัว.

**ตัดสิน:** ในชั้น render ทั้งสองรายงาน แยก ITM020 ออกจาก typo รายตัว:
- ITM020 (ทั้งบิลไม่มีหน่วย — เกิดซ้ำหลายสิบบิล/ไฟล์) → **ยุบเป็น 1 บรรทัด/ไฟล์** นับจำนวนบิล:
  `ไฟล์ TOR: 50 บิลไม่มีหน่วยสินค้าทั้งบิล (ช่องหน่วยว่างในต้นฉบับ)`.
- typo รายการสินค้าจริง (ITM004/005/010/011/019 มี seq) → **คงชี้ทีละตัว** (ผู้ใช้เปิดไปแก้
  ถูกจุด) — ตรงเจตนา "นอกจากรายการสินค้า".

**ไฟล์ที่แก้ (report-layer):**
- `super_ultra_viewer.py::_pinpoint_field` (F_ITEM): แยกนับ ITM020 ต่อ prefix → append บรรทัดสรุป.
- `agents/vendor_report_ext.py::_item_field_text`: เพิ่ม import `_file_prefix` + แยกนับ ITM020
  ต่อไฟล์ → append บรรทัดสรุป.

**ผลลัพธ์จริง (corpus):** อีแอ่น 2019 — company_summary จาก 50 บรรทัด (~6,200 อักษร) เหลือ
1 บรรทัด ; vendor_report 10.อีแอ่น2019.txt เหลือ 605 อักษรทั้งไฟล์. company_summary.txt
รวมจาก 60,673 → 54,427 อักษร.

**ผลกระทบ golden:** **ไม่ขยับ** — เป็นชั้นแสดงผล (engine issue/ITM020 detail คงเดิม).
`regression_full . corpus` = `31013a31` คงเดิม. locked report tests (super_ultra_viewer /
report_c1_c2 / realcases_v9_2 / vendor_report) ผ่านครบ.

**ตรึง:** `test_itm020_collapse.py` (A: _pinpoint_field ยุบ ITM020 ต่อไฟล์ + typo คงรายตัว ;
B: vendor_report _item_field_text ยุบ) เพิ่มใน `run_ci.sh` [4b5].

**หมายเหตุ:** บรรทัด `หมายเหตุ : หน่วยสินค้าบางรายการไม่มีหน่วย (… N รายการ)` (company_unit_notes
นับ "รายการ") คงไว้ — เป็นมุมมองระดับ item ส่วนสรุป ITM020 เป็นระดับ "บิล" ; ทั้งคู่ 1 บรรทัด.
