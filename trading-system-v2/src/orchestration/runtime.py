# Layer 2 — Orchestration (runtime)
from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from decimal import Decimal

import orjson
import structlog

from infrastructure.config import Settings
from infrastructure.eventbus.in_memory import InMemoryEventBus
from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway
from infrastructure.gateway.simulator import SimulatorGateway
from orchestration.agents.sample_agent import SampleAgent
from orchestration.ports.price_feed import PriceFeed
from orchestration.supervisors.price_supervisor import PriceSupervisor

_AGENT_NAMES = ("agent_1", "agent_2", "agent_3")


class PipelineRuntime:
    def __init__(self, settings: Settings, logger: structlog.BoundLogger) -> None:
        self.settings = settings
        self.logger = logger
        # B1 fix: bus is created once in constructor and never replaced
        self.bus = InMemoryEventBus()
        self.mode: str = "simulator"
        self.feed: PriceFeed | None = None
        self.supervisor: PriceSupervisor | None = None
        self.supervisor_task: asyncio.Task[None] | None = None
        self.agents: dict[str, SampleAgent] = {
            name: SampleAgent(name, self.bus, settings.prices_topic, logger)
            for name in _AGENT_NAMES
        }
        self.agent_tasks: dict[str, asyncio.Task[None]] = {}
        self.start_time_ms: int = 0
        self.msg_count_window: deque[int] = deque(maxlen=60)
        self.emergency_stopped: bool = False
        self._latest_price: Decimal | None = None
        self._latest_latency_ms: int = 0
        self._msg_count_current: int = 0
        self._window_task: asyncio.Task[None] | None = None

    async def start(self, mode: str) -> None:
        self.mode = mode
        self.start_time_ms = int(time.time() * 1000)
        self.emergency_stopped = False

        feed: PriceFeed
        if mode == "simulator":
            feed = SimulatorGateway()
        else:
            feed = BitkubWebSocketGateway(self.settings.bitkub_ws_url)
        self.feed = feed

        self.supervisor = PriceSupervisor(
            feed, self._counting_bus(), self.settings.prices_topic, self.logger
        )
        self.supervisor_task = asyncio.create_task(self.supervisor.run())
        self._window_task = asyncio.create_task(self._tick_window())

        for name in _AGENT_NAMES:
            await self.start_agent(name)

    def _counting_bus(self) -> _CountingBusProxy:
        return _CountingBusProxy(self.bus, self)

    async def stop(self) -> None:
        for name in list(self.agent_tasks):
            await self.stop_agent(name)

        if self.supervisor_task and not self.supervisor_task.done():
            self.supervisor_task.cancel()
            # B7 fix: suppress only CancelledError and TimeoutError; log others
            try:
                await asyncio.wait_for(self.supervisor_task, timeout=2.0)
            except (asyncio.CancelledError, TimeoutError):
                pass
            except Exception:
                self.logger.warning("runtime.stop_supervisor_error", exc_info=True)

        if self._window_task and not self._window_task.done():
            self._window_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._window_task

    async def switch_mode(self, mode: str) -> None:
        # B1 fix: stop agents/feed/supervisor, recreate components but reuse same bus
        await self.stop()
        # Recreate agents using the SAME bus (do not replace self.bus)
        self.agents = {
            name: SampleAgent(name, self.bus, self.settings.prices_topic, self.logger)
            for name in _AGENT_NAMES
        }
        self.agent_tasks = {}
        await self.start(mode)

    async def start_agent(self, name: str) -> None:
        if name not in self.agents:
            return
        agent = self.agents[name]
        if name in self.agent_tasks and not self.agent_tasks[name].done():
            return
        agent.running = True
        task = asyncio.create_task(agent.start())
        self.agent_tasks[name] = task

    async def stop_agent(self, name: str) -> None:
        if name not in self.agents:
            return
        await self.agents[name].stop()
        if name in self.agent_tasks:
            task = self.agent_tasks.pop(name)
            if not task.done():
                task.cancel()
                # B7 fix: suppress only CancelledError and TimeoutError; log others
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass
                except Exception:
                    self.logger.warning("runtime.stop_agent_error", name=name, exc_info=True)

    async def emergency_stop(self) -> None:
        for name in list(self.agents):
            await self.stop_agent(name)
        self.emergency_stopped = True

    # B2 fix: add emergency_reset() to clear the emergency_stopped flag
    async def emergency_reset(self) -> None:
        """Clear the emergency_stopped flag. Does not auto-start anything."""
        self.emergency_stopped = False

    def record_message(self, price: Decimal, latency_ms: int) -> None:
        self._latest_price = price
        self._latest_latency_ms = max(0, latency_ms)  # B9 fix: clamp latency >= 0

    async def _tick_window(self) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            self.msg_count_window.append(self._msg_count_current)
            self._msg_count_current = 0

    def status(self) -> dict[str, object]:
        uptime_sec = int((time.time() * 1000 - self.start_time_ms) / 1000)
        window = list(self.msg_count_window)
        msg_per_sec = round(sum(window) / max(len(window), 1), 1)
        # B9 fix: add latency_precision field
        return {
            "mode": self.mode,
            "uptime_sec": uptime_sec,
            "msg_per_sec": msg_per_sec,
            "latency_ms": self._latest_latency_ms,
            "latency_precision": "ms",
            "latest_price": str(self._latest_price) if self._latest_price is not None else None,
            "emergency_stopped": self.emergency_stopped,
            "agents": [a.status() for a in self.agents.values()],
        }


class _CountingBusProxy:
    def __init__(self, bus: InMemoryEventBus, runtime: PipelineRuntime) -> None:
        self._bus = bus
        self._runtime = runtime

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        await self._bus.publish(topic, key, value)
        try:
            data: dict[str, object] = orjson.loads(value)
            price_val = data.get("price")
            ts_ms_val = data.get("ts_ms")
            if price_val is not None and isinstance(ts_ms_val, int):
                price = Decimal(str(price_val))
                raw_latency = int(time.time() * 1000) - ts_ms_val
                latency = max(0, raw_latency)  # B9 fix: clamp latency >= 0
                self._runtime.record_message(price, latency)
                self._runtime._msg_count_current += 1
        # B7 fix: only suppress CancelledError/TimeoutError; log other exceptions
        except (asyncio.CancelledError, TimeoutError):
            raise
        except Exception:
            self._runtime.logger.warning("counting_bus.parse_error", exc_info=True)
