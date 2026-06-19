# Layer 2 — Orchestration (agents/entry_exit)
from __future__ import annotations

import asyncio
import time
from decimal import Decimal, InvalidOperation

import orjson
import structlog

from domain.analytics.indicators import ema
from domain.strategy.base import SignalAction, StrategyContext
from domain.strategy.ema_cross import EmaCrossStrategy
from domain.strategy.multi_indicator import (
    expanded_confluence_signal,
    multi_indicator_signal,
)
from orchestration.agents.learning import Learner
from orchestration.ports.event_bus import EventBus


class EntryExitAgent:
    """EMA-cross entry/exit signals — now self-learning.

    Every emitted signal is recorded and later graded against the REAL price
    that followed (Learner), giving a measured hit-rate. A confirmation filter
    (`_min_gap_pct`) self-tunes from that hit-rate: lose too often → demand a
    wider EMA gap before acting; win often → relax it. This makes the primary
    signal agent adapt instead of firing every raw cross.
    """

    def __init__(
        self,
        bus: EventBus,
        topic_in: str,
        topic_out: str,
        logger: structlog.BoundLogger,
        multi_indicator: bool = True,
        expanded: bool = False,
        adapt_every: int = 8,
    ) -> None:
        self._bus = bus
        self._topic_in = topic_in
        self._topic_out = topic_out
        self._log = logger
        self._strategy = EmaCrossStrategy()
        # When True, entries lean on a multi-indicator confluence (EMA momentum +
        # trend + MACD + RSI) over the price history, not just a single EMA cross.
        self._multi_indicator = multi_indicator
        # When True, the confluence widens from 4 lines to the 9-line expanded
        # vocabulary (adds SMA cross, WMA/HMA slope, Bollinger bias, RSI-based MA)
        # so the analyst reasons over more of what it now knows.
        self._expanded = expanded
        # How many graded (resolved) trades of experience to gather before the
        # agent re-tunes its own selectivity. Operator-controllable — the bot
        # still trades and records outcomes from the very first signal; this only
        # sets how often it adjusts its OWN knobs. Min 1.
        self._adapt_every = max(1, int(adapt_every))
        self._last_action: SignalAction = SignalAction.HOLD
        self._prices: list[Decimal] = []
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self.signal_count = 0
        # Self-improvement: graded on real signal outcomes (kind="strategy").
        self.learner = Learner("market_analyst", "strategy")
        self.detail = ""
        self.enabled: bool = True    # T3: gate signal emission into the pipeline
        self._min_gap_pct = 0.0      # adaptive |EMA gap| % required to act
        self._last_adapt_at = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("entry_exit_agent.started")
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
                    ts_ms = int(data.get("ts_ms", 0)) or int(time.time() * 1000)
                    if price <= 0:
                        continue
                    self._prices.append(price)
                    if len(self._prices) > 500:
                        self._prices = self._prices[-500:]
                    # Reflection: grade matured predictions vs the real price.
                    self.learner.resolve(price, ts_ms)
                    await self._evaluate(price, ts_ms)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("entry_exit_agent.parse_error", exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("entry_exit_agent.stopped")

    async def _evaluate(self, price: Decimal, ts_ms: int) -> None:
        if self._multi_indicator:
            if self._expanded:
                res = expanded_confluence_signal(self._prices)
                label = "Confluence+"
            else:
                res = multi_indicator_signal(self._prices)
                label = "Confluence"
            action = res.action
            confidence = res.confidence
            self.detail = f"{label} {res.detail} · แม่น {self._hr_txt()}"
        else:
            ctx = StrategyContext(prices=tuple(self._prices), position_qty=Decimal(0))
            sig = self._strategy.decide(ctx)
            gap_pct = self._ema_gap_pct()
            action = sig.action if gap_pct >= self._min_gap_pct else SignalAction.HOLD
            confidence = sig.confidence
            self.detail = (
                f"EMA-cross · ยืนยัน≥{self._min_gap_pct:.2f}% (gap {gap_pct:.2f}%)"
                f" · แม่น {self._hr_txt()}"
            )
        # Emit only on a CHANGE of side: a persisting confluence must not spam the
        # bus every tick (the single-position rule + Supreme window also dedup). A
        # HOLD resets the latch so the next BUY/SELL re-arms.
        if action == SignalAction.HOLD:
            self._last_action = SignalAction.HOLD
        elif action != self._last_action and self.enabled:
            self.signal_count += 1
            self.learner.predict(action.value, price, ts_ms)  # record for grading
            out = orjson.dumps({
                "signal": action.value, "price": str(price),
                "ts_ms": ts_ms, "source": "market_analyst", "confidence": str(confidence),
            })
            await self._bus.publish(self._topic_out, b"signal", out)
            self._last_action = action
        self._maybe_adapt()

    def _ema_gap_pct(self) -> float:
        if len(self._prices) < 55:
            return 0.0
        fast = ema(self._prices, 12)[-1]
        slow = ema(self._prices, 26)[-1]
        return float(abs(fast - slow) / slow * 100) if slow > 0 else 0.0

    def _hr_txt(self) -> str:
        hr = self.learner.hit_rate()
        return f"{hr * 100:.0f}% ({self.learner.resolved} ไม้)" if hr is not None else "—"

    def set_adapt_every(self, n: int) -> None:
        """Operator sets how many graded trades of experience to gather before
        the agent re-tunes its own selectivity (min 1)."""
        self._adapt_every = max(1, int(n))

    def _maybe_adapt(self) -> None:
        r = self.learner.today_resolved
        step = self._adapt_every
        if r < step or r == self._last_adapt_at or r % step != 0:
            return
        self._last_adapt_at = r
        hr = self.learner.today_hit_rate() or 0.0
        if hr < 0.45:
            old = self._min_gap_pct
            self._min_gap_pct = min(1.0, self._min_gap_pct + 0.1)
            self.learner.adapt_count += 1
            self.learner.log(
                f"แพ้บ่อย (แม่น {hr * 100:.0f}%) → เพิ่มเงื่อนไขยืนยัน "
                f"{old:.2f}%→{self._min_gap_pct:.2f}%", "adapt",
            )
        elif hr > 0.6 and self._min_gap_pct > 0:
            old = self._min_gap_pct
            self._min_gap_pct = max(0.0, self._min_gap_pct - 0.05)
            self.learner.adapt_count += 1
            self.learner.log(
                f"แม่นขึ้น ({hr * 100:.0f}%) → ผ่อนเงื่อนไข "
                f"{old:.2f}%→{self._min_gap_pct:.2f}%", "adapt",
            )

    async def stop(self) -> None:
        self.running = False
