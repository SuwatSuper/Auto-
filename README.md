# 👑 Kingdom Prime — Live-Data, Paper-First Trading System

An automated BTC/THB trading system for the **Bitkub** exchange.

- **Live market data** (Bitkub public REST ticker by default; WebSocket optional).
- **Paper execution by default** — no real orders are sent until you explicitly arm
  live trading through multiple safety gates.
- **Clean 3-layer architecture** (domain → orchestration → infrastructure) with a
  swarm of decision/risk/treasury agents and a CEO audit trail.

> ⚠️ **Trading involves real financial risk.** The default mode (`paper`) simulates
> fills against live prices and never spends money. Going live is deliberately
> gated (see [Safety model](#-safety-model)). Profit targets are goals the system
> *pursues* — never guarantees. This software is provided as-is and is not
> financial advice.

🇹🇭 ผู้ใช้ภาษาไทยเริ่มที่ **[START_HERE_TH.md](START_HERE_TH.md)** ·
คู่มือละเอียด **[MANUAL_TH.md](MANUAL_TH.md)** · เทรดจริง **[LIVE_TRADING_TH.md](LIVE_TRADING_TH.md)**

---

## 🚀 Quick start

Requires **Python 3.12+**.

### One command (macOS / Linux)

```bash
./start.sh        # creates a venv, installs deps, starts the server, opens the dashboard
```

Windows: double-click `start.bat` (or right-click `start.ps1` → *Run with PowerShell*).

### Manual (any OS)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt          # Windows: .venv\Scripts\pip
PYTHONPATH=src .venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
# open http://localhost:8000/
```

Then open **http://localhost:8000/**.

---

## 🖥 Dashboards & endpoints

| URL | What it is |
|---|---|
| `/` | **Kingdom Prime** dashboard — the single page (chart, balances, trades, all controls) |
| `/api/status` | System status (JSON) |
| `/api/ceo/summary`, `/api/ceo/audit` | Executive view + decision audit trail |
| `/healthz`, `/metrics` | Liveness + Prometheus-style metrics |
| `/ws` | Read-only price/status stream (origin-checked) |

---

## 🏛 Architecture

Three layers with a strict dependency rule (layer *N* imports only from *N* or lower):

```
src/domain/          Layer 1 — pure business logic (Decimal money, no frameworks/I-O)
src/orchestration/   Layer 2 — runtime, department agents, supervisors, ports
src/infrastructure/  Layer 3 — FastAPI, WebSocket/REST gateways, SQLite, dashboards
```

Price ticks flow `prices → signals.v1 → decisions.v1 → risk.v1 → execution`. The
Supreme Commander tallies agent votes; the Risk and Treasury agents can veto; the
CEO agent records an audit trail of what fired and why. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/EVENTS.md](docs/EVENTS.md).

---

## ⚙️ Configuration

Copy the template and edit it (never commit your real `.env` — it is git-ignored):

```bash
cp .env.example .env
```

Key settings (full list and inline docs in [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `EXECUTION_ENGINE` | `paper` | `paper` (safe sim) or `live` (real orders — gated) |
| `INITIAL_CAPITAL` | `1000` | Paper-trading starting equity (THB) |
| `TARGET_DAILY_PROFIT_PCT` | `5` | Daily net-profit target the system pursues |
| `ENABLED_STRATEGIES` | `trend_following` | Comma-separated strategy names |
| `DASHBOARD_API_KEY` | — | Required to authorize control endpoints / remote access |
| `DASHBOARD_PASSWORD` | — | Operator login (exchanged for a token via `POST /api/login`) |
| `WEB_HOST` / `WEB_PORT` | `127.0.0.1` / `8000` | Bind address (non-loopback requires a credential) |
| `BITKUB_API_KEY` / `BITKUB_API_SECRET` | — | Only needed for live mode / real wallet reads |

---

## 🛡 Safety model

Paper is the **safe resting state**: a missing confirmation token, an open circuit
breaker, a present kill file, or an unverified account all degrade to paper
automatically. Going live requires **all four gates** open:

1. `engine_live` — `EXECUTION_ENGINE=live`
2. `confirm_token` — exact confirmation string on `POST /api/execution/mode`
3. `kill_switch_clear` — no `data/KILL_SWITCH` file present
4. `breaker_closed` — circuit breaker not tripped

Additional guard rails (all pinned by tests):

- **Hard, code-level caps** — no single live order may exceed **1,000 THB**, total
  deployable ≤ **10,000 THB**. These cannot be raised from config or the dashboard;
  over-cap orders are *rejected and logged CRITICAL* (never silently trimmed).
- **Treasury veto** — a real BUY never fires if the account is halted, underfunded,
  or would breach the survival floor.
- **Real-balance close** — a protective close never sells more coin than the real
  wallet holds.
- **Reconciliation gate** — live orders never arm against an unverified account.
- **Fail-closed bind / strict auth** — binding to a non-loopback host without a
  credential refuses to start; money-spending endpoints require `X-API-Key` even
  from localhost.

Full operator procedures: [docs/LIVE_TRADING_RUNBOOK.md](docs/LIVE_TRADING_RUNBOOK.md)
· security model: [docs/SECURITY.md](docs/SECURITY.md).

---

## 🧪 Quality gates & testing

The CI pipeline ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) enforces
lint, strict typing, and a 90% coverage gate. Run them locally:

```bash
ruff check src tests                       # lint
PYTHONPATH=src mypy src/                    # strict type check (132 source files)
PYTHONPATH=src pytest                       # tests + coverage gate (fail-under 90%)
```

Current baseline: **858 passed, 1 skipped, 91% coverage**; `ruff` and
`mypy --strict` clean. Integration tests that hit external services are marked
`integration` and skipped by default.

---

## 📁 Project structure

```
src/                 Application code (3 layers, see above)
tests/               858 tests: domain / orchestration / infrastructure / web / architecture / contracts
docs/                ARCHITECTURE, RUNBOOK, LIVE_TRADING_RUNBOOK, EVENTS, ADRs, SECURITY
docs/archive/        Development-history reports & build prompts (not needed to run)
deploy/              systemd unit, logrotate config, DEPLOY.md
scripts/             Dev/ops helpers (run, bench, make_zip, setup_env, probes)
*.md (root)          User-facing guides (this file + Thai guides)
```

---

## 🚢 Deployment

Production deployment (Ubuntu + systemd) is documented in
[deploy/DEPLOY.md](deploy/DEPLOY.md), including the `kingdom_prime.service` unit and
`logrotate.conf`. Operational procedures are in [docs/RUNBOOK.md](docs/RUNBOOK.md).

---

## 📜 License & disclaimer

This is personal trading software. Use at your own risk. Past simulated performance
does not predict future results, and live trading can lose real money. You are
responsible for any keys, funds, and orders you authorize.
