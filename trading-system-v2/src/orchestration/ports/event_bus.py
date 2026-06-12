# Layer 2 — Orchestration (ports/event_bus)
"""EventBus port: publish/subscribe interface for in-process event routing."""
from __future__ import annotations

import asyncio
from typing import Protocol


class EventBus(Protocol):
    """Async pub/sub bus for typed byte payloads."""

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        """Publish a message to the given topic."""
        ...

    def subscribe(self, topic: str, maxsize: int = 10_000) -> asyncio.Queue[bytes]:
        """Subscribe to a topic; returns an async queue receiving published values."""
        ...

    def unsubscribe(self, topic: str, queue: asyncio.Queue[bytes]) -> None:
        """Remove a previously-subscribed queue."""
        ...
