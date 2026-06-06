# P3 FOLLOW-UP — สิ่งที่ทำรอบนี้ + งานที่เลื่อน (พร้อมเหตุผลและสูตรย้ายอย่างปลอดภัย)

อัปเดต: 2026-06 · รอบ "P1/P2 hardening + CI + fixture"
หลักการเดิม: **ไม่แตะ business logic / golden hash**, แก้แบบ incremental, มี regression guard ทุกขั้น.

---

## 0. สรุปผู้บริหาร (30 วินาที)

รอบนี้ปิดงาน **P1 (สูง) + P2 (กลาง)** ที่ REBUILD_STATUS ข้อ 8 แนะนำไว้ และ **ทำให้พิสูจน์อัตโนมัติได้ใน CI**.
งาน **P3** (เสี่ยงสูง/ประโยชน์ต่ำตอนนี้) เลื่อนออกอย่างมีเหตุผล พร้อมสูตรย้ายให้ทำทีหลังอย่างปลอดภัย.

| การทดสอบ | ผล |
|---|---|
| `smoke_test.py` (รวม version gate ใหม่) | ✅ 26/26 + gate |
| `test_pinned_logic.py` (ตรึง 3 จุด APPROX) | ✅ 44/44 |
| `test_mesh_contract.py` (สัญญา Tier-1) | ✅ 16/16 |
| `test_agents.py . tests/fixtures` (fixture) | ✅ 37/37 |
| `regression_full.py . tests/fixtures …` (fixture) | ✅ `d8bcde85…` (engine==agent) |
| `regression_full.py . <81 ไฟล์จริง>` | ✅ `ec61907f…` (engine==agent==baseline, **ไม่เปลี่ยนหลัง P2-B**) |
| `test_agents.py . <81 ไฟล์จริง>` | ✅ 38/38 |

---

## 1. สิ่งที่ทำรอบนี้

### P1-A — ตรึง (pin) 3 จุดที่กู้คืนแบบ ⚠ APPROX  → `test_pinned_logic.py`
ฝัง "ค่าที่ตรวจวัดจริง" เป็น literal (ไม่คำนวณซ้ำจากโมดูล) เพื่อให้ **การแก้น้ำหนัก/เกณฑ์/รูปแบบเงียบ ๆ = ล้มทันที**:
- `puopuy_units._vat_tolerance` — **RESTORED** `0.5 + |subtotal|/100000` (OBJ-1A); ทดสอบ None/abs/comma/ขยะ, บิลใหญ่, ชนิด `Decimal`
- `analytics.compute_bill_confidence` — น้ำหนักหักคะแนนทุกตัว + คะแนน/tier ของบิลตัวอย่างแต่ละแบบ + clamp [0,1] + เส้น exception→LOW
- `analytics.summarize_by_company` / `_period_label` — รูปแบบ `period` (พ.ศ. 2 หลัก.เดือน), เรียง/ไม่ซ้ำ/`'-'`, ยอดเป็นตัวเลขเสมอ

> ไม่ต้องใช้ข้อมูลจริง → รันใน CI ได้. ถ้าเจอต้นฉบับแล้วแก้: ต้องแก้ค่าที่ตรึง + สร้าง baseline ใหม่ + รัน regression.

### P1-B — เวอร์ชัน mismatch = exit ≠ 0  → `version_gate.py`
แทน "พิมพ์ ⚠️ แล้วรันต่อ" เดิม ด้วยด่านที่ **หยุดจริงเมื่อเพี้ยนระดับอันตราย**:
- source of truth เดียว = `config._LOCKED`
- นโยบายเป็นชั้น: lib หัวใจ (pandas/xlrd/openpyxl/rapidfuzz) major/minor/ขาด = **FAIL**; pythainlp major = FAIL ที่เหลือ WARN; matplotlib/plotly/tqdm = WARN เท่านั้น (ไม่กระทบ golden hash — พิสูจน์เชิงประจักษ์)
- `--strict` = ต้องตรงเป๊ะทุกตัว (ใช้ release/audit) · escape hatch `PUOPUY_ALLOW_VERSION_MISMATCH=1`
- เสียบใน bootstrap ของโมดูลหลัก (หยุดตั้งแต่ import ถ้าเพี้ยนจริง) + เพิ่ม section ใน `smoke_test.py`

### P2-A — สัญญา "ผู้ผลิต Tier-1 ครบ" ของ mesh  → `mesh_contract.py` (+ crosscheck/confidence)
แก้ความเสี่ยง "Tier-2 เพี้ยนเงียบเมื่อ Tier-1 isolated-fail":
- `verify_producers(results, mesh, expected)` ใช้ทั้ง `ctx.results[].status` (รัน/ล้ม/ข้าม) และ `mesh.agents_seen()` (โพสต์หรือยัง)
- จำแนก missing/errored (= ละเมิด), skipped (เตือน), silent (รัน ok แต่ 0 finding = ปกติได้)
- `CrossCheckAgent` ยกธง `MESH-CONTRACT` (ERROR, ระดับ pipeline) **ครั้งเดียว** เมื่อพบละเมิด; `ConfidenceAgent` บันทึกสุขภาพในสรุป (ไม่ออกธงซ้ำ) เพื่อให้ตีความคะแนนได้
- **ไม่เพิ่ม agent ใหม่** (ค่า `agents_expected=9` ของ super ไม่เปลี่ยน) · เป็น finding/summary ล้วน → ไม่กระทบ golden hash

### P2-B — แคบ `except Exception: pass` ใน hot-path ของ `parser.py`
แยก "fallback ที่ None/ข้ามถูกต้อง" ออกจาก "error ที่ควร log file/sheet":
- filename range-parse (`int(...)`) → `except (ValueError, TypeError)`
- VAT-rate cell coercion ใน double-loop → `except (ValueError, TypeError, OverflowError)`
- error ชนิด "ไม่คาด" จะลอยขึ้นไปให้ขอบเขตชีตที่มีอยู่แล้ว (`SYS001` พร้อม file/sheet) บันทึก แทนการกลืนเงียบ
- **พิสูจน์:** `regression_full` บนข้อมูลจริง 81 ไฟล์ ยังได้ `ec61907f…` เป๊ะ (พฤติกรรมไม่เปลี่ยน)

### CRITICAL — แก้วิกฤตเพิ่ม (รอบ "ทำการแก้ไขวิกฤตโค้ดเรา")

**C1 — ผลตรวจ "ขยับตามเวลา" (reproducibility time-bomb)**
- *Current risk:* กฎ `r_dt002` (future date) / `r_dt003` (year sanity) เทียบกับ `datetime.now()` ตรง ๆ → ผลตรวจ + golden hash ขึ้นกับ "วันที่รัน". บิลปลายปีจะพลิก future→past เมื่อข้ามวัน/ข้ามปี → hash drift เงียบ. (ตรงกับ Predictability ที่ scorecard ให้คะแนนต่ำ)
- *Root cause:* นาฬิกาฝังในกฎ (ไม่ inject) + พบบั๊กแฝง: `r_dt002` อ้าง `timezone` ที่ไม่ได้ import → `except` กลืน → เดิมใช้เวลา server-local แทนเวลาไทยอย่างเงียบ ๆ
- *Long-term impact:* รัน regression ปีหน้าได้ hash ต่าง โดยไม่มีใครรู้ว่า "เพราะเวลา" หรือ "เพราะโค้ดเปลี่ยน" → audit พิสูจน์ย้อนหลังไม่ได้
- *Fix:* เพิ่ม `config.audit_today()` (default = วันนี้เวลาไทย; override ด้วย env `PUOPUY_AUDIT_DATE=YYYY-MM-DD`) แล้วให้ `r_dt002/r_dt003` เรียกแทน `datetime.now()`; แก้บั๊ก timezone แฝงไปในตัว. ตั้ง `PUOPUY_AUDIT_DATE` ใน CI → ผลตรวจนิ่งตามเวลา
- *Migration risk:* ต่ำมาก — default = พฤติกรรมเดิม; **regression บนข้อมูลจริงยังได้ `ec61907f…` เป๊ะ** (วันที่ชุดข้อมูล ≤ CE 2026-05 ห่างจาก "วันนี้" → กฎไม่ติดทั้งสองทาง). ตรึงพฤติกรรมไว้ใน `test_pinned_logic.py` แล้ว
- *Priority:* **สูง** (กระทบ reproducibility ซึ่งเป็นแกนของระบบ audit)

**C2 — `input()` ค้าง/พังในโหมดอัตโนมัติ**
- *Current risk:* โหมดรายงานเต็ม (non-LEAN) เรียก `input('ใช้ Tier 2 …')` ตรง ๆ → รันใน CI/cron/subprocess/redirect จะ **ค้างถาวร** หรือพังด้วย `EOFError`
- *Root cause:* prompt โต้ตอบในเส้นรันหลัก โดยไม่เช็ค TTY/ไม่มี fallback
- *Long-term impact:* งาน batch โหมดเต็มแขวน/ล้มแบบเดาไม่ถูก
- *Fix:* ทำให้ปลอดภัย — เช็ค env `PUOPUY_ONLINE_VERIFY` ก่อน, ถ้าไม่มี TTY → ออฟไลน์อัตโนมัติ, มี TTY แต่กด EOF → ออฟไลน์ (ไม่พัง)
- *Migration risk:* ต่ำ — interactive เดิมยังถามเหมือนเดิม; เปลี่ยนเฉพาะกรณีไม่มีคนตอบ. อยู่นอกเส้น golden (golden_master ไม่เรียก main) → hash ไม่เปลี่ยน
- *Priority:* **สูง** (stability ในงานอัตโนมัติ)

> หมายเหตุการตรวจ: network calls (webverify/llm_provider) มี circuit-breaker + timeout + คืน None เมื่อออฟไลน์ (degrade graceful ไม่ crash) และอยู่ "นอกเส้น golden" → ไม่ใช่จุดวิกฤตที่ทำ hash เพี้ยน. ไม่มี mutable default args. จึงโฟกัสที่ C1/C2.

### ของใหม่ที่เพิ่ม (เครื่องมือ/โครงสร้าง)
- **fixture สังเคราะห์** `tests/fixtures/fixture_invoices.xlsx` (3 บิล, **ข้อมูลปลอมล้วน**, layout เลียนของจริง) + baseline `tests/fixtures/baseline_fixture.json` (`d8bcde85…`) → ปลดล็อก `test_agents`/`regression_full` ให้รันใน CI โดยไม่ต้องมีข้อมูลลูกค้า
- **CI** `.github/workflows/ci.yml` (รันทุก push): gate → smoke → pinned → mesh-contract → agents(fixture) → regression(fixture)
- **รันในเครื่อง:** `run_ci.sh`, `Makefile` (`make ci`)
- **lockfile:** `constraints.txt` (ตรงกับ `_LOCKED`) — `pip install -r requirements.txt -c constraints.txt`
- `.gitignore` กันไฟล์ชั่วคราว + กัน commit ข้อมูลลูกค้า (`*.xls/*.xlsx` ยกเว้น fixture)
- `regression_full.py` รับ argv[3]=baseline (เพื่อรันบน fixture) — **backward compatible**

---

## 2. งาน P3 ที่ "เลื่อน" — เหตุผล + สูตรย้ายอย่างปลอดภัย

> เกณฑ์ตัดสิน: P3 ทุกข้อ **เสี่ยง regression สูง / ประโยชน์ต่ำตอนนี้** และระบบทำงานดีอยู่แล้ว.
> การ rewrite ใหญ่ขัดกับหลักงาน (เลี่ยง rewrite ที่ไม่จำเป็น, ลดความเสี่ยง regression) จึงเลื่อน — ไม่ใช่ทิ้ง.

### P3-1 — global mutable state ใน `state.py` (จำเป็นเฉพาะถ้าจะรัน "ขนาน")
**ความเสี่ยงปัจจุบัน:** caches/audit-trail เป็น module-level object ที่หลายโมดูลเขียนร่วม → ถ้ารันหลายงานพร้อมกันใน process เดียว (threads) จะปนกัน.
**ทำไมยังไม่แก้:** ระบบรันแบบ single-process/serial (81 ไฟล์ก็พอ) และมี `reset_run_state()` + `.clear()` คง identity อยู่แล้ว → รันซ้ำในเซสชันเดียวปลอดภัย. การแปลงเป็น context object เต็มรูปแตะ call site จำนวนมาก = เสี่ยง.
**สูตรย้าย (เมื่อจะ scale ขนานจริง):**
1. ห่อ state ทั้งหมดใน class `RunState` (ฟิลด์เดิมทุกตัว) แทน module globals.
2. ส่ง `RunState` ผ่านพารามิเตอร์ (หรือ `contextvars.ContextVar` เพื่อไม่แตะลายเซ็นฟังก์ชันมาก).
3. เปลี่ยนทีละโมดูล (parser → rules → reporting) โดยรัน `regression_full` หลังแต่ละ step ให้ hash คงเดิม.
4. ทดสอบขนานด้วย `ThreadPoolExecutor` 2 งาน → ผลต้องไม่ปนกัน.

### P3-2 — แยกไฟล์ใหญ่ `parser.py`/`rules_engine.py`/`reporting.py` (>1.4k บรรทัด)
**ความเสี่ยงปัจจุบัน:** อ่าน/ดูแลยาก (ฟังก์ชันยักษ์, ไฟล์ใหญ่).
**ทำไมยังไม่แก้:** ตรงกับที่ HANDOVER/P1_P2_FIXES เดิมสรุป — layering สะอาด ไม่มี circular, ใช้เวลามาก + แตะ cross-import หลายสิบจุด (แต่ละจุด silent-break risk), ประโยชน์ต่ำเทียบความเสี่ยง.
**สูตรย้าย (incremental, ปลอดภัย):**
1. แยก "ฟังก์ชัน leaf บริสุทธิ์" ออกก่อน (ไม่พึ่ง state/ไม่ถูกพึ่งวนกลับ) ไปไฟล์ย่อย แล้ว `from x import *` กลับเข้าที่เดิม → ชื่อใน namespace เดิมครบ (gate `core_access._REQUIRED` ไม่พัง).
2. รัน `smoke` + `regression_full` หลังทุกการแยก (hash ต้องคงเดิม).
3. ทยอยทีละกลุ่มฟังก์ชัน — ห้ามแยกหลายไฟล์รวด.

### P3-3 — ย้ายตารางข้อมูลใน `config.py` (≈48KB) → JSON
**ความเสี่ยงปัจจุบัน:** ไฟล์ config ใหญ่ (ข้อมูล + โค้ดปนกัน).
**ทำไมยังไม่แก้:** ตารางหลายตัวเป็น `set`/`tuple`/regex-compiled — JSON เก็บได้แต่ `list` → ต้องแปลงชนิดกลับตอนโหลด. ถ้าพลาด (list แทน set, ลำดับเปลี่ยน) → พฤติกรรม/`golden hash` เพี้ยน. เป็น "rewrite ที่เสี่ยงเพื่อความสวยงาม" = ไม่คุ้มตอนนี้.
**สูตรย้าย (ถ้าทำ):**
1. ย้ายเฉพาะตาราง "ข้อมูลล้วน" ที่เป็น dict/list ตรงๆ (เช่น `THAI_MONTHS`, `SOURCE_TRUST`) ไป JSON ก่อน.
2. โหลดด้วย loader ที่ **คืนชนิดเดิมเป๊ะ** (`set(...)` ที่เคยเป็น set, `tuple(...)` ที่เคยเป็น tuple, `re.compile` สำหรับ pattern).
3. ห้ามย้าย `UNIT_HINT_PATTERNS`/whitelist ที่เป็น set/regex จนกว่าจะมี loader ที่พิสูจน์ชนิดแล้ว.
4. รัน `regression_full` (81 ไฟล์) ทุก step — hash ต้องคงเดิม.

---

## 3. วิธีรัน CI / regression

```bash
# ── ในเครื่อง (เร็ว, ไม่ต้องมีข้อมูลจริง) ───────────────────────────────
make ci                      # gate+smoke+pinned+mesh+agents+regression (fixture)
# หรือ
bash run_ci.sh

# ── regression เต็มบนข้อมูลจริง (ต้องมี 81 ไฟล์, hash ec61907f…) ────────
PYTHONHASHSEED=0 python3 regression_full.py . /path/to/81-files
bash run_ci.sh /path/to/81-files     # รวมขั้น regression+agents เต็ม
make regression-real DATA=/path/to/81-files

# ── เมื่อแก้ fixture โดยตั้งใจ → สร้าง baseline ใหม่ ─────────────────────
make baseline-fixture
```

> ทุกขั้นต้องตั้ง `PYTHONHASHSEED=0` (Makefile/scripts ตั้งให้แล้ว). ข้อมูลลูกค้า **ห้าม commit** — CI ใช้ fixture สังเคราะห์เท่านั้น; regression เต็มรันในเครื่องที่มีข้อมูล.

---

## 4. ของที่ "ต้องไม่เปลี่ยน" (invariants ที่ guard ไว้แล้ว)
- ผลตรวจหลักบน 81 ไฟล์: `BILLS=632 dup=1 iv_seq=26 iv_date=0 typos=34 companies=2` · hash `ec61907f…`
- ชั้น agent ไม่เปลี่ยนผลตรวจ (engine==agent)
- `agents_expected=10` ของ SuperAgent (เดิม 9 — เพิ่ม `verification` ที่รันจริงใน Tier-2 แต่ตกหล่นจาก
  `_EXPECTED`; แก้พร้อมอัปเดต `test_agents.py` ดู Decision Log §5 [P2]). ห้ามเพิ่ม/ลด agent โดยไม่อัปเดต test.
ถ้าตัวใดเปลี่ยน = ตั้งใจหรือบั๊ก — ต้องอธิบาย + สร้าง baseline ใหม่อย่างตั้งใจ.

---

## 5. Decision Log — STABILIZE & HARDEN (session 2026-06)

> หลักการ: DIAGNOSE→DECIDE→FIX→VERIFY · golden ห้ามขยับเว้นมีหลักฐาน before/after บน 81 ไฟล์อ้างอิง
> · ทุกการ defer มีเหตุผล · hash-gate ที่รันได้ใน sandbox นี้ = fixture `d8bcde85` (3 บิล) — golden 81/106
> ไฟล์จริงต้องรันบนเครื่องที่มีข้อมูล (sandbox ไม่มี `/mnt/project`).

### #1 MERGED CELLS — DIAGNOSED → NO-FIX (มีหลักฐาน) · เพิ่ม guard
- **Current risk:** ค่าวิกฤต (ยอด/VAT/รวม/เลขภาษี) อาจตกใน merged range แล้ว parser มองไม่เห็น → ยอดผิดเงียบ.
- **Diagnose (forensic):** `diagnose_merged_cells.py` รันบนไฟล์จริง 3 ไฟล์ (KRR/STC/TKH, รวม 15 บิล,
  merged 165–210 ช่วง/ไฟล์). ผล: **ไม่มีค่าวิกฤตหายเลย** — ทุกบิล reconcile (subtotal+vat=total เป๊ะ
  เช่น 173269×1.07=185397.83) + เลขภาษีถูกจับครบ. ค่าที่ scanner รุ่นแรกธง (เช่น `244474` ที่ KRR
  ชีต5 R5C19) ตรวจ cell จริงพบว่าอยู่ **เหนือ** `IV-69050092` → เป็น "เลข running หัวเอกสาร" ไม่ใช่ฟิลด์บิล
  (parser ถูกที่ไม่จับ). 20 ธงทั้งหมด = false-positive ประเภทนี้.
- **Decision:** **ไม่แตะ parser** — ไม่มีหลักฐานว่าพังบนข้อมูลที่ตรวจได้. แทนที่จะแก้แบบเดา (เสี่ยงขยับ
  golden โดยไม่จำเป็น) → ติดตั้ง **guard** `diagnose_merged_cells.py tests/real_cases` ใน run_ci.sh [3x6]
  + ci.yml (จับ regression ถ้าอนาคต parser ทำค่าหายบน real_cases).
- **Hash expectation:** **ไม่เปลี่ยน** (ไม่แตะ parser/golden path) — ยืนยัน fixture `d8bcde85` คงเดิม.
- **ค้างไว้ให้เจ้าของระบบ:** รัน `python3 diagnose_merged_cells.py <โฟลเดอร์ 106 ไฟล์จริง>` บนเครื่องที่มีข้อมูล.
  ถ้าขึ้น 🚩 (taxid หาย / recon ไม่ผ่านแบบไม่ใช่ VAT003) = เจอของจริง → ค่อยทำ merged-cell handler
  แล้ววัด golden 81 ไฟล์ before/after (justify: false-positive ลด, true-positive คงอยู่).
- **Priority:** P2 (latent — ยังไม่พบ active loss).
