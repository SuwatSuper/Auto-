# Layer 3 — Infrastructure (events/in_memory_event_store)
"""In-memory EventStore adapter for testing and P1 bootstrap."""
from __future__ import annotations

import json


class InMemoryEventStore:
    """In-memory implementation of the EventStore port."""

    def __init__(self) -> None:
        self._lines: list[bytes] = []

    async def append(self, envelope_json: bytes) -> None:
        """Append one canonical-JSON envelope line."""
        self._lines.append(envelope_json)

    async def replay(self, from_ms: int, to_ms: int) -> list[bytes]:
        """Return all envelopes with ts_ms in [from_ms, to_ms]."""
        result: list[bytes] = []
        for line in self._lines:
            try:
                obj = json.loads(line)
                ts = obj.get("ts_ms", 0)
                if from_ms <= ts <= to_ms:
                    result.append(line)
            except (json.JSONDecodeError, AttributeError):
                continue
        return result
