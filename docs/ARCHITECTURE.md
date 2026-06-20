# Architecture

## Layers

- **Layer 1 — Domain**: Pure business logic. No I/O, no frameworks.
- **Layer 2 — Orchestration**: Wires domain to ports. Agents, supervisors, runtime.
- **Layer 3 — Infrastructure**: Adapters: WebSocket gateway, in-memory bus, FastAPI API.

## Dependency Rule

Layer N may only import from Layer N or lower. Infrastructure never imports from Orchestration or Domain by default; Orchestration imports Domain; Domain imports nothing external.

## Key Components

- `PipelineRuntime`: Starts/stops feed, supervisor, agents.
- `InMemoryEventBus`: Pub/sub bus shared across the system.
- `PriceSupervisor`: Reads from feed, normalizes, publishes to bus.
- `SampleAgent`: Subscribes to bus, tracks latest price.

## Kingdom Prime integration (2026-06-12)
- Layer 2 runtime now builds the 7 department agents (entry_exit, news_sentiment,
  risk, probability, historical_research, simulation, supreme) — names are 1:1
  with dashboard chibis (H5). Routing: prices → signals.v1 → decisions.v1 → risk.v1.
- Layer 3 serves static/kingdom.html at `/` (classic UI at `/classic`).
- AgentLike Protocol in runtime keeps Layer 2 typed without concrete agent imports leaking upward.

## Production Migration (this session)

- `SimulatorGateway` (synthetic price feed) removed from `src/`.
- `/api/mode/{x}` rejects any mode except `live`.
- `runtime.status()` now exposes `execution_engine: "paper"`, `data_source: "live_bitkub_ws"`, `execution_warning`.
- Added Layer-2 `CeoAgent` (10th agent) — observer only, builds an audit trail.
- Added Layer-1 modules:
  - `domain/audit/decision_log.py` — immutable, replayable decision ledger.
  - `domain/reporting/ceo_report.py` — pure executive-summary aggregator.
- New endpoints: `GET /api/ceo/summary`, `GET /api/ceo/audit`, `GET /api/ceo/agents`.
- Dashboard mock data (`SYMBOL_PRICES`, `POSITIONS`, `TRADES`, `EQUITY_CURVE`, `MONTHLY_RETURNS`, `startDemoSimulator`, hardcoded `1284567.89` initial state) removed.
- Live order execution is STILL NOT implemented. The `tests/architecture/test_paper_only.py` guard remains in force.

## Machine-enforced architecture

The layer rules are not a convention — they are tests (`tests/architecture/`):

- **Layer purity** (`test_layer_rules.py`): domain may import only
  stdlib + pydantic + numpy/pandas/vendor_ta; it must not import
  `time/random/os/datetime/asyncio/httpx/infrastructure/orchestration` — checked
  **recursively**, so a hidden function-scope import is caught too.
- **Float ban**: `domain/portfolio`, `domain/risk`, `domain/backtest` must not
  use `float` literals or annotations (Decimal only) — AST-checked.
- **Execution cage** (`test_execution_guard.py`): order-placement markers
  (`place-bid`, `X-BTK-APIKEY`, …) may appear only in `gateway/bitkub_rest.py`,
  and only `execution_agent.py` may import it. Default engine is `paper`.
- **Honesty** (`test_honesty_guard.py`): dashboard/runtime numbers must come
  from the treasury ledger, never fabricated constants or `Math.random()`.
- **Schema compatibility** (`tests/contracts/`): published message schemas may
  add optional fields but not remove/rename required ones.

## Ports & adapters

`orchestration/ports/` defines protocols (clock, event bus, price feed, state
store, …) that the runtime depends on; Layer-3 adapters implement them and are
wired at the `bootstrap` composition root. This keeps Layer 2 testable without
real I/O (see `tests/conftest.py`'s `FakePriceFeed`).

## Observability

Read-model endpoints (`/healthz`, `/api/health`, `/metrics`) and the
`infrastructure/observability` metrics registry expose live state without
coupling the runtime to infrastructure — see [OBSERVABILITY.md](OBSERVABILITY.md).

## Extending

See [EXTENDING.md](EXTENDING.md) for the strategy / agent / gateway / metric
extension points and the checks each must pass.
