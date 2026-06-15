# Layer 2 — Orchestration (agents/timeline_analyst)
"""TimelineAnalystAgent — replays the full price timeline, measures the real
win rate of entry setups, classifies the market regime, and publishes a
win-probability (p_win) that the entry gate uses to only fire high-odds trades.

Honest by construction: p_win is the MEASURED win rate of comparable historical
setups (past 50 + recent 50), not a promise. With a thin history it reports a
small sample and the gate refuses to fire until enough setups are graded.
"""
from __future__ import annotations

import time
from decimal import Decimal

import orjson
import structlog

from domain.analytics.indicators import ema
from domain.analytics.timeline import ema_cross_setups, summarize
from orchestration.agents.learning import Learner
from orchestration.ports.event_bus import EventBus


class TimelineAnalystAgent:
    """Rolling timeline analysis → regime + measured p_win for the entry gate."""

    role = "Replays full price history; only greenlights ≥min_p_win setups"

    def __init__(
        self,
        name: str,
        bus: EventBus,
        prices_topic: str,
        topic_out: str,
        logger: structlog.BoundLogger,
        min_p_win: Decimal = Decimal("0.80"),
        max_history: int = 6000,
        analyze_every: int = 5,
        min_samples: int = 20,
    ) -> None:
        self.name = name
        self._bus = bus
        self._topic_in = prices_topic
        self._topic_out = topic_out
        self._log = logger.bind(agent=name)
        self._min_p_win = min_p_win
        self._min_samples = max(1, min_samples)
        self._max_history = max_history
        self._analyze_every = max(1, analyze_every)
        self.learner = Learner(name, "reliability")

        self.running = False
        self.msg_count = 0
        self.last_beat_ms = 0
        self.detail = ""

        self._hist: list[Decimal] = []
        self._since_analyze = 0
        # Published analysis (also read directly by the runtime gate)
        self.p_win: Decimal = Decimal("0")
        self.p_win_samples: int = 0
        self.regime: str = "RANGE"
        self.past_win_rate: str | None = None
        self.recent_win_rate: str | None = None
        self.analysis: dict[str, object] = {}

    async def start(self) -> None:
        self.running = True
        import asyncio  # noqa: PLC0415

        queue = self._bus.subscribe(self._topic_in)
        self._log.info("timeline_analyst.started", min_p_win=str(self._min_p_win))
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
                    price = Decimal(str(orjson.loads(raw).get("price", "0")))
                except (orjson.JSONDecodeError, ValueError, ArithmeticError):
                    continue
                if price <= 0:
                    continue
                self._hist.append(price)
                if len(self._hist) > self._max_history:
                    self._hist = self._hist[-self._max_history:]
                self._since_analyze += 1
                if self._since_analyze >= self._analyze_every:
                    self._since_analyze = 0
                    await self._analyze()
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("timeline_analyst.stopped")

    async def stop(self) -> None:
        self.running = False

    def set_min_p_win(self, value: Decimal) -> None:
        self._min_p_win = value

    def _classify_regime(self) -> str:
        h = self._hist
        if len(h) < 55:
            return "RANGE"
        window = h[-30:]
        mean = sum(window) / Decimal(len(window))
        if mean <= 0:
            return "RANGE"
        var = sum((c - mean) ** 2 for c in window) / Decimal(len(window))
        vol_pct = var.sqrt() / mean * Decimal("100")
        if vol_pct > Decimal("3"):
            return "HIGH_VOL"
        fast = ema(h, 20)[-1]
        slow = ema(h, 50)[-1]
        gap = (fast - slow) / slow * Decimal("100") if slow > 0 else Decimal("0")
        if gap > Decimal("0.3"):
            return "TREND_UP"
        if gap < Decimal("-0.3"):
            return "TREND_DOWN"
        return "RANGE"

    async def _analyze(self) -> None:
        setups = ema_cross_setups(self._hist)
        summary = summarize(setups, past_n=50, recent_n=50)
        self.regime = self._classify_regime()
        p = summary.get("p_win")
        self.p_win = Decimal(str(p)) if p is not None else Decimal("0")
        sample = summary.get("sample", 0)
        self.p_win_samples = sample if isinstance(sample, int) else 0
        self.past_win_rate = summary.get("past_win_rate")  # type: ignore[assignment]
        self.recent_win_rate = summary.get("recent_win_rate")  # type: ignore[assignment]
        self.analysis = {**summary, "regime": self.regime, "min_p_win": str(self._min_p_win)}

        pass_gate = self.p_win_samples >= self._min_samples and self.p_win >= self._min_p_win
        self.detail = (
            f"วิเคราะห์ {self.p_win_samples} setups (อดีต {summary.get('past_n')}/"
            f"ล่าสุด {summary.get('recent_n')}) · p_win {float(self.p_win) * 100:.0f}% "
            f"(เกณฑ์ {float(self._min_p_win) * 100:.0f}%) · regime {self.regime} → "
            + ("✅ ยิงได้" if pass_gate else "⛔ ยังไม่ถึงเกณฑ์")
        )
        if self.p_win_samples >= self._min_samples:
            self.learner.note_threshold(
                int(self.p_win * 100),
                f"อัตราชนะย้อนหลังขยับเป็น {float(self.p_win) * 100:.0f}% "
                f"(เกณฑ์ยิง {float(self._min_p_win) * 100:.0f}%)",
            )
        await self._publish()

    async def _publish(self) -> None:
        import contextlib  # noqa: PLC0415

        payload = orjson.dumps(
            {
                "type": "TIMELINE_ANALYSIS",
                "ts_ms": int(time.time() * 1000),
                "p_win": str(self.p_win),
                "p_win_samples": self.p_win_samples,
                "regime": self.regime,
                "analysis": self.analysis,
            }
        )
        with contextlib.suppress(Exception):
            await self._bus.publish(self._topic_out, b"timeline", payload)

    # ── learning-board surface (shown for every agent) ───────────────
    def learns_from(self) -> str:
        return "ผลแพ้/ชนะของ setup ในอดีตทั้งหมด — เก็บสถิติว่าแบบไหนชนะจริง"

    def can_improve(self) -> str:
        return "ปรับเกณฑ์ p_win/regime ให้คัดเฉพาะจังหวะโอกาสชนะสูง (ยิงน้อยลงแต่แม่นขึ้น)"
