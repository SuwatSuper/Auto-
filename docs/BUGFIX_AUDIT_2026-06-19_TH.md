# รายงานการแก้บั๊ก (Bug-Audit Fixes) — 2026-06-19

แก้ตามผลตรวจใน `BUG_AUDIT_REPORT_TH.md` ผลรวมหลังแก้: `ruff` ✅ · `mypy --strict` ✅ ·
**pytest 997 ผ่าน / 1 skip** · coverage **91.56%** (เกิน gate 90%) — เพิ่มเทสใหม่ 20 ชุดล็อกพฤติกรรมที่แก้

---

## ✅ แก้แล้ว (ตามที่สั่ง + ส่วนที่เหลือที่ปลอดภัย)

### 🔴 Critical
- **C1 — Circuit breaker persist ข้าม restart.** เพิ่ม `to_dict`/`load_dict` + hook `on_change` ใน `CircuitBreaker`; runtime persist ทุกครั้งที่ trip/reset/record_trade (`_schedule_breaker_persist` → state store) และ `_restore_breaker()` ตอน start() **ก่อน** load_controls (operator threshold ยังชนะ). เบรกที่ trip แล้ว **ค้างต่อหลัง restart — เฉพาะ operator เท่านั้นที่ reset ได้** (ตามที่สั่ง). ไฟล์: `domain/risk/circuit_breaker.py`, `runtime_memory.py`, `runtime_agents.py`, `runtime.py`
- **C2 — Order timeout ทิ้งโพสิชันจริง.** ใน `_route_live` แยก `BitkubApiError` (เอ็กซ์เชนจ์ปฏิเสธ = ไม่ฟิล ปลอดภัย) ออกจาก transport/timeout (กำกวม = อาจฟิลแล้ว). กรณีกำกวม → **trip เบรกเกอร์ (halt) + ส่ง critical alert** ให้ operator ไป reconcile เอง. ไฟล์: `orchestration/agents/execution_agent.py`

### 🟠 High
- **H1 — Control plane CSRF.** เพิ่ม `check_csrf()` เช็ค `Origin`/`Sec-Fetch-Site` กันคำสั่งเปลี่ยน state ข้าม-origin แม้บน loopback (เว็บมุ่งร้ายในเบราว์เซอร์สั่งไม่ได้แล้ว); non-browser/same-origin/GET ไม่กระทบ. ไฟล์: `infrastructure/web/_helpers.py`
- **H2 — live-arm re-arm เองตอน restart.** เพิ่ม `_revalidate_persisted_execution_mode()` ตอน start(): ถ้า `.env` = live แต่ด่าน arm ไม่ครบ → **ตกกลับ paper + alert** ต้อง re-arm เอง (ไม่บูตมายิงเงินจริงด้วย invariant อ่อนกว่าเดิม). ไฟล์: `orchestration/runtime_risk.py`, `runtime.py`
- **H3 — Bitkub balance endpoint ถูกถอด (ยืนยันแล้วจากเอกสาร Bitkub: v3 crypto endpoints deprecated 03/02/2025).** migrate ไป `GET /api/v4/wallet/balances` (adapt เป็น shape เดิม) + **fallback ไป v3 อัตโนมัติ** ถ้า v4 ใช้ไม่ได้. ไฟล์: `infrastructure/gateway/bitkub_rest.py`
- **H4 (บางส่วน) — idempotency.** ปิดช่อง double-send ที่ reachable จริง (double-click) ด้วย M3 lock. *cli_id ฝั่งเอ็กซ์เชนจ์ยังไม่เปิด* (รอยืนยัน field กับ Bitkub) — ไม่มี retry/replay vector อื่นในโค้ด
- **H5 — Backtest gross PnL + win_rate ราย-บาร์.** (a) daily-loss gate ใช้ realized **หักฟี** แล้ว; (b) `win_rate`/`expectancy` คิดจาก **round-trip จริง** (จับตอน position กลับ flat) ไม่ใช่ผลต่าง equity ราย-บาร์. ไฟล์: `domain/backtest/engine.py`
- **H6 — Watchdog restart storm.** เพิ่ม cap (`max_agent_restarts=10`, เกินแล้ว "ยอมแพ้" + critical alert) + exponential backoff ต่อ-agent. ไฟล์: `runtime.py`, `config.py`
- **H7 — fsync/atomic write.** JSONL store `flush()+os.fsync()` ทุก append + ข้าม torn-tail ตอนอ่าน; เขียน `.env` แบบ atomic (tmp+fsync+`os.replace`). ไฟล์: `events/jsonl_store.py`, `runtime_risk.py`
- **H8 — token.** ช่องโจมตีจริง (CSRF) ปิดด้วย H1 แล้ว; typed confirm token = การยืนยันของ operator (คงไว้ตามดีไซน์ "operator คุมเอง")

### 🟡 Medium
- **M1 — บังคับ backstop ตอน arm live.** ห้าม arm live ถ้า `max_consecutive_losses==0` หรือ `max_daily_loss_pct>=100` (ต้องตั้ง backstop จริงก่อน). `runtime_risk.py:_live_arm_preconditions`
- **M2 — evaluate() 0=unlimited.** `domain/risk/rules.py`
- **M3 — manual order lock.** `asyncio.Lock` คร่อม read-decide-place-mutate กัน double-real-order. `runtime_live.py`
- **M4 — resting limit ไม่ mirror.** limit order ที่ไม่มี fill จริง ไม่ถูก record เป็นโพสิชัน paper. `execution_agent.py`
- **M5 — roll_day ด้วย timer.** เรียกจาก memory loop (ไม่ผูกกับการ poll status) + reset `_last_seen_pct`. `runtime_memory.py`, `learning.py`
- **M6 — sqlite.** `synchronous=FULL` (money store durability) + escape LIKE wildcard ใน `keys()`. `state/sqlite_store.py`
- **M8 — chmod .env 600.** ใน `_persist_env_setting`. `runtime_risk.py`
- **M9 — kelly restore.** `update_risk_settings(..., from_restore=True)` ไม่ปิด Kelly ตอน restore. `runtime_risk.py`, `runtime_memory.py`
- **M10 — daily-summary ฐานเดียวกัน.** `end_equity = start + realized_today` (realized-ledger สอดคล้องทั้งแถว). `runtime_status.py`

### ⚪ Low
- **L1** `>=` open-positions cap · **L2** `release_reservation` คืน counters · **L4** market_mode BREAKOUT reachable · **L7** auto-trip timestamp จริง

---

## ⏸ ยังไม่แก้ (เจตนา — เสี่ยง/ต้องตัดสินใจเชิงนโยบาย/ยืนยันภายนอก) — เอกสารไว้

- **M11 servertime drift** (SUSPECT): ต้อง poll servertime เป็นระยะ (network ทดสอบที่นี่ไม่ได้); host+NTP ปกติพอใช้. มี `get_server_time()` พร้อมต่อยอด
- **M12 p_win fill-timing** (SUSPECT): เปลี่ยน entry grading `prices[i]`→`prices[i+1]` กระทบนิยามการวัด win-rate เป็นวงกว้าง — เป็น judgment ไม่ใช่บั๊กชัด
- **M13 / L3 ADX warmup**: แก้ seeding จะเปลี่ยนค่าอินดิเคเตอร์ + เสี่ยงต่อ signal/regime; `dmi_adx` ไม่อยู่บนเส้นทางจริง, vendor ADX ต่าง ~0.5%
- **L8/C3 pct_return denominator**: per-day vs initial_capital เป็น judgment (per-day ฐานของ daily row ก็มีเหตุผล)
- **L9 monotonic clock · L12 signal handling · L13 standing-halt ใช้ cash**: Low/by-design (uvicorn จัดการ graceful shutdown ผ่าน lifespan; review_open ใช้ equity สำหรับไม้ใหม่อยู่แล้ว)

> หมายเหตุ: ไม่แตะคณิตอินดิเคเตอร์/seeding และไม่บังคับ field API ที่ยืนยันกับ Bitkub ไม่ได้ — เพื่อไม่ให้เกิด regression ในระบบเงินจริง
