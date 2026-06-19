# Kingdom Prime — RELEASE AUDIT REPORT (ด่านสุดท้ายก่อนใช้จริง)

> ตรวจ 13 ด้าน + owner's 5 checks · effort: max · แปะ output จริงทุกด้าน
> **ข้อจำกัดที่ต้องบอกตามจริง:** prompt ขอให้ gate นี้รันใน *session แยก* จากคนเขียนโค้ด
> ผมคือ session เดียวกับที่เพิ่งทำ Phase 10 — จึงตรวจแบบ adversarial ที่สุดเท่าที่ทำได้
> และระบุชัดว่าตรงไหน "รันจริงพิสูจน์แล้ว" vs "พึ่งเทสต์ที่มีอยู่"

---

## 🔢 สรุปผล
- **บั๊กที่เจอ:** 2 (S1 ×1, S3 ×1) · **แก้แล้ว:** S1 (1/1) · **เหลือ:** S3 ×1 (cosmetic — มีเหตุผล ไม่แก้)
- **S0/S1 คงค้าง: 0** ✅
- เทสต์เต็ม: **823 passed, 1 skipped · coverage 91.17%** (เกณฑ์ 90)
- ruff ✅ · mypy --strict ✅ (132 ไฟล์) · architecture guards (cage+honesty+fence+layer) ✅
- soak 60s: ไม่ crash / ไม่ leak / ไม่ hang · restart ×4: ไม่พัง guard ทำงาน
- reconcile: **เลขจอ = ledger = trades_*.csv เป๊ะระดับสตางค์** ✅

---

## 🐞 BUG/CRASH LEDGER

### [R1] S1 — `TradeCsvLogger` ไม่ถูกต่อเข้า runtime → ไม่มี `data/trades_*.csv` ตอนรันจริง
- **ที่เจอ:** ด้าน M (data recording) + owner check #1 (เลขจอตรง trades_*.csv)
- **อาการ:** `TradeCsvLogger` มีโค้ดครบ + unit test ครบ แต่ **ไม่เคยถูกสร้างใน production**
  (`grep "TradeCsvLogger(" src/` = ไม่มีเลย). รันจริง paper/live แล้ว **ไม่มีไฟล์ trades CSV เกิดขึ้น**
- **ผลกระทบ:** (1) owner ตรวจ "เลขจอตรง CSV" ไม่ได้ (ไม่มี CSV) (2) การบันทึก provenance หาย
  (3) **ML win-prob loop (U2/Phase10) เทรนจาก `data/trades_*.csv` ไม่ได้** เพราะไฟล์ไม่เกิด
- **root cause:** ขาดการ wire — bootstrap/runtime ไม่เคยสร้าง recorder agent/task
- **repro:** `pytest tests/orchestration/test_trade_csv_wiring.py` (ก่อนแก้ = fail: ไม่มี CSV)
- **การแก้:** `runtime.start()` สร้าง `TradeCsvLogger` เป็น background task subscribe topic paper events
  เขียนลง dir เดียวกับ state.db (gated `persist_state`); `runtime.stop()` ปิด/ยกเลิกสะอาด
- **regression test:** `tests/orchestration/test_trade_csv_wiring.py::test_runtime_records_closed_trades_to_csv`
  (fail ก่อนแก้ → pass หลังแก้ · ตรวจ row มี pnl_net/strategy_id/regime/win_prob_est ตรง)
- **commit:** `fix[R1/S1]: wire TradeCsvLogger into the runtime`

### [R2] S3 — `status()` แปลงเงินเป็น `float` ที่ขอบ JSON (display) → คลาดเคลื่อนระดับ ~1e-9 บาท
- **ที่เจอ:** ด้าน I (reconcile) ตอนรันจริง: `screen.cash=49152.77083380553` vs `ledger.cash=49152.7708338055288750`
- **อาการ:** เลขตรงกัน ~13–14 หลักนัยสำคัญ ต่างที่หลักที่ 14+ (เศษ float) — **ไม่ถึง 1 สตางค์**
- **วิเคราะห์ว่าทำไมไม่ใช่ S0:** ledger เงินเป็น **Decimal เป๊ะ** ทุกการคำนวณ; float เกิดเฉพาะตอน
  serialize ออก JSON เพื่อโชว์ (`runtime_status.py:287-292`). reconcile ระดับสตางค์ (0.01) = **ตรงเป๊ะ**
  (พิสูจน์ด้านล่าง) · `equity_str`/`initial_capital` ส่งเป็น string เต็มความละเอียดอยู่แล้ว
- **ทำไมไม่แก้ใน gate นี้:** เปลี่ยน format เงินใน status เป็น string จะกระทบ dashboard JS + เทสต์จำนวนมาก
  ที่ `float(s["cash"])` — ความเสี่ยง regression สูงกว่าผลได้ (ต่าง < 1e-9 บาท มองด้วยตาไม่เห็น)
  จัดเป็น **S3** ตามจริง · honesty guard เดิมยังเขียว · owner check #1 (มองด้วยตา) ผ่าน
- **regression test:** ไม่เพิ่ม (ไม่ได้แก้โค้ด) — มี `equity_str` string-exact ให้ใช้ถ้าต้องการความเป๊ะ 100%

---

## 🔬 ผลตรวจ 13 ด้าน (output จริง)

### A. Static + guards
```
ruff check src tests        → All checks passed!
mypy --strict src/          → no issues found in 132 source files
grep "type: ignore" src/    → 6 (ทั้งหมดของเดิม: composition glue ที่ gateway เป็น object — ไม่ใช่ของใหม่)
noqa ที่ใช้                  → PLC0415 (local import เลี่ยง circular) เป็นหลัก — ไม่ใช่กลบ error
ไฟล์ > 500 บรรทัด           → ไม่มี
pytest tests/architecture/  → 35 passed (cage + honesty + risk-fence + layer rules)
```

### B. Exception-safety
- `except:` เปล่า = **ไม่มี** · `except BaseException` = **ไม่มี** (ไม่กลืน Cancelled/KeyboardInterrupt)
- ทุก agent loop มี Supervisor (`supervisor.py`) + watchdog (`runtime._watchdog`) auto-restart มี backoff,
  แยก cancelled ออกจาก crash, บันทึกเหตุ crash; external call (REST/WS/RSS/SQLite) ห่อ error + timeout

### C. Boot / shutdown / restart
```
boot จากศูนย์ (ไม่มี data/ ไม่มี .env): GET / = 200 · GET /api/status = 200
  · สร้าง data/state.db เอง · equity=cash=initial=1000 (reconcile)
restart ×4: live_tasks=181 ทุกรอบ · crashed=0 · double-start guard = OK ทุกรอบ
```

### D/E. Crash-recovery / deadlock
- watchdog auto-restart + state กลับครบ: `test_crash_recovery.py` (3) ผ่าน
- loop ทุกตัวมี timeout (`asyncio.timeout(0.5)` / `wait_for`) — ไม่ block ตลอดกาล; heartbeat staleness ตรวจได้

### F. Soak / stress (รันจริง 60 วินาที, ~82–91 msg/s)
```
t=10s RSS=42.2MB  t=30s RSS=46.5MB  t=60s RSS=46.9MB  (โตรวม 4.8MB แล้วนิ่ง)
crashed=0 restarts=0 · LEAK CHECK: OK (bounded) · ไม่ hang
```
> หมายเหตุตามจริง: soak ที่ทำคือ **60 วินาที** (ไม่ใช่ 30 นาที/หลายวันแบบ wall-clock).
> ส่วนหลายวันพึ่งเทสต์ `FixedClock` ที่มีอยู่ (thai_time/daily reset) — ผ่าน

### G. Resource bounded
- `test_memory_bounds`, `test_seen_ids_bounded`, `test_load_scaling`, `test_dropped_messages` → ผ่าน
- soak ยืนยัน RSS นิ่ง (buffer/deque/queue bounded จริง)

### H. Concurrency races
- เจอ publish-before-subscribe ตอนเขียน regression test เอง (recorder ต้อง subscribe ก่อน publish) →
  ยืนยันว่าพฤติกรรม bus เป็นไปตามที่คาด · regression races เดิม (stale double-entry, id collision) เทสต์ครอบ

### I. Financial correctness + Honesty (รันจริง — หัวใจ "ห้ามโกหก")
```
INVARIANT equity == cash + open_mkt_value : OK
INVARIANT pnl_today == realized + unreal  : OK
INVARIANT screen.cash == ledger.cash      : OK  (ระดับสตางค์)
INVARIANT csv_sum(4 rows) == realized     : OK  (csv=-22530.69 == ledger=-22530.69)
```
- ค่าธรรมเนียมหักสองขา · `pnl_net = gross − fee − slippage` · daily% = realized net จริง (ไม่ใช่ target)
- ไม่มี `float(` ใน **เส้นทางคำนวณเงิน** (ledger เป็น Decimal); float มีแค่ขอบ display (ดู R2)

### J. Risk rails adversarial
- order > hard-cap (1,001/999999999) → **reject** · cap เกินเพดานโค้ด → reject · live notional clamp ที่จุดจ่ายเงินจริง
- kill-switch (ไฟล์ `data/KILL_SWITCH`) → block live **ข้าม restart** (เป็นไฟล์ดิสก์)
- daily target 5% → ล็อกหยุดเปิดไม้ · bracket H1 บังคับ (ไม่มีไม้ไร้ stop/TP)
- `test_real_money_matrix` (22) · `test_kill_switch` (3) · `test_daily_target` (5) → ผ่านหมด

### K. Edge / boundary
- ราคา 0/ติดลบ/NaN/inf, JSON พัง, field หาย → parser ทุกตัวกัน (price feed, depth, sentiment, ml)
- order ราคาแย่ → reject ไม่ 500 ไม่เปิดไม้มั่ว (`manual_order` ตรวจ finite/>0)

### L. Time / timezone
- `test_thai_time` ผ่าน · daily reset เที่ยงคืนเวลาไทย (tz offset 420 นาที) · day rollover ถูก

### M. Data recording
- **แก้ R1 แล้ว** → `trades_*.csv` เขียนจริงตอนรัน, คอลัมน์ครบ (Phase 5 provenance), แถวตรง event จริง
- `daily_summary.csv` คำนวณจาก ledger จริง (`test_data_recording` ผ่าน)

---

## ✅ owner's 5 checks (ทำให้ผ่านก่อนส่ง)
1. **เลขจอตรง trades_*.csv** → ✅ reconcile เป๊ะ (csv_sum == realized == screen) + regression test
2. **order เกิน cap → reject** → ✅ `test_hard_cap_validation_matrix` (1001/999999999 = reject)
3. **kill-switch → live block (ข้าม restart)** → ✅ ไฟล์ KILL_SWITCH คงอยู่ข้าม restart
4. **ถึง 5% → ล็อกกำไร** → ✅ `test_trade_budget_locks_when_target_reached`
5. **ปิด-เปิดใหม่ state ไม่หาย** → ✅ `test_crash_recovery` + `test_memory_persistence`

---

## ⚠️ รายงานปิดท้าย — ตามจริง
- **เจอ 2 / แก้ 1 (S1) / เหลือ 1 (S3 มีเหตุผล)** · S0/S1 คงค้าง = 0
- **มั่นใจ (รันจริงพิสูจน์):** boot-from-zero, reconcile screen=ledger=CSV, soak 60s ไม่ leak,
  restart ×4, risk rails reject, honesty invariants
- **ตรวจไม่ครบ/ทำไม่ได้ใน session นี้ (ตามจริง):** (ก) soak ระดับ 30 นาที–หลายวัน *wall-clock* จริง
  (ทำได้แค่ 60s + FixedClock tests) (ข) live เงินจริงบน Bitkub endpoint จริง (ใช้ mock gateway เท่านั้น)
  (ค) gate นี้ควรเป็น session แยกจากคนเขียน — ผมเป็น session เดียวกัน
- **ห้ามสรุปว่า "ไม่มีบั๊ก / ปลอดภัย 100% / พร้อมเทรดเงินจริง"** — เขียนได้แค่ที่ verify จริง.
  การเปิด live เงินจริงต้องผ่าน **paper track record ต่อเนื่อง + edge validation (walk-forward/OOS)** ก่อนเสมอ
- **ส่งมอบ:** `dist/kingdom_prime_final.zip`
