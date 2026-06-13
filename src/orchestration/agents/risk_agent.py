# Layer 2 — Orchestration (agents/risk_agent)
from __future__ import annotations

import asyncio
import time
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
    ) -> None:
        self._bus = bus
        self._topic_in = topic_in
        self._topic_out = topic_out
        self._log = logger
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
                    peak = Money(amount=Decimal("1000000"), currency=THB)
                    current = Money(amount=Decimal("1000000"), currency=THB)
                    daily_pnl = Money(amount=Decimal(0), currency=THB)
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
