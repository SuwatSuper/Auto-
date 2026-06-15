# Layer 2 — Orchestration (agents/risk_agent)
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.portfolio.models import Account
from domain.risk.rules import RiskLimits, evaluate
from domain.shared.money import THB, Money
from domain.trading.orders import Order, OrderStatus, Side
from orchestration.ports.event_bus import EventBus


class RiskAgent:
    def __init__(
        self,
        bus: EventBus,
        topic_in: str,
        topic_out: str,
        logger: structlog.BoundLogger,
        limits: RiskLimits | None = None,
        equity_fn: Callable[[], tuple[Decimal, Decimal, Decimal]] | None = None,
    ) -> None:
        self._bus = bus
        self._topic_in = topic_in
        self._topic_out = topic_out
        self._log = logger
        # Returns REAL (peak_equity, current_equity, daily_pnl) so the drawdown /
        # daily-loss limbs vet against live treasury state, not a constant.
        self._equity_fn = equity_fn
        self._limits = limits or RiskLimits(
            max_order_qty=Decimal("1"),
            max_position_qty=Decimal("1"),
            max_daily_loss=Money(amount=Decimal("100000"), currency=THB),
            max_drawdown_pct=Decimal("20"),
            kill_switch=False,
        )
        self._account = Account(
            account_id="risk_agent",
            cash=Money(amount=Decimal("1000000"), currency=THB),
            realized_pnl=Money(amount=Decimal(0), currency=THB),
        )
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self.rejected_count = 0
        # Surfaced on the dashboard via _agent_status (.detail) so this ADVISORY
        # monitor's verdict is visible, not published into the void. The binding
        # rails live in ExecutionAgent + TreasuryAgent; this is a second opinion.
        self.detail = "ที่ปรึกษาความเสี่ยง: ยังไม่มีคำสั่งให้ตรวจ"

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("risk_agent.started")
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    async with asyncio.timeout(0.5):
                        raw = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data = orjson.loads(raw)
                    order_qty = Decimal(str(data.get("qty", "0.01")))
                    order = Order(
                        order_id=f"risk-{self.msg_count:06d}",
                        symbol="THB_BTC",
                        side=Side.BUY,
                        qty=order_qty,
                        limit_price=None,
                        status=OrderStatus.NEW,
                        created_ms=0,
                    )
                    # Real account state when wired; otherwise the honest
                    # no-movement baseline (peak == current, daily_pnl == 0),
                    # never a fabricated drawdown.
                    if self._equity_fn is not None:
                        peak_d, current_d, daily_d = self._equity_fn()
                    else:
                        peak_d = current_d = self._account.cash.amount
                        daily_d = Decimal(0)
                    peak = Money(amount=peak_d, currency=THB)
                    current = Money(amount=current_d, currency=THB)
                    daily_pnl = Money(amount=daily_d, currency=THB)
                    decision = evaluate(
                        order=order,
                        account=self._account,
                        positions={},
                        limits=self._limits,
                        daily_pnl=daily_pnl,
                        peak_equity=peak,
                        current_equity=current,
                    )
                    if not decision.approved:
                        self.rejected_count += 1
                    last = ", ".join(r.value for r in decision.reasons)
                    self.detail = (
                        f"ที่ปรึกษาความเสี่ยง (advisory): ตรวจ {self.msg_count} รายการ · "
                        f"ติง {self.rejected_count} ครั้ง"
                        + (f" · ล่าสุด: {last}" if last else "")
                    )
                    # Advisory verdict stream (event record); the visible signal
                    # is .detail / rejected_count above.
                    out = orjson.dumps({
                        "approved": decision.approved,
                        "reasons": [r.value for r in decision.reasons],
                    })
                    await self._bus.publish(self._topic_out, b"risk", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("risk_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("risk_agent.stopped")

    async def stop(self) -> None:
        self.running = False
