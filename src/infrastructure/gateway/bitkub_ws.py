# Layer 3 — Infrastructure (gateway/bitkub_ws)
from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Awaitable, Callable

import structlog
from websockets.asyncio.client import connect


def iter_json_objects(text: str) -> list[dict[str, object]]:
    """Bitkub WS may concatenate multiple JSON objects in one frame."""
    decoder = json.JSONDecoder()
    out: list[dict[str, object]] = []
    idx, n = 0, len(text)
    while idx < n:
        while idx < n and text[idx] in " \t\r\n":
            idx += 1
        if idx >= n:
            break
        try:
            obj, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            break  # trailing garbage — keep what we parsed so far
        if isinstance(obj, dict):
            out.append(obj)
        idx = end
    return out


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
        # B6 fix: use websockets.asyncio.client.connect (new API, not legacy)
        self._log.info("bitkub_ws.connecting", url=self._url)
        async with connect(self._url) as ws:
            self._log.info("bitkub_ws.connected", url=self._url)
            last_heartbeat = asyncio.get_event_loop().time()
            async for message in ws:
                now = asyncio.get_event_loop().time()
                if now - last_heartbeat >= self._HEARTBEAT_INTERVAL:
                    self._log.info("bitkub_ws.heartbeat", url=self._url)
                    last_heartbeat = now
                try:
                    s = message.decode("utf-8", errors="replace") if isinstance(message, bytes) else message
                    for obj in iter_json_objects(s):
                        await on_raw(obj)
                except Exception as exc:
                    self._log.warning("bitkub_ws.bad_frame", error=str(exc))
                    continue

    def _backoff(self, attempt: int) -> float:
        base: float = min(self._BACKOFF_BASE * float(2**attempt), self._BACKOFF_CAP)
        jitter: float = base * 0.2 * (random.random() * 2.0 - 1.0)
        return float(max(0.0, base + jitter))
