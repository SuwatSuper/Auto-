# Layer 2 — Orchestration (ports/state_store)
"""StateStore port: key-value persistence interface."""
from __future__ import annotations

from typing import Protocol


class StateStore(Protocol):
    """Async key-value store for bytes."""

    async def get(self, key: str) -> bytes | None:
        """Return the stored value for key, or None if absent."""
        ...

    async def set(self, key: str, value: bytes) -> None:
        """Store value under key."""
        ...

    async def keys(self, prefix: str = "") -> list[str]:
        """Return all keys matching the given prefix."""
        ...
