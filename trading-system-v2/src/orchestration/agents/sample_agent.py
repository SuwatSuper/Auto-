# Layer 2 — Orchestration (agents/sample_agent)
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus


class SampleAgent:
    def __init__(
        self,
        name: str,
        bus: InMemoryEventBus,
        topic: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self.name = name
        self._bus = bus
        self._topic = topic
        self._log = logger.bind(agent=name)
        self.running: bool = False
        self.msg_count: int = 0
        self.parse_failures: int = 0  # B5 fix: track parse failures
        self.latest_price: Decimal | None = None
        self._queue: asyncio.Queue[bytes] | None = None

    async def start(self) -> None:
        # B5 fix: clean event-driven loop with asyncio.timeout, imports at top
        self.running = True
        queue: asyncio.Queue[bytes] = self._bus.subscribe(self._topic)
        self._queue = queue
        self._log.info("sample_agent.started")
        try:
            while self.running:
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
                    # B5 fix: narrow exception handling, increment parse_failures
                    self.parse_failures += 1
                    self._log.warning("sample_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic, queue)
            self._queue = None
            self._log.info("sample_agent.stopped")

    async def stop(self) -> None:
        self.running = False

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "running": self.running,
            "msg_count": self.msg_count,
            "parse_failures": self.parse_failures,  # B5 fix: include in status
            "latest_price": str(self.latest_price) if self.latest_price is not None else None,
        }
