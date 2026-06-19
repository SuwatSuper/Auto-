# Events

All in-process coordination flows over the `EventBus` (`InMemoryEventBus`).
Agents are decoupled: a producer publishes to a topic, consumers subscribe. There
is **no hidden attribute coupling** between decision agents — every cross-agent
input travels on a topic below.

## Pipeline (price → order)

```
prices.thb_btc.v1 → signals.v1 → decisions.v1 → decisions.approved.v1 → paper.events.v1
                       (Supreme)     (Risk gate)        (Paper trader)
```

## Topics

| Topic | Producer(s) | Consumer(s) | Payload (key fields) |
|-------|-------------|-------------|----------------------|
| `prices.thb_btc.v1` | PriceSupervisor (Bitkub feed) | every analyst, Supreme inputs, hub, gate sources | `{price, ts_ms, symbol}` |
| `signals.v1` | EntryExit (market_analyst), trend/mean/breakout, Entry Chief | SupremeAgent | `{signal, price, ts_ms, source, confidence?}` |
| `decisions.v1` | SupremeAgent | ExecutionAgent (risk_gate), RiskAgent | `{decision, signal, decision_id, net_votes, voters}` |
| `decisions.approved.v1` | ExecutionAgent | PaperTraderAgent | approved decision / `EXECUTION_VETOED` |
| `risk.v1` | RiskAgent | (advisory; dashboard) | `{verdict, reasons}` |
| `treasury.v1` | TreasuryAgent | (audit / dashboard) | ledger events |
| `paper.events.v1` | PaperTraderAgent | trades table, CSV logger, **weighting loop** | `FILL` / `CLOSE` / `ENTRY_REJECTED` |
| `news.raw.v1` | news loop (RSS) | NewsSentimentAgent | `{score, label, headline_count}` |

### Confluence inputs (Task 1 — consumed by the entry gate via `_confluence_loop`)

The runtime's `_confluence_loop` subscribes to all of these and folds them into a
single `_confluence` cache. `_entry_gate` reads **only** that cache (never an
agent attribute), so a department influences entries solely by publishing here.

| Topic | Producer | Field used by the gate | Gate veto |
|-------|----------|------------------------|-----------|
| `timeline.v1` | TimelineAnalystAgent (Group B) | `p_win`, `p_win_samples`, `regime` | `P_WIN_BELOW_MIN`, `SAMPLE_TOO_SMALL`, regime checks |
| `sim.results.v1` | SimulationAgent / execution_agent (Group B) | `win_rate` | `SIM_WIN_RATE_LOW` (opt-in) |
| `analysis.v1` | Division chiefs (Group B) | `bias` (averaged → `swarm_bias`) | `SWARM_CONSENSUS_OPPOSED` (default on) |
| `probability.v1` | ProbabilityAgent / probability_lab (Group A) | `prob_bull` | `PROBABILITY_OPPOSED` (opt-in) |
| `sentiment.v1` | NewsSentimentAgent / news_intelligence (Group A) | `sentiment_score` | `SENTIMENT_OPPOSED` (default on) |
| `research.v1` | HistoricalResearchAgent / research_dept (Group A) | `price_pctl`, `pct_from_mean` | `PRICE_OVEREXTENDED` (opt-in) |

`sentiment` and `swarm` vetoes are ON by default (they don't fight a long-only
trend entry). The mean-reversion-flavoured vetoes (`probability`, `research`,
`sim`) are operator opt-in (`gate_probability_veto`, `gate_research_veto`,
`gate_sim_veto`) — but all six reads are always consumed and surfaced in
`/api/status` under `confluence`.

## Dynamic weighting feedback (Task 2)

```
paper.events.v1 (CLOSE: pnl_net, voters) → _weighting_loop → SourcePerformance → Supreme.update_weights
```

- Each Supreme `EXECUTE` decision carries the `voters` that made up the winning
  side; the paper trader stamps them (and the `decision_id`) onto the matching
  `FILL`/`CLOSE` events.
- `_weighting_loop` attributes each closed trade's Win/Loss to those voters.
  A source with win-rate **> 55%** is boosted (vote weight up to 2.0); **< 45%**
  is muted (weight 0.0 — its vote is ignored but it keeps a live record and can
  recover). Weights are pushed into the Supreme commander, which tallies a
  **weighted** consensus. Surfaced in `/api/status` under `dynamic_weighting`.

## Swarm consensus weighting (Task 3)

The 150-agent grid (3 divisions × 50 distinct `(timeframe, method, window)`
slices) is aggregated by division chiefs that weight each worker by its method's
measured reliability **in the current regime** (`SwarmMetaLearner`), fed from the
workers' real graded outcomes. The regime comes from the bus-fed confluence
cache. Equal-weight voting is the fallback when no meta-learner is wired.

Learned source weights and swarm reliability are persisted (`weights.learned.v1`
in the state store) and restored on startup.

## PriceUpdate Schema

```json
{
  "event_id": "uuid",
  "symbol": "THB_BTC",
  "price": "1500000.00",
  "ts_ms": 1700000000000,
  "source": "bitkub",
  "version": 1
}
```
