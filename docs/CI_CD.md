# CI / CD

Every push and pull request runs three independent workflows. All gates must be
green to merge.

## `ci.yml` — quality gates

| Job | Command | Notes |
|-----|---------|-------|
| `lint` | `ruff check src tests` | Rules `E,W,F,I,UP,B,SIM` (see `pyproject.toml`). |
| `typecheck` | `mypy src/` | `--strict`, no per-module suppressions. |
| `test` | `PYTHONPATH=src pytest` | Matrix **Python 3.12 + 3.13**; coverage **≥ 90%** enforced via `--cov-fail-under` in `pyproject.toml`. |

Jobs are split so a lint failure doesn't mask a type/test failure, and each uses
`actions/setup-python` **pip caching** (`cache-dependency-path:
requirements-dev.txt`) to speed installs. `concurrency` cancels superseded runs
per ref.

## `security.yml` — supply-chain & SAST

| Step | Tool | What it catches |
|------|------|-----------------|
| Dependency scan | `pip-audit -r requirements.txt -r requirements-dev.txt` | Known CVEs in dependencies (OSV/PyPI advisories). |
| Static analysis | `bandit -r src -ll -ii` | Medium+ severity / high-confidence code security issues. |
| Secret scan | `detect-secrets-hook --baseline .secrets.baseline` | New secrets vs the committed baseline of known test fixtures. |

Runs on push/PR and weekly (`cron`). The `.secrets.baseline` records the known
test-only fixtures (golden HMAC secret, dashboard test keys) so only *new*
secrets fail the job.

## `codeql.yml` — GitHub CodeQL

`github/codeql-action` analyses Python with the `security-and-quality` query
suite on push/PR and weekly. Results surface in the repo's Security tab.

## `dependabot.yml`

Weekly update PRs for both the `pip` and `github-actions` ecosystems (grouped,
limit 5 open PRs each).

## Running the gates locally

```bash
pip install -r requirements-dev.txt
ruff check src tests
mypy src/
PYTHONPATH=src pytest
pip-audit -r requirements.txt -r requirements-dev.txt
bandit -r src -ll -ii
git ls-files | xargs detect-secrets-hook --baseline .secrets.baseline
```
