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
from collections.abc import Awaitable, Callable
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
from orchestration.agents.paper_persistence import (
    _POSITION_KEY,
    _SESSION_KEY,
    load_state,
    save_state,
    treasury_snapshot,
)
from orchestration.agents.treasury_agent import TreasuryAgent
from orchestration.ports.event_bus import EventBus
from orchestration.ports.state_store import StateStore

__all__ = ["PaperTraderAgent", "TradeParams", "_POSITION_KEY", "_SESSION_KEY"]


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
        max_order_thb: str = "0",
    ) -> None:
        self.risk_per_trade_pct = Decimal(risk_per_trade_pct)
        self.stop_pct = Decimal(stop_pct)
        self.take_profit_pct = Decimal(take_profit_pct)
        self.fee_taker_bps = Decimal(fee_taker_bps)
        self.slippage_bps = Decimal(slippage_bps)
        self.symbol = symbol
        # Hard per-order notional cap in THB (0 = unlimited). Shared by the
        # live order builder so the real order and its paper mirror size to
        # the SAME qty (no divergence when a cap is active).
        self.max_order_thb = Decimal(max_order_thb)


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
        live_close_fn: Callable[[Decimal, Decimal], Awaitable[None]] | None = None,
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
        # Async hook to close the REAL exchange position on a protective exit
        # (stop/TP/trailing/manual/emergency). Without it, a live position would
        # be left open with no stop-loss when the paper bracket fires. The
        # runtime no-ops it unless live orders are armed. Opposite-signal closes
        # are NOT routed here — the execution gate already placed that ask.
        self._live_close_fn = live_close_fn
        # Whether the open position is backed by a REAL order (opened via the
        # live mirror). Only such positions are closed on the exchange.
        self._position_is_live: bool = False

        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0

        self.position: PaperPosition | None = None
        self.mark_price: Decimal | None = None
        # Trailing-stop overlay (lives beside the H1 bracket, NOT inside the
        # frozen PaperPosition — a trailing stop legitimately rises above entry
        # once in profit, which the bracket validator forbids). Only ever
        # ratcheted UP; reset whenever the position changes.
        self.trail_stop: Decimal | None = None
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

    def set_trail_stop(self, new_stop: Decimal) -> bool:
        """Ratchet the trailing stop UP (never down) for the open position.

        Returns True if the stop was raised. No-op when flat, when the new stop
        is not above the current trailing level, or when it is at/above the
        latest mark (a stop must sit below price to be meaningful)."""
        if self.position is None or new_stop <= 0:
            return False
        if self.mark_price is not None and new_stop >= self.mark_price:
            return False
        if self.trail_stop is None or new_stop > self.trail_stop:
            self.trail_stop = new_stop
            return True
        return False

    async def manual_buy(
        self, price: Decimal | None = None, is_live: bool = False
    ) -> tuple[bool, str]:
        """Operator-initiated BUY. Uses the given price or the latest mark.

        Respects the treasury cash check and the single-position rule. Returns
        (ok, message). ``is_live`` marks the position as real-order-backed so its
        protective exits close the real position too (the runtime places the
        real bid before calling this).
        """
        if price is not None:
            self.mark_price = price
        if self.mark_price is None:
            return False, "no price available yet"
        if self.position is not None:
            return False, "a position is already open"
        before = self.entries_opened
        await self._open(self.mark_price, is_live=is_live)
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
            mark = Decimal(str(price_val))
            # NaN/Infinity parse OK but raise on the check_exit comparison below.
            if not mark.is_finite() or mark <= 0:
                return
            self.mark_price = mark
        except (orjson.JSONDecodeError, InvalidOperation, ValueError):
            self._log.warning("paper_trader.price_parse_error", exc_info=True)
            return
        if self.position is not None:
            reason = check_exit(self.position, self.mark_price)
            # Trailing-stop overlay: fires only if the fixed bracket didn't.
            if (
                reason is None
                and self.trail_stop is not None
                and self.mark_price <= self.trail_stop
            ):
                reason = ExitReason.TRAILING_STOP
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
        # A live mirror carries the exchange's actual fill rate so the paper
        # position opens/closes at the SAME price the real order used.
        if data.get("live_mirror") and data.get("price") is not None:
            with contextlib.suppress(InvalidOperation, ValueError):
                self.mark_price = Decimal(str(data.get("price")))
        if signal == "SELL" and self.position is not None and self.mark_price is not None:
            await self._close(self.mark_price, ExitReason.OPPOSITE_SIGNAL)
            return
        if signal == "BUY" and self.position is None and self.mark_price is not None:
            # Phase 5 provenance: carry which strategy/regime/win-prob opened it.
            meta = {
                "strategy_id": str(data.get("source", "")),
                "regime": str(data.get("regime", "")),
                "win_prob_est": str(data.get("win_prob", data.get("p_win", ""))),
            }
            await self._open(
                self.mark_price, is_live=bool(data.get("live_mirror")),
                meta=meta, fill=self._live_fill(data),
            )

    def _live_fill(self, data: dict[str, object]) -> dict[str, Decimal] | None:
        """Parse the exchange's real fill (qty + THB spent) from a live-mirror
        decision. Returns None for paper decisions or when the ack omitted it
        (the open then falls back to risk-based sizing)."""
        if not data.get("live_mirror") or data.get("fill_qty") in (None, ""):
            return None
        try:
            qty = Decimal(str(data.get("fill_qty")))
            thb = Decimal(str(data.get("fill_thb", "0")))
        except (InvalidOperation, ValueError):
            return None
        if not qty.is_finite() or qty <= 0:
            return None
        return {"qty": qty, "thb": thb if (thb.is_finite() and thb > 0) else Decimal("0")}

    # ── open / close ─────────────────────────────────────────────
    async def _open(
        self, signal_price: Decimal, is_live: bool = False,
        meta: dict[str, str] | None = None,
        fill: dict[str, Decimal] | None = None,
    ) -> None:
        p = self._params
        use_fill = fill is not None
        if fill is not None:
            # Real LIVE fill: open at the EXACT qty + rate the exchange reported,
            # so the dashboard position/PnL tracks real money (no re-derivation).
            entry = signal_price  # already the real fill rate (no extra slippage)
            qty = fill["qty"]
        else:
            entry = slip_buy(signal_price, p.slippage_bps)
        stop = entry * (Decimal("1") - p.stop_pct / Decimal("100"))
        if not use_fill:
            qty = size_order(
                cash=self._treasury.cash,
                entry_price=entry,
                stop_price=stop,
                risk_per_trade_pct=p.risk_per_trade_pct,
                fee_bps=p.fee_taker_bps,
                slippage_bps=Decimal("0"),  # entry already slipped above
            )
            # Hard per-order notional cap (THB). Keeps the paper position in lockstep
            # with the live order builder, which applies the same cap.
            cap = getattr(p, "max_order_thb", Decimal("0"))
            if cap > 0 and entry > 0 and qty * entry > cap:
                from decimal import ROUND_DOWN  # noqa: PLC0415
                qty = (cap / entry).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        if qty <= 0:
            self.entries_rejected += 1
            return
        entry_fee = fee_for(qty * entry, p.fee_taker_bps)
        # On a real fill, debit the treasury by the exact THB the exchange spent.
        order_cost = fill["thb"] if (fill is not None and fill["thb"] > 0) else (qty * entry + entry_fee)
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
                # Real fill: pass the exact rate with no extra slippage. Paper:
                # pass the raw signal so the engine applies its slippage model.
                signal_price=entry if use_fill else signal_price,
                stop_pct=p.stop_pct,
                take_profit_pct=p.take_profit_pct,
                fee_bps=p.fee_taker_bps,
                slippage_bps=Decimal("0") if use_fill else p.slippage_bps,
                now_ms=int(time.time() * 1000),
            )
        except ValueError:
            self._treasury.release_reservation(order_cost)
            self._log.error("paper_trader.open_failed_refunded", exc_info=True)
            return
        self.trail_stop = None  # fresh position — no trailing level yet
        self._position_is_live = is_live  # real order backs this position?
        self.entries_opened += 1
        await self._publish_event(
            "FILL",
            {
                "qty": str(self.position.qty),
                "entry": str(self.position.entry_price),
                "stop": str(self.position.stop_price),
                "take_profit": str(self.position.take_profit_price),
                "strategy_id": (meta or {}).get("strategy_id", ""),
                "regime": (meta or {}).get("regime", ""),
                "win_prob_est": (meta or {}).get("win_prob_est", ""),
            },
        )
        await self._save()
        await self._treasury.persist()

    async def _close(self, mark: Decimal, reason: ExitReason) -> None:
        if self.position is None:
            return
        closing_qty = self.position.qty
        was_live = self._position_is_live
        trade = close_position(
            self.position,
            mark,
            reason,
            self._params.fee_taker_bps,
            self._params.slippage_bps,
            int(time.time() * 1000),
        )
        self.position = None
        self.trail_stop = None
        self._position_is_live = False
        self.trades_closed += 1
        self.last_trade = trade
        self._treasury.settle_close(trade)
        # Close the REAL position on the exchange for protective exits. An
        # OPPOSITE_SIGNAL close arrived as a mirrored SELL decision that the
        # execution gate already placed live — routing it again would double-sell.
        if (
            was_live
            and reason is not ExitReason.OPPOSITE_SIGNAL
            and self._live_close_fn is not None
        ):
            try:
                await self._live_close_fn(closing_qty, mark)
            except Exception:  # never let a live-close error corrupt paper state
                self._log.error("paper_trader.live_close_failed", exc_info=True)
        if self._circuit_breaker is not None:
            self._circuit_breaker.record_trade(trade.pnl)
        fee_paid = trade.entry_fee + trade.exit_fee
        await self._publish_event(
            "CLOSE",
            {
                "reason": trade.reason.value,
                "pnl": str(trade.pnl),                       # net (after both fees)
                "exit": str(trade.exit_price),
                "cash": str(self._treasury.cash),
                "entry_fee": str(trade.entry_fee),
                "exit_fee": str(trade.exit_fee),
                "fee_paid": str(fee_paid),                   # real, both legs
                "pnl_gross": str(trade.pnl + fee_paid),      # before fees
                "pnl_net": str(trade.pnl),                   # == target metric
                "slippage_bps": str(self._params.slippage_bps),
            },
        )
        await self._save()
        await self._treasury.persist()

    # ── persistence ──────────────────────────────────────────────
    def _treasury_snapshot(self) -> dict[str, object]:
        return treasury_snapshot(self)

    async def _load(self) -> None:
        await load_state(self)

    async def _save(self) -> None:
        await save_state(self)


    async def _publish_event(self, kind: str, body: dict[str, object]) -> None:
        out = orjson.dumps({"type": kind, "ts_ms": int(time.time() * 1000), **body})
        await self._bus.publish(self._events_topic, b"paper", out)
