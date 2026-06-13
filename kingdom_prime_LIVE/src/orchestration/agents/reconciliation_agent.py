# Layer 2 — Orchestration (agents/reconciliation_agent)
"""ReconciliationAgent — polls BalanceSource and publishes reconciliation events.

On startup the agent is NOT reconciled. After the first successful balance poll
it sets is_reconciled=True, which the ExecutionAgent's startup gate reads.
"""
from __future__ import annotations

import asyncio
import time

import orjson
import structlog

from orchestration.ports.balance_source import BalanceSource
from orchestration.ports.event_bus import EventBus

_TOPIC_DEFAULT = "reconciliation.v1"


class ReconciliationAgent:
    """Polls BalanceSource every poll_interval_s and publishes reconciliation events.

    ExecutionAgent can use `agent.is_reconciled` as its startup gate.
    """

    def __init__(
        self,
        bus: EventBus,
        balance_source: BalanceSource,
        reconciliation_topic: str = _TOPIC_DEFAULT,
        logger: structlog.BoundLogger | None = None,
        poll_interval_s: float = 60.0,
    ) -> None:
        self._bus = bus
        self._source = balance_source
        self._topic = reconciliation_topic
        self._log = (logger or structlog.get_logger()).bind(agent="reconciliation")
        self._poll_interval = poll_interval_s

        self.running: bool = False
        self.msg_count: int = 0
        self.last_beat_ms: int = 0
        self._reconciled: bool = False
        # Last successfully polled real balances (symbol -> str amount).
        # Surfaced by PipelineRuntime.status() so the dashboard can show the
        # real Bitkub wallet once the account is connected.
        self.last_balances: dict[str, str] = {}

    @property
    def is_reconciled(self) -> bool:
        """True after at least one successful balance poll."""
        return self._reconciled

    async def start(self) -> None:
        """Poll balance source until stopped; first success marks as reconciled."""
        self.running = True
        self._log.info("reconciliation_agent.started", interval_s=self._poll_interval)
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                await self._poll()
                # Sleep in small chunks so stop() is responsive
                deadline = time.monotonic() + self._poll_interval
                while self.running and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)
        finally:
            self._log.info("reconciliation_agent.stopped")

    async def stop(self) -> None:
        """Signal the polling loop to exit."""
        self.running = False

    async def _poll(self) -> None:
        """Attempt one balance fetch and publish the result."""
        try:
            balances = await self._source.get_balance()
        except Exception as exc:
            self._log.warning(
                "reconciliation_agent.poll_failed",
                error=str(exc),
                reconciled=self._reconciled,
            )
            await self._publish(reconciled=False, balances={})
            return

        if not self._reconciled:
            self._log.info("reconciliation_agent.first_reconciliation")
            self._reconciled = True

        self.msg_count += 1
        str_balances = {k: str(v) for k, v in balances.items()}
        self.last_balances = str_balances
        await self._publish(reconciled=True, balances=str_balances)

    async def _publish(self, *, reconciled: bool, balances: dict[str, str]) -> None:
        payload = orjson.dumps(
            {
                "type": "RECONCILIATION",
                "ts_ms": int(time.time() * 1000),
                "reconciled": reconciled,
                "balances": balances,
            }
        )
        try:
            await self._bus.publish(self._topic, b"reconciliation", payload)
        except Exception:
            pass
