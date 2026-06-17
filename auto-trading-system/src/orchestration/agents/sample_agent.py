# Layer 2 — Orchestration (agents/sample_agent)
"""SampleAgent: consumes price events from the bus and tracks latest price."""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus


class SampleAgent:
    """Consumes price events from the event bus. Depends on EventBus port, not concrete adapter."""

    def __init__(
        self,
        name: str,
        bus: EventBus,
        topic: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self.name = name
        self._bus = bus
        self._topic = topic
        self._log = logger.bind(agent=name)
        self.running: bool = False
        self.msg_count: int = 0
        self.last_beat_ms: int = 0
        self.parse_failures: int = 0
        self.latest_price: Decimal | None = None
        self._queue: asyncio.Queue[bytes] | None = None

    async def start(self) -> None:
        """Consume events from bus until stop() is called."""
        self.running = True
        queue: asyncio.Queue[bytes] = self._bus.subscribe(self._topic)
        self._queue = queue
        self._log.info("sample_agent.started")
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    async with asyncio.timeout(0.5):
                        raw_bytes = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data: dict[str, object] = orjson.loads(raw_bytes)
                    price_val = data.get("price")
                    if price_val is not None:
                        self.latest_price = Decimal(str(price_val))
                except (orjson.JSONDecodeError, InvalidOperation, ValueError) as exc:
                    self.parse_failures += 1
                    self._log.warning("sample_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic, queue)
            self._queue = None
            self._log.info("sample_agent.stopped")

    async def stop(self) -> None:
        """Signal the agent to stop on next timeout."""
        self.running = False

    def status(self) -> dict[str, object]:
        """Return current agent status."""
        return {
            "name": self.name,
            "running": self.running,
            "msg_count": self.msg_count,
            "parse_failures": self.parse_failures,
            "latest_price": str(self.latest_price) if self.latest_price is not None else None,
        }
