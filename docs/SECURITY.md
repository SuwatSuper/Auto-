# Security

## Secrets

API keys are stored as `SecretStr` in `Settings` and never logged. Use environment
variables or a `.env` file. The Bitkub key/secret and the dashboard key are never
returned by any endpoint (`/api/credentials` echoes only `has_key`).

## Auth model (control plane)

The dashboard is a single-user **local control room**. Auth is enforced in
`infrastructure/web/_helpers.py`:

### 1. Fail-closed bind (`assert_safe_bind`, T1)

`create_app()` refuses to start when bound to a **non-loopback** host
(`web_host` not in `127.0.0.1` / `::1` / `localhost`) unless a control credential
(`DASHBOARD_API_KEY` or `DASHBOARD_PASSWORD`) is set. This prevents exposing the
control plane to the LAN/Internet with no auth.

```
WEB_HOST=0.0.0.0 (no key/password)  → RuntimeError, refuses to start
WEB_HOST=0.0.0.0 DASHBOARD_API_KEY=… → starts; remote requests need the key
WEB_HOST=127.0.0.1                   → starts (loopback only)
```

### 2. Ordinary control endpoints (`check_api_key`)

Risk settings, breaker, agent start/stop, emergency stop, alerts, strategy
toggles, capital, kill-switch *read*. Localhost is trusted (no key needed);
remote requests require `X-API-Key == DASHBOARD_API_KEY` (when a key is set).

### 3. Dangerous endpoints (`check_api_key_strict`, D3 = strict)

These spend real money or change the real-money posture and require a valid
`X-API-Key` **even from localhost** (no loopback bypass). If no key is configured
they are **locked** (fail-closed) — set `DASHBOARD_API_KEY` or log in first:

- `POST /api/execution/mode`   (arm live trading)
- `POST /api/credentials`      (set real Bitkub API keys)
- `POST /api/order`            (place a real order)
- `POST /api/positions/close`, `POST /api/positions/close_all`
- `POST /api/kill_switch`      (block/unblock live across restarts)

Obtain the token by setting `DASHBOARD_API_KEY` in `.env`, or via
`POST /api/login` with `DASHBOARD_PASSWORD` (returns the token). Rotate by editing
`.env` and restarting. Send it as the `X-API-Key` header.

## WebSocket

`/ws` validates the `Origin` header against the configured host/port. It streams
read-only price/status data (no control actions). For exposure beyond localhost,
deploy behind a reverse proxy with TLS + auth.

## Real-money ceilings

A hard-coded per-order ceiling (`HARD_CAP_SINGLE_ORDER_THB` in
`orchestration/control.py`) cannot be exceeded by any config or dashboard input —
the live order path rejects (and logs CRITICAL) any order above it. See
[LIVE_TRADING_RUNBOOK.md](LIVE_TRADING_RUNBOOK.md).
