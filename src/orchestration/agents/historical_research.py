# Layer 2 — Orchestration (agents/historical_research)
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus


class HistoricalResearchAgent:
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
        self._prices: list[Decimal] = []

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("historical_research_agent.started")
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
                    price = Decimal(str(data.get("price", "0")))
                    self._prices.append(price)
                    if len(self._prices) > 1000:
                        self._prices = self._prices[-1000:]
                    out = orjson.dumps({
                        "price_count": len(self._prices),
                        "latest_price": str(price),
                    })
                    await self._bus.publish(self._topic_out, b"history", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("historical_research_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("historical_research_agent.stopped")

    async def stop(self) -> None:
        self.running = False
