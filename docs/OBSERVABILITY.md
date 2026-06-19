# Observability

Kingdom Prime exposes its real state through structured logs, an event ledger,
HTTP health probes, and a Prometheus-compatible metrics endpoint. Every number
comes from the live runtime / treasury ledger — nothing is fabricated (see
`tests/architecture/test_honesty_guard.py`).

## HTTP endpoints

| Endpoint        | Purpose                                                            |
|-----------------|-------------------------------------------------------------------|
| `GET /healthz`  | Liveness probe — `{"status":"ok","ts_ms":…}`. Cheap, always open.  |
| `GET /api/health` | Detailed health: agent counts, running/stale agents, feed status, uptime, emergency-stop flag. |
| `GET /metrics`  | Prometheus text exposition (see below).                            |
| `GET /api/timeline` | Recent mode/uptime/agents snapshot for the dashboard.         |

## Metrics (`GET /metrics`)

The endpoint renders the live `runtime.status()` snapshot into the Prometheus
text exposition format via a small, dependency-free registry:

- `src/infrastructure/observability/metrics.py` — `MetricsRegistry`
  (counters/gauges + labels, `render()` → Prometheus text). Pure and
  unit-tested (`tests/infrastructure/test_metrics.py`).
- `src/infrastructure/observability/status_metrics.py` —
  `render_status_metrics(status, *, agent_count=…)` maps a status snapshot to
  metrics, reading every field defensively so a partial status never 500s.

### Exported families

| Metric | Type | Meaning |
|--------|------|---------|
| `trading_uptime_seconds` | gauge | Process uptime |
| `trading_agents_total` / `trading_agent_count` | gauge | Registered agents (`*_count` is the legacy alias, pinned to `len(runtime.agents)`) |
| `trading_agents_running` | gauge | Agents currently running |
| `trading_agents_stale` | gauge | Agents flagged stale by the supervisor |
| `trading_feed_connected` | gauge | Price feed connected (1/0) |
| `trading_emergency_stopped` | gauge | Emergency stop active (1/0) |
| `trading_equity_thb` | gauge | Account equity (THB) from the treasury ledger |
| `trading_cash_thb` | gauge | Account cash (THB) |
| `trading_pnl_today_thb` | gauge | Realized + unrealized PnL today (THB) |
| `trading_msg_rate` / `trading_latency_ms` | gauge | Pipeline throughput / latency |

### Scraping

```yaml
# prometheus.yml
scrape_configs:
  - job_name: kingdom-prime
    static_configs:
      - targets: ["127.0.0.1:8000"]
```

`/metrics` is intentionally open (no account data) so a loopback Prometheus can
scrape it without a key, exactly like `/healthz`.

## Logs & ledger

- **Structured logs** — `structlog` JSON events across the runtime.
- **Daily summary** — `infrastructure/logging/daily_summary.py`.
- **Trade CSV** — `infrastructure/logging/trade_csv.py` (per-fill audit row).
- **Event store** — `infrastructure/events/jsonl_store.py` (append-only JSONL
  ledger; replayable, contract-tested in `tests/contracts/`).

## Extending metrics

Add a new family in `status_metrics.py` with a `reg.gauge(...)` /
`reg.counter(...)` call and a one-line entry in the table above. The registry
handles labels, escaping, and formatting; add a unit test asserting the new
line appears in `render()`.
