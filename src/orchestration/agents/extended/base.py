# Layer 2 — Orchestration (agents/extended/base)
"""Shared lifecycle bases for the extended department agents.

``_AgentBase`` provides the common AgentLike surface (heartbeat / counters /
learner). ``PeriodicAgent`` runs ``tick()`` on an interval; ``PriceListenerAgent``
subscribes to the price topic and maintains a rolling close series. Concrete
agents live in ``price_agents`` and ``periodic_agents``.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation
from typing import Protocol

import orjson
import structlog

from orchestration.agents.learning import Learner
from orchestration.ports.event_bus import EventBus


class RuntimeView(Protocol):
    """Minimal read/act surface an agent needs from the runtime."""

    def status(self) -> dict[str, object]: ...
    def trip_breaker(self, reason: str = ...) -> dict[str, object]: ...
    async def send_alert(self, message: str, level: str = ...) -> bool: ...


def _f(value: object, default: float = 0.0) -> float:
    """Best-effort float conversion (never raises)."""
    try:
        if value is None:
            return default
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ── shared lifecycle bases ───────────────────────────────────────────
class _AgentBase:
    """Common AgentLike surface (running / heartbeat / counters / detail)."""

    role: str = ""

    def __init__(self, name: str, logger: structlog.BoundLogger, kind: str = "reliability") -> None:
        self.name = name
        self._log = logger
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self.detail: str = ""
        self.learner = Learner(name, kind)

    async def stop(self) -> None:
        self.running = False


class PeriodicAgent(_AgentBase):
    """Runs ``tick()`` on an interval, refreshing the heartbeat every second so
    long intervals never look stale to the watchdog."""

    interval: float = 3.0

    async def start(self) -> None:
        self.running = True
        self._log.info("agent.started", agent=self.name)
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    await self.tick()
                    self.msg_count += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # an agent must never crash the loop
                    self._log.warning("agent.tick_error", agent=self.name, exc_info=exc)
                slept = 0.0
                while slept < self.interval and self.running:
                    step = min(1.0, self.interval - slept)
                    await asyncio.sleep(step)
                    slept += step
                    self.last_beat_ms = int(time.time() * 1000)
        finally:
            self._log.info("agent.stopped", agent=self.name)

    async def tick(self) -> None:  # pragma: no cover - overridden
        ...


class PriceListenerAgent(_AgentBase):
    """Subscribes to the price topic and maintains a rolling close series."""

    def __init__(
        self, name: str, bus: EventBus, prices_topic: str, logger: structlog.BoundLogger,
        kind: str = "reliability",
    ) -> None:
        super().__init__(name, logger, kind)
        self._bus = bus
        self._topic_in = prices_topic
        self._topic_out: str | None = None
        self._prices: list[Decimal] = []
        self.signal_count = 0
        # Smoothing: don't re-publish the SAME action more than once per this
        # many seconds, so a fast tick stream can't flood the decision pipeline.
        self._emit_throttle_s = 1.0
        self._last_emit_at: dict[str, float] = {}

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("agent.started", agent=self.name)
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    async with asyncio.timeout(0.5):
                        raw = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data = orjson.loads(raw)
                    price = Decimal(str(data.get("price", "0")))
                    ts_ms = int(data.get("ts_ms", 0)) or int(time.time() * 1000)
                    if price <= 0:
                        continue
                    self._prices.append(price)
                    if len(self._prices) > 600:
                        self._prices = self._prices[-600:]
                    await self.on_price(price, ts_ms)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("agent.parse_error", agent=self.name, exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("agent.stopped", agent=self.name)

    async def on_price(self, price: Decimal, ts_ms: int) -> None:  # pragma: no cover
        ...

    async def _emit(self, action: str, price: Decimal, ts_ms: int) -> None:
        if self._topic_out is None:
            return
        # Throttle repeats of the same action to keep the pipeline smooth.
        now = time.monotonic()
        if now - self._last_emit_at.get(action, 0.0) < self._emit_throttle_s:
            return
        self._last_emit_at[action] = now
        self.signal_count += 1
        # Record the prediction so the REAL outcome can be graded later.
        self.learner.predict(action, price, ts_ms)
        # `source` lets the Supreme commander tally a real multi-agent
        # consensus instead of acting on each lone signal.
        out = orjson.dumps(
            {"signal": action, "price": str(price), "ts_ms": ts_ms, "source": self.name}
        )
        await self._bus.publish(self._topic_out, b"signal", out)

    def _hr_txt(self) -> str:
        hr = self.learner.hit_rate()
        return f"{hr * 100:.0f}% ({self.learner.resolved} ไม้)" if hr is not None else "—"
