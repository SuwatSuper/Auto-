from __future__ import annotations

from typing import Protocol


class EventPublisher(Protocol):
    async def publish(self, topic: str, key: bytes, value: bytes) -> None: ...
