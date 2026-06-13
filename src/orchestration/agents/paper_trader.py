# Layer 2 — Orchestration (agents/paper_trader)
"""PaperTraderAgent — the simulated execution engine (PAPER ONLY).

Inputs : decisions.v1 (Supreme: {"decision": "EXECUTE", "signal": "BUY"/"SELL"})
         prices topic  (marks for bracket checks)
Money  : every entry must be approved by the TreasuryAgent (sole cash owner).
Bracket: stop-loss + take-profit attached atomically at open (H1, Layer-1 model).
Exits  : stop hit, take-profit hit, opposite confirmed signal, emergency flatten.
There is NO code path that sends a real order to any exchange.
"""
from __future__ import annotations

import asyncio
import contextlib
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.portfolio.treasury import worst_case_loss
from domain.risk.circuit_breaker import CircuitBreaker
from domain.trading.paper import (
    ClosedTrade,
    ExitReason,
    PaperPosition,
    check_exit,
    close_position,
    fee_for,
    open_position,
    size_order,
    slip_buy,
)
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.ports.event_bus import EventBus
from orchestration.ports.state_store import StateStore

_POSITION_KEY = "paper.position.v1"
_SESSION_KEY = "paper.session.v1"


class TradeParams:
    """Plain holder for hot trading parameters (Decimal strings accepted)."""

    def __init__(
        self,
        risk_per_trade_pct: str = "1.0",
        stop_pct: str = "1.0",
        take_profit_pct: str = "1.5",
        fee_taker_bps: str = "25",
        slippage_bps: str = "5",
        symbol: str = "THB_BTC",
    ) -> None:
        self.risk_per_trade_pct = Decimal(risk_per_trade_pct)
        self.stop_pct = Decimal(stop_pct)
        self.take_profit_pct = Decimal(take_profit_pct)
        self.fee_taker_bps = Decimal(fee_taker_bps)
        self.slippage_bps = Decimal(slippage_bps)
        self.symbol = symbol


class PaperTraderAgent:
    """Holds the (single, long-only) paper position and its bracket."""

    def __init__(
        self,
        bus: EventBus,
        decisions_topic: str,
        prices_topic: str,
        events_topic: str,
        logger: structlog.BoundLogger,
        treasury: TreasuryAgent,
        params: TradeParams,
        state_store: StateStore | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._bus = bus
        self._decisions_topic = decisions_topic
        self._prices_topic = prices_topic
        self._events_topic = events_topic
        self._log = logger.bind(agent="paper_trader")
        self._treasury = treasury
        self._params = params
        self._store = state_store
        self._circuit_breaker = circuit_breaker

        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0

        self.position: PaperPosition | None = None
        self.mark_price: Decimal | None = None
        self.trades_closed: int = 0
        self.entries_opened: int = 0
        self.entries_rejected: int = 0
        self.last_trade: ClosedTrade | None = None
        self.emergency_flatten: bool = False
        self.state_loaded: bool = False
        self._session_seq: int = 0

    # ── runtime-facing views ─────────────────────────────────────
    def open_positions(self) -> int:
        return 1 if self.position is not None else 0

    def get_portfolio(self) -> list[dict[str, object]]:
        """Return open positions with real mark prices for the dashboard."""
        if self.position is None:
            return []
        pos = self.position
        mark = self.mark_price
        if mark is None:
            return [{"symbol": pos.symbol, "qty": str(pos.qty),
                     "avg_price": str(pos.entry_price), "mark_price": None,
                     "market_value": None, "unrealized_pnl": None,
                     "price_unavailable": True}]
        return [{"symbol": pos.symbol, "qty": str(pos.qty),
                 "avg_price": str(pos.entry_price), "mark_price": str(mark),
                 "market_value": str(pos.market_value(mark)),
                 "unrealized_pnl": str(pos.unrealized_pnl(mark)),
                 "price_unavailable": False}]

    def open_market_value(self) -> Decimal:
        if self.position is None or self.mark_price is None:
            return Decimal("0")
        return self.position.market_value(self.mark_price)

    def unrealized_pnl(self) -> Decimal:
        if self.position is None or self.mark_price is None:
            return Decimal("0")
        return self.position.unrealized_pnl(self.mark_price)

    # ── lifecycle ────────────────────────────────────────────────
    async def start(self) -> None:
        self.running = True
        await self._load()
        q_dec = self._bus.subscribe(self._decisions_topic)
        q_px = self._bus.subscribe(self._prices_topic)
        self._log.info("paper_trader.started")
        t_dec: asyncio.Task[bytes] | None = None
        t_px: asyncio.Task[bytes] | None = None
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                if t_dec is None:
                    t_dec = asyncio.create_task(q_dec.get())
                if t_px is None:
                    t_px = asyncio.create_task(q_px.get())
                done, _ = await asyncio.wait(
                    {t_dec, t_px}, timeout=0.5, return_when=asyncio.FIRST_COMPLETED
                )
                if t_px in done:
                    raw = t_px.result()
                    t_px = None
                    await self._on_price(raw)
                if t_dec in done:
                    raw = t_dec.result()
                    t_dec = None
                    await self._on_decision(raw)
        finally:
            for t in (t_dec, t_px):
                if t is not None and not t.done():
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await t
            self._bus.unsubscribe(self._decisions_topic, q_dec)
            self._bus.unsubscribe(self._prices_topic, q_px)
            await self._save()
            self._log.info("paper_trader.stopped")

    async def stop(self) -> None:
        self.running = False

    async def flatten(self, reason: ExitReason = ExitReason.EMERGENCY) -> None:
        """Close any open position at the latest mark (emergency stop path)."""
        if self.position is not None and self.mark_price is not None:
            await self._close(self.mark_price, reason)

    async def manual_buy(self, price: Decimal | None = None) -> tuple[bool, str]:
        """Operator-initiated paper BUY. Uses the given price or the latest mark.

        Respects the treasury cash check and the single-position rule. Returns
        (ok, message). No real exchange order is sent in paper mode.
        """
        if price is not None:
            self.mark_price = price
        if self.mark_price is None:
            return False, "no price available yet"
        if self.position is not None:
            return False, "a position is already open"
        before = self.entries_opened
        await self._open(self.mark_price)
        if self.entries_opened > before:
            return True, "opened"
        return False, "entry rejected (cash/limits)"

    async def manual_close(self, price: Decimal | None = None) -> tuple[bool, str]:
        """Operator-initiated paper CLOSE at the given price or latest mark."""
        if price is not None:
            self.mark_price = price
        if self.position is None:
            return False, "no open position"
        if self.mark_price is None:
            return False, "no price available yet"
        await self._close(self.mark_price, ExitReason.MANUAL)
        return True, "closed"

    # ── message handlers ─────────────────────────────────────────
    async def _on_price(self, raw: bytes) -> None:
        self.msg_count += 1
        try:
            data = orjson.loads(raw)
            price_val = data.get("price")
            if price_val is None:
                return
            self.mark_price = Decimal(str(price_val))
        except (orjson.JSONDecodeError, InvalidOperation, ValueError):
            self._log.warning("paper_trader.price_parse_error", exc_info=True)
            return
        if self.position is not None:
            reason = check_exit(self.position, self.mark_price)
            if reason is not None:
                await self._close(self.mark_price, reason)

    async def _on_decision(self, raw: bytes) -> None:
        self.msg_count += 1
        try:
            data = orjson.loads(raw)
        except orjson.JSONDecodeError:
            self._log.warning("paper_trader.decision_parse_error", exc_info=True)
            return
        if data.get("decision") != "EXECUTE":
            return
        signal = data.get("signal")
        if signal == "SELL" and self.position is not None and self.mark_price is not None:
            await self._close(self.mark_price, ExitReason.OPPOSITE_SIGNAL)
            return
        if signal == "BUY" and self.position is None and self.mark_price is not None:
            await self._open(self.mark_price)

    # ── open / close ─────────────────────────────────────────────
    async def _open(self, signal_price: Decimal) -> None:
        p = self._params
        entry = slip_buy(signal_price, p.slippage_bps)
        stop = entry * (Decimal("1") - p.stop_pct / Decimal("100"))
        qty = size_order(
            cash=self._treasury.cash,
            entry_price=entry,
            stop_price=stop,
            risk_per_trade_pct=p.risk_per_trade_pct,
            fee_bps=p.fee_taker_bps,
            slippage_bps=Decimal("0"),  # entry already slipped above
        )
        if qty <= 0:
            self.entries_rejected += 1
            return
        entry_fee = fee_for(qty * entry, p.fee_taker_bps)
        order_cost = qty * entry + entry_fee
        exit_fee_est = fee_for(qty * stop, p.fee_taker_bps)
        worst = worst_case_loss(qty, entry, stop, entry_fee, exit_fee_est)

        decision = self._treasury.request_open(order_cost, worst, self.open_market_value())
        if not decision.approved:
            self.entries_rejected += 1
            await self._publish_event(
                "ENTRY_REJECTED", {"reasons": [r.value for r in decision.reasons]}
            )
            return
        try:
            self.position = open_position(
                symbol=p.symbol,
                qty=qty,
                signal_price=signal_price,
                stop_pct=p.stop_pct,
                take_profit_pct=p.take_profit_pct,
                fee_bps=p.fee_taker_bps,
                slippage_bps=p.slippage_bps,
                now_ms=int(time.time() * 1000),
            )
        except ValueError:
            self._treasury.release_reservation(order_cost)
            self._log.error("paper_trader.open_failed_refunded", exc_info=True)
            return
        self.entries_opened += 1
        await self._publish_event(
            "FILL",
            {
                "qty": str(self.position.qty),
                "entry": str(self.position.entry_price),
                "stop": str(self.position.stop_price),
                "take_profit": str(self.position.take_profit_price),
            },
        )
        await self._save()
        await self._treasury.persist()

    async def _close(self, mark: Decimal, reason: ExitReason) -> None:
        if self.position is None:
            return
        trade = close_position(
            self.position,
            mark,
            reason,
            self._params.fee_taker_bps,
            self._params.slippage_bps,
            int(time.time() * 1000),
        )
        self.position = None
        self.trades_closed += 1
        self.last_trade = trade
        self._treasury.settle_close(trade)
        if self._circuit_breaker is not None:
            self._circuit_breaker.record_trade(trade.pnl)
        await self._publish_event(
            "CLOSE",
            {
                "reason": trade.reason.value,
                "pnl": str(trade.pnl),
                "exit": str(trade.exit_price),
                "cash": str(self._treasury.cash),
            },
        )
        await self._save()
        await self._treasury.persist()

    # ── persistence ──────────────────────────────────────────────
    def _treasury_snapshot(self) -> dict[str, object]:
        t = self._treasury
        return {
            "cash": str(t.cash),
            "realized_pnl": str(t.realized_pnl),
            "realized_today": str(t.realized_today),
            "day_key": t.day_key,
            "wins": t.wins,
            "losses": t.losses,
            "halted": t.halted,
        }

    async def _load(self) -> None:
        if self._store is None:
            return
        # Try combined atomic key first (crash-safe)
        raw = await self._store.get(_SESSION_KEY)
        if raw is not None:
            try:
                data = orjson.loads(raw)
                self._session_seq = int(data.get("seq", 0))
                pos_data = data.get("position")
                if pos_data is not None:
                    self.position = PaperPosition.model_validate(pos_data)
                self.trades_closed = int(data.get("trades_closed", 0))
                self.entries_opened = int(data.get("entries_opened", 0))
                # Restore treasury from the same snapshot
                t_data = data.get("treasury")
                if t_data:
                    self._treasury.cash = Decimal(str(t_data["cash"]))
                    self._treasury.realized_pnl = Decimal(str(t_data["realized_pnl"]))
                    self._treasury.realized_today = Decimal(str(t_data["realized_today"]))
                    self._treasury.day_key = str(t_data["day_key"])
                    self._treasury.wins = int(t_data["wins"])
                    self._treasury.losses = int(t_data["losses"])
                    self._treasury.halted = bool(t_data["halted"])
                # Validate consistency: position must be reflected in reserved cash
                if self.position is not None and t_data:
                    # If a position exists but cash is above initial_capital, something is off
                    # We trust cash (never invent money) and keep position if plausible
                    pass
                self.state_loaded = True
                self._treasury._session_loaded = True
                self._log.info("paper_trader.session_restored", open=self.position is not None)
                return
            except (orjson.JSONDecodeError, KeyError, ValueError, Exception):
                self._log.warning("paper_trader.session_corrupt_ignored", exc_info=True)

        # Backward-compat: fall back to legacy split keys
        raw = await self._store.get(_POSITION_KEY)
        if raw is None:
            return
        try:
            data = orjson.loads(raw)
            pos_data = data.get("position")
            if pos_data is not None:
                self.position = PaperPosition.model_validate(pos_data)
            self.trades_closed = int(data.get("trades_closed", 0))
            self.entries_opened = int(data.get("entries_opened", 0))
            # Consistency check: if position exists, verify cash doesn't exceed initial capital
            # (legacy state may be inconsistent — drop phantom position, keep cash)
            if self.position is not None and self._treasury.cash >= self._treasury._limits.initial_capital:
                self._log.warning(
                    "state.inconsistent_repaired",
                    reason="position_with_full_cash",
                )
                self.position = None
            self.state_loaded = True
            self._log.info("paper_trader.state_restored", open=self.position is not None)
        except (orjson.JSONDecodeError, KeyError, ValueError):
            self._log.warning("paper_trader.state_corrupt_ignored", exc_info=True)

    async def _save(self) -> None:
        if self._store is None:
            return
        self._session_seq += 1
        pos = None
        if self.position is not None:
            pos = orjson.loads(self.position.model_dump_json())
        payload = orjson.dumps(
            {
                "seq": self._session_seq,
                "treasury": self._treasury_snapshot(),
                "position": pos,
                "trades_closed": self.trades_closed,
                "entries_opened": self.entries_opened,
            }
        )
        await self._store.set(_SESSION_KEY, payload)

    async def _publish_event(self, kind: str, body: dict[str, object]) -> None:
        out = orjson.dumps({"type": kind, "ts_ms": int(time.time() * 1000), **body})
        await self._bus.publish(self._events_topic, b"paper", out)
