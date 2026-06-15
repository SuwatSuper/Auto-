# Layer 2 — Orchestration (runtime/runtime_agents)
"""Agent construction (department + money agents) for PipelineRuntime.

Mixin for PipelineRuntime; see orchestration.runtime for the composed class.
"""
from __future__ import annotations

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
from orchestration.ports.event_bus import EventBus
from orchestration.runtime_base import (
    _TOPIC_ANALYSIS,
    _TOPIC_DECISIONS,
    _TOPIC_DECISIONS_APPROVED,
    _TOPIC_NEWS_RAW,
    _TOPIC_PAPER_EVENTS,
    _TOPIC_PROBABILITY,
    _TOPIC_RESEARCH,
    _TOPIC_RISK,
    _TOPIC_SENTIMENT,
    _TOPIC_SIGNALS,
    _TOPIC_SIM_RESULTS,
    _TOPIC_TIMELINE,
    _TOPIC_TREASURY,
    AgentLike,
    _RuntimeBase,
)


class _AgentsMixin(_RuntimeBase):

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
            min_samples=int(getattr(self.settings, "gate_min_samples", 8)),
        )
        agents["timeline_analyst"] = self._timeline
        money = self._make_money_agents(bus, prices)
        agents.update(money)
        # CEO observer — must be added AFTER money agents so it can see them
        # in self._runtime.status(). It only observes; never executes.
        ceo = CeoAgent(
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
        agents["ceo"] = ceo
        self._ceo = ceo
        # Connect the REAL Bitkub account (read-only) when credentials exist.
        self._reconciliation = None
        self._rest_gateway = None
        self._maybe_build_reconciliation(bus, log)
        if self._reconciliation is not None:
            agents["reconciliation"] = self._reconciliation
        # Hand the (possibly None) live gateway to the execution gate. Without
        # this the gate's _rest_gateway stays None and real orders never fire,
        # even with all four live gates open.
        gate = agents.get("risk_gate")
        if gate is not None and hasattr(gate, "set_rest_gateway"):
            gate.set_rest_gateway(self._rest_gateway)
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
