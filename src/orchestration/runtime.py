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
from typing import TYPE_CHECKING, Protocol

import orjson
import structlog

from domain.portfolio.treasury import TreasuryLimits
from domain.risk.circuit_breaker import CircuitBreaker
from orchestration.agents.ceo_agent import CeoAgent
from orchestration.agents.entry_exit import EntryExitAgent
from orchestration.agents.historical_research import HistoricalResearchAgent
from orchestration.agents.learning import Learner, blended_score, reliability_score
from orchestration.agents.news_sentiment import NewsSentimentAgent
from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
from orchestration.agents.probability import ProbabilityAgent
from orchestration.agents.risk_agent import RiskAgent
from orchestration.agents.simulation import SimulationAgent
from orchestration.agents.supreme import SupremeAgent
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.ports.clock import Clock
from orchestration.ports.event_bus import EventBus
from orchestration.ports.event_store import EventStore
from orchestration.ports.price_feed import PriceFeed
from orchestration.ports.state_store import StateStore
from orchestration.supervisors.price_supervisor import PriceSupervisor

if TYPE_CHECKING:
    from orchestration.control import RiskSettings


class AgentLike(Protocol):
    """Minimal contract every runtime agent satisfies (Layer-2 port)."""

    running: bool
    msg_count: int
    last_beat_ms: int

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


# Department topics (Layer-2 routing table). Names are 1:1 with the
# Kingdom Prime dashboard chibis — no decorative/ghost agents (H5).
_TOPIC_SIGNALS = "signals.v1"
_TOPIC_DECISIONS = "decisions.v1"
_TOPIC_DECISIONS_APPROVED = "decisions.approved.v1"
_TOPIC_RISK = "risk.v1"
_TOPIC_SENTIMENT = "sentiment.v1"
_TOPIC_NEWS_RAW = "news.raw.v1"
_TOPIC_PROBABILITY = "probability.v1"
_TOPIC_RESEARCH = "research.v1"
_TOPIC_SIM_RESULTS = "sim.results.v1"
_TOPIC_TREASURY = "treasury.v1"
_TOPIC_PAPER_EVENTS = "paper.events.v1"
_TOPIC_TIMELINE = "timeline.v1"
# Analyst swarm: divisions publish their consensus bias here so the rest of the
# swarm (and the entry hunters) can coordinate for maximum performance.
_TOPIC_ANALYSIS = "analysis.v1"


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

    def _make_agents(self) -> dict[str, AgentLike]:
        """Build the 7-department company + CEO observer. Every entry maps 1:1
        to a real running task and to one dashboard chibi (H5 — agent truth)."""
        from orchestration.agents.execution_agent import ExecutionAgent  # noqa: PLC0415

        bus = self._ensure_bus()
        prices: str = getattr(self.settings, "prices_topic", "prices.thb_btc.v1")
        log = self.logger

        # Build risk gate components
        max_losses = int(getattr(self.settings, "max_consecutive_losses", 5))
        self._circuit_breaker = CircuitBreaker(max_consecutive_losses=max_losses)
        from infrastructure.gateway.rate_limiter import TokenBucket  # noqa: PLC0415
        token_bucket = TokenBucket(capacity=10, refill_per_sec=2.0)

        agents: dict[str, AgentLike] = {
            "market_analyst": EntryExitAgent(bus, prices, _TOPIC_SIGNALS, log),
            "news_intelligence": NewsSentimentAgent(bus, _TOPIC_NEWS_RAW, _TOPIC_SENTIMENT, log),
            "risk_management": RiskAgent(
                bus, _TOPIC_DECISIONS, _TOPIC_RISK, log,
                equity_fn=self._risk_equity_state,
            ),
            "probability_lab": ProbabilityAgent(bus, prices, _TOPIC_PROBABILITY, log),
            "research_dept": HistoricalResearchAgent(bus, prices, _TOPIC_RESEARCH, log),
            "execution_agent": SimulationAgent(bus, prices, _TOPIC_SIM_RESULTS, log),
            "supreme_commander": SupremeAgent(
                bus, _TOPIC_SIGNALS, _TOPIC_DECISIONS, log,
                window_s=float(getattr(self.settings, "supreme_window_s", 8.0)),
                buy_votes=int(getattr(self.settings, "supreme_buy_votes", 1)),
                sell_votes=int(getattr(self.settings, "supreme_sell_votes", 1)),
            ),
            "risk_gate": ExecutionAgent(
                bus=bus,
                raw_decisions_topic=_TOPIC_DECISIONS,
                approved_topic=_TOPIC_DECISIONS_APPROVED,
                settings=self.settings,
                breaker=self._circuit_breaker,
                rate_limiter=token_bucket,
                logger=log,
                open_positions_fn=lambda: self._trader.open_positions() if self._trader is not None else 0,
                max_open_positions=int(getattr(self.settings, "max_open_positions", 1)),
                live_order_fn=self._build_live_order,
                entry_gate_fn=self._entry_gate,
                trade_budget_fn=self._trade_budget,
            ),
        }
        # ── Phase-2 extended departments — all real, data-driven ──────
        from orchestration.agents.extended import (  # noqa: PLC0415
            ApiConnectionMonitorAgent,
            BlackSwanDetectorAgent,
            BreakoutSpecialistAgent,
            DashboardSynthesizerAgent,
            DrawdownGuardianAgent,
            DynamicPositionSizerAgent,
            FeeOptimizerAgent,
            GarbageCollectorAgent,
            LatencyPingerAgent,
            MeanReversionAgent,
            ProfitSweeperAgent,
            TaxAccountingClerkAgent,
            TrailingStopBotAgent,
            TrendFollowerAgent,
            VolatilityOracleAgent,
        )

        def _flt(key: str, default: float) -> float:
            try:
                return float(str(getattr(self.settings, key, default)))
            except (TypeError, ValueError):
                return default

        taker_bps = _flt("fee_taker_bps", 25.0)
        maker_bps = _flt("fee_maker_bps", taker_bps)
        dd_limit = _flt("max_daily_loss_pct", 100.0)
        agents.update(
            {
                "volatility_oracle": VolatilityOracleAgent("volatility_oracle", bus, prices, log),
                "trend_follower": TrendFollowerAgent("trend_follower", bus, prices, _TOPIC_SIGNALS, log),
                "mean_reversion": MeanReversionAgent("mean_reversion", bus, prices, _TOPIC_SIGNALS, log),
                "breakout_specialist": BreakoutSpecialistAgent("breakout_specialist", bus, prices, _TOPIC_SIGNALS, log),
                "black_swan_detector": BlackSwanDetectorAgent("black_swan_detector", bus, prices, self, log),
                "drawdown_guardian": DrawdownGuardianAgent("drawdown_guardian", self, dd_limit, log),
                "position_sizer": DynamicPositionSizerAgent("position_sizer", self, 2.0, log),
                "trailing_stop": TrailingStopBotAgent("trailing_stop", self, 1.5, log),
                "profit_sweeper": ProfitSweeperAgent("profit_sweeper", self, 0.5, log),
                "fee_optimizer": FeeOptimizerAgent("fee_optimizer", maker_bps, taker_bps, log),
                "latency_pinger": LatencyPingerAgent("latency_pinger", self, log),
                "api_monitor": ApiConnectionMonitorAgent("api_monitor", self, log),
                "dashboard_synth": DashboardSynthesizerAgent("dashboard_synth", self, 2.0, log),
                "tax_clerk": TaxAccountingClerkAgent("tax_clerk", self, log),
                "garbage_collector": GarbageCollectorAgent("garbage_collector", log),
            }
        )
        # ── Analyst swarm (Phase 5) — 150 real agents in three divisions ──
        # Historical Chart Lab (50) + Live Price Lab (50) + Entry Hunters (50),
        # each with a chief that aggregates a consensus bias. They span every
        # timeframe (วินาที/นาที/ชั่วโมง/วัน) and method, and the entry hunters
        # feed BUY signals into the SAME pipeline (signals → Supreme → gate).
        from orchestration.agents.swarm import build_swarm_agents  # noqa: PLC0415
        swarm = build_swarm_agents(
            bus, prices, _TOPIC_SIGNALS, _TOPIC_ANALYSIS, log, per_division=50
        )
        agents.update(swarm)
        # Timeline Analyst — replays full history, measures p_win, gates entries.
        from orchestration.agents.timeline_analyst import TimelineAnalystAgent  # noqa: PLC0415
        self._timeline = TimelineAnalystAgent(
            "timeline_analyst", bus, prices, _TOPIC_TIMELINE, log,
            min_p_win=self._dec_setting("min_p_win", "0.55"),
        )
        agents["timeline_analyst"] = self._timeline
        money = self._make_money_agents(bus, prices)
        agents.update(money)
        # CEO observer — must be added AFTER money agents so it can see them
        # in self._runtime.status(). It only observes; never executes.
        agents["ceo"] = CeoAgent(
            bus=bus, logger=log, runtime=self,
            agent_roles={
                "market_analyst":    "Generates EMA-cross entry/exit signals",
                "news_intelligence": "Aggregates news sentiment",
                "risk_management":   "Advisory risk monitor (real veto = treasury + risk gate)",
                "probability_lab":   "RSI-based probability scoring",
                "research_dept":     "Rolling historical statistics",
                "execution_agent":   "Rolling paper backtest with fees+slippage",
                "supreme_commander": "Final signal arbiter",
                "treasury":          "Sole owner of cash and PnL ledger",
                "paper_trader":      "Bracketed paper execution engine",
                "ceo":               "Executive observer / audit trail",
                "volatility_oracle": "ATR/Bollinger volatility + squeeze",
                "trend_follower":    "Rides confirmed trends (EMA20/50)",
                "mean_reversion":    "Fades RSI extremes",
                "breakout_specialist": "Donchian breakout trader",
                "black_swan_detector": "Detects crashes; trips breaker",
                "drawdown_guardian": "Halts on daily-loss breach",
                "position_sizer":    "Kelly position sizing",
                "trailing_stop":     "Trailing stop to lock profit",
                "profit_sweeper":    "Sweeps profit to a vault",
                "fee_optimizer":     "Maker/taker fee minimiser",
                "latency_pinger":    "Exchange latency watchdog",
                "api_monitor":       "Feed/account health monitor",
                "dashboard_synth":   "Daily KPI synthesizer",
                "tax_clerk":         "Realized-PnL tax ledger",
                "garbage_collector": "Memory hygiene / GC",
                "timeline_analyst":  "Replays full history; win-probability entry gate",
            },
        )
        self._ceo = agents["ceo"]
        # Connect the REAL Bitkub account (read-only) when credentials exist.
        self._reconciliation = None
        self._rest_gateway = None
        self._maybe_build_reconciliation(bus, log)
        if self._reconciliation is not None:
            agents["reconciliation"] = self._reconciliation  # type: ignore[assignment,unused-ignore]
        # Hand the (possibly None) live gateway to the execution gate. Without
        # this the gate's _rest_gateway stays None and real orders never fire,
        # even with all four live gates open.
        gate = agents.get("risk_gate")
        if gate is not None and hasattr(gate, "set_rest_gateway"):
            gate.set_rest_gateway(self._rest_gateway)  # type: ignore[attr-defined]
        return agents

    def _maybe_build_reconciliation(self, bus: EventBus, log: structlog.BoundLogger) -> None:
        """Build a ReconciliationAgent bound to the live Bitkub wallet.

        No-op (paper-only behaviour preserved) unless BITKUB_API_KEY is set.
        Infrastructure imports are function-local to satisfy the Layer-2 guard.
        """
        key = getattr(self.settings, "bitkub_api_key", None)
        secret = getattr(self.settings, "bitkub_api_secret", None)
        try:
            has_key = bool(key is not None and key.get_secret_value())
        except AttributeError:
            has_key = bool(key)
        if not has_key:
            return
        from infrastructure.gateway.bitkub_balance import BitkubBalanceSource  # noqa: PLC0415
        from orchestration.agents.execution_agent import build_live_gateway  # noqa: PLC0415
        from orchestration.agents.reconciliation_agent import ReconciliationAgent  # noqa: PLC0415

        gateway = build_live_gateway(key, secret)
        self._rest_gateway = gateway
        balance_source = BitkubBalanceSource(gateway)
        self._reconciliation = ReconciliationAgent(
            bus, balance_source, "reconciliation.v1", log, poll_interval_s=60.0
        )

    def _make_money_agents(self, bus: EventBus, prices: str) -> dict[str, AgentLike]:
        """Treasury (sole cash owner) + PaperTrader (positions). PAPER ONLY."""
        store = self._ensure_state_store()
        limits = TreasuryLimits(
            initial_capital=self._initial_capital,
            survival_floor_pct=self._dec_setting("survival_floor_pct", "70"),
            max_daily_loss_pct=self._dec_setting("max_daily_loss_pct", "5"),
        )
        tz_offset = int(getattr(self.settings, "risk_day_tz_offset_minutes", 420))
        treasury = TreasuryAgent(bus, _TOPIC_TREASURY, self.logger, limits, store, tz_offset_minutes=tz_offset)
        params = TradeParams(
            risk_per_trade_pct=str(getattr(self.settings, "risk_per_trade_pct", "1.0")),
            stop_pct=str(getattr(self.settings, "stop_pct", "1.0")),
            take_profit_pct=str(getattr(self.settings, "take_profit_pct", "1.5")),
            fee_taker_bps=str(getattr(self.settings, "fee_taker_bps", "25")),
            slippage_bps=str(getattr(self.settings, "slippage_bps", "5")),
        )
        trader = PaperTraderAgent(
            bus, _TOPIC_DECISIONS_APPROVED, prices, _TOPIC_PAPER_EVENTS,
            self.logger, treasury, params, store,
            circuit_breaker=self._circuit_breaker,
            live_close_fn=self._live_close,
        )
        self._treasury = treasury
        self._trader = trader
        self._trade_params = params
        return {"treasury": treasury, "paper_trader": trader}

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
                    agent.coach_tighten(best_name)  # type: ignore[attr-defined]

    def _task_alive(self, name: str) -> bool:
        task = self.agent_tasks.get(name)
        return task is not None and not task.done()

    def _agent_status(self, name: str, agent: AgentLike) -> dict[str, object]:
        """Generic, typed status view over any AgentLike."""
        stale_ms = int(getattr(self.settings, "heartbeat_stale_ms", 5000))
        now_ms = int(time.time() * 1000)
        alive = agent.running and self._task_alive(name)
        beat = agent.last_beat_ms
        stale = bool(alive and beat > 0 and (now_ms - beat) > stale_ms)
        status: dict[str, object] = {
            "name": name,
            "running": alive,
            "claimed_running": agent.running,
            "last_beat_ms": beat,
            "stale": stale,
            "crashed": bool(agent.running and not self._task_alive(name)),
            "crash_reason": self.crashed_agents.get(name),
            "restarts": self.restart_counts.get(name, 0),
            "msg_count": agent.msg_count,
        }
        parse_failures = getattr(agent, "parse_failures", None)
        if isinstance(parse_failures, int):
            status["parse_failures"] = parse_failures
        signal_count = getattr(agent, "signal_count", None)
        if isinstance(signal_count, int):
            status["signal_count"] = signal_count
        decision_count = getattr(agent, "decision_count", None)
        if isinstance(decision_count, int):
            status["decision_count"] = decision_count
        rejected_count = getattr(agent, "rejected_count", None)
        if isinstance(rejected_count, int):
            status["rejected_count"] = rejected_count

        # Human-readable detail (new agents expose .detail; others fall back).
        detail = getattr(agent, "detail", "")
        if isinstance(detail, str) and detail:
            status["detail"] = detail

        # ── EXP / level (skill) — earned from REAL work, hard-capped at 5000 ──
        sig = signal_count if isinstance(signal_count, int) else 0
        dec = decision_count if isinstance(decision_count, int) else 0
        rej = rejected_count if isinstance(rejected_count, int) else 0
        restarts = self.restart_counts.get(name, 0)
        raw_exp = agent.msg_count + sig * 15 + dec * 20 + rej * 10
        exp = max(0, min(self._EXP_CAP, raw_exp - restarts * 50))
        level = min(50, 1 + exp // 100)
        ranks = ["Rookie", "Skilled", "Expert", "Master", "Grandmaster", "Legendary"]
        rank = ranks[min(len(ranks) - 1, level // 10)]
        status["exp"] = exp
        status["exp_max"] = self._EXP_CAP
        status["level"] = level
        status["rank"] = rank

        # ── Self-improvement view: daily score + REAL accuracy ──
        learner = self._learner_for(name, agent)
        learner.roll_day()
        reliability = reliability_score(
            running=alive, stale=stale,
            crashed=bool(agent.running and not self._task_alive(name)),
            restarts=restarts, msg_count=agent.msg_count,
        )
        learner.score = round(blended_score(reliability, learner), 1)
        status["score"] = learner.score
        status["score_kind"] = learner.kind
        hr = learner.hit_rate()
        status["hit_rate"] = round(hr * 100, 1) if hr is not None else None
        status["resolved"] = learner.resolved
        status["adapt_count"] = learner.adapt_count
        # Learning board: what this agent learns from mistakes + can improve,
        # with the real recent losses and parameter changes it made.
        status.update(self._learning_card(name, agent, learner))
        return status

    # Per-agent "learns from mistakes / can improve" cards for the dashboard
    # learning board. Agents that expose learns_from()/can_improve() override
    # these; the rest get an honest, specific description here.
    _LEARNING_CARDS: dict[str, tuple[str, str]] = {
        "market_analyst": ("สัญญาณ EMA-cross ที่ทายผิดทิศ (เกรดกับราคาจริง)",
                           "เพิ่มเงื่อนไขยืนยัน gap EMA เมื่อแพ้บ่อย / ผ่อนเมื่อแม่น"),
        "news_intelligence": ("ข่าวที่ให้ sentiment ผิดทาง",
                             "ถ่วงน้ำหนักแหล่งข่าวที่แม่นกว่า (ขยาย feed)"),
        "risk_management": ("ออเดอร์ที่ปล่อยผ่านแล้วชนลิมิต",
                           "ปรับเพดานความเสี่ยง/exposure อัตโนมัติ"),
        "probability_lab": ("ค่าความน่าจะเป็น RSI ที่ทายผิด",
                           "ปรับช่วง RSI/threshold ที่ใช้คำนวณ"),
        "research_dept": ("สถิติย้อนหลังที่คลาดเคลื่อนจากของจริง",
                         "ขยายหน้าต่างข้อมูล/ความถี่ rolling"),
        "execution_agent": ("ผล backtest หมุนที่ขาดทุน",
                           "ปรับโมเดล fee/slippage ให้ตรงตลาดจริง"),
        "supreme_commander": ("การตัดสินใจที่สวนเสียงส่วนใหญ่แล้วผิด",
                             "ปรับเกณฑ์ consensus (จำนวนโหวต/กรอบเวลา)"),
        "risk_gate": ("ออเดอร์ที่โดน veto / โดนเกต p_win",
                     "ปรับ rate-limit + เกณฑ์ win-probability"),
        "treasury": ("การขาดทุนที่ทะลุเพดานรายวัน",
                    "ปรับ survival-floor / daily-loss limit"),
        "paper_trader": ("ไม้ที่โดน stop-loss",
                        "ปรับ stop / take-profit / trailing"),
        "ceo": ("เหตุการณ์เสี่ยงที่ควรเตือนแต่พลาด",
               "ปรับเกณฑ์การรายงาน/แจ้งเตือน"),
        "volatility_oracle": ("การพยากรณ์ squeeze/ระเบิดที่พลาด",
                             "ปรับ threshold ความผันผวน"),
        "trend_follower": ("เทรนด์หลอก (สัญญาณ EMA ผิด)",
                          "เพิ่ม gap ยืนยัน EMA จากผลแพ้/ชนะจริง"),
        "mean_reversion": ("การ fade ที่ผิด (ราคาไม่เด้งกลับ)",
                          "ปรับ RSI oversold/overbought จากผลจริง"),
        "breakout_specialist": ("เบรกหลอก (false breakout)",
                               "ขยาย/ลดกรอบ Donchian N จากผลจริง"),
        "black_swan_detector": ("การจับช็อกราคาช้า/พลาด",
                               "ปรับ threshold %การเคลื่อนไหว 60 วิ"),
        "drawdown_guardian": ("การสั่งหยุดเทรดช้าเกินไป",
                             "ปรับเพดาน drawdown รายวัน"),
        "position_sizer": ("ขนาดไม้ที่ใหญ่/เล็กเกินจาก Kelly",
                          "ปรับสูตร Kelly จาก win-rate จริง"),
        "trailing_stop": ("การล็อกกำไรช้าไป (คืนกำไร)",
                         "ปรับ %trailing ให้ตามกำไรจริง"),
        "profit_sweeper": ("จังหวะกวาดกำไรที่พลาด",
                          "ปรับสัดส่วนกวาดกำไรเข้าคลัง"),
        "fee_optimizer": ("การเลือก maker/taker ที่จ่ายแพง",
                         "ปรับกลยุทธ์ลดค่าธรรมเนียม"),
        "latency_pinger": ("ช่วง latency พุ่งที่ตอบสนองช้า",
                          "ปรับ threshold ชะลอการยิงออเดอร์"),
        "api_monitor": ("ช่วงฟีด/บัญชีหลุดที่จับช้า",
                       "ปรับความถี่/เกณฑ์การตรวจสอบ"),
        "dashboard_synth": ("KPI สรุปที่คลาดเคลื่อน",
                           "ปรับการกลั่น KPI รายวัน"),
        "tax_clerk": ("รายการ PnL ที่ตกหล่น",
                     "ปรับการจัดหมวดเพื่อภาษี"),
        "garbage_collector": ("รอบ GC ที่คืนหน่วยความจำได้น้อย",
                             "ปรับความถี่/เกณฑ์การเก็บกวาดหน่วยความจำ"),
    }

    def _learning_card(self, name: str, agent: AgentLike, learner: Learner) -> dict[str, object]:
        """What this agent learns from its mistakes + what it can improve, with
        REAL recent losing outcomes and the parameter changes it made."""
        lf = getattr(agent, "learns_from", None)
        ci = getattr(agent, "can_improve", None)
        learns_from = lf() if callable(lf) else None
        can_improve = ci() if callable(ci) else None
        if learns_from is None or can_improve is None:
            default = self._LEARNING_CARDS.get(
                name, ("ผลการทำงานจริงเทียบกับสิ่งที่คาด", "ปรับพารามิเตอร์จากสถิติจริง")
            )
            learns_from = learns_from or default[0]
            can_improve = can_improve or default[1]
        return {
            "learns_from": learns_from,
            "can_improve": can_improve,
            "recent_mistakes": learner.recent_mistakes(5),
            "recent_improvements": learner.recent_improvements(5),
        }

    def _learner_for(self, name: str, agent: AgentLike) -> Learner:
        """The agent's own Learner if it has one (extended agents), else a
        runtime-side reliability learner created on demand."""
        own = getattr(agent, "learner", None)
        if isinstance(own, Learner):
            return own
        if name not in self._learners:
            self._learners[name] = Learner(name, "reliability")
        return self._learners[name]

    def learning_overview(self, limit: int = 40) -> dict[str, object]:
        """Leaderboard + merged real-time learning feed across all agents.

        Every entry is a REAL event with a real timestamp — nothing fabricated.
        """
        rows: list[dict[str, object]] = []
        feed: list[dict[str, object]] = []
        for name, agent in self.agents.items():
            learner = self._learner_for(name, agent)
            hr = learner.hit_rate()
            card = self._learning_card(name, agent, learner)
            rows.append({
                "name": name,
                "score": learner.score,
                "kind": learner.kind,
                "hit_rate": round(hr * 100, 1) if hr is not None else None,
                "resolved": learner.resolved,
                "today_resolved": learner.today_resolved,
                "adapt_count": learner.adapt_count,
                **card,
            })
            for entry in learner.recent(limit):
                e = dict(entry)
                e["agent"] = name
                feed.append(e)
        rows.sort(key=lambda r: (r["score"] if isinstance(r["score"], int | float) else 0), reverse=True)
        feed.sort(key=lambda e: e.get("ts_ms", 0), reverse=True)  # type: ignore[arg-type,return-value]
        return {
            "ts_ms": int(time.time() * 1000),
            "llm_critic": "disabled (no API key) — scores are statistical, not LLM",
            "leaderboard": rows,
            "feed": feed[:limit],
        }

    def _risk_equity_state(self) -> tuple[Decimal, Decimal, Decimal]:
        """Real (peak_equity, current_equity, daily_pnl) for the Risk agent's
        drawdown / daily-loss checks. Before any trade this is the honest
        no-movement baseline (equity == peak, pnl == 0), not a fabrication."""
        if self._treasury is not None and self._trader is not None:
            current = self._treasury.cash + self._trader.open_market_value()
            daily_pnl = self._treasury.realized_today + self._trader.unrealized_pnl()
            peak = self._peak_equity if self._peak_equity >= current else current
            return peak, current, daily_pnl
        return self._initial_capital, self._initial_capital, Decimal("0")

    def _win_rate(self) -> float | None:
        """Win rate of the rolling paper backtest run by the execution
        department over live prices (fees + slippage included). None until
        the first window completes — never a fabricated number."""
        agent = self.agents.get("execution_agent")
        raw = getattr(agent, "last_win_rate", None) if agent is not None else None
        if raw is None:
            return None
        try:
            return float(Decimal(str(raw)))
        except InvalidOperation:
            return None

    # ── Operator control plane (dashboard-driven, live) ──────────────
    _LIVE_TOKEN = "I_ACCEPT_REAL_MONEY_RISK"
    _BREAKER_RESET_TOKEN = "MANUAL_RESET_CONFIRMED"
    _CONTROL_KEY = "control.settings.v1"
    _MEMORY_KEY = "agents.memory.v1"  # every agent's learned memory, on disk
    _EXP_CAP = 5000  # max agent skill (EXP) — agents level up from real work

    def _risk_gate(self) -> object | None:
        return self.agents.get("risk_gate")

    def _current_risk_settings(self) -> RiskSettings:
        """Build a RiskSettings snapshot from the live objects."""
        from orchestration.control import RiskSettings  # noqa: PLC0415

        tp = self._trade_params
        br = self._circuit_breaker
        gate = self._risk_gate()
        daily = (
            self._treasury.limits.max_daily_loss_pct
            if self._treasury is not None
            else self._dec_setting("max_daily_loss_pct", "5")
        )
        return RiskSettings(
            risk_per_trade_pct=getattr(tp, "risk_per_trade_pct", Decimal("1")),
            stop_pct=getattr(tp, "stop_pct", Decimal("1")),
            take_profit_pct=getattr(tp, "take_profit_pct", Decimal("1.5")),
            max_daily_loss_pct=daily,
            max_consecutive_losses=(
                br.max_consecutive_losses if br is not None else 5
            ),
            max_open_positions=int(getattr(gate, "_max_open_positions", 1)),
            max_deployable_thb=self._max_deployable_thb,
            max_single_order_thb=self._max_single_order_thb,
            min_p_win=self._dec_setting("min_p_win", "0.55"),
        )

    def get_risk_settings(self) -> dict[str, str]:
        """Current live risk settings for the dashboard."""
        return self._current_risk_settings().as_str_dict()

    async def update_risk_settings(
        self, patch: dict[str, object]
    ) -> tuple[bool, dict[str, object]]:
        """Validate + apply risk settings live. Returns (ok, payload).

        On success the new values immediately affect the next trade (sizing,
        stop/TP), the daily-loss cap, the consecutive-loss breaker threshold,
        and the open-position cap. Settings are persisted to the state store.
        """
        from orchestration.control import validate_risk_settings  # noqa: PLC0415

        current = self._current_risk_settings()
        new, errors = validate_risk_settings(current, patch)  # type: ignore[arg-type]
        if new is None:
            return False, {"errors": errors}

        # Apply to the live objects.
        tp = self._trade_params
        if tp is not None:
            tp.risk_per_trade_pct = new.risk_per_trade_pct  # type: ignore[attr-defined]
            tp.stop_pct = new.stop_pct  # type: ignore[attr-defined]
            tp.take_profit_pct = new.take_profit_pct  # type: ignore[attr-defined]
        if self._treasury is not None:
            from domain.portfolio.treasury import TreasuryLimits  # noqa: PLC0415

            self._treasury.update_limits(
                TreasuryLimits(
                    initial_capital=self._initial_capital,
                    survival_floor_pct=self._dec_setting("survival_floor_pct", "70"),
                    max_daily_loss_pct=new.max_daily_loss_pct,
                )
            )
        if self._circuit_breaker is not None:
            self._circuit_breaker.update_threshold(new.max_consecutive_losses)
        # Win-probability gate is operator-tunable live: update the setting the
        # entry gate reads AND the Timeline Analyst's own threshold/display.
        self.settings.min_p_win = str(new.min_p_win)  # type: ignore[attr-defined]
        if self._timeline is not None and hasattr(self._timeline, "set_min_p_win"):
            self._timeline.set_min_p_win(new.min_p_win)  # type: ignore[attr-defined]
        gate = self._risk_gate()
        if gate is not None and hasattr(gate, "set_max_open_positions"):
            gate.set_max_open_positions(new.max_open_positions)  # type: ignore[attr-defined]
        self._max_deployable_thb = new.max_deployable_thb
        self._max_single_order_thb = new.max_single_order_thb
        # Keep the paper sizing cap in lockstep with the live order cap so a
        # real order and its paper mirror size identically.
        if tp is not None:
            tp.max_order_thb = new.max_single_order_thb  # type: ignore[attr-defined]

        await self._persist_controls(new.as_str_dict())
        self._record_control("risk_settings_updated", dict(patch))
        return True, {"settings": new.as_str_dict()}

    def update_trailing_stop(self, new_stop: object) -> bool:
        """Let the Trailing-Stop agent ratchet the live position's protective
        stop UP (lock profit). Real effect — not advisory. Returns True if
        the stop moved. Disabled via trailing_stop_enabled=false."""
        if self._trader is None:
            return False
        if not bool(getattr(self.settings, "trailing_stop_enabled", True)):
            return False
        try:
            stop = Decimal(str(new_stop))
        except (InvalidOperation, ValueError, TypeError):
            return False
        return self._trader.set_trail_stop(stop)

    def apply_kelly_risk(self, suggested_pct: object) -> bool:
        """Let the Kelly sizer drive the live per-trade risk %, clamped to a
        safe band [0.25 .. kelly_max_risk_pct]. Real effect on the NEXT entry.
        Disabled via kelly_sizing_enabled=false. Returns True if applied."""
        tp = self._trade_params
        if tp is None or not bool(getattr(self.settings, "kelly_sizing_enabled", True)):
            return False
        try:
            val = Decimal(str(suggested_pct))
        except (InvalidOperation, ValueError, TypeError):
            return False
        lo = Decimal("0.25")
        hi = self._dec_setting("kelly_max_risk_pct", "2.0")
        if hi < lo:
            hi = lo
        clamped = max(lo, min(hi, val))
        tp.risk_per_trade_pct = clamped  # type: ignore[attr-defined]
        return True

    def trip_breaker(self, reason: str = "MANUAL") -> dict[str, object]:
        """Manually open the circuit breaker (halts trading via the risk gate)."""
        if self._circuit_breaker is None:
            return {"ok": False, "error": "no breaker"}
        self._circuit_breaker.trip(reason or "MANUAL", int(time.time()))
        self._record_control("breaker_trip", {"reason": reason})
        self._schedule_alert(f"🛑 Circuit breaker tripped: {reason}", "critical")
        return {"ok": True, "is_open": True}

    # ── Alerts ────────────────────────────────────────────────────────
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
        loop.create_task(self.send_alert(message, level))

    # ── Manual trade command (operator override) ──────────────────────
    async def manual_order(
        self, side: str, price: object | None = None
    ) -> tuple[bool, dict[str, object]]:
        """Operator BUY / SELL(=CLOSE). In paper mode this changes the REAL
        paper portfolio; live routing remains gated. Respects breaker + cash."""
        if self._trader is None:
            return False, {"error": "runtime not started"}
        if self._circuit_breaker is not None and self._circuit_breaker.is_open:
            return False, {"error": "circuit breaker is OPEN"}
        px: Decimal | None = None
        if price is not None:
            try:
                px = Decimal(str(price))
            except (InvalidOperation, ValueError):
                return False, {"error": f"bad price {price!r}"}
        side_u = str(side).upper()
        if side_u == "BUY":
            # In live-armed mode a manual BUY fires a REAL bid first; the paper
            # position is then marked live-backed so its exits close the real
            # position too. Manual orders bypass the p_win gate (operator override).
            placed_live = await self._place_manual_live_bid(px)
            ok, msg = await self._trader.manual_buy(px, is_live=placed_live)
            if placed_live and ok:
                msg = f"{msg} (ส่งคำสั่งจริงบน Bitkub แล้ว)"
        elif side_u in ("SELL", "CLOSE"):
            # manual_close → _close(MANUAL) → live_close_fn closes the real
            # position when it was live-backed.
            ok, msg = await self._trader.manual_close(px)
        else:
            return False, {"error": f"unknown side {side!r} (use BUY/SELL)"}
        self._record_control("manual_order", {"side": side_u, "result": msg})
        if ok:
            self._schedule_alert(f"📋 Manual {side_u}: {msg}", "info")
        return ok, {"message": msg, "positions": self._trader.open_positions()}

    async def _place_manual_live_bid(self, px: Decimal | None) -> bool:
        """Place a REAL bid for an operator BUY when live orders are armed and
        no position is open. Returns True only if the real order was placed."""
        if self._trader is None or self._trade_params is None:
            return False
        if self._trader.position is not None or not self._live_orders_armed():
            return False
        if px is not None:
            self._trader.mark_price = px  # ensure sizing uses the operator price
        symbol = str(getattr(self._trade_params, "symbol", "THB_BTC"))
        spec = self._build_live_order({"signal": "BUY", "symbol": symbol})
        if not spec:
            return False
        gate = self.agents.get("risk_gate")
        gw = getattr(gate, "_rest_gateway", None) if gate is not None else None
        if gw is None or not hasattr(gw, "place_bid"):
            return False
        try:
            await gw.place_bid(  # type: ignore[attr-defined]
                spec["symbol"], spec["amount"], spec["rate"], spec.get("typ", "market")
            )
            self.logger.info("runtime.manual_live_bid", amount=spec["amount"])
            return True
        except Exception:
            self.logger.error("runtime.manual_live_bid_failed", exc_info=True)
            return False

    async def close_all(self) -> dict[str, object]:
        """Flatten all open paper positions (operator action)."""
        if self._trader is None:
            return {"ok": False, "error": "runtime not started"}
        from domain.trading.paper import ExitReason  # noqa: PLC0415

        await self._trader.flatten(ExitReason.MANUAL)
        self._record_control("close_all", {})
        return {"ok": True, "positions": self._trader.open_positions()}

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

    # ── Entry governance: win-probability gate + daily trade budget ──────
    def _roll_trade_day(self) -> None:
        today = self._treasury.day_key if self._treasury is not None else ""
        if today != self._trades_day_key:
            self._trades_day_key = today
            self._entries_baseline = self._trader.entries_opened if self._trader is not None else 0

    def trades_today(self) -> int:
        cur = self._trader.entries_opened if self._trader is not None else 0
        return max(0, cur - self._entries_baseline)

    def daily_profit_pct(self) -> Decimal:
        if self._treasury is None or self._initial_capital <= 0:
            return Decimal("0")
        return (self._treasury.realized_today / self._initial_capital * Decimal("100"))

    def _trade_budget(self) -> bool:
        """True while a new entry is allowed today (trade-count quota + optional
        profit-target lock). Daily LOSS halting is owned by the treasury."""
        self._roll_trade_day()
        if self._max_trades_per_day > 0 and self.trades_today() >= self._max_trades_per_day:
            return False
        target_locked = (
            self._stop_at_daily_target
            and self._target_daily_profit_pct > 0
            and self.daily_profit_pct() >= self._target_daily_profit_pct
        )
        return not target_locked  # opt-in: halt new entries once target reached

    def _entry_gate(self, data: dict[str, object]) -> tuple[bool, list[str]]:
        """Confluence + win-probability gate for a proposed BUY entry.
        Returns (approved, reason_codes). Honest: p_win is the Timeline Analyst's
        MEASURED historical win rate, not a promise."""
        if not self._entry_gate_enabled:
            return True, []
        from domain.strategy.base import SignalAction  # noqa: PLC0415
        from domain.strategy.confluence import (  # noqa: PLC0415
            EntryInputs,
            GateParams,
            evaluate_entry,
        )

        tl = self._timeline
        p_win = Decimal(str(getattr(tl, "p_win", "0"))) if tl is not None else Decimal("0")
        samples = int(getattr(tl, "p_win_samples", 0)) if tl is not None else 0
        regime = str(getattr(tl, "regime", "RANGE")) if tl is not None else "RANGE"
        try:
            sentiment = Decimal(str(self.last_news.get("score", "0")))
        except (InvalidOperation, ValueError, TypeError):
            sentiment = Decimal("0")

        inputs = EntryInputs(
            signal_action=SignalAction.BUY,
            signal_confidence=Decimal("1"),  # already cleared Supreme consensus
            regime=regime,
            sentiment_score=sentiment,
            p_win=p_win,
            p_win_samples=samples,
            trend_agree=(regime != "TREND_DOWN"),
        )
        params = GateParams(
            min_p_win=self._dec_setting("min_p_win", "0.55"),
            min_confidence=self._dec_setting("gate_min_confidence", "0.50"),
            min_samples=int(getattr(self.settings, "gate_min_samples", 8)),
            block_regime_mismatch=bool(getattr(self.settings, "gate_block_regime_mismatch", False)),
        )
        decision = evaluate_entry(inputs, params)
        reasons = [r.value for r in decision.reasons]
        for r in reasons:
            self._gate_block_reasons[r] = self._gate_block_reasons.get(r, 0) + 1
        return decision.approved, reasons

    async def _live_close(self, qty: object, rate: object) -> None:
        """Place a REAL closing ask for a protective exit (stop/TP/trailing/
        manual/emergency) on the live exchange. Called by the paper trader only
        for live-backed positions; no-ops unless live orders are armed so it is
        always safe to wire in paper mode."""
        if not self._live_orders_armed():
            return
        gate = self.agents.get("risk_gate")
        gw = getattr(gate, "_rest_gateway", None) if gate is not None else None
        if gw is None or not hasattr(gw, "place_ask"):
            return
        symbol = str(getattr(self._trade_params, "symbol", "THB_BTC")).lower()
        try:
            # market order: a protective stop must FILL even as price falls through.
            result = await gw.place_ask(symbol, str(qty), str(rate), "market")  # type: ignore[attr-defined]
            self.logger.info("runtime.live_exit_order", qty=str(qty), rate=str(rate),
                             order_id=(result.get("result", {}) or {}).get("id")
                             if isinstance(result, dict) else None)
        except Exception:
            self.logger.error("runtime.live_exit_failed", exc_info=True)
            self._schedule_alert(
                f"⚠️ ปิด position จริงไม่สำเร็จ (qty {qty}) — ตรวจสอบบัญชี Bitkub ด่วน",
                "critical",
            )

    def _build_live_order(self, data: dict[str, object]) -> dict[str, str] | None:
        """Turn an approved decision into a sized, capped live order spec.

        Uses the same sizing as the paper engine, then clamps the notional to
        ``max_single_order_thb`` (when set) as a hard safety cap for the first
        live orders. Returns {action: bid|ask, symbol, amount, rate} or None.
        """
        from domain.trading.paper import size_order, slip_buy  # noqa: PLC0415

        signal = str(data.get("signal", ""))
        symbol = str(data.get("symbol", "thb_btc")).lower()
        trader = self._trader
        tp = self._trade_params
        if trader is None or tp is None or self._treasury is None:
            return None
        mark = trader.mark_price
        if mark is None:
            return None

        if signal == "BUY":
            if trader.position is not None:
                return None  # single-position rule
            entry = slip_buy(mark, tp.slippage_bps)  # type: ignore[attr-defined]
            stop = entry * (Decimal("1") - tp.stop_pct / Decimal("100"))  # type: ignore[attr-defined]
            qty = size_order(
                cash=self._treasury.cash,
                entry_price=entry,
                stop_price=stop,
                risk_per_trade_pct=tp.risk_per_trade_pct,  # type: ignore[attr-defined]
                fee_bps=tp.fee_taker_bps,  # type: ignore[attr-defined]
                slippage_bps=Decimal("0"),
            )
            if qty <= 0:
                return None
            # Apply the per-order THB cap on QTY (not notional) so the real
            # order and its paper mirror — which caps qty identically — end up
            # the same size. No divergence when the cap is active.
            cap = self._max_single_order_thb
            if cap > 0 and entry > 0 and qty * entry > cap:
                from decimal import ROUND_DOWN  # noqa: PLC0415
                qty = (cap / entry).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
            if qty <= 0:
                return None
            notional = qty * mark
            return {
                "action": "bid",
                "symbol": symbol,
                "amount": str(notional.quantize(Decimal("0.01"))),
                "rate": str(mark),
                "typ": str(getattr(self.settings, "live_order_type", "market")),
            }

        if signal == "SELL":
            pos = trader.position
            if pos is None:
                return None  # nothing to sell/close
            return {
                "action": "ask",
                "symbol": symbol,
                "amount": str(pos.qty),
                "rate": str(mark),
                "typ": str(getattr(self.settings, "live_order_type", "market")),
            }
        return None

    # ── Live account credentials (set from the dashboard, no restart) ──
    def account_status(self) -> dict[str, object]:
        """Real-account connection status (never leaks the key)."""
        recon = self._reconciliation
        try:
            has_key = bool(
                getattr(self.settings, "bitkub_api_key", None)
                and self.settings.bitkub_api_key.get_secret_value()  # type: ignore[attr-defined]
            )
        except AttributeError:
            has_key = bool(getattr(self.settings, "bitkub_api_key", None))
        return {
            "has_key": has_key,
            "connected": self._rest_gateway is not None,
            "reconciled": bool(getattr(recon, "is_reconciled", False)) if recon else False,
            "balances": dict(getattr(recon, "last_balances", {})) if recon else {},
            "last_error": getattr(recon, "last_error", None) if recon else None,
        }

    async def connect_account(
        self,
        api_key: str,
        api_secret: str,
        *,
        balance_source: object | None = None,
        start_polling: bool = True,
    ) -> dict[str, object]:
        """Connect the REAL Bitkub account live: update credentials, build the
        gateway + reconciliation poller, persist to .env. No restart needed.
        balance_source can be injected for tests (avoids real network)."""
        if not api_key or not api_secret:
            return {"ok": False, "error": "api_key and api_secret are required"}
        from pydantic import SecretStr  # noqa: PLC0415

        self.settings.bitkub_api_key = SecretStr(api_key)  # type: ignore[attr-defined]
        self.settings.bitkub_api_secret = SecretStr(api_secret)  # type: ignore[attr-defined]

        await self._disconnect_account()

        if balance_source is None:
            from infrastructure.gateway.bitkub_balance import BitkubBalanceSource  # noqa: PLC0415
            from orchestration.agents.execution_agent import build_live_gateway  # noqa: PLC0415

            gateway = build_live_gateway(
                self.settings.bitkub_api_key, self.settings.bitkub_api_secret
            )
            with contextlib.suppress(Exception):
                await gateway.__aenter__()  # type: ignore[attr-defined]
            self._rest_gateway = gateway
            balance_source = BitkubBalanceSource(gateway)
        else:
            self._rest_gateway = object()  # marker so status shows connected

        from orchestration.agents.reconciliation_agent import ReconciliationAgent  # noqa: PLC0415

        recon = ReconciliationAgent(
            self._ensure_bus(), balance_source, "reconciliation.v1", self.logger,
            poll_interval_s=60.0,
        )
        self._reconciliation = recon
        self.agents["reconciliation"] = recon  # type: ignore[assignment]
        # Keep the execution gate's live gateway in sync with the freshly
        # connected account (None-safe; only a real signed gateway can order).
        gate = self.agents.get("risk_gate")
        if gate is not None and hasattr(gate, "set_rest_gateway"):
            gw = self._rest_gateway if hasattr(self._rest_gateway, "place_bid") else None
            gate.set_rest_gateway(gw)  # type: ignore[attr-defined]

        # Immediately VERIFY by reading the real wallet once, so the Connect
        # response tells the truth: real balances on success, or the real
        # Bitkub error (bad key / no permission / IP not allowed) on failure.
        verified = False
        verify_error: str | None = None
        balances: dict[str, str] = {}
        try:
            raw = await balance_source.get_balance()  # type: ignore[attr-defined]
            balances = {k: str(v) for k, v in raw.items()}
            verified = True
        except Exception as exc:
            verify_error = str(exc)
        recon.set_state(reconciled=verified, error=verify_error, balances=balances)

        if start_polling:
            await self.start_agent("reconciliation")
        self._persist_credentials(api_key, api_secret)
        self._record_control("credentials_set", {"has_key": True, "verified": verified})
        if verified:
            self._schedule_alert("🔌 Bitkub account connected & wallet read OK", "info")
        else:
            self._schedule_alert(f"⚠️ Bitkub connected but wallet read failed: {verify_error}", "warning")
        return {
            "ok": True,
            "verified": verified,
            "error": verify_error,
            "balances": balances,
            **self.account_status(),
        }

    async def _disconnect_account(self) -> None:
        """Stop any existing reconciliation poller and close the gateway."""
        # Disable live order routing first — never leave the gate holding a
        # gateway that is about to be closed.
        gate = self.agents.get("risk_gate")
        if gate is not None and hasattr(gate, "set_rest_gateway"):
            gate.set_rest_gateway(None)  # type: ignore[attr-defined]
        if "reconciliation" in self.agents:
            with contextlib.suppress(Exception):
                await self.stop_agent("reconciliation")
            self.agents.pop("reconciliation", None)
        if self._rest_gateway is not None:
            exit_fn = getattr(self._rest_gateway, "__aexit__", None)
            if callable(exit_fn):
                with contextlib.suppress(Exception):
                    await exit_fn(None, None, None)
        self._rest_gateway = None
        self._reconciliation = None

    def _persist_credentials(self, api_key: str, api_secret: str) -> None:
        """Write the credentials into .env, preserving other lines."""
        from pathlib import Path  # noqa: PLC0415

        env = Path(".env")
        lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []

        def _set(field: str, value: str, src: list[str]) -> list[str]:
            prefix = field + "="
            out: list[str] = []
            found = False
            for ln in src:
                if ln.strip().startswith(prefix):
                    out.append(f"{field}={value}")
                    found = True
                else:
                    out.append(ln)
            if not found:
                out.append(f"{field}={value}")
            return out

        lines = _set("BITKUB_API_KEY", api_key, lines)
        lines = _set("BITKUB_API_SECRET", api_secret, lines)
        with contextlib.suppress(Exception):
            env.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def reset_breaker(self, token: str) -> dict[str, object]:
        """Close the breaker — requires the confirmation token."""
        if self._circuit_breaker is None:
            return {"ok": False, "error": "no breaker"}
        ok = self._circuit_breaker.reset(token, int(time.time()))
        if ok:
            self._record_control("breaker_reset", {})
        return {"ok": ok, "is_open": self._circuit_breaker.is_open}

    def _live_gate_checklist(self) -> dict[str, bool]:
        """Return each live gate's pass/fail state (truthful, no guesswork)."""
        from pathlib import Path  # noqa: PLC0415

        engine = str(getattr(self.settings, "execution_engine", "paper"))
        confirm = str(getattr(self.settings, "live_trading_confirm", ""))
        kill = Path("data/KILL_SWITCH").exists()
        breaker_open = bool(self._circuit_breaker and self._circuit_breaker.is_open)
        return {
            "engine_live": engine == "live",
            "confirm_token": confirm == self._LIVE_TOKEN,
            "kill_switch_clear": not kill,
            "breaker_closed": not breaker_open,
        }

    def get_execution_mode(self) -> dict[str, object]:
        """Current execution mode + the 4-gate checklist."""
        gates = self._live_gate_checklist()
        return {
            "mode": str(getattr(self.settings, "execution_engine", "paper")),
            "gates": gates,
            "all_gates_open": all(gates.values()),
        }

    def set_execution_mode(
        self, mode: str, confirm: str = ""
    ) -> tuple[bool, dict[str, object]]:
        """Switch paper<->live. Live requires the confirm token AND the other
        gates (no kill switch, breaker closed). Paper always allowed."""
        if mode == "paper":
            self.settings.execution_engine = "paper"  # type: ignore[attr-defined]
            self.settings.live_trading_confirm = ""  # type: ignore[attr-defined]
            self._record_control("execution_mode", {"mode": "paper"})
            return True, self.get_execution_mode()
        if mode != "live":
            return False, {"error": f"unknown mode {mode!r} (use 'paper' or 'live')"}
        if confirm != self._LIVE_TOKEN:
            return False, {
                "error": "live requires the confirmation token",
                "required_token": self._LIVE_TOKEN,
            }
        from pathlib import Path  # noqa: PLC0415

        if Path("data/KILL_SWITCH").exists():
            return False, {"error": "KILL_SWITCH file present — remove it first"}
        if self._circuit_breaker is not None and self._circuit_breaker.is_open:
            return False, {"error": "circuit breaker is OPEN — reset it first"}
        # Real-money guard: never arm live with an unbounded order size. Require
        # a per-order THB cap so the first live orders are bounded even if the
        # experiment-mode loss limits are still wide open.
        if self._max_single_order_thb <= 0:
            return False, {
                "error": (
                    "set a per-order cap first: max_single_order_thb must be > 0 "
                    "before going live (protects against an unbounded first order)"
                ),
                "field": "max_single_order_thb",
            }
        self.settings.execution_engine = "live"  # type: ignore[attr-defined]
        self.settings.live_trading_confirm = self._LIVE_TOKEN  # type: ignore[attr-defined]
        self._record_control("execution_mode", {"mode": "live"})
        return True, self.get_execution_mode()

    def control_audit(self, limit: int = 100) -> list[dict[str, object]]:
        """Recent operator control actions (who/what/when)."""
        return self._control_audit[-max(1, min(limit, 1000)):]

    def _record_control(self, action: str, detail: dict[str, object]) -> None:
        self._control_audit.append(
            {"ts_ms": int(time.time() * 1000), "action": action, "detail": detail}
        )
        if len(self._control_audit) > 2000:
            self._control_audit = self._control_audit[-2000:]
        self.logger.info("control.action", action=action, detail=detail)

    async def _persist_controls(self, settings: dict[str, str]) -> None:
        store = self._state_store or self._ensure_state_store()
        if store is None:
            return
        with contextlib.suppress(Exception):
            await store.set(self._CONTROL_KEY, orjson.dumps(settings))

    # ── Agent memory (survives shutdown — saved on the user's machine) ──
    def _memory_store(self) -> StateStore | None:
        """The state store used for agent memory (SQLite on disk in prod)."""
        return self._state_store or self._ensure_state_store()

    async def _persist_memories(self) -> None:
        """Write every agent's Learner memory (counters + mistakes/fixes journal)
        to the state store as one atomic snapshot. Best-effort; never raises."""
        store = self._memory_store()
        if store is None:
            return
        payload: dict[str, object] = {
            name: self._learner_for(name, agent).to_dict()
            for name, agent in self.agents.items()
        }
        with contextlib.suppress(Exception):
            await store.set(self._MEMORY_KEY, orjson.dumps(payload))

    async def _restore_memories(self) -> None:
        """Reload each agent's memory from the last session so it remembers its
        past mistakes and the fixes it made (ความทรงจำจากของเดิม)."""
        store = self._memory_store()
        if store is None:
            return
        try:
            raw = await store.get(self._MEMORY_KEY)
        except Exception:
            return
        if raw is None:
            return
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            return
        if not isinstance(data, dict):
            return
        restored = 0
        for name, agent in self.agents.items():
            mem = data.get(name)
            if not isinstance(mem, dict):
                continue
            learner = self._learner_for(name, agent)
            learner.load_dict(mem)
            learner.log("🧠 จำจากเซสชันก่อนได้ (ความผิดพลาด + การแก้ไข)", "event")
            restored += 1
        self.logger.info("runtime.memory_restored", agents=restored)

    async def _memory_loop(self) -> None:
        """Persist memory on an interval so progress is saved gradually."""
        interval = float(getattr(self.settings, "memory_persist_interval_s", 30.0))
        while True:
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            await self._persist_memories()

    async def load_controls(self) -> None:
        """Restore persisted control settings on startup (best-effort)."""
        store = self._state_store or self._ensure_state_store()
        if store is None:
            return
        try:
            raw = await store.get(self._CONTROL_KEY)
        except Exception:
            return
        if raw is None:
            return
        with contextlib.suppress(Exception):
            data = orjson.loads(raw)
            if isinstance(data, dict):
                await self.update_risk_settings(dict(data))

    def status(self) -> dict[str, object]:
        """Return current runtime status for the dashboard."""
        uptime_sec = int((time.time() * 1000 - self.start_time_ms) / 1000)
        window = list(self.msg_count_window)
        msg_per_sec = round(sum(window) / max(len(window), 1), 1)

        if self._treasury is not None and self._trader is not None:
            cash = self._treasury.cash
            equity = cash + self._trader.open_market_value()
            realized_today = self._treasury.realized_today
            pnl_today_dec = realized_today + self._trader.unrealized_pnl()
            positions = self._trader.open_positions()
            wins, losses = self._treasury.wins, self._treasury.losses
            trades_closed = self._trader.trades_closed
            halted = self._treasury.halted
            win_rate = self._treasury.win_rate()
        else:
            cash = equity = self._initial_capital
            realized_today = pnl_today_dec = Decimal("0")
            positions = wins = losses = trades_closed = 0
            halted = False
            win_rate = None
        if equity > self._peak_equity:
            self._peak_equity = equity
        drawdown_pct = (
            float((self._peak_equity - equity) / self._peak_equity * 100)
            if self._peak_equity > 0
            else 0.0
        )
        pnl_today = float(pnl_today_dec)
        daily_loss_pct = (
            float(-realized_today / self._initial_capital * 100)
            if realized_today < 0
            else 0.0
        )

        recon = self._reconciliation
        account_connected = self._rest_gateway is not None
        reconciled = bool(getattr(recon, "is_reconciled", False)) if recon is not None else False
        real_balances = dict(getattr(recon, "last_balances", {})) if recon is not None else {}

        # p50/p95 latency from rolling window (real samples, never estimated)
        samples = sorted(self._latency_samples) if self._latency_samples else []
        p50_ms = samples[len(samples) // 2] if samples else 0
        p95_ms = samples[max(0, int(len(samples) * 0.95) - 1)] if len(samples) > 1 else (samples[0] if samples else 0)

        # Real portfolio (mark at latest price) — no fabricated values
        portfolio: list[dict[str, object]] = (
            self._trader.get_portfolio() if self._trader is not None else []
        )

        # Wallet value: sum bitkub_balances at real prices when available
        wallet_thb = self._compute_wallet_value_thb(real_balances)

        # State-restoration indicator (was position loaded from SQLite on this boot?)
        state_restored = bool(
            self._trader is not None and getattr(self._trader, "state_loaded", False)
        )
        state_db_path = str(getattr(self.settings, "state_db_path", ""))

        return {
            "mode": self.mode,
            "uptime_sec": uptime_sec,
            "uptime_seconds": uptime_sec,
            "msg_per_sec": msg_per_sec,
            "msg_rate": msg_per_sec,
            "latency_ms": self._latest_latency_ms,
            "latency_precision": "ms",
            "latest_price": str(self._latest_price) if self._latest_price is not None else None,
            "emergency_stopped": self.emergency_stopped,
            "kill_switch": self.emergency_stopped,
            "equity": float(equity),
            "equity_str": str(equity),
            "cash": float(cash),
            "initial_capital": str(self._initial_capital),
            "pnl_today": pnl_today,
            "realized_today": float(realized_today),
            "daily_loss_pct": daily_loss_pct,
            "drawdown_pct": drawdown_pct,
            "positions": positions,
            "win_rate": win_rate,
            "backtest_win_rate": self._win_rate(),
            "wins": wins,
            "losses": losses,
            "trades_closed": trades_closed,
            "treasury_halted": halted,
            # Production-migration honesty: live PRICE feed. The execution
            # engine reflects the REAL configured mode (paper unless the
            # operator armed live behind all four gates) — never hardcoded,
            # so the dashboard cannot claim paper while orders fire live.
            "data_source": "live_bitkub_ws",
            "execution_engine": str(getattr(self.settings, "execution_engine", "paper")),
            # Price-feed health so the dashboard can explain a missing price
            # instead of showing a bare "—".
            "price_feed": {
                "mode": str(getattr(self.settings, "price_feed_mode", "rest")),
                "connected": self._latest_price is not None,
                "last_error": (
                    getattr(self.feed, "last_error", None) if self.feed is not None else None
                ),
            },
            # Phase A: real Bitkub account connected READ-ONLY when a key is set.
            "bitkub_account_connected": account_connected,
            "bitkub_reconciled": reconciled,
            "bitkub_balances": real_balances,
            "account": self.account_status(),
            "portfolio": portfolio,
            "wallet_value_thb": wallet_thb,
            "p50_latency_ms": p50_ms,
            "p95_latency_ms": p95_ms,
            "state_restored": state_restored,
            "state_db_path": state_db_path,
            "execution_warning": self._execution_warning(account_connected),
            "dropped_messages": self._count_dropped_messages(),
            "risk_settings": self.get_risk_settings(),
            "breaker": {
                "is_open": bool(self._circuit_breaker and self._circuit_breaker.is_open),
                "consecutive_losses": (
                    self._circuit_breaker.consecutive_losses
                    if self._circuit_breaker is not None else 0
                ),
                "max_consecutive_losses": (
                    self._circuit_breaker.max_consecutive_losses
                    if self._circuit_breaker is not None else 0
                ),
            },
            "execution_mode": self.get_execution_mode(),
            "live_orders_armed": self._live_orders_armed(),
            "timeline": self._timeline_status(),
            "entry_gate": self._entry_gate_status(),
            "daily": self._daily_status(),
            "news": dict(self.last_news),
            "agents": [self._agent_status(n, a) for n, a in self.agents.items()],
        }

    def _live_orders_armed(self) -> bool:
        """True only when real orders can actually fire RIGHT NOW: live mode +
        all four gates open + a signed gateway wired into the execution gate."""
        engine = str(getattr(self.settings, "execution_engine", "paper"))
        if engine != "live" or not all(self._live_gate_checklist().values()):
            return False
        gate = self.agents.get("risk_gate")
        gw = getattr(gate, "_rest_gateway", None) if gate is not None else None
        return bool(gw is not None and hasattr(gw, "place_bid"))

    def _execution_warning(self, account_connected: bool) -> str:
        """Truthful one-line execution banner for the dashboard."""
        if self._live_orders_armed():
            return (
                "🔴 LIVE: real orders WILL fire on Bitkub — all four safety "
                "gates are open and a signed account is connected."
            )
        prefix = (
            "Real Bitkub account connected READ-ONLY (live wallet). "
            if account_connected
            else "No Bitkub API key configured — paper over live prices. "
        )
        return prefix + (
            "Order firing is SIMULATED; live orders require arming all four "
            "safety gates (execution_engine=live + confirm token + no "
            "KILL_SWITCH + breaker closed) with an account connected."
        )

    def _timeline_status(self) -> dict[str, object]:
        """Timeline Analyst snapshot for the dashboard (win-prob + regime)."""
        tl = self._timeline
        if tl is None:
            return {"available": False}
        return {
            "available": True,
            "p_win": str(getattr(tl, "p_win", "0")),
            "p_win_pct": round(float(getattr(tl, "p_win", 0)) * 100, 1),
            "p_win_samples": int(getattr(tl, "p_win_samples", 0)),
            "regime": str(getattr(tl, "regime", "RANGE")),
            "past_win_rate": getattr(tl, "past_win_rate", None),
            "recent_win_rate": getattr(tl, "recent_win_rate", None),
            "min_p_win": str(self._dec_setting("min_p_win", "0.55")),
            "passes_gate": (
                int(getattr(tl, "p_win_samples", 0)) >= int(getattr(self.settings, "gate_min_samples", 8))
                and Decimal(str(getattr(tl, "p_win", "0"))) >= self._dec_setting("min_p_win", "0.55")
            ),
            "analysis": dict(getattr(tl, "analysis", {})),
        }

    def _entry_gate_status(self) -> dict[str, object]:
        return {
            "enabled": self._entry_gate_enabled,
            "min_p_win": str(self._dec_setting("min_p_win", "0.55")),
            "blocked_by_reason": dict(self._gate_block_reasons),
            "blocked_total": sum(self._gate_block_reasons.values()),
        }

    def _daily_status(self) -> dict[str, object]:
        """Daily trade-budget + profit-target progress (honest: a target, not a
        promise — the market decides whether it is reached)."""
        profit_pct = float(self.daily_profit_pct())
        target = float(self._target_daily_profit_pct)
        return {
            "trades_today": self.trades_today(),
            "max_trades_per_day": self._max_trades_per_day,
            "target_profit_pct": target,
            "profit_pct_today": round(profit_pct, 3),
            "target_reached": profit_pct >= target if target > 0 else False,
            "stop_at_target": self._stop_at_daily_target,
            "note": "เป้าหมาย ไม่ใช่การการันตี — ตลาดเป็นผู้กำหนด",
        }

    def _compute_wallet_value_thb(self, balances: dict[str, str]) -> dict[str, object]:
        """Compute wallet value in THB from real balances + real latest price."""
        if not balances:
            return {"total_thb": None, "entries": [], "price_unavailable": True}
        mark = self._latest_price
        entries: list[dict[str, object]] = []
        total_thb: Decimal | None = Decimal("0") if mark is not None else None
        for sym, amt_str in balances.items():
            try:
                amt = Decimal(amt_str)
            except Exception:
                continue
            if sym == "THB":
                value_thb: Decimal | None = amt
                unavailable = False
            elif mark is not None and sym in ("BTC", "THB_BTC"):
                value_thb = amt * mark
                unavailable = False
            else:
                value_thb = None
                unavailable = True
            entries.append({
                "symbol": sym,
                "qty": amt_str,
                "value_thb": str(value_thb) if value_thb is not None else None,
                "price_unavailable": unavailable,
            })
            if total_thb is not None and value_thb is not None:
                total_thb += value_thb
        return {
            "total_thb": str(total_thb) if total_thb is not None else None,
            "entries": entries,
            "price_unavailable": any(e["price_unavailable"] for e in entries),
        }

    def _count_dropped_messages(self) -> int:
        """Return total dropped messages across all bus implementations."""
        total = 0
        for bus in (self._bus_impl,):
            if bus is not None:
                total += getattr(bus, "dropped_messages", 0)
        return total

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
