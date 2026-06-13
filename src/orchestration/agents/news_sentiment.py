# Layer 2 — Orchestration (agents/news_sentiment)
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus


class NewsSentimentAgent:
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
        self.parse_failures = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("news_sentiment_agent.started")
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
                    score = Decimal(str(data.get("score", "0")))
                    out = orjson.dumps({"sentiment_score": str(score), "source": "news"})
                    await self._bus.publish(self._topic_out, b"sentiment", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self.parse_failures += 1
                    self._log.warning("news_sentiment_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("news_sentiment_agent.stopped")

    async def stop(self) -> None:
        self.running = False
