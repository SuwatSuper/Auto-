# รายงานตรวจบั๊กระบบ Kingdom Prime (Bitkub Trading Bot)

> วันที่ตรวจ: 2026-06-19 · ขอบเขต: `kingdom_prime_complete_v2.zip` (261 ไฟล์ Python, ~31,000 บรรทัด, 117 ไฟล์เทส)
> วิธีตรวจ: รัน `ruff` / `mypy --strict` / `pytest` ทั้งชุด + รีวิวโค้ดเชิงลึก 5 ระบบย่อยแบบขนาน + เขียนสคริปต์ทดสอบยืนยัน (repro) บั๊กสำคัญเอง

---

## สรุปภาพรวม (TL;DR)

**ของที่ผ่านสะอาด** ✅
- `ruff check` ผ่านหมด, `mypy --strict` ไม่มี error (136 ไฟล์), **เทส 977 ผ่าน / skip 1** (รันได้แม้บน Python 3.11 + pandas 3.0)
- คณิตศาสตร์อินดิเคเตอร์หลักบนเส้นทางจริง (RSI/EMA/MACD/ATR/Bollinger/SuperTrend) **ถูกต้องตามตำรา**
- Backtest engine **ไม่มี lookahead** (ตัดสินใจที่ `prices[:i+1]` แล้วเติมที่บาร์ถัดไป)
- Invariant เงินสดหลัก `cash == initial + realized_pnl` **ถูกต้อง** ทั้ง paper และ live-fill
- การ sign HMAC ของ Bitkub v3 **ถูกต้อง**, ไม่มีการ log ความลับ (ใช้ `SecretStr`), SQL parameterized (ไม่มี injection)

**แต่มีบั๊กจริงที่ต้องแก้** — สรุปตามความรุนแรง:

| ระดับ | จำนวน | หัวข้อสำคัญที่สุด |
|-------|-------|-----------------|
| 🔴 Critical | 2 | Circuit breaker ไม่ถูกบันทึก (restart แล้วปลดเบรกเอง); order timeout ทิ้งโพสิชันจริงที่ระบบไม่รู้ |
| 🟠 High | 8 | Control plane ไม่มี auth + โดน CSRF; live-arm ติดค้างใน .env แล้ว re-arm เองตอน restart; ไม่มี idempotency key; watchdog restart storm |
| 🟡 Medium | 13 | default config ปิด backstop ทั้งหมด; race ส่งออเดอร์ซ้ำ (manual); backtest stats ผิดนิยาม |
| ⚪ Low | 12 | off-by-one, dead branch, timestamp เพี้ยน ฯลฯ |

> **ข้อสรุปด้านความปลอดภัย:** ระบบ *เซฟตอนนี้เพราะมัน fail ไป paper mode* — บั๊ก High ของ Bitkub balance endpoint ทำให้ live trading ใช้งานจริงไม่ได้เลย (ดู H3). แต่ถ้าแก้ตรงนั้นแล้วเปิด live โดยไม่แก้ Critical/High ที่เหลือ จะมีความเสี่ยงเงินจริงสูง

---

## 🔴 CRITICAL

### C1 — Circuit breaker ที่ "trip" แล้ว ไม่ถูกบันทึก → restart ครั้งเดียวปลดเบรกเองเงียบๆ
- **สถานะ:** CONFIRMED (รีโปรแล้ว) · **ไฟล์:** `src/orchestration/runtime_agents.py:55`, `src/domain/risk/circuit_breaker.py:17-21`
- `CircuitBreaker` ถูกสร้างใหม่ทุกครั้งที่บูต (`_open=False`) ไม่มี `to_dict`/`load_dict` และไม่มีจุดไหนใน `runtime_memory.py`/`runtime.start()` กู้สถานะคืน (ยืนยันด้วย grep — ไม่มี caller)
- **ทริกเกอร์:** เบรกเกอร์ auto-trip จากการขาดทุนต่อเนื่อง (`paper_trader.py:494` → `record_trade`) หรือ operator สั่ง trip แล้วโปรเซส restart (crash loop จาก watchdog ที่ไม่มี cap — ดู H6, deploy, OOM)
- **ผลกับเงินจริง:** ด่านหยุดเทรด (`runtime_live.py:49-54`, `runtime_status.py:373`) ถูกล้างเงียบๆ บอตที่หยุดหลังขาดทุนหนักจะกลับมายิงออเดอร์ Bitkub จริงทันทีหลัง restart และต้องขาดทุนซ้ำอีก N ครั้งกว่าจะ trip ใหม่ — ตัวนับ treasury รายวัน *ถูกบันทึก* แต่เบรกเกอร์เป็น hard-stop ตัวเดียวที่ไม่ถูกบันทึก
- **วิธีแก้:** เพิ่ม `to_dict`/`load_dict` ใน `CircuitBreaker`; `store.set` ทุกครั้งที่ trip/reset/record_trade; กู้คืนใน `start()` ข้างๆ `load_controls()`

### C2 — Order timeout แบบกำกวม ทิ้งโพสิชันจริงที่ไม่มีใครคุม (ไม่มีการ reconcile fill เลย)
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/agents/execution_agent.py:369-372`
- เมื่อ `place_bid`/`place_ask` throw จาก read timeout/connection drop (timeout 10s) โค้ดแค่ log `live_order_failed`, ปล่อย inflight slot, แล้ว `return` — **ไม่ query `order_info`** เพื่อเช็คว่าจริงๆ ออเดอร์ฟิลไปแล้วหรือยัง
- ยืนยัน: `order_info` และ `cancel_order` ถูก *นิยาม* ใน `bitkub_rest.py:190,206` แต่ **ไม่มี caller ใน `src/` เลย** (grep แล้ว) → ไม่มีกลไก reconcile fill ใดๆ
- **ผลกับเงินจริง:** Bitkub อาจรับและฟิลออเดอร์แล้ว (แต่ response หาย) → มีโพสิชัน BTC จริงบนเอ็กซ์เชนจ์ที่บอตไม่รู้ → ไม่มีวันใส่ stop-loss/TP/trailing ให้มัน ตอนตลาดดิ่งโพสิชันนี้เลือดไหลโดยไม่มีการป้องกัน (คลาสสิก exactly-once vs at-least-once)
- **วิธีแก้:** ในทุก exception ของออเดอร์ ก่อนยอมแพ้ ให้ poll `order_info`/open-orders เพื่อตัดสินว่าฟิลไหม แล้ว record/mirror หรือ cancel; ส่ง alert วิกฤตเมื่อ resolve ไม่ได้

---

## 🟠 HIGH

### H1 — Control plane บน localhost ไม่มี auth เลย และโดน CSRF ได้ (เว็บมุ่งร้ายสั่ง kill-switch / arm live / ส่งออเดอร์ได้)
- **สถานะ:** CONFIRMED (รีโปรแล้ว) · **ไฟล์:** `src/infrastructure/web/_helpers.py:100-145` (`check_api_key`/`check_api_key_strict` ทั้งคู่ `return` ทันทีถ้า `is_local_request`)
- ดีไซน์ตั้งใจให้ "ห้องคุมเครื่องเดียว" — request จาก loopback เชื่อถือเต็มที่ ไม่ต้องคีย์ แต่ **ไม่มีการเช็ค Origin/CSRF token** เลย
- **ทริกเกอร์ที่เป็นช่องโหว่จริง:** เว็บไซต์มุ่งร้ายที่ operator เปิดในเบราว์เซอร์ POST ข้าม origin มาที่ `http://127.0.0.1:8000/api/kill_switch` ด้วย `Content-Type: text/plain` (เลี่ยง CORS preflight) เบราว์เซอร์ส่งจาก loopback (ระบบเชื่อถือ) → ปิด kill switch / arm live / ส่งออเดอร์ได้ (CORS ไม่กันการเขียน state แบบ simple request)
- **ผลกระทบ:** โปรเซสอื่นในเครื่อง/ผู้ใช้ OS คนอื่น สั่ง control plane ได้โดยไม่มี credential; เว็บมุ่งร้ายขับ control plane ผ่านเบราว์เซอร์ได้
- **วิธีแก้:** บังคับ CSRF token (double-submit cookie หรือ header ที่หน้าเว็บฉีดจาก `page_control_key`) บนทุก endpoint ที่เปลี่ยน state แม้แต่ loopback; และ/หรือ ปฏิเสธ POST ที่ `Origin`/`Sec-Fetch-Site` เป็น cross-site

### H2 — สถานะ live-armed ติดค้างใน `.env` แล้ว re-arm เองตอน restart โดยข้ามด่านตรวจตอน arm
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/runtime_risk.py:281-291, 346-352`, อ่านกลับที่ `:201-214`
- ตอน arm จะเขียน `EXECUTION_ENGINE=live` + `LIVE_TRADING_CONFIRM` ลง `.env` แต่ด่านตรวจรวยๆ ตอน arm (per-order cap > 0, cap ≥ min ของเอ็กซ์เชนจ์, cap ≤ เพดาน — `:252-280`) รันแค่ใน `set_execution_mode` เท่านั้น ตอน restart แค่ *อ่าน flag จาก .env* → ข้ามด่านพวกนั้น
- รวมกับ C1 (เบรกเกอร์รีเซ็ตเป็น closed ตอน restart) → restart เดียวบูตมาในสถานะพร้อมยิงเงินจริงด้วย invariant ที่อ่อนกว่าตอน arm ครั้งแรก
- **วิธีแก้:** บังคับให้ re-arm อย่างชัดเจนหลัง restart หรือรันด่านตรวจ `set_execution_mode` ทั้งชุดตอนบูตก่อน `_live_orders_armed()` จะคืน True ได้

### H3 — Balance endpoint `/api/v3/market/wallet` อาจถูก Bitkub ถอดแล้ว → reconcile ล้มเสมอ → live trading ใช้งานจริงไม่ได้เลย
- **สถานะ:** CONFIRMED (จากโครงสร้างโค้ด — *ต้องยืนยันสถานะ API ปัจจุบันของ Bitkub อีกที*) · **ไฟล์:** `src/infrastructure/gateway/bitkub_rest.py:132-133` (`get_wallet` → `POST /api/v3/market/wallet`)
- agent รายงานว่า Bitkub ถอด `/api/v3/market/wallet` และ `/api/v3/market/balances` (changelog 2026-05-26) — นี่เป็นจุด **เดียว** ที่บอตเรียกดู balance (ไม่มี v4 fallback, grep ยืนยัน) ส่วน place-bid/ask/cancel/order-info/ticker ยังใช้ได้
- **ผลกระทบ:** `ReconciliationAgent._poll` throw เสมอ → `is_reconciled` ค้าง False → ด่าน M2 reconciliation (`runtime_agents.py:97`) บล็อกออเดอร์ live ทั้งหมด (อัตโนมัติ + manual) → ฟีเจอร์ live ตกไป paper เงียบๆ ใช้เงินจริงไม่ได้
- **วิธีแก้:** ย้ายไป `GET /api/v4/wallet/balances`/`assets` (sign path/พารามใหม่) แล้วอัปเดต parsing ใน `BitkubBalanceSource`
- ⚠ **หมายเหตุ:** ข้อนี้อ้างอิงสถานะ API ภายนอก ควรเปิดเอกสาร Bitkub ปัจจุบันยืนยันก่อนตัดสิน

### H4 — ไม่มี client order id / idempotency key ส่งให้ Bitkub → retry/restart ใดๆ ส่งออเดอร์ซ้ำได้
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/infrastructure/gateway/bitkub_rest.py:146-188`, dedup ที่ `execution_agent.py:255-264`
- ป้องกันซ้ำแค่ใน-process ด้วย `sha256(decision_id)` ใน `set` ระดับ session — หายเมื่อ restart และเป็น per-process เท่านั้น เกตเวย์ไม่มี replay protection; เส้นทาง manual (`_place_manual_live_bid`) และ `_live_close` **ข้าม dedup set ทั้งหมด**
- **ผลกระทบ:** double-click ของ operator, retry wrapper ในอนาคต, หรือ restart-replay จะส่งออเดอร์จริงตัวที่สองโดยไม่มีการ์ดฝั่งเอ็กซ์เชนจ์
- **วิธีแก้:** ส่ง `cli_id` (client order id) ของ Bitkub ที่ derive จาก decision id ให้เอ็กซ์เชนจ์ปฏิเสธตัวซ้ำ; persist `seen_ids` ข้าม restart

### H5 — Backtest realized PnL เป็น GROSS (ไม่หักค่าฟี) แล้วป้อนด่าน daily-loss + win_rate/expectancy นับผิดหน่วย
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/domain/portfolio/engine.py:52,74,94`, ใช้ที่ `src/domain/backtest/engine.py:200` → `rules.py:93`; และ `backtest/engine.py:210-219`
- **(a)** `apply_fill` ตั้ง `realized = qty*(price−entry)` (ไม่รวมฟี) — แม้ `cash` ถูกต้อง (หักฟีแล้ว) แต่ฟิลด์ `realized_pnl` เป็น gross → ใน `run_backtest` ใช้เป็น `daily_pnl` เทียบ `max_daily_loss` ทำให้ขาดทุนต่อวัน **ถูกประเมินต่ำกว่าจริงเท่ากับฟีรวม** → ด่าน DAILY_LOSS trip ช้าหรือไม่ trip; ยังพบว่า `daily_pnl` นี้เป็นยอด **สะสมตั้งแต่เริ่ม** ไม่รีเซ็ตรายวันด้วย
- **(b)** `win_rate`/`expectancy` คำนวณจาก *ผลต่าง equity ราย-บาร์* ไม่ใช่ราย-เทรด: round-trip ขาดทุนสุทธิที่ถือ 5 บาร์ (delta `[+1,−1,+1,+1,−3]` สุทธิ −1 = แพ้) ถูกรายงานเป็น `win_rate=0.6` (รีโปรยืนยัน) → ตัวเลขนี้ป้อน gate `min_p_win`/`min_sim_win_rate` ทำให้ด่านเลือกจังหวะหละหลวมกว่าที่ตัวเลขบอก
- **วิธีแก้:** คิด PnL ต่อ round-trip จาก `all_trades` หักฟีทั้งสองขา; หรือเปลี่ยนชื่อฟิลด์เป็น `bar_win_rate` และป้อนด่าน daily-loss ด้วยตัวเลขหักฟี

### H6 — Watchdog restart agent ไม่มี cap และไม่มี backoff (restart storm)
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/runtime.py:704-737`
- `restart_counts` ถูก ++ (`:728`) แต่อ่านไปแสดงผลเฉยๆ ไม่เคยใช้เป็น cap; ไม่มี `asyncio.sleep` backoff ก่อน `start_agent` (`:737`) — ต่างจาก `Supervisor` ของ price-feed ที่มี cap+backoff
- **ทริกเกอร์:** agent ตัวใดใน ~165 ตัวที่ task จบด้วย exception นอก try/except ราย-tick (เช่นใน `PriceListenerAgent.start` รอบ `self._bus.subscribe`) → watchdog สร้างใหม่ทุก `watchdog_interval_s` (ดีฟอลต์ 2.0s) ตลอดไป
- **ผลกระทบ:** crash-restart loop แน่น → log ท่วม, CPU เผา, subscriber churn; รวมกับ C1/H2 → loop นี้กลายเป็นตัว re-arm live เอง ขณะระบบยังขึ้น "เขียว"
- **วิธีแก้:** ใส่ cap ต่อ-agent (มาร์คว่า crashed ถาวรเมื่อเกิน N) + exponential backoff คีย์จาก `restart_counts[name]`

### H7 — JSONL event store ไม่ fsync; เขียน `.env` ไม่ atomic → audit log / credential หาย-พังตอน crash
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/infrastructure/events/jsonl_store.py:25-37`, `runtime_risk.py:354-376`, `runtime_live.py:516-540`
- JSONL: เขียนแล้ว return ไม่มี `flush()`/`os.fsync()` → ไฟดับแล้วท้าย log หาย; ฝั่งอ่านยัง yield บรรทัดท้ายที่ขาดเป็น record ปกติ (`line.strip()` ผ่าน partial JSON)
- `.env`: `env.write_text(...)` (truncate-then-write) ไม่มี temp + `os.replace` → crash กลางคันทำให้ `.env` พัง เสีย `INITIAL_CAPITAL`/credential/`EXECUTION_ENGINE`
- **วิธีแก้:** JSONL `flush()+os.fsync()` หลัง append และ validate บรรทัดท้ายตอนอ่าน; `.env` เขียน `.env.tmp` → fsync → `os.replace`

### H8 — Confirmation token ของ arm-live และ reset-breaker เป็นค่าคงที่ฮาร์ดโค้ดสาธารณะ
- **สถานะ:** CONFIRMED (อันตรายเมื่อรวมกับ H1) · **ไฟล์:** `runtime_risk.py:19-20` (`I_ACCEPT_REAL_MONEY_RISK`), `circuit_breaker.py:15` (`MANUAL_RESET_CONFIRMED`)
- เป็น string literal ที่ commit ลง git ไม่ใช่ secret — ไม่มี nonce/หมดอายุ replay ได้เต็มที่ ใครก็ตามที่เข้าถึง endpoint ได้ (ดู H1) และรู้ค่าคงที่ที่เดาง่ายนี้ arm live / reset breaker ได้
- **วิธีแก้:** วางหลัง auth จริง; ถ้าจะใช้เป็น confirmation ให้เป็น token สุ่มต่อ-session ที่เห็นเฉพาะ operator ที่ผ่าน auth แล้วเทียบด้วย `hmac.compare_digest`

---

## 🟡 MEDIUM

### M1 — Default config ปิด backstop อัตโนมัติทุกตัว เหลือแค่ survival floor
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/infrastructure/config.py:70` (`max_consecutive_losses="0"`), `:54` (`max_daily_loss_pct="100"`)
- ดีฟอลต์ที่ shipped: เบรกเกอร์ = 0 = ไม่จำกัด (ไม่ trip จากขาดทุนเลย), daily-loss cap = 100% ถ้า operator arm live โดยไม่ปรับ ทั้งเบรกเกอร์และ daily-loss halt **ไม่มีวันทำงาน** เหลือแค่ survival floor 70% — `.env.example` แนะนำ `MAX_CONSECUTIVE_LOSSES=5` แต่ดีฟอลต์ในโค้ดคือ 0
- **วิธีแก้:** ปฏิเสธการ arm live (หรือ force prompt) เมื่อ `max_consecutive_losses==0` หรือ `max_daily_loss_pct>=100`; ตั้งดีฟอลต์ live-mode ที่ปลอดภัยกว่า

### M2 — `evaluate()` ปฏิเสธ *ทุก* ออเดอร์เมื่อ `RiskLimits.max_consecutive_losses == 0` (semantic กลับด้านกับ "0 = ไม่จำกัด")
- **สถานะ:** CONFIRMED (latent — ปัจจุบันยังไม่ reachable บน production wiring) · **ไฟล์:** `src/domain/risk/rules.py:107`
- `if consecutive_losses >= limits.max_consecutive_losses:` — เพราะ `consecutive_losses` เริ่มที่ 0 ดังนั้น `0 >= 0` เป็นจริงเสมอ (รีโปรยืนยัน: คืน `CONSECUTIVE_LOSSES_EXCEEDED`) ขณะที่ทั้งระบบที่อื่น (เบรกเกอร์/config/control) ตีความ 0 = "ไม่จำกัด" — `evaluate()` เป็นที่เดียวที่ 0 แปลว่า "trip ทันทีตลอด"
- ปัจจุบัน `RiskLimits` ที่ป้อน `evaluate()` ใช้ดีฟอลต์ 5 เสมอ (operator's 0 ไหลเข้าแค่ `CircuitBreaker`) จึงยังไม่ยิงจริง แต่เป็นกับดักถ้ามีใคร wire ค่า operator เข้า `evaluate()` ในอนาคต (ชื่อฟิลด์ตรงกันเป๊ะ) จะบล็อกเทรด 100% โดยหาสาเหตุไม่เจอ
- **วิธีแก้:** `if limits.max_consecutive_losses > 0 and consecutive_losses >= limits.max_consecutive_losses:`

### M3 — `manual_order(BUY)` race ส่งออเดอร์จริงซ้ำ (เส้นทาง manual ไม่มี inflight guard/lock)
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/runtime_live.py:58-104` (เช็ค position ที่ `:78` ก่อน `await gw.place_bid` ที่ `:97`)
- คลิก BUY พร้อมกันสองครั้งผ่านด่าน `self._trader.position is not None` ทั้งคู่ แล้ว `await` network bid ทั้งคู่ → วางบิดจริงสองตัวก่อนตัวใดตั้ง `self.position` เส้นทางอัตโนมัติมี `_inflight_entries` กันไว้ แต่ manual ไม่มี; ไม่มี `asyncio.Lock` ใน orchestration เลย
- **วิธีแก้:** ถือ `asyncio.Lock` ตัวเดียวคร่อมช่วง read-decide-place-mutate ใน `manual_order` (และ breaker trip/reset, `set_execution_mode`); อย่าปล่อย lock คร่อม network await

### M4 — Resting limit order ถูก mirror เข้า paper เป็น "ฟิลเต็ม" ทันที (paper เพี้ยนจาก live)
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/agents/execution_agent.py:375-405`
- ถ้า `live_order_type=limit` (operator ตั้งได้, ดีฟอลต์ `market`) Bitkub คืน order id แต่ `rec`/`amt` อาจเป็น 0/หาย สำหรับออเดอร์ที่ยัง resting → mirror ตก fallback `elif rate:` (`:399`) แล้ว record โพสิชัน paper เต็มเหมือนฟิลแล้ว → บอตคิดว่ามีของที่ยังไม่มี, `_live_close` จะพยายามขายเหรียญที่ไม่เคยได้ → Bitkub ปฏิเสธ + บัญชีเพี้ยน
- **วิธีแก้:** ถ้า ack ไม่มี fill จริง ให้ถือเป็น "resting" อย่า mirror; poll `order_info` จนฟิล/cancel แล้ว mirror qty จริง

### M5 — Daily counter rollover (`roll_day`) ขับด้วยการ poll status ไม่ใช่ timer
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/agents/learning.py:167-173` (caller เดียวคือ `runtime_status.py:135` ตอน build status)
- ถ้าไม่มีการ poll status คร่อมเที่ยงคืน (รัน headless/UI idle) → `today_resolved/today_correct` ไม่รีเซ็ต → self-tuning ของ strategy (`extended/price_agents.py:82,126,176`) ปรับพารามเทรดจริงจาก hit-rate รายวันที่ค้างหลายวัน = ผูกการปรับที่กระทบเงินไว้กับ side effect ของการ observe
- **วิธีแก้:** เรียก `roll_day()` จาก timer ของ runtime สำหรับทุก learner; ให้ build status เป็น read-only; รีเซ็ต `_last_seen_pct` ใน `roll_day()` ด้วย

### M6 — SQLite store: durability window (WAL+NORMAL) + connection แชร์ข้ามเธรด + `keys()` LIKE wildcard
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/infrastructure/state/sqlite_store.py:15-28, 64-68`
- (a) WAL + `synchronous=NORMAL`: `set()` ที่ commit แล้ว (positions/balances) อาจหายตอนไฟดับ; (b) ใช้ `Connection(check_same_thread=False)` ตัวเดียวข้ามหลายเธรดของ executor (serialize ด้วย async lock จึงไม่ concurrent แต่พึ่ง invariant ที่ไม่ได้เขียนไว้); (c) `keys(prefix)` ใช้ `LIKE prefix||'%'` ไม่ escape `_`/`%` → prefix ที่มีอักขระพวกนี้ match เกิน
- **วิธีแก้:** `synchronous=FULL` สำหรับ store เงิน (หรือ checkpoint+fsync ตอน critical write); ใช้ executor `max_workers=1`; `LIKE ? ESCAPE '\'`

### M7 — งานคำนวณหนักแบบ sync บน event loop (timeline analyst / simulation) + try/except แคบ
- **สถานะ:** CONFIRMED · **ไฟล์:** `timeline_analyst.py:126-153`, `simulation.py:63-88`
- `ema_cross_setups`/`ema` รันบนประวัติเต็ม (ถึง 6000 Decimal) ทุก 5 tick ไม่มี `run_in_executor`; simulation รัน backtest 50 บาร์ทุก tick — บล็อกเธรด loop เดียว → price bridge/execution gate/reconciliation/FastAPI ค้าง (ราคา stale ป้อน gate); และ `timeline_analyst._analyze` (`:94`) **ไม่มี try/except** → exception ฆ่า loop แล้วไป thrash ผ่าน H6
- **วิธีแก้:** offload เข้า `run_in_executor` และ/หรือ cap ช่วงที่วิเคราะห์; ขยาย guard ของ loop เป็น `except Exception`

### M8 — Bitkub key/secret ถูกเขียนลง `.env` เป็น plaintext ด้วย permission ดีฟอลต์
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/runtime_live.py:516-540` (`_persist_credentials` จาก `connect_account`)
- ในหน่วยความจำเป็น `SecretStr` ไม่รั่ว แต่บนดิสก์เขียนเป็น raw text ไม่มี `chmod 600`
- **วิธีแก้:** `os.chmod(".env", 0o600)` หลังเขียนเป็นอย่างน้อย; ดีกว่านั้นใช้ OS keyring / ไม่ persist secret

### M9 — `load_controls` ปิด Kelly sizing เงียบๆ ทุก restart
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/runtime_memory.py:124-138` → `runtime_risk.py:111-112`
- snapshot ที่กู้คืน (มี `risk_per_trade_pct` เสมอ) ถูกส่งผ่าน `update_risk_settings` ซึ่งตั้ง `kelly_sizing_enabled=False` เมื่อมี `risk_per_trade_pct` ใน patch → การ restore ที่ขับด้วยเครื่องไปทริก heuristic "operator คุมเอง" ผิด ปิดฟีเจอร์ที่ operator เปิดไว้ทุกบูต
- **วิธีแก้:** restore ผ่าน path/flag ที่ข้าม toggle `kelly_sizing_enabled=False`

### M10 — Daily-summary แถวเดียวปนฐาน realized กับ unrealized (ไม่สอดคล้องในตัว)
- **สถานะ:** CONFIRMED · **ไฟล์:** `src/orchestration/runtime_status.py:494-504`, `daily_summary.py:42-43`
- เมื่อมีโพสิชันเปิดตอนเขียน: `end_equity = cash+open_value` (รวม unrealized) แต่ `pnl_net`/`pct_return_net`/`target_reached` = realized-only → `end_equity − start_equity = 5000` แต่ `pnl_net = 0` ในแถวเดียวกัน (รีโปรยืนยัน) → daily ledger ขัดแย้งในตัวเองทุกครั้งที่มีของเปิด
- **วิธีแก้:** ใช้ฐานเดียวกัน — คิด `pct_return` จาก `(end_equity − start_equity)/start_equity` หรือทำ end_equity เป็น realized-only

### M11 — Clock signing ใช้นาฬิกาเครื่อง ไม่ใช้ `get_server_time` แก้ drift
- **สถานะ:** SUSPECT · **ไฟล์:** `src/infrastructure/gateway/bitkub_rest.py:69-70, 111-117`
- `_default_clock` = `int(time.time()*1000)` (wall clock) สเปกบอกให้ดึง timestamp จาก `/api/v3/servertime`; `get_server_time()` มีแต่ไม่มี caller — ถ้านาฬิกา host drift เกิน window ที่ Bitkub รับ ทุก signed request (ออเดอร์+balance) ถูกปฏิเสธเงียบๆ
- **วิธีแก้:** ตอน startup + เป็นระยะ ดึง servertime คำนวณ offset เก็บไว้ บวกใน `_ts()`

### M12 — p_win (entry gate) วัดโดยสมมติฟิลที่ราคาปิดบาร์สัญญาณ แต่จริงฟิลบาร์ถัดไป (ลำเอียงดีเกินจริง)
- **สถานะ:** SUSPECT · **ไฟล์:** `src/domain/analytics/timeline.py:46-60` (`entry = prices[i]`) vs `backtest/engine.py:156-160` (ฟิลที่ `next_price`)
- `ema_cross_setups` เกรด cross ที่บาร์ `i` ด้วย `entry = prices[i]` (ปิดบาร์ที่เพิ่งฟอร์ม ซื้อไม่ทันจริง) → win-prob ในอดีตสมมติฟิลเร็ว/ดีกว่าที่ระบบทำได้จริง 1 บาร์ → ด่าน `min_p_win=0.80` หละหลวมกว่าตัวเลขบอกเล็กน้อย
- **วิธีแก้:** เกรดด้วย `entry = prices[i+1]` ให้ตรงกับ execution

### M13 — `dmi_adx` (pure Decimal) ไม่ตรงกับ vendor `.ta.adx` (seed/warmup คนละแบบ)
- **สถานะ:** CONFIRMED (ไม่อยู่บนเส้นทาง regime จริง) · **ไฟล์:** `indicator_lines.py:464-496` vs `vendor_ta/__init__.py:142-170`
- pure seed ที่ index 14, vendor seed ที่ 13 → +DI/−DI/ADX เริ่มช้ากว่า 1 บาร์ และ steady-state ต่างกัน ~0.16% — แต่ไม่มี strategy/gate ใช้ `dmi_adx` (live ใช้ `ta.adx` ผ่าน `regime.py`) จึงเป็น defect ความสอดคล้อง ไม่ใช่บั๊กเงินตรงๆ
- **วิธีแก้:** ทำให้ `_wilder_sum` seed ที่ window แรกเดียวกับ vendor/ATR

---

## ⚪ LOW / Informational

| # | หัวข้อ | ไฟล์ | หมายเหตุ |
|---|--------|------|----------|
| L1 | `evaluate()` open-positions ใช้ `>` ขณะด่านจริงใช้ `>=` (off-by-one ปล่อยถึง cap+1) | `rules.py:110` | advisory/backtest เท่านั้น; ด่าน live ที่ `execution_agent.py:220` ใช้ `>=` ถูกต้อง |
| L2 | `release_reservation` คืน cash แต่ไม่ลด `entries_today`/`approved_count` → phantom entry กิน quota รายวัน | `treasury_agent.py:135-138,178-180` | เกิดเมื่อ `open_position` raise หลัง treasury อนุมัติ |
| L3 | `vendor_ta` ADX (live regime) warmup เร็วกว่า canonical 1 บาร์ + offset ~0.5% | `vendor_ta/__init__.py:15-30` → `regime.py:46` | เทียบ `adx>25` พลิก TREND/RANGE ได้เฉพาะค่าก้ำกึ่ง |
| L4 | `detect_market_mode` คืน `BREAKOUT` ไม่ได้เลย (dead branch) | `market_mode.py:16-29` | playbook BREAKOUT ใน `regime_weights` ไม่ถูกเรียก |
| L5 | inflight reservation รั่วบน paper path + `live_no_router` → false POSITION_CAP ชั่วคราว ≤5s | `execution_agent.py:272-281,332-337` | self-heal; พลาดเทรด ไม่เสียเงิน |
| L6 | WS reconnect ไม่มี backoff escalation (reset attempt=0 หลังเฟรมแรก) | `bitkub_ws.py:58-62` | เฉพาะ `price_feed_mode=ws` (ดีฟอลต์ rest) |
| L7 | CircuitBreaker auto-trip บันทึก `now=0` (1970) ใน trip_history | `circuit_breaker.py:72` | audit timestamp เพี้ยน (ไม่กระทบ logic) |
| L8 | `pct_return`/`daily_profit_pct` ใช้ตัวหารต่างกันระหว่างหน้า dashboard กับ CSV | `daily_summary.py:43` vs `runtime_live.py:136` | reporting ไม่ตรงกัน ไม่ขยับเงินผิด |
| L9 | `SystemClock.now_ms` ใช้ `time.time_ns()` (ไม่ monotonic) สำหรับทั้ง timestamp และ duration | `clocks/system_clock.py:11-13` | NTP step ย้อนทำ window เบรกเกอร์/cooldown เพี้ยน |
| L10 | Event bus drop event เก่าสุดเงียบๆ เมื่อ queue (ดีฟอลต์ 10k) เต็ม | `eventbus/in_memory.py:20-24` | at-most-once มี silent loss บน topic วิกฤต |
| L11 | Event ที่ publish ก่อน subscriber มาสาย หายโดยไม่มี counter | `in_memory.py:18` | startup กันด้วยลำดับ subscribe; reconnect ยังหลุดได้ |
| L12 | ไม่มี signal handling ใน `main.py` → SIGKILL/non-lifespan ทำให้ httpx client รั่ว + memory ที่ยังไม่ flush หาย | `src/main.py` | shutdown สะอาดรันผ่าน ASGI lifespan เท่านั้น |
| L13 | `should_halt`/survival floor เช็คกับ `cash` ไม่ใช่ equity ตอน rollover | `treasury_agent.py:176,290` | halt ที่ยืนอยู่ไม่ trip จาก unrealized drawdown; `review_open` ใช้ equity ถูกต้อง |

---

## ลำดับความสำคัญในการแก้ (แนะนำ)

**ก่อนเปิด live เด็ดขาด:**
1. **C1** — persist circuit breaker state
2. **C2** — reconcile fill หลัง order timeout (poll `order_info`)
3. **H3** — migrate balance endpoint ไป v4 (ไม่งั้น live ใช้ไม่ได้อยู่แล้ว)
4. **M1** — บังคับ backstop ตอน arm live (ห้าม `max_consecutive_losses=0` / `daily_loss=100%`)
5. **H4** — ส่ง `cli_id` idempotency key
6. **H2** — ห้าม auto re-arm live ตอน restart

**ความปลอดภัยเว็บ:**
7. **H1 + H8** — CSRF token + ไม่เชื่อ loopback แบบไม่มีเงื่อนไขบน money endpoints + token ที่เป็น secret จริง

**เสถียรภาพ/ความถูกต้อง:**
8. **H6** (watchdog cap+backoff), **H7** (fsync/atomic write), **M3** (lock manual order), **M7** (offload heavy compute)

**ความถูกต้องของตัวเลข (ไม่ขยับเงินจริง แต่ทำให้ตัดสินใจผิด):**
9. **H5** (backtest gross PnL + win_rate ราย-บาร์), **M2** (evaluate 0-semantics), **M5/M9/M10**

---

## ภาคผนวก — สิ่งที่ตรวจแล้ว "ถูกต้อง" (ไม่ใช่บั๊ก)
- HMAC signing scheme + headers ของ Bitkub v3 (เทียบ reference vector), GET query order, float→str→Decimal round-trip ราคา/จำนวน
- คณิต `size_with_fees` per-unit-risk, ทิศ rounding ทุก sizing fn เป็น ROUND_DOWN (ไม่เคยปัดขึ้นเกินงบเสี่ยง), Kelly clamp [0,0.25], max_notional cap
- Weighted-average entry ตอน add/partial-close, invariant `cash == initial + realized_pnl` (paper+live), `close_position` หักฟีทั้งสองขา
- RSI/EMA/MACD/ATR/Bollinger(population stddev)/WMA/Williams%R/SuperTrend ตรงตำรา, `ml_winprob` sigmoid clamp [0,1] ไม่มี NaN เข้า sizing
- Backtest ไม่มี lookahead, SQL parameterized (ไม่มี injection), ไม่ log secret, background task ถือ strong ref, stop/cancel-and-await ถูกต้อง, token bucket ไม่ burst เกิน capacity, `assert_safe_bind` fail-closed
