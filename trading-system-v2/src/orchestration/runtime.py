# Layer 2 — Orchestration (runtime)
"""PipelineRuntime: wires feed, supervisor, and agents behind ports."""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import time
from collections import deque
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from orchestration.agents.sample_agent import SampleAgent
from orchestration.ports.clock import Clock
from orchestration.ports.event_bus import EventBus
from orchestration.ports.event_store import EventStore
from orchestration.ports.price_feed import PriceFeed
from orchestration.ports.state_store import StateStore
from orchestration.supervisors.price_supervisor import PriceSupervisor

_AGENT_NAMES = ("agent_1", "agent_2", "agent_3")


@dataclasses.dataclass(frozen=True)
class RuntimeDeps:
    """Frozen dataclass of ports + factories for PipelineRuntime."""

    bus: EventBus
    clock: Clock
    state_store: StateStore
    event_store: EventStore
    feed_factory: Callable[[str], PriceFeed]
    prices_topic: str = "prices.thb_btc.v1"


class PipelineRuntime:
    """Orchestrates feed, supervisor, and agents around a single shared bus."""

    def __init__(
        self,
        settings: object,
        logger: structlog.BoundLogger,
        deps: RuntimeDeps | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger
        self._deps = deps

        # Bus: prefer injected (deps), otherwise create lazily via _CountingBusProxy
        # The actual concrete bus is stored in _bus_impl; _counting_bus wraps it.
        # For backwards-compat when deps=None, a concrete bus is built at runtime
        # (this path is only used in tests that don't yet provide deps).
        self._bus_impl: EventBus | None = deps.bus if deps is not None else None
        self.mode: str = "simulator"
        self.feed: PriceFeed | None = None
        self.supervisor: PriceSupervisor | None = None
        self.supervisor_task: asyncio.Task[None] | None = None
        self.agents: dict[str, SampleAgent] = {}
        self.agent_tasks: dict[str, asyncio.Task[None]] = {}
        self.start_time_ms: int = 0
        self.msg_count_window: deque[int] = deque(maxlen=60)
        self.emergency_stopped: bool = False
        self._latest_price: Decimal | None = None
        self._latest_latency_ms: int = 0
        self._msg_count_current: int = 0
        self._window_task: asyncio.Task[None] | None = None

    @property
    def bus(self) -> EventBus:
        """Return the underlying event bus (for WS subscriptions and direct tests)."""
        if self._bus_impl is None:
            raise RuntimeError("PipelineRuntime not started — no bus available")
        return self._bus_impl

    def _ensure_bus(self) -> EventBus:
        """Return bus, creating an in-memory one if no deps provided."""
        if self._bus_impl is None:
            from infrastructure.eventbus.in_memory import InMemoryEventBus  # noqa: PLC0415

            self._bus_impl = InMemoryEventBus()
        return self._bus_impl

    def _make_agents(self) -> dict[str, SampleAgent]:
        bus = self._ensure_bus()
        topic: str = getattr(self.settings, "prices_topic", "prices.thb_btc.v1")
        return {
            name: SampleAgent(name, bus, topic, self.logger)
            for name in _AGENT_NAMES
        }

    async def start(self, mode: str) -> None:
        """Start feed, supervisor, and agents in the given mode."""
        self.mode = mode
        now = time.time() * 1000
        self.start_time_ms = int(now)
        self.emergency_stopped = False

        bus = self._ensure_bus()
        topic: str = getattr(self.settings, "prices_topic", "prices.thb_btc.v1")
        ws_url: str = getattr(self.settings, "bitkub_ws_url", "")

        feed: PriceFeed
        if self._deps is not None:
            feed = self._deps.feed_factory(mode)
        else:
            # Fallback for tests without deps (imports infra here to avoid top-level violation)
            if mode == "simulator":
                from infrastructure.gateway.simulator import SimulatorGateway  # noqa: PLC0415

                feed = SimulatorGateway()
            else:
                from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway  # noqa: PLC0415

                feed = BitkubWebSocketGateway(ws_url)
        self.feed = feed

        counting_bus = _CountingBusProxy(bus, self)
        self.supervisor = PriceSupervisor(feed, counting_bus, topic, self.logger)
        self.supervisor_task = asyncio.create_task(self.supervisor.run())
        self._window_task = asyncio.create_task(self._tick_window())

        self.agents = self._make_agents()
        self.agent_tasks = {}
        for name in _AGENT_NAMES:
            await self.start_agent(name)

    async def stop(self) -> None:
        """Stop all agents, supervisor, and background tasks."""
        for name in list(self.agent_tasks):
            await self.stop_agent(name)

        if self.supervisor_task and not self.supervisor_task.done():
            self.supervisor_task.cancel()
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
        """Switch mode, reusing the same bus (B1 fix)."""
        await self.stop()
        self.agents = self._make_agents()
        self.agent_tasks = {}
        await self.start(mode)

    async def start_agent(self, name: str) -> None:
        """Start a named agent if not running."""
        if name not in self.agents:
            return
        agent = self.agents[name]
        if name in self.agent_tasks and not self.agent_tasks[name].done():
            return
        agent.running = True
        self.agent_tasks[name] = asyncio.create_task(agent.start())

    async def stop_agent(self, name: str) -> None:
        """Stop a named agent."""
        if name not in self.agents:
            return
        await self.agents[name].stop()
        if name in self.agent_tasks:
            task = self.agent_tasks.pop(name)
            if not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, TimeoutError):
                    pass
                except Exception:
                    self.logger.warning("runtime.stop_agent_error", name=name, exc_info=True)

    async def emergency_stop(self) -> None:
        """Emergency stop: cancel all agents and supervisor."""
        for name in list(self.agents):
            await self.stop_agent(name)
        if self.supervisor_task and not self.supervisor_task.done():
            self.supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self.supervisor_task, timeout=2.0)
        self.emergency_stopped = True

    async def emergency_reset(self) -> None:
        """B2 fix: clear emergency_stopped without auto-starting (distinct from start)."""
        self.emergency_stopped = False

    def record_message(self, price: Decimal, latency_ms: int) -> None:
        """Record a processed price message for metrics."""
        self._latest_price = price
        self._latest_latency_ms = max(0, latency_ms)

    async def _tick_window(self) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            self.msg_count_window.append(self._msg_count_current)
            self._msg_count_current = 0

    def status(self) -> dict[str, object]:
        """Return current runtime status for the dashboard."""
        uptime_sec = int((time.time() * 1000 - self.start_time_ms) / 1000)
        window = list(self.msg_count_window)
        msg_per_sec = round(sum(window) / max(len(window), 1), 1)
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
    """Wraps the EventBus to track price-message metrics."""

    def __init__(self, bus: EventBus, runtime: PipelineRuntime) -> None:
        self._bus = bus
        self._runtime = runtime
        self.parse_failures: int = 0

    def subscribe(self, topic: str, maxsize: int = 10_000) -> asyncio.Queue[bytes]:
        """Delegate subscribe to the underlying bus."""
        return self._bus.subscribe(topic, maxsize)

    def unsubscribe(self, topic: str, queue: asyncio.Queue[bytes]) -> None:
        """Delegate unsubscribe to the underlying bus."""
        self._bus.unsubscribe(topic, queue)

    async def publish(self, topic: str, key: bytes, value: bytes) -> None:
        """Publish and record metrics; log unexpected errors (B7 fix)."""
        await self._bus.publish(topic, key, value)
        try:
            data: dict[str, object] = orjson.loads(value)
            price_val = data.get("price")
            ts_ms_val = data.get("ts_ms")
            if price_val is not None and isinstance(ts_ms_val, int):
                price = Decimal(str(price_val))
                raw_latency = int(time.time() * 1000) - ts_ms_val
                self._runtime.record_message(price, max(0, raw_latency))
                self._runtime._msg_count_current += 1
        except (asyncio.CancelledError, TimeoutError):
            raise
        except (orjson.JSONDecodeError, InvalidOperation, KeyError, ValueError, TypeError):
            self.parse_failures += 1
            self._runtime.logger.warning("counting_bus.parse_error", exc_info=True)
        except Exception:
            self.parse_failures += 1
            self._runtime.logger.error("counting_bus.unexpected_error", exc_info=True)
