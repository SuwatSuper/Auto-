# Layer 3 — Infrastructure (gateway/rate_limiter)
"""Async token-bucket rate limiter."""
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable


class TokenBucket:
    """Async token bucket: capacity tokens refilled at refill_per_sec tokens/s.

    Thread/task-safe via asyncio.Lock.
    clock is injected for deterministic testing (defaults to time.monotonic).
    """

    def __init__(
        self,
        capacity: int,
        refill_per_sec: float,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._capacity = capacity
        self._refill_per_sec = refill_per_sec
        self._clock: Callable[[], float] = clock if clock is not None else time.monotonic
        self._tokens: float = float(capacity)
        self._last_refill: float = self._clock()
        self._lock: asyncio.Lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            while True:
                now = self._clock()
                elapsed = now - self._last_refill
                self._tokens = min(
                    float(self._capacity),
                    self._tokens + elapsed * self._refill_per_sec,
                )
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                wait_time = (1.0 - self._tokens) / self._refill_per_sec
                await asyncio.sleep(wait_time)
