# Layer 2 — Orchestration (agents/treasury_agent)
"""TreasuryAgent — the account guardian (Agent บัญชีคุมเงิน).

Sole authority over cash. The paper trader cannot move one satang without
calling request_open()/settle_close() here. Pure rules live in Layer 1
(domain.portfolio.treasury); this agent owns state, persistence, and events.

PAPER ONLY: this agent manages simulated THB. No live order path exists.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.portfolio.treasury import (
    TreasuryDecision,
    TreasuryLimits,
    review_open,
    should_halt,
)
from domain.trading.paper import ClosedTrade
from orchestration.ports.event_bus import EventBus
from orchestration.ports.state_store import StateStore

_STATE_KEY = "treasury.account.v1"
# Combined atomic snapshot written by the paper trader (position + treasury).
# Must match PaperTraderAgent._SESSION_KEY — the single source of truth on load.
_SESSION_KEY = "paper.session.v1"


class TreasuryAgent:
    """Owns cash / realized PnL / win-loss ledger; vetoes unsafe entries."""

    def __init__(
        self,
        bus: EventBus,
        topic_out: str,
        logger: structlog.BoundLogger,
        limits: TreasuryLimits,
        state_store: StateStore | None = None,
        publish_interval_s: float = 1.0,
        tz_offset_minutes: int = 420,
    ) -> None:
        self._bus = bus
        self._topic_out = topic_out
        self._log = logger.bind(agent="treasury")
        self._limits = limits
        self._store = state_store
        self._publish_interval_s = publish_interval_s
        self._tz = timezone(timedelta(minutes=tz_offset_minutes))

        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0

        self.cash: Decimal = limits.initial_capital
        self.realized_pnl: Decimal = Decimal("0")
        self.realized_today: Decimal = Decimal("0")
        self.fees_today: Decimal = Decimal("0")  # Phase 5: real fees booked today
        self.day_key: str = self._local_day()
        self.wins: int = 0
        self.losses: int = 0
        self.halted: bool = False
        self.approved_count: int = 0
        self.rejected_count: int = 0
        self._session_loaded: bool = False  # set by paper_trader when session key wins

    def set_capital(self, new_capital: Decimal) -> None:
        """Operator reset of the starting capital / money base (PAPER only).

        Rebuilds the survival-floor and daily-loss limits off the new base and
        re-funds cash to it. Intended for use before trading begins.
        """
        self._limits = self._limits.model_copy(update={"initial_capital": new_capital})
        self.cash = new_capital
        self.halted = should_halt(self.realized_today, self.cash, self._limits)

    # ── lifecycle ────────────────────────────────────────────────
    async def start(self) -> None:
        self.running = True
        await self._load()
        self._log.info("treasury_agent.started", cash=str(self.cash))
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                self._rollover_if_new_day()
                await self._publish_status()
                self.msg_count += 1
                try:
                    async with asyncio.timeout(self._publish_interval_s):
                        await asyncio.sleep(self._publish_interval_s)
                except TimeoutError:  # pragma: no cover - sleep < timeout
                    continue
        finally:
            await self._save()
            self._log.info("treasury_agent.stopped")

    async def stop(self) -> None:
        self.running = False

    # ── the money API (called synchronously by the paper trader) ─
    def request_open(
        self, order_cost: Decimal, worst_case: Decimal, open_market_value: Decimal
    ) -> TreasuryDecision:
        """Approve/veto an entry. On approval, RESERVE the full order cost."""
        self._rollover_if_new_day()
        equity = self.cash + open_market_value
        decision = review_open(
            cash=self.cash,
            equity=equity,
            realized_today=self.realized_today,
            order_cost=order_cost,
            worst_case_loss=worst_case,
            limits=self._limits,
            halted=self.halted,
        )
        if decision.approved:
            self.cash -= order_cost
            self.approved_count += 1
        else:
            self.rejected_count += 1
        return decision

    def would_approve(
        self, order_cost: Decimal, worst_case: Decimal, open_market_value: Decimal
    ) -> bool:
        """Non-mutating pre-check: would request_open() approve this entry right
        now? Used to gate a REAL live order BEFORE it is placed, so a halted /
        underfunded / floor-breaching account never spends real money."""
        self._rollover_if_new_day()
        equity = self.cash + open_market_value
        decision = review_open(
            cash=self.cash,
            equity=equity,
            realized_today=self.realized_today,
            order_cost=order_cost,
            worst_case_loss=worst_case,
            limits=self._limits,
            halted=self.halted,
        )
        return decision.approved

    def settle_close(self, trade: ClosedTrade) -> None:
        """Return sale proceeds to cash and book the realized result."""
        self._rollover_if_new_day()
        proceeds = trade.qty * trade.exit_price - trade.exit_fee
        self.cash += proceeds
        self.realized_pnl += trade.pnl
        self.realized_today += trade.pnl
        self.fees_today += trade.entry_fee + trade.exit_fee
        if trade.pnl > 0:
            self.wins += 1
        elif trade.pnl < 0:
            self.losses += 1
        self.halted = should_halt(self.realized_today, self.cash, self._limits)

    def release_reservation(self, amount: Decimal) -> None:
        """Refund a reservation if an approved open could not complete."""
        self.cash += amount

    def update_limits(self, limits: TreasuryLimits) -> None:
        """Replace risk limits live (operator control) and re-evaluate halt."""
        self._limits = limits
        self.halted = should_halt(self.realized_today, self.cash, self._limits)

    @property
    def limits(self) -> TreasuryLimits:
        """Current treasury limits (for dashboard display)."""
        return self._limits

    def win_rate(self) -> float | None:
        total = self.wins + self.losses
        return (self.wins / total) if total else None

    # ── persistence ──────────────────────────────────────────────
    async def _load(self) -> None:
        if self._session_loaded:
            return  # session key already loaded by paper_trader — skip stale own key
        if self._store is None:
            return
        # Prefer the atomic combined session snapshot (paper.session.v1), which
        # the paper trader writes on every open/close. Reading it directly here
        # removes the startup race: treasury and paper_trader now both restore
        # from the SAME authoritative key regardless of task scheduling, so a
        # crash between the two persistence writes can't roll cash back a trade.
        session_raw = await self._store.get(_SESSION_KEY)
        if session_raw is not None:
            try:
                t = orjson.loads(session_raw).get("treasury")
                if t:
                    self.cash = Decimal(str(t["cash"]))
                    self.realized_pnl = Decimal(str(t["realized_pnl"]))
                    self.realized_today = Decimal(str(t["realized_today"]))
                    self.fees_today = Decimal(str(t.get("fees_today", "0")))
                    self.day_key = str(t["day_key"])
                    self.wins = int(t["wins"])
                    self.losses = int(t["losses"])
                    self.halted = bool(t["halted"])
                    self._rollover_if_new_day()
                    self._log.info("treasury_agent.state_restored_from_session", cash=str(self.cash))
                    return
            except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation):
                self._log.warning("treasury_agent.session_corrupt_ignored", exc_info=True)
        raw = await self._store.get(_STATE_KEY)
        if raw is None:
            return
        try:
            data = orjson.loads(raw)
            self.cash = Decimal(str(data["cash"]))
            self.realized_pnl = Decimal(str(data["realized_pnl"]))
            self.realized_today = Decimal(str(data["realized_today"]))
            self.fees_today = Decimal(str(data.get("fees_today", "0")))
            self.day_key = str(data["day_key"])
            self.wins = int(data["wins"])
            self.losses = int(data["losses"])
            self.halted = bool(data["halted"])
            self._rollover_if_new_day()
            self._log.info("treasury_agent.state_restored", cash=str(self.cash))
        except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation):
            self._log.warning("treasury_agent.state_corrupt_ignored", exc_info=True)

    async def _save(self) -> None:
        if self._store is None:
            return
        payload = orjson.dumps(
            {
                "cash": str(self.cash),
                "realized_pnl": str(self.realized_pnl),
                "realized_today": str(self.realized_today),
                "fees_today": str(self.fees_today),
                "day_key": self.day_key,
                "wins": self.wins,
                "losses": self.losses,
                "halted": self.halted,
            }
        )
        await self._store.set(_STATE_KEY, payload)

    async def persist(self) -> None:
        """Public persist hook — trader calls this after every settlement."""
        await self._save()

    # ── internals ────────────────────────────────────────────────
    def _local_day(self) -> str:
        return datetime.now(tz=self._tz).strftime("%Y-%m-%d")

    def _rollover_if_new_day(self) -> None:
        today = self._local_day()
        if today != self.day_key:
            self.day_key = today
            self.realized_today = Decimal("0")
            self.fees_today = Decimal("0")
            if self.cash >= self._limits.floor_equity():
                self.halted = False  # daily halt clears at Thai (UTC+7) midnight; floor halt stays

    async def _publish_status(self) -> None:
        out = orjson.dumps(
            {
                "cash": str(self.cash),
                "realized_pnl": str(self.realized_pnl),
                "realized_today": str(self.realized_today),
                "wins": self.wins,
                "losses": self.losses,
                "halted": self.halted,
            }
        )
        await self._bus.publish(self._topic_out, b"treasury", out)
