# 🔬 BUG AUDIT REPORT — Kingdom Prime

> Session ผู้ตรวจสอบอิสระ (adversarial). สมมติว่าระบบมีบั๊กเสมอ — ตรวจ 10 ชั้น แปะผลจริง
> วันที่: 2026-06-15 · `pytest 733 passed / 1 skip` · `ruff` ✅ · `mypy --strict` ✅ (125 ไฟล์)

---

## สรุปผล (ตามจริง — ห้ามเกิน)

ตรวจ 10 ชั้นด้วยการ **รันเทสต์ regression จริง + boot จริง + reconcile เลขกับ ledger**
- **บั๊กที่เจอ:** 1 ตัว — `B-AUDIT-1` (S3, honesty-guard อ่อน) → **แก้แล้ว** (เพิ่ม guard ครอบจริง)
- **S0/S1:** ไม่พบในชั้นที่ตรวจ (regression money/risk/concurrency/persistence ผ่านครบ)
- **ตรวจไม่ได้ครบใน sandbox นี้:** live Bitkub network (WS feed / REST backfill) ถูกบล็อก — ตรวจได้แค่ว่า boot degrade สวย (dashboard 200, feed=unavailable ไม่ crash)

> "เทสต์เขียว ≠ ไม่มีบั๊ก" — ผมโฟกัสตรงเส้นเงิน/ความซื่อสัตย์/รั้วความเสี่ยง (เสี่ยงสุด) และ regression เก่า
> ที่โปรเจกต์นี้เคยเจอ. การ fuzz ระยะยาว/chaos เต็มรูปแบบ และ live-network ยังไม่ได้รันครบในรอบนี้.

---

## BUG LEDGER

### B-AUDIT-1 — honesty guard อ่อน (จับ fabricator ที่เปลี่ยนชื่อไม่ได้) · S3 → แก้แล้ว
- **ที่เจอ:** `tests/architecture/test_execution_guard.py::test_no_mock_data_in_production_dashboard`
- **อาการ:** guard เดิม match สตริงตรงตัว `"function simulateAgentMetrics() {\n  const"` เท่านั้น —
  ถ้ามีคนเปลี่ยนชื่อ/จัดรูปแบบฟังก์ชันสร้างข้อมูลปลอมใหม่ guard จะ **ไม่จับ** (false negative)
- **root cause:** การ์ดอิงสตริงเป๊ะ ไม่ได้อิงเจตนา. (หมายเหตุ: `simulateAgentMetrics()` ปัจจุบันเป็น
  **stub ว่าง** หลัง production migration — ไม่ได้สร้างข้อมูลปลอมจริง จึงเป็น S3 ไม่ใช่ S0)
- **repro:** `grep -n "simulateAgentMetrics" kingdom.html` → ฟังก์ชันยังอยู่ (ว่าง) แต่ guard เดิมไม่ครอบ
- **แก้:** เพิ่ม `tests/architecture/test_honesty_guard.py` — สแกน `Math.random()` / demo-simulator /
  fabricating-body + **unit reconcile** (เลขจอ == ledger) + เทสต์ "วันแดงต้องโชว์ % จริงไม่ใช่เป้า"
- **regression test:** `test_no_random_or_fabricated_numbers_in_production_js`,
  `test_status_equity_cash_reconcile_with_treasury_ledger`, `test_daily_pct_shows_real_loss_not_target`

---

## ผลตรวจ 10 ชั้น (แปะผลจริง)

| ชั้น | ตรวจอะไร | ผล |
|---|---|---|
| **1 Static** | ruff / mypy --strict / type:ignore count / god-file / TODO-FIXME / import cycle / layer leak | ✅ ruff+mypy สะอาด · `type: ignore` = 6 (เดิม 44) · ไม่มีไฟล์ >500 · ไม่มี TODO/FIXME · `test_layer_rules` 14 passed |
| **2 Dynamic (boot)** | boot จริง + ยิง endpoint | ✅ `GET /`=200, `/healthz`=200, `/api/status` JSON ถูก (equity=1000, kill_switch=false), `/api/strategies`=200 · feed degrade สวย (sandbox บล็อก WS) |
| **3 Financial** | เลขจอ = ledger? fee สองขา? Decimal ล้วน? | ✅ `test_honesty_guard`: status.equity/cash==treasury.cash, pnl_today==realized_today (net), close_position หัก fee ทั้งสองขา · ไม่มี `float(` ในเส้นเงิน |
| **4 รั้วความเสี่ยง** | order>cap reject? floor/loss-cap/H1 บังคับ? learning แตะไม่ได้? | ✅ `test_risk_fence_immutable` 7 + `test_real_money_matrix` 21: hard-cap reject+CRITICAL, survival_floor/hard-cap ไม่อยู่ใน tunable set, bracket H1 atomic |
| **5 Concurrency/race** | publish-before-subscribe / double-entry / id() collision | ✅ 15 passed (`dropped_messages`, `seen_ids_bounded`, `crash_recovery`, `trades_actually_fire`, `_noid_seq` counter) |
| **6 Persistence** | kill→reboot state กลับมา? WAL? | ✅ 29 passed (`crash_recovery`, `sqlite_wal`, `memory_persistence`, atomic snapshot) |
| **7 Self-improvement** | bounded range? แตะ risk ไม่ได้? log? | ✅ `_apply_params` ปฏิเสธค่านอกกรอบ + risk-fence keys · ทุกการปรับ log ลง control audit · learner ปรับจาก hit-rate จริง |
| **8 Resilience** | kill agent → restart? feed หลุด degrade? | ✅ watchdog auto-restart (`test_agents`, `test_runtime`) · feed unavailable ไม่ crash (boot จริง) |
| **9 Resource/leak** | queue/deque/seen_ids bounded? | ✅ 22 passed (`memory_bounds`, `seen_ids_bounded`, `load_scaling`) |
| **10 Honesty + data** | ไม่มี fake data? metric จาก ledger? CSV ครบ? | ✅ `test_honesty_guard` 6 · CSV มี fee/slippage/gross/net/strategy/regime/win_prob · `daily_summary.csv` reconcile กับ ledger เป๊ะ |

---

## คำสั่ง verify ที่รัน (ผลจริงด้านบน)
```
pytest tests/architecture/                         → 35 passed
pytest -k "race or dropped or seen_ids or crash_recovery"  → 15 passed
pytest -k "persist or wal or sqlite or memory_persist"     → 29 passed
pytest -k "bounds or bounded or memory or load_scaling"    → 22 passed
ruff check src tests                               → clean
mypy --strict src/                                 → Success (125 files)
pytest -q --cov=src --cov-fail-under=90            → 733 passed / cov 90.56%
boot smoke                                         → GET / 200, /api/status equity=1000
```

---

## ⚠️ สิ่งที่เจ้าของควรตรวจเองปิดท้าย
1. เปิด `data/trades_*.csv` เทียบเลขกับตาดู (คอลัมน์ pnl_net/fee_paid)
2. ลอง POST `/api/risk/settings {"max_single_order_thb":"5000"}` → ต้อง **reject** (เกิน hard cap 1,000)
3. กด KILL_SWITCH → arm live ต้องถูก block (ข้าม restart ด้วย)
4. ปล่อย paper จนถึง 5% → ต้องล็อกกำไร (block BUY ใหม่)
5. ปิด-เปิดใหม่ → state (`data/state.db`) ไม่หาย

> **ไม่เคลมว่า "ปลอดภัย 100% / ไม่มีบั๊ก / พร้อมเทรดเงินจริง"** — รายงานได้แค่สิ่งที่ verify จริงตามตารางบน
> การเปิด live เงินจริงต้องผ่าน **paper track record หลายสัปดาห์ + edge validation (walk-forward/OOS)** ก่อนเสมอ
