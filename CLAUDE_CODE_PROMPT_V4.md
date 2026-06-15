# THE KING DOME PRIME — V4: SUPER ULTRA & THE LIVING COMPANY (run AFTER V3's P12)

> วิธีใช้: รอ V3 (P7–P12) จบและ commit ครบ → New session ที่ root `trading-system-v2` → วางไฟล์นี้ทั้งไฟล์ → effort Low

---

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
