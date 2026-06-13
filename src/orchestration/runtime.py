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
from typing import Protocol

import orjson
import structlog

from domain.portfolio.treasury import TreasuryLimits
from domain.risk.circuit_breaker import CircuitBreaker
from orchestration.agents.ceo_agent import CeoAgent
from orchestration.agents.entry_exit import EntryExitAgent
from orchestration.agents.historical_research import HistoricalResearchAgent
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
        self.restart_counts: dict[str, int] = {}
        self.crashed_agents: dict[str, str] = {}
        # Circuit breaker — shared between ExecutionAgent and paper trader close
        self._circuit_breaker: CircuitBreaker | None = None
        # Live Bitkub account connection (read-only reconciliation). Built only
        # when BITKUB_API_KEY is present; otherwise the system runs exactly as
        # before (paper execution over the live price feed).
        self._rest_gateway: object | None = None
        self._reconciliation: object | None = None

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
            "risk_management": RiskAgent(bus, _TOPIC_DECISIONS, _TOPIC_RISK, log),
            "probability_lab": ProbabilityAgent(bus, prices, _TOPIC_PROBABILITY, log),
            "research_dept": HistoricalResearchAgent(bus, prices, _TOPIC_RESEARCH, log),
            "execution_agent": SimulationAgent(bus, prices, _TOPIC_SIM_RESULTS, log),
            "supreme_commander": SupremeAgent(bus, _TOPIC_SIGNALS, _TOPIC_DECISIONS, log),
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
            ),
        }
        money = self._make_money_agents(bus, prices)
        agents.update(money)
        # CEO observer — must be added AFTER money agents so it can see them
        # in self._runtime.status(). It only observes; never executes.
        agents["ceo"] = CeoAgent(
            bus=bus, logger=log, runtime=self,
            agent_roles={
                "market_analyst":    "Generates EMA-cross entry/exit signals",
                "news_intelligence": "Aggregates news sentiment",
                "risk_management":   "Vetoes orders breaching risk limits",
                "probability_lab":   "RSI-based probability scoring",
                "research_dept":     "Rolling historical statistics",
                "execution_agent":   "Rolling paper backtest with fees+slippage",
                "supreme_commander": "Final signal arbiter",
                "treasury":          "Sole owner of cash and PnL ledger",
                "paper_trader":      "Bracketed paper execution engine",
                "ceo":               "Executive observer / audit trail",
            },
        )
        self._ceo = agents["ceo"]
        # Connect the REAL Bitkub account (read-only) when credentials exist.
        self._reconciliation = None
        self._rest_gateway = None
        self._maybe_build_reconciliation(bus, log)
        if self._reconciliation is not None:
            agents["reconciliation"] = self._reconciliation  # type: ignore[assignment,unused-ignore]
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
        )
        self._treasury = treasury
        self._trader = trader
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
            # feed in this build. If Bitkub WS is unreachable the supervisor
            # logs the failure and the dashboard surfaces "DATA UNAVAILABLE".
            if mode != "live":
                raise ValueError(
                    f"only 'live' mode is supported (got {mode!r}); "
                    "simulator/paper/demo modes were removed in the Production Migration"
                )
            from infrastructure.gateway.bitkub_ws import BitkubWebSocketGateway  # noqa: PLC0415

            feed = BitkubWebSocketGateway(ws_url)
        self.feed = feed

        counting_bus = _CountingBusProxy(bus, self)
        self.supervisor = PriceSupervisor(feed, counting_bus, topic, self.logger)
        self.supervisor_task = asyncio.create_task(self.supervisor.run())
        self._window_task = asyncio.create_task(self._tick_window())

        self.agents = self._make_agents()
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

    async def stop(self) -> None:
        """Stop all agents, supervisor, and background tasks."""
        if self._watchdog_task and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watchdog_task
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
                self.agent_tasks.pop(name, None)
                agent.running = False
                await self.start_agent(name)

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
        return status

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
            "daily_loss_pct": daily_loss_pct,
            "drawdown_pct": drawdown_pct,
            "positions": positions,
            "win_rate": win_rate,
            "backtest_win_rate": self._win_rate(),
            "wins": wins,
            "losses": losses,
            "trades_closed": trades_closed,
            "treasury_halted": halted,
            # Production-migration honesty: live PRICE feed, paper EXECUTION engine.
            # The dashboard renders a banner from this dict — do not remove.
            "data_source": "live_bitkub_ws",
            "execution_engine": "paper",
            # Phase A: real Bitkub account connected READ-ONLY when a key is set.
            "bitkub_account_connected": account_connected,
            "bitkub_reconciled": reconciled,
            "bitkub_balances": real_balances,
            "portfolio": portfolio,
            "wallet_value_thb": wallet_thb,
            "p50_latency_ms": p50_ms,
            "p95_latency_ms": p95_ms,
            "state_restored": state_restored,
            "state_db_path": state_db_path,
            "execution_warning": (
                "Real Bitkub account connected READ-ONLY (live wallet). "
                if account_connected
                else "No Bitkub API key configured — paper over live prices. "
            )
            + "Order firing is still SIMULATED; enabling live orders is a "
            "separate, tested step behind the 4 safety gates.",
            "dropped_messages": self._count_dropped_messages(),
            "agents": [self._agent_status(n, a) for n, a in self.agents.items()],
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
