# Layer 2 — Orchestration (agents/extended/price_agents)
"""Price-listening extended agents (volatility, trend, mean-reversion, breakout,
black-swan). Each computes from the rolling real close series — no fabricated
signals; an agent either computes from real inputs or reports it is warming up.
"""
from __future__ import annotations

from decimal import Decimal

import structlog

from domain.analytics.indicators import ema
from domain.strategy.base import SignalAction, StrategyContext
from domain.strategy.rsi_reversion import RsiReversionStrategy
from orchestration.agents.extended.base import PriceListenerAgent, RuntimeView
from orchestration.ports.event_bus import EventBus


# ── 1. Data & Alpha: Volatility Oracle (real, close-based) ───────────
class VolatilityOracleAgent(PriceListenerAgent):
    role = "ATR/Bollinger volatility + squeeze detection"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log)
        self.vol_pct: float = 0.0
        self.squeeze: bool = False

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        n = 20
        if len(self._prices) < n + 1:
            self.detail = f"อุ่นเครื่อง ({len(self._prices)}/{n + 1})"
            return
        closes = self._prices[-n:]
        sma = sum(closes) / Decimal(n)
        var = sum((c - sma) ** 2 for c in closes) / Decimal(n)
        sd = var.sqrt()
        self.vol_pct = float(sd / sma * Decimal(200)) if sma > 0 else 0.0  # 2σ band width %
        prev = self.squeeze
        self.squeeze = self.vol_pct < 1.0
        self.detail = f"ความผันผวน {self.vol_pct:.2f}% " + ("· SQUEEZE ⚠ ใกล้ระเบิด" if self.squeeze else "· ปกติ")
        if self.squeeze != prev:
            self.learner.log(
                (f"ตรวจพบ SQUEEZE (σ {self.vol_pct:.2f}%) — ตลาดอาจระเบิดแรง" if self.squeeze
                 else f"ความผันผวนคลายตัว (σ {self.vol_pct:.2f}%)"),
                "event",
            )


# ── 2. Strategy: Trend Follower (EMA20/50 cross, self-tuning) ────────
class TrendFollowerAgent(PriceListenerAgent):
    role = "Rides trends (EMA20/50) — self-tunes confirmation from real wins"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, signals_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log, kind="strategy")
        self._topic_out = signals_topic
        self._pf: Decimal | None = None
        self._ps: Decimal | None = None
        self._min_gap_pct = 0.0   # adaptive: required |EMA gap| % to act
        self._last_adapt_at = 0

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        self.learner.resolve(price, ts_ms)
        if len(self._prices) < 55:
            self.detail = f"อุ่นเครื่อง ({len(self._prices)}/55)"
            return
        fast = ema(self._prices, 20)[-1]
        slow = ema(self._prices, 50)[-1]
        gap_pct = float(abs(fast - slow) / slow * 100) if slow > 0 else 0.0
        self.detail = (
            f"EMA20={fast:.0f} EMA50={slow:.0f} ({'ขาขึ้น' if fast > slow else 'ขาลง'})"
            f" · ยืนยัน≥{self._min_gap_pct:.2f}% · แม่น {self._hr_txt()}"
        )
        if self._pf is not None and self._ps is not None and gap_pct >= self._min_gap_pct:
            if self._pf <= self._ps and fast > slow:
                await self._emit("BUY", price, ts_ms)
            elif self._pf >= self._ps and fast < slow:
                await self._emit("SELL", price, ts_ms)
        self._pf, self._ps = fast, slow
        self._maybe_adapt()

    def _maybe_adapt(self) -> None:
        r = self.learner.today_resolved
        if r < 8 or r == self._last_adapt_at or r % 8 != 0:
            return
        self._last_adapt_at = r
        hr = self.learner.today_hit_rate() or 0.0
        if hr < 0.45:
            old = self._min_gap_pct
            self._min_gap_pct = min(1.0, self._min_gap_pct + 0.1)
            self.learner.adapt_count += 1
            self.learner.log(f"แพ้บ่อย (แม่น {hr * 100:.0f}%) → เพิ่มเงื่อนไขยืนยัน {old:.2f}%→{self._min_gap_pct:.2f}%", "adapt")
        elif hr > 0.6 and self._min_gap_pct > 0:
            old = self._min_gap_pct
            self._min_gap_pct = max(0.0, self._min_gap_pct - 0.05)
            self.learner.adapt_count += 1
            self.learner.log(f"แม่นขึ้น ({hr * 100:.0f}%) → ผ่อนเงื่อนไข {old:.2f}%→{self._min_gap_pct:.2f}%", "adapt")

    def coach_tighten(self, coach: str) -> None:
        old = self._min_gap_pct
        self._min_gap_pct = min(1.0, self._min_gap_pct + 0.1)
        self.learner.adapt_count += 1
        self.learner.log(f"เรียนจากโค้ช {coach} → เข้มงวดขึ้น {old:.2f}%→{self._min_gap_pct:.2f}%", "coach")


# ── 3. Strategy: Mean Reversion (RSI, self-tuning) ───────────────────
class MeanReversionAgent(PriceListenerAgent):
    role = "Fades extremes (RSI) — self-tunes thresholds from real wins"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, signals_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log, kind="strategy")
        self._topic_out = signals_topic
        self._strat = RsiReversionStrategy()
        self._last_adapt_at = 0

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        self.learner.resolve(price, ts_ms)
        ctx = StrategyContext(prices=tuple(self._prices), position_qty=Decimal(0))
        sig = self._strat.decide(ctx)
        self.detail = f"RSI {self._strat.oversold:.0f}/{self._strat.overbought:.0f} · {sig.reason} · แม่น {self._hr_txt()}"
        if sig.action != SignalAction.HOLD:
            await self._emit(sig.action.value, price, ts_ms)
        self._maybe_adapt()

    def _maybe_adapt(self) -> None:
        r = self.learner.today_resolved
        if r < 8 or r == self._last_adapt_at or r % 8 != 0:
            return
        self._last_adapt_at = r
        hr = self.learner.today_hit_rate() or 0.0
        o, ob = self._strat.oversold, self._strat.overbought
        if hr < 0.45:
            self._strat.oversold = max(Decimal(15), o - Decimal(2))
            self._strat.overbought = min(Decimal(85), ob + Decimal(2))
            self.learner.adapt_count += 1
            self.learner.log(f"แพ้บ่อย (แม่น {hr * 100:.0f}%) → เข้มขึ้น RSI {o}/{ob}→{self._strat.oversold}/{self._strat.overbought}", "adapt")
        elif hr > 0.6:
            self._strat.oversold = min(Decimal(35), o + Decimal(1))
            self._strat.overbought = max(Decimal(65), ob - Decimal(1))
            self.learner.adapt_count += 1
            self.learner.log(f"แม่นขึ้น ({hr * 100:.0f}%) → ผ่อน RSI {o}/{ob}→{self._strat.oversold}/{self._strat.overbought}", "adapt")

    def coach_tighten(self, coach: str) -> None:
        o, ob = self._strat.oversold, self._strat.overbought
        self._strat.oversold = max(Decimal(15), o - Decimal(2))
        self._strat.overbought = min(Decimal(85), ob + Decimal(2))
        self.learner.adapt_count += 1
        self.learner.log(f"เรียนจากโค้ช {coach} → เข้มขึ้น RSI → {self._strat.oversold}/{self._strat.overbought}", "coach")


# ── 4. Strategy: Breakout Specialist (Donchian, self-tuning) ─────────
class BreakoutSpecialistAgent(PriceListenerAgent):
    role = "Trades breakouts (Donchian) — self-tunes channel from real wins"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, signals_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log, kind="strategy")
        self._topic_out = signals_topic
        self._n = 20
        self._last_adapt_at = 0

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        self.learner.resolve(price, ts_ms)
        if len(self._prices) < self._n + 1:
            self.detail = f"อุ่นเครื่อง ({len(self._prices)}/{self._n + 1})"
            return
        window = self._prices[-(self._n + 1):-1]
        hi, lo = max(window), min(window)
        self.detail = f"กรอบ(N={self._n}) {lo:.0f}–{hi:.0f} · แม่น {self._hr_txt()}"
        if price > hi:
            await self._emit("BUY", price, ts_ms)
        elif price < lo:
            await self._emit("SELL", price, ts_ms)
        self._maybe_adapt()

    def _maybe_adapt(self) -> None:
        r = self.learner.today_resolved
        if r < 8 or r == self._last_adapt_at or r % 8 != 0:
            return
        self._last_adapt_at = r
        hr = self.learner.today_hit_rate() or 0.0
        if hr < 0.45:
            old = self._n
            self._n = min(50, self._n + 5)
            self.learner.adapt_count += 1
            self.learner.log(f"เบรกหลอกบ่อย (แม่น {hr * 100:.0f}%) → ขยายกรอบ N {old}→{self._n}", "adapt")
        elif hr > 0.6:
            old = self._n
            self._n = max(10, self._n - 3)
            self.learner.adapt_count += 1
            self.learner.log(f"แม่นขึ้น ({hr * 100:.0f}%) → ลดกรอบ N {old}→{self._n}", "adapt")

    def coach_tighten(self, coach: str) -> None:
        old = self._n
        self._n = min(50, self._n + 5)
        self.learner.adapt_count += 1
        self.learner.log(f"เรียนจากโค้ช {coach} → ขยายกรอบ N {old}→{self._n}", "coach")


# ── 5. Risk: Black Swan Detector (real, price-shock) ─────────────────
class BlackSwanDetectorAgent(PriceListenerAgent):
    role = "Detects violent moves; trips breaker on a crash"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log)
        self._rt = runtime
        self._hist: list[tuple[int, Decimal]] = []
        self._fired = False
        self.swans_detected = 0
        self._alert_pct = 5.0   # |move| in 60s that is "abnormal"
        self._trip_pct = 10.0   # |move| in 60s that halts trading

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        self._hist.append((ts_ms, price))
        cutoff = ts_ms - 60_000
        self._hist = [(t, p) for t, p in self._hist if t >= cutoff]
        if len(self._hist) < 2:
            return
        old = self._hist[0][1]
        move = float((price - old) / old * 100) if old > 0 else 0.0
        self.detail = f"การเคลื่อนไหว 60 วิ {move:+.2f}%"
        if abs(move) >= self._alert_pct and not self._fired:
            self._fired = True
            self.swans_detected += 1
            self._log.warning("black_swan.detected", move_pct=round(move, 2))
            self.learner.log(f"🦢 ตรวจพบหงส์ดำ: BTC {move:+.1f}% ใน 60 วิ", "event")
            await self._rt.send_alert(f"🦢 Black swan: BTC {move:+.1f}% ใน 60 วิ", "critical")
            if abs(move) >= self._trip_pct:
                self._rt.trip_breaker(f"BLACK_SWAN {move:+.1f}%")
                self.learner.log(f"สั่งหยุดเทรดฉุกเฉิน (ราคาเคลื่อน {move:+.1f}%)", "adapt")
        elif abs(move) < self._alert_pct:
            self._fired = False
