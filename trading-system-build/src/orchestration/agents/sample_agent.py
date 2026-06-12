from __future__ import annotations

import statistics
import time
from collections import deque

import orjson
import structlog

from infrastructure.eventbus.in_memory import InMemoryEventBus


class SampleAgent:
    _WINDOW_SIZE: int = 100

    def __init__(
        self,
        bus: InMemoryEventBus,
        topic: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self._bus = bus
        self._topic = topic
        self._log = logger
        self._latencies: deque[float] = deque(maxlen=self._WINDOW_SIZE)

    async def start(self) -> None:
        queue = self._bus.subscribe(self._topic)
        count = 0
        latest_price: str = "n/a"

        while True:
            raw_bytes = await queue.get()
            count += 1
            try:
                data: dict[str, object] = orjson.loads(raw_bytes)
                latest_price = str(data.get("price", "n/a"))
                ts_ms = data.get("ts_ms")
                if isinstance(ts_ms, int):
                    latency_ms = time.time_ns() // 1_000_000 - ts_ms
                    self._latencies.append(float(latency_ms))
            except Exception as exc:
                self._log.warning("sample_agent.parse_error", exc_info=exc)

            if count % 10 == 0:
                p50 = round(statistics.median(self._latencies), 2) if self._latencies else 0.0
                self._log.info(
                    "sample_agent.stats",
                    count=count,
                    latest_price=latest_price,
                    latency_ms_p50=p50,
                )
