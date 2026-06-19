# Layer 2 — Orchestration (agents/simulation)
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.backtest.engine import FeeModel, SlippageModel, run_backtest
from domain.risk.rules import RiskLimits
from domain.shared.money import THB, Money
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
        self.last_beat_ms: int = 0
        # Last computed rolling-backtest report (real prices, fees+slippage
        # included). None until the first 50-tick window completes.
        self.last_win_rate: str | None = None
        self.last_total_trades: int = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("simulation_agent.started")
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
                    price = Decimal(str(data.get("price", "0")))
                    ts_ms = int(data.get("ts_ms", 0))
                    self._prices.append((ts_ms, price))
                    # Keep only the rolling window the backtest actually uses.
                    # Without this the list grows by one entry per tick forever
                    # (~60 MB over a 10-day run) — the only unbounded buffer on
                    # the live price path. The backtest reads self._prices[-50:].
                    if len(self._prices) > 50:
                        self._prices = self._prices[-50:]
                    if len(self._prices) >= 50:
                        strategy = EmaCrossStrategy()
                        limits = RiskLimits(
                            max_order_qty=Decimal("1"),
                            max_position_qty=Decimal("1"),
                            max_daily_loss=Money(amount=Decimal("100000"), currency=THB),
                            max_drawdown_pct=Decimal("20"),
                            kill_switch=False,
                        )
                        report = run_backtest(
                            prices=self._prices[-50:],
                            strategy=strategy,
                            limits=limits,
                            fees=FeeModel(taker_bps=Decimal("25")),
                            slippage=SlippageModel(slip_bps=Decimal("5")),
                            initial_cash=Money(amount=Decimal("100000"), currency=THB),
                            order_qty=Decimal("0.01"),
                        )
                        self.last_win_rate = str(report.win_rate)
                        self.last_total_trades = len(report.trades)
                        out = orjson.dumps({
                            "total_trades": len(report.trades),
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
