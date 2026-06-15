# Layer 3 — Infrastructure (perf/bench)
"""Performance benchmark harness for the hot paths.

Pure measurement over in-memory objects (no network/disk). Returns measured
numbers so the CLI (``scripts/bench.py``) can print a baseline and the perf
regression guard test can assert they stay within budget — making the NFR
"measurable" literally true.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from decimal import Decimal

from domain.backtest.engine import FeeModel, SlippageModel, run_backtest
from domain.risk.rules import RiskLimits
from domain.shared.money import THB, Money
from domain.strategy.base import SignalAction
from domain.strategy.confluence import EntryInputs, GateParams, evaluate_entry
from domain.strategy.ema_cross import EmaCrossStrategy
from infrastructure.eventbus.in_memory import InMemoryEventBus


@dataclass(frozen=True)
class BenchResult:
    """Measured throughput/latency of the benchmarked hot paths."""

    event_bus_msgs_per_sec: float
    backtest_bars_per_sec: float
    gate_latency_p50_us: float
    gate_latency_p95_us: float


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency=THB)


def bench_event_bus(n: int = 50_000) -> float:
    """Publish ``n`` messages through the in-memory bus; return msgs/sec."""

    async def _run() -> float:
        bus = InMemoryEventBus()
        queue = bus.subscribe("bench")
        payload = b'{"price":"1500000","ts_ms":1}'
        start = time.perf_counter()
        for _ in range(n):  # 1:1 publish→consume so the bounded queue never overflows
            await bus.publish("bench", b"k", payload)
            queue.get_nowait()
        dur = time.perf_counter() - start
        return n / dur if dur > 0 else 0.0

    return asyncio.run(_run())


def bench_backtest(bars: int = 5_000) -> float:
    """Run the event-driven backtest over ``bars`` bars; return bars/sec."""
    prices: list[tuple[int, Decimal]] = [
        (i * 1000, Decimal(1_000_000) + Decimal((i * 37) % 50_000)) for i in range(bars)
    ]
    limits = RiskLimits(
        max_order_qty=Decimal("1"), max_position_qty=Decimal("2"),
        max_daily_loss=_money("999999999"), max_drawdown_pct=Decimal("99"), kill_switch=False,
    )
    start = time.perf_counter()
    run_backtest(
        prices=prices, strategy=EmaCrossStrategy(fast=3, slow=5), limits=limits,
        fees=FeeModel(taker_bps=Decimal("10")), slippage=SlippageModel(slip_bps=Decimal("5")),
        initial_cash=_money("10000000"), order_qty=Decimal("0.001"),
    )
    dur = time.perf_counter() - start
    return bars / dur if dur > 0 else 0.0


def bench_gate_latency(n: int = 50_000) -> tuple[float, float]:
    """Measure the confluence entry-gate decision latency; return (p50, p95) µs."""
    inputs = EntryInputs(
        signal_action=SignalAction.BUY, signal_confidence=Decimal("1"),
        regime="TREND_UP", sentiment_score=Decimal("0"),
        p_win=Decimal("0.7"), p_win_samples=40, trend_agree=True,
    )
    params = GateParams()
    samples: list[float] = []
    for _ in range(n):
        start = time.perf_counter()
        evaluate_entry(inputs, params)
        samples.append((time.perf_counter() - start) * 1e6)
    samples.sort()
    p50 = samples[len(samples) // 2]
    p95 = samples[min(len(samples) - 1, int(len(samples) * 0.95))]
    return p50, p95


def run_all(scale: float = 1.0) -> BenchResult:
    """Run every benchmark at ``scale`` and return the combined result."""
    msgs = bench_event_bus(int(50_000 * scale))
    bars = bench_backtest(int(5_000 * scale))
    p50, p95 = bench_gate_latency(int(50_000 * scale))
    return BenchResult(msgs, bars, p50, p95)
