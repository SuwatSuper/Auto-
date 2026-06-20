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
    _TOPIC_ANALYSIS,
    _TOPIC_PAPER_EVENTS,
    _TOPIC_PROBABILITY,
    _TOPIC_RESEARCH,
    _TOPIC_SENTIMENT,
    _TOPIC_SIM_RESULTS,
    _TOPIC_TIMELINE,
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


def _obj_int(value: object, default: int) -> int:
    """Best-effort int from an ``object`` bus field (never raises)."""
    try:
        return int(str(value)) if value is not None else default
    except (TypeError, ValueError):
        return default


def _obj_float(value: object, default: float) -> float:
    """Best-effort float from an ``object`` bus field (never raises)."""
    try:
        return float(str(value)) if value is not None else default
    except (TypeError, ValueError):
        return default


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
        # Wall-clock ms of the last price published to the bus. Powers the
        # staleness watchdog: a feed that is alive but no longer producing
        # (wedged httpx pool, silent half-open WS, API shape change) leaves
        # this frozen, so the watchdog can re-dial it instead of letting the
        # displayed price hang forever. 0 = no price seen since feed (re)start.
        self._last_price_wall_ms: int = 0
        self._price_feed_stale_restarts: int = 0
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
        # H6: per-agent restart backoff clock + the set of agents we've given up
        # on (exhausted the restart cap) so the watchdog can't storm-restart.
        self._agent_next_retry: dict[str, float] = {}
        self._agents_given_up: set[str] = set()
        self._learners: dict[str, Learner] = {}
        # Circuit breaker — shared between ExecutionAgent and paper trader close
        self._circuit_breaker: CircuitBreaker | None = None
        # Serializes operator manual orders so two concurrent clicks can't place
        # two real bids (M3). Created lazily inside the running loop.
        self._manual_order_lock: asyncio.Lock | None = None
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
        # ── Task 1: bus-fed confluence cache ────────────────────────────────
        # The entry gate reads ONLY from this dict — never from agent instance
        # attributes. A background consumer (``_confluence_loop``) subscribes to
        # every department's output topic and keeps these fields fresh. Defaults
        # are NEUTRAL so the gate behaves until real reads arrive over the bus.
        self._confluence: dict[str, object] = {
            "p_win": "0", "p_win_samples": 0, "regime": "RANGE",
            "past_win_rate": None, "recent_win_rate": None, "analysis": {},
            "sentiment": "0",          # news_intelligence  (sentiment.v1)
            "prob_bull": "0.5",        # probability_lab    (probability.v1)
            "sim_win_rate": "-1",      # execution_agent    (sim.results.v1)
            "sim_total_trades": 0,
            "price_pctl": "-1",        # research_dept      (research.v1)
            "pct_from_mean": "0",
            "swarm_bias": 0.0,         # division chiefs    (analysis.v1)
        }
        self._division_bias: dict[str, float] = {}
        self._confluence_task: asyncio.Task[None] | None = None
        # ── Task 2: dynamic weighting (paper.events → source win-rate) ──────
        from domain.analytics.source_weights import SourcePerformance  # noqa: PLC0415
        self._source_perf = SourcePerformance()
        self._weighting_task: asyncio.Task[None] | None = None
        # ── Task 3: shared regime-aware meta-learner for the 150-agent grid ──
        from domain.analytics.swarm_meta import SwarmMetaLearner  # noqa: PLC0415
        self._swarm_meta = SwarmMetaLearner()

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
        # Restore a TRIPPED circuit breaker from the last session BEFORE controls
        # (so the operator's live threshold still wins) — a halt must survive a
        # restart; only the operator may reset it (C1).
        await self._restore_breaker()
        # Restore operator control settings (risk params, caps) from disk.
        await self.load_controls()
        # H2: a persisted live flag must NOT silently re-arm real-money trading
        # on restart — re-validate the arm-time invariants (cap, backstops,
        # breaker, kill switch) now that controls are loaded; drop to paper if
        # any fail so the operator must consciously re-arm.
        self._revalidate_persisted_execution_mode()
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
        # Task 1 + 2 consumers: subscribe BEFORE producers so no message is lost
        # (the in-memory bus has no replay). The confluence loop feeds the entry
        # gate; the weighting loop routes paper.events back into vote weights.
        self._confluence_task = asyncio.create_task(self._confluence_loop())
        self._weighting_task = asyncio.create_task(self._weighting_loop())
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
        # Baseline the staleness clock to feed-start so a feed that never
        # produces is also re-dialed (not just one that produced then stopped).
        self._last_price_wall_ms = int(time.time() * 1000)
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
        for task in (self._confluence_task, self._weighting_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
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
        # Emergency stop must be a CLEAN halt — cancel the background loops too
        # (coach/news/memory/trade-rec/window/csv), not just agents + watchdog,
        # so nothing keeps running side-effects after the panic button.
        await self._cancel_background_loops()
        if self.supervisor_task and not self.supervisor_task.done():
            self.supervisor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(self.supervisor_task, timeout=2.0)
        self.emergency_stopped = True

    async def _cancel_background_loops(self) -> None:
        """Cancel the periodic background-loop tasks (coach / news / memory /
        trade-recorder / tick-window / trade-csv). Shared by emergency_stop() so a
        panic halt leaves nothing running (stop() cancels them explicitly too)."""
        for task in (
            self._coach_task, self._news_task, self._memory_task,
            self._trade_rec_task, self._window_task,
            self._confluence_task, self._weighting_task,
        ):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        if self._trade_csv is not None and hasattr(self._trade_csv, "stop"):
            with contextlib.suppress(Exception):
                await self._trade_csv.stop()
        if self._trade_csv_task and not self._trade_csv_task.done():
            self._trade_csv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._trade_csv_task

    async def emergency_reset(self) -> None:
        """B2 fix: clear emergency_stopped without auto-starting (distinct from start)."""
        self.emergency_stopped = False

    def record_message(self, price: Decimal, latency_ms: int) -> None:
        """Record a processed price message for metrics."""
        self._latest_price = price
        self._last_price_wall_ms = int(time.time() * 1000)
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

    # ── Task 1: bus-fed confluence consumer ──────────────────────────
    _CONFLUENCE_TOPICS = (
        _TOPIC_TIMELINE,       # Group B: timeline_analyst (p_win, regime)
        _TOPIC_SIM_RESULTS,    # Group B: execution_agent (Sim) win_rate
        _TOPIC_ANALYSIS,       # Group B: division chiefs' consensus bias
        _TOPIC_PROBABILITY,    # Group A: probability_lab (prob_bull)
        _TOPIC_SENTIMENT,      # Group A: news_intelligence (sentiment)
        _TOPIC_RESEARCH,       # Group A: research_dept (price percentile)
    )

    def _apply_confluence_message(self, topic: str, data: dict[str, object]) -> None:
        """Fold one department message into the confluence cache. Pure dict
        updates — this is the ONLY place agent outputs enter the entry gate, so
        there is no hidden attribute coupling anywhere."""
        c = self._confluence
        if topic == _TOPIC_TIMELINE:
            c["p_win"] = str(data.get("p_win", c["p_win"]))
            c["p_win_samples"] = _obj_int(data.get("p_win_samples"), 0)
            c["regime"] = str(data.get("regime", c["regime"]))
            c["past_win_rate"] = data.get("past_win_rate", c["past_win_rate"])
            c["recent_win_rate"] = data.get("recent_win_rate", c["recent_win_rate"])
            if isinstance(data.get("analysis"), dict):
                c["analysis"] = data["analysis"]
        elif topic == _TOPIC_SIM_RESULTS:
            c["sim_win_rate"] = str(data.get("win_rate", c["sim_win_rate"]))
            c["sim_total_trades"] = _obj_int(data.get("total_trades"), 0)
        elif topic == _TOPIC_ANALYSIS:
            div = str(data.get("division", ""))
            self._division_bias[div] = _obj_float(data.get("bias"), 0.0)
            if self._division_bias:
                c["swarm_bias"] = sum(self._division_bias.values()) / len(self._division_bias)
        elif topic == _TOPIC_PROBABILITY:
            c["prob_bull"] = str(data.get("prob_bull", c["prob_bull"]))
        elif topic == _TOPIC_SENTIMENT:
            c["sentiment"] = str(data.get("sentiment_score", c["sentiment"]))
        elif topic == _TOPIC_RESEARCH:
            c["price_pctl"] = str(data.get("price_pctl", c["price_pctl"]))
            c["pct_from_mean"] = str(data.get("pct_from_mean", c["pct_from_mean"]))

    async def _confluence_loop(self) -> None:
        """Subscribe to every department output topic and keep the confluence
        cache fresh. Replaces the old direct reads of agent attributes."""
        bus = self._ensure_bus()
        queues = {t: bus.subscribe(t) for t in self._CONFLUENCE_TOPICS}
        # One in-flight get() per topic; refresh whichever completes.
        getters: dict[str, asyncio.Task[bytes]] = {}
        try:
            while True:
                for topic, q in queues.items():
                    if topic not in getters or getters[topic].done():
                        getters[topic] = asyncio.create_task(q.get())
                done, _ = await asyncio.wait(
                    set(getters.values()), timeout=0.5, return_when=asyncio.FIRST_COMPLETED
                )
                for topic, task in list(getters.items()):
                    if task in done:
                        try:
                            raw = task.result()
                            data = orjson.loads(raw)
                            if isinstance(data, dict):
                                self._apply_confluence_message(topic, data)
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            self.logger.warning("runtime.confluence_frame_error", exc_info=True)
                        del getters[topic]
        except asyncio.CancelledError:
            raise
        finally:
            for t in getters.values():
                if not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        await t
            for topic, q in queues.items():
                bus.unsubscribe(topic, q)

    # ── Task 2: dynamic-weighting feedback loop ───────────────────────
    def _record_trade_outcome(self, ev: dict[str, object]) -> None:
        """Attribute a CLOSE event's Win/Loss to the sources that voted it open,
        then push the refreshed vote weights into the Supreme commander."""
        if ev.get("type") != "CLOSE":
            return
        raw_voters = ev.get("voters")
        voters = [str(v) for v in raw_voters] if isinstance(raw_voters, list) else []
        if not voters:
            return
        try:
            pnl_net = Decimal(str(ev.get("pnl_net", ev.get("pnl", "0"))))
        except (InvalidOperation, ValueError, TypeError):
            return
        self._source_perf.record_many(voters, won=pnl_net > 0)
        supreme = self.agents.get("supreme_commander")
        if supreme is not None and hasattr(supreme, "update_weights"):
            supreme.update_weights(self._source_perf.weights())

    async def _weighting_loop(self) -> None:
        """Route paper.events Win/Loss/PnL back into the per-source vote weights
        (Task 2). A dedicated subscriber, decoupled from the trades-table mirror."""
        bus = self._ensure_bus()
        queue = bus.subscribe(_TOPIC_PAPER_EVENTS)
        try:
            while True:
                raw = await queue.get()
                try:
                    ev = orjson.loads(raw)
                    if isinstance(ev, dict):
                        self._record_trade_outcome(ev)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.logger.warning("runtime.weighting_frame_error", exc_info=True)
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
            try:
                for name in list(self.agent_tasks):
                    task = self.agent_tasks.get(name)
                    agent = self.agents.get(name)
                    if task is None or agent is None:
                        continue
                    if not task.done() or not agent.running:
                        continue  # alive, or intentionally stopped
                    # H6: cap restarts + exponential backoff so a deterministically
                    # crashing agent can't storm the loop (log flood / CPU churn /
                    # a vehicle to silently re-arm live across reboots).
                    count = self.restart_counts.get(name, 0)
                    max_restarts = int(getattr(self.settings, "max_agent_restarts", 10))
                    if 0 < max_restarts <= count:
                        agent.running = False  # give up; stop re-evaluating it
                        if name not in self._agents_given_up:
                            self._agents_given_up.add(name)
                            self.crashed_agents[name] = f"GAVE UP after {count} restarts"
                            self.logger.critical(
                                "watchdog.agent_restart_exhausted",
                                agent=name, restarts=count,
                            )
                            self._schedule_alert(
                                f"🛑 Agent '{name}' พังซ้ำ {count} ครั้ง — หยุดรีสตาร์ทอัตโนมัติ "
                                "ต้องตรวจสอบเอง", "critical",
                            )
                        continue
                    now_mono = time.monotonic()
                    if now_mono < self._agent_next_retry.get(name, 0.0):
                        continue  # still inside the backoff window
                    base = float(getattr(self.settings, "agent_restart_backoff_s", 2.0))
                    self._agent_next_retry[name] = now_mono + min(base * (2 ** count), 60.0)
                    reason = "crashed"
                    try:
                        exc = task.exception()
                        if exc is not None:
                            reason = f"{type(exc).__name__}: {exc}"
                    except asyncio.CancelledError:
                        continue  # cancelled tasks are not crashes
                    self.crashed_agents[name] = reason
                    self.restart_counts[name] = count + 1
                    self.logger.error(
                        "watchdog.agent_crashed_restarting", agent=name, reason=reason
                    )
                    self._learner_for(name, agent).log(
                        f"พัง ({reason}) → ระบบรีสตาร์ทอัตโนมัติ (self-healing)", "event"
                    )
                    self.agent_tasks.pop(name, None)
                    agent.running = False
                    await self.start_agent(name)
                # The price-feed bridge is the single most critical task — if it
                # dies (e.g. the restart Supervisor exhausts its budget) the whole
                # pipeline goes silent. Cover it here too: recreate it if it died
                # while the system is still meant to be running.
                sup = self.supervisor_task
                if (
                    sup is not None and sup.done() and not sup.cancelled()
                    and not self.emergency_stopped and self._price_guardian is not None
                ):
                    why = "completed"
                    with contextlib.suppress(Exception):
                        e = sup.exception()
                        why = f"{type(e).__name__}: {e}" if e is not None else "completed"
                    self.logger.error("watchdog.price_feed_restarting", reason=why)
                    self._price_guardian.reset()  # fresh budget (symmetry w/ stale path)
                    self.supervisor_task = asyncio.create_task(self._price_guardian.run())
                    # Rebase the staleness clock too, so the next tick doesn't
                    # immediately re-dial the feed we just recreated before it
                    # has had a chance to produce its first price.
                    self._last_price_wall_ms = int(time.time() * 1000)
                else:
                    await self._restart_feed_if_stale()
            except Exception:
                # A bug in the watchdog body must never kill self-healing.
                self.logger.error("watchdog.loop_error", exc_info=True)

    async def _restart_feed_if_stale(self) -> None:
        """Re-dial a feed that is alive but no longer producing prices.

        The existing ``sup.done()`` branch only catches a feed task that has
        DIED. A feed can also go silent while its task stays alive — a wedged
        httpx connection pool, a half-open WebSocket the keepalive missed, or an
        API response shape change that yields no parseable price. The displayed
        BTC price then hangs with no recovery. Here we detect that no price has
        reached the bus for ``price_stale_restart_s`` and force a fresh
        ``feed.run()`` (new HTTP client / new socket)."""
        sup = self.supervisor_task
        guardian = self._price_guardian
        if (
            sup is None or guardian is None or sup.done()
            or self.emergency_stopped or self._last_price_wall_ms == 0
        ):
            return
        threshold_ms = int(float(getattr(self.settings, "price_stale_restart_s", 30.0)) * 1000)
        age_ms = int(time.time() * 1000) - self._last_price_wall_ms
        if age_ms < threshold_ms:
            return
        self.logger.error("watchdog.price_feed_stale_restarting", stale_ms=age_ms)
        sup.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sup
        guardian.reset()  # fresh restart budget for the re-dialed feed
        self.supervisor_task = asyncio.create_task(guardian.run())
        # Reset the clock so the new feed gets a full grace window to produce
        # before another re-dial (avoids a tight restart loop).
        self._last_price_wall_ms = int(time.time() * 1000)
        self._price_feed_stale_restarts += 1

    async def _coach_loop(self) -> None:
        """Peer-coaching: the best strategy agent of the round coaches the
        laggards (they tighten their own params). Real, logged, no fakery."""
        while True:
            try:
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                break
            try:
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
            except Exception:
                # One bad coaching round must not kill the loop (self-healing).
                self.logger.warning("coach.loop_error", exc_info=True)


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
        # A network bind never auto-opens the control plane on its own. The one
        # exception: a DASHBOARD_PASSWORD is set — then mint a per-process key so
        # /api/login can return a usable token AND both auth gates have a real
        # secret to compare against. (Without this, a password-only LAN bind
        # bricked the strict endpoints and left the non-strict ones open.) The key
        # is NOT injected into the page for this case (see page_control_key), so a
        # remote client must log in to obtain it.
        if host not in ("127.0.0.1", "::1", "localhost") and not self._password_value():
            return ""
        if not self._ephemeral_control_key:
            import secrets as _secrets  # noqa: PLC0415

            self._ephemeral_control_key = _secrets.token_urlsafe(24)
        return self._ephemeral_control_key

    def _password_value(self) -> str:
        raw = getattr(self.settings, "dashboard_password", None)
        if raw is None:
            return ""
        return str(raw.get_secret_value()) if hasattr(raw, "get_secret_value") else str(raw)

    def page_control_key(self) -> str:
        """Control key to INJECT into the served dashboard page.

        Equals ``control_key()`` for a loopback bind or an explicit
        DASHBOARD_API_KEY (the operator's own choice), but EMPTY for a
        password-protected NETWORK bind — there the key must be obtained via
        ``POST /api/login``, never pre-exposed in the page to anyone who can
        reach it."""
        raw = getattr(self.settings, "dashboard_api_key", None)
        if raw is None:
            api_key = ""
        elif hasattr(raw, "get_secret_value"):
            api_key = str(raw.get_secret_value())
        else:
            api_key = str(raw)
        host = str(getattr(self.settings, "web_host", "127.0.0.1"))
        is_loopback = host in ("127.0.0.1", "::1", "localhost")
        return self.control_key() if (api_key or is_loopback) else ""

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
