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

from domain.analytics.swarm_meta import SwarmMetaLearner
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
    """One method on one timeframe over a specific LOOKBACK WINDOW — its assigned
    slice of the chart (division of labour). Both modes read up to the CURRENT
    forming candle so a 'historical' analyst still catches the present trick; the
    difference is the window: 'historical' = deep context, 'live' = recent/fast.
    Grades its own calls against the real price that follows (its own memory)."""

    interval = 4.0

    def __init__(
        self,
        name: str,
        hub: MarketDataHub,
        timeframe: str,
        method: str,
        mode: str,  # "historical" (deep window) | "live" (short recent window)
        logger: structlog.BoundLogger,
        window: int | None = None,
    ) -> None:
        super().__init__(name, logger, kind="strategy")
        self._hub = hub
        self._tf = timeframe
        self._method = method
        self._mode = mode
        self._window = window
        self.read: AnalysisRead = AnalysisRead.neutral("เริ่มต้น")
        self.signal_count = 0

    @property
    def method(self) -> str:
        """The analysis method this grid agent runs (key for dynamic weighting)."""
        return self._method

    @property
    def timeframe(self) -> str:
        return self._tf

    def _hr_txt(self) -> str:
        hr = self.learner.hit_rate()
        return f"{hr * 100:.0f}% ({self.learner.resolved} ครั้ง)" if hr is not None else "—"

    async def tick(self) -> None:
        price, ts_ms = self._hub.latest()
        if price is not None:
            self.learner.resolve(price, ts_ms)
        # Always include the current candle (catch the present); the window
        # decides how much past context this analyst weighs (its assigned slice).
        candles = self._hub.series(self._tf, include_current=True)
        if self._window is not None and len(candles) > self._window:
            candles = candles[-self._window:]
        read = run_method(self._method, candles)
        self.read = read
        scope = "อดีต-ลึก" if self._mode == "historical" else "ปัจจุบัน-เร็ว"
        win = f"·{self._window}แท่ง" if self._window is not None else ""
        self.detail = (
            f"[{self._tf}·{self._method}·{scope}{win}] {read.label} → {read.direction} "
            f"({float(read.strength) * 100:.0f}%) · แม่น {self._hr_txt()}"
        )
        if price is not None and read.direction in (BULL, BEAR) and read.strength >= _ACT_STRENGTH:
            action = "BUY" if read.direction == BULL else "SELL"
            self.learner.predict(action, price, ts_ms)
            self.signal_count += 1


# ── entry hunter (advisory scout — the Entry Chief consolidates) ─────
class EntryHunterAgent(PeriodicAgent):
    """Scouts a buy entry on its slice and raises a ``ready`` flag when its
    method is bullish enough AND the division bias agrees. It does NOT emit to
    the signal bus itself — the Entry Chief consolidates all 50 scouts into ONE
    coordinated BUY, which keeps the pipeline smooth (no 50-way signal flood)."""

    interval = 3.0

    def __init__(
        self,
        name: str,
        hub: MarketDataHub,
        timeframe: str,
        method: str,
        threshold: Decimal,
        bias_provider: Callable[[], float],
        logger: structlog.BoundLogger,
    ) -> None:
        super().__init__(name, logger, kind="strategy")
        self._hub = hub
        self._tf = timeframe
        self._method = method
        self._threshold = threshold
        self._bias_provider = bias_provider
        self.read: AnalysisRead = AnalysisRead.neutral("เริ่มต้น")
        self.ready = False
        self._was_ready = False
        self.signal_count = 0
        self.entries_found = 0

    @property
    def method(self) -> str:
        """The analysis method this grid agent runs (key for dynamic weighting)."""
        return self._method

    @property
    def timeframe(self) -> str:
        return self._tf

    def _hr_txt(self) -> str:
        hr = self.learner.hit_rate()
        return f"{hr * 100:.0f}% ({self.learner.resolved} ครั้ง)" if hr is not None else "—"

    async def tick(self) -> None:
        price, ts_ms = self._hub.latest()
        if price is not None:
            self.learner.resolve(price, ts_ms)
        candles = self._hub.series(self._tf, include_current=True)
        read = run_method(self._method, candles)
        self.read = read
        bias = self._bias_provider()
        self.ready = read.direction == BULL and read.strength >= self._threshold and bias >= 0.0
        self.detail = (
            f"[{self._tf}·{self._method}] {read.label} · ฉันทามติ {bias:+.2f} "
            f"· แม่น {self._hr_txt()}" + (" · 🎯 พร้อมเข้า" if self.ready else " · เฝ้ารอจังหวะ")
        )
        # Edge-triggered self-learning: record a prediction only on a NEW ready
        # episode so the scout grades itself without spamming.
        if self.ready and not self._was_ready and price is not None:
            self.learner.predict("BUY", price, ts_ms)
            self.signal_count += 1
            self.entries_found += 1
        self._was_ready = self.ready


# ── division chief (aggregates 50 workers → consensus bias) ──────────
class DivisionChiefAgent(PeriodicAgent):
    """Reads its workers' latest verdicts, computes a consensus bias in [-1,1],
    and publishes it so the rest of the swarm can coordinate.

    Task 3 — dynamic weighting: when a :class:`SwarmMetaLearner` is wired in, the
    consensus is no longer an equal-weight headcount. Each worker's vote is scaled
    by its method's MEASURED reliability *in the current regime* (graded from real
    price outcomes the workers self-score). The swarm thus naturally leans on the
    grid agents that are actually winning under the conditions at hand — true,
    LLM-free consensus that adapts as the regime shifts. With no meta-learner the
    original equal-weight behaviour is preserved (back-compat for tests).
    """

    interval = 3.0

    def __init__(
        self,
        name: str,
        workers: list[ChartAnalystAgent | EntryHunterAgent],
        bus: EventBus,
        analysis_topic: str,
        label: str,
        logger: structlog.BoundLogger,
        meta: SwarmMetaLearner | None = None,
        regime_provider: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(name, logger, kind="reliability")
        self._workers = workers
        self._bus = bus
        self._analysis_topic = analysis_topic
        self._label = label
        self.bias: float = 0.0
        self._last_bucket = 99
        # Dynamic-weighting machinery (Task 3). ``meta`` is shared across the
        # divisions so reliability accrues per (method, regime) for the whole grid.
        self.meta = meta
        self._regime_provider = regime_provider
        # Last seen (resolved, correct) per worker, to record only NEW outcomes
        # into the meta-learner each tick (deltas, not the running totals).
        self._seen: dict[str, tuple[int, int]] = {}

    def _record_outcomes(self, regime: str) -> None:
        """Feed each worker's newly-graded predictions into the shared meta-learner
        as (method, regime) Win/Loss outcomes — the real signal the weights learn
        from. Bounded, deterministic, no I/O."""
        meta = self.meta
        if meta is None:
            return
        for w in self._workers:
            resolved = w.learner.resolved
            correct = w.learner.correct
            prev_r, prev_c = self._seen.get(w.name, (0, 0))
            d_resolved = resolved - prev_r
            d_correct = correct - prev_c
            if d_resolved > 0:
                wins = max(0, min(d_resolved, d_correct))
                for _ in range(wins):
                    meta.record(w.method, regime, won=True)
                for _ in range(d_resolved - wins):
                    meta.record(w.method, regime, won=False)
            self._seen[w.name] = (resolved, correct)

    def _weighted_bias(self, regime: str) -> float:
        """Reliability-weighted net bias in [-1, 1]. Equal-weight if no meta."""
        meta = self.meta
        num = 0.0
        den = 0.0
        for w in self._workers:
            weight = float(meta.weight(w.method, regime)) if meta is not None else 1.0
            direction = (
                1.0 if w.read.direction == BULL
                else -1.0 if w.read.direction == BEAR
                else 0.0
            )
            num += weight * direction
            den += weight
        return num / den if den else 0.0

    async def tick(self) -> None:
        regime = self._regime_provider() if self._regime_provider is not None else "RANGE"
        self._record_outcomes(regime)
        bulls = sum(1 for w in self._workers if w.read.direction == BULL)
        bears = sum(1 for w in self._workers if w.read.direction == BEAR)
        total = len(self._workers)
        neutrals = total - bulls - bears
        self.bias = self._weighted_bias(regime)
        weighted = self.meta is not None
        tag = f" · ถ่วงน้ำหนักตาม regime {regime}" if weighted else ""
        self.detail = (
            f"{self._label}: 🟢{bulls} 🔴{bears} ⚪{neutrals} → ฉันทามติ {self.bias:+.2f}{tag}"
        )
        out = orjson.dumps(
            {
                "division": self.name,
                "bias": f"{self.bias:.4f}",
                "bulls": bulls,
                "bears": bears,
                "neutral": neutrals,
                "weighted": weighted,
                "regime": regime,
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


# ── entry chief (consolidates 50 scouts → one coordinated BUY) ───────
class EntryChiefAgent(DivisionChiefAgent):
    """Aggregates the entry scouts and emits ONE coordinated BUY to the signal
    bus when a quorum of scouts are ready AND the division is net-bullish.
    Edge-triggered (re-arms only after the consensus clears) so the pipeline
    receives at most one BUY per bullish episode — smooth, not a 50-way flood."""

    def __init__(
        self,
        name: str,
        scouts: list[ChartAnalystAgent | EntryHunterAgent],
        hub: MarketDataHub,
        bus: EventBus,
        analysis_topic: str,
        signals_topic: str,
        label: str,
        logger: structlog.BoundLogger,
        quorum_frac: float = 0.25,
        meta: SwarmMetaLearner | None = None,
        regime_provider: Callable[[], str] | None = None,
    ) -> None:
        super().__init__(
            name, scouts, bus, analysis_topic, label, logger,
            meta=meta, regime_provider=regime_provider,
        )
        self._hub = hub
        self._signals_topic = signals_topic
        self._quorum = max(1, int(len(scouts) * quorum_frac))
        self._armed = True
        self.buys_emitted = 0

    async def tick(self) -> None:
        await super().tick()  # refresh consensus bias + publish analysis
        ready = sum(1 for w in self._workers if getattr(w, "ready", False))
        price, ts_ms = self._hub.latest()
        fire = ready >= self._quorum and self.bias > 0.0
        if fire and self._armed and price is not None:
            out = orjson.dumps(
                {"signal": "BUY", "price": str(price), "ts_ms": ts_ms, "source": self.name}
            )
            await self._bus.publish(self._signals_topic, b"signal", out)
            self._armed = False
            self.buys_emitted += 1
            self.learner.log(
                f"สั่งซื้อรวม: {ready}/{len(self._workers)} พรานพร้อม (bias {self.bias:+.2f})", "event"
            )
        elif not fire:
            self._armed = True  # re-arm once the consensus clears
        self.detail = (
            f"{self._label}: พร้อมเข้า {ready}/{len(self._workers)} (เกณฑ์ {self._quorum}) "
            f"· bias {self.bias:+.2f} · ยิงซื้อไปแล้ว {self.buys_emitted} ครั้ง"
        )


# ── deterministic spec generation ───────────────────────────────────
def make_specs(n: int) -> list[tuple[str, str]]:
    """Divide the chart-watching evenly: round-robin the timeframes while
    cycling methods, so every timeframe gets a balanced share and no two
    analysts watch the same (timeframe, method) slice until all are used.
    Deterministic, exactly ``n`` specs."""
    from domain.analytics.swarm_methods import METHOD_NAMES  # local: keep import graph flat

    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    method_idx = 0
    while len(out) < n:
        tf = TIMEFRAMES[len(out) % len(TIMEFRAMES)]
        # advance the method every full sweep of the timeframes
        method = METHOD_NAMES[method_idx % len(METHOD_NAMES)]
        if len(out) % len(TIMEFRAMES) == len(TIMEFRAMES) - 1:
            method_idx += 1
        spec = (tf, method)
        # keep slices distinct where possible (fall back to allow once exhausted)
        if spec in seen and len(seen) < len(TIMEFRAMES) * len(METHOD_NAMES):
            method_idx += 1
            continue
        seen.add(spec)
        out.append(spec)
    return out


# Lookback windows (in candles) — the historical division weighs DEEP context,
# the live division reacts to a SHORT recent window. Cycled across the 50 so
# each analyst owns a distinct depth as well as a distinct (timeframe, method).
_HIST_WINDOWS: list[int] = [300, 240, 180, 120]
_LIVE_WINDOWS: list[int] = [60, 45, 30, 20]


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
    meta: SwarmMetaLearner | None = None,
    regime_provider: Callable[[], str] | None = None,
) -> dict[str, AgentLike]:
    """Assemble the full analyst swarm. Returns name → agent (all real tasks).

    Task 3: ``meta`` (a shared :class:`SwarmMetaLearner`) and ``regime_provider``
    enable regime-aware dynamic weighting across the whole 150-agent parameter
    grid — each division chief weights its workers by their method's measured
    reliability in the current regime. Defaults (None) keep equal-weight voting.
    """
    hub = MarketDataHub()
    agents: dict[str, AgentLike] = {"market_data_hub": MarketDataHubAgent(
        "market_data_hub", bus, prices_topic, hub, logger
    )}

    # Historical Chart Lab — each analyst owns a distinct (timeframe, method)
    # slice with a DEEP lookback window (past context) but still reads up to the
    # present candle so it also catches the current trick.
    hist_workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    for i, (tf, method) in enumerate(make_specs(per_division), start=1):
        name = f"hist_{i:02d}_{tf}_{method}"
        window = _HIST_WINDOWS[(i - 1) % len(_HIST_WINDOWS)]
        a = ChartAnalystAgent(name, hub, tf, method, "historical", logger, window=window)
        agents[name] = a
        hist_workers.append(a)
    hist_chief = DivisionChiefAgent(
        "historical_chief", hist_workers, bus, analysis_topic, "วิเคราะห์กราฟอดีต", logger,
        meta=meta, regime_provider=regime_provider,
    )
    agents["historical_chief"] = hist_chief

    # Live Price Lab — same slices but a SHORT recent window: fast present read.
    live_workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    for i, (tf, method) in enumerate(make_specs(per_division), start=1):
        name = f"live_{i:02d}_{tf}_{method}"
        window = _LIVE_WINDOWS[(i - 1) % len(_LIVE_WINDOWS)]
        a = ChartAnalystAgent(name, hub, tf, method, "live", logger, window=window)
        agents[name] = a
        live_workers.append(a)
    live_chief = DivisionChiefAgent(
        "live_chief", live_workers, bus, analysis_topic, "อ่านราคาปัจจุบัน", logger,
        meta=meta, regime_provider=regime_provider,
    )
    agents["live_chief"] = live_chief

    # Entry Hunters — consult the average of the two analysis divisions' bias.
    def _entry_bias() -> float:
        return (hist_chief.bias + live_chief.bias) / 2.0

    entry_workers: list[ChartAnalystAgent | EntryHunterAgent] = []
    for i, (tf, method) in enumerate(make_specs(per_division), start=1):
        name = f"entry_{i:02d}_{tf}_{method}"
        a2 = EntryHunterAgent(
            name, hub, tf, method, _entry_threshold(i), _entry_bias, logger
        )
        agents[name] = a2
        entry_workers.append(a2)
    # The Entry Chief is the SINGLE emitter for the whole entry division: it
    # consolidates its 50 scouts into one coordinated, edge-triggered BUY.
    entry_chief = EntryChiefAgent(
        "entry_chief", entry_workers, hub, bus, analysis_topic, signals_topic,
        "หาจุดเข้าซื้อ", logger, meta=meta, regime_provider=regime_provider,
    )
    agents["entry_chief"] = entry_chief

    return agents
