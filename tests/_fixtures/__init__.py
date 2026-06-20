"""Test-only deterministic price feed.

This fixture exists ONLY under tests/ — it is never imported from src/.
The Production Migration removed every synthetic-data path from production
code; tests must supply their own fake feeds via dependency injection.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class FakePriceFeed:
    """Emits deterministic price ticks at a fast cadence for tests."""

    def __init__(self, interval_s: float = 0.05, base: float = 1_500_000.0) -> None:
        self._interval_s = interval_s
        self._base = base
        self._step = 0

    async def run(self, on_raw: Callable[[dict[str, object]], Awaitable[None]]) -> None:
        while True:
            self._step += 1
            await on_raw({
                "stream": "market.ticker.thb_btc",
                "last": str(round(self._base + self._step * 1.0, 2)),
                "ts": int(time.time()),
            })
            await asyncio.sleep(self._interval_s)
