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
from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
from orchestration.agents.reconciliation_agent import ReconciliationAgent
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.ports.event_bus import EventBus
from orchestration.ports.price_feed import PriceFeed
from orchestration.ports.state_store import StateStore
from orchestration.runtime_agents import _AgentsMixin
from orchestration.runtime_base import (
    _TOPIC_PAPER_EVENTS,
    AgentLike,
    NewsSource,
    Notifier,
    RuntimeDeps,
    SettingsView,
    _RuntimeBase,
)
from orchestration.runtime_io import _IoMixin
from orchestration.runtime_live import _LiveTradingMixin
from orchestration.runtime_memory import _MemoryMixin
from orchestration.runtime_risk import _RiskControlMixin
from orchestration.runtime_status import _StatusMixin
from orchestration.runtime_strategy import _StrategyMixin
from orchestration.supervisors.price_supervisor import PriceSupervisor
from orchestration.supervisors.supervisor import Supervisor


class PipelineRuntime(
    _AgentsMixin,
    _StatusMixin,
    _RiskControlMixin,
    _LiveTradingMixin,
    _MemoryMixin,
    _StrategyMixin,
    _IoMixin,
    _RuntimeBase,
):
    """Orchestrates feed, supervisor, and agents around a single shared bus."""

    def __init__(
        self,
        settings: SettingsView,
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
        # Restart-guard around the price-feed→bus bridge (auto-restart + backoff).
        self._price_guardian: Supervisor | None = None
        self.supervisor_task: asyncio.Task[None] | None = None
        self.agents: dict[str, AgentLike] = {}
        self.agent_tasks: dict[str, asyncio.Task[None]] = {}
        self.start_time_ms: int = 0
        self.msg_count_window: deque[int] = deque(maxlen=60)
        # Bounded buffers powering the minimal dashboard chart + trades table.
        self._price_history: deque[tuple[int, str]] = deque(maxlen=900)
        self._recent_trades: deque[dict[str, object]] = deque(maxlen=200)
        self._trade_rec_task: asyncio.Task[None] | None = None
        self.emergency_stopped: bool = False
        # Per-process control key auto-provisioned for a LOCAL dashboard so the
        # operator never hand-edits .env (network binds still require an explicit
        # key via assert_safe_bind). Injected into the served page each load.
        self._ephemeral_control_key: str = ""
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
        # Trade-recording background task (writes data/trades_*.csv — the owner's
        # ground-truth ledger and the ML win-prob loop's training source).
        self._trade_csv: object | None = None
        self._trade_csv_task: asyncio.Task[None] | None = None
        self._news_source: NewsSource | None = None  # NewsRssFeed (injectable for tests)
        self.last_news: dict[str, object] = {}
        self.restart_counts: dict[str, int] = {}
        self.crashed_agents: dict[str, str] = {}
        self._learners: dict[str, Learner] = {}
        # Circuit breaker — shared between ExecutionAgent and paper trader close
        self._circuit_breaker: CircuitBreaker | None = None
        # Operator control plane (live, dashboard-driven)
        self._trade_params: TradeParams | None = None  # mutated live
        self._control_audit: list[dict[str, object]] = []
        # Strong refs to in-flight alert tasks so the GC can't kill a critical
        # alert (e.g. "real close failed") mid-send.
        self._alert_tasks: set[asyncio.Task[bool]] = set()
        self._max_deployable_thb: Decimal = Decimal("0")   # 0 = unlimited
        self._max_single_order_thb: Decimal = Decimal("0")  # 0 = unlimited
        self._notifier: Notifier | None = None  # AlertNotifier (lazy, infra)
        # Live Bitkub account connection (read-only reconciliation). Built only
        # when BITKUB_API_KEY is present; otherwise the system runs exactly as
        # before (paper execution over the live price feed).
        self._rest_gateway: object | None = None
        self._reconciliation: ReconciliationAgent | None = None
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
        # Wrap the bridge in the restart Supervisor so a crash auto-restarts with
        # backoff instead of silently killing the price stream (the watchdog only
        # watches agents, not this task). The feed also retries internally; this
        # is the outer safety net. NOTE: the task is created LAST (below), after
        # every agent has subscribed, to avoid a publish-before-subscribe race.
        self._price_guardian = Supervisor("price_feed", self.supervisor.run, self.logger)
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
                # _rest_gateway is polymorphic (signed gateway | None | connection
                # marker); the async-context surface only exists on the real gateway.
                await self._rest_gateway.__aenter__()  # type: ignore[attr-defined]
                self.logger.info("runtime.bitkub_gateway_connected")
            except Exception:
                self.logger.error("runtime.bitkub_gateway_open_failed", exc_info=True)
        self.agent_tasks = {}
        for name in list(self.agents):
            await self.start_agent(name)
        # Record paper FILL/CLOSE events for the dashboard (subscribe BEFORE the
        # price feed starts so no trade is missed).
        self._trade_rec_task = asyncio.create_task(self._recent_trades_loop())
        # Producers start LAST: every consumer above has already run its
        # synchronous bus.subscribe() before the first price tick can be
        # published, closing the publish-before-subscribe startup race (the
        # in-memory bus has no replay, so a tick sent before a subscribe is lost).
        # Warm-start (production live path only): seed agents + chart with recent
        # REAL prices NOW that every consumer has subscribed and BEFORE the live
        # feed starts, so history precedes live. Graceful — never blocks startup
        # on a slow/unreachable exchange beyond the short fetch timeout.
        if self._deps is None:
            await self._backfill_history(topic)
        self.supervisor_task = asyncio.create_task(self._price_guardian.run())
        self._watchdog_task = asyncio.create_task(self._watchdog())
        self._coach_task = asyncio.create_task(self._coach_loop())
        # Gradually persist memory to the user's machine while running so a hard
        # crash still keeps most of what the agents learned (ทยอย ๆ เซฟ).
        self._memory_task = asyncio.create_task(self._memory_loop())
        if bool(getattr(self.settings, "news_enabled", True)):
            self._news_task = asyncio.create_task(self._news_loop())
        # Record every closed paper trade to data/trades_*.csv (provenance ledger
        # + ML training source). Gated on persist_state so ephemeral test runtimes
        # don't litter the working tree; on by default in production.
        if bool(getattr(self.settings, "persist_state", True)):
            from pathlib import Path  # noqa: PLC0415

            from infrastructure.logging.trade_csv import TradeCsvLogger  # noqa: PLC0415

            data_dir = Path(str(getattr(self.settings, "state_db_path", "data/state.db"))).parent
            recorder = TradeCsvLogger(self._ensure_bus(), _TOPIC_PAPER_EVENTS, log_dir=data_dir)
            self._trade_csv = recorder
            self._trade_csv_task = asyncio.create_task(recorder.start())

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
        if self._trade_rec_task and not self._trade_rec_task.done():
            self._trade_rec_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._trade_rec_task
        if self._trade_csv is not None and hasattr(self._trade_csv, "stop"):
            await self._trade_csv.stop()
        if self._trade_csv_task and not self._trade_csv_task.done():
            self._trade_csv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._trade_csv_task
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

    def price_history(self) -> list[dict[str, object]]:
        """Recent (ts_ms, price) ticks for the dashboard chart backfill."""
        return [{"ts_ms": ts, "price": px} for ts, px in list(self._price_history)]

    async def _backfill_history(self, topic: str, symbol: str = "THB_BTC") -> None:
        """Warm-start: seed the agents' price buffers + the dashboard chart with
        recent REAL Bitkub prices so they compute immediately instead of starting
        cold (no history → long warm-up before the win-prob gate trusts anything).

        Never raises — a blocked or slow exchange just leaves the previous
        cold-start behaviour (the published batch carries historical timestamps,
        so it precedes the live ticks the agents receive next)."""
        try:
            from domain.trading.market_data import (  # noqa: PLC0415
                NormalizationFailure,
                normalize_bitkub_ticker,
            )
            from infrastructure.gateway.bitkub_rest_ticker import (  # noqa: PLC0415
                fetch_recent_prices,
            )

            base = str(getattr(self.settings, "bitkub_rest_url", "https://api.bitkub.com"))
            prices = await fetch_recent_prices(symbol=symbol, base_url=base, limit=300)
            if not prices:
                self.logger.info("runtime.history_backfill_empty")
                return
            bus = self._ensure_bus()
            seeded = 0
            for ts_ms, price in prices:
                result = normalize_bitkub_ticker({"last": str(price), "symbol": symbol}, now_ms=ts_ms)
                if isinstance(result, NormalizationFailure):
                    continue
                await bus.publish(
                    topic, result.symbol.encode(), orjson.dumps(result.model_dump(mode="json"))
                )
                self._price_history.append((ts_ms, str(price)))
                seeded += 1
            self.logger.info("runtime.history_backfilled", count=seeded)
        except Exception:
            self.logger.warning("runtime.history_backfill_failed", exc_info=True)

    def recent_trades(self) -> list[dict[str, object]]:
        """Recent paper FILL/CLOSE events (oldest first) for the trades table."""
        return list(self._recent_trades)

    async def _recent_trades_loop(self) -> None:
        """Mirror paper FILL/CLOSE events into a bounded buffer for the dashboard."""
        bus = self._ensure_bus()
        queue = bus.subscribe(_TOPIC_PAPER_EVENTS)
        try:
            while True:
                raw = await queue.get()
                try:
                    ev = orjson.loads(raw)
                    # Guard non-dict payloads: a JSON array/scalar would raise on
                    # .get and kill this (un-watched) loop, freezing the trades
                    # feed permanently. Never let one bad frame stop the loop.
                    if isinstance(ev, dict) and ev.get("type") in ("FILL", "CLOSE"):
                        self._recent_trades.append(ev)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger.warning("runtime.recent_trades_frame_error", exc_info=True)
        except asyncio.CancelledError:
            raise
        finally:
            bus.unsubscribe(_TOPIC_PAPER_EVENTS, queue)

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
            # Phase 5: keep today's daily_summary.csv row fresh (never crashes).
            with contextlib.suppress(Exception):
                self.write_daily_summary()
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


    def control_key(self) -> str:
        """Effective dashboard control key used by the strict auth gate + page
        injection.

        If DASHBOARD_API_KEY is configured, use it. Otherwise, when bound to a
        LOOPBACK host (single-user local dashboard), mint a per-process key once
        and reuse it — so the operator's own machine works with zero key handling
        ('ใส่รอบเดียวจบ'). It is injected into the served page each load, so it is
        never typed. For a NON-loopback bind we return '' (no auto-key): the
        startup bind-guard already forces an explicit credential there, so the
        network control plane is never opened by this convenience.
        """
        raw = getattr(self.settings, "dashboard_api_key", None)
        if raw is None:
            cur = ""
        elif hasattr(raw, "get_secret_value"):
            cur = str(raw.get_secret_value())
        else:
            cur = str(raw)
        if cur:
            return cur
        host = str(getattr(self.settings, "web_host", "127.0.0.1"))
        if host not in ("127.0.0.1", "::1", "localhost"):
            return ""
        if not self._ephemeral_control_key:
            import secrets as _secrets  # noqa: PLC0415

            self._ephemeral_control_key = _secrets.token_urlsafe(24)
        return self._ephemeral_control_key

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
                self._runtime._price_history.append((ts_ms_val, str(price)))
        except (asyncio.CancelledError, TimeoutError):
            raise
        except (orjson.JSONDecodeError, InvalidOperation, KeyError, ValueError, TypeError):
            self.parse_failures += 1
            self._runtime.logger.warning("counting_bus.parse_error", exc_info=True)
        except Exception:
            self.parse_failures += 1
            self._runtime.logger.error("counting_bus.unexpected_error", exc_info=True)
