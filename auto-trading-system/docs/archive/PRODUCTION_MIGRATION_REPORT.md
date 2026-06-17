# Production Migration — Phase 1 Backend Complete

## What is done (backend, this session)

| Component | Layer | Status |
|---|---|---|
| `domain/audit/decision_log.py` (immutable, replayable audit ledger) | 1 | ✅ 18/18 tests pass |
| `domain/reporting/ceo_report.py` (pure CEO summary aggregator) | 1 | ✅ 23/23 tests pass |
| `orchestration/agents/ceo_agent.py` (observer; subscribes to signals/decisions/risk/paper/treasury) | 2 | ✅ wired into runtime |
| `runtime.py`: removed simulator fallback, forced `live` mode only, registered CEO as 10th agent | 2 | ✅ |
| `runtime.py.status()`: added `data_source`, `execution_engine`, `execution_warning` fields | 2 | ✅ |
| Deleted `infrastructure/gateway/simulator.py` | 3 | ✅ |
| `infrastructure/web/api.py`: added `/api/ceo/summary`, `/api/ceo/audit`, `/api/ceo/agents`; lifespan starts in `live` mode; `/api/mode/{x}` rejects anything except `live` | 3 | ✅ |
| `tests/_fixtures/FakePriceFeed`: test-only deterministic feed via DI | — | ✅ |
| All test fixtures (`test_api.py`, `test_ws.py`, `test_runtime.py`, `test_kingdom_integration.py`) re-wired to inject `FakePriceFeed` via `RuntimeDeps` instead of relying on the (removed) `SimulatorGateway` | — | ✅ |
| Updated `EXPECTED_AGENTS` (9 → 10, includes `ceo`) and metric count (`trading_agent_count 10`) | — | ✅ |
| Test contract updated: `paper_trading: True` → `execution_engine: "paper"` + `execution_warning` string | — | ✅ |

## Test results

```
283 passed, 1 warning in 14.20s
Coverage: 89% (2675 statements, 281 missed)
```

(Baseline before migration: 241 tests, 89% coverage.
This session: +42 tests for the new domain modules.)

## What is NOT done (handover for next session — see SONNET_PROMPT.md)

| Item | Why it was deferred |
|---|---|
| Strip mock data from `kingdom.html` (5 constants + `startDemoSimulator` + `simulateAgentMetrics` + hardcoded `handleStatus({equity:1284567.89,...})`) | 4 000 line HTML file; needs careful surgical edits — packaged as a Sonnet task |
| Add CEO page tab + `renderCeoPage()` | Same |
| "DATA UNAVAILABLE" empty-states across all pages | Same |
| Execution-warning banner reading `status.execution_warning` | Same |
| Extend `tests/architecture/test_paper_only.py` to block mock-data patterns in production JS | Cheap, included in Sonnet prompt |
| Update `README_TH.md`, `docs/ARCHITECTURE.md`, `SCORECARD.md` | Included in Sonnet prompt |

## What is DELIBERATELY NOT done (architectural decision)

**Live order execution against Bitkub REST.** The codebase has zero
order-placement code by design (architecture-test enforced). Writing
untested live-trading code in a single AI session puts real money at risk.
A separate migration with a Bitkub sandbox/testnet + dry-run gate +
manual approval is required before that step.

Files unchanged for this reason:
- `domain/trading/paper.py`        (paper execution math)
- `orchestration/agents/paper_trader.py`  (paper execution engine)
- `orchestration/agents/treasury_agent.py` (treasury — paper cash ledger)
- `tests/architecture/test_paper_only.py`  (live-execution guard — intentionally KEPT)
