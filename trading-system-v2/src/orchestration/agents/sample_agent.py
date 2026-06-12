from __future__ import annotations

from decimal import Decimal

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
        self._log = logger
        self.running: bool = False
        self.msg_count: int = 0
        self.latest_price: Decimal | None = None
        self._queue: object = None

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic)
        self._queue = queue
        self._log.info("sample_agent.started", name=self.name)
        try:
            while self.running:
                try:
                    raw_bytes = queue.get_nowait()
                except Exception:
                    import asyncio

                    try:
                        raw_bytes = await asyncio.wait_for(queue.get(), timeout=0.1)
                    except TimeoutError:
                        continue
                self.msg_count += 1
                try:
                    data: dict[str, object] = orjson.loads(raw_bytes)
                    price_val = data.get("price")
                    if price_val is not None:
                        self.latest_price = Decimal(str(price_val))
                except Exception as exc:
                    self._log.warning("sample_agent.parse_error", name=self.name, exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic, queue)
            self._log.info("sample_agent.stopped", name=self.name)

    async def stop(self) -> None:
        self.running = False

    def status(self) -> dict[str, object]:
        return {
            "name": self.name,
            "running": self.running,
            "msg_count": self.msg_count,
            "latest_price": str(self.latest_price) if self.latest_price is not None else None,
        }
