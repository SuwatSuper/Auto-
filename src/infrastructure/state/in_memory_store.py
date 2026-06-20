# Layer 3 — Infrastructure (state/in_memory_store)
"""In-memory StateStore adapter for testing and P1 bootstrap."""
from __future__ import annotations


class InMemoryStateStore:
    """In-memory implementation of the StateStore port."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        """Return value for key, or None."""
        return self._data.get(key)

    async def set(self, key: str, value: bytes) -> None:
        """Store value under key."""
        self._data[key] = value

    async def keys(self, prefix: str = "") -> list[str]:
        """Return all keys matching prefix."""
        return [k for k in self._data if k.startswith(prefix)]
