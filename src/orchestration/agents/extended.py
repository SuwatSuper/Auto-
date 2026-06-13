# Layer 2 — Orchestration (agents/extended)
"""Extended department agents — Phase 2 expansion.

Every agent here does REAL work on data the system already has (the live price
stream + real portfolio/treasury/breaker state). No fabricated signals: an agent
either computes from real inputs or reports that it is warming up. Agents that
need an external data source NOT yet wired (on-chain, macro, social, order book,
funding-rate) are intentionally NOT included — they are deferred until a real
source exists, per the project's no-mock-data policy.
"""
from __future__ import annotations

import asyncio
import gc
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

import orjson
import structlog

from domain.analytics.indicators import ema
from domain.risk.sizing import kelly_fraction
from domain.strategy.base import SignalAction, StrategyContext
from domain.strategy.rsi_reversion import RsiReversionStrategy
from orchestration.ports.event_bus import EventBus


class RuntimeView(Protocol):
    """Minimal read/act surface an agent needs from the runtime."""

    def status(self) -> dict[str, object]: ...
    def trip_breaker(self, reason: str = ...) -> dict[str, object]: ...
    async def send_alert(self, message: str, level: str = ...) -> bool: ...


def _f(value: object, default: float = 0.0) -> float:
    """Best-effort float conversion (never raises)."""
    try:
        if value is None:
            return default
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ── shared lifecycle bases ───────────────────────────────────────────
class _AgentBase:
    """Common AgentLike surface (running / heartbeat / counters / detail)."""

    role: str = ""

    def __init__(self, name: str, logger: structlog.BoundLogger) -> None:
        self.name = name
        self._log = logger
        self.running = False
        self.msg_count = 0
        self.last_beat_ms: int = 0
        self.detail: str = ""

    async def stop(self) -> None:
        self.running = False


class PeriodicAgent(_AgentBase):
    """Runs ``tick()`` on an interval, refreshing the heartbeat every second so
    long intervals never look stale to the watchdog."""

    interval: float = 3.0

    async def start(self) -> None:
        self.running = True
        self._log.info("agent.started", agent=self.name)
        try:
            while self.running:
                self.last_beat_ms = int(time.time() * 1000)
                try:
                    await self.tick()
                    self.msg_count += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # an agent must never crash the loop
                    self._log.warning("agent.tick_error", agent=self.name, exc_info=exc)
                slept = 0.0
                while slept < self.interval and self.running:
                    step = min(1.0, self.interval - slept)
                    await asyncio.sleep(step)
                    slept += step
                    self.last_beat_ms = int(time.time() * 1000)
        finally:
            self._log.info("agent.stopped", agent=self.name)

    async def tick(self) -> None:  # pragma: no cover - overridden
        ...


class PriceListenerAgent(_AgentBase):
    """Subscribes to the price topic and maintains a rolling close series."""

    def __init__(
        self, name: str, bus: EventBus, prices_topic: str, logger: structlog.BoundLogger
    ) -> None:
        super().__init__(name, logger)
        self._bus = bus
        self._topic_in = prices_topic
        self._topic_out: str | None = None
        self._prices: list[Decimal] = []
        self.signal_count = 0

    async def start(self) -> None:
        self.running = True
        queue = self._bus.subscribe(self._topic_in)
        self._log.info("agent.started", agent=self.name)
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
                    if len(self._prices) > 600:
                        self._prices = self._prices[-600:]
                    await self.on_price(price, ts_ms)
                except (orjson.JSONDecodeError, KeyError, ValueError, InvalidOperation) as exc:
                    self._log.warning("agent.parse_error", agent=self.name, exc_info=exc)
        finally:
            self._bus.unsubscribe(self._topic_in, queue)
            self._log.info("agent.stopped", agent=self.name)

    async def on_price(self, price: Decimal, ts_ms: int) -> None:  # pragma: no cover
        ...

    async def _emit(self, action: str, price: Decimal, ts_ms: int) -> None:
        if self._topic_out is None:
            return
        self.signal_count += 1
        out = orjson.dumps({"signal": action, "price": str(price), "ts_ms": ts_ms})
        await self._bus.publish(self._topic_out, b"signal", out)


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
        self.squeeze = self.vol_pct < 1.0
        self.detail = f"ความผันผวน {self.vol_pct:.2f}% " + ("· SQUEEZE ⚠ ใกล้ระเบิด" if self.squeeze else "· ปกติ")


# ── 2. Strategy: Trend Follower (EMA20/50 cross, real) ───────────────
class TrendFollowerAgent(PriceListenerAgent):
    role = "Rides confirmed trends (EMA20/50 cross)"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, signals_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log)
        self._topic_out = signals_topic
        self._pf: Decimal | None = None
        self._ps: Decimal | None = None

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        if len(self._prices) < 55:
            self.detail = f"อุ่นเครื่อง ({len(self._prices)}/55)"
            return
        fast = ema(self._prices, 20)[-1]
        slow = ema(self._prices, 50)[-1]
        self.detail = f"EMA20={fast:.0f} EMA50={slow:.0f} → {'ขาขึ้น' if fast > slow else 'ขาลง'}"
        if self._pf is not None and self._ps is not None:
            if self._pf <= self._ps and fast > slow:
                await self._emit("BUY", price, ts_ms)
            elif self._pf >= self._ps and fast < slow:
                await self._emit("SELL", price, ts_ms)
        self._pf, self._ps = fast, slow


# ── 3. Strategy: Mean Reversion (RSI, real) ──────────────────────────
class MeanReversionAgent(PriceListenerAgent):
    role = "Fades extremes (RSI oversold/overbought)"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, signals_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log)
        self._topic_out = signals_topic
        self._strat = RsiReversionStrategy()

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        ctx = StrategyContext(prices=tuple(self._prices), position_qty=Decimal(0))
        sig = self._strat.decide(ctx)
        self.detail = f"สัญญาณ: {sig.reason}"
        if sig.action != SignalAction.HOLD:
            await self._emit(sig.action.value, price, ts_ms)


# ── 4. Strategy: Breakout Specialist (Donchian, real) ────────────────
class BreakoutSpecialistAgent(PriceListenerAgent):
    role = "Trades range breakouts (Donchian channel)"

    def __init__(self, name: str, bus: EventBus, prices_topic: str, signals_topic: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, bus, prices_topic, log)
        self._topic_out = signals_topic
        self._n = 20

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        if len(self._prices) < self._n + 1:
            self.detail = f"อุ่นเครื่อง ({len(self._prices)}/{self._n + 1})"
            return
        window = self._prices[-(self._n + 1):-1]
        hi, lo = max(window), min(window)
        self.detail = f"กรอบ {lo:.0f}–{hi:.0f}"
        if price > hi:
            await self._emit("BUY", price, ts_ms)
        elif price < lo:
            await self._emit("SELL", price, ts_ms)


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
            await self._rt.send_alert(f"🦢 Black swan: BTC {move:+.1f}% ใน 60 วิ", "critical")
            if abs(move) >= self._trip_pct:
                self._rt.trip_breaker(f"BLACK_SWAN {move:+.1f}%")
        elif abs(move) < self._alert_pct:
            self._fired = False


# ── 6. Risk: Drawdown Guardian (real monitor + kill switch) ──────────
class DrawdownGuardianAgent(PeriodicAgent):
    role = "Halts trading if daily loss breaches the limit"

    def __init__(self, name: str, runtime: RuntimeView, limit_pct: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._limit = limit_pct
        self.guards_triggered = 0

    async def tick(self) -> None:
        s = self._rt.status()
        dd = _f(s.get("drawdown_pct"))
        dl = _f(s.get("daily_loss_pct"))
        self.detail = f"DD {dd:.1f}% · ขาดทุนวันนี้ {dl:.1f}% / เพดาน {self._limit:.0f}%"
        if self._limit > 0 and dl >= self._limit and not bool(s.get("treasury_halted")):
            self._rt.trip_breaker(f"DRAWDOWN_GUARD ขาดทุน {dl:.1f}%")
            self.guards_triggered += 1
            await self._rt.send_alert(f"🛡️ Drawdown guard: หยุดเทรด (ขาดทุน {dl:.1f}%)", "critical")


# ── 7. Risk: Dynamic Position Sizer (Kelly, real) ────────────────────
class DynamicPositionSizerAgent(PeriodicAgent):
    role = "Suggests position size via Kelly criterion"

    def __init__(self, name: str, runtime: RuntimeView, win_loss_ratio: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._wl = Decimal(str(win_loss_ratio))
        self.suggested_risk_pct = 0.0

    async def tick(self) -> None:
        s = self._rt.status()
        wins = int(_f(s.get("wins")))
        losses = int(_f(s.get("losses")))
        total = wins + losses
        wr = Decimal(wins) / Decimal(total) if total > 0 else Decimal("0.5")
        k = kelly_fraction(wr, self._wl)
        self.suggested_risk_pct = float(k) * 100
        self.detail = f"Kelly แนะนำเสี่ยง {self.suggested_risk_pct:.2f}%/ไม้ (WR {float(wr) * 100:.0f}%, {total} ไม้)"


# ── 8. Risk: Trailing Stop Bot (real, advisory) ──────────────────────
class TrailingStopBotAgent(PeriodicAgent):
    role = "Tracks a trailing stop to lock in profit"

    def __init__(self, name: str, runtime: RuntimeView, trail_pct: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._trail = trail_pct
        self._peak: float | None = None
        self.trail_stop: float = 0.0

    async def tick(self) -> None:
        s = self._rt.status()
        port = s.get("portfolio")
        rows = port if isinstance(port, list) else []
        if not rows:
            self._peak = None
            self.trail_stop = 0.0
            self.detail = "ไม่มี position เปิดอยู่"
            return
        mark = _f(rows[0].get("mark_price") if isinstance(rows[0], dict) else None)
        if mark <= 0:
            self.detail = "ยังไม่มีราคา mark"
            return
        self._peak = mark if self._peak is None else max(self._peak, mark)
        self.trail_stop = self._peak * (1 - self._trail / 100)
        self.detail = f"จุดสูงสุด {self._peak:.0f} · trailing-stop {self.trail_stop:.0f} ({self._trail:.1f}%)"


# ── 9. Risk/Treasury: Profit Sweeper (real bookkeeping) ──────────────
class ProfitSweeperAgent(PeriodicAgent):
    role = "Sweeps realized profit into a stablecoin vault"

    interval = 5.0

    def __init__(self, name: str, runtime: RuntimeView, sweep_ratio: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._ratio = sweep_ratio
        self._last_realized = 0.0
        self.vault_thb = 0.0

    async def tick(self) -> None:
        s = self._rt.status()
        realized = _f(s.get("realized_today"))
        if realized > self._last_realized:
            self.vault_thb += (realized - self._last_realized) * self._ratio
            self._last_realized = realized
        elif realized < self._last_realized:
            self._last_realized = realized  # new day / drawdown — reset baseline
        self.detail = f"คลังกำไร (vault) ฿{self.vault_thb:,.2f} · กวาด {self._ratio * 100:.0f}% ของกำไรที่รับรู้"


# ── 10. Execution: Fee Optimizer (real maker/taker calc) ─────────────
class FeeOptimizerAgent(PeriodicAgent):
    role = "Chooses maker vs taker to minimise fees"

    interval = 5.0

    def __init__(self, name: str, maker_bps: float, taker_bps: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._maker = maker_bps
        self._taker = taker_bps

    async def tick(self) -> None:
        rec = "MAKER (ตั้งรอ)" if self._maker <= self._taker else "TAKER (เคาะ)"
        saving = abs(self._taker - self._maker)
        self.detail = f"maker {self._maker:.0f}bps vs taker {self._taker:.0f}bps → แนะนำ {rec} (ประหยัด {saving:.0f}bps)"


# ── 11. Execution: Latency Pinger (real, from measured samples) ──────
class LatencyPingerAgent(PeriodicAgent):
    role = "Watches exchange latency; throttles when laggy"

    def __init__(self, name: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self.high_latency = False

    async def tick(self) -> None:
        s = self._rt.status()
        cur = _f(s.get("latency_ms"))
        p50 = _f(s.get("p50_latency_ms"))
        p95 = _f(s.get("p95_latency_ms"))
        self.high_latency = p95 > 1000
        self.detail = f"latency now {cur:.0f}ms · p50 {p50:.0f}ms · p95 {p95:.0f}ms" + (" ⚠ แล็กสูง — ชะลอยิงออเดอร์" if self.high_latency else "")


# ── 12. System: API & Connection Monitor (real self-monitor) ─────────
class ApiConnectionMonitorAgent(PeriodicAgent):
    role = "Watches feed/account health; flags outages"

    def __init__(self, name: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self.outages = 0
        self._was_ok = True

    async def tick(self) -> None:
        s = self._rt.status()
        pf = s.get("price_feed")
        pf = pf if isinstance(pf, dict) else {}
        acct = s.get("account")
        acct = acct if isinstance(acct, dict) else {}
        feed_ok = bool(pf.get("connected"))
        err = pf.get("last_error")
        if not feed_ok and self._was_ok:
            self.outages += 1
        self._was_ok = feed_ok
        acct_txt = "เชื่อมบัญชีแล้ว" if acct.get("connected") else "ยังไม่ใส่ key"
        self.detail = (
            f"ฟีดราคา {'OK ✅' if feed_ok else 'ขาด ❌'}"
            + (f" ({err})" if err and not feed_ok else "")
            + f" · บัญชี: {acct_txt} · ขาดการเชื่อมต่อสะสม {self.outages} ครั้ง"
        )


# ── 13. System: Dashboard Synthesizer (real KPIs + midnight push) ────
class DashboardSynthesizerAgent(PeriodicAgent):
    role = "Distils 4 KPIs; pushes a daily midnight summary"

    interval = 5.0

    def __init__(self, name: str, runtime: RuntimeView, rr: float, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime
        self._rr = rr
        self._last_push_day: str | None = None
        self.summary: dict[str, float] = {}

    async def tick(self) -> None:
        s = self._rt.status()
        wins = int(_f(s.get("wins")))
        losses = int(_f(s.get("losses")))
        total = wins + losses
        wr = (wins / total * 100) if total > 0 else 0.0
        dd = _f(s.get("drawdown_pct"))
        pnl = _f(s.get("pnl_today"))
        self.summary = {"win_rate": round(wr, 1), "rr": self._rr, "max_drawdown": round(dd, 1), "pnl_today": round(pnl, 2)}
        self.detail = f"WR {wr:.0f}% · R:R {self._rr:.1f} · MaxDD {dd:.1f}% · PnL ฿{pnl:,.0f}"
        now = datetime.now()
        day = now.strftime("%Y-%m-%d")
        if now.hour == 0 and self._last_push_day != day:
            self._last_push_day = day
            await self._rt.send_alert(
                f"🌙 สรุปวัน: WR {wr:.0f}% · R:R {self._rr:.1f} · MaxDD {dd:.1f}% · PnL ฿{pnl:,.0f}", "info"
            )


# ── 14. System: Tax & Accounting Clerk (real closed-trade ledger) ────
class TaxAccountingClerkAgent(PeriodicAgent):
    role = "Books realized PnL per trade for tax reporting"

    interval = 5.0

    def __init__(self, name: str, runtime: RuntimeView, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self._rt = runtime

    async def tick(self) -> None:
        s = self._rt.status()
        closed = int(_f(s.get("trades_closed")))
        wins = int(_f(s.get("wins")))
        losses = int(_f(s.get("losses")))
        realized = _f(s.get("realized_today"))
        self.detail = f"ปิดแล้ว {closed} ไม้ (ชนะ {wins}/แพ้ {losses}) · กำไรรับรู้วันนี้ ฿{realized:,.2f} → บันทึกเพื่อภาษี"


# ── 15. System: Garbage Collector (real memory hygiene) ──────────────
class GarbageCollectorAgent(PeriodicAgent):
    role = "Frees memory and keeps the runtime lean"

    interval = 30.0

    def __init__(self, name: str, log: structlog.BoundLogger) -> None:
        super().__init__(name, log)
        self.collections = 0
        self.freed_total = 0

    async def tick(self) -> None:
        freed = gc.collect()
        self.collections += 1
        self.freed_total += freed
        tracked = len(gc.get_objects())
        self.detail = f"gc รอบที่ {self.collections} · คืน {freed} objects · ติดตามอยู่ {tracked:,}"
