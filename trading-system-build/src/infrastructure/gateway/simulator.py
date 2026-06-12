from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable

import structlog


class SimulatorGateway:
    _INTERVAL_S: float = 0.2
    _BASE_PRICE: float = 1_500_000.0
    _STEP: float = 500.0

    def __init__(self) -> None:
        self._rng = random.Random(42)
        self._price = self._BASE_PRICE
        self._log = structlog.get_logger(__name__)

    async def run(self, on_raw: Callable[[dict[str, object]], Awaitable[None]]) -> None:
        self._log.info("simulator.started")
        while True:
            step = self._rng.uniform(-self._STEP, self._STEP)
            self._price += step
            payload: dict[str, object] = {
                "stream": "market.ticker.thb_btc",
                "last": str(round(self._price, 2)),
                "ts": int(time.time()),
            }
            await on_raw(payload)
            await asyncio.sleep(self._INTERVAL_S)
