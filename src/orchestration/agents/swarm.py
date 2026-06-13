# Layer 2 — Orchestration (agents/swarm)
"""Analyst swarm — 150 real agents in three divisions that talk to each other.

  • Historical Chart Lab (50) — run a method over COMPLETED candles of a
    timeframe (1s/1m/1h/1d): the past trend / pattern.
  • Live Price Lab (50)       — run the same methods including the CURRENTLY
    forming candle: the present read.
  • Entry Hunters (50)        — hunt buy entry points; emit BUY to the signal
    bus only when their method is bullish AND their division consensus agrees.

A shared :class:`MarketDataHub` resamples the real tick stream into OHLC candles
so every agent computes on REAL data (honest "warming up" until a timeframe has
enough bars). Each division has a chief that aggregates its 50 workers into a
consensus *bias* and publishes it — that aggregate is how the divisions
coordinate for maximum performance, and what the entry hunters consult before
acting. Every agent keeps a Learner (its memory of mistakes + fixes).
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from decimal import Decimal
from typing import Protocol

import orjson
import structlog

from domain.analytics.swarm_methods import (
    BEAR,
    BULL,
    AnalysisRead,
    Candle,
    run_method,
)
from orchestration.agents.extended import PeriodicAgent, PriceListenerAgent
from orchestration.ports.event_bus import EventBus

# Timeframes the swarm spans, every second / minute / hour / day.
TIMEFRAMES: list[str] = ["1s", "1m", "1h", "1d"]
_TF_SECONDS: dict[str, int] = {"1s": 1, "1m": 60, "1h": 3600, "1d": 86400}
_TF_LABEL: dict[str, str] = {"1s": "วินาที", "1m": "นาที", "1h": "ชั่วโมง", "1d": "วัน"}

_ACT_STRENGTH = Decimal("0.5")  # min strength before a read counts as a prediction


class AgentLike(Protocol):
    """Minimal lifecycle surface the runtime needs from a swarm agent."""

    running: bool
    msg_count: int
    last_beat_ms: int

    async def start(self) -> None: ...
    async def stop(self) -> None: ...


# ── shared market-data backbone ──────────────────────────────────────
class MarketDataHub:
    """Resamples the real tick stream into OHLC candles per timeframe.

    Pure in-process state (Decimal prices). ``ingest`` is fed by the hub agent;
    every analyst reads ``series``/``latest`` from the same hub so the whole
    swarm works off one shared, honest view of the market.
    """

    def __init__(self, maxlen: int = 300) -> None:
        self._maxlen = maxlen
        self._completed: dict[str, deque[Candle]] = {
            tf: deque(maxlen=maxlen) for tf in TIMEFRAMES
        }
        self._cur: dict[str, Candle | None] = {tf: None for tf in TIMEFRAMES}
        self._bucket: dict[str, int] = {tf: -1 for tf in TIMEFRAMES}
        self._latest_price: Decimal | None = None
        self._latest_ts: int = 0

    def ingest(self, price: Decimal, ts_ms: int) -> None:
        if price <= 0:
            return
        self._latest_price = price
        self._latest_ts = ts_ms
        for tf, sec in _TF_SECONDS.items():
            bucket = ts_ms // (sec * 1000)
            cur = self._cur[tf]
            if cur is None or bucket != self._bucket[tf]:
                if cur is not None:
                    self._completed[tf].append(cur)
                self._cur[tf] = Candle(bucket * sec * 1000, price, price, price, price)
                self._bucket[tf] = bucket
            else:
                self._cur[tf] = Candle(
                    cur.ts_ms, cur.open, max(cur.high, price), min(cur.low, price), price
                )

    def series(self, timeframe: str, *, include_current: bool = False) -> list[Candle]:
        comp = list(self._completed.get(timeframe, deque()))
        cur = self._cur.get(timeframe)
        if include_current and cur is not None:
            comp.append(cur)
        return comp

    def latest(self) -> tuple[Decimal | None, int]:
        return self._latest_price, self._latest_ts

    def candle_counts(self) -> dict[str, int]:
        return {tf: len(self._completed[tf]) for tf in TIMEFRAMES}


# ── hub agent (feeds the shared hub from the price bus) ───────────────
class MarketDataHubAgent(PriceListenerAgent):
    role = "Builds multi-timeframe OHLC candles (1s/1m/1h/1d) for the swarm"

    def __init__(
        self,
        name: str,
        bus: EventBus,
        prices_topic: str,
        hub: MarketDataHub,
        logger: structlog.BoundLogger,
    ) -> None:
        super().__init__(name, bus, prices_topic, logger)
        self.hub = hub

    async def on_price(self, price: Decimal, ts_ms: int) -> None:
        self.hub.ingest(price, ts_ms)
        counts = self.hub.candle_counts()
        self.detail = "แท่งเทียน · " + " ".join(
            f"{_TF_LABEL[tf]} {counts[tf]}" for tf in TIMEFRAMES
        )


# ── analyst worker (historical OR live) ──────────────────────────────
class ChartAnalystAgent(PeriodicAgent):
    """Runs one method on one timeframe and grades its own calls (real memory)."""

    interval = 4.0

    def __init__(
        self,
        name: str,
        hub: MarketDataHub,
        timeframe: str,
        method: str,
        mode: str,  # "historical" (past candles) | "live" (incl. current candle)
        logger: structlog.BoundLogger,
    ) -> None:
        super().__init__(name, logger, kind="strategy")
        self._hub = hub
        self._tf = timeframe
        self._method = method
        self._mode = mode
        self.read: AnalysisRead = AnalysisRead.neutral("เริ่มต้น")
        self.signal_count = 0

    def _hr_txt(self) -> str:
        hr = self.learner.hit_rate()
        return f"{hr * 100:.0f}% ({self.learner.resolved} ครั้ง)" if hr is not None else "—"

    async def tick(self) -> None:
        price, ts_ms = self._hub.latest()
        if price is not None:
            self.learner.resolve(price, ts_ms)
        candles = self._hub.series(self._tf, include_current=(self._mode == "live"))
        read = run_method(self._method, candles)
        self.read = read
        scope = "อดีต" if self._mode == "historical" else "ปัจจุบัน"
        self.detail = (
            f"[{self._tf}·{self._method}·{scope}] {read.label} → {read.direction} "
            f"({float(read.strength) * 100:.0f}%) · แม่น {self._hr_txt()}"
        )
        if price is not None and read.direction in (BULL, BEAR) and read.strength >= _ACT_STRENGTH:
            action = "BUY" if read.direction == BULL else "SELL"
            self.learner.predict(action, price, ts_ms)
            self.signal_count += 1


# ── entry hunter (emits BUY signals through the existing pipeline) ────
class EntryHunterAgent(PeriodicAgent):
    """Looks for buy entry points; emits BUY to the signal bus when its method
    is bullish AND the divisions' consensus bias agrees (coordination)."""

    interval = 3.0

    def __init__(
        self,
        name: str,
        hub: MarketDataHub,
        timeframe: str,
        method: str,
        threshold: Decimal,
        bus: EventBus,
        signals_topic: str,
        bias_provider: Callable[[], float],
        logger: structlog.BoundLogger,
    ) -> None:
        super().__init__(name, logger, kind="strategy")
        self._hub = hub
        self._tf = timeframe
        self._method = method
        self._threshold = threshold
        self._bus = bus
        self._signals_topic = signals_topic
        self._bias_provider = bias_provider
        self.read: AnalysisRead = AnalysisRead.neutral("เริ่มต้น")
        self.signal_count = 0
        self.entries_found = 0

    def _hr_txt(self) -> str:
        hr = self.learner.hit_rate()
        return f"{hr * 100:.0f}% ({self.learner.resolved} ครั้ง)" if hr is not None else "—"

    async def _emit_buy(self, price: Decimal, ts_ms: int) -> None:
        out = orjson.dumps(
            {"signal": "BUY", "price": str(price), "ts_ms": ts_ms, "source": self.name}
        )
        await self._bus.publish(self._signals_topic, b"signal", out)

    async def tick(self) -> None:
        price, ts_ms = self._hub.latest()
        if price is not None:
            self.learner.resolve(price, ts_ms)
        candles = self._hub.series(self._tf, include_current=True)
        read = run_method(self._method, candles)
        self.read = read
        bias = self._bias_provider()
        ready = read.direction == BULL and read.strength >= self._threshold and bias >= 0.0
        self.detail = (
            f"[{self._tf}·{self._method}] {read.label} · ฉันทามติ {bias:+.2f} "
            f"· แม่น {self._hr_txt()}" + (" · 🎯 เข้าซื้อ!" if ready else " · เฝ้ารอจังหวะ")
        )
        if ready and price is not None:
            await self._emit_buy(price, ts_ms)
            self.learner.predict("BUY", price, ts_ms)
            self.signal_count += 1
            self.entries_found += 1
            self.learner.log(
                f"พบจุดเข้าซื้อ @{price:.0f} ({self._method}/{self._tf}, "
                f"strength {float(read.strength) * 100:.0f}%, bias {bias:+.2f})",
                "event",
            )


# ── division chief (aggregates 50 workers → consensus bias) ──────────
class DivisionChiefAgent(PeriodicAgent):
    """Reads its workers' latest verdicts, computes a consensus bias in [-1,1],
    and publishes it so the rest of the swarm can coordinate."""

    interval = 3.0

    def __init__(
        self,
        name: str,
        workers: list[ChartAnalystAgent | EntryHunterAgent],
        bus: EventBus,
        analysis_topic: str,
        label: str,
        logger: structlog.BoundLogger,
    ) -> None:
        super().__init__(name, logger, kind="reliability")
        self._workers = workers
        self._bus = bus
        self._analysis_topic = analysis_topic
        self._label = label
        self.bias: float = 0.0
        self._last_bucket = 99

    async def tick(self) -> None:
        bulls = sum(1 for w in self._workers if w.read.direction == BULL)
        bears = sum(1 for w in self._workers if w.read.direction == BEAR)
        total = len(self._workers)
        neutrals = total - bulls - bears
        self.bias = (bulls - bears) / total if total else 0.0
        self.detail = (
            f"{self._label}: 🟢{bulls} 🔴{bears} ⚪{neutrals} → ฉันทามติ {self.bias:+.2f}"
        )
        out = orjson.dumps(
            {
                "division": self.name,
                "bias": f"{self.bias:.4f}",
                "bulls": bulls,
                "bears": bears,
                "neutral": neutrals,
                "ts_ms": int(time.time() * 1000),
                "source": self.name,
            }
        )
        await self._bus.publish(self._analysis_topic, b"analysis", out)
        bucket = int(round((self.bias + 1) * 5))  # de-dupe journal to shifts
        if bucket != self._last_bucket:
            self._last_bucket = bucket
            mood = "เอนขึ้น" if self.bias > 0.15 else "เอนลง" if self.bias < -0.15 else "เป็นกลาง"
            self.learner.log(f"ฉันทามติฝ่าย{mood} ({self.bias:+.2f})", "event")

    def bias_value(self) -> float:
        return self.bias


# ── deterministic spec generation ───────────────────────────────────
def make_specs(n: int) -> list[tuple[str, str]]:
    """Spread methods across timeframes, deterministically, to exactly ``n``."""
    from domain.analytics.swarm_methods import METHOD_NAMES  # local: keep import graph flat

    out: list[tuple[str, str]] = []
    for tf in TIMEFRAMES:
        for method in METHOD_NAMES:
            out.append((tf, method))
            if len(out) >= n:
                return out
    while len(out) < n:  # only if methods×timeframes < n (not with the default set)
        out.append((TIMEFRAMES[len(out) % len(TIMEFRAMES)], METHOD_NAMES[len(out) % len(METHOD_NAMES)]))
    return out


def _entry_threshold(i: int) -> Decimal:
    """A spread of entry strictness across the 50 hunters (0.50 … 0.80)."""
    return Decimal("0.50") + Decimal(i % 6) * Decimal("0.06")


# ── factory: build the whole swarm (1 hub + 3 chiefs + 150 workers) ──
def build_swarm_agents(
    bus: EventBus,
    prices_topic: str,
    signals_topic: str,
    analysis_topic: str,
    logger: structlog.BoundLogger,
    *,
    per_division: int = 50,
) -> dict[str, AgentLike]:
    """Assemble the full analyst swarm. Returns name → agent (all real tasks)."""
    hub = MarketDataHub()
    agents: dict[str, AgentLike] = {"market_data_hub": MarketDataHubAgent(
        "market_data_hub", bus, prices_topic, hub, logger
    )}

    # Historical Chart Lab — completed candles (the past).
    hist_workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    for i, (tf, method) in enumerate(make_specs(per_division), start=1):
        name = f"hist_{i:02d}_{tf}_{method}"
        a = ChartAnalystAgent(name, hub, tf, method, "historical", logger)
        agents[name] = a
        hist_workers.append(a)
    hist_chief = DivisionChiefAgent(
        "historical_chief", hist_workers, bus, analysis_topic, "วิเคราะห์กราฟอดีต", logger
    )
    agents["historical_chief"] = hist_chief

    # Live Price Lab — includes the currently forming candle (the present).
    live_workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    for i, (tf, method) in enumerate(make_specs(per_division), start=1):
        name = f"live_{i:02d}_{tf}_{method}"
        a = ChartAnalystAgent(name, hub, tf, method, "live", logger)
        agents[name] = a
        live_workers.append(a)
    live_chief = DivisionChiefAgent(
        "live_chief", live_workers, bus, analysis_topic, "อ่านราคาปัจจุบัน", logger
    )
    agents["live_chief"] = live_chief

    # Entry Hunters — consult the average of the two analysis divisions' bias.
    def _entry_bias() -> float:
        return (hist_chief.bias + live_chief.bias) / 2.0

    entry_workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    for i, (tf, method) in enumerate(make_specs(per_division), start=1):
        name = f"entry_{i:02d}_{tf}_{method}"
        a2 = EntryHunterAgent(
            name, hub, tf, method, _entry_threshold(i), bus, signals_topic, _entry_bias, logger
        )
        agents[name] = a2
        entry_workers.append(a2)
    entry_chief = DivisionChiefAgent(
        "entry_chief", entry_workers, bus, analysis_topic, "หาจุดเข้าซื้อ", logger
    )
    agents["entry_chief"] = entry_chief

    return agents
