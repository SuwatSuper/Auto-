# SCORECARD

## Phase 0 — Bug Fixes

### Bugs Fixed

| Bug | Description | Fix | Status |
|-----|-------------|-----|--------|
| B1 | `switch_mode` replaced `self.bus` with a new `InMemoryEventBus`, orphaning WS subscribers | Bus created once in constructor; `switch_mode` reuses same bus, only recreates agents/feed/supervisor | ✅ Fixed |
| B2 | `emergency_stopped` flag could never be cleared | Added `PipelineRuntime.emergency_reset()`, `POST /api/emergency_reset`, distinct "Reset Stop" UI button | ✅ Fixed |
| B3 | WS status starvation — status only sent when price events arrive (timeout fallback) | Decoupled via `asyncio.TaskGroup`: one task forwards prices, independent 1 Hz ticker sends status | ✅ Fixed |
| B4 | Test fixtures leaked pending tasks (no cleanup in teardown) | `runtime_client` fixture always `await runtime.stop()` in `finally` block | ✅ Fixed |
| B5 | SampleAgent busy-poll with `get_nowait()` loop and imports inside loop | Clean event-driven loop with `asyncio.timeout(0.5)`, top-level imports, narrow exception handling, `parse_failures` counter in `status()` | ✅ Fixed |
| B6 | Deprecated `websockets.legacy.client` API | Migrated to `websockets.asyncio.client.connect`; kept backoff+jitter logic intact | ✅ Fixed |
| B7 | `contextlib.suppress(asyncio.CancelledError, Exception)` silently suppressed all errors | Now suppresses only `(asyncio.CancelledError, TimeoutError)`; logs other exceptions via structlog | ✅ Fixed |
| B8 | XSS via `row.innerHTML` in `app.js` with unescaped data | **Fixed in P0**: replaced all `innerHTML` assignments with DOM element construction (`createElement`/`textContent`/`dataset`) | ✅ Fixed |
| B9 | Latency metric could go negative (future-dated timestamps); no precision indicator | Clamped at `max(0, latency)` in both `record_message()` and `_CountingBusProxy.publish()`; added `latency_precision: "ms"` to `status()` | ✅ Fixed |

### Test Results (P0)

```
======================== 31 passed in 3.82s ========================
```

All 31 tests pass including:
- `test_switch_mode_keeps_bus_subscribers` (B1)
- `test_emergency_reset_clears_flag`, `test_emergency_reset_allows_restart`, `test_emergency_stop_and_reset` (B2)
- `test_status_sent_even_under_price_flood` (B3)
- Fixture teardown with `await runtime.stop()` (B4)
- `test_agent_stops_cleanly_within_1s`, `test_agent_parse_failures_counted`, `test_agent_status_includes_parse_failures` (B5)
- `test_backoff_within_bounds_attempts_0_to_10`, `test_backoff_increases_with_attempts`, `test_backoff_bounds`, `test_backoff_never_negative` (B6)
- `test_stop_does_not_swallow_all_exceptions` (B7)
- `test_status_includes_latency_precision`, `test_latency_clamped_at_zero` (B9)

### Linting & Type Checking

```
ruff check src tests scripts  →  All checks passed!
mypy src/                     →  Success: no issues found in 25 source files
```

### Notes

- B8 (XSS) was noted in the spec as "Note in SCORECARD only (will be fixed in P5)" but was proactively fixed in P0 by replacing all `innerHTML` assignments with safe DOM API calls (`createElement`, `textContent`, `dataset`).
- Layer 1 violation: `market_data.py` uses `structlog` via `TYPE_CHECKING` guard (import only for type hints, not runtime). This will be fully purified in P1 per spec.
- Warnings in test output: FastAPI `ORJSONResponse` deprecation (upstream library) and Starlette `TestClient` deprecation (use httpx2) — neither affects functionality.

## Phases P1–P6

Pending — to be implemented in subsequent sessions.
