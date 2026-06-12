# Sonnet Production Migration Completion Prompt

> **HOW TO USE THIS PROMPT**
> Paste everything below the line `--- BEGIN PROMPT ---` into a new Claude
> Sonnet session that has Phase-1 zip mounted at `/mnt/user-data/uploads/`.
> Use effort: low. Do NOT modify the prompt.

---

--- BEGIN PROMPT ---

You are continuing a Production Migration on the `kingdom_prime` trading
system. Phase 1 (backend) is DONE and tests are green. Your job is Phase 2
(frontend + docs + final packaging). Follow this script literally.

## Rules

1. **Do exactly what each STEP says. No improvisation.**
2. **Run the VERIFY command after each STEP. If it fails, fix it before
   moving on.**
3. **All paths are absolute under `/home/claude/work` after extraction.**
4. **Never invent mock/sample/placeholder data.** If a value is unknown,
   render `"DATA UNAVAILABLE"` and log a warning.
5. **Never remove the `tests/architecture/test_paper_only.py` file** — it
   is a deliberate safety guard.
6. **Use `str_replace` for surgical edits to `kingdom.html`** — do NOT
   regenerate the whole file. It is ~4 000 lines and rewriting risks data
   loss.

## STEP 0 — Setup

```bash
cd /home/claude
unzip -q /mnt/user-data/uploads/kingdom_phase1.zip -d work
cd work
python3 -m venv .venv
.venv/bin/pip install --quiet -r requirements.txt -e .
.venv/bin/pip install --quiet pytest pytest-asyncio pytest-cov hypothesis
PYTHONPATH=src .venv/bin/python -m pytest --no-cov -q 2>&1 | tail -3
```

VERIFY: must print `283 passed`. If not, stop and report.

---

## STEP 1 — Strip mock data constants from `kingdom.html`

File: `src/infrastructure/web/static/kingdom.html`

Find the block starting with the comment `MOCK DOMAIN DATA  (deterministic seed — replaced by backend feed)` and delete from that comment up to (and including) the line `const MONTHLY_RETURNS = [...]`.

Use `grep -n "MOCK DOMAIN DATA" src/infrastructure/web/static/kingdom.html` first to confirm the line number (it should be around line 3489–3490).

Replace the entire block (the comment header line, plus `SYMBOL_PRICES`, `POSITIONS`, `TRADES`, `EQUITY_CURVE` IIFE, and `MONTHLY_RETURNS`) with this single block:

```javascript
/* ══════════════════════════════════════════════════════════════
   PRODUCTION DATA POLICY — NO MOCK DATA
   All numeric/position/trade data MUST come from the backend
   (/api/status, /api/ceo/*, WebSocket /ws). When a value is
   missing, renderers MUST display "DATA UNAVAILABLE", never a
   placeholder number.
══════════════════════════════════════════════════════════════ */
const SYMBOL_PRICES = {};   // populated by handlePrice() only
const POSITIONS     = [];   // populated by /api/status only
const TRADES        = [];   // populated by paper.events.v1 WS only
const EQUITY_CURVE  = [];   // populated by /api/status history only
const MONTHLY_RETURNS = []; // populated by /api/ceo/summary only
```

VERIFY:
```bash
grep -c "1284567\|2450000\|2410000\|6300\|22500" src/infrastructure/web/static/kingdom.html
```
Must print `0`.

---

## STEP 2 — Delete `startDemoSimulator()`

In `src/infrastructure/web/static/kingdom.html`, find the block:

```
/* ══════════════════════════════════════════════════════════════
   STANDALONE DEMO SIMULATOR
```

Delete that entire comment header AND the full `function startDemoSimulator() { ... }` definition. The function ends just before:

```
/* ──────────────────────────────────────────────────────────────
   PERIODIC UPDATES
```

Keep `PERIODIC UPDATES` and everything after.

Also remove the call to `startDemoSimulator();` in the `DOMContentLoaded` listener (search for the literal `startDemoSimulator();` and remove that line).

VERIFY:
```bash
grep -c "startDemoSimulator" src/infrastructure/web/static/kingdom.html
```
Must print `0`.

---

## STEP 3 — Delete the hardcoded initial mock `handleStatus({...1284567.89...})` call

In the `DOMContentLoaded` listener find the block that starts with the comment `// Initial mock equity so dashboard doesn't appear empty on first load` and ends with the closing `});` of the `handleStatus({...})` call.

Delete that entire block (comment + call).

VERIFY:
```bash
grep -c "Initial mock equity" src/infrastructure/web/static/kingdom.html
```
Must print `0`.

---

## STEP 4 — Remove `simulateAgentMetrics()` body, replace with no-op

The function `simulateAgentMetrics()` (search for its `function simulateAgentMetrics` declaration) injects fake emotion/stress drift.

Replace the entire function body (everything between the opening `{` and the matching closing `}`) with a single comment line:

```javascript
function simulateAgentMetrics() {
  /* Production migration: agent metrics now come from /api/status only. */
}
```

Keep its `setInterval` caller as-is (it now calls a no-op, which is fine).

VERIFY:
```bash
grep -A 2 "function simulateAgentMetrics" src/infrastructure/web/static/kingdom.html | head -4
```
Must show the no-op comment.

---

## STEP 5 — Remove the simulator mode toggle button

In `src/infrastructure/web/static/kingdom.html`, find the line:

```html
<button class="mode-btn active" data-mode="simulator" id="btn-sim">SIM</button>
```

Delete that entire line.

Also find the JavaScript handler `if (sModeSim) sModeSim.addEventListener('click', ...);` (search for `sModeSim`) and delete that line.

VERIFY:
```bash
grep -cE "btn-sim|sModeSim" src/infrastructure/web/static/kingdom.html
```
Must print `0`.

---

## STEP 6 — Add CEO navigation item

In `src/infrastructure/web/static/kingdom.html`, find the existing nav items (search for `data-page="settings"` to locate the nav block).

Insert this line right BEFORE the settings nav item:

```html
<li class="nav-item" data-page="ceo"><span class="nav-icon">👑</span><span class="nav-label" data-i18n="nav_ceo">CEO</span></li>
```

VERIFY:
```bash
grep -c 'data-page="ceo"' src/infrastructure/web/static/kingdom.html
```
Must print `1`.

---

## STEP 7 — Add CEO page-content section

In `src/infrastructure/web/static/kingdom.html`, find the existing `<section data-page-content="settings"` block.

Insert this entire block right BEFORE that section:

```html
<section class="page-content" data-page-content="ceo">
  <header class="page-header">
    <div class="page-title" data-i18n="pg_ceo_title">CEO — Executive Reporting</div>
    <div class="page-sub" data-i18n="pg_ceo_sub">Audit trail · agent health · risk · business KPIs</div>
  </header>
  <div id="ceo-banner" class="warning-banner" style="display:none;"></div>
  <div class="ceo-grid">
    <div class="ceo-card"><h3 data-i18n="ceo_business">Business</h3><div id="ceo-business">DATA UNAVAILABLE</div></div>
    <div class="ceo-card"><h3 data-i18n="ceo_risk">Risk</h3><div id="ceo-risk">DATA UNAVAILABLE</div></div>
    <div class="ceo-card"><h3 data-i18n="ceo_health">System Health</h3><div id="ceo-health">DATA UNAVAILABLE</div></div>
    <div class="ceo-card ceo-card-wide"><h3 data-i18n="ceo_agents">Agents</h3><div id="ceo-agents">DATA UNAVAILABLE</div></div>
    <div class="ceo-card ceo-card-wide"><h3 data-i18n="ceo_audit">Audit Trail (last 50)</h3><div id="ceo-audit">DATA UNAVAILABLE</div></div>
  </div>
</section>
```

VERIFY:
```bash
grep -c 'data-page-content="ceo"' src/infrastructure/web/static/kingdom.html
```
Must print `1`.

---

## STEP 8 — Add CEO styles

Find the closing `</style>` tag in `kingdom.html` (use `grep -n "</style>" src/infrastructure/web/static/kingdom.html | head -1`). Insert RIGHT BEFORE the closing `</style>`:

```css
.warning-banner { background:#3a1a00; color:#ffb74d; padding:8px 12px; border-radius:4px; margin-bottom:12px; font-size:13px; }
.ceo-grid { display:grid; grid-template-columns:repeat(3, 1fr); gap:16px; padding:16px; }
.ceo-card { background:rgba(255,255,255,0.04); border-radius:8px; padding:16px; }
.ceo-card-wide { grid-column: span 3; }
.ceo-card h3 { margin:0 0 12px; font-size:14px; color:#80d8ff; text-transform:uppercase; letter-spacing:1px; }
.ceo-card table { width:100%; font-size:12px; border-collapse:collapse; }
.ceo-card th, .ceo-card td { padding:4px 8px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.06); }
.ceo-health-RUNNING { color:#80e27e; }
.ceo-health-WARNING { color:#ffb74d; }
.ceo-health-STOPPED { color:#ff5252; }
.ceo-health-IDLE    { color:#b0bec5; }
.ceo-risk-LOW       { color:#80e27e; }
.ceo-risk-MODERATE  { color:#ffd54f; }
.ceo-risk-HIGH      { color:#ffb74d; }
.ceo-risk-CRITICAL  { color:#ff5252; font-weight:bold; }
.ceo-unavailable    { color:#b0bec5; font-style:italic; }
@media (max-width: 900px) { .ceo-grid { grid-template-columns: 1fr; } .ceo-card-wide { grid-column: auto; } }
```

VERIFY:
```bash
grep -c "ceo-grid" src/infrastructure/web/static/kingdom.html
```
Must print at least `2` (one in CSS, one in HTML).

---

## STEP 9 — Add CEO page renderer

In `src/infrastructure/web/static/kingdom.html`, find the line that reads:

```javascript
const PAGE_RENDERERS = {
```

Add `ceo:       renderCeoPage,` to that object (before `settings:`).

Then find the closing brace of the PAGE_RENDERERS object and AFTER the next blank line, insert the following functions verbatim:

```javascript
/* ══════════════════════════════════════════════════════════════
   CEO PAGE — pulls /api/ceo/{summary,audit,agents} on every render.
   Renders "DATA UNAVAILABLE" if any field is null. NEVER fabricates.
══════════════════════════════════════════════════════════════ */
async function renderCeoPage() {
  const banner = $('ceo-banner');
  try {
    const [sumRes, auditRes] = await Promise.all([
      fetch('/api/ceo/summary'),
      fetch('/api/ceo/audit?limit=50'),
    ]);
    if (!sumRes.ok || !auditRes.ok) {
      banner.style.display = 'block';
      banner.textContent = 'CEO endpoints unavailable (HTTP ' + sumRes.status + '/' + auditRes.status + ')';
      ['ceo-business','ceo-risk','ceo-health','ceo-agents','ceo-audit'].forEach(id => {
        const el = $(id); if (el) { el.textContent = 'DATA UNAVAILABLE'; el.classList.add('ceo-unavailable'); }
      });
      return;
    }
    const summary = await sumRes.json();
    const audit = await auditRes.json();
    if (window.handleStatus && State.executionWarning) {
      banner.style.display = 'block';
      banner.textContent = State.executionWarning;
    } else {
      banner.style.display = 'none';
    }
    renderCeoBusiness(summary.business);
    renderCeoRisk(summary.risk);
    renderCeoHealth(summary.health);
    renderCeoAgents(summary.agents);
    renderCeoAudit(audit);
  } catch (err) {
    console.error('renderCeoPage', err);
    banner.style.display = 'block';
    banner.textContent = 'CEO render failed: ' + (err && err.message ? err.message : String(err));
  }
}

function _fmtMoney(v) {
  if (v === null || v === undefined) return null;
  const n = Number(v);
  if (!isFinite(n)) return null;
  return '฿ ' + n.toLocaleString('th-TH', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function _unavailable(el) { el.textContent = 'DATA UNAVAILABLE'; el.classList.add('ceo-unavailable'); }

function renderCeoBusiness(b) {
  const el = $('ceo-business'); el.innerHTML = ''; el.classList.remove('ceo-unavailable');
  if (b.portfolio_value_availability !== 'AVAILABLE') { _unavailable(el); return; }
  const rows = [
    ['Portfolio value', _fmtMoney(b.portfolio_value) || '—'],
    ['Cash', b.cash_availability === 'AVAILABLE' ? (_fmtMoney(b.cash) || '—') : 'DATA UNAVAILABLE'],
    ['PnL total', _fmtMoney(b.pnl_total) || '—'],
    ['PnL today', _fmtMoney(b.pnl_today) || '—'],
  ];
  const t = el.appendChild(document.createElement('table'));
  rows.forEach(([k,v]) => {
    const tr = t.appendChild(document.createElement('tr'));
    const td1 = tr.appendChild(document.createElement('td')); td1.textContent = k;
    const td2 = tr.appendChild(document.createElement('td')); td2.textContent = v;
  });
  if (b.allocation_pct && b.allocation_pct.length) {
    const h = el.appendChild(document.createElement('div'));
    h.textContent = 'Allocation';
    h.style.marginTop = '8px';
    const t2 = el.appendChild(document.createElement('table'));
    b.allocation_pct.forEach(a => {
      const tr = t2.appendChild(document.createElement('tr'));
      tr.appendChild(document.createElement('td')).textContent = a.symbol;
      tr.appendChild(document.createElement('td')).textContent = a.pct + '%';
    });
  }
}

function renderCeoRisk(r) {
  const el = $('ceo-risk'); el.innerHTML = ''; el.classList.remove('ceo-unavailable');
  const rows = [
    ['Risk level', r.risk_level, 'ceo-risk-' + r.risk_level],
    ['Drawdown', r.drawdown_pct + '%', null],
    ['Daily loss', r.daily_loss_pct + '%', null],
    ['Treasury halted', r.treasury_halted ? 'YES' : 'no', r.treasury_halted ? 'ceo-risk-CRITICAL' : null],
    ['Emergency stopped', r.emergency_stopped ? 'YES' : 'no', r.emergency_stopped ? 'ceo-risk-CRITICAL' : null],
  ];
  const t = el.appendChild(document.createElement('table'));
  rows.forEach(([k, v, cls]) => {
    const tr = t.appendChild(document.createElement('tr'));
    tr.appendChild(document.createElement('td')).textContent = k;
    const td = tr.appendChild(document.createElement('td'));
    td.textContent = v;
    if (cls) td.classList.add(cls);
  });
  if (r.concentration_alerts && r.concentration_alerts.length) {
    const w = el.appendChild(document.createElement('div'));
    w.classList.add('warning-banner');
    w.textContent = 'Concentration > 40%: ' + r.concentration_alerts.join(', ');
  }
}

function renderCeoHealth(h) {
  const el = $('ceo-health'); el.innerHTML = ''; el.classList.remove('ceo-unavailable');
  const rows = [
    ['Feed connected', h.feed_connected ? 'YES' : 'NO'],
    ['Feed age (ms)', h.feed_age_ms === null ? 'DATA UNAVAILABLE' : String(h.feed_age_ms)],
    ['Agents running', h.running_agents + ' / ' + h.total_agents],
    ['Crashed', (h.crashed_agents || []).join(', ') || '—'],
    ['Stale', (h.stale_agents || []).join(', ') || '—'],
  ];
  const t = el.appendChild(document.createElement('table'));
  rows.forEach(([k, v]) => {
    const tr = t.appendChild(document.createElement('tr'));
    tr.appendChild(document.createElement('td')).textContent = k;
    tr.appendChild(document.createElement('td')).textContent = v;
  });
}

function renderCeoAgents(agents) {
  const el = $('ceo-agents'); el.innerHTML = ''; el.classList.remove('ceo-unavailable');
  if (!agents || !agents.length) { _unavailable(el); return; }
  const t = el.appendChild(document.createElement('table'));
  const thr = t.appendChild(document.createElement('tr'));
  ['Name', 'Role', 'Health', 'Detail', 'Restarts', 'Msgs'].forEach(h => {
    const th = thr.appendChild(document.createElement('th'));
    th.textContent = h;
  });
  agents.forEach(a => {
    const tr = t.appendChild(document.createElement('tr'));
    tr.appendChild(document.createElement('td')).textContent = a.name;
    tr.appendChild(document.createElement('td')).textContent = a.role;
    const td = tr.appendChild(document.createElement('td'));
    td.textContent = a.health;
    td.classList.add('ceo-health-' + a.health);
    tr.appendChild(document.createElement('td')).textContent = a.detail;
    tr.appendChild(document.createElement('td')).textContent = a.restarts;
    tr.appendChild(document.createElement('td')).textContent = a.msg_count;
  });
}

function renderCeoAudit(audit) {
  const el = $('ceo-audit'); el.innerHTML = ''; el.classList.remove('ceo-unavailable');
  if (!audit || !audit.records || !audit.records.length) { _unavailable(el); return; }
  const t = el.appendChild(document.createElement('table'));
  const thr = t.appendChild(document.createElement('tr'));
  ['#', 'Time', 'Agent', 'Action', 'Outcome', 'Confidence', 'Reason'].forEach(h => {
    const th = thr.appendChild(document.createElement('th'));
    th.textContent = h;
  });
  audit.records.forEach(r => {
    const tr = t.appendChild(document.createElement('tr'));
    tr.appendChild(document.createElement('td')).textContent = r.seq;
    tr.appendChild(document.createElement('td')).textContent = new Date(r.ts_ms).toLocaleTimeString();
    tr.appendChild(document.createElement('td')).textContent = r.agent;
    tr.appendChild(document.createElement('td')).textContent = r.action;
    tr.appendChild(document.createElement('td')).textContent = r.outcome;
    tr.appendChild(document.createElement('td')).textContent = r.confidence;
    tr.appendChild(document.createElement('td')).textContent = r.reason;
  });
}
```

VERIFY:
```bash
grep -c "renderCeoPage" src/infrastructure/web/static/kingdom.html
```
Must print at least `2` (route entry + function definition).

---

## STEP 10 — Add execution-warning banner reading `status.execution_warning`

Find the function `handleStatus` in `kingdom.html` (search for `function handleStatus`).

In the body of `handleStatus`, BEFORE the existing `State.equity = data.equity ?? null` line, add:

```javascript
  // Production migration: stash the execution warning so other pages can render it
  if (data.execution_warning) {
    State.executionWarning = data.execution_warning;
    State.executionEngine  = data.execution_engine || 'unknown';
    State.dataSource       = data.data_source || 'unknown';
    const topBanner = $('top-warning-banner');
    if (topBanner) {
      topBanner.style.display = 'block';
      topBanner.textContent = '⚠ ' + data.execution_warning;
    }
  }
```

Then find the top of the `<body>` tag and insert RIGHT AFTER `<body>` (use `grep -n "^<body" src/infrastructure/web/static/kingdom.html`):

```html
<div id="top-warning-banner" class="warning-banner" style="display:none; position:sticky; top:0; z-index:100;"></div>
```

VERIFY:
```bash
grep -c "top-warning-banner" src/infrastructure/web/static/kingdom.html
```
Must print at least `2` (HTML element + JS reference).

---

## STEP 11 — Make existing pages handle missing data

In every renderer (`renderPortfolioPage`, `renderTradingPage`, `renderAnalyticsPage`, `renderRiskPage`, `renderAgentsPage`) — find each function and add this as the FIRST executable line of the function body:

```javascript
  if (!State.connected) {
    const empty = document.querySelector('[data-page-content="' + State.currentPage + '"] .page-empty-state');
    /* The renderer continues anyway — empty data simply produces empty tables */
  }
```

Then locate every place where a renderer reads from `POSITIONS`, `TRADES`, `EQUITY_CURVE`, `MONTHLY_RETURNS`, or `SYMBOL_PRICES` and assigns it to a UI element. After each assignment, add a check:

```javascript
  if (!POSITIONS.length) { /* container.textContent = 'DATA UNAVAILABLE'; */ }
```

(You can leave the existing logic — empty arrays will render empty tables, which is acceptable for now. Just ensure no fabricated fallbacks remain.)

VERIFY:
```bash
grep -cE "Math\.random\(\)" src/infrastructure/web/static/kingdom.html
```
Must print `0`. (Math.random in PRODUCTION dashboard JS is forbidden.)

If any `Math.random()` remains, search for it and delete the surrounding logic — it is fabricating data.

---

## STEP 12 — Extend `test_paper_only.py` with mock-data guard

Open `tests/architecture/test_paper_only.py` and add this test at the end of the file:

```python
def test_no_mock_data_in_production_dashboard() -> None:
    """Production migration: dashboard JS must not contain random/mock data
    generators. Tests must use the FakePriceFeed in tests/_fixtures/ only.
    """
    dashboard = SRC.parent / "src/infrastructure/web/static/kingdom.html"
    text = dashboard.read_text(encoding="utf-8")
    forbidden = (
        "Math.random()",
        "1284567.89",
        "startDemoSimulator",
        "function simulateAgentMetrics() {\n  const",  # fake metric drift body
    )
    offenders = [m for m in forbidden if m in text]
    assert not offenders, (
        "Mock data pattern found in production dashboard: " + ", ".join(offenders)
    )


def test_simulator_gateway_deleted() -> None:
    """The synthetic-price gateway must not exist in production src/."""
    sim_path = SRC / "infrastructure/gateway/simulator.py"
    assert not sim_path.exists(), f"{sim_path} must be deleted in Production Migration"
```

VERIFY:
```bash
PYTHONPATH=src .venv/bin/python -m pytest --no-cov tests/architecture/test_paper_only.py -q 2>&1 | tail -5
```
Must show all tests passing.

---

## STEP 13 — Full test run

```bash
cd /home/claude/work && PYTHONPATH=src .venv/bin/python -m pytest --no-cov -q 2>&1 | tail -5
```

VERIFY: `285 passed` (283 baseline + 2 new tests from STEP 12). If less, look at the failure and fix it. Do NOT mark complete until green.

---

## STEP 14 — Update docs

### `README_TH.md`

Replace the first non-empty line (currently `# 👑 KINGDOM PRIME — AI-Powered Paper-Trading Ecosystem`) with:

```
# 👑 KINGDOM PRIME — Live-Data, Paper-Execution Trading System (Production Migration)
```

Replace the description line `ระบบเทรดจำลอง (PAPER ONLY — ...)` with:

```
ระบบเทรด **ราคา LIVE จาก Bitkub** + **execution ยังเป็น paper** (ปลอดภัย — ยังไม่ส่งออเดอร์จริง)
สถาปัตยกรรม 3 ชั้น + CEO Agent (audit trail). Production Migration: ลบ mock data, ลบ simulator, เหลือ live data path เท่านั้น.
```

### `docs/ARCHITECTURE.md`

Append at the end:

```markdown

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
```

### `SCORECARD.md`

Append at the end:

```markdown

---

## ✅ Phase P7 — Production Migration

| Item | Status |
|---|---|
| Mock data removed from dashboard | ✅ |
| `SimulatorGateway` deleted | ✅ |
| Demo/paper/sandbox mode rejected by `/api/mode/{x}` | ✅ |
| CEO Agent (Layer 2 observer) added | ✅ |
| `domain/audit/decision_log.py` + 18 tests | ✅ |
| `domain/reporting/ceo_report.py` + 23 tests | ✅ |
| CEO endpoints (`/api/ceo/{summary,audit,agents}`) | ✅ |
| CEO dashboard page tab | ✅ |
| `DATA UNAVAILABLE` empty states | ✅ |
| Execution-engine warning banner | ✅ |
| Architecture guard updated to block mock data | ✅ |
| All tests passing | ✅ 285 / 285 |

### What is intentionally NOT done

Live order placement against Bitkub REST. The `test_paper_only.py`
architecture guard remains in force. To enable live execution, a separate
session must add a signed Bitkub REST client, run dry-mode shadow tests
against the Bitkub sandbox, and gate behind manual approval.
```

VERIFY:
```bash
grep -c "Phase P7" SCORECARD.md
```
Must print `1`.

---

## STEP 15 — Zip and present

```bash
cd /home/claude
rm -rf /home/claude/work/.venv /home/claude/work/.pytest_cache /home/claude/work/.hypothesis
find /home/claude/work -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null
find /home/claude/work -name '*.egg-info' -type d -exec rm -rf {} + 2>/dev/null
cd /home/claude/work && zip -qr /mnt/user-data/outputs/kingdom_prime_production.zip . -x ".venv/*" "*.pyc" "__pycache__/*"
ls -la /mnt/user-data/outputs/kingdom_prime_production.zip
```

Then call `present_files` with the zip path so the user can download it.

VERIFY: `zip -l` shows ≥250 files, and the zip is < 5 MB.

---

## DONE

Your final user-facing message must include:
1. Confirmation that `285 passed` was achieved.
2. Confirmation that `grep -c "Math.random()" src/infrastructure/web/static/kingdom.html` returns `0`.
3. The download link from `present_files`.
4. A list of every step you completed.
5. Any step you SKIPPED and why (if you had to skip any, this is a failure — you should have fixed it instead).

DO NOT claim the migration is complete unless all 15 steps verified green.

--- END PROMPT ---
