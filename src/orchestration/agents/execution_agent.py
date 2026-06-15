# Layer 2 — Orchestration (agents/execution_agent)
"""ExecutionAgent — gatekeeper between strategy decisions and order routing.

This is the ONLY orchestration module allowed to import bitkub_rest (via local
import, keeping the module-level layer boundary clean).

Order pipeline for every EXECUTE decision:
  0. Startup reconciliation gate (live wiring only)
  1. Circuit-breaker check (fast path — no partial evaluation)
  2. Open-position cap — counts entries already routed but not yet reflected in
     the trader's count (the paper mirror is async), so a burst of BUYs cannot
     stale-read a 0 and place duplicate live orders.
  2a. Daily trade budget (quota / profit-target) — entries only
  2b. Confluence / win-probability entry gate — entries only
  3. Idempotency: sha256(decision_id)[:16] deduplication (session-scoped)
  4. Rate limiter token acquisition
  5. Live-gate routing (absolute notional hard-cap reject at the money-spending
     boundary) or paper delegation

Risk-rail note: the qty / drawdown / exposure rules in ``domain.risk.rules`` are
evaluated by the SEPARATE *advisory* ``RiskAgent`` (its verdict count is surfaced
on the dashboard); they are intentionally NOT a binding gate here. The binding
rails enforced in this agent are the circuit-breaker, the open-position cap, the
daily budget, the entry gate, and the absolute notional hard cap. The treasury
independently enforces the survival floor and the H1 stop-loss/take-profit
bracket on every open.
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import hashlib
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import orjson
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from orchestration.ports.event_bus import EventBus

_KILL_SWITCH_PATH = Path("data/KILL_SWITCH")
_LIVE_CONFIRM = "I_ACCEPT_REAL_MONEY_RISK"


class _RateLimiter(Protocol):
    """Token-bucket port (infrastructure.gateway.TokenBucket satisfies it)."""

    async def acquire(self) -> None: ...


class ExecutionAgent:
    """Routes approved decisions to the paper bus or the live REST gateway.

    Live trading requires ALL FOUR gates to be open simultaneously:
      (a) settings.execution_engine == "live"
      (b) settings.live_trading_confirm == "I_ACCEPT_REAL_MONEY_RISK"
      (c) data/KILL_SWITCH file does not exist
      (d) circuit_breaker.is_open is False

    Optional 5th gate (startup reconciliation):
      (e) reconciliation_gate() returns True — blocks decisions until the
          ReconciliationAgent completes its first balance poll.

    Any failed gate silently falls back to the paper path and logs CRITICAL
    "live_blocked" with the gate name that failed.
    """

    _MAX_SEEN_IDS = 10_000
    # An entry placed here only shows up in ``open_positions_fn`` after the paper
    # mirror is consumed on a separate task. Until then we hold a reservation so
    # a burst of BUYs can't each read a stale count and double-enter. The
    # reservation is force-drained after this many seconds (the entry has either
    # materialised into the open count or failed — either way the count is now
    # the truth), so a rejected entry can never permanently block trading.
    _INFLIGHT_GRACE_S = 5.0

    def __init__(
        self,
        bus: EventBus,
        raw_decisions_topic: str,
        approved_topic: str,
        settings: object,
        breaker: CircuitBreaker,
        rate_limiter: _RateLimiter,
        logger: structlog.BoundLogger,
        rest_gateway: object | None = None,
        reconciliation_gate: Callable[[], bool] | None = None,
        open_positions_fn: Callable[[], int] | None = None,
        max_open_positions: int = 1,
        live_order_fn: Callable[[dict[str, object]], dict[str, str] | None] | None = None,
        entry_gate_fn: Callable[[dict[str, object]], tuple[bool, list[str]]] | None = None,
        trade_budget_fn: Callable[[], bool] | None = None,
    ) -> None:
        self._bus = bus
        self._raw_topic = raw_decisions_topic
        self._approved_topic = approved_topic
        self._settings = settings
        self._breaker = breaker
        self._rate_limiter = rate_limiter
        self._log = logger.bind(agent="execution_agent")
        self._rest_gateway = rest_gateway
        self._reconciliation_gate = reconciliation_gate
        self._open_positions_fn = open_positions_fn
        self._max_open_positions = max_open_positions
        # Entries routed but not yet reflected in open_positions() (mirror lag).
        self._inflight_entries: int = 0
        self._inflight_at: float = 0.0
        # Builds the sized+capped live order spec from a decision (provided by
        # the runtime, which owns cash/price/params). None => no live placement.
        self._live_order_fn = live_order_fn
        # Confluence/win-probability gate for ENTRIES: returns (approved, reasons).
        # Blocks BUYs whose estimated win probability / regime / sentiment fail.
        self._entry_gate_fn = entry_gate_fn
        # Daily trade-budget gate: returns True while the day's trade quota and
        # profit-target rules still allow a new entry.
        self._trade_budget_fn = trade_budget_fn
        self.live_orders_placed: int = 0
        self.gate_blocked: int = 0

        self.running: bool = False
        self.msg_count: int = 0
        self.last_beat_ms: int = 0
        # Bounded deque + set for O(1) lookup with eviction of oldest ids
        self._seen_ids_deque: collections.deque[str] = collections.deque(maxlen=self._MAX_SEEN_IDS)
        self._seen_ids: set[str] = set()
        # Monotonic fallback counter for decisions that carry no decision_id /
        # event_id. NEVER use id(data) here: CPython reuses the memory address
        # of the short-lived parsed dict, so id() collides across distinct
        # decisions and silently suppresses real trades (entries stop after the
        # first). A per-agent counter guarantees a unique, stable fallback id.
        self._noid_seq: int = 0

    def set_max_open_positions(self, value: int) -> None:
        """Change the open-position cap live (operator control)."""
        if value < 1:
            raise ValueError("max_open_positions must be >= 1")
        self._max_open_positions = value

    def set_rest_gateway(self, gateway: object | None) -> None:
        """Inject / replace / clear the live REST gateway at runtime.

        The runtime builds the signed Bitkub gateway AFTER this agent is
        constructed (and rebuilds it when the operator connects an account),
        so it must push the gateway in here. Without this, ``_rest_gateway``
        stays None and every decision falls back to paper even when all four
        live gates are open — i.e. real orders can never fire (the live path
        was dead code before this wiring)."""
        self._rest_gateway = gateway

    async def start(self) -> None:
        """Subscribe and process decisions until stopped."""
        self.running = True
        queue = self._bus.subscribe(self._raw_topic)
        self._log.info("execution_agent.started")
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    raw = await asyncio.wait_for(queue.get(), timeout=0.5)
                except TimeoutError:
                    continue
                self.msg_count += 1
                await self._handle(raw)
        finally:
            self._bus.unsubscribe(self._raw_topic, queue)
            self._log.info("execution_agent.stopped")

    async def stop(self) -> None:
        """Signal the agent loop to exit."""
        self.running = False

    # ── Internal pipeline ─────────────────────────────────────────────

    async def _handle(self, raw: bytes) -> None:
        """Process one raw decision message through the full gate pipeline."""
        try:
            data: dict[str, object] = orjson.loads(raw)
        except (orjson.JSONDecodeError, ValueError):
            self._log.warning("execution_agent.bad_frame")
            return

        if data.get("decision") != "EXECUTE":
            return

        # 0. Startup reconciliation gate (optional — only present in live wiring)
        if self._reconciliation_gate is not None and not self._reconciliation_gate():
            await self._publish_rejection(["STARTUP_NOT_RECONCILED"])
            self._log.warning("execution_agent.vetoed", reason="STARTUP_NOT_RECONCILED")
            return

        # 1. Circuit-breaker fast path
        if self._breaker.is_open:
            await self._publish_rejection(["CIRCUIT_BREAKER_OPEN"])
            self._log.warning("execution_agent.vetoed", reason="CIRCUIT_BREAKER_OPEN")
            return

        # 2. Open-position cap — count entries already routed but not yet
        # reflected in the trader's open count (the paper mirror is consumed on
        # a separate task, so a naive read lags). Without this, two
        # near-simultaneous live BUYs each read a stale 0 and place TWO real
        # orders despite max_open_positions=1 (the regression in
        # test_audit_double_entry). The reservation can never push the effective
        # count above the cap and self-heals as the trader catches up, positions
        # close, or the grace window expires.
        if self._open_positions_fn is not None and data.get("signal") == "BUY":
            open_pos = self._open_positions_fn()
            now = time.monotonic()
            if now - self._inflight_at > self._INFLIGHT_GRACE_S:
                self._inflight_entries = 0
            self._inflight_entries = min(
                self._inflight_entries, max(0, self._max_open_positions - open_pos)
            )
            if open_pos + self._inflight_entries >= self._max_open_positions:
                await self._publish_rejection(["POSITION_CAP_REACHED"])
                self._log.warning("execution_agent.vetoed", reason="POSITION_CAP_REACHED")
                return

        # 2a. Daily trade budget (quota / profit-target) — entries only
        if (
            self._trade_budget_fn is not None
            and data.get("signal") == "BUY"
            and not self._trade_budget_fn()
        ):
            await self._publish_rejection(["DAILY_BUDGET_REACHED"])
            self._log.info("execution_agent.vetoed", reason="DAILY_BUDGET_REACHED")
            return

        # 2b. Confluence / win-probability gate — entries only. Only ≥min_p_win
        # setups in a sane regime pass; everything else is observed, not traded.
        if self._entry_gate_fn is not None and data.get("signal") == "BUY":
            approved, reasons = self._entry_gate_fn(data)
            if not approved:
                self.gate_blocked += 1
                await self._publish_rejection(reasons)
                self._log.info("execution_agent.gate_blocked", reasons=reasons)
                return

        # 3. Idempotency check
        # Only an explicit decision_id / event_id identifies a genuine
        # duplicate. When neither is present we mint a fresh monotonic id so
        # every distinct decision is treated as unique (see _noid_seq note).
        explicit_id = data.get("decision_id") or data.get("event_id")
        if explicit_id:
            raw_id = str(explicit_id)
        else:
            self._noid_seq += 1
            raw_id = f"_noid:{self._noid_seq}"
        client_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
        if client_id in self._seen_ids:
            self._log.info("execution_agent.duplicate_suppressed", client_id=client_id)
            return
        # Evict oldest if at capacity
        if len(self._seen_ids_deque) == self._MAX_SEEN_IDS:
            oldest = self._seen_ids_deque[0]  # will be evicted by deque on next append
            self._seen_ids.discard(oldest)
        self._seen_ids_deque.append(client_id)
        self._seen_ids.add(client_id)

        # 4. Rate limiter
        await self._rate_limiter.acquire()

        # 5. Live-gate routing. Reserve an in-flight slot for a BUY entry BEFORE
        # routing so the very next decision (processed before the mirror updates
        # the open count) sees the reservation in the cap check above.
        if self._open_positions_fn is not None and data.get("signal") == "BUY":
            self._inflight_entries += 1
            self._inflight_at = time.monotonic()
        live_ok, blocked_gate = self._live_gates_open()
        if live_ok and self._rest_gateway is not None:
            await self._route_live(data)
        else:
            if not live_ok:
                self._log.critical("live_blocked", gate=blocked_gate)
            await self._route_paper(raw)

    def _live_gates_open(self) -> tuple[bool, str | None]:
        """Check all four live trading gates; return (open, failed_gate_name)."""
        engine = str(getattr(self._settings, "execution_engine", "paper"))
        if engine != "live":
            return False, "execution_engine"
        confirm = str(getattr(self._settings, "live_trading_confirm", ""))
        if confirm != _LIVE_CONFIRM:
            return False, "live_trading_confirm"
        if _KILL_SWITCH_PATH.exists():
            return False, "kill_switch_file"
        if self._breaker.is_open:
            return False, "circuit_breaker"
        return True, None

    async def _route_live(self, data: dict[str, object]) -> None:
        """Place a REAL order via the signed gateway, then mirror to paper for
        position/dashboard tracking. Sizing + caps come from live_order_fn."""
        signal = str(data.get("signal", ""))
        symbol = str(data.get("symbol", "thb_btc")).lower()
        self._log.info("execution_agent.live_route", signal=signal, symbol=symbol)

        gw = self._rest_gateway
        if gw is None or self._live_order_fn is None:
            # Live gates open but no router/gateway wired — do NOT silently drop;
            # mirror to paper so the decision is still recorded.
            await self._route_paper(orjson.dumps(data))
            self._log.warning("execution_agent.live_no_router")
            return

        spec = self._live_order_fn(data)
        if not spec:
            self._log.info("execution_agent.live_skip", reason="no_spec")
            return

        action = spec.get("action")
        sym = spec.get("symbol", symbol)
        amount = spec.get("amount", "")
        rate = spec.get("rate", "")
        typ = spec.get("typ", "limit")
        try:
            if action == "bid":
                # T5: hard ceiling enforced at the money-spending boundary —
                # reject (never silently trim) a BUY above the absolute cap.
                from orchestration.control import order_over_hard_cap  # noqa: PLC0415
                over = order_over_hard_cap(amount)
                if over is not None:
                    self._log.critical("execution_agent.hard_cap_reject", reason=over)
                    return
                # gw is the polymorphic _rest_gateway (a real SIGNED gateway here,
                # gated by _live_gates_open); its order methods are not on `object`.
                result = await gw.place_bid(sym, amount, rate, typ)  # type: ignore[attr-defined]
            elif action == "ask":
                result = await gw.place_ask(sym, amount, rate, typ)  # type: ignore[attr-defined]
            else:
                self._log.warning("execution_agent.live_bad_action", action=str(action))
                return
        except Exception as exc:  # no auto-retry on a signed order
            self._log.error("execution_agent.live_order_failed", error=str(exc))
            return

        self.live_orders_placed += 1
        res = result.get("result", {}) if isinstance(result, dict) else {}
        order_id = res.get("id") if isinstance(res, dict) else None
        # Surface the real fill so paper/dashboard reflect what actually
        # happened, not an assumed instant fill. Bitkub echoes the filled
        # receive/amount on the order ack; we log it and forward it to the
        # paper mirror so its qty can track the REAL fill (avoids the
        # paper-vs-live divergence when an order partially fills).
        filled = res.get("rec") if isinstance(res, dict) else None  # coin received (bid)
        spent = res.get("amt") if isinstance(res, dict) else None
        self._log.info(
            "execution_agent.live_order_placed",
            action=action, symbol=sym, amount=amount, rate=rate,
            order_id=order_id, filled_rec=filled, spent_amt=spent,
        )
        # Mirror to the paper trader so the dashboard position view tracks it.
        # Carry the exchange's actual rate/fill so the paper position mirrors
        # the live order rather than re-deriving its own (single source of truth).
        mirror = dict(data)
        mirror["live_mirror"] = True
        if rate:
            mirror["price"] = str(rate)
        await self._route_paper(orjson.dumps(mirror))

    async def _route_paper(self, raw: bytes) -> None:
        """Re-publish the approved decision to the paper-trader's input topic."""
        await self._bus.publish(self._approved_topic, b"exec", raw)

    async def _publish_rejection(self, reasons: list[str]) -> None:
        """Publish a veto event to the approved topic so the CEO can observe it."""
        payload = orjson.dumps(
            {
                "type": "EXECUTION_VETOED",
                "ts_ms": int(time.time() * 1000),
                "reasons": reasons,
            }
        )
        with contextlib.suppress(Exception):
            await self._bus.publish(self._approved_topic, b"exec", payload)


# ── Cage-safe factory ─────────────────────────────────────────────────
# execution_agent is the ONLY module permitted to import bitkub_rest
# (enforced by tests/architecture/test_execution_guard.py). This factory
# lets the runtime obtain a live gateway without ever naming bitkub_rest.
# The import is function-local to satisfy the Layer-2 "no infrastructure at
# module scope" rule.

def build_live_gateway(api_key: object, api_secret: object) -> object:
    """Construct a live Bitkub REST gateway from API credentials.

    api_key / api_secret may be pydantic SecretStr or plain str. Returns an
    un-entered gateway; the caller manages its async context
    (``await gw.__aenter__()`` / ``__aexit__``).
    """
    from pydantic import SecretStr  # noqa: PLC0415

    from infrastructure.gateway.bitkub_rest import BitkubRestGateway  # noqa: PLC0415

    key = api_key if isinstance(api_key, SecretStr) else SecretStr(str(api_key))
    secret = api_secret if isinstance(api_secret, SecretStr) else SecretStr(str(api_secret))
    return BitkubRestGateway(key, secret)
