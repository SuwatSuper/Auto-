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

**Strict bus connectivity & self-learning** — every cross-agent input travels on a
topic; there is no hidden attribute coupling. The entry gate consumes a single
bus-fed *confluence* cache (timeline win-probability + regime, the rolling
backtest win-rate, the swarm consensus bias, RSI probability, news sentiment, and
the research price-percentile). A quantitative feedback loop routes `paper.events`
Win/Loss back into per-source **vote weights** (>55% boosted, <45% muted) and into
the 150-agent grid's regime-aware reliability weighting — the system adapts to the
current market with **no LLM in the loop**. Both are surfaced under
`/api/status` (`confluence`, `dynamic_weighting`).

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

Three CI workflows run on every push/PR (details in [docs/CI_CD.md](docs/CI_CD.md)):

- **[`ci.yml`](.github/workflows/ci.yml)** — `lint` (ruff), `typecheck`
  (mypy --strict), `test` (Python **3.12 + 3.13** matrix, 90% coverage gate),
  with pip caching.
- **[`security.yml`](.github/workflows/security.yml)** — `pip-audit`
  (dependency CVEs), `bandit` (SAST), `detect-secrets` (secret scan vs baseline).
- **[`codeql.yml`](.github/workflows/codeql.yml)** — GitHub CodeQL + weekly
  Dependabot updates.

Run them locally:

```bash
ruff check src tests                       # lint
mypy src/                                   # strict type check (141 source files)
PYTHONPATH=src pytest                       # tests + coverage gate (fail-under 90%)
pip-audit -r requirements.txt              # dependency vulnerability scan
bandit -r src -ll -ii                       # static security analysis
```

Current baseline: **1034 passed, 1 skipped, ~92% coverage**; `ruff`,
`mypy --strict`, `pip-audit`, and `bandit` all clean. Tests make no real network
calls (RSS/feeds are stubbed in `conftest.py`); integration tests that hit
external services are marked `integration` and skipped by default.

## 📈 Does it actually make money?

That verdict is decided by the **profit-proof** tools, which trade **both
directions** (long when price rises, short when it falls) across **any market**:

```bash
# net return / profit factor / drawdown / PROFITABLE verdict, long + short
PYTHONPATH=src python scripts/prove_profit.py --csv data/btc_1h.csv --direction both
# per-trade edge: win% vs breakeven% (incl. fees+slippage)
PYTHONPATH=src python scripts/backtest_edge.py --csv data/btc_1h.csv --bracket both
```

The engine is unit-tested and validated on synthetic up/down trends (longs profit
in uptrends, shorts in downtrends); the **real** verdict needs real candles
(`--fetch` once `api.bitkub.com` is allowlisted, or `--csv`). See
[docs/PROFIT_PROOF.md](docs/PROFIT_PROOF.md). An honest tool never reports edge it
hasn't measured on real prices.

---

## 📁 Project structure

```
src/                 Application code (3 layers, see above)
tests/               1000+ tests: domain / orchestration / infrastructure / web / architecture / contracts
docs/                ARCHITECTURE, CI_CD, OBSERVABILITY, EXTENDING, PROFIT_PROOF, BACKTEST_EDGE, SECURITY, RUNBOOK, EVENTS, ADRs, INDICATORS_TH
deploy/              systemd unit, logrotate config, DEPLOY.md
scripts/             Dev/ops helpers (prove_profit, backtest_edge, run, bench, setup_env, probes)
*.md (root)          User-facing guides (this file + Thai guides)
```

**More docs:** [PROFIT_PROOF](docs/PROFIT_PROOF.md) · [BACKTEST_EDGE](docs/BACKTEST_EDGE.md) ·
[CI_CD](docs/CI_CD.md) · [OBSERVABILITY](docs/OBSERVABILITY.md) ·
[EXTENDING](docs/EXTENDING.md) · [ARCHITECTURE](docs/ARCHITECTURE.md) · [SECURITY](docs/SECURITY.md)

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
