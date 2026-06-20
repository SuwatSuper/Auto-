# FIX_REPORT_TH — รายงานตรวจรับ & แก้บั๊ก Kingdom Prime

> เอกสารนี้คือรายงาน **ตรวจรับ (release audit) ฉบับล่าสุดและเป็นทางการ** สำหรับการ
> รีเช็กบั๊กทั้งระบบแบบ adversarial → แก้ → ยืนยันด้วยการรันจริง รายงานเก่าในรีโป
> (RELEASE_AUDIT_REPORT_TH.md, FIX_REPORT_RECHECK_TH.md, PHASE*_*.md ฯลฯ) เก็บไว้
> เป็นประวัติเท่านั้น — ให้ยึดไฟล์นี้

วันที่: 2026-06-15 · Python 3.12.3 · เป้าหมาย Windows/3.12 · paper-only

---

## 0. วิธีตรวจ (methodology)

- ตั้ง venv สด Python 3.12 → `pip install -e ".[dev]"` (ได้ pandas 3.0.3, numpy 2.4.6,
  pydantic 2.13, pytest 9.1, mypy 2.1, ruff 0.15 — **ใหม่กว่าที่โปรเจกต์เคยพัฒนาไว้**)
- รัน 3 gate เป็น ground truth ก่อนแตะอะไร (ไม่เชื่อ report เก่า)
- Adversarial audit แบบขนาน 5 ด้าน (เงิน/Decimal · determinism+layer · exception+
  concurrency · risk rails+paper-lock+architecture · edge/time+completeness) — รันโค้ดจริงทุกด้าน
- **กฎ audit-first**: ทุกบั๊ก "รันพิสูจน์อาการก่อน" → แก้ → เพิ่ม regression test
  (fail-ก่อนแก้ / pass-หลังแก้)
- ยืนยัน runtime จริง: boot-from-zero / soak 60s / kill -TERM + reboot / watchdog

---

## 1. STEP 0 — Ground truth (ก่อนแก้)

```
$ ruff check src tests
All checks passed!

$ mypy src/
Success: no issues found in 132 source files

$ pytest
824 passed, 1 skipped, 2 warnings in 62.48s
Required test coverage of 90% reached. Total coverage: 91.17%
```

gate เขียวตั้งแต่ต้น **แต่ไม่ได้แปลว่าไม่มีบั๊ก** — งานคือหาบั๊กที่ gate มองไม่เห็น
และพบว่ามีจริง (ดูข้อ 2) รวมถึง **เทสต์ที่จับบั๊กได้แล้วถูกลบทิ้งเพื่อให้ suite เขียว**

---

## 2. ตารางบั๊กที่เจอและแก้

> ระดับ: S0 วิกฤต · S1 ร้ายแรง · S2 กลาง · S3 ต่ำ/cosmetic — แก้ครบทุกตัว

| ID | ระดับ | ที่เจอ | อาการ / root cause | การแก้ | regression test | ไฟล์ที่แก้ |
|----|------|--------|--------------------|--------|-----------------|-----------|
| KP-01 | **S1** | `agents/execution_agent.py` (live order path) | **Live double-entry**: BUY 2 ไม้ติดๆ กันยิง order จริง 2 ครั้งทั้งที่ `max_open_positions=1`. loop เป็น serial แต่ `open_positions()` lag เพราะ paper-mirror อัปเดตแบบ async → ไม้ที่ 2 อ่านค่า 0 ค้าง. **พิรุธ: เคยมีเทสต์ `test_audit_double_entry.py::test_live_double_entry_race` จับได้ แต่ source ถูกลบทิ้ง (เหลือ .pyc ใน `__pycache__`) เพื่อให้ suite เขียวแทนการแก้บั๊ก** | เพิ่ม in-flight reservation (`_inflight_entries` + grace 5s, self-heal) นับไม้ที่ routed แล้วแต่ยังไม่สะท้อนใน open count → cap ถูกต้องโดยไม่ต้องรอ mirror | **คืนเทสต์ที่ถูกลบ** `test_audit_double_entry.py` (2 เคส) | `execution_agent.py` |
| KP-02 | S2 | `agents/execution_agent.py` docstring + `agents/risk_agent.py` | docstring โฆษณา pipeline ขั้นที่ 2 = "`domain.risk.rules.evaluate()` — full gate check" **แต่โค้ดไม่เคยเรียก**. RiskAgent evaluate จริงแล้ว publish ไป `risk.v1` ที่ **ไม่มี subscriber** → verdict หายไป (dead stream) | แก้ docstring ให้ตรงความจริง (ระบุ rail ที่บังคับใช้จริง + ว่า RiskAgent เป็น advisory) + เพิ่ม `.detail` ให้ RiskAgent ให้ verdict โผล่บน dashboard ผ่าน `_agent_status` (เลิก publish ลงเหว) | ครอบโดย `test_execution_agent.py` + `test_department_agents.py` ที่ผ่าน | `execution_agent.py`, `risk_agent.py` |
| KP-03 | S2 | `agents/learning.py:_today`, `agents/extended/periodic_agents.py` (DashboardSynth) | `datetime.now()` แบบ **naive (เวลาเครื่อง)** ใช้คำนวณ "วันนี้"/midnight push แต่ treasury ยึด UTC+7 → บนเครื่องที่ไม่ใช่ Bangkok (cloud/CI) คนละวันกัน, daily counter ของ learner ไม่ reset ตรงเที่ยงคืนไทย | เพิ่ม `thai_now()` (UTC+7 fixed) ใช้ทั้ง `_today()` และ midnight push | `test_thai_time.py::test_learning_today_uses_thai_day_not_host_clock` (freeze 18:30 UTC) | `learning.py`, `periodic_agents.py` |
| KP-04 | S3 | `agents/extended/periodic_agents.py:TrailingStopBotAgent` | คำนวณ trailing-stop เป็น **float** (`peak*(1-trail/100)`) แล้วดันเข้าเป็น protective stop จริงผ่าน `Decimal(str(float))` → ผิดกฎ "เงินใช้ Decimal เท่านั้น" (sub-satang noise บนเส้นทางเงินจริง) | คำนวณด้วย Decimal ล้วน (`_dec(mark_price)` + `_trail_frac` Decimal) | `test_extended_agents.py::test_trailing_stop_pushes_exact_decimal_no_float_noise` | `periodic_agents.py`, `extended/base.py` (เพิ่ม `_dec`) |
| KP-05 | S3 | `orchestration/control.py:order_over_hard_cap` | guard เพดานเงิน-จ่ายจริง **พังกับ non-finite**: `"nan"` → `InvalidOperation` (crash), `"-Infinity"` → คืน `None` (**ผ่าน cap!**) | เพิ่ม `is_finite()` → reject non-finite ทุกตัว | `test_real_money_matrix.py::test_order_over_hard_cap_rejects_non_finite` | `control.py` |
| KP-06 | S3 | `gateway/bitkub_rest_ticker.py:extract_last_price` | `"NaN"` → raise, `"Infinity"`/`"inf"` → คืน `Decimal('Infinity')` (leak) ผิด contract ("คืน Decimal บวกหรือ None") | เพิ่ม `is_finite()` → คืน None | `test_rest_ticker.py::test_extract_non_finite_returns_none` | `bitkub_rest_ticker.py` |
| KP-07 | S3 | `orchestration/runtime.py:start` | **publish-before-subscribe**: producer (price feed) ถูก start ก่อน agent subscribe → tick แรกอาจหาย (bus in-memory ไม่ replay) | ย้าย start price feed ไป **หลังสุด** (หลัง agent subscribe ครบ) | ครอบโดย `test_paper_pipeline.py` + soak (msg/s นิ่ง) | `runtime.py` |
| KP-08 | S3 | `orchestration/runtime.py` + `supervisors/supervisor.py` | price-feed→bus bridge **ไม่มีใคร restart** (watchdog ดูแค่ agent); คลาส `Supervisor` (restart+backoff) **มีเทสต์แต่ไม่ถูก wire** (dead) | wire `Supervisor` ครอบ bridge → auto-restart+backoff | คลาสมีเทสต์อยู่แล้ว (`test_department_agents.py`); ครอบ start ด้วย full suite + soak | `runtime.py` |
| KP-09 | S3 | `domain/analytics/ta.py` | `.ta` pandas accessor เป็น **process-global** ถ้า pip `pandas_ta` ลง+import หลัง vendored stub จะ **เงียบๆ shadow** (pandas แค่ warn) → indicator เปลี่ยน impl. (latent: ยังไม่มี pandas_ta ลง) | เพิ่ม assert ว่า owner ของ `.ta` คือ `vendor_ta` ไม่งั้น raise ตอน import (fail loud) | `test_ta.py::test_ta_accessor_is_the_vendored_stub` | `ta.py` |
| KP-10 | S3 | `tests/architecture/test_layer_rules.py` | layer-purity test เดิม walk แค่ module-level → import ต้องห้ามที่ซ่อนใน function body ของ domain หลุดได้; `datetime`/`threading` ถูกอนุญาต (อยู่ใน stdlib) | เพิ่มเทสต์ walk **ทั้ง AST tree** + บัญชีต้องห้ามชัดเจน (รวม datetime/threading) สำหรับ domain | `test_layer_rules.py::test_domain_pure_even_in_nested_scopes` (เทสต์เองคือ regression) | `test_layer_rules.py` |
| KP-11 | S3 | `tests/orchestration/test_execution_agent.py` | `@pytest.mark.integration` ไม่ได้ลงทะเบียน → `PytestUnknownMarkWarning` | ลงทะเบียน marker ใน `pyproject.toml` | full suite = 0 warnings | `pyproject.toml` |
| KP-12 | S3 | test client (starlette) | `StarletteDeprecationWarning` (httpx vs httpx2) — third-party, test-only | ใส่ filter ignore พร้อมคอมเมนต์ | full suite = 0 warnings | `pyproject.toml` |
| KP-13 | S3 | `agents/treasury_agent.py:256` | คอมเมนต์ว่า "daily halt clears at **UTC** midnight" แต่จริงคือ **Thai (UTC+7)** midnight | แก้คอมเมนต์ | — (คอมเมนต์) | `treasury_agent.py` |
| KP-14 | S3 | `agents/extended/periodic_agents.py:ProfitSweeperAgent` | vault เป็น **float**, role อ้าง "stablecoin vault / real bookkeeping" ทั้งที่ **ไม่ย้ายเงินจริง** (overstated) | เปลี่ยนเป็น Decimal + อ่าน `realized_today_str` (authoritative) + wording ตรงจริง ("advisory · ไม่ย้ายเงินจริง") | ครอบโดย `test_extended_agents.py`/`test_kingdom_integration.py` | `periodic_agents.py`, `runtime_agents.py` |
| KP-15 | S3 | `domain/analytics/ta.py` docstring | docstring เขียน "wrappers over **pandas_ta**" ทั้งที่ใช้ vendored stub | แก้ docstring | — | `ta.py` |

### ข้อจำกัด/ข้อสังเกตที่ "พูดตามจริง" (verify ไม่ได้/ตั้งใจไม่แก้)

- **KP-16 (S3, บันทึกไว้ ไม่แก้):** `tests/architecture/test_execution_guard.py::test_order_markers_only_in_bitkub_rest`
  สแกน string literal (`"place-bid"` ฯลฯ) → **เลี่ยงได้ด้วยการต่อ string แบบ dynamic**.
  คงไว้เพราะ cage ถูกทดสอบเชิงพฤติกรรมจริงด้วย (live gate บล็อก mock gateway ได้) และการ
  เขียน AST-scan ที่รัดกุมกว่ามีความเสี่ยง false-positive สูง — แจ้งเป็น limitation มากกว่าแก้แบบเสี่ยง
- **เชื่อมต่อ Bitkub จริง (live REST/WS):** network egress ไป `api.bitkub.com` ถูก **บล็อกใน
  sandbox นี้ (HTTP 403 not in allowlist)** → **ยืนยันการเชื่อมราคา/บัญชีจริงไม่ได้**. แต่กลายเป็น
  resilience test ที่ดี: เมื่อ feed ต่อไม่ได้ ระบบยัง boot ได้, /api/status=200, แสดง DATA
  UNAVAILABLE, ไม่ crash (backoff). การ soak ใช้ **mock ticker server ภายในเครื่อง** ป้อนราคาจริง
  ผ่าน pipeline เดิม
- **Windows จริง:** ทดสอบบน Linux/3.12.3 (ใกล้เคียง 3.12 เป้าหมาย). โค้ด timezone ใช้ fixed-offset
  `timezone(timedelta(...))` (ไม่ใช้ `ZoneInfo`) จึง **ไม่ต้องพึ่ง tzdata** บน Windows — ยืนยันแล้วว่า
  ไม่มี `zoneinfo` ใน src/tests
- **paper-only:** บั๊ก KP-01 อยู่บนเส้นทาง live เท่านั้น (ต้องปลด 4 gate + ใส่ API key). โหมด paper
  (ดีฟอลต์) ปลอดภัยอยู่แล้ว (paper trader serial เห็น position!=None) — แต่แก้เพราะโค้ด live ต้องถูกต้อง

---

## 3. หลักฐานการรันจริง (audit-first repro)

### 3.1 พิรุธ: เทสต์ double-entry ถูกลบ (เหลือแต่ .pyc)

```
$ ls tests/orchestration/test_audit_double_entry.py        → No such file
$ ls tests/orchestration/__pycache__/test_audit_double_entry.*.pyc  → มีอยู่ (6070 bytes)
# strings ใน .pyc:
  "Two near-simultaneous live BUYs: does the gate place TWO real bids
   despite max_open_positions=1, because the paper mirror that updates the
   open-position count is asynchronous?"
  "DOUBLE ENTRY: placed " ... " real bids with max_open_positions=1"
```
→ เป็นเทสต์ที่จับ KP-01 ได้ แล้ว source ถูกลบ (ไฟล์อื่นทุกไฟล์มี .py ครบ มีแต่ไฟล์นี้ที่หาย)

### 3.2 repro บั๊ก (ก่อนแก้)

```
BUG1 double-entry: REAL_BIDS=2 (max_open_positions=1) -> DOUBLE-ENTRY BUG
BUG2 order_over_hard_cap('nan')        -> RAISES InvalidOperation
BUG2 order_over_hard_cap('-Infinity')  -> None  <-- PASSES CAP (bad)
BUG3 extract_last_price(last='NaN')        -> RAISES InvalidOperation
BUG3 extract_last_price(last='Infinity')   -> Decimal('Infinity')  <-- leaked
BUG (KP-03) 18:30 UTC -> Thai 2026-06-16 | naive(UTC) 2026-06-15 | OFF BY A DAY
```

### 3.3 หลังแก้

```
BUG1 double-entry: REAL_BIDS=1 (max_open_positions=1) -> ok
BUG2 order_over_hard_cap('nan'/'NaN'/'-Infinity'/'Infinity'/'inf') -> "non-finite ... rejected"
BUG3 extract_last_price(NaN/Infinity/inf) -> None
```

### 3.4 Runtime resilience (boot/soak/restart) — uvicorn จริง + mock ticker

```
=== PHASE 1: boot-from-zero (ไม่มี data/ ไม่มี .env) ===
GET /=200  /api/status=200  /healthz=200  /api/health=200  /metrics=200
execution_engine='paper'   data/state.db created? True
latest_price='2884775.35'  feed_connected=True
=== PHASE 2: soak 60s ===
RSS start=61820KB end=63288KB delta=1468KB (ไม่ leak)  msg/s=2.0 คงที่  crashed: none  alive
=== PHASE 3: kill -TERM + reboot ===
POST /api/order BUY -> 200 {opened, positions:1}   cash_str=50.003431534130956
SIGTERM -> exited rc=-15 ; reboot -> state_restored=True ; positions=1 ; cash_str ตรงเป๊ะ
```

### 3.5 watchdog + risk rails

```
$ pytest test_paper_pipeline.py::test_watchdog_restarts_crashed_agent_and_records_reason
PASSED   (restart_counts['crashy']>=1 ; crashed_agents['crashy']=="RuntimeError: boom")

$ pytest test_kill_switch test_daily_target test_real_money_matrix tests/architecture/
73 passed   (kill-switch persist ข้าม restart, hard-cap reject, daily-target lock, cage/honesty/risk-fence)

malformed price (domain chokepoint normalize_bitkub_ticker):
  0 -> NON_POSITIVE_PRICE | -1 -> NON_POSITIVE_PRICE | nan -> INTERNAL | inf -> INTERNAL
  -inf -> NON_POSITIVE_PRICE | None -> MISSING_LAST | 100 -> OK   (ไม่ 500 ไม่เปิดไม้มั่ว)
```

---

## 4. STEP 3 — Verify ซ้ำ (หลังแก้ครบ)

```
$ ruff check src tests
All checks passed!

$ mypy src/
Success: no issues found in 132 source files

$ pytest
842 passed, 1 skipped in 60.42s
Required test coverage of 90% reached. Total coverage: 91.34%
```

- เทสต์เพิ่มจาก 824 → **842** (+18 regression tests ใหม่/คืนกลับ)
- coverage 91.17% → **91.34%**
- **0 warnings** (เดิม 2)
- `mypy --strict` ไม่มี per-module ignore ใหม่

---

## 5. กฎเหล็กที่คงไว้ (ไม่ฝ่าฝืน)

- `execution_engine` ดีฟอลต์ = `"paper"` (ยืนยัน runtime จริง) — ไม่ถอด/ลดการ์ด ไม่ต่อ live order
- Rule H1: ทุกไม้เปิดด้วย SL+TP atomic (model-validator ใน `PaperPosition` บังคับ `stop<entry<TP`)
- เงินใช้ Decimal — ปิดช่อง float บนเส้นทางเงินที่เหลือ (KP-04, KP-14)
- ไม่โกหก: รายงานนี้เขียนเฉพาะที่ verify ด้วยการรันจริง + แปะ output; ระบุข้อจำกัดที่ทำไม่ได้ตามจริง
  (เชื่อม Bitkub จริง / Windows จริง — ดูข้อ 2)

> **ไม่ยืนยัน** ว่า "ไม่มีบั๊กเหลือ / ปลอดภัย 100% / พร้อมเทรดเงินจริง" — ระบบนี้ paper-only โดยตั้งใจ
> สิ่งที่ยืนยันได้คือ: gate เขียวครบ, บั๊กที่เจอถูกแก้+มี regression, runtime boot/soak/restart/watchdog
> ผ่านจริงในสภาพแวดล้อมนี้
