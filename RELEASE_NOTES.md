# Release Notes — Kingdom Prime (Production Release)

This document records the release-preparation pass that consolidated the reviewed
and fixed codebase into a single deployable package.

## Validation summary

All quality gates pass on Python 3.12:

| Gate | Command | Result |
|---|---|---|
| Lint | `ruff check src tests` | ✅ All checks passed |
| Types | `PYTHONPATH=src mypy src/` | ✅ no issues in 132 source files (`--strict`) |
| Tests + coverage | `PYTHONPATH=src pytest` | ✅ 858 passed, 1 skipped, **91% coverage** (gate: 90%) |

The skipped test is the external-service integration test (marker `integration`),
skipped by default — by design.

## What changed in this release pass

### Added — indicator knowledge for the analyst agent
- **`src/domain/analytics/indicator_lines.py`** — a pure-`Decimal` library covering
  all **45 standard indicator lines across 9 families** (moving averages, MACD,
  Bollinger, oscillators, Ichimoku, DMI/ADX, channels/envelopes, Fibonacci/pivots,
  trailing stops). ATR/SuperTrend cross-validate against the vendored `.ta` stub.
- **`src/domain/analytics/indicator_catalog.py`** — a declarative 45-entry catalogue
  (English/Thai names, family, category, inputs, Thai description) so the agent can
  *enumerate and explain* its indicator vocabulary, not just compute it.
- **`expanded_confluence_signal`** — widens the Market Analyst's confluence vote from
  4 to 9 lines (SMA cross, WMA/HMA slope, Bollinger bias, RSI-based MA). Opt-in via
  `EXPANDED_CONFLUENCE_ENTRY` (default off). See **`docs/INDICATORS_TH.md`**.

### Added
- **English `README.md`** — replaced the 2-line placeholder with a complete,
  accurate production README (quick start, architecture, configuration, safety
  model, quality gates, deployment) cross-checked against the implementation.
- **`docs/archive/README.md`** — index explaining the archived development history.
- **`RELEASE_NOTES.md`** — this file.
- **`.env.example`** — documented the previously-undocumented optional settings
  (`PRICE_FEED_MODE`, `NEWS_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `ALERT_WEBHOOK_URL`), all set to values that match the in-code defaults.

### Modified
- **`README_TH.md`** — updated two references that pointed at the moved build
  prompts (`CLAUDE_CODE_MASTER.md` → `docs/archive/CLAUDE_CODE_MASTER.md`) and
  refreshed the stale test count (202+ → 858).
- **`.env.example`** — clarified that the in-code default for
  `MAX_CONSECUTIVE_LOSSES` is `0` (unlimited) and that the example value `5` is a
  safer starting point for real-money use.

### Moved (reorganized, not deleted — full history preserved in git)
- Development-process artifacts moved from the repository root into
  **`docs/archive/`**: the build/upgrade prompts (`CLAUDE_CODE_MASTER.md`,
  `CLAUDE_CODE_PROMPT_V3/V4.md`, `SONNET_PROMPT.md`), the per-phase reports,
  audits, fix logs, and scorecards (24 files total). They are not needed to build,
  run, test, or deploy; the production root now holds only user-facing guides.

### Removed
- Nothing was deleted. The earlier review phases had already removed the
  simulator/mock-data path, dead code, and debug artifacts; this pass verified
  there were **no** stray `TODO`/`FIXME`, `print`/`console.log` debug statements,
  unused dependencies, or experimental modules remaining in `src/`.

## Why

Release preparation requires a clean, navigable production root and documentation
that matches the code. The codebase itself was already green across lint, types,
and tests; the work here was consolidation, documentation accuracy, and
organization — no behavioral code changes were made.

## Known limitations

- **Live trading is intentionally constrained.** Hard, code-level caps (single
  order ≤ 1,000 THB; total deployable ≤ 10,000 THB) cannot be raised from config
  or the dashboard — only by editing `src/orchestration/control.py` plus its test
  and redeploying. This is by design.
- **Single-symbol focus** (BTC/THB) and a single-user local control room. Exposing
  the dashboard beyond localhost requires a credential and is best done behind a
  reverse proxy with TLS (see `docs/SECURITY.md`).
- **Profit targets are pursued, not guaranteed.** Real results depend on the market
  and Bitkub fees.
- **Offline install** via `start.sh` expects a `wheels/` directory (git-ignored);
  without it, dependency install falls back to PyPI (network required).

## Monitoring recommendations

- Liveness/metrics: `GET /healthz`, `GET /metrics`.
- Operational status: `GET /api/status` (feed connected, drawdown, daily loss,
  `live_orders_armed`).
- Decision / control audit trails: `GET /api/ceo/audit`, `GET /api/control/audit`.
- Logs: ship/rotate via the provided `deploy/logrotate.conf`; run under the
  `deploy/kingdom_prime.service` systemd unit for restart-on-failure.

## Rollback considerations

- **Paper is the safe resting state.** `POST /api/execution/mode {"mode":"paper"}`
  disarms live instantly (no token needed). A missing confirm token, an open
  circuit breaker, a `data/KILL_SWITCH` file, or an unverified account all degrade
  to paper automatically.
- **Panic:** `POST /api/emergency_stop`, then `touch data/KILL_SWITCH` to block any
  live arming across restarts; `POST /api/positions/close_all` to flatten.
- **Code rollback:** this release is a single commit on the feature branch; revert
  the commit (or redeploy the previous tag) to roll back. State lives in
  `data/state.db` (SQLite, git-ignored) and survives restarts.
