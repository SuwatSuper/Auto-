# Extending Kingdom Prime

The system is built around a few stable extension points so new behaviour is
added at the edges, not by editing core flow. Every new module keeps the layer
rules (`tests/architecture/test_layer_rules.py`): **domain stays pure**
(stdlib + pydantic + numpy/pandas only, Decimal for money), orchestration may
import domain, infrastructure may import anything.

## Add a strategy (Layer 1)

1. Create `src/domain/strategy/<name>.py` exposing either `decide(ctx)` (price
   series) or `decide_df(df)` returning an `OhlcvSignal` with `stop_price` /
   `take_profit_price` (a bracket).
2. Register it in `src/domain/strategy/registry.py` (`_REGISTRY[...] = Cls`).
3. Add tests under `tests/domain/` — mirror the existing determinism,
   no-lookahead, and `stop < entry < tp` checks in `test_new_strategies.py`.
4. The P0 backtester (`scripts/backtest_edge.py`) picks up registry strategies
   automatically — measure the new edge before trusting it.

Rules: **Decimal only** (float is AST-banned in financial domain), no I/O, no
`datetime`/`random`/`time`.

## Add an agent (Layer 2)

Agents live in `src/orchestration/agents/` and subscribe/publish on the event
bus (`prices → signals.v1 → decisions.v1 → risk.v1`). Wire it in the runtime
agent builder and add it to the agent status map. Keep imports within
`domain + orchestration + structlog/orjson/pydantic`.

## Add a gateway / adapter (Layer 3)

Infrastructure adapters (e.g. a new exchange or data feed) go under
`src/infrastructure/gateway/`. Follow `bitkub_klines.py`: a **pure parser**
plus a thin HTTP/IO shell, an injectable client for tests, and no order-placement
markers (those are caged in `bitkub_rest.py` — enforced by
`tests/architecture/test_execution_guard.py`). Add `py.typed` to new packages.

## Add a metric (Layer 3)

Add a `reg.gauge(...)` / `reg.counter(...)` in
`src/infrastructure/observability/status_metrics.py` and a unit test. See
[OBSERVABILITY.md](OBSERVABILITY.md).

## Evolve an event schema

Published message schemas are contract-tested
(`tests/contracts/test_schema_compat.py`): **adding** an optional field is
backward-compatible; **removing/renaming** a required field must fail the test.
Update the schema registry and the contract test together.

## Before you ship

```bash
ruff check src tests && mypy src/ && PYTHONPATH=src pytest
```

New `src/` code must keep total coverage ≥ 90%, so ship tests with it.
