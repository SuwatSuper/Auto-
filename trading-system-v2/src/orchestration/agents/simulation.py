# Layer 2 — Orchestration (agents/simulation)
from __future__ import annotations

import asyncio
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.backtest.engine import run_backtest
from domain.strategy.ema_cross import EmaCrossStrategy
from orchestration.ports.event_bus import EventBus


class SimulationAgent:
    def __init__(
        self,
        bus: EventBus,
        topic_in: str,
        topic_out: str,
        logger: structlog.BoundLogger,
    ) -> None:
        self._bus = bus
        self._topic_in = topic_in
        self._topic_out = topic_out
        self._log = logger
        self._prices: list[tuple[int, Decimal]] = []
        self.running = False
        self.msg_count = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("simulation_agent.started")
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
                    price = Decimal(str(data.get("price", "0")))
                    ts_ms = int(data.get("ts_ms", 0))
                    self._prices.append((ts_ms, price))
                    if len(self._prices) >= 50:
                        strategy = EmaCrossStrategy()
                        report = run_backtest(
                            strategy,
                            self._prices[-50:],
                            Decimal("100000"),
                            Decimal("0.01"),
                        )
                        out = orjson.dumps({
                            "total_trades": report.total_trades,
                            "win_rate": str(report.win_rate),
                            "expectancy": str(report.expectancy),
                        })
                        await self._bus.publish(self._topic_out, b"simulation", out)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("simulation_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("simulation_agent.stopped")

    async def stop(self) -> None:
        self.running = False
