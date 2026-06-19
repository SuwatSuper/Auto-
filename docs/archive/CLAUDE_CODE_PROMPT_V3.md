# THE KING DOME PRIME — UPGRADE MISSION V3 (SUPERSEDES V2 — run AFTER P0–P6)

> วิธีใช้: รอ run เดิม (P0–P6) จบและ commit ครบ → New session ที่ root ของ `trading-system-v2` → วางไฟล์นี้ทั้งไฟล์ → effort Low
> ไฟล์นี้แทนที่ CLAUDE_CODE_PROMPT_V2.md ทั้งฉบับ ถ้ามี commit P7+ จาก V2 อยู่แล้ว: สเปคในไฟล์นี้ชนะเสมอเมื่อขัดกัน

---

## PRECONDITION CHECK (do this before anything)

```
git log --oneline | head -30
python -m pytest -q && python -m ruff check src tests scripts && python -m mypy
```

Commits `P0:`–`P6:` must exist and the suite must be green. If not: open `CLAUDE_CODE_PROMPT.md`, finish the missing phases under its rules first, then return here.

## EXECUTION CONTRACT

All rules from `CLAUDE_CODE_PROMPT.md` remain in force verbatim: phases strictly in order P7→P12, VERIFY after each phase with real output appended to `SCORECARD.md` (section `## V3`), commit per phase, complete code only, layer header comments, Layer 1 = stdlib+pydantic only, Decimal-only money, ports not concretes, **no live order execution ever** (paper only), offline static assets, never weaken a test, do not ask the user anything.

Stack stays: FastAPI + vanilla-JS dashboard + SQLite/JSONL behind existing ports. PostgreSQL/Redis/Docker/React/PySide6 deferred → `docs/ADR-0004-deferred-infra.md`.

## CEO DESIGN ORDERS (2026-06-12) — what V3 exists to deliver

1. **Trade frequently, every day.** The system hunts opportunities all day across symbols/strategies/timeframes. The daily profit band is +3% (protect) / +5% (capture & stop). "No trade" is still allowed when guards trip — capital preservation outranks the target, per the owner's own spec.
2. **Diversification.** Three axes: symbols (THB_BTC, THB_ETH, THB_XRP on Bitkub — this CEO order overrides the earlier BTC-only line; record in ADR-0005), strategies (regime-routed), timeframes (1m + 5m).
3. **Every running component is a visible agent on the dashboard. No lying.** Each chibi maps 1:1 to a real running task with a live heartbeat. No decorative/ghost agents.
4. **Dashboard is the only control surface.** Every tunable parameter and every action is operable from the dashboard at runtime, no restarts, no .env edits.

## NON-NEGOTIABLE HONESTY RULES (each enforced by a named test)

- **H1** Every paper entry creates a bracket (stop-loss + take-profit) atomically at fill. No code path or setting opens a position without a stop. `test_entry_without_stop_is_impossible`.
- **H2** Losses are realized and counted. Forbidden by behavior tests: averaging down, widening/removing a stop after entry, holding a loser past its stop, excluding any closed trade from stats. `test_no_averaging_down`, `test_stop_cannot_be_widened`, `test_all_closed_trades_counted`.
- **H3** Every performance number on API/dashboard/reports is recomputed by the Auditor from the event store incl. fees+slippage. `test_status_numbers_come_from_auditor`.
- **H4/H6** No guaranteed-profit claims anywhere. Static scan fails on strings: `100% win`, `guaranteed`, `รับประกันกำไร`, `การันตีกำไร`. The daily-target widget label (TH/EN): "เป้าเก็บกำไรรายวัน — เพดานหยุดเทรด ไม่ใช่การรับประกันผลตอบแทน / Daily capture cap — a stop point, not a promised return." `test_no_guarantee_claims`.
- **H5 — Agent Truth.** (a) All background tasks in src/ are created ONLY via `runtime.spawn(name, coro)` which registers them in a task registry (grep/AST test: `asyncio.create_task(` appears nowhere in `src/` outside `runtime.spawn`'s own body and FastAPI internals in `web/`). (b) Every registered agent reports `last_beat_ms` (heartbeat each loop iteration). (c) `/api/status.agents` == runtime registry == what the dashboard renders; a stale heartbeat (> 5s) must render the chibi as FROZEN state, never hidden. Tests: `test_agent_registry_status_parity`, `test_heartbeat_stale_flag`, `test_no_unregistered_tasks`.

---

## PHASE 7 — GOVERNANCE + ALLOCATION DOMAIN (Layer 1, pure, TDD — tests first)

Package `src/domain/governance/` (frozen pydantic models, pure functions, clock values passed in, exhaustive boundary tests):

1. **`capital_preservation.py`** — unchanged authority, supreme veto:
   - Drawdown tiers: dd ≥ 15% → `HALT_24H`; ≥ 20% → `HALT_72H`; ≥ 25% → `HALT_UNTIL_CEO_APPROVAL`. `evaluate_drawdown(peak_equity, current_equity, now_ms, existing_halt) -> HaltState(kind, until_ms|None, requires_ceo)`. Halts never shorten; CEO approval is the only release for the 25% tier.
   - `survival_veto(order_qty, entry_price, stop_price, fee_bps, equity, initial_capital, floor_pct=Decimal("0.70")) -> RiskDecision` — worst-case loss = qty×|entry−stop| + round-trip fees; veto reason `SURVIVAL_FLOOR` if equity − worst_case < floor_pct × initial_capital.
   - Tests at 14.99/15.00/19.99/20.00/24.99/25.00 + survival math hand-computed.

2. **`daily_profit.py`** — `TradePolicy: NORMAL | RISK_HALF_LOCK | HALT_FOR_DAY`. `daily_policy(daily_pnl_pct, *, soften_at=Decimal("3.0"), halt_at=Decimal("5.0"))`:
   - ≥ +5.0% → `HALT_FOR_DAY`: **close ALL open positions at market to lock the day's gain**, block new entries until next UTC midnight.
   - ≥ +3.0% → `RISK_HALF_LOCK`: halve risk per trade AND tighten every open position's stop to `max(current_stop, breakeven ± fees)` (direction-aware; stops only ever tighten — pure helper `tighten_stop(side, entry, current_stop, fee_bps) -> Decimal` with tests).
   - Tests at 2.99/3.00/4.99/5.00, negative pnl, and the never-loosen property.

3. **`loss_guardian.py`** — consecutive realized losses portfolio-wide: ≥3 → RISK_HALF, ≥5 → SAFE_MODE, ≥7 → HALT_24H; a realized win resets to 0. Pure reducer + sequence tests (L3, L5, L7, L2-W-L2, exits allowed during SAFE_MODE).

4. **`safe_mode.py`** — active → risk ×0.25, entries blocked, exits allowed. Activated by guardian/sentinel/CEO; deactivated only by CEO. Tests.

5. **`regime.py`** — `classify_regime(adx, atr_pct, bb_width_pct, realized_vol_pct, params) -> TRENDING|SIDEWAYS|VOLATILE` (defaults: VOLATILE if rvol ≥ 2.0 or atr_pct ≥ 1.5; else TRENDING if adx ≥ 25; else SIDEWAYS). `risk_multiplier`: TRENDING 1.0, SIDEWAYS 0.5, VOLATILE 0.3. **Strategy routing map** `strategy_for(regime)`: TRENDING → "ema_cross", SIDEWAYS → "rsi_reversion", VOLATILE → None (no entries). Tests per branch.

6. **`confluence.py` — SetupGate (frequency-tuned).** `EntryInputs`: signal_action, signal_confidence, regime, sentiment_score, micro_imbalance, spoof_score, p_win, trend_agree, timeframe. `evaluate_entry(inputs, params) -> EntryDecision(approved, reasons)`; reason codes: `NO_SIGNAL, LOW_CONFIDENCE, REGIME_VOLATILE_BLOCKED, STRATEGY_REGIME_MISMATCH, SENTIMENT_OPPOSED, MICRO_OPPOSED, SPOOF_RISK, P_WIN_BELOW_MIN`. **Defaults for daily-hunting mode: min_confidence 0.50, min_p_win Decimal("0.58"), max_spoof 60; SIDEWAYS entries allowed (reversion strategy), VOLATILE blocked.** All params come from a `GateParams` model so the runtime ParamStore (P9) can hot-swap them. Docstring states plainly: raising min_p_win raises selectivity and lowers trade count; no setting guarantees outcomes. Tests: one per reason + all-pass + param-injection test.

7. **`allocation.py` — Diversification engine (pure).**
   - `AllocationLimits`: `risk_per_trade_pct=Decimal("1.0")`, `max_symbol_exposure_pct=Decimal("25.0")`, `max_concurrent_positions=3`, `max_positions_per_symbol=1`.
   - `size_order(equity, entry_price, stop_price, limits, risk_multiplier) -> Decimal` — qty = (equity × risk_per_trade_pct/100 × risk_multiplier) / |entry−stop|, quantized; returns 0 if stop distance is 0.
   - `check_allocation(proposed_symbol, proposed_notional, open_positions: Mapping[symbol, notional], equity, limits) -> RiskDecision` with reasons `MAX_CONCURRENT_REACHED, SYMBOL_EXPOSURE_EXCEEDED, ALREADY_IN_POSITION`.
   - Hand-computed sizing tests + every rejection reason + the diversification property (with 25% cap and 3 slots, no single symbol can exceed 25% of equity — hypothesis test over random sequences).

8. **`explain.py`** — `GateRecord(gate, verdict, reasons, values)`, `DecisionExplanation(order_ref, records, final)`, `summarize()` → "BUY THB_ETH เพราะ: Signal ✓, Regime TRENDING ✓, p_win 0.61 ✓, Allocation ✓, Risk ✓, Capital Preservation ✓". Tests.

### VERIFY P7
```
python -m pytest tests/domain/governance -q
python -m pytest -q && python -m ruff check src tests && python -m mypy
```
Commit `P7: governance — daily 3/5% capture band, loss guardian, regime routing, frequency-tuned gate, allocation engine`.

---

## PHASE 8 — CANDLES + INDICATORS (Layer 1)

1. **`src/domain/analytics/candles.py`** — `Candle(open_ms, open, high, low, close)`; `build_candles(ticks, interval_ms)` pure aggregation (used for both 60_000 and 300_000 ms); partial last candle excluded. Hand-built tick-list tests for both intervals.
2. **`src/domain/analytics/volatility.py`** — over candles/closes, Decimal in/out: `atr(candles, 14)` (Wilder, TR uses prev close), `adx(candles, 14)` (full ±DI/DX/ADX chain), `bollinger_width_pct(closes, 20, 2)`, `realized_vol_pct(closes, 30)`, `profit_factor(pnls)`, `sharpe(returns)` (stdev 0 → 0). Each with a small hand-computed vector in test comments (e.g., ATR period 3 over 6 candles).

### VERIFY P8
```
python -m pytest tests/domain -q && python -m pytest -q
python -m ruff check src tests && python -m mypy
```
Commit `P8: candles 1m/5m, ATR/ADX/BB/rvol, PF, sharpe`.

---

## PHASE 9 — ORCHESTRATION: MULTI-SYMBOL, AGENT TRUTH, LIVE PARAMS (Layer 2)

**Settings additions** (defaults): `symbols=["THB_BTC","THB_ETH","THB_XRP"]`, `initial_capital=Decimal("1000")`, `stop_pct=Decimal("1.0")`, `take_profit_pct=Decimal("1.5")`, `fee_taker_bps=Decimal("25")`, `daily_soften_pct=Decimal("3.0")`, `daily_halt_pct=Decimal("5.0")`, plus GateParams + AllocationLimits defaults. Extend `Symbol` StrEnum with THB_ETH, THB_XRP (additive — THB_BTC untouched).

1. **Multi-symbol feeds.** BitkubWebSocketGateway accepts a list of streams and builds the multi-stream URL (`market.ticker.thb_btc,market.ticker.thb_eth,...`); normalizer resolves symbol from the stream/sym field (extend `normalize_bitkub_ticker` additively — existing tests untouched, new tests for ETH/XRP payloads). SimulatorGateway emits all configured symbols, each with its own seeded walk (seed = 42 + index). Per-symbol topics `prices.thb_btc.v1`, `prices.thb_eth.v1`, `prices.thb_xrp.v1` (the BTC topic name is unchanged = back-compat).

2. **`runtime.spawn(name, coro)` + heartbeats (H5).** Central task registry: every background task in src/ is created only through spawn; registry holds {name, task, started_ms, last_beat_ms}. BaseAgent beats every loop iteration; supervisors beat on supervise ticks. `status()` exposes per-agent `last_beat_ms` and computed `stale: bool` (>5000ms). Implement the H5 tests from the honesty section now.

3. **Per-symbol pipelines.** For each enabled symbol spawn: CandleAgent (1m AND 5m candles → `candles.{sym}.1m.v1` / `.5m.v1`), RegimeFilterAgent (per symbol, on 1m closes), EntryExitAgent (regime-routed: runs `strategy_for(regime)` — EmaCross on TRENDING using both 1m+5m confirmation `trend_agree`, RsiReversion on SIDEWAYS using 1m; emits exit signals on reversal), MicrostructureAgent (5s scan per symbol; live = Bitkub depth REST via stdlib urllib in `asyncio.to_thread`, simulator = deterministic synthetic book; spoof scoring pure math in `domain/analytics/microstructure.py` per the ±0.5%/15s rule, tests over synthetic snapshots), ProbabilityAgent (per symbol×regime, Laplace `(wins+1)/(n+2)`, rolling 200).

4. **GovernanceGate (portfolio-level brain, single agent).** Consumes all `signals.*`; for each entry signal runs the authority chain, one GateRecord per stage:
   1. SetupGate (confluence, hot params)
   2. Regime risk multiplier
   3. **Allocation** — `size_order` (1% risk × multipliers) then `check_allocation` (max 3 concurrent, 25%/symbol, 1/symbol)
   4. DailyProfit policy (HALT_FOR_DAY blocks entries; RISK_HALF_LOCK halves size + tightens stops)
   5. LossGuardian policy
   6. SafeMode policy
   7. RiskAgent domain limits
   8. **CapitalPreservation final veto** (drawdown tiers + survival_veto + kill switch) — nothing overrides this.
   Approved → order (DecisionExplanation attached) → approval queue if `require_approval` else execute; Rejected → rejection envelope with full chain. Tests: stage-7-approves-stage-8-vetoes hierarchy proof + one rejection per stage + a multi-symbol test (BTC position open → ETH entry approved → 4th concurrent rejected `MAX_CONCURRENT_REACHED`).

5. **SimulationAgent / PositionManager (multi-symbol).** Brackets atomic at fill (H1); per-price-event checks stop/tp per symbol; closes on opposite confirmed signal; `ALREADY_IN_POSITION` rejection enforces H2 no-averaging; realized results feed guardian/probability/daily-pnl (vs initial_capital, UTC day). Daily HALT closes all positions market-wide to lock gains. Halt states persisted with until_ms — restart mid-halt stays halted (test).

6. **BlackSwanSentinel (portfolio).** Per-symbol |1m return| ≥ 3% OR feed gap > 30s on any symbol → flatten ALL positions, SAFE_MODE on, CRITICAL `alerts.v1`, CEO banner. FixedClock tests.

7. **AuditorAgent.** Every 10s recompute portfolio-wide + per-symbol: gross, fee_total, slippage_cost, net, win_rate, PF, trade_count; reconcile vs equity (tol 0.01); publish `audit.v1`; `/api/status` performance numbers read ONLY from auditor (H3 test).

8. **ParamStore (dashboard-only control).** StateStore-backed hot parameter table read by gates on every evaluation: whitelist = {min_p_win, min_confidence, max_spoof, stop_pct, take_profit_pct, risk_per_trade_pct, max_symbol_exposure_pct, max_concurrent_positions, daily_soften_pct, daily_halt_pct, require_approval, symbol_enabled.{sym}, strategy_enabled.{name}}. Every change is appended to the EventStore as `params.v1` (audit trail). Test: change min_p_win via ParamStore → next gate decision uses it without restart.

### VERIFY P9
```
python -m pytest tests/orchestration -q && python -m pytest -q
python -m ruff check src tests && python -m mypy
```
Commit `P9: multi-symbol pipelines, allocation in chain, agent-truth registry, hot ParamStore`.

---

## PHASE 10 — DASHBOARD: KING DOME PRIME CONTROL CENTER (Layer 3)

1. **API**: `GET/POST /api/params` (POST = API-key, whitelist-validated, returns applied values), `GET /api/audit`, `GET /api/regime` (per symbol), `GET /api/halts`, `GET /api/positions`, `POST /api/safe_mode/{on|off}`, `POST /api/ceo_approval`, `POST /api/agents/{name}/restart`, existing approve/reject reused. Status adds: per-symbol {price, regime, p_win, position}, portfolio {equity, drawdown_pct, daily_pnl_pct, policy, consecutive_losses, exposure_per_symbol_pct}, audit block, alerts, halt block, safe_mode, and per-agent {heartbeat_ms_ago, stale}.

2. **Factory floor (extend, keep chibi system)**: three production lines (BTC 🟠 / ETH 🔵 / XRP ⚫), each line shows its own pipeline chibis + regime badge + mini price ticker; Capital Preservation office above Supreme; Auditor desk; Sentinel tower. **Agent roster is rendered from `/api/status.agents` only** — every registered agent appears, stale heartbeat renders FROZEN (gray, ❄), restart button per chibi (H5 on screen).

3. **CEO Control Center panel** (all = the only control surface): sliders/inputs bound to `/api/params` with live apply + toast (min_p_win 0.50–0.95, stop %, TP %, risk/trade %, max concurrent, symbol toggles, strategy toggles, require_approval, daily 3/5 thresholds), Safe Mode toggle, CEO-approval button (appears at the 25% tier), Start/Pause/E-Stop/Reset as before.

4. **Daily target widget**: progress bar 0 → 3% (amber "ลดเสี่ยง+ล็อกทุน") → 5% (green "เก็บกำไร หยุดวันนี้") with the H4/H6 label verbatim; countdown to UTC midnight while halted. **Diversification widget**: exposure-per-symbol donut (hand-drawn canvas, no libs) + open-positions table (symbol, side, qty, entry, stop, tp, uPnL) — stops shown are the real bracket values from state (truth).

5. **Explainability modal** unchanged from V2 spec: click any trade/rejection → full gate chain ✅/❌ + values + `summarize()`; TH/EN i18n parity for every new key. Static budget ≤ 220 KB, offline scan, textContent-only, forbidden-claims scan (H4/H6) — all as pytest static tests.

### VERIFY P10
```
python -m pytest tests/web -q && python -m pytest -q
python scripts/run.py --simulator   # smoke: 3 lines live, change min_p_win from the panel and watch rejections flip, restart an agent, open an explanation; then stop
python -m ruff check src tests scripts && python -m mypy
```
Commit `P10: control center, 3-symbol floor, agent-truth UI, daily capture widget`.

---

## PHASE 11 — BACKTEST + ACCEPTANCE (Layer 1 + scripts)

1. FeeModel default 25 bps everywhere; goldens re-derived BY HAND in comments.
2. `BacktestReport` adds gross_profit, net_profit, fee_total, profit_factor, sharpe (keep slippage_cost); backtester upgraded to run the full V3 chain (gate→allocation→governance) over multi-symbol series.
3. `src/domain/backtest/acceptance.py` — criteria per spec: PF > 1.50, MDD < 15%, expectancy > 0, Sharpe > 1.00, win_rate 45–60% band (above band → REVIEW, below → FAIL). Tests per criterion + REVIEW path.
4. `scripts/backtest_run.py` — seeded 90-day 1m synthetic series ×3 symbols (`random.Random(20260612+i)`), full chain, prints report + acceptance table + per-symbol breakdown; run it, paste into SCORECARD; determinism ×3 via canonical-JSON SHA256.

### VERIFY P11
```
python -m pytest -q && python scripts/backtest_run.py
python -m ruff check src tests scripts && python -m mypy
```
Commit `P11: multi-symbol backtest, Bitkub fees, 90-day acceptance`.

---

## PHASE 12 — FINAL VERIFY + SCORECARD V3 + DOCS

1. Docs: ARCHITECTURE (authority chain + 3-line floor diagram), EVENTS (per-symbol topics, params.v1, audit.v1, alerts.v1, explanation payload), RUNBOOK (daily 3/5 band behavior, halts 15/20/25, safe mode, CEO release, what survives restart, how to tune from the panel), ADR-0003 (selectivity vs guaranteed win-rate — keep), **ADR-0005-multi-symbol-diversification.md** (CEO order overrides BTC-only; allocation rules), ADR-0004 unchanged. README rebrand + quick-start.
2. `SCORECARD.md` → `## V3 FINAL`: 13 categories re-evidenced + **Honesty table H1–H6 → test names** + backtest acceptance table + halt-persistence restart proof + agent-truth parity proof.
3. Finish only when all green and pasted:
```
python -m ruff check src tests scripts
python -m mypy
python -m pytest -q
python -m pytest -q
python -m pytest -q
python scripts/bench_bus.py
python scripts/backtest_run.py
```
Commit `P12: King Dome Prime v3 complete`.
