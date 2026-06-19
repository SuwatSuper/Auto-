# Layer 2 — Orchestration (runtime_base)
"""Shared state + cross-mixin contract for PipelineRuntime.

``_RuntimeBase`` declares every instance attribute the runtime owns plus stub
signatures for the methods that are called across mixin boundaries, so each
behaviour mixin type-checks under --strict in isolation. The real bodies live in
the mixins / core class; these stubs are always overridden via the MRO.
"""
from __future__ import annotations

import asyncio
import dataclasses
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

import structlog
from pydantic import SecretStr

from domain.analytics.source_weights import SourcePerformance
from domain.analytics.swarm_meta import SwarmMetaLearner
from domain.risk.circuit_breaker import CircuitBreaker
from orchestration.agents.ceo_agent import CeoAgent
from orchestration.agents.learning import Learner
from orchestration.agents.paper_trader import PaperTraderAgent, TradeParams
from orchestration.agents.reconciliation_agent import ReconciliationAgent
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.ports.clock import Clock
from orchestration.ports.event_bus import EventBus
from orchestration.ports.event_store import EventStore
from orchestration.ports.price_feed import PriceFeed
from orchestration.ports.state_store import StateStore
from orchestration.supervisors.price_supervisor import PriceSupervisor

# Department topics (Layer-2 routing table).
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
_TOPIC_ANALYSIS = "analysis.v1"


class SettingsView(Protocol):
    """The mutable settings surface the runtime writes to directly (live wiring).

    Everything else is read defensively via ``getattr``; this protocol exists so
    the few real attribute *assignments* type-check without suppressions. The
    concrete ``infrastructure.config.Settings`` satisfies it structurally."""

    bitkub_api_key: SecretStr
    bitkub_api_secret: SecretStr
    execution_engine: str
    live_trading_confirm: str
    min_p_win: str
    # Disarmed when the operator sets risk %/trade by hand, so their exact value
    # is not re-clamped by the Kelly auto-sizer.
    kelly_sizing_enabled: bool


class Notifier(Protocol):
    """Layer-2 alert port (infrastructure.alerts.AlertNotifier satisfies it)."""

    async def send(self, message: str, level: str = ...) -> bool: ...


class NewsSource(Protocol):
    """Layer-2 news port (infrastructure.gateway.NewsRssFeed satisfies it)."""

    async def fetch_headlines(self) -> list[str]: ...


class AgentLike(Protocol):
    """Minimal contract every runtime agent satisfies (Layer-2 port)."""

    running: bool
    msg_count: int
    last_beat_ms: int

    async def start(self) -> None: ...

    async def stop(self) -> None: ...


@dataclasses.dataclass(frozen=True)
class RuntimeDeps:
    """Frozen dataclass of ports + factories for PipelineRuntime."""

    bus: EventBus
    clock: Clock
    state_store: StateStore
    event_store: EventStore
    feed_factory: Callable[[str], PriceFeed]
    prices_topic: str = "prices.thb_btc.v1"


class _RuntimeBase:
    """Attribute + cross-mixin method contract (see module docstring)."""

    settings: SettingsView
    logger: structlog.BoundLogger
    _deps: RuntimeDeps | None
    _bus_impl: EventBus | None
    mode: str
    feed: PriceFeed | None
    supervisor: PriceSupervisor | None
    supervisor_task: asyncio.Task[None] | None
    agents: dict[str, AgentLike]
    agent_tasks: dict[str, asyncio.Task[None]]
    start_time_ms: int
    msg_count_window: deque[int]
    emergency_stopped: bool
    _latest_price: Decimal | None
    _latest_latency_ms: int
    _last_price_wall_ms: int
    _price_feed_stale_restarts: int
    _latency_samples: deque[int]
    _msg_count_current: int
    _window_task: asyncio.Task[None] | None
    _initial_capital: Decimal
    _peak_equity: Decimal
    _treasury: TreasuryAgent | None
    _trader: PaperTraderAgent | None
    _ceo: CeoAgent | None
    _state_store: StateStore | None
    _watchdog_task: asyncio.Task[None] | None
    _coach_task: asyncio.Task[None] | None
    _news_task: asyncio.Task[None] | None
    _memory_task: asyncio.Task[None] | None
    _news_source: NewsSource | None
    last_news: dict[str, object]
    restart_counts: dict[str, int]
    crashed_agents: dict[str, str]
    _agent_next_retry: dict[str, float]
    _agents_given_up: set[str]
    _learners: dict[str, Learner]
    _circuit_breaker: CircuitBreaker | None
    _manual_order_lock: asyncio.Lock | None
    _trade_params: TradeParams | None
    _control_audit: list[dict[str, object]]
    _alert_tasks: set[asyncio.Task[bool]]
    _max_deployable_thb: Decimal
    _max_single_order_thb: Decimal
    _notifier: Notifier | None
    _rest_gateway: object | None
    _reconciliation: ReconciliationAgent | None
    _timeline: object | None
    _entry_gate_enabled: bool
    _max_trades_per_day: int
    _target_daily_profit_pct: Decimal
    _stop_at_daily_target: bool
    _trades_day_key: str
    _entries_baseline: int
    _gate_block_reasons: dict[str, int]
    # Task 1: bus-fed confluence cache (the entry gate's only input source).
    _confluence: dict[str, object]
    _division_bias: dict[str, float]
    _confluence_task: asyncio.Task[None] | None
    # Task 2: dynamic-weighting feedback (paper.events → per-source win-rate).
    _source_perf: SourcePerformance
    _weighting_task: asyncio.Task[None] | None
    # Task 3: shared regime-aware meta-learner for the 150-agent grid.
    _swarm_meta: SwarmMetaLearner

    def _ensure_bus(self) -> EventBus:
        raise NotImplementedError

    def _ensure_state_store(self) -> StateStore | None:
        raise NotImplementedError

    def _dec_setting(self, name: str, default: str) -> Decimal:
        raise NotImplementedError

    def _make_agents(self) -> dict[str, AgentLike]:
        raise NotImplementedError

    async def start_agent(self, name: str) -> None:
        raise NotImplementedError

    async def stop_agent(self, name: str) -> None:
        raise NotImplementedError

    def _learner_for(self, name: str, agent: AgentLike) -> Learner:
        raise NotImplementedError

    def _risk_equity_state(self) -> tuple[Decimal, Decimal, Decimal]:
        raise NotImplementedError

    def _win_rate(self) -> float | None:
        raise NotImplementedError

    def get_risk_settings(self) -> dict[str, str]:
        raise NotImplementedError

    async def update_risk_settings(
        self, patch: dict[str, object], *, from_restore: bool = False
    ) -> tuple[bool, dict[str, object]]:
        raise NotImplementedError

    def _schedule_alert(self, message: str, level: str = "warning") -> None:
        raise NotImplementedError

    def trades_today(self) -> int:
        raise NotImplementedError

    def daily_profit_pct(self) -> Decimal:
        raise NotImplementedError

    def _trade_budget(self) -> bool:
        raise NotImplementedError

    def _entry_gate(self, data: dict[str, object]) -> tuple[bool, list[str]]:
        raise NotImplementedError

    def _confluence_dec(self, key: str, default: str = "0") -> Decimal:
        raise NotImplementedError

    def _confluence_int(self, key: str, default: int = 0) -> int:
        raise NotImplementedError

    async def _live_close(self, qty: object, rate: object) -> None:
        raise NotImplementedError

    def _build_live_order(self, data: dict[str, object]) -> dict[str, str] | None:
        raise NotImplementedError

    def account_status(self) -> dict[str, object]:
        raise NotImplementedError

    def _live_gate_checklist(self) -> dict[str, bool]:
        raise NotImplementedError

    def get_execution_mode(self) -> dict[str, object]:
        raise NotImplementedError

    def _record_control(self, action: str, detail: dict[str, object]) -> None:
        raise NotImplementedError

    async def _persist_controls(self, settings: dict[str, str]) -> None:
        raise NotImplementedError

    async def _persist_breaker(self) -> None:
        raise NotImplementedError

    def _schedule_breaker_persist(self) -> None:
        raise NotImplementedError

    async def _restore_breaker(self) -> None:
        raise NotImplementedError

    async def _persist_memories(self) -> None:
        raise NotImplementedError

    async def _restore_memories(self) -> None:
        raise NotImplementedError

    async def _memory_loop(self) -> None:
        raise NotImplementedError

    async def _news_loop(self) -> None:
        raise NotImplementedError

    def write_daily_summary(self) -> dict[str, object]:
        raise NotImplementedError

    async def load_controls(self) -> None:
        raise NotImplementedError

    def _live_orders_armed(self) -> bool:
        raise NotImplementedError

    # ── External runtime contract (agents receive ``self`` as a RuntimeView) ──
    def status(self) -> dict[str, object]:
        raise NotImplementedError

    def trip_breaker(self, reason: str = "MANUAL") -> dict[str, object]:
        raise NotImplementedError

    async def send_alert(self, message: str, level: str = "info") -> bool:
        raise NotImplementedError
