# Live Trading Runbook (Operator) — Kingdom Prime

> Real money. Read this top to bottom before arming live. Every control endpoint
> below needs the header `X-API-Key: <DASHBOARD_API_KEY>` unless you are on the
> same machine (localhost is trusted).

This runbook covers going live on Bitkub with **real funds**, the guard rails
that protect you, and what to do when something goes wrong.

---

## 0. Safety model (what protects your money)

| Layer | Control | Where |
|---|---|---|
| **Hard cap (in code)** | No single live order may exceed **1,000,000 THB**; total deployable ≤ **5,000,000 THB**. Config *cannot* exceed these — enforced at validation **and** clamped again when the order is built. | `orchestration/control.py` (`HARD_CAP_SINGLE_ORDER_THB`, `HARD_CAP_DEPLOYABLE_THB`), `runtime_live._build_live_order` |
| Operator per-order cap | `max_single_order_thb` — your own (lower) ceiling. Required `> 0` to arm live. | `/api/risk/settings` |
| 4 live gates | `engine_live`, `confirm_token`, `kill_switch_clear`, `breaker_closed` — **all** must be open to place a real order. | `/api/execution/mode` |
| Treasury veto (C1) | A real BUY never fires if the account is halted / underfunded / would breach the survival floor. | `treasury.would_approve` |
| Real-balance close (C2) | A protective close never asks to sell more coin than the **real wallet** holds. | `runtime_live._live_close` |
| Reconciliation gate (M2) | Live orders do not arm against an **unverified** account (no successful balance reconciliation yet). | `runtime_live._live_orders_armed` |
| Circuit breaker / drawdown / kill switch | Halt trading on a crash, a daily-loss breach, or an operator kill file. | breaker + drawdown guardian + `data/KILL_SWITCH` |

These invariants are pinned by the `tests/orchestration/test_real_money_matrix.py`
and `test_live_safety.py` suites — do not weaken them without a replacement test.

---

## 1. Pre-flight checklist (before arming live)

1. **Paper-trade first.** Confirm the system runs clean in paper mode (`execution_engine=paper`) and the dashboard shows real ticks (not "DATA UNAVAILABLE").
2. **Connect the real account** (read-only reconciliation starts automatically):
   ```
   POST /api/credentials  { "api_key": "...", "api_secret": "..." }
   ```
   Confirm `GET /api/credentials/status` shows the account connected and that a first reconciliation has happened.
3. **Set a per-order cap** (your ceiling, below the hard cap):
   ```
   POST /api/risk/settings  { "max_single_order_thb": "5000" }
   ```
   Must be `> bitkub_min_order_thb` and `<= 1,000,000`. Start small.
4. **Check the gates are ready:**
   ```
   GET /api/execution/mode
   → { "mode": "paper", "gates": { engine_live, confirm_token, kill_switch_clear, breaker_closed }, "all_gates_open": ... }
   ```
   `kill_switch_clear` and `breaker_closed` must be `true`.

---

## 2. Arming live

```
POST /api/execution/mode
{ "mode": "live", "confirm": "I_ACCEPT_REAL_MONEY_RISK" }
```

The request is **rejected** (and stays paper) unless ALL of:
- the confirmation token matches exactly,
- `data/KILL_SWITCH` does not exist,
- the circuit breaker is closed,
- `max_single_order_thb` is `> 0`, `>= bitkub_min_order_thb`, and `<= 1,000,000` (hard cap).

On success the response shows `"mode": "live"` and `"all_gates_open": true`.

> Going back to paper is always allowed and never needs a token:
> `POST /api/execution/mode { "mode": "paper" }`.

---

## 3. Monitoring while live

| Check | Endpoint | Watch for |
|---|---|---|
| Live status | `GET /api/status` | `live_orders_armed`, `execution_mode`, drawdown, daily loss, feed connected |
| Executive view | `GET /api/ceo/summary` | risk level, emergency_stopped, treasury_halted |
| Audit trail | `GET /api/ceo/audit` | what fired, why, outcome |
| Control history | `GET /api/control/audit` | who changed what, when |
| Liveness / metrics | `GET /healthz`, `GET /metrics` | uptime, msg rate, latency |

Keep the dashboard open. The "Self-improvement" tab shows each agent's real
recent losses and parameter changes.

---

## 4. Emergency procedures

**STOP EVERYTHING NOW (panic button):**
```
POST /api/emergency_stop      # halts feed + all agents immediately
```
Then, if you must guarantee no further real orders even on restart, drop the
kill file:
```
touch data/KILL_SWITCH        # blocks arming live until removed
```

**Trip the circuit breaker** (halts trading, keeps the system observing):
```
POST /api/breaker/trip   { "reason": "operator halt" }
```
**Reset it** (requires the reset token):
```
POST /api/breaker/reset  { "token": "MANUAL_RESET_CONFIRMED" }
```

**Flatten positions** (close everything at market):
```
POST /api/positions/close_all
```

**Recover after an emergency stop:** `POST /api/emergency_reset` clears the flag
only — it does **not** auto-start. Press *Start All* or switch mode to resume.

---

## 5. Rollback to paper (safe default)

1. `POST /api/execution/mode { "mode": "paper" }` — disarms live instantly.
2. `POST /api/positions/close_all` if you want to be flat.
3. Investigate via `/api/ceo/audit` and the trade CSVs under `data/`.

The system is designed so that **paper is the safe resting state**: a missing
token, an open breaker, a present kill file, or an unverified account all degrade
to paper automatically.

---

## 6. Incident triage (quick reference)

| Symptom | Likely cause | Action |
|---|---|---|
| No real orders firing while "live" | a gate is closed | `GET /api/execution/mode` → find the `false` gate |
| "treasury veto" in logs | halted / underfunded / floor breach | check daily loss; reset breaker if appropriate |
| Orders bounce on exchange | per-order cap below `bitkub_min_order_thb` | raise `max_single_order_thb` |
| Account shows unverified | reconciliation hasn't succeeded | check API keys + connectivity; live stays disarmed (safe) |
| Cannot arm: "exceeds the hard ceiling" | cap > 1,000,000 THB | lower `max_single_order_thb` (the code ceiling cannot be raised at runtime) |

---

## 7. Changing the hard caps

The hard caps are **deliberately not operator-settable**. To change them you
edit `HARD_CAP_SINGLE_ORDER_THB` / `HARD_CAP_DEPLOYABLE_THB` in
`src/orchestration/control.py`, update `test_real_money_matrix.py`, and redeploy.
This is a code review + CI gate by design — a fat-finger on the dashboard can
never authorise an unbounded real order.
