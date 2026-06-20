# ADR-0003 — Observability metrics & supply-chain hardening

- Status: Accepted (2026-06-19)
- Context: The system had a minimal hard-coded `/metrics` endpoint and a
  single-job CI (ruff + mypy + pytest) with no dependency/secret/SAST scanning.
  Observability and CI/security were the weakest engineering dimensions.

## Decision

1. **Observability** — introduce a dependency-free Prometheus metrics registry
   (`infrastructure/observability/metrics.py`) and a pure status→metrics mapper
   (`status_metrics.py`). `GET /metrics` now renders rich runtime metrics
   (uptime, agent running/stale counts, feed/emergency flags, equity/cash/PnL),
   keeping the legacy `trading_agent_count` for existing scrapers. Both modules
   are unit-tested.

2. **Supply-chain & SAST** — split CI into `lint` / `typecheck` / `test`
   (matrix 3.12 + 3.13, pip caching, 90% coverage gate) and add:
   - `pip-audit` (dependency CVE scan) in a dedicated `security.yml`,
   - `bandit -ll -ii` (static security analysis),
   - `detect-secrets` against a committed `.secrets.baseline`,
   - `codeql.yml` (GitHub CodeQL, security-and-quality),
   - `dependabot.yml` (weekly pip + actions updates).

3. **Fix the one real finding** — replace `xml.etree.ElementTree.fromstring`
   with `defusedxml` in `gateway/news_rss.py` (untrusted RSS parsing), clearing
   the only bandit medium/high issue.

## Consequences

- `/metrics` is now testable and extensible; adding a metric is a one-liner plus
  a test.
- Dependencies, secrets, and code are scanned on every push/PR and weekly.
- New runtime dependency: `defusedxml` (small, no transitive risk).
- Whole-repo `ruff format` was deliberately **not** adopted to avoid a large,
  behaviour-neutral churn diff; the existing `ruff check` style is kept.
