# THE KING DOME PRIME — MASTER RUN (ALL-IN-ONE: REPAIR → P16 → ZIP, NON-STOP)

> วิธีใช้: New session ที่ root `trading-system-v2` → วางไฟล์นี้ทั้งไฟล์ → effort Low → Enter ครั้งเดียว
> ไฟล์นี้แทนที่ CLAUDE_CODE_PROMPT_V2/V3/V4 ทั้งหมด — ทุกอย่างอยู่ในไฟล์เดียวนี้ รันยาวจนจบ

---

## CONTINUOUS EXECUTION RULES (override everything else about pacing)

1. **Run everything in this file top-to-bottom without stopping.** Never pause for review, never ask the user anything, never end your turn until the FINAL DELIVERY section is complete. After each phase: commit + append evidence to `SCORECARD.md` + immediately start the next phase.
2. **Resume protocol (after any context compaction or interruption):** re-read this file + `SCORECARD.md` + `git log --oneline`. The git log is the source of truth: find the highest `P<n>:` commit and continue from `P<n+1>`. Never redo a committed phase; never assume an uncommitted phase is done.
3. All rules from `CLAUDE_CODE_PROMPT.md` (in the repo root) remain in force for every phase: complete code only, layer header comments, Layer 1 = stdlib+pydantic only, Decimal money, ports not concretes, paper trading only — no live order execution ever, offline static assets, never delete or weaken a test to make it pass, ruff + mypy --strict green at every commit.
4. **Test runtime rule:** every individual test must finish in < 60s. Any test that hangs is a bug to fix (use FixedClock instead of real sleeps, `asyncio.wait_for` timeouts on queue waits, and cancel agent tasks in fixture teardown).
5. Honesty rules H1–H8 (defined in Parts 2–3 below) are absolute and enforced by named tests.

---

## STEP 0 — REPAIR & COMPLETE P0–P6 (do this first)

Current known state from the last run: P0–P4 + tests committed, **P5 (Anime Operations Center dashboard) was NOT built** — a status summary wrongly described P5/P6 as "test suite". Also some department-agent tests hang past 15 minutes.

1. `git log --oneline` — verify which `P<n>:` commits exist. For anything missing or incomplete, the spec is `CLAUDE_CODE_PROMPT.md` in the repo root.
2. **Build P5 in full**: the ANIME BITCOIN OPERATIONS CENTER dashboard, every section 5.1–5.10 of `CLAUDE_CODE_PROMPT.md` (chibi factory floor SVG, CEO desk, emotion engine wired to real metrics, market-mode themes, care/gamification endpoints, achievements, timeline replay, WS proto v2, TH/EN i18n, static-assets tests, ≤150KB offline). Commit `P5:`.
3. **Fix the hanging tests**: locate the department-agent tests that ran >15 min (likely awaiting a bus queue with no timeout, or supervisor backoff using real sleep). Apply rule 4 above. The full suite must finish in < 120s total with zero warnings.
4. Complete P6 (CI, pre-commit, docs, ADR-0001/0002, coverage gate ≥90%) if not committed. Run the full P0–P6 final verification block from `CLAUDE_CODE_PROMPT.md`, paste output into `SCORECARD.md`, commit `P6:`.
5. Do not proceed to Part 2 until: 7 commits `P0:`–`P6:` exist, suite green < 120s, zero warnings, ruff + mypy clean.

---

# PART 2 — KING DOME PRIME PHASES P7–P12

(Original V3 mission. The "supersedes V2" framing stands; specs below are authoritative.)

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

---

# PART 3 — SUPER ULTRA & THE LIVING COMPANY: PHASES P13–P16

## PRECONDITION CHECK

```
git log --oneline | head -40
python -m pytest -q && python -m ruff check src tests scripts && python -m mypy
```

Commits `P0:`–`P12:` must all exist, suite green. If V3 phases are missing: finish `CLAUDE_CODE_PROMPT_V3.md` first, then return here.

## EXECUTION CONTRACT

All rules from `CLAUDE_CODE_PROMPT.md` + V3 honesty rules H1–H6 remain in force verbatim. Phases strictly P13→P16, VERIFY + SCORECARD (`## V4`) + commit per phase, complete code only, paper trading only, Layer rules enforced, never weaken a test.

New honesty rules added in this mission:

- **H7 — Optimizer bounds.** The optimizer may change ONLY whitelisted gate/sizing params within hard clamps. It can NEVER touch: capital-preservation tiers, survival floor, daily 3/5% band, fee model, stop existence (H1), kill switch, safe mode. Attempting a forbidden key is filtered and logged. `test_optimizer_cannot_touch_forbidden_keys`, `test_optimizer_clamps_out_of_range`.
- **H8 — Honest intelligence labels.** News sentiment is lexicon-based keyword scoring; the UI widget carries tooltip (TH/EN): "วิเคราะห์จากคำสำคัญในพาดหัวข่าว ไม่ใช่ความเข้าใจข่าวแบบมนุษย์ / Keyword-lexicon scoring of headlines, not human-level comprehension." Static scan test includes this label's presence and still forbids all guarantee claims. `test_news_label_present`.

---

## PHASE 13 — TRUE COMPOUNDING SEMANTICS (Layer 1 + 2)

1. **Start-of-day equity baseline.** Runtime snapshots `start_of_day_equity` at each UTC midnight rollover (and on first boot of a day), persisted via StateStore. `daily_pnl_pct = (equity − start_of_day_equity) / start_of_day_equity × 100`. The 3/5% band from V3 now reads this value — so on winning days the next day's band is measured from the new, larger base. Update `daily_profit` call sites + tests; rollover test with FixedClock crossing midnight.
2. **Equity-based sizing verification (compounding proof).** `size_order` already takes live equity — add the explicit test `test_compounding_two_green_days`: simulate day 1 ending +4% (positions closed, day locked), roll to day 2, assert the first order's qty on day 2 > the first order's qty on day 1 under identical prices/stops. Also `test_drawdown_shrinks_size` (red day → smaller next size). This is the mechanical compound-interest behavior: profits enlarge the base automatically; losses shrink it.
3. **Status additions**: `start_of_day_equity`, `compound_growth_pct = (equity/initial_capital − 1) × 100`, and a `days_green / days_red / days_flat` counter persisted across restarts (test). Dashboard CEO desk shows "Compound Growth" big number + a 30-day daily-return strip (tiny green/red/gray squares, canvas-drawn, from EventStore daily summaries).

### VERIFY P13
```
python -m pytest -q && python -m ruff check src tests && python -m mypy
```
Commit `P13: compounding — start-of-day baseline, equity-scaled sizing proofs, growth widgets`.

---

## PHASE 14 — INTELLIGENCE AGENTS: NEWS, HISTORY, MEETINGS (Layers 1+2+3)

1. **News sentiment domain** — `src/domain/analytics/news_sentiment.py` (Layer 1, pure): weighted lexicon as a frozen mapping — ≥ 40 English terms (e.g., "etf approval"+3, "halving"+2, "adoption"+2, "rally"+2, "hack"−4, "ban"−3, "lawsuit"−2, "crash"−3 …) and ≥ 20 Thai terms ("อนุมัติ"+2, "แฮ็ก"−4, "ฟ้อง"−2, "พุ่ง"+2, "ร่วง"−2 …). `score_headlines(headlines: Sequence[str]) -> SentimentReading(score: Decimal −1..1, fear_greed: Decimal 0..100, matched_terms: tuple[str,...])` — case-insensitive, multi-word phrases matched first, score = clamped weighted mean, fear_greed = 50 + score×50. Tests with crafted TH/EN headline sets incl. exact expected Decimals, empty input → neutral 0/50.
2. **NewsReaderAgent** — port `NewsFeed(Protocol): async fetch_headlines() -> list[str]`; adapters: `RssNewsFeed` (Layer 3, stdlib `urllib.request` + `xml.etree`, 10s timeout, parses `<item><title>` from each URL in `Settings.news_rss_urls` — defaults to two public crypto RSS URLs; failures logged, return []) and `SimulatedNewsFeed` (deterministic seeded synthetic headlines cycling bull/bear/neutral). Agent polls every `Settings.news_poll_s=300`, publishes `news.v1` {headline_count, score, fear_greed, top_headline, matched_terms}; this score now feeds SetupGate's `sentiment_score` input (replacing the price-derived proxy in live mode; proxy remains the simulator fallback). Tests use a fake feed — no network in tests. H8 label on the dashboard news widget.
3. **Historical backfill** — port `HistoryFeed(Protocol): async fetch_candles(symbol, resolution_min, n) -> list[Candle]`; adapter `BitkubHistoryFeed` (Layer 3, public TradingView-style OHLC REST endpoint from `Settings.bitkub_history_url`, stdlib urllib, parsed into domain Candles) and `SimulatedHistoryFeed` (30 seeded days). On boot, runtime backfills each enabled symbol's CandleAgent (so ATR/ADX/strategies are warm immediately instead of waiting an hour) and stores a `history_backfilled` marker event. **HistoricalResearchAgent upgrade**: over the full candle history compute lifetime max_drawdown, longest bull/bear segments (regime classification applied across history), 30-day realized vol — publish enriched `research.v1`. Tests with a canned JSON fixture file (no network).
4. **Meeting Protocol (the company coordination).** Supreme assembles `MeetingMinutes` envelope every `Settings.meeting_interval_s=3600` AND immediately on any CRITICAL alert: {period, regime per symbol, sentiment reading, research summary, p_win per symbol, trades/wins/losses this period, daily_pnl_pct, policy, open positions, alerts, optimizer last action (P15)}. Published to `meetings.v1`, persisted via EventStore. Dashboard "Open Meeting" modal renders the latest minutes as the meeting room scene (chibis of contributing agents seated around a table, each with their one-line summary). Test: minutes assembled from latest envelopes, emergency meeting fired on CRITICAL.

### VERIFY P14
```
python -m pytest -q && python -m ruff check src tests && python -m mypy
python scripts/run.py --simulator   # smoke: news widget live with H8 label, meeting modal shows minutes; stop
```
Commit `P14: news lexicon agent, historical backfill, research upgrade, meeting protocol`.

---

## PHASE 15 — SUPER ULTRA AGENT (Self Learning Lab → AUTO mode)

The owner's spec defines a Self Learning Lab that analyzes backtests and proposes improvements. V4 realizes it as **SuperUltraAgent** with auto-apply, bounded by H7. Org position: above Supreme, **below Capital Preservation** — it tunes the hunt; it can never loosen survival.

1. **Walk-forward optimizer domain** — `src/domain/optimize/walkforward.py` (Layer 1, pure, deterministic):
   - `ParamGrid` model: candidate values per whitelisted key — `min_p_win` {0.55,0.60,0.65,0.70,0.75,0.80}, `min_confidence` {0.40,0.50,0.60}, `stop_pct` {0.5,1.0,1.5,2.0}, `take_profit_pct` {1.0,1.5,2.0,3.0}, `risk_per_trade_pct` {0.5,1.0,1.5,2.0}.
   - `walk_forward(candles, grid, engine_params) -> OptimizationResult`: split the window into train 5d / validate 2d (rolling); run the existing backtest engine per candidate on train, take the top 5 by net_profit, re-run those on the **validation** segment; winner = best validation net_profit subject to constraints PF ≥ 1.2, MDD ≤ 10%, trades ≥ 5; no candidate qualifies → result `NO_CHANGE` with reason. Ties → higher PF. Returns winner params + full evidence (train/validate reports).
   - Tests: synthetic series engineered so a known param set must win; NO_CHANGE path; determinism (same inputs → same winner, SHA256 of canonical result ×3).
2. **SuperUltraAgent (Layer 2)** — every `Settings.optimize_interval_s=21600` (6h) and on demand:
   - Pull last 7 days of 1m candles per enabled symbol (history + live store), run `walk_forward` per symbol×routed-strategy.
   - **Mode AUTO (default ON per CEO order, dashboard-toggleable + lockable):** apply winner via ParamStore (H7 clamps enforced at apply), save `last_known_good` (the params active before the change + their realized 7d net), publish `optimizer.v1` {mode, before, after, evidence}.
   - **Auto-revert:** at each run, first evaluate realized net since the last apply; if it is negative while `last_known_good`'s trailing baseline was positive, or underperforms baseline by > 20%, revert to `last_known_good`, mark the change FAILED in `optimizer.v1`, then continue the new optimization.
   - **Mode APPROVAL:** park the winner as a pending proposal; `GET /api/optimizer/proposals`, `POST /api/optimizer/{id}/approve|reject` (API-key).
   - `POST /api/optimize/run` triggers an immediate cycle (rate-limited 1/10min).
   - Tests: clamp + forbidden-key tests (H7), apply→ParamStore→next gate decision uses new value, revert path with crafted outcomes, proposals flow, heartbeat/registry (H5 inherited), and the invariant test `test_optimizer_cannot_modify_halt_state`.
3. **Dashboard** — Super Ultra office on the floor (🧠 chibi with crown-circuit, seated above Supreme, below the Capital Preservation shield office). Optimizer panel: AUTO/APPROVAL toggle + lock, last-run time, current vs winner params table with validation evidence numbers, pending proposals (approve/reject), change-history timeline from `optimizer.v1` events, Run Now button. The chibi goes `proud` on a successful apply, `confused` on revert. i18n TH/EN for all of it.

### VERIFY P15
```
python -m pytest tests/domain/optimize tests/orchestration -q && python -m pytest -q
python -m ruff check src tests scripts && python -m mypy
```
Commit `P15: Super Ultra — walk-forward auto-tuning with clamps, auto-revert, approval mode`.

---

## PHASE 16 — FINAL VERIFY + SCORECARD V4 + DOCS

1. Docs: ARCHITECTURE (org chart now CEO → Capital Preservation → **Super Ultra** → Supreme → departments; data flow incl. news/history/meetings/optimizer), EVENTS (news.v1, research.v1, meetings.v1, optimizer.v1), RUNBOOK (optimizer modes, lock, revert behavior, RSS configuration, backfill), **ADR-0006-walkforward-optimizer.md** (why walk-forward validation instead of in-sample picking — the overfitting guard), README update.
2. `SCORECARD.md` → `## V4 FINAL`: honesty table now H1–H8 → test names; compounding proof test names; optimizer evidence sample; 13 categories re-checked where touched.
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
Commit `P16: King Dome Prime v4 complete — the living company`.

---

# FINAL DELIVERY (only after P16 is committed and green)

1. Run the complete final gate one last time and paste all outputs into `SCORECARD.md` under `## MASTER FINAL`:
```
python -m ruff check src tests scripts
python -m mypy
python -m pytest -q
python -m pytest -q
python -m pytest -q
python scripts/bench_bus.py
python scripts/backtest_run.py
```
2. `SCORECARD.md` must end with: the 13-category table all at 10/10 with evidence, the honesty table H1–H8 → passing test names, and the git log showing commits `P0:` through `P16:`.
3. Package the complete system: create `kingdome_prime_complete.zip` at the repo root containing the entire repo EXCLUDING `.git/`, `.venv/`, `__pycache__/`, `data/`, `*.pyc` (use `git archive --format=zip -o kingdome_prime_complete.zip HEAD` — it respects the repo content exactly as committed).
4. Final message to the user: one short summary — phases completed, test count, coverage %, where the zip is. Nothing else.
