# Layer 2 — Orchestration (agents/historical_research)
"""HistoricalResearchAgent (research_dept) — rolling price-history statistics.

Task 1: previously this agent only republished a price *count*, which is not a
quantifiable confluence input. It now computes, from its real rolling window,
where the current price sits relative to recent history:

  • ``price_pctl`` — the fraction of the window at or below the current price
    (0 = cheapest in window, 1 = most expensive). A BUY near the very top of the
    range is chasing; the entry gate can veto that (PRICE_OVEREXTENDED).
  • ``pct_from_mean`` — current price's distance from the rolling mean, in %.

Both are MEASURED from real ticks — no fabricated values, no LLM.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from orchestration.ports.event_bus import EventBus

# Need a meaningful window before a percentile/mean read is trustworthy.
_MIN_SAMPLES = 30


class HistoricalResearchAgent:
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
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self._prices: list[Decimal] = []
        # Last published read (also surfaced on the dashboard / status).
        self.price_pctl: Decimal | None = None
        self.pct_from_mean: Decimal | None = None
        self.detail = ""

    def _compute(self, price: Decimal) -> tuple[Decimal | None, Decimal | None]:
        """Percentile of ``price`` within the window + % distance from its mean.

        Returns (None, None) until the window holds at least ``_MIN_SAMPLES``
        ticks so the gate never trusts a number measured from too little data.
        """
        window = self._prices
        if len(window) < _MIN_SAMPLES:
            return None, None
        at_or_below = sum(1 for p in window if p <= price)
        pctl = Decimal(at_or_below) / Decimal(len(window))
        mean = sum(window) / Decimal(len(window))
        pct_from_mean = (
            (price - mean) / mean * Decimal("100") if mean > 0 else Decimal("0")
        )
        return pctl, pct_from_mean

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("historical_research_agent.started")
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
                    if price <= 0:
                        continue
                    self._prices.append(price)
                    if len(self._prices) > 1000:
                        self._prices = self._prices[-1000:]
                    pctl, pct_from_mean = self._compute(price)
                    self.price_pctl = pctl
                    self.pct_from_mean = pct_from_mean
                    # Honest: until the window is deep enough, publish a "no read"
                    # percentile (−1) so the gate's research veto stays inert.
                    out = orjson.dumps({
                        "price_count": len(self._prices),
                        "latest_price": str(price),
                        "price_pctl": str(pctl) if pctl is not None else "-1",
                        "pct_from_mean": str(pct_from_mean) if pct_from_mean is not None else "0",
                        "samples": len(self._prices),
                    })
                    await self._bus.publish(self._topic_out, b"history", out)
                    if pctl is not None and pct_from_mean is not None:
                        self.detail = (
                            f"ราคาอยู่อันดับ {float(pctl) * 100:.0f}% ของช่วง "
                            f"({len(self._prices)} ไม้) · ห่างค่าเฉลี่ย {float(pct_from_mean):+.2f}%"
                        )
                    else:
                        self.detail = f"กำลังเก็บสถิติ ({len(self._prices)}/{_MIN_SAMPLES} ไม้)"
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("historical_research_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("historical_research_agent.stopped")

    async def stop(self) -> None:
        self.running = False
