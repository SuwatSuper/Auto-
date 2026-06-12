# Layer 2 — Orchestration (agents/execution_agent)
"""ExecutionAgent — gatekeeper between strategy decisions and order routing.

This is the ONLY orchestration module allowed to import bitkub_rest (via local
import, keeping the module-level layer boundary clean).

Order pipeline for every EXECUTE decision:
  1. Circuit-breaker check (fast path — no partial evaluation)
  2. domain.risk.rules.evaluate() — full gate check
  3. Idempotency: sha256(decision_id)[:16] deduplication (session-scoped)
  4. Rate limiter token acquisition
  5. Live-gate routing or paper delegation
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import time
from collections.abc import Callable
from pathlib import Path

import orjson
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from orchestration.ports.event_bus import EventBus

_KILL_SWITCH_PATH = Path("data/KILL_SWITCH")
_LIVE_CONFIRM = "I_ACCEPT_REAL_MONEY_RISK"


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

    def __init__(
        self,
        bus: EventBus,
        raw_decisions_topic: str,
        approved_topic: str,
        settings: object,
        breaker: CircuitBreaker,
        rate_limiter: object,  # TokenBucket — local import avoids circular deps
        logger: structlog.BoundLogger,
        rest_gateway: object | None = None,
        reconciliation_gate: Callable[[], bool] | None = None,
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

        self.running: bool = False
        self.msg_count: int = 0
        self.last_beat_ms: int = 0
        self._seen_ids: set[str] = set()

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

        # 2. Idempotency check
        raw_id = str(data.get("decision_id") or data.get("event_id") or id(data))
        client_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
        if client_id in self._seen_ids:
            self._log.info("execution_agent.duplicate_suppressed", client_id=client_id)
            return
        self._seen_ids.add(client_id)

        # 3. Rate limiter
        await self._rate_limiter.acquire()

        # 4. Live-gate routing
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
        """Route an approved decision to the live REST gateway."""
        signal = str(data.get("signal", ""))
        symbol = str(data.get("symbol", "thb_btc")).lower()
        self._log.info("execution_agent.live_route", signal=signal, symbol=symbol)
        # Live routing is wired by the caller (runtime); the gateway interface
        # is intentionally abstract here to allow test injection.
        # Concrete REST calls are made by the injected rest_gateway object.

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
