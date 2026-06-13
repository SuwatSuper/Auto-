from __future__ import annotations

import asyncio
import contextlib

import structlog


class InMemoryEventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue[bytes]]] = {}
        self._log = structlog.get_logger(__name__)
        self._dropped: dict[str, int] = {}

    @property
    def dropped_messages(self) -> int:
        """Total number of messages dropped across all topics due to full queues."""
        return sum(self._dropped.values())

    def dropped_by_topic(self) -> dict[str, int]:
        return dict(self._dropped)

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        queues = self._subs.get(topic, [])
        for queue in queues:
            if queue.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                self._dropped[topic] = self._dropped.get(topic, 0) + 1
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
