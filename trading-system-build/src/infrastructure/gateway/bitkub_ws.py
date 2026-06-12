from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

import orjson
import structlog
import websockets
import websockets.legacy.client


class BitkubWebSocketGateway:
    _BACKOFF_BASE: float = 1.0
    _BACKOFF_CAP: float = 30.0
    _HEARTBEAT_INTERVAL: float = 30.0

    def __init__(self, url: str) -> None:
        self._url = url
        self._log = structlog.get_logger(__name__)

    async def run(self, on_raw: Callable[[dict[str, object]], Awaitable[None]]) -> None:
        attempt = 0
        while True:
            try:
                await self._connect_and_consume(on_raw)
                attempt = 0
            except asyncio.CancelledError:
                self._log.info("bitkub_ws.cancelled")
                raise
            except Exception as exc:
                delay = self._backoff(attempt)
                self._log.warning(
                    "bitkub_ws.reconnecting",
                    attempt=attempt,
                    delay_s=round(delay, 2),
                    exc_info=exc,
                )
                await asyncio.sleep(delay)
                attempt += 1

    async def _connect_and_consume(
        self, on_raw: Callable[[dict[str, object]], Awaitable[None]]
    ) -> None:
        self._log.info("bitkub_ws.connecting", url=self._url)
        async with websockets.legacy.client.connect(self._url) as ws:
            self._log.info("bitkub_ws.connected", url=self._url)
            last_heartbeat = asyncio.get_event_loop().time()
            async for message in ws:
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= self._HEARTBEAT_INTERVAL:
                    self._log.info("bitkub_ws.heartbeat", url=self._url)
                    last_heartbeat = now
                payload: dict[str, object] = orjson.loads(message)
                await on_raw(payload)

    def _backoff(self, attempt: int) -> float:
        base: float = min(self._BACKOFF_BASE * float(2**attempt), self._BACKOFF_CAP)
        jitter: float = base * 0.2 * (random.random() * 2.0 - 1.0)
        return float(max(0.0, base + jitter))
