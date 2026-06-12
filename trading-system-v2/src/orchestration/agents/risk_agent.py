# Layer 2 — Orchestration (agents/risk_agent)
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.risk.rules import RiskDecision, RiskLimits, evaluate
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
            max_position_size=Decimal("1"),
            max_daily_loss=Decimal("10000"),
            max_drawdown_pct=Decimal("20"),
            max_order_size=Decimal("0.5"),
        )
        self.running = False
        self.msg_count = 0
        self.rejected_count = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("risk_agent.started")
        try:
            while self.running:
                try:
                    async with asyncio.timeout(0.5):
                        raw = await queue.get()
                except TimeoutError:
                    continue
                self.msg_count += 1
                try:
                    data = orjson.loads(raw)
                    order_size = Decimal(str(data.get("size", "0")))
                    eval_result = evaluate(order_size, self._limits)
                    if eval_result.decision == RiskDecision.REJECT:
                        self.rejected_count += 1
                    out = orjson.dumps({
                        "decision": eval_result.decision.value,
                        "reason": eval_result.reason,
                        "adjusted_size": str(eval_result.adjusted_size) if eval_result.adjusted_size else None,
                    })
                    await self._bus.publish(self._topic_out, b"risk", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("risk_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("risk_agent.stopped")

    async def stop(self) -> None:
        self.running = False
