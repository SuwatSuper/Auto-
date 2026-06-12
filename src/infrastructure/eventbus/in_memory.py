from __future__ import annotations

import asyncio
import contextlib

import structlog


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[bytes]]] = {}
        self._log = structlog.get_logger(__name__)

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        queues = self._subs.get(topic, [])
        for queue in queues:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                self._log.warning("event_bus.queue_full_drop_oldest", topic=topic)
            await queue.put(value)

    def subscribe(self, topic: str, maxsize: int = 10_000) -> asyncio.Queue[bytes]:
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=maxsize)
        self._subs.setdefault(topic, []).append(queue)
        return queue

    def unsubscribe(self, topic: str, queue: asyncio.Queue[bytes]) -> None:
        subs = self._subs.get(topic, [])
        with contextlib.suppress(ValueError):
            subs.remove(queue)
