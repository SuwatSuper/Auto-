# Layer 2 — Orchestration (agents/probability)
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.analytics.indicators import rsi_wilder
from orchestration.ports.event_bus import EventBus


class ProbabilityAgent:
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
        self._prices: list[Decimal] = []
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("probability_agent.started")
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
                    if len(self._prices) > 500:
                        self._prices = self._prices[-500:]
                    rsi_vals = rsi_wilder(self._prices, 14)
                    rsi = rsi_vals[-1] if rsi_vals else Decimal("NaN")
                    # Honest: until RSI can actually be computed (warm-up), do NOT
                    # publish a fabricated 0.5 probability — stay silent.
                    if rsi.is_nan():
                        continue
                    prob_bull = (Decimal("100") - rsi) / Decimal("100")
                    out = orjson.dumps({"prob_bull": str(prob_bull), "rsi": str(rsi)})
                    await self._bus.publish(self._topic_out, b"probability", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("probability_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("probability_agent.stopped")

    async def stop(self) -> None:
        self.running = False
