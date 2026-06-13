# Layer 2 — Orchestration (supervisors/supervisor)
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import structlog


class Supervisor:
    def __init__(
        self,
        name: str,
        coro_factory: Callable[[], Awaitable[None]],
        logger: structlog.BoundLogger,
        max_restarts: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
    ) -> None:
        self._name = name
        self._coro_factory = coro_factory
        self._log = logger
        self._max_restarts = max_restarts
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._restart_count = 0
        self._running = False

    async def run(self) -> None:
        self._running = True
        while self._running:
            try:
                await self._coro_factory()
                self._restart_count = 0
            except asyncio.CancelledError:
                self._log.info("supervisor.cancelled", name=self._name)
                raise
            except Exception as exc:
                self._restart_count += 1
                if self._restart_count > self._max_restarts:
                    self._log.error(
                        "supervisor.max_restarts_exceeded",
                        name=self._name,
                        restarts=self._restart_count,
                        exc_info=exc,
                    )
                    raise
                delay = min(
                    self._backoff_base * (2 ** (self._restart_count - 1)),
                    self._backoff_cap,
                )
                self._log.warning(
                    "supervisor.restarting",
                    name=self._name,
                    restart=self._restart_count,
                    delay_s=round(delay, 2),
                    exc_info=exc,
                )
                await asyncio.sleep(delay)

    def stop(self) -> None:
        self._running = False
