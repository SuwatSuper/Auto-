# Layer 2 — Orchestration (agents/supreme)
from __future__ import annotations

import asyncio
import time
from decimal import InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus


class SupremeAgent:
    """Aggregates signals from all department agents and makes final decisions."""

    def __init__(
        self,
        bus: EventBus,
        topic_in: str,
        topic_out: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self._bus = bus
        self._topic_in = topic_in
        self._topic_out = topic_out
        self._log = logger
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self.decision_count = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("supreme_agent.started")
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    async with asyncio.timeout(0.5):
                        raw = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data = orjson.loads(raw)
                    signal = data.get("signal", "HOLD")
                    decision = "EXECUTE" if signal in ("BUY", "SELL") else "OBSERVE"
                    self.decision_count += 1
                    # Stamp every decision with a unique id so the execution
                    # gate's idempotency check identifies genuine duplicates
                    # instead of falling back to id(data) (unstable). Counter +
                    # timestamp is unique within a run and human-traceable.
                    decision_id = f"sup-{self.decision_count}-{int(time.time() * 1000)}"
                    out = orjson.dumps(
                        {"decision": decision, "signal": signal, "decision_id": decision_id}
                    )
                    await self._bus.publish(self._topic_out, b"supreme", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("supreme_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("supreme_agent.stopped")

    async def stop(self) -> None:
        self.running = False
