# Layer 2 — Orchestration (ports/event_store)
"""EventStore port: append-only audit log of canonical-JSON event envelopes."""
from __future__ import annotations

from typing import Protocol


class EventStore(Protocol):
    """Append-only log of serialized EventEnvelope bytes."""

    async def append(self, envelope_json: bytes) -> None:
        """Append one canonical-JSON envelope line."""
        ...

    async def replay(self, from_ms: int, to_ms: int) -> list[bytes]:
        """Return all envelope lines with ts_ms in [from_ms, to_ms]."""
        ...
