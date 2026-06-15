# Layer 2 — Orchestration (runtime)
"""PipelineRuntime: wires feed, supervisor, and agents behind ports.

The behaviour is split across cohesive mixins (agents / status / risk / live /
memory) defined in sibling ``runtime_*`` modules; this module owns construction,
the lifecycle (start/stop/loops), alerts, and composes the final class.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.risk.circuit_breaker import CircuitBreaker
from orchestration.agents.ceo_agent import CeoAgent
from orchestration.agents.learning import Learner
from orchestration.agents.paper_trader import PaperTraderAgent
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.ports.event_bus import EventBus
from orchestration.ports.price_feed import PriceFeed
from orchestration.ports.state_store import StateStore
from orchestration.runtime_agents import _AgentsMixin
from orchestration.runtime_base import _TOPIC_NEWS_RAW, AgentLike, RuntimeDeps, _RuntimeBase
from orchestration.runtime_live import _LiveTradingMixin
from orchestration.runtime_memory import _MemoryMixin
from orchestration.runtime_risk import _RiskControlMixin
from orchestration.runtime_status import _StatusMixin
from orchestration.supervisors.price_supervisor import PriceSupervisor


class PipelineRuntime(
    _AgentsMixin,
    _StatusMixin,
    _RiskControlMixin,
    _LiveTradingMixin,
    _MemoryMixin,
    _RuntimeBase,
):
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
        # Production migration: only 'live' mode exists. Kept as a field for
        # backwards-compat with the status payload, but never set to anything else.
        self.mode: str = "live"
        self.feed: PriceFeed | None = None
        self.supervisor: PriceSupervisor | None = None
        self.supervisor_task: asyncio.Task[None] | None = None
        self.agents: dict[str, AgentLike] = {}
        self.agent_tasks: dict[str, asyncio.Task[None]] = {}
        self.start_time_ms: int = 0
        self.msg_count_window: deque[int] = deque(maxlen=60)
        self.emergency_stopped: bool = False
        self._latest_price: Decimal | None = None
        self._latest_latency_ms: int = 0
        self._latency_samples: deque[int] = deque(maxlen=100)
        self._msg_count_current: int = 0
        self._window_task: asyncio.Task[None] | None = None

        # Paper portfolio (PAPER ONLY — no live execution path exists).
        # Money truth lives in TreasuryAgent; positions in PaperTraderAgent.
        self._initial_capital: Decimal = self._read_initial_capital()
        self._peak_equity: Decimal = self._initial_capital
        self._treasury: TreasuryAgent | None = None
        self._trader: PaperTraderAgent | None = None
        self._ceo: CeoAgent | None = None
        self._state_store: StateStore | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._coach_task: asyncio.Task[None] | None = None
        self._news_task: asyncio.Task[None] | None = None
        self._memory_task: asyncio.Task[None] | None = None
        self._news_source: object | None = None  # NewsRssFeed (injectable for tests)
        self.last_news: dict[str, object] = {}
        self.restart_counts: dict[str, int] = {}
        self.crashed_agents: dict[str, str] = {}
        self._learners: dict[str, Learner] = {}
        # Circuit breaker — shared between ExecutionAgent and paper trader close
        self._circuit_breaker: CircuitBreaker | None = None
        # Operator control plane (live, dashboard-driven)
        self._trade_params: object | None = None  # TradeParams (mutated live)
        self._control_audit: list[dict[str, object]] = []
        # Strong refs to in-flight alert tasks so the GC can't kill a critical
        # alert (e.g. "real close failed") mid-send.
        self._alert_tasks: set[asyncio.Task[bool]] = set()
        self._max_deployable_thb: Decimal = Decimal("0")   # 0 = unlimited
        self._max_single_order_thb: Decimal = Decimal("0")  # 0 = unlimited
        self._notifier: object | None = None  # AlertNotifier (lazy, infra)
        # Live Bitkub account connection (read-only reconciliation). Built only
        # when BITKUB_API_KEY is present; otherwise the system runs exactly as
        # before (paper execution over the live price feed).
        self._rest_gateway: object | None = None
        self._reconciliation: object | None = None
        # Timeline Analyst (win-probability gate source) + daily trade governance
        self._timeline: object | None = None
        self._entry_gate_enabled: bool = bool(getattr(settings, "entry_gate_enabled", True))
        self._max_trades_per_day: int = int(getattr(settings, "max_trades_per_day", 1000))
        self._target_daily_profit_pct: Decimal = self._dec_setting("target_daily_profit_pct", "5")
        self._stop_at_daily_target: bool = bool(getattr(settings, "stop_at_daily_target", False))
        self._trades_day_key: str = ""
        self._entries_baseline: int = 0
        self._gate_block_reasons: dict[str, int] = {}

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

    def _ensure_state_store(self) -> StateStore | None:
        """Build the default SQLite store once (deps may inject their own)."""
        if self._deps is not None:
            return self._deps_state_store()
        if self._state_store is None and bool(getattr(self.settings, "persist_state", True)):
            from pathlib import Path  # noqa: PLC0415

            from infrastructure.state.sqlite_store import SqliteStateStore  # noqa: PLC0415

            db_path = Path(str(getattr(self.settings, "state_db_path", "data/state.db")))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_store = SqliteStateStore(db_path)
        return self._state_store

    def _deps_state_store(self) -> StateStore | None:
        return self._deps.state_store if self._deps is not None else None

    def _dec_setting(self, name: str, default: str) -> Decimal:
        try:
            return Decimal(str(getattr(self.settings, name, default)))
        except InvalidOperation:
            return Decimal(default)

    def _read_initial_capital(self) -> Decimal:
        raw = getattr(self.settings, "initial_capital", "100000")
        try:
            value = Decimal(str(raw))
        except InvalidOperation:
            value = Decimal("100000")
        return value if value > 0 else Decimal("100000")

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
            # Production migration: LIVE DATA ONLY. There is no synthetic price
            # feed in this build. If Bitkub is unreachable the supervisor logs
            # the failure and the dashboard surfaces "DATA UNAVAILABLE".
            if mode != "live":
                raise ValueError(
                    f"only 'live' mode is supported (got {mode!r}); "
                    "simulator/paper/demo modes were removed in the Production Migration"
                )
            feed_mode = str(getattr(self.settings, "price_feed_mode", "rest")).lower()
            if feed_mode == "ws":
                from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway  # noqa: PLC0415

                feed = BitkubWebSocketGateway(ws_url)
                self.logger.info("runtime.price_feed", mode="ws", url=ws_url)
            else:
                from infrastructure.gateway.bitkub_rest_ticker import (  # noqa: PLC0415
                    BitkubRestTickerFeed,
                )

                feed = BitkubRestTickerFeed(
                    base_url=str(getattr(self.settings, "bitkub_rest_url", "https://api.bitkub.com")),
                    symbol="THB_BTC",
                    interval_s=float(getattr(self.settings, "price_poll_interval_s", 3.0)),
                )
                self.logger.info("runtime.price_feed", mode="rest")
        self.feed = feed

        counting_bus = _CountingBusProxy(bus, self)
        self.supervisor = PriceSupervisor(feed, counting_bus, topic, self.logger)
        self.supervisor_task = asyncio.create_task(self.supervisor.run())
        self._window_task = asyncio.create_task(self._tick_window())

        self.agents = self._make_agents()
        # Restore operator control settings (risk params, caps) from disk.
        await self.load_controls()
        # Restore every agent's MEMORY (mistakes + fixes) from the last session
        # so they pick up where they left off tomorrow (ความทรงจำจากของเดิม).
        await self._restore_memories()
        # Open the live Bitkub gateway http client (if connected) BEFORE the
        # reconciliation agent starts polling the real wallet.
        if self._rest_gateway is not None:
            try:
                await self._rest_gateway.__aenter__()  # type: ignore[attr-defined]
                self.logger.info("runtime.bitkub_gateway_connected")
            except Exception:
                self.logger.error("runtime.bitkub_gateway_open_failed", exc_info=True)
        self.agent_tasks = {}
        for name in list(self.agents):
            await self.start_agent(name)
        self._watchdog_task = asyncio.create_task(self._watchdog())
        self._coach_task = asyncio.create_task(self._coach_loop())
        # Gradually persist memory to the user's machine while running so a hard
        # crash still keeps most of what the agents learned (ทยอย ๆ เซฟ).
        self._memory_task = asyncio.create_task(self._memory_loop())
        if bool(getattr(self.settings, "news_enabled", True)):
            self._news_task = asyncio.create_task(self._news_loop())

    async def stop(self) -> None:
        """Stop all agents, supervisor, and background tasks."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
        if self._coach_task and not self._coach_task.done():
            self._coach_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._coach_task
        if self._news_task and not self._news_task.done():
            self._news_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._news_task
        if self._memory_task and not self._memory_task.done():
            self._memory_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._memory_task
        # Final memory flush on shutdown / closing the app (กดกากบาทออก) so every
        # agent remembers tomorrow what it got wrong and what it changed.
        await self._persist_memories()
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

        # Close the live Bitkub gateway http client (if it was opened).
        if self._rest_gateway is not None:
            with contextlib.suppress(Exception):
                await self._rest_gateway.__aexit__(None, None, None)  # type: ignore[attr-defined]
            self._rest_gateway = None

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
        """Emergency stop: flatten paper position, then cancel everything."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
        if self._trader is not None:
            try:
                await self._trader.flatten()
            except Exception:
                self.logger.error("runtime.emergency_flatten_error", exc_info=True)
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
        clamped = max(0, latency_ms)
        self._latest_latency_ms = clamped
        self._latency_samples.append(clamped)

    async def _tick_window(self) -> None:
        while True:
            try:
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            self.msg_count_window.append(self._msg_count_current)
            self._msg_count_current = 0

    async def _watchdog(self) -> None:
        """Auto-restart crashed agents; record crash reasons (H5: agent truth)."""
        interval = float(getattr(self.settings, "watchdog_interval_s", 2.0))
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            for name in list(self.agent_tasks):
                task = self.agent_tasks.get(name)
                agent = self.agents.get(name)
                if task is None or agent is None:
                    continue
                if not task.done() or not agent.running:
                    continue  # alive, or intentionally stopped
                reason = "crashed"
                try:
                    exc = task.exception()
                    if exc is not None:
                        reason = f"{type(exc).__name__}: {exc}"
                except asyncio.CancelledError:
                    continue  # cancelled tasks are not crashes
                self.crashed_agents[name] = reason
                self.restart_counts[name] = self.restart_counts.get(name, 0) + 1
                self.logger.error(
                    "watchdog.agent_crashed_restarting", agent=name, reason=reason
                )
                self._learner_for(name, agent).log(
                    f"พัง ({reason}) → ระบบรีสตาร์ทอัตโนมัติ (self-healing)", "event"
                )
                self.agent_tasks.pop(name, None)
                agent.running = False
                await self.start_agent(name)

    async def _coach_loop(self) -> None:
        """Peer-coaching: the best strategy agent of the round coaches the
        laggards (they tighten their own params). Real, logged, no fakery."""
        while True:
            try:
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                break
            strat: list[tuple[str, AgentLike, float]] = []
            for name, agent in self.agents.items():
                learner = self._learner_for(name, agent)
                if learner.kind != "strategy" or learner.today_resolved < 8:
                    continue
                hr = learner.today_hit_rate() or 0.0
                strat.append((name, agent, hr))
            if len(strat) < 2:
                continue
            strat.sort(key=lambda t: t[2], reverse=True)
            best_name, _, best_hr = strat[0]
            self._learner_for(best_name, self.agents[best_name]).log(
                f"เป็นโค้ชรอบนี้ (แม่นวันนี้ {best_hr * 100:.0f}%)", "coach"
            )
            for _name, agent, hr in strat[1:]:
                if hr < 0.45 and hasattr(agent, "coach_tighten"):
                    agent.coach_tighten(best_name)

    def _ensure_notifier(self) -> object | None:
        if self._notifier is None:
            from infrastructure.alerts.notifier import AlertNotifier  # noqa: PLC0415

            self._notifier = AlertNotifier(
                telegram_bot_token=str(getattr(self.settings, "telegram_bot_token", "")),
                telegram_chat_id=str(getattr(self.settings, "telegram_chat_id", "")),
                webhook_url=str(getattr(self.settings, "alert_webhook_url", "")),
                logger=self.logger,
            )
        return self._notifier

    async def send_alert(self, message: str, level: str = "info") -> bool:
        """Send an operator alert (Telegram/webhook). Never raises."""
        notifier = self._ensure_notifier()
        if notifier is None:
            return False
        return await notifier.send(message, level)  # type: ignore[attr-defined,no-any-return]

    def _schedule_alert(self, message: str, level: str = "warning") -> None:
        """Fire an alert without blocking, if an event loop is running."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.send_alert(message, level))
        self._alert_tasks.add(task)
        task.add_done_callback(self._alert_tasks.discard)

    async def _news_loop(self) -> None:
        """Poll RSS headlines, score them (pure domain), publish to news.raw.v1.

        The News Intelligence agent consumes news.raw.v1 and republishes a
        sentiment signal. Failures never crash the loop.
        """
        from domain.analytics.sentiment import classify_sentiment, score_headlines  # noqa: PLC0415

        interval = float(getattr(self.settings, "news_poll_interval_s", 120.0))
        if self._news_source is None:
            from infrastructure.gateway.news_rss import NewsRssFeed  # noqa: PLC0415

            self._news_source = NewsRssFeed()
        bus = self._ensure_bus()
        while True:
            try:
                headlines: list[str] = await self._news_source.fetch_headlines()  # type: ignore[attr-defined]
                if headlines:
                    score = score_headlines(headlines)
                    label = str(classify_sentiment(score))
                    payload = orjson.dumps(
                        {
                            "score": str(score),
                            "label": label,
                            "headline_count": len(headlines),
                            "sample": headlines[:5],
                        }
                    )
                    await bus.publish(_TOPIC_NEWS_RAW, b"news", payload)
                    self.last_news = {
                        "score": str(score),
                        "label": label,
                        "headline_count": len(headlines),
                        "sample": headlines[:5],
                        "ts_ms": int(time.time() * 1000),
                    }
                    self.logger.info(
                        "news.published", score=str(score), label=label, count=len(headlines)
                    )
                else:
                    self.logger.warning("news.no_headlines")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.warning("news.loop_error", exc_info=True)
            await asyncio.sleep(interval)

    @property
    def ceo(self) -> CeoAgent | None:
        """Return the CEO observer agent, or None before start()."""
        return self._ceo


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
