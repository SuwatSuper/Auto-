# Layer 2 — Orchestration (agents/entry_exit)
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.strategy.base import Signal
from domain.strategy.ema_cross import EmaCrossStrategy
from orchestration.ports.event_bus import EventBus


class EntryExitAgent:
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
        self._strategy = EmaCrossStrategy()
        self.running = False
        self.msg_count = 0
        self.signal_count = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("entry_exit_agent.started")
        try:
            while self.running:
                try:
                    async with asyncio.timeout(0.5):
                        raw = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data = orjson.loads(raw)
                    price = Decimal(str(data.get("price", "0")))
                    ts_ms = int(data.get("ts_ms", 0))
                    signal = self._strategy.on_price(price, ts_ms)
                    if signal != Signal.HOLD:
                        self.signal_count += 1
                        out = orjson.dumps({"signal": signal.value, "price": str(price), "ts_ms": ts_ms})
                        await self._bus.publish(self._topic_out, b"signal", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("entry_exit_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("entry_exit_agent.stopped")

    async def stop(self) -> None:
        self.running = False
